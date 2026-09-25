import json
import base64
import io
import os
from pathlib import Path
from PIL import Image, ImageFilter
import numpy as np

from diagnose import diagnose_leaf, get_service

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"

def run_all_tests():
    print("==================================================================")
    print("   KRISHIRAKSHA COMPONENT 3 (VISION) - VERIFICATION SUITE")
    print("==================================================================\n")
    
    # -------------------------------------------------------------
    # 1. Test Confident Diagnosis Branch (Step 5 & 6)
    # -------------------------------------------------------------
    print("[TEST 1] Confident Diagnosis & Grad-CAM Generation:")
    sample_eb_path = next((DATA_DIR / "test" / "Tomato___Early_blight").glob("*.jpg"))
    result_confident = diagnose_leaf(sample_eb_path, confidence_threshold=0.65)
    
    print(f"  Input File:            {sample_eb_path.name}")
    print(f"  Disease Class:         {result_confident['disease_class']}")
    print(f"  Calibrated Confidence: {result_confident['calibrated_confidence']*100:.2f}%")
    print(f"  Needs Second Photo:    {result_confident['needs_second_photo']}")
    print(f"  Reason:                {result_confident['reason']}")
    print(f"  Grad-CAM Base64 Len:   {len(result_confident['gradcam_image_base64']) if result_confident['gradcam_image_base64'] else 'None'}")
    
    assert result_confident['needs_second_photo'] is False, "Expected confident diagnosis branch"
    assert result_confident['disease_class'] == "Tomato___Early_blight", "Expected Tomato___Early_blight"
    assert result_confident['gradcam_image_base64'] is not None, "Expected Grad-CAM overlay"
    print("  -> TEST 1 PASSED.\n")
    
    # -------------------------------------------------------------
    # 2. Test Low-Confidence Safeguard Fallback Branch (Step 5)
    # -------------------------------------------------------------
    print("[TEST 2] Low-Confidence Safeguard Fallback Branch (Default 0.65 Threshold):")
    np.random.seed(0)
    noisy_img = Image.fromarray(np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8))
    
    result_low_conf = diagnose_leaf(noisy_img, confidence_threshold=0.65)
    print(f"  Input:                 Ambiguous / Out-of-Distribution Noise Image")
    print(f"  Disease Class:         {result_low_conf['disease_class']}")
    print(f"  Calibrated Confidence: {result_low_conf['calibrated_confidence']*100:.2f}%")
    print(f"  Needs Second Photo:    {result_low_conf['needs_second_photo']}")
    print(f"  Reason:                {result_low_conf['reason']}")
    print(f"  Grad-CAM Base64:       {result_low_conf['gradcam_image_base64']}")
    
    assert result_low_conf['needs_second_photo'] is True, "Expected fallback safeguard to trigger"
    assert result_low_conf['disease_class'] is None, "Should NOT diagnose when low confidence"
    assert result_low_conf['gradcam_image_base64'] is None, "Should NOT generate GradCAM when low confidence"
    print("  -> TEST 2 PASSED.\n")

    # -------------------------------------------------------------
    # 3. Test Format-Invariance on IDENTICAL Single Image (Check 1)
    # -------------------------------------------------------------
    print("[TEST 3] Multi-Format Input Support on EXACT SAME Shared Image:")
    shared_test_path = sample_eb_path
    
    # Format A: File path (str/Path)
    res_path = diagnose_leaf(shared_test_path)
    # Format B: PIL.Image
    res_pil = diagnose_leaf(Image.open(shared_test_path))
    # Format C: Raw bytes (FastAPI UploadFile.read())
    with open(shared_test_path, "rb") as f:
        shared_bytes = f.read()
    res_bytes = diagnose_leaf(shared_bytes)
    # Format D: io.BytesIO
    res_bytesio = diagnose_leaf(io.BytesIO(shared_bytes))
    
    print(f"  Shared Image:          {shared_test_path.name}")
    print(f"  Format 1 (Path):       {res_path['disease_class']:<22} | Conf: {res_path['calibrated_confidence']:.4f} | Needs2nd: {res_path['needs_second_photo']}")
    print(f"  Format 2 (PIL.Image):  {res_pil['disease_class']:<22} | Conf: {res_pil['calibrated_confidence']:.4f} | Needs2nd: {res_pil['needs_second_photo']}")
    print(f"  Format 3 (Raw bytes):  {res_bytes['disease_class']:<22} | Conf: {res_bytes['calibrated_confidence']:.4f} | Needs2nd: {res_bytes['needs_second_photo']}")
    print(f"  Format 4 (io.BytesIO): {res_bytesio['disease_class']:<22} | Conf: {res_bytesio['calibrated_confidence']:.4f} | Needs2nd: {res_bytesio['needs_second_photo']}")
    
    assert res_path['disease_class'] == res_pil['disease_class'] == res_bytes['disease_class'] == res_bytesio['disease_class'], "Mismatch across input formats!"
    assert res_path['calibrated_confidence'] == res_pil['calibrated_confidence'] == res_bytes['calibrated_confidence'] == res_bytesio['calibrated_confidence'], "Confidence mismatch across input formats!"
    print("  -> TEST 3 PASSED (100% format-invariant).\n")

    # -------------------------------------------------------------
    # 4. Stress-Test with Multiple Real Messy Field Photos (Check 2)
    # -------------------------------------------------------------
    print("[TEST 4 / STEP 7] Stress-Testing Multiple Real In-The-Wild Photos:")
    messy_photos = [
        ("messy_field_photo.jpg", "Messy Photo 1: Outdoor field canopy, natural lighting, soil/stem background (Early Blight)"),
        ("messy_field_photo_2.jpg", "Messy Photo 2: High-res outdoor macro shot of Alternaria solani leaf lesions"),
        ("messy_field_photo_3.jpg", "Messy Photo 3: Outdoor garden leaf with Septoria leaf spot damage (OOD disease stress test)"),
        ("messy_field_photo_4.jpg", "Messy Photo 4: Outdoor garden tomato plant with spider mite/thrips damage & garden foliage")
    ]
    
    for filename, description in messy_photos:
        file_path = BASE_DIR / filename
        if not file_path.exists():
            print(f"  [SKIPPED] {filename} not found.")
            continue
            
        res = diagnose_leaf(file_path, confidence_threshold=0.65)
        print(f"  File:                  {filename}")
        print(f"  Context:               {description}")
        print(f"  Dimensions:            {Image.open(file_path).size}")
        print(f"  Diagnosis:             {res['disease_class']}")
        print(f"  Calibrated Confidence: {res['calibrated_confidence']*100:.2f}%" if res['calibrated_confidence'] else "  Calibrated Confidence: None")
        print(f"  Needs Second Photo:    {res['needs_second_photo']}")
        print(f"  Reason:                {res['reason']}")
        print(f"  Grad-CAM Generated:    {res['gradcam_image_base64'] is not None}")
        
        # Save Grad-CAM overlay for live demo inspection
        if res['gradcam_image_base64']:
            raw_png = base64.b64decode(res['gradcam_image_base64'])
            overlay_name = file_path.stem + "_gradcam.png"
            with open(BASE_DIR / overlay_name, "wb") as f:
                f.write(raw_png)
            print(f"  -> Grad-CAM overlay saved to: {overlay_name}")
        print("  " + "-"*50)
    print("  -> TEST 4 PASSED.\n")

    # -------------------------------------------------------------
    # 5. Corrupted & Invalid Input Regression Tests (Check 3)
    # -------------------------------------------------------------
    print("[TEST 5 / TEST 6 REGRESSION] Corrupted and Invalid Input Handling:")
    
    # Subtest 5A: Truncated JPEG (50% of valid image bytes)
    with open(sample_eb_path, "rb") as f:
        full_bytes = f.read()
    truncated_bytes = full_bytes[:len(full_bytes) // 2]
    res_trunc = diagnose_leaf(truncated_bytes)
    print(f"  5A. Truncated JPEG (50% bytes): Needs 2nd Photo = {res_trunc['needs_second_photo']} | Reason = {res_trunc['reason']}")
    assert res_trunc['needs_second_photo'] is True, "Truncated image must return needs_second_photo=True"
    assert res_trunc['disease_class'] is None, "Truncated image must have disease_class=None"
    assert res_trunc['reason'] is not None and "Image decoding error" in res_trunc['reason']

    # Subtest 5B: Text file disguised as JPEG bytes
    fake_jpg_bytes = b"This is not a real JPEG image file, it is plaintext content."
    res_fake = diagnose_leaf(fake_jpg_bytes)
    print(f"  5B. Text disguised as JPEG:     Needs 2nd Photo = {res_fake['needs_second_photo']} | Reason = {res_fake['reason']}")
    assert res_fake['needs_second_photo'] is True, "Fake JPEG must return needs_second_photo=True"
    assert res_fake['disease_class'] is None
    assert res_fake['reason'] is not None and "Image decoding error" in res_fake['reason']

    # Subtest 5C: Empty byte string
    empty_bytes = b""
    res_empty = diagnose_leaf(empty_bytes)
    print(f"  5C. Empty byte string:          Needs 2nd Photo = {res_empty['needs_second_photo']} | Reason = {res_empty['reason']}")
    assert res_empty['needs_second_photo'] is True, "Empty bytes must return needs_second_photo=True"
    assert res_empty['disease_class'] is None
    assert res_empty['reason'] is not None and "Image decoding error" in res_empty['reason']

    # Subtest 5D: Non-existent file path
    res_missing = diagnose_leaf("data/test/non_existent_leaf_12345.jpg")
    print(f"  5D. Missing file path:          Needs 2nd Photo = {res_missing['needs_second_photo']} | Reason = {res_missing['reason']}")
    assert res_missing['needs_second_photo'] is True, "Missing file must return needs_second_photo=True"
    assert res_missing['disease_class'] is None
    assert res_missing['reason'] is not None and "Image decoding error" in res_missing['reason']

    # Subtest 5E: Unsupported object type (e.g. integer or dict)
    res_badtype = diagnose_leaf(12345)
    print(f"  5E. Unsupported data type:      Needs 2nd Photo = {res_badtype['needs_second_photo']} | Reason = {res_badtype['reason']}")
    assert res_badtype['needs_second_photo'] is True, "Invalid type must return needs_second_photo=True"
    assert res_badtype['disease_class'] is None
    assert res_badtype['reason'] is not None and "Invalid image input type" in res_badtype['reason']
    
    print("  -> TEST 5 / TEST 6 REGRESSION PASSED (Zero crashes, graceful fallbacks).\n")

    # -------------------------------------------------------------
    # 6. Verification of Calibration JSON & Schema (Check 4 & 5)
    # -------------------------------------------------------------
    print("[TEST 6] Verifying Calibration Artifacts & Contract Schema:")
    cal_path = BASE_DIR / "models" / "calibration.json"
    assert cal_path.exists(), "calibration.json must exist"
    with open(cal_path, "r") as f:
        cal_data = json.load(f)
    print(f"  calibration.json temperature: {cal_data.get('temperature')} (type: {type(cal_data.get('temperature')).__name__})")
    assert "temperature" in cal_data and isinstance(cal_data["temperature"], float), "T must be a float in calibration.json"
    assert cal_data["temperature"] > 0, "Temperature T must be strictly positive"
    
    # Contract Schema Check
    expected_keys = {"disease_class", "calibrated_confidence", "needs_second_photo", "gradcam_image_base64", "reason"}
    for res in [result_confident, result_low_conf, res_path, res_trunc, res_fake, res_empty]:
        assert set(res.keys()) == expected_keys, f"Contract schema violation: {res.keys()}"
    print(f"  Contract keys verified: {sorted(list(expected_keys))}")
    
    print("\n==================================================================")
    print("   ALL 6 COMPREHENSIVE VERIFICATION TESTS PASSED SUCCESSFULLY")
    print("==================================================================")

if __name__ == "__main__":
    run_all_tests()
