"""HTTP contract checks for the offline synthetic JIT demonstration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from secure_client import SecureClient as TestClient
from main import app
from voyage_store import VoyageStore


class DemoApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory()
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.store_patch = patch.object(app.state, 'voyages', app.state.voyages)
        cls.store_patch.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store_patch.stop()
        cls.client.__exit__(None,None,None)
        cls.folder.cleanup()

    def test_capability_and_catalog(self) -> None:
        health = self.client.get('/api/v1/health')
        self.assertEqual(health.status_code, 200)
        self.assertIn('synthetic_jit_v1', health.json()['capabilities'])
        self.assertIn('api_version', health.json())
        response = self.client.get('/api/v1/demo/scenarios')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['scenarios']), 8)
        self.assertEqual(response.json()['model_report']['data_source'], 'synthetic')

    def test_run_and_restore_need_no_weather_network(self) -> None:
        with patch('weather_service.urlopen', side_effect=AssertionError('No network in synthetic demo')):
            response = self.client.post('/api/v1/demo/scenarios/berth_queue/run', json={'seed':42})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['data_source'], 'synthetic')
        self.assertEqual(body['baseline'], body['strategies'][0])
        self.assertEqual({trace['target'] for trace in body['predictions']}, {'sea','land','readiness'})
        restored = self.client.get('/api/v1/demo/runs/'+body['id'])
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), body)
        changed = self.client.post('/api/v1/demo/scenarios/berth_queue/run', json={'port_congestion_percent':95})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['inputs']['port_congestion_percent'],95)
        self.assertNotEqual(changed.json()['id'], body['id'])
        self.assertEqual(self.client.get('/api/v1/demo/runs/'+body['id']).json(), body)

    def test_unknown_and_invalid_inputs(self) -> None:
        self.assertEqual(self.client.post('/api/v1/demo/scenarios/missing/run',json={}).status_code,404)
        self.assertEqual(self.client.get('/api/v1/demo/runs/missing').status_code,404)
        for payload in ({'wind_speed_ms':26}, {'wave_height_m':0}, {'seed':True}, {'port_congestion_percent':101}, {'unexpected':1}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/api/v1/demo/scenarios/calm/run',json=payload).status_code,422)

    def test_unready_demo_returns_503(self) -> None:
        with patch.object(app.state,'resources',None):
            self.assertEqual(self.client.get('/api/v1/demo/scenarios').status_code,503)
            self.assertEqual(self.client.post('/api/v1/demo/scenarios/calm/run',json={}).status_code,503)

    def test_saved_voyage_simulation_preserves_its_baseline(self) -> None:
        payload={'source':'Махачкала','target':'Решт','departure_at':'2026-11-12T00:00:00Z',
                 'transport_modes':['ship','rail'],'conditions':{'weather_mode':'scenario',
                 'scenario':{'source':'scenario','wind_speed_ms':4,'wave_height_m':1}}}
        response=self.client.post('/api/v1/voyages',json=payload)
        self.assertEqual(response.status_code,201,response.text)
        saved=response.json()
        with patch('weather_service.urlopen',side_effect=AssertionError('Synthetic saved voyage must not access APIs')):
            response=self.client.post(f'/api/v1/voyages/{saved["id"]}/jit/simulate',json={})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['parent_voyage_id'],saved['id'])
        self.assertEqual(response.json()['strategies'][1]['status'],'ok')
        self.assertEqual(response.json()['strategies'][2]['status'],'blocked')
        self.assertEqual(self.client.get(f'/api/v1/voyages/{saved["id"]}').json(),saved)
        road=self.client.post('/api/v1/voyages',json={**payload,'transport_modes':['road']}).json()
        result=self.client.post(f'/api/v1/voyages/{road["id"]}/jit/simulate',json={})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['strategies'][0]['status'],'not_applicable')
        self.assertEqual(result.json()['predictions'],[])

    def test_saved_winter_voyage_uses_utc_season_and_no_onward_leg(self) -> None:
        response=self.client.post('/api/v1/voyages',json={
            'source':'Астрахань','target':'Энзели','departure_at':'2026-01-15T00:00:00Z',
            'transport_modes':['ship','road'],'conditions':{'weather_mode':'scenario','road':{'closed':True},
            'scenario':{'source':'scenario','wind_speed_ms':4,'wave_height_m':1}}})
        self.assertEqual(response.status_code,201,response.text)
        saved=response.json()
        response=self.client.post(f'/api/v1/voyages/{saved["id"]}/jit/simulate',json={})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertTrue(all(p['features']['season']=='Winter' for p in result['predictions'] if p['target']=='sea'))
        self.assertEqual(result['strategies'][2]['status'],'blocked')
        strategy=result['strategies'][0]
        self.assertEqual(strategy['nodes'],['Астрахань','Энзели'])
        self.assertAlmostEqual(strategy['total_time_hours'],sum(s['expected_time_hours'] for s in strategy['segments']))
