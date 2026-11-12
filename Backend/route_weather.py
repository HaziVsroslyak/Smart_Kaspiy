"""Weather provenance and explicit demonstration rules for route planning."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from weather_service import Coordinates, OpenWeatherService, WeatherError


class ScenarioWeather(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    source: Literal["scenario"]
    wind_speed_ms: float = Field(ge=0, le=100)
    wind_gust_ms: float | None = Field(default=None, ge=0, le=150)
    wave_height_m: float | None = Field(default=None, ge=0, le=30)


class ForecastRouteWeather(Coordinates):
    source: Literal["openweather"]
    forecast_at: AwareDatetime = Field(strict=False)


RouteWeather = Annotated[ScenarioWeather | ForecastRouteWeather, Field(discriminator="source")]


class WeatherImpact(BaseModel):
    source: Literal["scenario", "openweather", "manual"]
    severity: float = Field(ge=0, le=10)
    wind_speed_ms: float | None = None
    wind_gust_ms: float | None = None
    wave_height_m: float | None = None
    forecast_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime | None = None
    location: Coordinates | None = None
    sea_restricted: bool = False
    reasons: list[str] = Field(default_factory=list)
    scope: Literal["representative_point_all_sea_legs"] = "representative_point_all_sea_legs"
    policy: str = "demo-v1: wind/gust >= 20 m/s or waves > 2.5 m; not an official port closure"


def resolve_route_weather(
    weather: ScenarioWeather | ForecastRouteWeather | None,
    manual_severity: float,
    service: OpenWeatherService | None,
) -> WeatherImpact:
    """Fetch provider values server-side; clients cannot label invented wind as live."""
    if weather is None:
        return WeatherImpact(source="manual", severity=manual_severity)
    impact = WeatherImpact(source=weather.source, severity=0)
    if isinstance(weather, ForecastRouteWeather):
        if service is None:
            raise WeatherError("Weather service is not initialized.", 503)
        forecast = service.forecast(Coordinates(latitude=weather.latitude, longitude=weather.longitude))
        # Require the exact slot selected in Weather, rather than silently changing time.
        slot = next((item for item in forecast.forecasts if item.valid_at == weather.forecast_at), None)
        if slot is None:
            raise ValueError("Forecast slot is no longer available. Select a new time in Weather.")
        impact.wind_speed_ms = slot.wind_speed_ms
        impact.wind_gust_ms = slot.wind_gust_ms
        impact.forecast_at = slot.valid_at
        impact.retrieved_at = forecast.retrieved_at
        impact.location = forecast.location
    else:
        impact.wind_speed_ms = weather.wind_speed_ms
        impact.wind_gust_ms = weather.wind_gust_ms
        impact.wave_height_m = weather.wave_height_m
    peak_wind = max(impact.wind_speed_ms or 0, impact.wind_gust_ms or 0)
    # Adapter into TransitPredictor's 0..10 feature, not a calibrated storm forecast.
    impact.severity = min(10.0, max(peak_wind / 25 * 10, (impact.wave_height_m or 0) / 4.5 * 10))
    if peak_wind >= 20:
        impact.reasons.append("Ветер или порывы ≥ 20 м/с")
    if impact.wave_height_m is not None and impact.wave_height_m > 2.5:
        impact.reasons.append("Высота волн > 2,5 м")
    impact.sea_restricted = bool(impact.reasons)
    return impact
