import unittest
from datetime import datetime,timedelta,timezone
from demo_contracts import DemoRunRequest
from jit_service import run_scenario
from weather_data.service import make_dataset
class Models:
 report={}
 def predict(self,target,features):
  value=10. if target=='readiness' else features['wind_speed_ms']/10 if target=='sea' else 0.
  return dict(model_id=target,target=target,value_hours=value,lower_hours=0.,upper_hours=value+1,features=features,data_version='test')
class JITWeatherTests(unittest.TestCase):
 def run_case(self,wave=.6,wind=5):
  start=datetime(2025,1,1,tzinfo=timezone.utc)
  rows=[dict(timestamp=(start+timedelta(hours=h)).isoformat(),latitude=lat,longitude=lon,wind_speed_ms=wind,wave_height_m=wave) for h in range(0,100,3) for lat,lon in [(42.99,47.6),(41.2,51.2),(37.53,49.48)]]
  data=make_dataset(rows,'Uploaded conditions',None,'uploaded_unverified','upload')
  return run_scenario('calm',DemoRunRequest(dataset_id=data.id,departure_at=start),Models(),weather_dataset=data)
 def test_real_features_and_snapshot(self):
  result=self.run_case();self.assertEqual(result.data_source,'mixed');self.assertTrue(result.weather_snapshot['used_records'])
  self.assertEqual(next(p for p in result.predictions if p.target=='sea').features['wind_speed_ms'],5)
  self.assertEqual(result.strategies[1].status,'ok')
 def test_missing_waves(self):
  result=self.run_case(wave=None);self.assertEqual(result.strategies[1].status,'insufficient_data');self.assertIsNone(result.strategies[1].co2_saved_tonnes)
  self.assertFalse(any(p.target=='sea' for p in result.predictions))
 def test_outside_model_domain(self):
  self.assertEqual(self.run_case(wind=40).strategies[0].status,'insufficient_data')
