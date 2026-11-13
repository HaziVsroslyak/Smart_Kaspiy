"""Shared synthetic episode source. Rules are demo assumptions, not measured physics."""
from __future__ import annotations
import random
from datetime import datetime, timedelta, timezone
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

DATA_VERSION = 'caspian-episodes-v1'
SEED = 42
SAMPLES = 20_000

class Episode(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    episode_id: str
    shipment_id: str
    scenario_id: str
    decision_at: datetime
    issued_at: datetime
    valid_at: datetime
    departure_port: str
    arrival_port: str
    season: str
    wind_speed_ms: float = Field(ge=0, le=25)
    wave_height_m: float = Field(ge=0.1, le=4.5)
    port_congestion_percent: float = Field(ge=10, le=100)
    road_congestion_percent: float = Field(ge=0, le=100)
    road_condition_severity: float = Field(ge=0, le=10)
    transport_mode: str
    queue_units: float = Field(ge=0)
    service_hours: float = Field(gt=0)
    active_berths: int = Field(ge=1)
    remaining_service_hours: float = Field(ge=0)
    distance_nm: float = Field(gt=0)
    cargo_weight_tons: float = Field(gt=0)
    sea_delay_hours: float = Field(ge=0)
    land_delay_hours: float = Field(ge=0)
    berth_ready_hours: float = Field(ge=0)
    actual_arrival: datetime
    source: str = 'synthetic'
    data_version: str = DATA_VERSION


def generate_training_episodes(samples: int = SAMPLES, seed: int = SEED) -> pd.DataFrame:
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 10:
        raise ValueError('samples must be an integer >= 10')
    rng = random.Random(seed)
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    records: list[dict[str, object]] = []
    wind = 8.0
    for index in range(samples):
        now = start + timedelta(hours=index)
        season = ('Winter', 'Spring', 'Summer', 'Autumn')[(now.month % 12) // 3]
        departure = rng.choice(('Астрахань', 'Махачкала', 'Оля'))
        # Persistent wind and lagged wave response, not independent random columns.
        previous_wind = wind
        wind = max(0.0, min(25.0, 0.75 * wind + 0.25 * rng.uniform(0, 25) + rng.gauss(0, 2)))
        wave = max(0.1, min(4.5, 0.12 * previous_wind + 0.03 * wind + rng.gauss(0, 0.25)))
        congestion = rng.uniform(10, 100)
        road_queue = max(0, min(100, congestion + rng.gauss(0, 20)))
        condition = rng.uniform(0, 10)
        mode = rng.choice(('rail', 'road'))
        service = rng.uniform(1, 4)
        berths = rng.randint(1, 4)
        queue = congestion / 100 * rng.uniform(0, 60)
        remaining = rng.uniform(0, 4)
        sea_delay = max(0, 0.35 * max(0, wind - 5) + 1.5 * max(0, wave - 0.5)
                        + (18 if wave > 2.5 else 0)
                        + (30 if season == 'Winter' and departure != 'Махачкала' else 0)
                        + rng.gauss(0, 0.35))
        land_delay = max(0, 0.15 * wind + (0.08 * road_queue + 0.8 * condition if mode == 'road' else 1)
                         + rng.gauss(0, 0.25))
        ready = max(0, remaining + queue * service / berths + rng.gauss(0, 0.3))
        record = Episode(episode_id=f'train-{seed}-{index:06d}', shipment_id=f'S-{seed}-{index:06d}',
            scenario_id='generated', decision_at=now, issued_at=now - timedelta(hours=1), valid_at=now + timedelta(hours=24),
            departure_port=departure, arrival_port=rng.choice(('Энзели', 'Амирабад')), season=season,
            wind_speed_ms=wind, wave_height_m=wave, port_congestion_percent=congestion,
            road_congestion_percent=road_queue, road_condition_severity=condition, transport_mode=mode,
            queue_units=queue, service_hours=service, active_berths=berths, remaining_service_hours=remaining,
            distance_nm=360, cargo_weight_tons=20, sea_delay_hours=sea_delay, land_delay_hours=land_delay,
            berth_ready_hours=ready, actual_arrival=now + timedelta(hours=max(36 + sea_delay, ready) + 2 + land_delay))
        records.append(record.model_dump())
    return pd.DataFrame.from_records(records)


def sea_projection(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ['departure_port', 'arrival_port', 'wind_speed_ms', 'wave_height_m', 'port_congestion_percent', 'season']
    return frame[columns].assign(delay_hours=frame.sea_delay_hours)


def land_projection(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({'weather_severity': frame.wind_speed_ms / 2.5,
        'port_congestion': frame.port_congestion_percent, 'transport_mode': frame.transport_mode,
        'season': frame.season.str.lower(), 'road_congestion_percent': frame.road_congestion_percent,
        'road_condition_severity': frame.road_condition_severity, 'delay_hours': frame.land_delay_hours})
