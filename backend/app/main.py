"""Fábrica da aplicação FastAPI. Arranque: uvicorn backend.app.main:app --reload"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.errors import install_error_handlers
from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_query import router as query_router
from backend.app.api.routes_schema import router as schema_router
from backend.app.config import ConfigError, Settings
from backend.app.execution.executor import SellerExecutors
from backend.app.generation.mock import MockGenerator
from backend.app.generation.openai_provider import OpenAICompatibleGenerator
from backend.app.history.store import HistoryStore
from backend.app.semantic.loader import load_semantic_model
from backend.app.validation.registry import ValidatedRegistry


def _build_generator(settings: Settings) -> Any:
    if settings.llm_provider == "mock":
        return MockGenerator()
    if not settings.llm_api_key or not settings.llm_model:
        raise ConfigError("QS_LLM_PROVIDER=openai exige QS_LLM_API_KEY e QS_LLM_MODEL")
    return OpenAICompatibleGenerator(
        settings.llm_base_url, settings.llm_api_key, settings.llm_model
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    executor = app.state.executor
    if executor is not None:
        executor.open()
    try:
        yield
    finally:
        if executor is not None:
            executor.close()
        close = getattr(app.state.generator, "close", None)
        if callable(close):
            close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env(os.environ)
    if settings.demo_auth and not settings.jwt_secret:
        raise RuntimeError("QS_DEMO_AUTH=true exige QS_JWT_SECRET definido.")
    app = FastAPI(title="QueryShield", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.semantic = load_semantic_model(settings.semantic_dir)
    app.state.validated = ValidatedRegistry()
    app.state.history = HistoryStore()
    app.state.generator = _build_generator(settings)
    app.state.executor = (
        SellerExecutors(
            settings.reader_dsn_template,
            settings.seller_ids,
            statement_timeout_ms=settings.statement_timeout_ms,
            max_rows=settings.max_rows,
            max_result_bytes=settings.max_result_bytes,
            deadline_margin_ms=settings.deadline_margin_ms,
            seller_passwords=settings.seller_passwords,
        )
        if settings.reader_dsn_template
        else None
    )
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
