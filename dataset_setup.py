import os
import shutil
import subprocess
import random
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
RAW_DOWNLOAD_DIR = BASE_DIR / "temp_pv_repo"

def download_and_extract_subset():
    print("[1/4] Setting up sparse git clone for Tomato___Early_blight and Tomato___healthy...")
    
    if RAW_DOWNLOAD_DIR.exists():
        shutil.rmtree(RAW_DOWNLOAD_DIR, ignore_errors=True)
    
    RAW_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Use sparse clone to only download the required 2 folders from raw/color
    commands = [
        ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1", "https://github.com/spMohanty/PlantVillage-Dataset.git", "."],
        ["git", "sparse-checkout", "init", "--cone"],
        ["git", "sparse-checkout", "set", "raw/color/Tomato___Early_blight", "raw/color/Tomato___healthy"],
        ["git", "checkout"]
    ]
    
    for cmd in commands:
        print(f"Running: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=RAW_DOWNLOAD_DIR, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error output: {res.stderr}")
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{res.stderr}")
            
    print("Sparse clone completed.")

def verify_and_split():
    print("[2/4] Verifying images and creating train/val/test splits...")
    
    src_early_blight = RAW_DOWNLOAD_DIR / "raw" / "color" / "Tomato___Early_blight"
    src_healthy = RAW_DOWNLOAD_DIR / "raw" / "color" / "Tomato___healthy"
    
    classes = {
        "Tomato___Early_blight": src_early_blight,
        "Tomato___healthy": src_healthy
    }
    
    splits = ["train", "val", "test"]
    split_ratios = {"train": 0.70, "val": 0.15, "test": 0.15}
    
    # Clean previous data dir if needed
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        
    for split in splits:
        for cls_name in classes.keys():
            (DATA_DIR / split / cls_name).mkdir(parents=True, exist_ok=True)
            
    stats = {}
    corrupted_count = 0
    
    random.seed(42)
    
    for cls_name, cls_path in classes.items():
        if not cls_path.exists():
            raise FileNotFoundError(f"Source folder not found: {cls_path}")
            
        all_files = [f for f in cls_path.iterdir() if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]]
        valid_files = []
        
        for f in all_files:
            try:
                with Image.open(f) as img:
                    img.verify()
                # Also verify we can actually decode it completely (Image.verify only checks header/structure)
                with Image.open(f) as img:
                    img.load()
                valid_files.append(f)
            except Exception as e:
                print(f"Corrupted image detected and discarded: {f.name} ({e})")
                corrupted_count += 1
                
        # Shuffle deterministically
        random.shuffle(valid_files)
        
        n_total = len(valid_files)
        n_train = int(n_total * 0.70)
        n_val = int(n_total * 0.15)
        n_test = n_total - n_train - n_val
        
        train_files = valid_files[:n_train]
        val_files = valid_files[n_train:n_train + n_val]
        test_files = valid_files[n_train + n_val:]
        
        for f in train_files:
            shutil.copy2(f, DATA_DIR / "train" / cls_name / f.name)
        for f in val_files:
            shutil.copy2(f, DATA_DIR / "val" / cls_name / f.name)
        for f in test_files:
            shutil.copy2(f, DATA_DIR / "test" / cls_name / f.name)
            
        stats[cls_name] = {
            "total_valid": n_total,
            "train": len(train_files),
            "val": len(val_files),
            "test": len(test_files)
        }
        
    print("[3/4] Cleaning up temporary git repo...")
    shutil.rmtree(RAW_DOWNLOAD_DIR, ignore_errors=True)
    
    print("[4/4] Dataset Setup Summary:")
    print(f"  - Discarded corrupted files: {corrupted_count}")
    for cls_name, counts in stats.items():
        print(f"  - {cls_name}: Total {counts['total_valid']} | Train: {counts['train']} | Val: {counts['val']} | Test: {counts['test']}")
        
    return stats

if __name__ == "__main__":
    download_and_extract_subset()
    verify_and_split()
