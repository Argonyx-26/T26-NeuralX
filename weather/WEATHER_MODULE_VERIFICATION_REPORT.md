# KrishiRaksha — Weather Module Verification Report

## 1. Executive Summary
The `weather` module has been comprehensively audited, fixed, and verified for the KrishiRaksha hackathon prototype. The module successfully orchestrates historical and forecast weather retrieval via Open-Meteo, calculates TOMCAST-style Disease Severity Values (DSV) for Tomato Early Blight using Relative Humidity (RH > 90%) as a leaf-wetness proxy, and filters forecast data for candidate spray windows. The module is fully ready for integration by the backend team, provided the UI explicitly communicates that DSV values are unverified prototype indicators and not calibrated infection probabilities.

## 2. Scope and Limitations
* **Supported Crop:** Tomato only.
* **Limitations:**
  * Uses unverified, prototype lookup tables for TOMCAST DSV.
  * Relies on Relative Humidity > 90% as a proxy for Leaf Wetness since Open-Meteo does not provide leaf wetness directly.
  * Does not track cumulative seasonal DSV. The backend must handle inter-request history if needed.
  * High DSV in historical testing indicates *favorable weather conditions*, but does not prove actual historical disease outbreaks.

## 3. File-by-File Implementation Summary
* `__init__.py`: Exposes the public API (`calculate_weather_risk`, `find_spray_windows`).
* `weather_api.py`: Connects to Open-Meteo's `forecast` and `archive` endpoints. Validates bounds. Formats output into a unified chronological array.
* `tomcast.py`: Iterates chronologically through hourly data, tracking continuous periods of `RH > 90%`, calculating average temperatures for those periods, and mapping them to a DSV using `_lookup_dsv_prototype`.
* `risk.py`: Wrapper for backend. Enforces `"tomato"` only. Coordinates fetching weather data and evaluating the TOMCAST model. Explicitly sets `weather_risk_level: "undetermined"`.
* `spray_window.py`: Filters forecast for `wind_speed_kmh` and `precipitation_mm`. Groups consecutive hours into windows and returns an `elapsed time` duration.
* `test_weather.py`: Comprehensive test suite containing 25 deterministic unit tests.

## 4. Weather API Audit
The integration with Open-Meteo was successfully audited:
* **Endpoints**: Correctly uses `v1/forecast` and `v1/archive`.
* **Validation**: Latitude (-90 to 90) and Longitude (-180 to 180) bounds are enforced.
* **Error Handling**: Missing fields, network timeouts (`urllib.error.URLError`), and JSON parse errors are gracefully caught, returning an error payload rather than crashing.
* **Timestamps**: Extracted natively as `"GMT"` by requesting `timezone=GMT` from the API. The module explicitly adds the `+00:00` UTC offset internally to prevent ambiguity.
* **Verification**: Internet requests against the historical API succeeded (see Section 7).

## 5. TOMCAST Methodology and Parameter Audit
* **Leaf-Wetness Proxy**: Identifies wetness strictly if `relative_humidity_percent > 90`.
* **Period Tracking**: Consecutive hourly records satisfying wetness are grouped. Any gap (missing data, non-wet hour) closes the period and evaluates the accumulated hours and `average_temperature`.
* **Missing/Invalid**: Missing temperatures or invalid timestamps safely break the wetness period, ensuring no artificial inflation of DSV.
* **Lookup Parameters**: 
  * *13-17°C*: 7-15h (DSV 1), 16-20h (DSV 2), >20h (DSV 3)
  * *18-20°C & 26-29°C*: 4-8h (DSV 1), 9-14h (DSV 2), 15-22h (DSV 3), >22h (DSV 4)
  * *21-25°C*: 3-5h (DSV 1), 6-12h (DSV 2), 13-20h (DSV 3), >20h (DSV 4)
* **Verification Status**: **UNVERIFIED**. These are prototype thresholds closely mirroring original FAST tables but require region-specific validation.

## 6. Reference Comparison
According to standard university extension resources (e.g., Michigan State University, VIPS-Landbruk), the original TOMCAST model utilizes a physical leaf wetness sensor and monitors temperatures between 13°C and 29°C.

| Model component | Current implementation | Reference description | Match / difference | Evidence or uncertainty |
| :--- | :--- | :--- | :--- | :--- |
| Wetness Tracking | Relative Humidity > 90% | Physical leaf wetness sensors | **Difference** | Proxies are common but less accurate (unverified for India). |
| Favorable Temp Range | 13°C to 29°C | 13°C to 29°C | **Match** | Matches established literature. |
| DSV Accumulation | Evaluated per continuous wet period | Evaluated daily (0-4 max per day) | **Difference** | Our code accumulates per wet period which could technically exceed 4 per day in edge cases. |

## 7. Historical-Weather Test Results
An integration test script was run for two distinct Indian climates for the period of Sept 1, 2023 - Sept 7, 2023.

* **Pune, India (18.52, 73.85)**
  * *Dataset*: Open-Meteo Archive
  * *Records Received*: 168 (0 missing)
  * *Calculated DSV*: **12**
  * *Interpretation*: High humidity/wetness drove favorable conditions. Does not prove actual blight occurrence.

* **Chennai, India (13.08, 80.27)**
  * *Dataset*: Open-Meteo Archive
  * *Records Received*: 168 (0 missing)
  * *Calculated DSV*: **0**
  * *Interpretation*: Hotter temperatures or drier air meant no favorable periods were logged.

## 8. Deterministic Test Results
The test suite ensures mathematical and logical stability.
* **Test Command**: `python -m unittest weather.test_weather -v`
* **Coverage**: Missing humidity, gaps, unordered timestamps, API failures, spray-window logic, and boundary conditions.
* **Result**: **25 tests passed in 0.006s. 0 failures.**

## 9. Spray-Window Review
The spray-window logic in `find_spray_windows` strictly filters out hours where `wind_speed_kmh > max_wind_speed` or `precipitation_mm > max_precipitation`.
* **Duration Logic**: Refactored to represent **elapsed time**. For example, a window spanning 00:00 to 04:00 is correctly evaluated as `duration_hours: 4`. A single qualifying hour evaluates as `duration_hours: 1`. 
* **Disclaimer**: Retains the required disclaimer that it does not guarantee safe spraying.

## 10. Risk-Function Review
The `calculate_weather_risk` function reliably orchestrates data retrieval and Tomcast scoring.
* **Unsupported Crops**: Correctly raises `ValueError` for non-tomato crops.
* **History**: The `history` parameter was removed from the API signature to prevent the backend from mistakenly believing cumulative history is handled automatically.
* **Outputs**: Returns `period_start` and `period_end` fields to explicitly communicate the timeframe of the provided DSV. `weather_risk_level` remains strictly `"undetermined"`.

## 11. Integration Contract for Person 1
Person 1 should interface using the following robust contracts.

### Weather Risk
```python
from weather.risk import calculate_weather_risk
result = calculate_weather_risk(18.52, 73.85, "tomato", historical=False)
```
**Output Structure:**
```json
{
    "crop": "tomato",
    "disease": "early_blight",
    "model_name": "prototype_tomcast_dsv",
    "period_start": "2026-09-17T13:00:00+00:00",
    "period_end": "2026-09-24T13:00:00+00:00",
    "dsv": 10,
    "weather_risk_level": "undetermined",
    "warnings": [],
    "disclaimer": "Prototype weather-based indicator..."
}
```
*Note: Network errors return gracefully with `dsv: None` and populate `"warnings"`.*

### Spray Windows
```python
from weather.spray_window import find_spray_windows
result = find_spray_windows(forecast_data, max_wind_speed=15.0, max_precipitation=0.0)
```
**Output Structure:**
```json
{
    "windows_found": true,
    "windows": [{"start": "2026-09-24T00:00:00+00:00", "end": "2026-09-24T04:00:00+00:00", "duration_hours": 4}],
    "warnings": [],
    "disclaimer": "Weather-filtered candidate periods only..."
}
```

## 12. Issue List (P0/P1/P2)
* **P0 (FIXED)**: Spray window duration counted data points instead of elapsed time. Fixed to `max(1, elapsed_hours)`.
* **P1 (FIXED)**: Ambiguous timezones in API outputs. Fixed by forcing explicit `+00:00` suffix to returned GMT stamps.
* **P1 (FIXED)**: Ambiguous DSV period. Fixed by adding `period_start` and `period_end` to output.
* **P1 (FIXED)**: Unused `history` argument confused intent. Fixed by removing it from the signature.
* **P2 (OPEN)**: Validating the lookup parameters and the RH > 90% proxy for Indian climates.

## 13. Changes Made
* Refactored spray window duration logic.
* Added UTC offset string literal to Open-Meteo timestamps.
* Removed unused `history` arg from `risk.py` signature.
* Appended `period_start` and `period_end` to `risk.py` return dict.
* Added single-hour duration test.

## 14. Remaining Uncertainties
* Whether Person 1's backend needs to persist DSV values across days to calculate seasonal accumulation (currently must be handled by the backend).

## 15. Reproduction Instructions
From the `weather` module root, run:
`python -m unittest weather.test_weather -v`

## 16. Final Handoff Checklist
- [x] Code is deterministic and tested.
- [x] Timezones explicitly labeled.
- [x] Scientific assumptions clearly disclosed as unverified prototypes.
- [x] Contract JSONs are stable.
- [x] Person 1 and Person 4 instructions prepared.
