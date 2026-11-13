"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Request
from weather_service import OpenWeatherService, WeatherError
from routing_engine import PredictionError, RouteNotFoundError


def get_weather(request: Request) -> OpenWeatherService:
    service = getattr(request.app.state, "weather", None)
    if service is None:
        raise HTTPException(503, "Weather service is not initialized.")
    return service


def voyage_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "Voyage not found.")
    if isinstance(exc, WeatherError):
        return HTTPException(exc.status_code, str(exc))
    if isinstance(exc, RouteNotFoundError):
        return HTTPException(409, str(exc))
    if isinstance(exc, PredictionError):
        return HTTPException(503, "Delay prediction is unavailable.")
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(409, str(exc))
