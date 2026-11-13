"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from jit_optimizer import MIN_SPEED_KNOTS
from routing_engine import Season
from smart_customs import CargoData
from smart_customs_and_jit import CargoPayload
from route_weather import RouteWeather, WeatherImpact


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class HealthResponse(ApiModel):
    status: Literal["ready", "not_ready"]
    routing_ready: bool
    caspian_model_ready: bool
    weather_configured: bool
    api_version: str = '0.2.0'
    capabilities: list[str] = Field(default_factory=lambda: ['voyages_v1', 'synthetic_jit_v1'])


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
