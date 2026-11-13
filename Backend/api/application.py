"""Application factory and lifecycle; domain services remain framework-independent."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from api.config import Settings
from api.resources import build_resources
from api.routers import customs, demo, health, jit, predictions, routing, voyages, weather
from voyage_store import VoyageStore
from weather_service import OpenWeatherService
from auth.service import AuthService
from auth.middleware import SecurityMiddleware
from auth.router import router as auth_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated app without opening SQLite or training models until startup."""
    configuration = settings if settings is not None else Settings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.resources = None
        application.state.weather = None
        application.state.voyages = None
        try:
            application.state.weather = OpenWeatherService(configuration.openweather_api_key)
            application.state.voyages = VoyageStore(configuration.database_path)
            application.state.auth = AuthService(application.state.voyages.database)
            application.state.resources = await run_in_threadpool(build_resources)
            yield
        finally:
            application.state.resources = None
            application.state.weather = None
            application.state.voyages = None
            application.state.auth = None

    application = FastAPI(title='Smart Caspian Transit', version='0.2.0', lifespan=lifespan)
    application.state.settings = configuration
    application.add_middleware(SecurityMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configuration.cors_origins),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    for module in (health, weather, predictions, jit, customs, routing, voyages, demo):
        application.include_router(module.router)
    application.include_router(auth_router)
    return application
