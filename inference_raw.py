import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
from pathlib import Path
from typing import Union, Tuple
import os

BASE_DIR = Path(__file__).parent.resolve()
MODEL_PATH = BASE_DIR / "models" / "mobilenet_v2_tomato.pth"

_CLASS_NAMES = ["Tomato___Early_blight", "Tomato___healthy"]
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL = None

_TRANSFORM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

def load_raw_model():
    global _MODEL
    if _MODEL is None:
        model = models.mobilenet_v2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, len(_CLASS_NAMES))
        
        checkpoint = torch.load(MODEL_PATH, map_location=_DEVICE, weights_only=True)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(_DEVICE)
        model.eval()
        _MODEL = model
    return _MODEL

def predict(image: Union[str, Path, Image.Image]) -> Tuple[str, float]:
    """
    Takes an image (file path or PIL Image object) and returns:
    (disease_label, raw_confidence) using raw softmax confidence.
    """
    model = load_raw_model()
    
    if isinstance(image, (str, Path)):
        img = Image.open(image).convert("RGB")
    elif isinstance(image, Image.Image):
        img = image.convert("RGB")
    else:
        raise ValueError(f"Unsupported image type: {type(image)}")
        
    tensor = _TRANSFORM(img).unsqueeze(0).to(_DEVICE)
    
    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0)
        conf, pred_idx = torch.max(probabilities, dim=0)
        
    return _CLASS_NAMES[pred_idx.item()], float(conf.item())

if __name__ == "__main__":
    import random
    
    test_dir = BASE_DIR / "data" / "test"
    sample_eb = list((test_dir / "Tomato___Early_blight").glob("*.*"))[:3]
    sample_h = list((test_dir / "Tomato___healthy").glob("*.*"))[:3]
    
    print("=== Raw Prediction Test on Test Set Samples ===")
    for img_path in sample_eb + sample_h:
        label, conf = predict(img_path)
        actual = img_path.parent.name
        print(f"File: {img_path.name:<30} | Actual: {actual:<22} | Predicted: {label:<22} | Raw Softmax Conf: {conf*100:.2f}%")
