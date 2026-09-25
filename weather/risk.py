"""
Unified Weather-Risk Interface.

Provides a unified function for the backend to assess weather risk for a given crop,
without needing to understand internal disease model implementations.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from .weather_api import get_hourly_weather, get_historical_weather
from .tomcast import calculate_tomcast_dsv

def calculate_weather_risk(
    latitude: float, 
    longitude: float, 
    crop: str, 
    historical: bool = False
) -> Dict[str, Any]:
    """
    Assess weather-based disease risk for a specific crop at given coordinates.
    
    Args:
        latitude (float): Latitude of the field.
        longitude (float): Longitude of the field.
        crop (str): Target crop type (e.g., 'tomato').
        historical (bool): Flag indicating if this is a historical replay.
        
    Returns:
        Dict[str, Any]: A structured response containing disease risk metrics.
    """
    if crop.lower() != "tomato":
        raise ValueError(f"Unsupported crop: {crop}. Only 'tomato' is supported.")

    try:
        if historical:
            # For a prototype historical replay, use the last 7 days from now as an example 
            # if no explicit start/end dates are provided via the interface.
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
            weather_data = get_historical_weather(latitude, longitude, start_date, end_date)
        else:
            weather_data = get_hourly_weather(latitude, longitude)
    except Exception as e:
        return {
            "crop": crop.lower(),
            "disease": "early_blight",
            "model_name": "prototype_tomcast_dsv",
            "period_start": None,
            "period_end": None,
            "dsv": None,
            "weather_risk_level": "undetermined",
            "warnings": [f"Failed to retrieve weather data: {e}"],
            "disclaimer": "The weather-based indicator has been calculated for your field. This is a prototype indicator, not a confirmed disease diagnosis. Please consider local agricultural guidance."
        }

    tomcast_result = calculate_tomcast_dsv(weather_data)
    
    hourly_data = weather_data.get("hourly_data", [])
    period_start = hourly_data[0]["time"] if hourly_data else None
    period_end = hourly_data[-1]["time"] if hourly_data else None
    
    return {
        "crop": crop.lower(),
        "disease": "early_blight",
        "model_name": tomcast_result.get("model_name", "prototype_tomcast_dsv"),
        "period_start": period_start,
        "period_end": period_end,
        "dsv": tomcast_result.get("dsv"),
        "weather_risk_level": "undetermined", # No validated DSV mapping rules established
        "warnings": tomcast_result.get("warnings", []),
        "disclaimer": "The weather-based indicator has been calculated for your field. This is a prototype indicator, not a confirmed disease diagnosis. Please consider local agricultural guidance. " + tomcast_result.get("disclaimer", "")
    }
