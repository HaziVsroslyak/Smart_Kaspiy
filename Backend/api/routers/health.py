"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import Request
from fastapi import APIRouter
from api.schemas import HealthResponse


router = APIRouter()


@router.get("/api/v1/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    ready = getattr(request.app.state, "resources", None) is not None
    service = getattr(request.app.state, "weather", None)
    return HealthResponse(
        status="ready" if ready else "not_ready", routing_ready=ready,
        caspian_model_ready=ready, weather_configured=bool(service and service.configured),
    )
