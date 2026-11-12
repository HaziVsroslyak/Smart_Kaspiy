"""Synthetic transit data and a local delay predictor for the hackathon MVP.

Run ``python ml_predictor.py`` to train and print an example prediction.
Training is explicit and never runs on import or during prediction.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

FEATURE_COLUMNS: tuple[str, ...] = (
    "weather_severity", "port_congestion", "transport_mode", "season", "road_congestion_percent", "road_condition_severity",
)
SEASONS: tuple[str, ...] = ("winter", "spring", "summer", "autumn")
CITIES: tuple[str, ...] = ("Астрахань", "Махачкала", "Энзели")


class TransitFeatures(BaseModel):
    """Prediction inputs: congestion is a percentage, not a fraction."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    weather_severity: float = Field(ge=0, le=10)
    port_congestion: float = Field(ge=0, le=100)
    transport_mode: Literal["ship", "rail", "road"]
    road_congestion_percent: float = Field(default=0, ge=0, le=100)
    road_condition_severity: float = Field(default=0, ge=0, le=10)
    season: Literal["winter", "spring", "summer", "autumn"]


class _TrainingRecord(TransitFeatures):
    delay_hours: float = Field(ge=0)


class ModelNotTrainedError(RuntimeError):
    """Raised when inference is requested before a successful training run."""


def generate_mock_data(random_state: int = 42) -> pd.DataFrame:
    """Return exactly 1,000 reproducible synthetic trips with nonnegative delays.

    Origin/destination are descriptive metadata, not model inputs. Rail trips
    involving Enzeli represent a simplified land itinerary, not a direct rail
    connection. The delay formula is a demo assumption, not measured evidence.
    """
    rng = random.Random(random_state)
    seasonal_delay = {"winter": 5.0, "spring": 2.0, "summer": 0.0, "autumn": 3.0}
    records: list[dict[str, str | float]] = []
    for _ in range(1000):
        origin, destination = rng.sample(CITIES, 2)
        weather = rng.uniform(0, 10)
        congestion = rng.uniform(0, 100)
        mode = rng.choice(("ship", "rail", "road"))
        season = rng.choice(SEASONS)
        road_queue = rng.uniform(0, 100) if mode == "road" else 0.0
        road_condition = rng.uniform(0, 10) if mode == "road" else 0.0
        # Ships are more weather-sensitive; high congestion has nonlinear cost.
        delay = (
            1.0
            + weather * (1.8 if mode == "ship" else 0.9 if mode == "road" else 0.65)
            + 0.09 * congestion
            + 0.012 * max(0.0, congestion - 65.0) ** 2
            + 0.12 * road_queue + 1.5 * road_condition
            + seasonal_delay[season]
            + (3.0 if mode == "ship" else 0.0)
            + rng.gauss(0.0, 1.5)
        )
        records.append({
            "origin": origin,
            "destination": destination,
            "weather_severity": weather,
            "port_congestion": congestion,
            "transport_mode": mode,
            "season": season,
            "road_congestion_percent": road_queue,
            "road_condition_severity": road_condition,
            "delay_hours": max(0.0, delay),
        })
    return pd.DataFrame.from_records(records)


class TransitPredictor:
    """Random Forest with shared categorical preprocessing for train/inference.

    Call ``train()`` once at startup, then reuse the instance for predictions.
    Invalid inputs raise ValueError (including Pydantic ValidationError).
    """

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self._pipeline: Pipeline | None = None

    def train(self, data: pd.DataFrame | None = None) -> TransitPredictor:
        """Fit on supplied trips, or generate the default synthetic dataset.

        Only the declared features are used; metadata is excluded.
        A failed retraining attempt leaves the previous model intact.
        """
        if data is None:
            data = generate_mock_data(self.random_state)
        if not isinstance(data, pd.DataFrame):
            raise TypeError("Training data must be a pandas DataFrame.")
        data = data.copy()
        for optional in ("road_congestion_percent", "road_condition_severity"):
            if optional not in data.columns:
                data[optional] = 0.0
        required = [*FEATURE_COLUMNS, "delay_hours"]
        if not data.columns.is_unique:
            raise ValueError("Training data contains duplicate columns.")
        missing = sorted(set(required) - set(data.columns))
        if missing:
            raise ValueError(f"Missing training columns: {', '.join(missing)}")
        if len(data) < 2:
            raise ValueError("Training requires at least two records.")
        validated: list[dict[str, object]] = []
        for row_number, record in enumerate(data[required].to_dict(orient="records")):
            try:
                validated.append(_TrainingRecord.model_validate(record).model_dump())
            except ValueError as exc:
                raise ValueError(f"Invalid training record at position {row_number}: {exc}") from exc
        frame = pd.DataFrame.from_records(validated)
        preprocessing = ColumnTransformer([
            ("numeric", "passthrough", ["weather_severity", "port_congestion", "road_congestion_percent", "road_condition_severity"]),
            ("categorical", OneHotEncoder(
                categories=[["ship", "rail", "road"], list(SEASONS)],
                handle_unknown="error",
            ), ["transport_mode", "season"]),
        ])
        pipeline = Pipeline([
            ("preprocessing", preprocessing),
            ("regressor", RandomForestRegressor(
                n_estimators=200,
                min_samples_leaf=2,
                random_state=self.random_state,
                n_jobs=1,
            )),
        ])
        pipeline.fit(frame[list(FEATURE_COLUMNS)], frame["delay_hours"])
        self._pipeline = pipeline
        return self

    def predict_delay(self, features: Mapping[str, object] | TransitFeatures) -> float:
        """Return a finite, nonnegative expected delay in hours for one trip."""
        if self._pipeline is None:
            raise ModelNotTrainedError("Call train() before predict_delay().")
        # Revalidate even model instances, which callers could have mutated.
        raw = features.model_dump() if isinstance(features, TransitFeatures) else dict(features)
        validated = TransitFeatures.model_validate(raw)
        frame = pd.DataFrame([validated.model_dump()], columns=list(FEATURE_COLUMNS))
        prediction = float(self._pipeline.predict(frame)[0])
        if not math.isfinite(prediction):
            raise RuntimeError("The model returned a non-finite delay.")
        return max(0.0, prediction)


if __name__ == "__main__":
    predictor = TransitPredictor().train()
    hours = predictor.predict_delay({
        "weather_severity": 7.0,
        "port_congestion": 80.0,
        "transport_mode": "ship",
        "season": "winter",
    })
    print(f"Expected delay: {hours:.2f} hours (synthetic demo model)")
