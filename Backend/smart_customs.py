"""Local smart-contract simulation: hash matching, not proof of authenticity."""

from __future__ import annotations

import hashlib
import hmac
import json
import re

from pydantic import BaseModel, ConfigDict, Field


class CargoData(BaseModel):
    """Weight is in kg; text is hashed exactly as supplied, without trimming."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    weight: float = Field(gt=0, description="Weight in kilograms")
    type: str = Field(min_length=1, max_length=200, pattern=r"\S")
    sender: str = Field(min_length=1, max_length=200, pattern=r"\S")
    recipient: str = Field(min_length=1, max_length=200, pattern=r"\S")


class CustomsPreClearance:
    """Stateless verification; each API response carries its own cargo status."""

    @staticmethod
    def calculate_cargo_hash(cargo_data: dict[str, object]) -> str:
        """SHA-256 of normalized JSON encoded as UTF-8.

        Validate four fields, normalize weight to float, sort keys, omit JSON
        whitespace and preserve Unicode. This same contract applies to clients.
        """
        cargo = CargoData.model_validate(cargo_data)
        serialized = json.dumps(
            cargo.model_dump(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def verify_cargo_hash(
        self, cargo_data: dict[str, object], provided_hash: str,
    ) -> bool:
        """Return False for a malformed/mismatching hash; invalid cargo raises ValueError."""
        expected_hash = self.calculate_cargo_hash(cargo_data)
        if not isinstance(provided_hash, str) or re.fullmatch(r"[0-9a-fA-F]{64}", provided_hash) is None:
            return False
        return hmac.compare_digest(expected_hash, provided_hash.lower())
