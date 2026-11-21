"""Fixtures comuns aos testes unitários da API (sem PostgreSQL)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

TEST_JWT_SECRET = "unit-test-secret-with-at-least-32-characters"
SEMANTIC_DIR = Path(__file__).resolve().parents[2] / "semantic"


@pytest.fixture()
def settings() -> Settings:
    return Settings(jwt_secret=TEST_JWT_SECRET, demo_auth=True, semantic_dir=SEMANTIC_DIR)


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
