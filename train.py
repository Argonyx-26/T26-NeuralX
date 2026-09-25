import os
import json
import time
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
from torchvision.models import MobileNet_V2_Weights
from sklearn.metrics import confusion_matrix, classification_report
import numpy as np

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Set seed
torch.manual_seed(42)
np.random.seed(42)

def get_data_loaders(batch_size=32):
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
    
    train_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        normalize
    ])
    
    eval_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        normalize
    ])
    
    train_dataset = datasets.ImageFolder(DATA_DIR / "train", transform=train_transform)
    val_dataset = datasets.ImageFolder(DATA_DIR / "val", transform=eval_transform)
    test_dataset = datasets.ImageFolder(DATA_DIR / "test", transform=eval_transform)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    
    class_names = train_dataset.classes
    print(f"Class mapping: {train_dataset.class_to_idx}")
    
    return train_loader, val_loader, test_loader, class_names

def train_mobilenet():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    train_loader, val_loader, test_loader, class_names = get_data_loaders()
    
    # Load pretrained MobileNetV2
    print("Loading pretrained MobileNetV2...")
    model = models.mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT)
    
    # Freeze all feature extraction layers
    for param in model.features.parameters():
        param.requires_grad = False
        
    # Replace final classification head
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, len(class_names))
    
    # Verify trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total params: {total_params:,} | Trainable params: {trainable_params:,} (only final classification layer)")
    
    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.classifier[1].parameters(), lr=0.001)
    
    num_epochs = 5
    best_val_acc = 0.0
    best_weights_path = MODELS_DIR / "mobilenet_v2_tomato.pth"
    
    print("\n--- Starting Fine-Tuning ---")
    for epoch in range(1, num_epochs + 1):
        start_t = time.time()
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item() * images.size(0)
            _, preds = torch.max(outputs, 1)
            correct += torch.sum(preds == labels.data).item()
            total += labels.size(0)
            
        train_loss = running_loss / total
        train_acc = correct / total
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                _, preds = torch.max(outputs, 1)
                val_correct += torch.sum(preds == labels.data).item()
                val_total += labels.size(0)
                
        val_loss = val_loss / val_total
        val_acc = val_correct / val_total
        epoch_time = time.time() - start_t
        
        print(f"Epoch {epoch}/{num_epochs} [{epoch_time:.1f}s] - Train Loss: {train_loss:.4f} Acc: {train_acc*100:.2f}% | Val Loss: {val_loss:.4f} Acc: {val_acc*100:.2f}%")
        
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save({
                'model_state_dict': model.state_dict(),
                'class_names': class_names,
                'val_acc': val_acc
            }, best_weights_path)
            
    print(f"\nBest model saved to {best_weights_path} with Val Acc: {best_val_acc*100:.2f}%")
    
    # Load best weights for evaluation on test set
    checkpoint = torch.load(best_weights_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    print("\n--- Evaluating on Test Set ---")
    all_preds = []
    all_labels = []
    all_probs = []
    
    with torch.no_grad():
        for images, labels in test_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            probs = torch.softmax(outputs, dim=1)
            _, preds = torch.max(outputs, 1)
            
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())
            
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    test_acc = np.mean(all_preds == all_labels)
    
    cm = confusion_matrix(all_labels, all_preds)
    report = classification_report(all_labels, all_preds, target_names=class_names, digits=4)
    
    print(f"Test Accuracy: {test_acc*100:.2f}%\n")
    print("Confusion Matrix:")
    print(f"{'':>25} Predicted {class_names[0]} | Predicted {class_names[1]}")
    print(f"Actual {class_names[0]:<20}: {cm[0][0]:>10} | {cm[0][1]:>10}")
    print(f"Actual {class_names[1]:<20}: {cm[1][0]:>10} | {cm[1][1]:>10}\n")
    print("Classification Report:")
    print(report)
    
    # Save training metadata
    with open(MODELS_DIR / "training_meta.json", "w") as f:
        json.dump({
            "class_names": class_names,
            "best_val_acc": float(best_val_acc),
            "test_acc": float(test_acc),
            "confusion_matrix": cm.tolist()
        }, f, indent=2)

if __name__ == "__main__":
    train_mobilenet()
