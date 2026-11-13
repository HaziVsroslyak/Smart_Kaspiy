"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from smart_customs_and_jit import verify_customs_hash
from fastapi import APIRouter
from api.schemas import CustomsRequest, LegacyCustomsRequest, CustomsResponse


router = APIRouter()


@router.post("/api/v1/customs/clear", response_model=CustomsResponse)
def clear_customs(payload: CustomsRequest | LegacyCustomsRequest) -> CustomsResponse:
    cargo = payload.cargo_payload if isinstance(payload, CustomsRequest) else payload.cargo_data
    verified = verify_customs_hash(cargo.model_dump(), payload.provided_hash)
    return CustomsResponse(
        status="Pre-cleared" if verified else "Requires inspection",
        green_corridor=verified,
    )
