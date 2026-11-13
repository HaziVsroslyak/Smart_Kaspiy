"""Local application configuration, resolved independently for each app."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path = field(default_factory=lambda: BACKEND_ROOT / 'artifacts' / 'voyages.sqlite3')
    openweather_api_key: str | None = field(default=None, repr=False)
    cors_origins: tuple[str, ...] = ('https://localhost',)

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv(BACKEND_ROOT / '.env', override=False)
        configured = os.getenv('DATABASE_PATH', '').strip()
        path = Path(configured).expanduser() if configured else BACKEND_ROOT / 'artifacts' / 'voyages.sqlite3'
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        origins=tuple(value.strip().rstrip('/') for value in os.getenv('APP_ORIGINS','https://localhost').split(',') if value.strip())
        if not origins or '*' in origins:
            raise ValueError('APP_ORIGINS must contain explicit trusted origins.')
        return cls(database_path=path, openweather_api_key=os.getenv('OPENWEATHER_API_KEY'),cors_origins=origins)
