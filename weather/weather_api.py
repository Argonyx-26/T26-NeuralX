"""
Open-Meteo API Integration.

Responsible for retrieving hourly weather data and historical weather data,
handling network errors, and ensuring consistent data structures.
"""
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional
from datetime import datetime

# Open-Meteo API endpoints
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Timeout for HTTP requests in seconds
TIMEOUT = 10

def _fetch_data(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to fetch and parse JSON data from an API endpoint."""
    query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query_string}"
    
    try:
        req = urllib.request.Request(full_url, headers={'User-Agent': 'KrishiRaksha-Weather-Module/1.0'})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise ValueError(f"Unexpected HTTP status code: {response.status}")
            
            data = json.loads(response.read().decode('utf-8'))
            return _format_response(data)
            
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to weather API: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse weather API response: {e}") from e
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}") from e

def _format_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format the Open-Meteo response into a consistent structure.
    
    Assumption: Timezone is strictly maintained as ISO8601 UTC strings if no timezone is 
    explicitly requested. Open-Meteo defaults to UTC unless specified.
    We request GMT to ensure consistent UTC parsing downstream.
    """
    if "hourly" not in data or "time" not in data["hourly"]:
        raise ValueError("Malformed API response: Missing hourly data.")
    
    hourly = data["hourly"]
    times = hourly.get("time", [])
    
    # We zip the hourly lists to create a unified timeseries list
    timeseries = []
    for i in range(len(times)):
        timeseries.append({
            "time": times[i] + "+00:00", # ISO8601 string explicitly in UTC
            "temperature_celsius": hourly.get("temperature_2m", [])[i] if "temperature_2m" in hourly else None,
            "relative_humidity_percent": hourly.get("relative_humidity_2m", [])[i] if "relative_humidity_2m" in hourly else None,
            "precipitation_mm": hourly.get("precipitation", [])[i] if "precipitation" in hourly else None,
            "wind_speed_kmh": hourly.get("wind_speed_10m", [])[i] if "wind_speed_10m" in hourly else None,
            "wind_direction_deg": hourly.get("wind_direction_10m", [])[i] if "wind_direction_10m" in hourly else None,
        })
        
    return {
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "timezone": data.get("timezone", "UTC"),
        "elevation": data.get("elevation"),
        "hourly_data": timeseries
    }

def get_hourly_weather(latitude: float, longitude: float, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Retrieve hourly weather data from Open-Meteo for the given coordinates.
    
    Args:
        latitude (float): Latitude of the field.
        longitude (float): Longitude of the field.
        start_date (Optional[datetime]): Optional start date for forecast data.
        end_date (Optional[datetime]): Optional end date for forecast data.
        
    Returns:
        Dict[str, Any]: Structured weather data containing temperature, humidity, rainfall, wind speed, etc.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValueError("Invalid coordinates provided.")
        
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m",
        "timezone": "GMT"
    }
    
    if start_date:
        params["start_date"] = start_date.strftime("%Y-%m-%d")
    if end_date:
        params["end_date"] = end_date.strftime("%Y-%m-%d")
        
    return _fetch_data(FORECAST_URL, params)

def get_historical_weather(latitude: float, longitude: float, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
    """
    Retrieve historical hourly weather data for replay demonstrations.
    
    Args:
        latitude (float): Latitude of the field.
        longitude (float): Longitude of the field.
        start_date (datetime): Start date of historical period.
        end_date (datetime): End date of historical period.
        
    Returns:
        Dict[str, Any]: Structured historical weather data.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise ValueError("Invalid coordinates provided.")
        
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m",
        "timezone": "GMT"
    }
    
    return _fetch_data(ARCHIVE_URL, params)
