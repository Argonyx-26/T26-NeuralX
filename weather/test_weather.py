"""
Unit Tests for the Weather Module.
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json
import urllib.error
from .weather_api import get_hourly_weather, get_historical_weather, FORECAST_URL, ARCHIVE_URL
from .tomcast import calculate_tomcast_dsv
from .risk import calculate_weather_risk
from .spray_window import find_spray_windows

class TestWeatherAPI(unittest.TestCase):
    
    def setUp(self):
        # Sample response matching Open-Meteo's format
        self.mock_response_data = {
            "latitude": 18.52,
            "longitude": 73.85,
            "timezone": "GMT",
            "elevation": 560,
            "hourly": {
                "time": ["2023-10-01T00:00", "2023-10-01T01:00"],
                "temperature_2m": [22.5, 22.1],
                "relative_humidity_2m": [85, 87],
                "precipitation": [0.0, 1.2],
                "wind_speed_10m": [5.4, 6.1],
                "wind_direction_10m": [180, 190]
            }
        }
    
    @patch('urllib.request.urlopen')
    def test_get_hourly_weather_success(self, mock_urlopen):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(self.mock_response_data).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        result = get_hourly_weather(18.52, 73.85)
        
        # Verify structure and values
        self.assertEqual(result["latitude"], 18.52)
        self.assertEqual(result["timezone"], "GMT")
        self.assertEqual(len(result["hourly_data"]), 2)
        
        first_hour = result["hourly_data"][0]
        self.assertEqual(first_hour["time"], "2023-10-01T00:00+00:00")
        self.assertEqual(first_hour["temperature_celsius"], 22.5)
        self.assertEqual(first_hour["relative_humidity_percent"], 85)
        self.assertEqual(first_hour["precipitation_mm"], 0.0)
        self.assertEqual(first_hour["wind_speed_kmh"], 5.4)
        
    @patch('urllib.request.urlopen')
    def test_get_historical_weather_success(self, mock_urlopen):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(self.mock_response_data).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        start_date = datetime(2023, 10, 1)
        end_date = datetime(2023, 10, 1)
        result = get_historical_weather(18.52, 73.85, start_date, end_date)
        
        # Verify it passed the right dates to the URL
        call_args = mock_urlopen.call_args[0][0].full_url
        self.assertIn("start_date=2023-10-01", call_args)
        self.assertIn("end_date=2023-10-01", call_args)
        self.assertTrue(call_args.startswith(ARCHIVE_URL))
        
    def test_invalid_coordinates(self):
        with self.assertRaises(ValueError):
            get_hourly_weather(95.0, 0.0)
            
        with self.assertRaises(ValueError):
            get_historical_weather(0.0, 200.0, datetime(2023, 10, 1), datetime(2023, 10, 1))
            
    @patch('urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        
        with self.assertRaises(ConnectionError):
            get_hourly_weather(18.52, 73.85)
            
    @patch('urllib.request.urlopen')
    def test_malformed_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"invalid json"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        with self.assertRaises(ValueError):
            get_hourly_weather(18.52, 73.85)

class TestTomcast(unittest.TestCase):
    
    def setUp(self):
        self.base_weather = {
            "latitude": 0.0,
            "longitude": 0.0,
            "hourly_data": []
        }
        
    def _create_record(self, time_str, temp, rh):
        return {
            "time": time_str,
            "temperature_celsius": temp,
            "relative_humidity_percent": rh
        }

    def test_valid_hourly_weather_input(self):
        # Temp 22 (requires 3h for DSV 1)
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 22, 95),
            self._create_record("2023-10-01T02:00", 22, 95),
            self._create_record("2023-10-01T03:00", 22, 95),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 1)
        
    def test_missing_temp_or_humidity(self):
        # Gap splits the period, resetting the counter
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 22, 95),
            self._create_record("2023-10-01T02:00", None, 95), # Missing temp
            self._create_record("2023-10-01T03:00", 22, 95),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 0) # 1 hour periods = 0 DSV
        
    def test_invalid_timestamps(self):
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("invalid-time", 22, 95)
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 0)
        self.assertTrue(len(result["warnings"]) > 0)

    def test_unordered_timestamps(self):
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T03:00", 22, 95),
            self._create_record("2023-10-01T01:00", 22, 95),
            self._create_record("2023-10-01T02:00", 22, 95),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 1)
        
    def test_gaps_in_hourly_observations(self):
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 22, 95),
            self._create_record("2023-10-01T02:00", 22, 95),
            # Gap at 03:00
            self._create_record("2023-10-01T04:00", 22, 95),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 0) # Periods are 2h and 1h -> 0 DSV
        
    def test_boundary_conditions(self):
        # RH exactly 90 is not wet (>90)
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 22, 90),
            self._create_record("2023-10-01T02:00", 22, 90),
            self._create_record("2023-10-01T03:00", 22, 90),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 0)

    def test_no_qualifying_period(self):
        data = self.base_weather.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 22, 80),
            self._create_record("2023-10-01T02:00", 22, 85),
        ]
        result = calculate_tomcast_dsv(data)
        self.assertEqual(result["dsv"], 0)

class TestWeatherRisk(unittest.TestCase):
    
    @patch('weather.risk.get_hourly_weather')
    def test_calculate_weather_risk_tomato_success(self, mock_get_hourly):
        mock_get_hourly.return_value = {
            "hourly_data": [
                {"time": "2023-10-01T01:00", "temperature_celsius": 22, "relative_humidity_percent": 95},
                {"time": "2023-10-01T02:00", "temperature_celsius": 22, "relative_humidity_percent": 95},
                {"time": "2023-10-01T03:00", "temperature_celsius": 22, "relative_humidity_percent": 95}
            ]
        }
        
        result = calculate_weather_risk(10.0, 20.0, "tomato")
        
        self.assertEqual(result["crop"], "tomato")
        self.assertEqual(result["disease"], "early_blight")
        self.assertEqual(result["dsv"], 1)
        self.assertEqual(result["weather_risk_level"], "undetermined")
        self.assertTrue("prototype" in result["disclaimer"])
        
    def test_calculate_weather_risk_unsupported_crop(self):
        with self.assertRaises(ValueError):
            calculate_weather_risk(10.0, 20.0, "wheat")
            
    @patch('weather.risk.get_hourly_weather')
    def test_calculate_weather_risk_api_error(self, mock_get_hourly):
        mock_get_hourly.side_effect = ConnectionError("API down")
        
        result = calculate_weather_risk(10.0, 20.0, "tomato")
        
        self.assertIsNone(result["dsv"])
        self.assertEqual(result["weather_risk_level"], "undetermined")
        self.assertTrue(len(result["warnings"]) > 0)
        self.assertTrue("API down" in result["warnings"][0])
        
    @patch('weather.risk.get_historical_weather')
    def test_calculate_weather_risk_historical(self, mock_get_historical):
        mock_get_historical.return_value = {"hourly_data": []}
        
        result = calculate_weather_risk(10.0, 20.0, "tomato", historical=True)
        
        mock_get_historical.assert_called_once()
        self.assertEqual(result["dsv"], 0)


class TestSprayWindow(unittest.TestCase):
    
    def setUp(self):
        self.base_forecast = {
            "hourly_data": []
        }
        
    def _create_record(self, time_str, wind, precip):
        return {
            "time": time_str,
            "wind_speed_kmh": wind,
            "precipitation_mm": precip
        }

    def test_find_spray_windows_valid_window(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 5.0, 0.0),
            self._create_record("2023-10-01T02:00", 4.0, 0.0)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertTrue(result["windows_found"])
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["start"], "2023-10-01T01:00:00")
        self.assertEqual(result["windows"][0]["end"], "2023-10-01T02:00:00")
        self.assertEqual(result["windows"][0]["duration_hours"], 1)

    def test_spray_window_single_hour(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 5.0, 0.0)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertTrue(result["windows_found"])
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["duration_hours"], 1)
        
    def test_wind_speed_above_limit(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 12.0, 0.0) # > 10.0
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertFalse(result["windows_found"])
        
    def test_precipitation_above_limit(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 5.0, 0.1) # > 0.0
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertFalse(result["windows_found"])
        
    def test_exact_limit_values(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 10.0, 0.5)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.5)
        self.assertTrue(result["windows_found"])
        
    def test_missing_data(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", None, 0.0),
            self._create_record("2023-10-01T02:00", 5.0, 0.0)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertTrue(result["windows_found"])
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["start"], "2023-10-01T02:00:00")
        
    def test_empty_forecast(self):
        result = find_spray_windows({"hourly_data": []}, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertFalse(result["windows_found"])
        
    def test_unordered_input(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T02:00", 5.0, 0.0),
            self._create_record("2023-10-01T01:00", 5.0, 0.0)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertTrue(result["windows_found"])
        self.assertEqual(result["windows"][0]["start"], "2023-10-01T01:00:00")
        self.assertEqual(result["windows"][0]["end"], "2023-10-01T02:00:00")
        
    def test_gap_in_qualifying_hours(self):
        data = self.base_forecast.copy()
        data["hourly_data"] = [
            self._create_record("2023-10-01T01:00", 5.0, 0.0),
            self._create_record("2023-10-01T02:00", 15.0, 0.0), # Too windy, breaks window
            self._create_record("2023-10-01T03:00", 5.0, 0.0)
        ]
        
        result = find_spray_windows(data, max_wind_speed=10.0, max_precipitation=0.0)
        self.assertTrue(result["windows_found"])
        self.assertEqual(len(result["windows"]), 2)

if __name__ == '__main__':
    unittest.main()
