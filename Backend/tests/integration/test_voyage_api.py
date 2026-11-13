import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from secure_client import SecureClient as TestClient
from main import app
from voyage_store import VoyageStore

class VoyageApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.client=TestClient(app);cls.client.__enter__()
        cls.store_patch=patch.object(app.state,'voyages',app.state.voyages);cls.store_patch.start()
    @classmethod
    def tearDownClass(cls):
        cls.store_patch.stop();cls.client.__exit__(None,None,None);cls.folder.cleanup()
    def payload(self):
        start=datetime.now(timezone.utc)
        return {'source':'Махачкала','target':'Решт','departure_at':start.isoformat(),
                'transport_modes':['ship','rail'],
                'conditions':{'weather_mode':'scenario','scenario':{'source':'scenario','wind_speed_ms':4}}}
    def test_create_reforecast_get_and_failed_update_preserve_plan(self):
        response=self.client.post('/api/v1/voyages',json=self.payload())
        self.assertEqual(response.status_code,201,response.text)
        first=response.json();baseline=first['baseline'];identity=first['id']
        response=self.client.post(f'/api/v1/voyages/{identity}/reforecast',json={'conditions':{'weather_mode':'scenario','scenario':{'source':'scenario','wind_speed_ms':22}}})
        self.assertEqual(response.status_code,200,response.text)
        updated=response.json()
        self.assertEqual(updated['baseline'],baseline)
        self.assertEqual(updated['revision'],1)
        self.assertTrue(all(s['transport_mode']!='ship' for s in updated['current']['fastest']['segments']))
        self.assertTrue(updated['current']['excluded_reasons'])
        fetched=self.client.get(f'/api/v1/voyages/{identity}')
        self.assertEqual(fetched.json(),updated)
        invalid=self.client.post(f'/api/v1/voyages/{identity}/reforecast',json={'conditions':{'port_congestion':{'Энзели':101}}})
        self.assertEqual(invalid.status_code,422)
        self.assertEqual(self.client.get(f'/api/v1/voyages/{identity}').json(),updated)
        self.assertEqual(self.client.get('/api/v1/voyages/missing').status_code,404)
    def test_failed_weather_does_not_overwrite_saved_forecast(self):
        response=self.client.post('/api/v1/voyages',json=self.payload())
        first=response.json();identity=first['id']
        from weather_service import OpenWeatherService
        with patch.object(app.state,'weather',OpenWeatherService(None)):
            failed=self.client.post(f'/api/v1/voyages/{identity}/reforecast',json={'conditions':{'weather_mode':'openweather'}})
        self.assertEqual(failed.status_code,503)
        self.assertEqual(self.client.get(f'/api/v1/voyages/{identity}').json(),first)
    def test_timezone_and_duplicate_schedule_validation(self):
        payload=self.payload();payload['departure_at']='2026-11-12T10:00:00'
        self.assertEqual(self.client.post('/api/v1/voyages',json=payload).status_code,422)
        payload=self.payload()
        connection={'terminal':'Энзели','transport_mode':'rail','first_departure_at':payload['departure_at'],'interval_hours':12}
        payload['connections']=[connection,connection]
        self.assertEqual(self.client.post('/api/v1/voyages',json=payload).status_code,422)
