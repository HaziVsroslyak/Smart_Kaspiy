import copy
import unittest
from unittest.mock import patch

from secure_client import SecureClient as TestClient
import networkx as nx

from main import app
from routing_engine import InvalidGraphError, PredictionError, RouteNotFoundError
from smart_customs import CustomsPreClearance
from smart_customs_and_jit import calculate_customs_hash


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def route_payload(self) -> dict[str, object]:
        return {"source": "Махачкала", "target": "Решт", "current_weather": 7.0}

    def test_customs_statuses(self) -> None:
        cargo = {"weight": 100, "type": "Зерно", "sender": "A", "recipient": "B"}
        digest = CustomsPreClearance.calculate_cargo_hash(cargo)
        response = self.client.post("/api/v1/customs/clear", json={"cargo_data": cargo, "provided_hash": digest})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "Pre-cleared", "green_corridor": True})
        response = self.client.post("/api/v1/customs/clear", json={"cargo_data": cargo, "provided_hash": "0" * 64})
        self.assertEqual(response.json(), {"status": "Requires inspection", "green_corridor": False})
        response = self.client.post("/api/v1/customs/clear", json={"cargo_data": cargo, "provided_hash": "invalid"})
        self.assertEqual(response.status_code, 422)

    def test_real_routing_and_validation(self) -> None:
        original_graph = copy.deepcopy(app.state.resources.graph)
        response = self.client.post("/api/v1/route/calculate", json=self.route_payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["nodes"][0], "Махачкала")
        self.assertEqual(body["nodes"][-1], "Решт")
        self.assertGreater(body["total_time_hours"], 0)
        self.assertGreater(body["total_cost_usd"], 0)
        self.assertTrue(nx.utils.graphs_equal(original_graph, app.state.resources.graph))
        for value in (-1, 11, True, "7"):
            response = self.client.post("/api/v1/route/calculate", json={**self.route_payload(), "current_weather": value})
            self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/v1/route/calculate", json={**self.route_payload(), "source": "Unknown"})
        self.assertEqual(response.status_code, 404)

    def test_identical_terminals(self) -> None:
        response = self.client.post("/api/v1/route/calculate", json={**self.route_payload(), "source": "Решт"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"], ["Решт"])
        self.assertEqual(response.json()["segments"], [])
        self.assertEqual(response.json()["total_time_hours"], 0)
        self.assertEqual(response.json()["total_cost_usd"], 0)

    def test_weather_reroutes_without_mutating_shared_network(self) -> None:
        original = copy.deepcopy(app.state.resources.graph)
        request = {**self.route_payload(), "season": "summer"}
        calm = self.client.post("/api/v1/route/calculate", json={**request, "weather": {
            "source": "scenario", "wind_speed_ms": 4, "wave_height_m": 1,
        }})
        storm = self.client.post("/api/v1/route/calculate", json={**request, "weather": {
            "source": "scenario", "wind_speed_ms": 22, "wave_height_m": 3.2,
        }})
        self.assertEqual(calm.status_code, 200)
        self.assertIn("ship", [s["transport_mode"] for s in calm.json()["segments"]])
        self.assertEqual(storm.status_code, 200)
        self.assertTrue(storm.json()["weather"]["sea_restricted"])
        for route in (storm.json(), storm.json()["eco"]):
            self.assertTrue(all(s["transport_mode"] != "ship" for s in route["segments"]))
            self.assertAlmostEqual(route["total_time_hours"], sum(s["expected_time_hours"] for s in route["segments"]))
            self.assertAlmostEqual(route["total_co2_emissions_kg"], sum(s["co2_emissions_kg"] for s in route["segments"]))
        restored = self.client.post("/api/v1/route/calculate", json={**request, "weather": {
            "source": "scenario", "wind_speed_ms": 4, "wave_height_m": 1,
        }})
        self.assertEqual(calm.json(), restored.json())
        self.assertTrue(nx.utils.graphs_equal(original, app.state.resources.graph))

    def test_storm_can_make_destination_unreachable(self) -> None:
        from dataclasses import replace
        graph = app.state.resources.graph.copy()
        graph.remove_edges_from([(u, v, k) for u, v, k, data in graph.edges(keys=True, data=True)
                                 if data["transport_mode"] != "ship"])
        with patch.object(app.state, "resources", replace(app.state.resources, graph=graph)):
            response = self.client.post("/api/v1/route/calculate", json={
                "source": "Махачкала", "target": "Энзели",
                "weather": {"source": "scenario", "wind_speed_ms": 20},
            })
        self.assertEqual(response.status_code, 409)

    def test_service_errors(self) -> None:
        for error, status in [(RouteNotFoundError("No route"), 409), (PredictionError("internal"), 503), (InvalidGraphError("internal"), 500)]:
            with self.subTest(status=status), patch("api.routers.routing.find_optimal_route", side_effect=error), patch("api.routers.routing.logger"):
                response = self.client.post("/api/v1/route/calculate", json=self.route_payload())
                self.assertEqual(response.status_code, status)
                self.assertNotIn("internal", response.text)
        with patch.object(app.state, "resources", None):
            response = self.client.post("/api/v1/route/calculate", json=self.route_payload())
            self.assertEqual(response.status_code, 503)

    def test_road_filters_borders_and_closures(self) -> None:
        original = copy.deepcopy(app.state.resources.graph)
        payload = {"source": "Махачкала", "target": "Энзели", "transport_modes": ["road"],
                   "road_conditions": {"border_wait_hours": 0}}
        first = self.client.post("/api/v1/route/calculate", json=payload)
        queued = self.client.post("/api/v1/route/calculate", json={**payload,
                                  "road_conditions": {"border_wait_hours": 12}})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(first.json()["segments"][0]["transport_mode"], "road")
        self.assertEqual(queued.json()["segments"][0]["border_wait_hours"], 36)
        self.assertAlmostEqual(queued.json()["total_time_hours"]-first.json()["total_time_hours"], 36)
        domestic = self.client.post("/api/v1/route/calculate", json={**payload, "source": "Энзели", "target": "Решт",
                                    "road_conditions": {"border_wait_hours": 12}})
        self.assertEqual(domestic.json()["segments"][0]["border_wait_hours"], 0)
        closed = self.client.post("/api/v1/route/calculate", json={**payload,"road_conditions":{"closed":True}})
        self.assertEqual(closed.status_code, 409)
        storm = self.client.post("/api/v1/route/calculate", json={**payload,
                                 "weather":{"source":"scenario","wind_speed_ms":22}})
        self.assertEqual(storm.status_code, 200)
        maximum = self.client.post("/api/v1/route/calculate", json={**payload,
                                   "road_conditions":{"border_wait_hours":168}})
        self.assertEqual(maximum.status_code, 200, maximum.text)
        self.assertEqual(maximum.json()["segments"][0]["border_wait_hours"], 504)
        alternative = self.client.post("/api/v1/route/calculate", json={**payload,
                                       "transport_modes":["ship","rail","road"],
                                       "road_conditions":{"closed":True}})
        self.assertEqual(alternative.status_code, 200)
        self.assertTrue(all(s["transport_mode"] != "road" for s in alternative.json()["segments"]))
        for modes in ([], ["truck"]):
            invalid = self.client.post("/api/v1/route/calculate", json={**payload,"transport_modes":modes})
            self.assertEqual(invalid.status_code, 422)
        self.assertTrue(nx.utils.graphs_equal(original, app.state.resources.graph))

    def test_cors_and_openapi(self) -> None:
        response = self.client.options("/api/v1/route/calculate", headers={
            "Origin": "https://example.com", "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/customs/clear", schema["paths"])
        self.assertIn("/api/v1/route/calculate", schema["paths"])
        self.assertIn("/api/v1/optimize/jit", schema["paths"])

    def test_customs_id_payload(self) -> None:
        cargo = {"weight": 100, "type": "Зерно", "id": "C-001"}
        digest = calculate_customs_hash(cargo)
        response = self.client.post("/api/v1/customs/clear", json={
            "cargo_payload": cargo, "provided_hash": digest,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "Pre-cleared", "green_corridor": True})
        response = self.client.post("/api/v1/customs/clear", json={
            "cargo_payload": {**cargo, "id": "C-002"}, "provided_hash": digest,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["green_corridor"])
        for invalid in ({"weight": 100, "type": "Зерно"}, {**cargo, "weight": -1}):
            response = self.client.post("/api/v1/customs/clear", json={
                "cargo_payload": invalid, "provided_hash": digest,
            })
            self.assertEqual(response.status_code, 422)

    def test_jit_and_remaining_wait(self) -> None:
        payload = {"distance_nm": 120, "current_speed_knots": 12, "port_delay_hours": 5}
        # JIT is independent of the trained ML model.
        with patch.object(app.state, "resources", None):
            response = self.client.post("/api/v1/optimize/jit", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["new_speed_knots"], 8)
        self.assertEqual(body["remaining_wait_hours"], 0)
        self.assertAlmostEqual(body["co2_saved_tonnes"], 2.98944)
        self.assertAlmostEqual(body["baseline_fuel_tonnes"], 1.728)
        self.assertAlmostEqual(body["optimized_fuel_tonnes"], 0.768)
        response = self.client.post("/api/v1/optimize/jit", json={**payload, "port_delay_hours": 30})
        self.assertEqual(response.json()["new_speed_knots"], 6)
        self.assertEqual(response.json()["remaining_wait_hours"], 20)

    def test_jit_validation(self) -> None:
        payload = {"distance_nm": 120, "current_speed_knots": 12, "port_delay_hours": 5}
        for field, value in [("distance_nm", 0), ("current_speed_knots", 5),
                             ("port_delay_hours", -1), ("distance_nm", True),
                             ("distance_nm", "120"), ("extra", 1),
                             ("current_speed_knots", 1e308)]:
            with self.subTest(field=field, value=value):
                response = self.client.post("/api/v1/optimize/jit", json={**payload, field: value})
                self.assertEqual(response.status_code, 422)
