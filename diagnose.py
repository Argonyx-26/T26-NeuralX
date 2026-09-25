import json
import io
import os
from pathlib import Path
from typing import Union, Dict, Any, Optional
from PIL import Image
import torch
import torch.nn as nn
from torchvision import transforms, models

try:
    from .gradcam import GradCAM, overlay_gradcam
except ImportError:
    from gradcam import GradCAM, overlay_gradcam

BASE_DIR = Path(__file__).parent.resolve()
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "mobilenet_v2_tomato.pth"
CALIBRATION_META_PATH = MODELS_DIR / "calibration.json"

_CLASS_NAMES = ["Tomato___Early_blight", "Tomato___healthy"]
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_TRANSFORM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

class TomatoDiagnosticService:
    def __init__(self):
        self.model = None
        self.temperature = 1.0
        self.gradcam = None
        self._initialize()

    def _initialize(self):
        # 1. Load MobileNetV2 architecture
        model = models.mobilenet_v2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, len(_CLASS_NAMES))
        
        # 2. Load trained checkpoint weights
        checkpoint = torch.load(MODEL_PATH, map_location=_DEVICE, weights_only=True)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(_DEVICE)
        model.eval()
        self.model = model
        
        # 3. Load learned temperature
        if CALIBRATION_META_PATH.exists():
            with open(CALIBRATION_META_PATH, "r") as f:
                meta = json.load(f)
                self.temperature = float(meta.get("temperature", 1.0))
        else:
            self.temperature = 1.0
            
        # 4. Attach Grad-CAM to the final feature extraction layer
        target_layer = self.model.features[-1]
        self.gradcam = GradCAM(self.model, target_layer)

    def diagnose(
        self,
        image: Union[str, Path, Image.Image, bytes, io.BytesIO],
        confidence_threshold: float = 0.65
    ) -> Dict[str, Any]:
        """
        Diagnoses a tomato leaf image.
        
        Parameters:
            image: File path, PIL Image, raw bytes, or BytesIO.
            confidence_threshold: Minimum calibrated confidence required (default 0.65).
            
        Returns:
            Dictionary matching the KrishiRaksha Component 3 handoff contract:
            {
                "disease_class": str | None,
                "calibrated_confidence": float | None,
                "needs_second_photo": bool,
                "gradcam_image_base64": str | None,
                "reason": str | None
            }
        """
        # Load & parse image
        try:
            if isinstance(image, (str, Path)):
                pil_img = Image.open(image)
            elif isinstance(image, bytes):
                pil_img = Image.open(io.BytesIO(image))
            elif isinstance(image, io.BytesIO):
                pil_img = Image.open(image)
            elif isinstance(image, Image.Image):
                pil_img = image
            else:
                return {
                    "disease_class": None,
                    "calibrated_confidence": None,
                    "needs_second_photo": True,
                    "gradcam_image_base64": None,
                    "reason": f"Invalid image input type: {type(image)}"
                }
            
            # Apply EXIF rotation for smartphone photos and verify image payload
            from PIL import ImageOps
            pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
            pil_img.load()  # Force decoding immediately to catch truncated / corrupted streams
        except Exception as e:
            return {
                "disease_class": None,
                "calibrated_confidence": None,
                "needs_second_photo": True,
                "gradcam_image_base64": None,
                "reason": f"Image decoding error: {str(e)}"
            }

        input_tensor = _TRANSFORM(pil_img).unsqueeze(0).to(_DEVICE)
        
        # 1. Forward pass for calibrated probability
        with torch.no_grad():
            raw_logits = self.model(input_tensor)
            calibrated_logits = raw_logits / self.temperature
            calibrated_probs = torch.softmax(calibrated_logits, dim=1).squeeze(0)
            best_conf, best_idx = torch.max(calibrated_probs, dim=0)
            
        calibrated_conf_val = float(best_conf.item())
        predicted_class = _CLASS_NAMES[best_idx.item()]
        
        # 2. Low-confidence safeguard
        if calibrated_conf_val < confidence_threshold:
            return {
                "disease_class": None,
                "calibrated_confidence": round(calibrated_conf_val, 4),
                "needs_second_photo": True,
                "gradcam_image_base64": None,
                "reason": (
                    f"Calibrated confidence ({calibrated_conf_val*100:.1f}%) is below the safety threshold "
                    f"({confidence_threshold*100:.1f}%). Please send another, clearer photo taken in good lighting."
                )
            }
            
        # 3. Confident diagnosis -> Generate Grad-CAM explanation overlay
        try:
            heatmap = self.gradcam.generate_heatmap(input_tensor, class_idx=best_idx.item())
            gradcam_b64 = overlay_gradcam(pil_img, heatmap)
        except Exception as e:
            gradcam_b64 = None
            
        return {
            "disease_class": predicted_class,
            "calibrated_confidence": round(calibrated_conf_val, 4),
            "needs_second_photo": False,
            "gradcam_image_base64": gradcam_b64,
            "reason": None
        }

# Singleton instance
_SERVICE = None

def get_service() -> TomatoDiagnosticService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TomatoDiagnosticService()
    return _SERVICE

def diagnose_leaf(
    image: Union[str, Path, Image.Image, bytes, io.BytesIO],
    confidence_threshold: float = 0.65
) -> Dict[str, Any]:
    """
    Public entry point for Person 1 (Backend / FastAPI).
    Exclusively returns calibrated confidence and never exposes raw softmax.
    """
    service = get_service()
    return service.diagnose(image, confidence_threshold=confidence_threshold)
