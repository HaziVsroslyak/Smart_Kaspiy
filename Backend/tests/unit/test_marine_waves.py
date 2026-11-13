"""Marine enrichment retains provenance and never fabricates missing coverage."""
import io
import json
import unittest
from urllib.error import URLError
from unittest.mock import patch

from weather_data.contracts import FetchRequest
from weather_data.service import fetch_dataset


class MarineWaveTests(unittest.TestCase):
    def request(self, **changes):
        return FetchRequest(latitude=41.2,longitude=51.2,start_date='2026-11-13',
                            end_date='2026-11-13',kind=changes.pop('kind','forecast'),**changes)

    def atmosphere(self):
        return {'latitude':41.21,'longitude':51.21,'hourly':{
            'time':['2026-11-13T00:00','2026-11-13T01:00'],
            'wind_speed_10m':[5,6]}}

    def marine(self, heights=None):
        return {'latitude':41.208,'longitude':51.208,'hourly_units':{'wave_height':'m'},
            'hourly':{'time':['2026-11-13T01:00','2026-11-13T02:00'],
                'wave_height':heights if heights is not None else [1.2,1.4],
                'wave_period':[4.0,4.2],'wave_direction':[150,160]}}

    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def test_exact_timestamp_merge_and_cell_provenance(self):
        with patch('weather_data.service.urlopen',side_effect=[self.response(self.atmosphere()),self.response(self.marine())]):
            result=fetch_dataset(self.request())
        self.assertIsNone(result.records[0].wave_height_m)
        self.assertEqual(result.records[1].wave_height_m,1.2)
        self.assertEqual(result.records[1].wave_period_s,4.0)
        self.assertEqual(result.wave_fetch_status,'partial')
        self.assertEqual(result.records[1].latitude,41.21)
        self.assertEqual(result.wave_grid_latitude,41.208)
        self.assertIn('marine-api.open-meteo.com',result.wave_source_url)

    def test_nulls_remain_missing(self):
        with patch('weather_data.service.urlopen',side_effect=[self.response(self.atmosphere()),self.response(self.marine([None,None]))]):
            result=fetch_dataset(self.request())
        self.assertEqual(result.wave_fetch_status,'unavailable')
        self.assertTrue(all(record.wave_height_m is None for record in result.records))

    def test_network_failure_preserves_atmosphere_and_explicit_failure(self):
        with patch('weather_data.service.urlopen',side_effect=[self.response(self.atmosphere()),URLError('offline')]):
            result=fetch_dataset(self.request())
        self.assertEqual(result.records[0].wind_speed_ms,5)
        self.assertEqual(result.wave_fetch_status,'unavailable')
        self.assertIn('unavailable',result.wave_fetch_detail)

    def test_distant_grid_and_malformed_array_rejected_without_partial_merge(self):
        for defect in ('distance','array'):
            marine=self.marine()
            if defect=='distance':marine['longitude']=40
            else:marine['hourly']['wave_period']=[]
            with self.subTest(defect=defect),patch('weather_data.service.urlopen',side_effect=[self.response(self.atmosphere()),self.response(marine)]):
                result=fetch_dataset(self.request())
            self.assertEqual(result.wave_fetch_status,'unavailable')
            self.assertTrue(all(record.wave_height_m is None for record in result.records))

    def test_archive_and_disabled_forecast_do_not_call_marine(self):
        for request,status in ((self.request(kind='archive'),'not_applicable'),
                               (self.request(include_waves=False),'not_requested')):
            with patch('weather_data.service.urlopen',return_value=self.response(self.atmosphere())) as call:
                result=fetch_dataset(request)
            self.assertEqual(call.call_count,1)
            self.assertEqual(result.wave_fetch_status,status)

    def test_complete_merge_changes_hash(self):
        marine=self.marine();marine['hourly']['time']=self.atmosphere()['hourly']['time']
        with patch('weather_data.service.urlopen',side_effect=[self.response(self.atmosphere()),self.response(marine)]):
            complete=fetch_dataset(self.request())
        with patch('weather_data.service.urlopen',return_value=self.response(self.atmosphere())):
            missing=fetch_dataset(self.request(include_waves=False))
        self.assertEqual(complete.wave_fetch_status,'complete')
        self.assertNotEqual(complete.content_hash,missing.content_hash)
