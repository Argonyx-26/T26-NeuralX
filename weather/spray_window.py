"""
Spray-Window Filter.

Identifies potential spray windows based on forecast conditions (e.g., low wind, no rain).
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta

def find_spray_windows(forecast_data: Dict[str, Any], max_wind_speed: float, max_precipitation: float = 0.0) -> Dict[str, Any]:
    """
    Identify periods suitable for spraying based on forecast weather conditions.
    
    Note: Weather filters alone do not guarantee safe spraying. Product labels must be followed.
    
    Args:
        forecast_data (Dict[str, Any]): Hourly weather forecast data.
        max_wind_speed (float): Maximum acceptable wind speed limit.
        max_precipitation (float): Maximum acceptable precipitation limit.
        
    Returns:
        Dict[str, Any]: Structured information about candidate spray windows.
    """
    hourly_data = forecast_data.get("hourly_data", [])
    
    # Sort chronologically to form consecutive windows
    try:
        sorted_data = sorted(
            [d for d in hourly_data if d.get("time")],
            key=lambda x: datetime.fromisoformat(x["time"])
        )
    except Exception:
        return {
            "windows_found": False,
            "windows": [],
            "warnings": ["Failed to parse or sort forecast timestamps."],
            "disclaimer": "Weather-filtered candidate periods only. Follow product labels."
        }
        
    windows = []
    current_window_start = None
    current_window_end = None
    warnings = []
    
    for record in sorted_data:
        try:
            current_time = datetime.fromisoformat(record["time"])
        except Exception:
            warnings.append(f"Invalid timestamp format: {record.get('time')}")
            # Break window
            if current_window_start is not None:
                windows.append({"start": current_window_start.isoformat(), "end": current_window_end.isoformat()})
                current_window_start = None
            continue
            
        wind = record.get("wind_speed_kmh")
        precip = record.get("precipitation_mm")
        
        # Safely handle missing values
        if wind is None or precip is None or not isinstance(wind, (int, float)) or not isinstance(precip, (int, float)):
            # Break window
            if current_window_start is not None:
                windows.append({"start": current_window_start.isoformat(), "end": current_window_end.isoformat()})
                current_window_start = None
            continue
            
        # Check limits
        conditions_met = wind <= max_wind_speed and precip <= max_precipitation
        
        if conditions_met:
            if current_window_start is None:
                current_window_start = current_time
                current_window_end = current_time
            else:
                # Check continuity
                if current_time - current_window_end == timedelta(hours=1):
                    current_window_end = current_time
                else:
                    # Gap breaks window
                    windows.append({"start": current_window_start.isoformat(), "end": current_window_end.isoformat()})
                    current_window_start = current_time
                    current_window_end = current_time
        else:
            if current_window_start is not None:
                windows.append({"start": current_window_start.isoformat(), "end": current_window_end.isoformat()})
                current_window_start = None
                
    # Close any open window at the end
    if current_window_start is not None:
        windows.append({"start": current_window_start.isoformat(), "end": current_window_end.isoformat()})

    # Add duration metric
    for w in windows:
        start_dt = datetime.fromisoformat(w["start"])
        end_dt = datetime.fromisoformat(w["end"])
        w["duration_hours"] = max(1, int((end_dt - start_dt).total_seconds() / 3600))
        
    return {
        "windows_found": len(windows) > 0,
        "windows": windows,
        "warnings": warnings,
        "disclaimer": "These are forecast periods that meet the configured weather filters. They do not guarantee that spraying is safe or effective. Follow the product label and local agricultural guidance."
    }
