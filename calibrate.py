import json
from pathlib import Path
from typing import Union, Tuple
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from scipy.optimize import minimize_scalar

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "mobilenet_v2_tomato.pth"
CALIBRATION_META_PATH = MODELS_DIR / "calibration.json"
RELIABILITY_PLOT_PATH = BASE_DIR / "reliability_diagram.png"

_CLASS_NAMES = ["Tomato___Early_blight", "Tomato___healthy"]
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def compute_ece(logits: torch.Tensor, labels: torch.Tensor, n_bins: int = 10) -> float:
    """
    Computes Expected Calibration Error (ECE) as defined in Guo et al., ICML 2017.
    """
    softmaxes = torch.softmax(logits, dim=1)
    confidences, predictions = torch.max(softmaxes, 1)
    accuracies = predictions.eq(labels)

    ece = torch.zeros(1, device=logits.device)
    bin_boundaries = torch.linspace(0, 1, n_bins + 1, device=logits.device)

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        in_bin = (confidences > bin_lower.item()) & (confidences <= bin_upper.item())
        prop_in_bin = in_bin.float().mean()
        
        if prop_in_bin.item() > 0:
            accuracy_in_bin = accuracies[in_bin].float().mean()
            avg_confidence_in_bin = confidences[in_bin].mean()
            ece += torch.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin

    return float(ece.item())

def get_bin_stats(logits: torch.Tensor, labels: torch.Tensor, n_bins: int = 10):
    softmaxes = torch.softmax(logits, dim=1)
    confidences, predictions = torch.max(softmaxes, 1)
    accuracies = predictions.eq(labels)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_accs = []
    bin_confs = []
    bin_counts = []
    
    conf_np = confidences.cpu().numpy()
    acc_np = accuracies.cpu().numpy()
    
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (conf_np > bin_lower) & (conf_np <= bin_upper)
        count = int(np.sum(in_bin))
        bin_counts.append(count)
        if count > 0:
            bin_accs.append(float(acc_np[in_bin].mean()))
            bin_confs.append(float(conf_np[in_bin].mean()))
        else:
            bin_accs.append(0.0)
            bin_confs.append((bin_lower + bin_upper) / 2.0)
            
    return bin_boundaries, np.array(bin_accs), np.array(bin_confs), np.array(bin_counts)

def plot_reliability_diagram(raw_logits: torch.Tensor, cal_logits: torch.Tensor, labels: torch.Tensor, T_val: float, save_path: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=150)
    
    raw_ece = compute_ece(raw_logits, labels)
    cal_ece = compute_ece(cal_logits, labels)
    
    bins, acc_raw, conf_raw, counts_raw = get_bin_stats(raw_logits, labels)
    _, acc_cal, conf_cal, counts_cal = get_bin_stats(cal_logits, labels)
    
    bin_centers = (bins[:-1] + bins[1:]) / 2.0
    width = 0.075
    
    # 1. Uncalibrated Plot
    ax1.plot([0, 1], [0, 1], "--", color="navy", linewidth=1.5, label="Perfect Calibration (y=x)")
    bars1 = ax1.bar(bin_centers, acc_raw, width=width, alpha=0.75, color="#e74c3c", edgecolor="black", label="Empirical Accuracy")
    ax1.plot(bin_centers, conf_raw, "o-", color="#962d22", linewidth=2, markersize=5, label="Mean Confidence")
    ax1.set_title(f"Uncalibrated (Raw Softmax, T=1.000)\nTest ECE: {raw_ece*100:.2f}%", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Confidence Bin", fontsize=11)
    ax1.set_ylabel("Empirical Accuracy", fontsize=11)
    ax1.set_xlim(0, 1.02)
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left")
    
    for bar, count in zip(bars1, counts_raw):
        if count > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., min(bar.get_height() + 0.02, 1.01), f"n={count}",
                     ha='center', va='bottom', fontsize=8, rotation=45)
    
    # 2. Calibrated Plot
    ax2.plot([0, 1], [0, 1], "--", color="navy", linewidth=1.5, label="Perfect Calibration (y=x)")
    bars2 = ax2.bar(bin_centers, acc_cal, width=width, alpha=0.75, color="#27ae60", edgecolor="black", label="Empirical Accuracy")
    ax2.plot(bin_centers, conf_cal, "o-", color="#196f3d", linewidth=2, markersize=5, label="Mean Confidence")
    ax2.set_title(f"Temperature Calibrated (T={T_val:.3f})\nTest ECE: {cal_ece*100:.2f}%", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Confidence Bin", fontsize=11)
    ax2.set_ylabel("Empirical Accuracy", fontsize=11)
    ax2.set_xlim(0, 1.02)
    ax2.set_ylim(0, 1.05)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left")
    
    for bar, count in zip(bars2, counts_cal):
        if count > 0:
            ax2.text(bar.get_x() + bar.get_width()/2., min(bar.get_height() + 0.02, 1.01), f"n={count}",
                     ha='center', va='bottom', fontsize=8, rotation=45)
    
    plt.suptitle("KrishiRaksha Tomato Model: Reliability Diagram Comparison (Guo et al. ICML 2017)", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    print(f"Reliability diagram saved to {save_path}")

def optimize_temperature(val_logits: torch.Tensor, val_labels: torch.Tensor) -> float:
    """
    Finds optimal scalar temperature T > 0 by minimizing CrossEntropyLoss (NLL) on validation set.
    """
    criterion = nn.CrossEntropyLoss()
    
    def loss_func(T_val):
        scaled_logits = val_logits / float(T_val)
        return criterion(scaled_logits, val_labels).item()
        
    res = minimize_scalar(loss_func, bounds=(0.05, 10.0), method='bounded')
    optimal_T = float(res.x)
    return optimal_T

_TRANSFORM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

_TEMPERATURE = None
_BASE_MODEL = None

def load_calibrated_model():
    global _BASE_MODEL, _TEMPERATURE
    if _BASE_MODEL is None:
        model = models.mobilenet_v2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, len(_CLASS_NAMES))
        
        checkpoint = torch.load(MODEL_PATH, map_location=_DEVICE, weights_only=True)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(_DEVICE)
        model.eval()
        _BASE_MODEL = model
        
        if CALIBRATION_META_PATH.exists():
            with open(CALIBRATION_META_PATH, "r") as f:
                meta = json.load(f)
                _TEMPERATURE = float(meta.get("temperature", 1.0))
        else:
            _TEMPERATURE = 1.0
            
    return _BASE_MODEL, _TEMPERATURE

def predict_calibrated(image: Union[str, Path, Image.Image]) -> Tuple[str, float]:
    """
    Takes an image (file path or PIL Image) and returns:
    (disease_label, calibrated_confidence)
    Guarantees only calibrated confidence is exposed.
    """
    model, temperature = load_calibrated_model()
    
    if isinstance(image, (str, Path)):
        img = Image.open(image).convert("RGB")
    elif isinstance(image, Image.Image):
        img = image.convert("RGB")
    else:
        raise ValueError(f"Unsupported image type: {type(image)}")
        
    tensor = _TRANSFORM(img).unsqueeze(0).to(_DEVICE)
    
    with torch.no_grad():
        raw_logits = model(tensor)
        calibrated_logits = raw_logits / temperature
        calibrated_probs = torch.softmax(calibrated_logits, dim=1).squeeze(0)
        conf, pred_idx = torch.max(calibrated_probs, dim=0)
        
    return _CLASS_NAMES[pred_idx.item()], float(conf.item())

def run_calibration_pipeline():
    eval_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    
    val_dataset = datasets.ImageFolder(DATA_DIR / "val", transform=eval_transform)
    test_dataset = datasets.ImageFolder(DATA_DIR / "test", transform=eval_transform)
    
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=0)
    
    base_model = models.mobilenet_v2(weights=None)
    base_model.classifier[1] = nn.Linear(base_model.classifier[1].in_features, len(_CLASS_NAMES))
    checkpoint = torch.load(MODEL_PATH, map_location=_DEVICE, weights_only=True)
    base_model.load_state_dict(checkpoint['model_state_dict'])
    base_model.to(_DEVICE)
    base_model.eval()
    
    # Collect validation logits
    val_logits_list = []
    val_labels_list = []
    with torch.no_grad():
        for input, label in val_loader:
            input = input.to(_DEVICE)
            logits = base_model(input)
            val_logits_list.append(logits)
            val_labels_list.append(label)
        val_raw_logits = torch.cat(val_logits_list).to(_DEVICE)
        val_labels = torch.cat(val_labels_list).to(_DEVICE)
        
    criterion = nn.CrossEntropyLoss()
    val_nll_before = criterion(val_raw_logits, val_labels).item()
    val_ece_before = compute_ece(val_raw_logits, val_labels)
    
    T = optimize_temperature(val_raw_logits, val_labels)
    
    val_cal_logits = val_raw_logits / T
    val_nll_after = criterion(val_cal_logits, val_labels).item()
    val_ece_after = compute_ece(val_cal_logits, val_labels)
    
    print("=== Validation Set Calibration Results ===")
    print(f"Optimal Learned Temperature T: {T:.4f}")
    print(f"Val NLL: Before (T=1.000) = {val_nll_before:.4f} | After (T={T:.4f}) = {val_nll_after:.4f}")
    print(f"Val ECE: Before (T=1.000) = {val_ece_before*100:.2f}% | After (T={T:.4f}) = {val_ece_after*100:.2f}%")
    
    # Collect test logits
    test_logits_list = []
    test_labels_list = []
    with torch.no_grad():
        for input, label in test_loader:
            input = input.to(_DEVICE)
            logits = base_model(input)
            test_logits_list.append(logits)
            test_labels_list.append(label)
        test_raw_logits = torch.cat(test_logits_list).to(_DEVICE)
        test_labels = torch.cat(test_labels_list).to(_DEVICE)
        
    test_cal_logits = test_raw_logits / T
    test_nll_before = criterion(test_raw_logits, test_labels).item()
    test_nll_after = criterion(test_cal_logits, test_labels).item()
    test_ece_before = compute_ece(test_raw_logits, test_labels)
    test_cal_ece = compute_ece(test_cal_logits, test_labels)
    
    print("\n=== Test Set Calibration Results ===")
    print(f"Test NLL: Before (T=1.000) = {test_nll_before:.4f} | After (T={T:.4f}) = {test_nll_after:.4f}")
    print(f"Test ECE: Before (T=1.000) = {test_ece_before*100:.2f}% | After (T={T:.4f}) = {test_cal_ece*100:.2f}%")
    
    with open(CALIBRATION_META_PATH, "w") as f:
        json.dump({
            "temperature": float(T),
            "val_nll_before": float(val_nll_before),
            "val_nll_after": float(val_nll_after),
            "val_ece_before": float(val_ece_before),
            "val_ece_after": float(val_ece_after),
            "test_nll_before": float(test_nll_before),
            "test_nll_after": float(test_nll_after),
            "test_ece_before": float(test_ece_before),
            "test_ece_after": float(test_cal_ece)
        }, f, indent=2)
        
    plot_reliability_diagram(test_raw_logits, test_cal_logits, test_labels, T, RELIABILITY_PLOT_PATH)

if __name__ == "__main__":
    run_calibration_pipeline()
