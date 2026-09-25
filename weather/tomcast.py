"""
Tomato Early Blight Model (TomCast).

Calculates Disease Severity Values (DSVs) based on temperature and leaf wetness.
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta

def calculate_tomcast_dsv(weather_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate the Disease Severity Value (DSV) for Tomato Early Blight.
    
    Important Note:
    Relative humidity is NOT the same as leaf wetness. If using RH or rainfall
    as a proxy for leaf wetness, it must be explicitly noted in the documentation
    or as part of the output result, and not claimed as true measured leaf wetness.
    
    This implementation uses RH > 90% as a proxy for leaf wetness.
    The exact DSV lookup tables (temperature vs. wetness duration) require 
    scientific verification for the specific region. This is a prototype 
    implementation.
    
    Args:
        weather_data (Dict[str, Any]): Structured hourly weather data.
                                     
    Returns:
        Dict[str, Any]: The calculated DSV score and metadata.
    """
    hourly_data = weather_data.get("hourly_data", [])
    
    # Sort chronologically
    try:
        sorted_data = sorted(
            [d for d in hourly_data if d.get("time")],
            key=lambda x: datetime.fromisoformat(x["time"])
        )
    except Exception as e:
        return {
            "model_name": "prototype_tomcast_dsv",
            "dsv": 0,
            "warnings": [f"Failed to parse timestamps chronologically: {e}"],
            "disclaimer": "RH proxy used for leaf wetness. Parameters require verification."
        }
        
    dsv_total = 0
    warnings = []
    
    current_wet_hours = 0
    temp_sum = 0.0
    previous_time = None
    
    for record in sorted_data:
        try:
            current_time = datetime.fromisoformat(record["time"])
        except Exception:
            warnings.append(f"Invalid timestamp format: {record.get('time')}")
            # Reset current period on invalid timestamp
            if current_wet_hours > 0:
                avg_temp = temp_sum / current_wet_hours
                dsv_total += _lookup_dsv_prototype(avg_temp, current_wet_hours)
            current_wet_hours = 0
            temp_sum = 0.0
            continue
            
        temp = record.get("temperature_celsius")
        rh = record.get("relative_humidity_percent")
        
        # Safely handle missing/invalid values
        if temp is None or rh is None or not isinstance(temp, (int, float)) or not isinstance(rh, (int, float)):
            # Gap in data, evaluate any accumulated wet period and reset
            if current_wet_hours > 0:
                avg_temp = temp_sum / current_wet_hours
                dsv_total += _lookup_dsv_prototype(avg_temp, current_wet_hours)
            current_wet_hours = 0
            temp_sum = 0.0
            previous_time = current_time
            continue
            
        # Proxy for leaf wetness: RH > 90%
        is_wet = rh > 90
        
        if is_wet:
            # Check for continuity
            if previous_time is None or (current_time - previous_time) == timedelta(hours=1):
                current_wet_hours += 1
                temp_sum += temp
            else:
                # Gap in hourly observations but current hour is wet
                # Evaluate previous period and start new one
                if current_wet_hours > 0:
                    avg_temp = temp_sum / current_wet_hours
                    dsv_total += _lookup_dsv_prototype(avg_temp, current_wet_hours)
                current_wet_hours = 1
                temp_sum = temp
        else:
            # Period ended
            if current_wet_hours > 0:
                avg_temp = temp_sum / current_wet_hours
                dsv_total += _lookup_dsv_prototype(avg_temp, current_wet_hours)
            current_wet_hours = 0
            temp_sum = 0.0
            
        previous_time = current_time
        
    # Evaluate any remaining period at the end
    if current_wet_hours > 0:
        avg_temp = temp_sum / current_wet_hours
        dsv_total += _lookup_dsv_prototype(avg_temp, current_wet_hours)
        
    return {
        "model_name": "prototype_tomcast_dsv",
        "dsv": dsv_total,
        "warnings": warnings,
        "disclaimer": "RH > 90% proxy used for leaf wetness. Lookup parameters are unverified prototypes."
    }

def _lookup_dsv_prototype(avg_temp: float, wet_hours: int) -> int:
    """
    Prototype lookup table for DSV based on average temperature and wetness duration.
    Requires scientific verification before production use.
    """
    if wet_hours == 0:
        return 0
        
    if 13 <= avg_temp <= 17:
        if wet_hours <= 6: return 0
        if wet_hours <= 15: return 1
        if wet_hours <= 20: return 2
        return 3
    elif 18 <= avg_temp <= 20 or 26 <= avg_temp <= 29:
        if wet_hours <= 3: return 0
        if wet_hours <= 8: return 1
        if wet_hours <= 14: return 2
        if wet_hours <= 22: return 3
        return 4
    elif 21 <= avg_temp <= 25:
        if wet_hours <= 2: return 0
        if wet_hours <= 5: return 1
        if wet_hours <= 12: return 2
        if wet_hours <= 20: return 3
        return 4
        
    # Temperature out of favorable range
    return 0
