"""Synthetic Caspian delay data and a validated scikit-learn pipeline.

The generator implements scenario assumptions, not a calibrated physical model.
Weather is supplied as input; the predictor does not forecast weather itself.
"""

from __future__ import annotations

import math
import random
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import NotFittedError
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DEPARTURE_PORTS = ("Астрахань", "Махачкала", "Оля")
ARRIVAL_PORTS = ("Энзели", "Амирабад")
SEASONS = ("Winter", "Spring", "Summer", "Autumn")
CATEGORICAL_FEATURES = ("departure_port", "arrival_port", "season")
NUMERIC_FEATURES = ("wind_speed_ms", "wave_height_m", "port_congestion_percent")
FEATURE_COLUMNS = (
    "departure_port", "arrival_port", "wind_speed_ms", "wave_height_m",
    "port_congestion_percent", "season",
)
TARGET_COLUMN = "delay_hours"


class CaspianFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    departure_port: Literal["Астрахань", "Махачкала", "Оля"]
    arrival_port: Literal["Энзели", "Амирабад"]
    wind_speed_ms: float = Field(ge=0, le=25)
    wave_height_m: float = Field(ge=0.1, le=4.5)
    port_congestion_percent: float = Field(ge=10, le=100)
    season: Literal["Winter", "Spring", "Summer", "Autumn"]


class _TrainingRecord(CaspianFeatures):
    delay_hours: float = Field(ge=0)


def _sample_delay(
    departure_port: str,
    wave_height_m: float,
    port_congestion_percent: float,
    season: str,
    rng: random.Random,
) -> float:
    delay = rng.uniform(0, 4)
    if wave_height_m > 2.5:
        delay += rng.uniform(12, 24)
    if port_congestion_percent > 85:
        delay += rng.uniform(10, 36)
    if season == "Winter" and departure_port in ("Астрахань", "Оля"):
        delay += rng.uniform(24, 48)
    return max(0.0, delay + rng.gauss(0, 0.5))


def generate_mock_data(samples: int = 5000, *, random_state: int = 42) -> pd.DataFrame:
    """Generate reproducible trips with additive storm, queue and ice delays.

    Numeric features are sampled uniformly and independently within the stated
    ranges. Gaussian noise has standard deviation 0.5 hours. Delays are clipped
    at zero. Wind has no separate penalty in the specified scenario rules.
    """
    if isinstance(samples, bool) or not isinstance(samples, int):
        raise TypeError("samples must be an integer.")
    if samples < 1:
        raise ValueError("samples must be positive.")
    rng = random.Random(random_state)
    records: list[dict[str, str | float]] = []
    for _ in range(samples):
        departure = rng.choice(DEPARTURE_PORTS)
        arrival = rng.choice(ARRIVAL_PORTS)
        wind = rng.uniform(0, 25)
        wave = rng.uniform(0.1, 4.5)
        congestion = rng.uniform(10, 100)
        season = rng.choice(SEASONS)
        records.append({
            "departure_port": departure,
            "arrival_port": arrival,
            "wind_speed_ms": wind,
            "wave_height_m": wave,
            "port_congestion_percent": congestion,
            "season": season,
            TARGET_COLUMN: _sample_delay(departure, wave, congestion, season, rng),
        })
    return pd.DataFrame.from_records(records, columns=[*FEATURE_COLUMNS, TARGET_COLUMN])


class CaspianPredictor:
    """Explicit training followed by single-trip predictions in hours."""

    def __init__(self, random_state: int = 42) -> None:
        preprocessor = ColumnTransformer([
            ("categorical", OneHotEncoder(
                categories=[list(DEPARTURE_PORTS), list(ARRIVAL_PORTS), list(SEASONS)],
                handle_unknown="error",
            ), list(CATEGORICAL_FEATURES)),
            ("numeric", StandardScaler(), list(NUMERIC_FEATURES)),
        ])
        self.pipeline: Pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("regressor", RandomForestRegressor(
                n_estimators=100, random_state=random_state, n_jobs=1,
            )),
        ])
        self._is_trained = False

    def train(self, df: pd.DataFrame) -> CaspianPredictor:
        """Fit using only the six declared features; return self for chaining.

        Invalid records raise ValueError. A failed retraining attempt preserves
        the previously fitted model. Preprocessing is fitted only on this df.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame.")
        if not df.columns.is_unique:
            raise ValueError("Training columns must be unique.")
        required = [*FEATURE_COLUMNS, TARGET_COLUMN]
        missing = [column for column in required if column not in df.columns]
        if missing:
            raise ValueError(f"Missing training columns: {', '.join(missing)}")
        if len(df) < 2:
            raise ValueError("Training requires at least two records.")
        validated: list[dict[str, object]] = []
        for position, record in enumerate(df[required].to_dict(orient="records")):
            try:
                validated.append(_TrainingRecord.model_validate(record).model_dump())
            except ValueError as exc:
                raise ValueError(f"Invalid training record at position {position}: {exc}") from exc
        frame = pd.DataFrame.from_records(validated)
        candidate: Pipeline = clone(self.pipeline)
        candidate.fit(frame[list(FEATURE_COLUMNS)], frame[TARGET_COLUMN])
        self.pipeline = candidate
        self._is_trained = True
        return self

    def predict(self, features_dict: dict[str, object]) -> float:
        """Return a finite, nonnegative delay; raise NotFittedError before train()."""
        if not self._is_trained:
            raise NotFittedError("Call train(df) before predict(features_dict).")
        features = CaspianFeatures.model_validate(features_dict)
        frame = pd.DataFrame([features.model_dump()], columns=list(FEATURE_COLUMNS))
        delay = float(self.pipeline.predict(frame)[0])
        if not math.isfinite(delay):
            raise RuntimeError("The model returned a non-finite delay.")
        return max(0.0, delay)


if __name__ == "__main__":
    predictor = CaspianPredictor().train(generate_mock_data())
    delay = predictor.predict({
        "departure_port": "Оля",
        "arrival_port": "Энзели",
        "wind_speed_ms": 18.0,
        "wave_height_m": 3.2,
        "port_congestion_percent": 90.0,
        "season": "Winter",
    })
    print(f"Expected delay: {delay:.2f} hours (synthetic scenario model)")
