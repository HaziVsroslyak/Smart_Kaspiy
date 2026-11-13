"""App-factory isolation and HTTP compatibility without training models."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.application import create_app
from api.config import BACKEND_ROOT, Settings


class ApplicationStructureTests(unittest.TestCase):
    def test_factory_defers_storage_and_isolates_lifecycles(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first_path = Path(folder) / 'first.sqlite3'
            second_path = Path(folder) / 'second.sqlite3'
            first = create_app(Settings(database_path=first_path))
            second = create_app(Settings(database_path=second_path))
            self.assertFalse(first_path.exists())
            self.assertFalse(second_path.exists())
            with patch('api.application.build_resources', return_value=object()):
                with TestClient(first) as left, TestClient(second) as right:
                    self.assertIsNot(first.state.voyages, second.state.voyages)
                    self.assertEqual(first.state.voyages.path, first_path)
                    self.assertEqual(second.state.voyages.path, second_path)
                    self.assertEqual(left.get('/healthz').json()['status'], 'ok')
                    self.assertEqual(right.get('/healthz').status_code, 200)
                self.assertIsNone(first.state.resources)
                self.assertIsNone(first.state.voyages)

    def test_startup_failure_clears_resources(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Settings(database_path=Path(folder) / 'test.sqlite3'))
            with patch('api.application.build_resources', side_effect=RuntimeError('training failed')):
                with self.assertRaisesRegex(RuntimeError, 'training failed'):
                    with TestClient(app):
                        pass
            self.assertIsNone(app.state.weather)
            self.assertIsNone(app.state.voyages)

    def test_configuration_is_backend_relative(self) -> None:
        self.assertNotIn('private-key', repr(Settings(openweather_api_key='private-key')))
        with patch.dict(os.environ, {'DATABASE_PATH': 'artifacts/custom.sqlite3'}):
            self.assertEqual(Settings.from_environment().database_path, BACKEND_ROOT / 'artifacts/custom.sqlite3')

    def test_route_inventory_and_validation_contract(self) -> None:
        app = create_app(Settings())
        schema = app.openapi()
        self.assertIn('/api/v1/auth/login',schema['paths'])
        for path in ('/api/v1/voyages', '/api/v1/demo/scenarios', '/api/v1/customs/clear',
                     '/api/v1/route/calculate', '/api/v1/optimize/jit'):
            self.assertIn(path, schema['paths'])
        self.assertFalse(schema['components']['schemas']['RouteRequest']['additionalProperties'])
        self.assertEqual(schema['components']['schemas']['JITResponse']['properties']['new_speed_knots']['minimum'], 6)
