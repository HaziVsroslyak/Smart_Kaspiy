"""Typed, synthetic-only JIT demonstration contracts."""
from __future__ import annotations
from typing import Literal
from pydantic import AwareDatetime, Field
from voyage_models import Contract

class DemoRunRequest(Contract):
    dataset_id: str | None = Field(default=None, min_length=1, max_length=200)
    departure_at: AwareDatetime | None = Field(default=None, strict=False)
    seed: int = Field(default=42, ge=0, le=2147483647)
    wind_speed_ms: float | None = Field(default=None, ge=0, le=25)
    wave_height_m: float | None = Field(default=None, ge=0.1, le=4.5)
    port_congestion_percent: float | None = Field(default=None, ge=10, le=100)

class DemoScenario(Contract):
    id: str
    title: str
    description: str

class PredictionTrace(Contract):
    model_id: str
    target: str
    value_hours: float = Field(ge=0)
    lower_hours: float = Field(ge=0)
    upper_hours: float = Field(ge=0)
    features: dict[str, object]
    data_version: str

class DemoEvent(Contract):
    name: str
    at: AwareDatetime
    detail: str

class DemoCheckpoint(Contract):
    name: str
    latitude: float
    longitude: float
    passage_at: AwareDatetime
    wind_speed_ms: float | None
    wave_height_m: float | None

class DemoTimelinePoint(Contract):
    name: str
    at: AwareDatetime

class DemoSegment(Contract):
    source: str
    target: str
    edge_id: str
    transport_mode: Literal['ship','rail','road']
    base_time_hours: float = Field(ge=0)
    delay_hours: float = Field(ge=0)
    expected_time_hours: float = Field(ge=0)
    border_wait_hours: float = Field(default=0, ge=0)
    cost_usd: float = Field(ge=0)
    co2_emissions_kg: float = Field(ge=0)

class StrategyResult(Contract):
    id: Literal['baseline','jit','alternative']
    label: str
    status: Literal['ok','blocked','not_applicable','insufficient_data']
    reason: str
    nodes: list[str]
    segments: list[DemoSegment] = Field(default_factory=list)
    speed_knots: float | None = None
    sea_arrival_at: AwareDatetime | None = None
    berth_ready_at: AwareDatetime | None = None
    handling_complete_at: AwareDatetime | None = None
    connection_at: AwareDatetime | None = None
    eta: AwareDatetime | None = None
    total_time_hours: float | None = None
    berth_wait_hours: float = Field(default=0, ge=0)
    connection_wait_hours: float = Field(default=0, ge=0)
    fuel_tonnes: float | None = None
    co2_tonnes: float | None = None
    cargo_co2e_kg: float | None = None
    cost_usd: float = Field(default=0, ge=0)
    remaining_wait_hours: float = Field(default=0, ge=0)
    checkpoints: list[DemoCheckpoint] = Field(default_factory=list)
    timeline: list[DemoTimelinePoint] = Field(default_factory=list)
    fuel_saved_tonnes: float | None = None
    co2_saved_tonnes: float | None = None

class DemoResult(Contract):
    id: str
    scenario_id: str
    title: str
    description: str
    data_source: Literal['synthetic', 'mixed'] = 'synthetic'
    weather_snapshot: dict[str, object] | None = None
    seed: int
    baseline: StrategyResult | None = None
    strategies: list[StrategyResult]
    predictions: list[PredictionTrace]
    events: list[DemoEvent]
    warnings: list[str]
    model_report: dict[str, object]
    created_at: AwareDatetime
    parent_voyage_id: str | None = None
    inputs: DemoRunRequest = Field(default_factory=DemoRunRequest)

class DemoCatalog(Contract):
    scenarios: list[DemoScenario]
    model_report: dict[str, object]
