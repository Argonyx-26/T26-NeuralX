# KrishiRaksha — Component 3: Leaf Photo Diagnosis (Vision Service)

## Overview
This module (`vision/`) provides the Tomato Leaf Disease Diagnostic service for **KrishiRaksha**. It uses a fine-tuned **MobileNetV2** model with **Temperature Scaling Calibration** (Guo et al., ICML 2017), **Grad-CAM visual explainability**, and a **low-confidence fallback safeguard**.

---

## Output Contract for Backend Integration (Person 1 / FastAPI)

Backend endpoints should call the primary entry point:
```python
from diagnose import diagnose_leaf

result = diagnose_leaf(image, confidence_threshold=0.65)
```

### Parameters:
- `image`: Supported formats:
  - Local file path (`str` or `pathlib.Path`)
  - `PIL.Image.Image` object
  - Raw binary image bytes (`bytes` or `io.BytesIO`)
- `confidence_threshold` *(optional, float, default=0.65)*: Minimum calibrated confidence required for diagnosis.

### Return Dictionary Schema:
```json
{
  "disease_class": "Tomato___Early_blight",  // "Tomato___Early_blight" | "Tomato___healthy" | null
  "calibrated_confidence": 0.9972,           // float | null (Guaranteed calibrated probability, never raw softmax)
  "needs_second_photo": false,               // boolean (true if image is ambiguous, blurry, or low-confidence)
  "gradcam_image_base64": "iVBORw0KGgo...",   // base64-encoded PNG overlay string | null
  "reason": null                             // string explanation if fallback triggered | null
}
```

---

## Safety Safeguard & Fallback Rules
1. If the **calibrated confidence** falls below `confidence_threshold` (default `0.65`):
   - `disease_class` is set to `null`
   - `needs_second_photo` is set to `true`
   - `gradcam_image_base64` is set to `null`
   - `reason` provides a user-friendly instruction: *"Calibrated confidence (X%) is below the safety threshold (65.0%). Please send another, clearer photo taken in good lighting."*
2. If the image is corrupted or invalid, `needs_second_photo` is set to `true` with the decoding error description in `reason`.

---

## FastAPI Integration Example

```python
from fastapi import FastAPI, UploadFile, File
from vision.diagnose import diagnose_leaf

app = FastAPI()

@app.post("/api/diagnose")
async def diagnose_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    diagnosis = diagnose_leaf(contents, confidence_threshold=0.65)
    return diagnosis
```

---

## Directory Structure
- `dataset_setup.py`: Downloads PlantVillage Tomato subset, validates PIL integrity, and creates 70/15/15 splits.
- `train.py`: Fine-tunes MobileNetV2 with frozen convolutional feature extractor.
- `inference_raw.py`: Model inference exposing raw softmax confidence.
- `calibrate.py`: Fits temperature scaling $T$ on the held-out validation set and plots reliability diagrams.
- `gradcam.py`: Computes Grad-CAM activation heatmaps and generates JET blended base64 PNGs.
- `diagnose.py`: **Primary public module** exposing `diagnose_leaf(image)`.
- `test_pipeline.py`: Comprehensive test suite verifying contract, fallback logic, and stress tests.
- `models/`: Contains model weights (`mobilenet_v2_tomato.pth`) and calibration metadata (`calibration.json`).
- `reliability_diagram.png`: Visual calibration comparison (Uncalibrated vs Calibrated).
