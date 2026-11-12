"""Run locally: python -m uvicorn main:app --reload"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

import networkx as nx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from jit_optimizer import JITInput, MIN_SPEED_KNOTS
from ml_predictor import TransitPredictor, generate_mock_data
from ml_pipeline import CaspianFeatures, CaspianPredictor, generate_mock_data as generate_caspian_data
from prediction_service import (
    DelayPrediction, ForecastDelayPrediction, ForecastDelayRequest, predict_from_weather,
)
from weather_service import Coordinates, OpenWeatherService, WeatherError, WeatherForecast
from routing_engine import (
    InvalidGraphError, PredictionError, RouteNotFoundError, Season,
    UnknownNodeError, create_transport_graph, find_optimal_route,
)
from smart_customs import CargoData
from smart_customs_and_jit import CargoPayload, optimize_vessel_speed, verify_customs_hash
from route_weather import RouteWeather, WeatherImpact, resolve_route_weather
from voyage_models import VoyageRequest, VoyageUpdate, VoyageResponse
from voyage_service import calculate_voyage
from voyage_store import VoyageStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutingResources:
    predictor: TransitPredictor
    graph: nx.MultiDiGraph
    caspian_predictor: CaspianPredictor


def build_resources() -> RoutingResources:
    predictor = TransitPredictor().train(generate_mock_data())
    caspian_predictor = CaspianPredictor().train(generate_caspian_data())
    return RoutingResources(predictor, create_transport_graph(), caspian_predictor)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    application.state.resources = None
    application.state.weather = OpenWeatherService(os.getenv("OPENWEATHER_API_KEY"))
    application.state.voyages = VoyageStore(Path(__file__).resolve().parent / "artifacts" / "voyages.sqlite3")
    try:
        application.state.resources = await run_in_threadpool(build_resources)
        yield
    finally:
        application.state.resources = None
        application.state.weather = None


app = FastAPI(title="Smart Caspian Transit", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class HealthResponse(ApiModel):
    status: Literal["ready", "not_ready"]
    routing_ready: bool
    caspian_model_ready: bool
    weather_configured: bool


@app.get("/api/v1/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    ready = getattr(request.app.state, "resources", None) is not None
    service = getattr(request.app.state, "weather", None)
    return HealthResponse(
        status="ready" if ready else "not_ready", routing_ready=ready,
        caspian_model_ready=ready, weather_configured=bool(service and service.configured),
    )


def get_weather(request: Request) -> OpenWeatherService:
    service = getattr(request.app.state, "weather", None)
    if service is None:
        raise HTTPException(503, "Weather service is not initialized.")
    return service


@app.get("/api/v1/weather/forecast", response_model=WeatherForecast)
def weather_forecast(
    request: Request,
    latitude: float = Query(ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(ge=-180, le=180, allow_inf_nan=False),
) -> WeatherForecast:
    try:
        return get_weather(request).forecast(Coordinates(latitude=latitude, longitude=longitude))
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@app.post("/api/v1/predictions/delay", response_model=DelayPrediction)
def predict_delay(payload: CaspianFeatures, request: Request) -> DelayPrediction:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Caspian model is not ready.")
    return DelayPrediction(
        delay_hours=resources.caspian_predictor.predict(payload.model_dump()), features_used=payload,
    )


@app.post("/api/v1/predictions/delay-from-weather", response_model=ForecastDelayPrediction)
def predict_weather_delay(payload: ForecastDelayRequest, request: Request) -> ForecastDelayPrediction:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Caspian model is not ready.")
    try:
        return predict_from_weather(payload, resources.caspian_predictor, get_weather(request))
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except ValueError:
        raise HTTPException(422, "Forecast time or weather features are outside the supported model range.") from None


class CustomsRequest(ApiModel):
    cargo_payload: CargoPayload
    provided_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$", min_length=64, max_length=64)


class LegacyCustomsRequest(ApiModel):
    """Previously published cargo_data request, retained for existing clients."""

    cargo_data: CargoData
    provided_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$", min_length=64, max_length=64)


class CustomsResponse(ApiModel):
    status: Literal["Pre-cleared", "Requires inspection"]
    green_corridor: bool


class RoadConditions(ApiModel):
    congestion_percent: float = Field(default=20, ge=0, le=100)
    condition_severity: float = Field(default=0, ge=0, le=10)
    border_wait_hours: float = Field(default=4, ge=0, le=168, description="Hours per border crossing")
    closed: bool = False


class RouteRequest(ApiModel):
    source: str = Field(min_length=1, max_length=200, pattern=r"\S")
    target: str = Field(min_length=1, max_length=200, pattern=r"\S")
    current_weather: float = Field(default=0, ge=0, le=10)
    season: Season = "summer"
    weather: RouteWeather | None = None
    transport_modes: list[Literal["ship", "rail", "road"]] = Field(default_factory=lambda: ["ship", "rail", "road"], min_length=1, max_length=3)
    road_conditions: RoadConditions = Field(default_factory=RoadConditions)


class RouteLeg(ApiModel):
    source: str
    target: str
    edge_id: str | int
    transport_mode: Literal["ship", "rail", "road"]
    base_time_hours: float = Field(ge=0)
    delay_hours: float = Field(ge=0)
    expected_time_hours: float = Field(ge=0)
    border_wait_hours: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    co2_emissions_kg: float = Field(ge=0)


class RouteDetails(ApiModel):
    nodes: list[str]
    segments: list[RouteLeg]
    total_base_time_hours: float = Field(ge=0)
    total_delay_hours: float = Field(ge=0)
    total_time_hours: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    total_co2_emissions_kg: float = Field(ge=0)


class RouteResponse(RouteDetails):
    eco: RouteDetails
    weather: WeatherImpact
    road_conditions: RoadConditions
    transport_modes: list[Literal["ship", "rail", "road"]]


class JITResponse(ApiModel):
    new_speed_knots: float = Field(ge=MIN_SPEED_KNOTS)
    arrival_in_hours: float = Field(gt=0)
    berth_available_in_hours: float = Field(gt=0)
    remaining_wait_hours: float = Field(ge=0)
    baseline_fuel_tonnes: float = Field(ge=0)
    optimized_fuel_tonnes: float = Field(ge=0)
    fuel_saved_tonnes: float = Field(ge=0)
    co2_saved_tonnes: float = Field(ge=0)
    fuel_coefficient: float = Field(gt=0)


@app.post("/api/v1/optimize/jit", response_model=JITResponse)
def optimize_jit(payload: JITInput) -> JITResponse:
    try:
        result = optimize_vessel_speed(
            payload.distance_nm, payload.current_speed_knots, payload.port_delay_hours,
        )
        return JITResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/customs/clear", response_model=CustomsResponse)
def clear_customs(payload: CustomsRequest | LegacyCustomsRequest) -> CustomsResponse:
    cargo = payload.cargo_payload if isinstance(payload, CustomsRequest) else payload.cargo_data
    verified = verify_customs_hash(cargo.model_dump(), payload.provided_hash)
    return CustomsResponse(
        status="Pre-cleared" if verified else "Requires inspection",
        green_corridor=verified,
    )


@app.post("/api/v1/route/calculate", response_model=RouteResponse)
def calculate_route(payload: RouteRequest, request: Request) -> RouteResponse:
    resources: RoutingResources | None = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(status_code=503, detail="Routing model is not ready.")
    try:
        impact = resolve_route_weather(payload.weather, payload.current_weather,
                                       getattr(request.app.state, "weather", None))
        network = resources.graph.copy()
        network.remove_edges_from([
            (start, end, key) for start, end, key, data in network.edges(keys=True, data=True)
            if data.get("transport_mode") not in payload.transport_modes
            or (data.get("transport_mode") == "road" and payload.road_conditions.closed)
        ])
        for _, _, data in network.edges(data=True):
            if data.get("transport_mode") == "road":
                data["road_congestion_percent"] = payload.road_conditions.congestion_percent
                data["road_condition_severity"] = payload.road_conditions.condition_severity
                data["border_wait_hours"] = payload.road_conditions.border_wait_hours * data.get("border_crossings", 0)
        if impact.sea_restricted:
            network.remove_edges_from([
                (start, end, key) for start, end, key, data in network.edges(keys=True, data=True)
                if data.get("transport_mode") == "ship"
            ])
        # The engine predicts delays once per edge and adds them to base times.
        routes = find_optimal_route(
            payload.source, payload.target, resources.predictor,
            impact.severity, graph=network, season=payload.season,
        )
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RouteNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PredictionError as exc:
        logger.exception("Route prediction failed")
        raise HTTPException(status_code=503, detail="Delay prediction is unavailable.") from exc
    except InvalidGraphError as exc:
        logger.exception("Invalid routing graph")
        raise HTTPException(status_code=500, detail="Routing network is invalid.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fastest = routes["fastest"]
    return RouteResponse(**fastest, eco=RouteDetails(**routes["eco"]), weather=impact,
                         road_conditions=payload.road_conditions, transport_modes=payload.transport_modes)


def voyage_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "Voyage not found.")
    if isinstance(exc, WeatherError):
        return HTTPException(exc.status_code, str(exc))
    if isinstance(exc, RouteNotFoundError):
        return HTTPException(409, str(exc))
    if isinstance(exc, PredictionError):
        return HTTPException(503, "Delay prediction is unavailable.")
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(409, str(exc))


@app.post("/api/v1/voyages", response_model=VoyageResponse, status_code=201)
def create_voyage(payload: VoyageRequest, request: Request) -> VoyageResponse:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Routing model is not ready.")
    try:
        snapshot = calculate_voyage(payload, payload.conditions, resources.graph,
                                    resources.predictor, request.app.state.weather)
        return request.app.state.voyages.create(payload, snapshot)
    except (WeatherError, RouteNotFoundError, PredictionError, ValueError) as exc:
        raise voyage_failure(exc) from None


@app.get("/api/v1/voyages/{voyage_id}", response_model=VoyageResponse)
def get_voyage(voyage_id: str, request: Request) -> VoyageResponse:
    try:
        return request.app.state.voyages.get(voyage_id)
    except KeyError as exc:
        raise voyage_failure(exc) from None


@app.post("/api/v1/voyages/{voyage_id}/reforecast", response_model=VoyageResponse)
def reforecast_voyage(voyage_id: str, payload: VoyageUpdate, request: Request) -> VoyageResponse:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Routing model is not ready.")
    try:
        saved = request.app.state.voyages.get(voyage_id)
        conditions = payload.conditions if payload.conditions is not None else saved.conditions
        snapshot = calculate_voyage(saved.request, conditions, resources.graph,
                                    resources.predictor, request.app.state.weather)
        return request.app.state.voyages.update(voyage_id, snapshot, conditions, saved.revision)
    except (KeyError, WeatherError, RouteNotFoundError, PredictionError, ValueError, RuntimeError) as exc:
        raise voyage_failure(exc) from None
