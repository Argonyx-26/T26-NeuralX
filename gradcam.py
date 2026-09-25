import base64
import io
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import matplotlib.cm as cm

class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.target_layer = target_layer
        self.gradients = None
        self.activations = None
        
        # Register hooks
        self.target_layer.register_forward_hook(self._save_activation)
        self.target_layer.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, module, input, output):
        self.activations = output.detach()

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate_heatmap(self, input_tensor: torch.Tensor, class_idx: int) -> np.ndarray:
        self.model.zero_grad()
        output = self.model(input_tensor)
        
        if class_idx is None:
            class_idx = torch.argmax(output, dim=1).item()
            
        score = output[0, class_idx]
        score.backward()
        
        # Pool the gradients across the channels
        pooled_gradients = torch.mean(self.gradients, dim=[0, 2, 3])
        
        # Weight the channels by corresponding gradients
        activations = self.activations[0]
        for i in range(activations.shape[0]):
            activations[i, :, :] *= pooled_gradients[i]
            
        heatmap = torch.mean(activations, dim=0).squeeze()
        heatmap = F.relu(heatmap)
        heatmap = heatmap.cpu().numpy()
        
        # Normalize heatmap between 0 and 1
        max_val = np.max(heatmap)
        if max_val > 1e-8:
            heatmap = heatmap / max_val
        else:
            heatmap = np.zeros_like(heatmap)
            
        return heatmap

def overlay_gradcam(original_pil: Image.Image, heatmap: np.ndarray, alpha: float = 0.4) -> str:
    """
    Overlays Grad-CAM heatmap on the original image and returns a base64-encoded PNG.
    """
    # Resize heatmap to match original image dimensions
    heatmap_pil = Image.fromarray(np.uint8(255 * heatmap)).resize(original_pil.size, Image.Resampling.BILINEAR)
    heatmap_norm = np.array(heatmap_pil) / 255.0
    
    # Apply JET colormap
    colormap = cm.get_cmap("jet")
    colored_heatmap = colormap(heatmap_norm)[:, :, :3]  # Drop alpha channel
    colored_heatmap = np.uint8(255 * colored_heatmap)
    
    orig_np = np.array(original_pil.convert("RGB"))
    
    # Blend overlay
    blended = np.uint8((1.0 - alpha) * orig_np + alpha * colored_heatmap)
    blended_pil = Image.fromarray(blended)
    
    # Convert to base64 string
    buffered = io.BytesIO()
    blended_pil.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return img_str
