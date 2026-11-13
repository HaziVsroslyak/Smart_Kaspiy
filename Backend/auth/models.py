"""Public identity contracts; secrets are never included in user responses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal['logistician', 'admin', 'root']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class User(Contract):
    id: str
    login: str
    email: str
    role: Role
    status: Literal['active', 'frozen']
    must_change_password: bool


@dataclass(frozen=True)
class Actor:
    user: User
    session_digest: str


class LoginRequest(Contract):
    identity: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class PasswordChange(Contract):
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=12, max_length=128, repr=False)


class CreateUser(Contract):
    login: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128, repr=False)


class RoleChange(Contract):
    role: Role


class TransferRequest(Contract):
    destination_user_id: str
    expected_ownership_revision: int = Field(ge=0)
