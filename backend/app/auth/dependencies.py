"""Dependência FastAPI que exige um Bearer token válido e devolve o Principal."""

from __future__ import annotations

from fastapi import Request

from backend.app.api.errors import ApiError
from backend.app.auth.tokens import AuthError, Principal, verify_token

UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def get_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthenticated", "Autenticação necessária.", UNAUTHENTICATED_HEADERS)
    secret = request.app.state.settings.jwt_secret
    try:
        return verify_token(token.strip(), secret)
    except AuthError as exc:
        raise ApiError(
            401, "unauthenticated", "Autenticação necessária.", UNAUTHENTICATED_HEADERS
        ) from exc
