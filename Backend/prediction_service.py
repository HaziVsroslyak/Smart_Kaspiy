"""API contracts and an explicit bridge from provider forecasts to delay ML."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from ml_pipeline import CaspianFeatures, CaspianPredictor
from weather_service import Coordinates, OpenWeatherService


class DelayPrediction(BaseModel):
    delay_hours: float = Field(ge=0)
    model: Literal["CaspianPredictor"] = "CaspianPredictor"
    training_data: Literal["synthetic"] = "synthetic"
    features_used: CaspianFeatures


class ForecastDelayRequest(Coordinates):
    departure_port: Literal["Астрахань", "Махачкала", "Оля"]
    arrival_port: Literal["Энзели", "Амирабад"]
    # JSON RFC3339 strings are parsed as aware datetimes despite strict numbers.
    forecast_at: AwareDatetime = Field(strict=False)
    wave_height_m: float = Field(ge=0.1, le=4.5)
    wave_source: str = Field(min_length=1, max_length=200, pattern=r"\S")
    port_congestion_percent: float = Field(ge=10, le=100)


class ForecastDelayPrediction(DelayPrediction):
    weather_provider: Literal["OpenWeather"] = "OpenWeather"
    forecast_valid_at: AwareDatetime
    weather_retrieved_at: AwareDatetime
    location: Coordinates
    wave_source: str


def season_for_month(month: int) -> str:
    return ("Winter", "Spring", "Summer", "Autumn")[(month % 12) // 3]


def predict_from_weather(
    request: ForecastDelayRequest, predictor: CaspianPredictor,
    weather: OpenWeatherService,
) -> ForecastDelayPrediction:
    forecast = weather.forecast(Coordinates(latitude=request.latitude, longitude=request.longitude))
    requested = request.forecast_at
    if not forecast.forecasts[0].valid_at <= requested <= forecast.forecasts[-1].valid_at:
        raise ValueError("forecast_at is outside the available forecast interval.")
    slot = min(forecast.forecasts, key=lambda value: abs((value.valid_at - requested).total_seconds()))
    if abs((slot.valid_at - requested).total_seconds()) > 5400:
        raise ValueError("No forecast slot within 90 minutes of forecast_at.")
    # Never clip out-of-training-range wind or invent a wave height.
    features = CaspianFeatures.model_validate({
        "departure_port": request.departure_port,
        "arrival_port": request.arrival_port,
        "wind_speed_ms": slot.wind_speed_ms,
        "wave_height_m": request.wave_height_m,
        "port_congestion_percent": request.port_congestion_percent,
        "season": season_for_month(slot.valid_at.month),
    })
    return ForecastDelayPrediction(
        delay_hours=predictor.predict(features.model_dump()), features_used=features,
        forecast_valid_at=slot.valid_at, weather_retrieved_at=forecast.retrieved_at,
        location=forecast.location, wave_source=request.wave_source,
    )
