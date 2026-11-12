"""JIT arrival and illustrative voyage fuel/CO2 estimates for one vessel."""

from __future__ import annotations

import math
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

MIN_SPEED_KNOTS = 6.0
CO2_FACTOR = 3.114  # tonnes CO2 / tonne of heavy fuel oil (task assumption)
# Demo calibration, NOT a measured vessel specification:
# fuel rate [tonnes/hour] = coefficient * speed [knots] ** 3.
DEFAULT_FUEL_COEFFICIENT = 0.0001


class JITInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    distance_nm: float = Field(gt=0)
    current_speed_knots: float = Field(ge=MIN_SPEED_KNOTS)
    port_delay_hours: float = Field(ge=0)


class _ESGInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    distance_nm: float = Field(gt=0)
    old_speed: float = Field(ge=MIN_SPEED_KNOTS)
    new_speed: float = Field(ge=MIN_SPEED_KNOTS)
    fuel_coefficient: float = Field(gt=0)


class ESGResult(TypedDict):
    baseline_fuel_tonnes: float
    optimized_fuel_tonnes: float
    fuel_saved_tonnes: float
    co2_saved_tonnes: float
    fuel_coefficient: float


def optimize_speed(
    distance_nm: float,
    current_speed_knots: float,
    port_delay_hours: float,
) -> float:
    """Delay arrival by slowing down, bounded below by 6 knots.

    port_delay_hours is EXTRA waiting after the original ETA, not time from now
    until berth release. If 6 knots is still too fast, waiting remains unavoidable.
    Invalid inputs or unrepresentable arithmetic raise ValueError.
    """
    data = JITInput(
        distance_nm=distance_nm, current_speed_knots=current_speed_knots,
        port_delay_hours=port_delay_hours,
    )
    original_eta = data.distance_nm / data.current_speed_knots
    target_eta = original_eta + data.port_delay_hours
    if not math.isfinite(target_eta) or original_eta <= 0:
        raise ValueError("Arrival time is outside the supported numeric range.")
    if data.port_delay_hours == 0:
        return data.current_speed_knots
    return max(MIN_SPEED_KNOTS, min(data.current_speed_knots, data.distance_nm / target_eta))


def calculate_esg(
    distance_nm: float,
    old_speed: float,
    new_speed: float,
    *,
    fuel_coefficient: float = DEFAULT_FUEL_COEFFICIENT,
) -> ESGResult:
    """Estimate voyage fuel savings and CO2, excluding fuel burned at anchor.

    Rate = k*v**3; duration = distance/v; voyage fuel = k*distance*v**2.
    Absolute tonnes require vessel calibration; the default k is illustrative.
    """
    data = _ESGInput(
        distance_nm=distance_nm, old_speed=old_speed,
        new_speed=new_speed, fuel_coefficient=fuel_coefficient,
    )
    if data.new_speed > data.old_speed:
        raise ValueError("new_speed must not exceed old_speed for JIT savings.")
    try:
        baseline = data.fuel_coefficient * data.distance_nm * data.old_speed ** 2
        optimized = data.fuel_coefficient * data.distance_nm * data.new_speed ** 2
        saved = max(0.0, baseline - optimized)
        co2_saved = saved * CO2_FACTOR
    except OverflowError as exc:
        raise ValueError("Fuel calculation is outside the supported numeric range.") from exc
    if not all(math.isfinite(value) for value in (baseline, optimized, saved, co2_saved)):
        raise ValueError("Fuel calculation is outside the supported numeric range.")
    return {
        "baseline_fuel_tonnes": baseline,
        "optimized_fuel_tonnes": optimized,
        "fuel_saved_tonnes": saved,
        "co2_saved_tonnes": co2_saved,
        "fuel_coefficient": data.fuel_coefficient,
    }
