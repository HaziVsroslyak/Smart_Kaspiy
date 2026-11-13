"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Request
from weather_service import WeatherError
from routing_engine import InvalidGraphError, PredictionError, RouteNotFoundError, UnknownNodeError, find_optimal_route
from route_weather import resolve_route_weather
from fastapi import APIRouter
from api.schemas import RouteRequest, RouteDetails, RouteResponse
from api.resources import RoutingResources
import logging


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/route/calculate", response_model=RouteResponse)
def calculate_route(payload: RouteRequest, request: Request) -> RouteResponse:
    resources: RoutingResources | None = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(status_code=503, detail="Routing model is not ready.")
    try:
        impact = resolve_route_weather(payload.weather, payload.current_weather,
                                       getattr(request.app.state, "weather", None))
        network = resources.graph.copy()
        network.remove_edges_from([
            (start, end, key) for start, end, key, data in network.edges(keys=True, data=True)
            if data.get("transport_mode") not in payload.transport_modes
            or (data.get("transport_mode") == "road" and payload.road_conditions.closed)
        ])
        for _, _, data in network.edges(data=True):
            if data.get("transport_mode") == "road":
                data["road_congestion_percent"] = payload.road_conditions.congestion_percent
                data["road_condition_severity"] = payload.road_conditions.condition_severity
                data["border_wait_hours"] = payload.road_conditions.border_wait_hours * data.get("border_crossings", 0)
        if impact.sea_restricted:
            network.remove_edges_from([
                (start, end, key) for start, end, key, data in network.edges(keys=True, data=True)
                if data.get("transport_mode") == "ship"
            ])
        # The engine predicts delays once per edge and adds them to base times.
        routes = find_optimal_route(
            payload.source, payload.target, resources.predictor,
            impact.severity, graph=network, season=payload.season,
        )
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RouteNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PredictionError as exc:
        logger.exception("Route prediction failed")
        raise HTTPException(status_code=503, detail="Delay prediction is unavailable.") from exc
    except InvalidGraphError as exc:
        logger.exception("Invalid routing graph")
        raise HTTPException(status_code=500, detail="Routing network is invalid.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fastest = routes["fastest"]
    return RouteResponse(**fastest, eco=RouteDetails(**routes["eco"]), weather=impact,
                         road_conditions=payload.road_conditions, transport_modes=payload.transport_modes)
