"""POST /auth/demo-login: emite um token demo para uma persona fictícia.

Desactivado por omissão. Só existe com QS_DEMO_AUTH=true e QS_JWT_SECRET definido.
Não é um mecanismo de autenticação de produção: não há palavra-passe.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.errors import ApiError
from backend.app.auth.tokens import DEFAULT_TTL_SECONDS, DEMO_PERSONAS, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class DemoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona: Annotated[str, Field(min_length=1, max_length=64)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    seller_id: int
    role: str


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(body: DemoLoginRequest, request: Request) -> TokenResponse:
    settings = request.app.state.settings
    if not settings.demo_auth or not settings.jwt_secret:
        raise ApiError(404, "not_found", "Recurso inexistente.")
    principal = DEMO_PERSONAS.get(body.persona)
    if principal is None:
        raise ApiError(401, "unauthenticated", "Persona desconhecida.")
    token = issue_token(principal, settings.jwt_secret)
    return TokenResponse(
        access_token=token,
        expires_in=DEFAULT_TTL_SECONDS,
        seller_id=principal.seller_id,
        role=principal.role.value,
    )
