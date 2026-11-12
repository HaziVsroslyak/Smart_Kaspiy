"""Weather-aware Dijkstra routing on a synthetic North–South corridor graph."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal, Protocol, TypedDict

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ml_predictor import TransitFeatures

Season = Literal["winter", "spring", "summer", "autumn"]


class DelayPredictor(Protocol):
    def predict_delay(self, features: Mapping[str, object]) -> float:
        """Return a finite, nonnegative delay in hours."""
        ...


class UnknownNodeError(ValueError):
    """The requested terminal does not exist."""


class RouteNotFoundError(RuntimeError):
    """No directed path connects the requested terminals."""


class InvalidGraphError(ValueError):
    """An edge has missing or invalid routing attributes."""


class PredictionError(RuntimeError):
    """Prediction failed or returned an invalid edge weight."""


class _EdgeAttributes(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    base_time_hours: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    co2_emissions_kg: float = Field(ge=0)
    transport_mode: Literal["ship", "rail"]
    port_congestion: float = Field(ge=0, le=100)


class RouteSegment(TypedDict):
    source: str
    target: str
    edge_id: str | int
    transport_mode: Literal["ship", "rail"]
    base_time_hours: float
    delay_hours: float
    expected_time_hours: float
    cost_usd: float
    co2_emissions_kg: float


class RouteResult(TypedDict):
    nodes: list[str]
    segments: list[RouteSegment]
    total_base_time_hours: float
    total_delay_hours: float
    total_time_hours: float
    total_cost_usd: float
    total_co2_emissions_kg: float


class OptimalRoutes(TypedDict):
    fastest: RouteResult
    eco: RouteResult


def create_transport_graph() -> nx.MultiDiGraph:
    """Build a fresh graph with illustrative times/costs/CO2 per one TEU.

    Edges represent whole simplified itineraries, including intermediate land
    sections that are not shown. They do not assert direct railway connections.
    Parallel edges preserve transport alternatives. Reverse trips are explicit.
    """
    graph = nx.MultiDiGraph()
    for city, kind in [
        ("Астрахань", "port_station"), ("Махачкала", "port_station"),
        ("Энзели", "port"), ("Решт", "station"),
    ]:
        graph.add_node(city, kind=kind)
    links: list[tuple[str, str, str, float, float, float, float]] = [
        ("Астрахань", "Махачкала", "rail", 14.0, 350.0, 35.0, 30.0),
        ("Астрахань", "Энзели", "ship", 32.0, 650.0, 180.0, 55.0),
        ("Махачкала", "Энзели", "ship", 20.0, 500.0, 140.0, 45.0),
        ("Махачкала", "Энзели", "rail", 46.0, 900.0, 65.0, 30.0),
        ("Махачкала", "Решт", "rail", 48.0, 950.0, 70.0, 25.0),
        ("Энзели", "Решт", "rail", 2.0, 100.0, 8.0, 20.0),
    ]
    for source, target, mode, hours, cost, co2, congestion in links:
        for start, end in ((source, target), (target, source)):
            graph.add_edge(
                start, end, key=mode, transport_mode=mode,
                base_time_hours=hours, cost_usd=cost,
                co2_emissions_kg=co2, port_congestion=congestion,
            )
    return graph


def _route_result(path: list[str], projection: nx.DiGraph) -> RouteResult:
    segments: list[RouteSegment] = [
        dict(projection[start][end]["segment"])
        for start, end in zip(path, path[1:])
    ]
    return {
        "nodes": path,
        "segments": segments,
        "total_base_time_hours": math.fsum(s["base_time_hours"] for s in segments),
        "total_delay_hours": math.fsum(s["delay_hours"] for s in segments),
        "total_time_hours": math.fsum(s["expected_time_hours"] for s in segments),
        "total_cost_usd": math.fsum(s["cost_usd"] for s in segments),
        "total_co2_emissions_kg": math.fsum(s["co2_emissions_kg"] for s in segments),
    }


def find_optimal_route(
    source: str,
    target: str,
    predictor: DelayPredictor,
    current_weather: float,
    *,
    graph: nx.MultiDiGraph | None = None,
    season: Season = "summer",
) -> OptimalRoutes:
    """Return fastest and minimum-CO2 routes using two Dijkstra searches.

    Weather severity (0–10) and season apply to every segment for this snapshot.
    Congestion and mode come from each edge. Predictions are evaluated once per
    edge per call and shared by both searches. The supplied graph is not mutated.
    The default season is an explicit demo assumption, not the system date.
    Identical endpoints return zero-length routes without calling the predictor.
    """
    # Reuse module 1's exact feature contract, including strict numeric validation.
    context = TransitFeatures(
        weather_severity=current_weather, port_congestion=0.0,
        transport_mode="ship", season=season,
    )
    network = create_transport_graph() if graph is None else graph
    if not isinstance(network, nx.MultiDiGraph):
        raise TypeError("graph must be a networkx.MultiDiGraph.")
    if not isinstance(source, str) or not isinstance(target, str):
        raise TypeError("source and target must be terminal names.")
    for node in (source, target):
        if node not in network:
            raise UnknownNodeError(f"Unknown terminal: {node}")
    if source == target:
        return {"fastest": _route_result([source], nx.DiGraph()),
                "eco": _route_result([source], nx.DiGraph())}
    if not nx.has_path(network, source, target):
        raise RouteNotFoundError(f"No route from {source} to {target}.")

    fastest_graph = nx.DiGraph()
    eco_graph = nx.DiGraph()
    fastest_graph.add_nodes_from(network.nodes)
    eco_graph.add_nodes_from(network.nodes)
    for start, end, key, raw in network.edges(keys=True, data=True):
        if not isinstance(start, str) or not isinstance(end, str) or type(key) not in (str, int):
            raise InvalidGraphError("Edges require string terminals and string/integer keys.")
        try:
            attributes = _EdgeAttributes.model_validate(raw)
        except ValidationError as exc:
            raise InvalidGraphError(f"Invalid edge {start} -> {end} ({key}): {exc}") from exc
        features = TransitFeatures(
            weather_severity=context.weather_severity,
            port_congestion=attributes.port_congestion,
            transport_mode=attributes.transport_mode,
            season=context.season,
        )
        try:
            raw_delay = predictor.predict_delay(features.model_dump())
            if isinstance(raw_delay, (bool, str, bytes)):
                raise ValueError("Delay must be numeric.")
            delay = float(raw_delay)
            if not math.isfinite(delay) or delay < 0:
                raise ValueError("Delay must be finite and nonnegative.")
        except Exception as exc:
            raise PredictionError(f"Prediction failed for {start} -> {end} ({key}).") from exc
        expected_time = attributes.base_time_hours + delay
        if not math.isfinite(expected_time):
            raise PredictionError(f"Expected time overflow for {start} -> {end} ({key}).")
        segment: RouteSegment = {
            "source": start, "target": end, "edge_id": key,
            "transport_mode": attributes.transport_mode,
            "base_time_hours": attributes.base_time_hours,
            "delay_hours": delay, "expected_time_hours": expected_time,
            "cost_usd": attributes.cost_usd,
            "co2_emissions_kg": attributes.co2_emissions_kg,
        }
        # Collapse parallel edges separately for each objective, retaining the
        # actual chosen edge and its metrics instead of just the terminal path.
        for projection, weight in (
            (fastest_graph, expected_time), (eco_graph, attributes.co2_emissions_kg),
        ):
            if not projection.has_edge(start, end) or weight < projection[start][end]["weight"]:
                projection.add_edge(start, end, weight=weight, segment=segment)

    fastest_path = nx.dijkstra_path(fastest_graph, source, target, weight="weight")
    eco_path = nx.dijkstra_path(eco_graph, source, target, weight="weight")
    return {
        "fastest": _route_result(fastest_path, fastest_graph),
        "eco": _route_result(eco_path, eco_graph),
    }


if __name__ == "__main__":
    import json

    from ml_predictor import TransitPredictor

    model = TransitPredictor().train()
    result = find_optimal_route("Махачкала", "Решт", model, 7.0, season="winter")
    print(json.dumps(result, ensure_ascii=True, indent=2))
