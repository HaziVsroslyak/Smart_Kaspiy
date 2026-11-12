"""OpenWeather 5-day / 3-hour forecasts. No fabricated wave-height fallback."""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ForecastSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    valid_at: AwareDatetime
    temperature_c: float
    wind_speed_ms: float = Field(ge=0)
    wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    wind_gust_ms: float | None = Field(default=None, ge=0)
    humidity_percent: float = Field(ge=0, le=100)
    pressure_hpa: float = Field(gt=0)
    precipitation_probability: float = Field(ge=0, le=1)
    rain_3h_mm: float = Field(ge=0)
    snow_3h_mm: float = Field(ge=0)
    description: str
    wave_height_m: None = None


class WeatherForecast(BaseModel):
    provider: Literal["OpenWeather"] = "OpenWeather"
    product: Literal["5-day/3-hour"] = "5-day/3-hour"
    source_url: str = "https://openweathermap.org/api/forecast5"
    location: Coordinates
    retrieved_at: AwareDatetime
    step_hours: Literal[3] = 3
    cached: bool = False
    wave_height_available: Literal[False] = False
    forecasts: list[ForecastSlot] = Field(min_length=1, max_length=40)


class _ProviderModel(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)


class _Main(_ProviderModel):
    temp: float
    humidity: float = Field(ge=0, le=100)
    pressure: float = Field(gt=0)


class _Wind(_ProviderModel):
    speed: float = Field(ge=0)
    deg: float | None = Field(default=None, ge=0, le=360)
    gust: float | None = Field(default=None, ge=0)


class _Condition(_ProviderModel):
    description: str


class _Precipitation(_ProviderModel):
    amount: float = Field(default=0, alias="3h", ge=0)


class _Entry(_ProviderModel):
    dt: int
    main: _Main
    wind: _Wind
    weather: list[_Condition] = Field(min_length=1)
    pop: float = Field(default=0, ge=0, le=1)
    rain: _Precipitation = Field(default_factory=_Precipitation)
    snow: _Precipitation = Field(default_factory=_Precipitation)


class _ProviderResponse(_ProviderModel):
    cod: str | int
    entries: list[_Entry] = Field(alias="list", min_length=1, max_length=40)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpenWeatherService:
    def __init__(
        self, api_key: str | None, *, timeout_seconds: float = 10,
        cache_ttl_seconds: float = 600, now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._timeout = timeout_seconds
        self._ttl = cache_ttl_seconds
        self._now = now
        self._cache: OrderedDict[tuple[float, float], WeatherForecast] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def forecast(self, location: Coordinates) -> WeatherForecast:
        if not self.configured:
            raise WeatherError("Set OPENWEATHER_API_KEY on the backend server.", 503)
        now = self._now()
        cache_key = (location.latitude, location.longitude)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                age = (now - cached.retrieved_at).total_seconds()
                future = [slot for slot in cached.forecasts if slot.valid_at >= now]
                if 0 <= age < self._ttl and future:
                    self._cache.move_to_end(cache_key)
                    result = cached.model_copy(deep=True)
                    result.forecasts = [slot.model_copy(deep=True) for slot in future]
                    result.cached = True
                    return result

        query = urlencode({
            "lat": location.latitude, "lon": location.longitude,
            "appid": self._api_key, "units": "metric", "lang": "ru", "cnt": 40,
        })
        try:
            # urllib does not log URLs (the query contains a private API key).
            with urlopen(f"{FORECAST_URL}?{query}", timeout=self._timeout) as response:
                raw = json.loads(response.read(2_000_000).decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise WeatherError("OpenWeather rejected the server API key or subscription.", 503) from None
            if exc.code == 429:
                raise WeatherError("OpenWeather quota exceeded; retry later.", 503) from None
            raise WeatherError("OpenWeather returned an upstream HTTP error.") from None
        except (URLError, TimeoutError, OSError):
            raise WeatherError("OpenWeather is unavailable or timed out.", 504) from None
        except (ValueError, UnicodeError):
            raise WeatherError("OpenWeather returned invalid JSON.") from None

        retrieved_at = self._now()
        try:
            parsed = _ProviderResponse.model_validate(raw)
            if str(parsed.cod) != "200":
                raise ValueError("Unsuccessful provider response")
            entries = sorted(parsed.entries, key=lambda entry: entry.dt)
            if any(b.dt - a.dt != 10800 for a, b in zip(entries, entries[1:])):
                raise ValueError("Invalid forecast timestamps")
            slots = [ForecastSlot(
                valid_at=datetime.fromtimestamp(entry.dt, tz=timezone.utc),
                temperature_c=entry.main.temp,
                wind_speed_ms=entry.wind.speed,
                wind_direction_deg=entry.wind.deg,
                wind_gust_ms=entry.wind.gust,
                humidity_percent=entry.main.humidity,
                pressure_hpa=entry.main.pressure,
                precipitation_probability=entry.pop,
                rain_3h_mm=entry.rain.amount,
                snow_3h_mm=entry.snow.amount,
                description=entry.weather[0].description,
            ) for entry in entries if entry.dt >= retrieved_at.timestamp()]
            result = WeatherForecast(location=location, retrieved_at=retrieved_at, forecasts=slots)
        except (ValueError, TypeError, OverflowError, OSError):
            raise WeatherError("OpenWeather returned an invalid or expired forecast.") from None
        with self._lock:
            self._cache[cache_key] = result.model_copy(deep=True)
            self._cache.move_to_end(cache_key)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
        return result
