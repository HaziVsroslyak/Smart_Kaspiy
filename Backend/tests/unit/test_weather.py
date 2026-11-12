import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError

from weather_service import Coordinates, OpenWeatherService, WeatherError

NOW = datetime(2026, 11, 12, 0, tzinfo=timezone.utc)
def provider_data():
    return {"cod":"200","list":[{"dt":int(NOW.timestamp())+10800*i,"main":{"temp":10,"pressure":1013,"humidity":60},"wind":{"speed":8,"deg":90},"weather":[{"description":"облачно"}]} for i in (1,2,3)]}

class WeatherTests(unittest.TestCase):
    def test_missing_key(self):
        with self.assertRaises(WeatherError) as err: OpenWeatherService(None).forecast(Coordinates(latitude=42,longitude=50))
        self.assertEqual(err.exception.status_code,503)
    def test_units_cache_and_no_waves(self):
        service=OpenWeatherService('secret',now=lambda:NOW)
        with patch('weather_service.urlopen',return_value=io.BytesIO(json.dumps(provider_data()).encode())) as fetch:
            result=service.forecast(Coordinates(latitude=42,longitude=50))
            cached=service.forecast(Coordinates(latitude=42,longitude=50))
        self.assertEqual(fetch.call_count,1)
        self.assertIn('units=metric',fetch.call_args.args[0])
        self.assertIsNone(result.forecasts[0].wave_height_m)
        self.assertTrue(cached.cached)
        self.assertNotIn('secret',result.model_dump_json())
    def test_provider_errors(self):
        for status,expected in [(401,503),(429,503),(500,502)]:
            with patch('weather_service.urlopen',side_effect=HTTPError('secret-url',status,'secret',None,None)):
                with self.assertRaises(WeatherError) as error: OpenWeatherService('secret').forecast(Coordinates(latitude=42,longitude=50))
                self.assertEqual(error.exception.status_code,expected)
                self.assertNotIn('secret',str(error.exception))
    def test_malformed_response(self):
        for data in ({}, {"cod":"200","list":[]}):
            with patch('weather_service.urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(WeatherError): OpenWeatherService('x').forecast(Coordinates(latitude=42,longitude=50))
