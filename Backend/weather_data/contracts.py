"""Immutable weather records and their source attribution."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class WeatherRecord(Contract):
    timestamp: AwareDatetime
    latitude: float=Field(ge=-90,le=90)
    longitude: float=Field(ge=-180,le=180)
    wind_speed_ms: float|None=Field(default=None,ge=0,le=150)
    wind_gust_ms: float|None=Field(default=None,ge=0,le=200)
    wind_direction_deg: float|None=Field(default=None,ge=0,le=360)
    wave_height_m: float|None=Field(default=None,ge=0,le=40)
    wave_period_s: float|None=Field(default=None,ge=0,le=60)
    wave_direction_deg: float|None=Field(default=None,ge=0,le=360)
    temperature_c: float|None=Field(default=None,ge=-100,le=70)
    precipitation_mm: float|None=Field(default=None,ge=0,le=2000)
    surface_pressure_hpa: float|None=Field(default=None,ge=500,le=1200)
    issued_at: AwareDatetime|None=None

class Dataset(Contract):
    id: str
    source_name: str
    source_url: str|None=None
    provenance: Literal['uploaded_unverified','provider']
    kind: Literal['upload','archive','forecast']
    retrieved_at: AwareDatetime
    content_hash: str
    requested_latitude: float|None=None
    requested_longitude: float|None=None
    precipitation_interval_hours: float|None=None
    wave_source_url: str|None=None
    wave_fetch_status: Literal['complete','partial','unavailable','not_requested','not_applicable']='not_requested'
    wave_fetch_detail: str|None=None
    wave_grid_latitude: float|None=Field(default=None,ge=-90,le=90)
    wave_grid_longitude: float|None=Field(default=None,ge=-180,le=180)
    records: list[WeatherRecord]

class ImportRequest(Contract):
    format: Literal['csv','json']
    content: str=Field(max_length=5*1024*1024)
    source_name: str=Field(min_length=1,max_length=200)
    source_url: str|None=Field(default=None,max_length=2000)

class FetchRequest(Contract):
    latitude: float=Field(ge=-90,le=90)
    longitude: float=Field(ge=-180,le=180)
    start_date: date
    end_date: date
    kind: Literal['archive','forecast']='archive'
    include_waves: bool=True

class ResolveRequest(Contract):
    latitude: float=Field(ge=-90,le=90)
    longitude: float=Field(ge=-180,le=180)
    timestamp: AwareDatetime

class Resolution(Contract):
    status: Literal['complete','missing']
    record: WeatherRecord|None=None
    gaps: list[str]
