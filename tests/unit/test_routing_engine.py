"""Routing checks with controlled delays and the real module 1 predictor."""

import copy
import math
import unittest
from collections.abc import Mapping

import networkx as nx

from ml_predictor import ModelNotTrainedError, TransitPredictor
from routing_engine import (
    InvalidGraphError, PredictionError, RouteNotFoundError, UnknownNodeError,
    create_transport_graph, find_optimal_route,
)


class WeatherPredictor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def predict_delay(self, features: Mapping[str, object]) -> float:
        self.calls.append(dict(features))
        return float(features["weather_severity"]) * (5 if features["transport_mode"] == "ship" else 0)


class ConstantPredictor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict_delay(self, features: Mapping[str, object]) -> float:
        return self.value


class RoutingEngineTests(unittest.TestCase):
    def test_graph_contract_and_independence(self) -> None:
        graph = create_transport_graph()
        self.assertIsInstance(graph, nx.MultiDiGraph)
        self.assertEqual(set(graph), {"Астрахань", "Махачкала", "Энзели", "Решт"})
        self.assertEqual(graph.number_of_edges("Махачкала", "Энзели"), 2)
        for source, target, key, data in graph.edges(keys=True, data=True):
            self.assertTrue(graph.has_edge(target, source, key))
            for attribute in ("base_time_hours", "cost_usd", "co2_emissions_kg"):
                self.assertGreaterEqual(data[attribute], 0)
        graph.clear()
        self.assertEqual(len(create_transport_graph()), 4)

    def test_weather_changes_fastest_but_not_co2_objective(self) -> None:
        calm = find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 0)
        storm = find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 10)
        self.assertEqual(calm["fastest"]["nodes"], ["Махачкала", "Энзели", "Решт"])
        self.assertEqual(storm["fastest"]["nodes"], ["Махачкала", "Решт"])
        self.assertEqual(calm["eco"]["nodes"], storm["eco"]["nodes"])
        self.assertEqual(calm["eco"]["total_co2_emissions_kg"], 70)

    def test_parallel_edges_and_aggregates(self) -> None:
        result = find_optimal_route("Махачкала", "Энзели", ConstantPredictor(1), 0)
        self.assertEqual(result["fastest"]["segments"][0]["edge_id"], "ship")
        self.assertEqual(result["eco"]["segments"][0]["edge_id"], "rail")
        self.assertEqual(result["fastest"]["total_time_hours"], 21)
        self.assertEqual(result["eco"]["total_time_hours"], 47)
        for route in result.values():
            for total, segment in [
                ("total_time_hours", "expected_time_hours"),
                ("total_cost_usd", "cost_usd"),
                ("total_co2_emissions_kg", "co2_emissions_kg"),
                ("total_delay_hours", "delay_hours"),
                ("total_base_time_hours", "base_time_hours"),
            ]:
                self.assertEqual(route[total], sum(s[segment] for s in route["segments"]))

    def test_prediction_context_and_no_graph_mutation(self) -> None:
        graph = create_transport_graph()
        before = copy.deepcopy(graph)
        predictor = WeatherPredictor()
        find_optimal_route("Астрахань", "Решт", predictor, 3, graph=graph, season="winter")
        self.assertEqual(len(predictor.calls), graph.number_of_edges())
        self.assertEqual(predictor.calls[0], {
            "weather_severity": 3.0, "port_congestion": 30.0,
            "transport_mode": "rail", "season": "winter",
        })
        self.assertTrue(nx.utils.graphs_equal(graph, before))

    def test_identical_endpoints_do_not_need_model(self) -> None:
        result = find_optimal_route("Решт", "Решт", TransitPredictor(), 0)
        for route in result.values():
            self.assertEqual(route["nodes"], ["Решт"])
            self.assertEqual(route["segments"], [])
            self.assertEqual(route["total_time_hours"], 0)
        result["fastest"]["nodes"].clear()
        self.assertEqual(result["eco"]["nodes"], ["Решт"])

    def test_unknown_terminal_and_disconnected_graph(self) -> None:
        with self.assertRaises(UnknownNodeError):
            find_optimal_route("Unknown", "Решт", WeatherPredictor(), 0)
        graph = create_transport_graph()
        graph.remove_edges_from(list(graph.in_edges("Решт", keys=True)))
        with self.assertRaises(RouteNotFoundError):
            find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 0, graph=graph)
        # Incoming edges removed; outgoing direction remains usable.
        self.assertTrue(find_optimal_route("Решт", "Махачкала", WeatherPredictor(), 0, graph=graph))

    def test_invalid_weather_and_season(self) -> None:
        for weather in (-1, 11, float("nan"), float("inf"), True, "5"):
            with self.subTest(weather=weather), self.assertRaises(ValueError):
                find_optimal_route("Махачкала", "Решт", WeatherPredictor(), weather)
        with self.assertRaises(ValueError):
            find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 0, season="unknown")

    def test_invalid_graph_attributes(self) -> None:
        for attribute, value in [
            ("base_time_hours", -1), ("cost_usd", float("nan")),
            ("co2_emissions_kg", -1), ("port_congestion", 101),
            ("transport_mode", "truck"),
        ]:
            graph = create_transport_graph()
            graph["Махачкала"]["Энзели"]["ship"][attribute] = value
            with self.subTest(attribute=attribute), self.assertRaises(InvalidGraphError):
                find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 0, graph=graph)
        graph = create_transport_graph()
        del graph["Махачкала"]["Энзели"]["ship"]["base_time_hours"]
        with self.assertRaises(InvalidGraphError):
            find_optimal_route("Махачкала", "Решт", WeatherPredictor(), 0, graph=graph)

    def test_invalid_predictions_and_untrained_model(self) -> None:
        for value in (-1, float("nan"), float("inf"), True, "5"):
            with self.subTest(value=value), self.assertRaises(PredictionError):
                find_optimal_route("Махачкала", "Решт", ConstantPredictor(value), 0)
        with self.assertRaises(PredictionError) as raised:
            find_optimal_route("Махачкала", "Решт", TransitPredictor(), 0)
        self.assertIsInstance(raised.exception.__cause__, ModelNotTrainedError)

    def test_real_ml_predictor_integration(self) -> None:
        predictor = TransitPredictor().train()
        result = find_optimal_route("Астрахань", "Решт", predictor, 7, season="winter")
        for route in result.values():
            self.assertTrue(math.isfinite(route["total_time_hours"]))
            self.assertGreater(route["total_time_hours"], route["total_base_time_hours"])
        self.assertLessEqual(result["fastest"]["total_time_hours"], result["eco"]["total_time_hours"])
        self.assertLessEqual(result["eco"]["total_co2_emissions_kg"], result["fastest"]["total_co2_emissions_kg"])


if __name__ == "__main__":
    unittest.main()
