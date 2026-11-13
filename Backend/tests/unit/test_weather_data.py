import json
import unittest
from weather_data.contracts import ImportRequest,ResolveRequest
from weather_data.service import import_dataset,resolve
class WeatherDataTests(unittest.TestCase):
 def test_equivalence_and_gaps(self):
  row={'timestamp':'2026-11-12T00:00:00Z','latitude':42,'longitude':50,'wind_speed_ms':12}
  a=import_dataset(ImportRequest(format='json',content=json.dumps([row]),source_name='test'))
  b=import_dataset(ImportRequest(format='csv',content='timestamp,latitude,longitude,wind_speed_ms\n2026-11-12T00:00:00Z,42,50,12',source_name='test'))
  self.assertEqual(a.content_hash,b.content_hash)
  self.assertEqual(a.provenance,'uploaded_unverified')
  self.assertEqual(resolve(a,ResolveRequest(latitude=42,longitude=50,timestamp='2026-11-12T00:00:00Z')).gaps,['wave_height_m'])
  self.assertIsNone(resolve(a,ResolveRequest(latitude=42,longitude=50,timestamp='2026-11-13T00:00:00Z')).record)
 def test_invalid(self):
  for content in ('[]','[{"timestamp":"2026-11-12T00:00:00","latitude":42,"longitude":50}]','[{"timestamp":"2026-11-12T00:00:00Z","latitude":NaN,"longitude":50}]'):
   with self.subTest(content=content),self.assertRaises(ValueError):import_dataset(ImportRequest(format='json',content=content,source_name='test'))
 def test_duplicates(self):
  row={'timestamp':'2026-11-12T00:00:00Z','latitude':42,'longitude':50}
  with self.assertRaises(ValueError):import_dataset(ImportRequest(format='json',content=json.dumps([row,row]),source_name='test'))
