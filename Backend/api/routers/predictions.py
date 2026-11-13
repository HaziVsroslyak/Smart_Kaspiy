"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from fastapi import HTTPException, Request
from ml_pipeline import CaspianFeatures
from prediction_service import DelayPrediction, ForecastDelayPrediction, ForecastDelayRequest, predict_from_weather
from weather_service import WeatherError
from fastapi import APIRouter
from api.dependencies import get_weather


router = APIRouter()


@router.post("/api/v1/predictions/delay", response_model=DelayPrediction)
def predict_delay(payload: CaspianFeatures, request: Request) -> DelayPrediction:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Caspian model is not ready.")
    return DelayPrediction(
        delay_hours=resources.caspian_predictor.predict(payload.model_dump()), features_used=payload,
    )


@router.post("/api/v1/predictions/delay-from-weather", response_model=ForecastDelayPrediction)
def predict_weather_delay(payload: ForecastDelayRequest, request: Request) -> ForecastDelayPrediction:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(503, "Caspian model is not ready.")
    try:
        return predict_from_weather(payload, resources.caspian_predictor, get_weather(request))
    except WeatherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except ValueError:
        raise HTTPException(422, "Forecast time or weather features are outside the supported model range.") from None
