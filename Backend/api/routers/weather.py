"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Query, Request
from weather_service import Coordinates, WeatherError, WeatherForecast
from fastapi import APIRouter
from api.dependencies import get_weather


router = APIRouter()


@router.get("/api/v1/weather/forecast", response_model=WeatherForecast)
def weather_forecast(
    request: Request,
    latitude: float = Query(ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(ge=-180, le=180, allow_inf_nan=False),
) -> WeatherForecast:
    try:
        return get_weather(request).forecast(Coordinates(latitude=latitude, longitude=longitude))
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None

# Imported datasets remain separate from the existing OpenWeather forecast contract.
from weather_data.contracts import ImportRequest, FetchRequest, ResolveRequest, Dataset, Resolution
from weather_data.service import import_dataset, fetch_dataset, resolve
from weather_data.repository import WeatherRepository
from urllib.error import URLError

def repository(request: Request) -> WeatherRepository:
    return WeatherRepository(request.app.state.voyages.database)

@router.post('/api/v1/weather/datasets/import',response_model=Dataset,status_code=201)
def import_weather(payload:ImportRequest,request:Request)->Dataset:
    try:return repository(request).save(import_dataset(payload))
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@router.post('/api/v1/weather/datasets/fetch',response_model=Dataset,status_code=201)
def fetch_weather(payload:FetchRequest,request:Request)->Dataset:
    if not 0<=(payload.end_date-payload.start_date).days<=30:raise HTTPException(422,'Date interval must be 1–31 days.')
    try:return repository(request).save(fetch_dataset(payload))
    except ValueError:raise HTTPException(502,'Weather provider returned invalid data.') from None
    except (URLError,TimeoutError,KeyError,IndexError,TypeError):raise HTTPException(502,'Weather provider unavailable or returned malformed data.') from None

@router.get('/api/v1/weather/datasets',response_model=list[Dataset])
def list_weather(request:Request)->list[Dataset]:return repository(request).list()

@router.get('/api/v1/weather/datasets/{identity}',response_model=Dataset)
def get_weather_dataset(identity:str,request:Request)->Dataset:return repository(request).get(identity)

@router.post('/api/v1/weather/datasets/{identity}/resolve',response_model=Resolution)
def resolve_weather(identity:str,payload:ResolveRequest,request:Request)->Resolution:
    return resolve(repository(request).get(identity),payload)
