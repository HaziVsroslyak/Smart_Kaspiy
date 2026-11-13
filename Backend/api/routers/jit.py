"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException
from jit_optimizer import JITInput
from smart_customs_and_jit import optimize_vessel_speed
from fastapi import APIRouter
from api.schemas import JITResponse


router = APIRouter()


@router.post("/api/v1/optimize/jit", response_model=JITResponse)
def optimize_jit(payload: JITInput) -> JITResponse:
    try:
        result = optimize_vessel_speed(
            payload.distance_nm, payload.current_speed_knots, payload.port_delay_hours,
        )
        return JITResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
