import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from secure_client import SecureClient as TestClient
from main import app
from weather_service import OpenWeatherService

class WeatherApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=TestClient(app); cls.client.__enter__()
    @classmethod
    def tearDownClass(cls): cls.client.__exit__(None,None,None)
    def test_health_and_manual_prediction(self):
        self.assertTrue(self.client.get('/api/v1/health').json()['caspian_model_ready'])
        result=self.client.post('/api/v1/predictions/delay',json={'departure_port':'Оля','arrival_port':'Энзели','wind_speed_ms':8,'wave_height_m':3,'port_congestion_percent':90,'season':'Winter'})
        self.assertEqual(result.status_code,200); self.assertEqual(result.json()['training_data'],'synthetic')
    def test_no_key_and_invalid_coordinates(self):
        with patch.object(app.state,'weather',OpenWeatherService(None)):
            self.assertEqual(self.client.get('/api/v1/weather/forecast?latitude=42&longitude=50').status_code,503)
        self.assertEqual(self.client.get('/api/v1/weather/forecast?latitude=100&longitude=50').status_code,422)
    def test_forecast_bridge(self):
        now=datetime(2026,11,12,tzinfo=timezone.utc)
        raw={'cod':'200','list':[{'dt':int(now.timestamp())+i*10800,'main':{'temp':10,'humidity':60,'pressure':1013},'wind':{'speed':8},'weather':[{'description':'clouds'}]} for i in (1,2)]}
        payload={'latitude':42,'longitude':50,'forecast_at':'2026-11-12T03:00:00Z','departure_port':'Оля','arrival_port':'Энзели','wave_height_m':3,'wave_source':'manual scenario','port_congestion_percent':90}
        with patch.object(app.state,'weather',OpenWeatherService('test',now=lambda:now)),patch('weather_service.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
            result=self.client.post('/api/v1/predictions/delay-from-weather',json=payload)
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['features_used']['season'],'Autumn')
            self.assertEqual(result.json()['features_used']['wind_speed_ms'],8)
            payload['forecast_at']='2026-12-01T03:00:00Z'
            self.assertEqual(self.client.post('/api/v1/predictions/delay-from-weather',json=payload).status_code,422)

    def test_route_uses_server_forecast_and_rejects_expired_slot(self):
        now=datetime(2026,11,12,tzinfo=timezone.utc)
        raw={'cod':'200','list':[{'dt':int(now.timestamp())+10800,
             'main':{'temp':10,'humidity':60,'pressure':1013},
             'wind':{'speed':8,'gust':23},'weather':[{'description':'clouds'}]}]}
        weather={'source':'openweather','latitude':42,'longitude':50,'forecast_at':'2026-11-12T03:00:00Z'}
        payload={'source':'Махачкала','target':'Решт','weather':weather}
        with patch.object(app.state,'weather',OpenWeatherService('test',now=lambda:now)),patch('weather_service.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
            result=self.client.post('/api/v1/route/calculate',json=payload)
            self.assertEqual(result.status_code,200,result.text)
            self.assertTrue(result.json()['weather']['sea_restricted'])
            self.assertEqual(result.json()['weather']['wind_gust_ms'],23)
            self.assertIsNone(result.json()['weather']['wave_height_m'])
            self.assertEqual(result.json()['weather']['source'],'openweather')
            self.assertTrue(all(s['transport_mode']!='ship' for s in result.json()['segments']))
            spoof=self.client.post('/api/v1/route/calculate',json={**payload,'weather':{**weather,'wind_speed_ms':0}})
            self.assertEqual(spoof.status_code,422)
            expired=self.client.post('/api/v1/route/calculate',json={**payload,'weather':{**weather,'forecast_at':'2026-11-11T03:00:00Z'}})
            self.assertEqual(expired.status_code,422)
        with patch.object(app.state,'weather',OpenWeatherService(None)):
            self.assertEqual(self.client.post('/api/v1/route/calculate',json=payload).status_code,503)
