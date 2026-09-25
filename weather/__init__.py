"""
KrishiRaksha Weather Module.

This package provides weather-based crop disease early warning capabilities,
spray window guidance, and integration with the Open-Meteo API.
"""

from .risk import calculate_weather_risk
from .spray_window import find_spray_windows

__all__ = [
    "calculate_weather_risk",
    "find_spray_windows"
]
