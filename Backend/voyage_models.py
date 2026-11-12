"""Time-aware voyage contracts. All timestamps use timezone-aware RFC3339."""
from __future__ import annotations
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from route_weather import ScenarioWeather

Mode = Literal['ship', 'rail', 'road']

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

class RoadState(Contract):
    congestion_percent: float = Field(default=20, ge=0, le=100)
    condition_severity: float = Field(default=0, ge=0, le=10)
    border_wait_hours: float = Field(default=4, ge=0, le=168)
    closed: bool = False

class VoyageConditions(Contract):
    weather_mode: Literal['openweather', 'scenario'] = 'scenario'
    scenario: ScenarioWeather = Field(default_factory=lambda: ScenarioWeather(source='scenario',wind_speed_ms=4))
    road: RoadState = Field(default_factory=RoadState)
    port_congestion: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_ports(self) -> VoyageConditions:
        for terminal, value in self.port_congestion.items():
            if terminal not in ('Астрахань','Махачкала','Энзели','Решт') or not 0 <= value <= 100:
                raise ValueError('Port congestion requires a known terminal and a percentage 0..100.')
        return self

class ConnectionSchedule(Contract):
    terminal: Literal['Астрахань','Махачкала','Энзели','Решт']
    transport_mode: Mode
    first_departure_at: AwareDatetime = Field(strict=False)
    interval_hours: float = Field(ge=1, le=168)
    handling_hours: float = Field(default=2, ge=0, le=48)

class VoyageRequest(Contract):
    source: Literal['Астрахань','Махачкала','Энзели','Решт']
    target: Literal['Астрахань','Махачкала','Энзели','Решт']
    departure_at: AwareDatetime = Field(strict=False)
    transport_modes: list[Mode] = Field(default_factory=lambda:['ship','rail','road'],min_length=1,max_length=3)
    connections: list[ConnectionSchedule] = Field(default_factory=list,max_length=8)
    conditions: VoyageConditions = Field(default_factory=VoyageConditions)

    @model_validator(mode='after')
    def unique_connections(self) -> VoyageRequest:
        keys=[(item.terminal,item.transport_mode) for item in self.connections]
        if len(set(keys)) != len(keys):
            raise ValueError('Only one periodic schedule per terminal and transport mode is supported.')
        return self

class VoyageUpdate(Contract):
    conditions: VoyageConditions | None = None

class Checkpoint(Contract):
    name: str
    latitude: float
    longitude: float
    passage_at: AwareDatetime
    forecast_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime | None = None
    wind_speed_ms: float | None = None
    wind_gust_ms: float | None = None
    wave_height_m: float | None = None
    severity: float | None = None
    status: Literal['forecast','scenario','outside_horizon']

class DelayReason(Contract):
    code: Literal['weather','port_congestion','missed_connection','connection_wait','border','storm_restriction','forecast_gap']
    message: str
    hours: float = Field(default=0, ge=0)

class TimedLeg(Contract):
    source: str
    target: str
    edge_id: str | int
    transport_mode: Mode
    base_time_hours: float
    delay_hours: float
    expected_time_hours: float
    border_wait_hours: float
    cost_usd: float
    co2_emissions_kg: float
    departure_at: AwareDatetime
    arrival_at: AwareDatetime
    connection_wait_hours: float
    checkpoints: list[Checkpoint]
    features_used: dict[str, float | str]
    reasons: list[DelayReason]
    eta_converged: bool

class TimedRoute(Contract):
    nodes: list[str]
    segments: list[TimedLeg]
    total_base_time_hours: float
    total_delay_hours: float
    total_time_hours: float
    total_cost_usd: float
    total_co2_emissions_kg: float
    departure_at: AwareDatetime
    eta: AwareDatetime
    coverage: Literal['complete','partial']
    reasons: list[DelayReason]

class VoyageSnapshot(Contract):
    calculated_at: AwareDatetime
    fastest: TimedRoute
    eco: TimedRoute
    excluded_reasons: list[DelayReason]
    alternative_reasons: list[DelayReason] = Field(default_factory=list)
    training_data: Literal['synthetic'] = 'synthetic'

class VoyageResponse(Contract):
    id: str
    request: VoyageRequest
    conditions: VoyageConditions
    baseline: VoyageSnapshot
    current: VoyageSnapshot
    eta_change_hours: float
    route_changed: bool
    revision: int
