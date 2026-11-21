"""Fábrica da aplicação FastAPI. Arranque: uvicorn backend.app.main:app --reload"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.errors import install_error_handlers
from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_query import router as query_router
from backend.app.api.routes_schema import router as schema_router
from backend.app.config import Settings
from backend.app.semantic.loader import load_semantic_model
from backend.app.validation.registry import ValidatedRegistry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env(os.environ)
    if settings.demo_auth and not settings.jwt_secret:
        raise RuntimeError("QS_DEMO_AUTH=true exige QS_JWT_SECRET definido.")
    app = FastAPI(title="QueryShield", version="0.1.0")
    app.state.settings = settings
    app.state.semantic = load_semantic_model(settings.semantic_dir)
    app.state.validated = ValidatedRegistry()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(schema_router)
    app.include_router(query_router)
    return app


app = create_app()
