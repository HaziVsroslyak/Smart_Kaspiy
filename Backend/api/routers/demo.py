"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Request
from demo_contracts import DemoCatalog, DemoResult, DemoRunRequest
from jit_service import catalog as demo_catalog, run_scenario, simulate_saved_voyage
from weather_data.repository import WeatherRepository
from fastapi import APIRouter


router = APIRouter()


@router.get('/api/v1/demo/scenarios', response_model=DemoCatalog)
def list_demo_scenarios(request: Request) -> DemoCatalog:
    resources = getattr(request.app.state, 'resources', None)
    if resources is None:
        raise HTTPException(503, 'Demo models are not ready.')
    return demo_catalog(resources.demo)


@router.post('/api/v1/demo/scenarios/{scenario_id}/run', response_model=DemoResult)
def run_demo_scenario(scenario_id: str, payload: DemoRunRequest, request: Request) -> DemoResult:
    resources = getattr(request.app.state, 'resources', None)
    if resources is None:
        raise HTTPException(503, 'Demo models are not ready.')
    try:
        dataset = WeatherRepository(request.app.state.voyages.database).get(payload.dataset_id) if payload.dataset_id else None
        result = run_scenario(scenario_id, payload, resources.demo, weather_dataset=dataset)
        request.app.state.voyages.save_demo(result)
        return result
    except KeyError:
        raise HTTPException(404, 'Demo scenario not found.') from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('/api/v1/demo/runs/{run_id}', response_model=DemoResult)
def get_demo_run(run_id: str, request: Request) -> DemoResult:
    try:
        return request.app.state.voyages.get_demo(run_id)
    except KeyError:
        raise HTTPException(404, 'Demo run not found.') from None


@router.post('/api/v1/voyages/{voyage_id}/jit/simulate', response_model=DemoResult)
def simulate_voyage_jit(voyage_id: str, payload: DemoRunRequest, request: Request) -> DemoResult:
    resources = getattr(request.app.state, 'resources', None)
    if resources is None:
        raise HTTPException(503, 'Demo models are not ready.')
    try:
        saved = request.app.state.voyages.get(voyage_id)
        dataset = WeatherRepository(request.app.state.voyages.database).get(payload.dataset_id) if payload.dataset_id else None
        result = simulate_saved_voyage(saved, payload, resources.demo, weather_dataset=dataset)
        request.app.state.voyages.save_demo(result)
        return result
    except KeyError:
        raise HTTPException(404, 'Voyage not found.') from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
