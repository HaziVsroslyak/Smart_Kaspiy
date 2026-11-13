"""HTTP application module for Smart Caspian Transit."""
from __future__ import annotations

from smart_customs_and_jit import verify_customs_hash, calculate_customs_hash, CargoPayload
from secrets import choice, randbelow, token_hex
from typing import Literal
from api.schemas import ApiModel
from fastapi import APIRouter
from api.schemas import CustomsRequest, LegacyCustomsRequest, CustomsResponse


router = APIRouter()


class CustomsDemo(ApiModel):
    cargo_payload: CargoPayload
    provided_hash: str
    data_source: Literal['synthetic'] = 'synthetic'
    expected_status: Literal['Pre-cleared', 'Requires inspection']


@router.get('/api/v1/customs/demo', response_model=CustomsDemo)
def generate_customs_demo(tampered: bool = False) -> CustomsDemo:
    """Produce a synthetic manifest; tampering changes weight after hashing."""
    cargo = CargoPayload(id=f'DEMO-{token_hex(4).upper()}',
                         type=choice(('Зерно', 'Металлопрокат', 'Текстиль', 'Оборудование', 'Фрукты')),
                         weight=float(1000 + randbelow(24001)))
    provided_hash = calculate_customs_hash(cargo.model_dump())
    if tampered:
        cargo = cargo.model_copy(update={'weight': cargo.weight + 100.0})
    return CustomsDemo(cargo_payload=cargo, provided_hash=provided_hash,
                       expected_status='Requires inspection' if tampered else 'Pre-cleared')


@router.post("/api/v1/customs/clear", response_model=CustomsResponse)
def clear_customs(payload: CustomsRequest | LegacyCustomsRequest) -> CustomsResponse:
    cargo = payload.cargo_payload if isinstance(payload, CustomsRequest) else payload.cargo_data
    verified = verify_customs_hash(cargo.model_dump(), payload.provided_hash)
    return CustomsResponse(
        status="Pre-cleared" if verified else "Requires inspection",
        green_corridor=verified,
    )
