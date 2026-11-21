"""Semantic layer e autenticação: papéis, PII, joins e erros 401 (tarefas 2.1 e 2.2)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.auth.tokens import (
    AUDIENCE,
    DEMO_PERSONAS,
    ISSUER,
    AuthError,
    issue_token,
    verify_token,
)
from backend.app.config import ConfigError, Settings
from backend.app.main import create_app
from backend.app.semantic.loader import SemanticConfigError, load_semantic_model
from backend.app.semantic.models import Role
from tests.unit.conftest import SEMANTIC_DIR, TEST_JWT_SECRET


def login(client: TestClient, persona: str) -> str:
    response = client.post("/auth/demo-login", json={"persona": persona})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def schema_for(client: TestClient, persona: str) -> dict:
    token = login(client, persona)
    return client.get("/schema/semantic", headers={"Authorization": f"Bearer {token}"}).json()


def _copy_semantic(tmp_path: Path) -> Path:
    shutil.copy(SEMANTIC_DIR / "schema.yaml", tmp_path / "schema.yaml")
    shutil.copy(SEMANTIC_DIR / "metrics.yaml", tmp_path / "metrics.yaml")
    return tmp_path


# --- semantic layer -------------------------------------------------------------------------


def test_semantic_files_load_and_define_the_required_metrics() -> None:
    model = load_semantic_model(SEMANTIC_DIR)
    assert {"receita", "venda", "devolucao", "encomenda_valida", "periodo"} <= set(model.metrics)
    assert "returns" in model.metrics["receita"].requires_tables


def test_analyst_sees_customers_without_email_or_phone(client: TestClient) -> None:
    body = schema_for(client, "analista.ngola")
    customers = next(t for t in body["tables"] if t["name"] == "customers")
    names = {c["name"] for c in customers["columns"]}
    assert "email" not in names and "phone" not in names
    assert "full_name" in names


def test_analyst_does_not_see_finance_tables(client: TestClient) -> None:
    body = schema_for(client, "analista.ngola")
    names = {t["name"] for t in body["tables"]}
    assert "payouts" not in names and "payments" not in names
    assert body["role"] == "seller_analyst"


def test_finance_sees_payouts_and_commission(client: TestClient) -> None:
    body = schema_for(client, "financas.ngola")
    payouts = next(t for t in body["tables"] if t["name"] == "payouts")
    assert "commission_amount" in {c["name"] for c in payouts["columns"]}


def test_secret_table_never_appears_in_any_role_view(client: TestClient) -> None:
    for persona in DEMO_PERSONAS:
        body = schema_for(client, persona)
        assert "internal_fraud_flags" not in {t["name"] for t in body["tables"]}


def test_analyst_joins_list_excludes_finance_tables(client: TestClient) -> None:
    body = schema_for(client, "analista.ngola")
    assert all("payouts" not in j and "payments" not in j for j in body["joins"])


def test_semantic_loader_rejects_join_to_missing_column(tmp_path: Path) -> None:
    folder = _copy_semantic(tmp_path)
    text = (folder / "schema.yaml").read_text(encoding="utf-8")
    (folder / "schema.yaml").write_text(
        text.replace("to: sellers.id", "to: sellers.nope", 1), encoding="utf-8"
    )
    with pytest.raises(SemanticConfigError, match="inexistente"):
        load_semantic_model(folder)


def test_semantic_loader_rejects_unknown_role(tmp_path: Path) -> None:
    folder = _copy_semantic(tmp_path)
    text = (folder / "schema.yaml").read_text(encoding="utf-8")
    (folder / "schema.yaml").write_text(
        text.replace("roles: [seller_analyst, seller_finance, platform_admin]", "roles: [root]", 1),
        encoding="utf-8",
    )
    with pytest.raises(SemanticConfigError, match="papel desconhecido"):
        load_semantic_model(folder)


# --- auth: 401 and roles --------------------------------------------------------------------


def test_semantic_endpoint_without_token_is_401(client: TestClient) -> None:
    response = client.get("/schema/semantic")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer", "Basic abc", "Bearer not-a-jwt", "Bearer "])
def test_malformed_authorization_headers_are_401(client: TestClient, header: str) -> None:
    response = client.get("/schema/semantic", headers={"Authorization": header})
    assert response.status_code == 401


def test_expired_token_is_rejected() -> None:
    old = issue_token(
        DEMO_PERSONAS["analista.ngola"],
        TEST_JWT_SECRET,
        now=int(time.time()) - 3600,
        ttl_seconds=60,
    )
    with pytest.raises(AuthError):
        verify_token(old, TEST_JWT_SECRET)


def test_token_signed_with_other_secret_is_rejected() -> None:
    token = issue_token(DEMO_PERSONAS["analista.ngola"], "x" * 40)
    with pytest.raises(AuthError):
        verify_token(token, TEST_JWT_SECRET)


def _forge(claims: dict) -> str:
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "a",
        "seller_id": 1,
        "role": "seller_analyst",
        "iat": now,
        "exp": now + 60,
    }
    base.update(claims)
    return jwt.encode(base, TEST_JWT_SECRET, algorithm="HS256")


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "outra-api"},
        {"role": "root"},
        {"seller_id": "1 OR 1=1"},
        {"seller_id": True},
        {"sub": ""},
    ],
)
def test_forged_or_malformed_claims_are_rejected(claims: dict) -> None:
    with pytest.raises(AuthError):
        verify_token(_forge(claims), TEST_JWT_SECRET)


def test_demo_login_is_disabled_by_default() -> None:
    client = TestClient(create_app(Settings(semantic_dir=SEMANTIC_DIR)))
    response = client.post("/auth/demo-login", json={"persona": "analista.ngola"})
    assert response.status_code == 404


def test_demo_login_rejects_unknown_persona(client: TestClient) -> None:
    response = client.post("/auth/demo-login", json={"persona": "nao.existe"})
    assert response.status_code == 401


def test_roles_map_to_expected_personas() -> None:
    assert DEMO_PERSONAS["analista.ngola"].role is Role.SELLER_ANALYST
    assert DEMO_PERSONAS["financas.ngola"].role is Role.SELLER_FINANCE
    assert DEMO_PERSONAS["admin.plataforma"].role is Role.PLATFORM_ADMIN


def test_settings_reject_invalid_provider_and_short_secret() -> None:
    with pytest.raises(ConfigError):
        Settings(llm_provider="desconhecido")
    with pytest.raises(ConfigError):
        Settings(jwt_secret="curto")


def test_settings_from_env_parses_and_validates() -> None:
    parsed = Settings.from_env({"QS_DEMO_AUTH": "true", "QS_MAX_ROWS": "50"})
    assert parsed.demo_auth is True and parsed.max_rows == 50
    with pytest.raises(ConfigError):
        Settings.from_env({"QS_MAX_ROWS": "abc"})
    with pytest.raises(ConfigError):
        Settings.from_env({"QS_DEMO_AUTH": "talvez"})
