"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Request
from weather_service import WeatherError
from routing_engine import PredictionError, RouteNotFoundError
from voyage_models import VoyageRequest, VoyageUpdate, VoyageResponse
from voyage_service import calculate_voyage
from fastapi import APIRouter
from api.dependencies import voyage_failure


router = APIRouter()


@router.get('/api/v1/voyages')
def list_voyages(request: Request) -> list[dict[str,object]]:
    return request.app.state.voyages.list_voyages()


@router.post("/api/v1/voyages", response_model=VoyageResponse, status_code=201)
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


@router.get("/api/v1/voyages/{voyage_id}", response_model=VoyageResponse)
def get_voyage(voyage_id: str, request: Request) -> VoyageResponse:
    try:
        return request.app.state.voyages.get(voyage_id)
    except KeyError as exc:
        raise voyage_failure(exc) from None


@router.post("/api/v1/voyages/{voyage_id}/reforecast", response_model=VoyageResponse)
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
