"""Customs pre-clearance simulation and JIT arrival business operations."""

from __future__ import annotations

import hashlib
import hmac
import json
import re

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from jit_optimizer import ESGResult, JITInput, calculate_esg, optimize_speed
from smart_customs import CargoData


class CargoPayload(BaseModel):
    """Cargo ID and description; weight is in kilograms."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    weight: float = Field(gt=0, description="Weight in kilograms")
    type: str = Field(min_length=1, max_length=200, pattern=r"\S")
    id: str = Field(min_length=1, max_length=200, pattern=r"\S")


_cargo_adapter = TypeAdapter(CargoPayload | CargoData)


def calculate_customs_hash(cargo_payload: dict[str, object]) -> str:
    """Validate cargo and hash canonical JSON using SHA-256.

    Accepts weight/type/id or the legacy weight/type/sender/recipient shape.
    Weight is normalized to float. Keys are sorted, separators have no spaces,
    text is preserved exactly, and JSON is encoded as UTF-8 without ASCII escapes.
    """
    cargo = _cargo_adapter.validate_python(cargo_payload)
    canonical = json.dumps(
        cargo.model_dump(), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_customs_hash(cargo_payload: dict[str, object], provided_hash: str) -> bool:
    """Return hash agreement; this simulation does not authenticate the sender."""
    expected_hash = calculate_customs_hash(cargo_payload)
    if not isinstance(provided_hash, str) or re.fullmatch(r"[0-9a-fA-F]{64}", provided_hash) is None:
        return False
    return hmac.compare_digest(expected_hash, provided_hash.lower())


class VesselOptimization(ESGResult):
    new_speed_knots: float
    arrival_in_hours: float
    berth_available_in_hours: float
    remaining_wait_hours: float


def optimize_vessel_speed(
    distance_nm: float,
    current_speed_knots: float,
    port_delay_hours: float,
) -> VesselOptimization:
    """Reduce speed to absorb EXTRA waiting after the original ETA.

    Uses the existing 6-knot lower bound and returns any unavoidable waiting.
    Hourly fuel rate is proportional to speed cubed; voyage fuel integrates that
    rate over distance/speed hours. The default vessel coefficient is a demo
    assumption. Fuel at anchor and train/truck timetable forecasts are excluded.
    """
    data = JITInput(
        distance_nm=distance_nm, current_speed_knots=current_speed_knots,
        port_delay_hours=port_delay_hours,
    )
    speed = optimize_speed(data.distance_nm, data.current_speed_knots, data.port_delay_hours)
    esg = calculate_esg(data.distance_nm, data.current_speed_knots, speed)
    berth_time = data.distance_nm / data.current_speed_knots + data.port_delay_hours
    arrival_time = data.distance_nm / speed
    return {
        **esg,
        "new_speed_knots": speed,
        "arrival_in_hours": arrival_time,
        "berth_available_in_hours": berth_time,
        "remaining_wait_hours": max(0.0, berth_time - arrival_time),
    }
