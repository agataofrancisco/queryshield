"""JWT demo (HS256): emissão e verificação do tenant (seller_id) e do papel.

Os tokens são validados com issuer, audience e expiração. Qualquer falha devolve AuthError
genérico: a resposta nunca explica qual verificação falhou.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt

from backend.app.semantic.models import Role

ISSUER = "queryshield"
AUDIENCE = "queryshield-api"
ALGORITHM = "HS256"
DEFAULT_TTL_SECONDS = 900


class AuthError(Exception):
    """Token ausente, inválido ou expirado."""


@dataclass(frozen=True)
class Principal:
    user: str
    seller_id: int
    role: Role


DEMO_PERSONAS: dict[str, Principal] = {
    "analista.ngola": Principal("analista.ngola", 1, Role.SELLER_ANALYST),
    "financas.ngola": Principal("financas.ngola", 1, Role.SELLER_FINANCE),
    "analista.benguela": Principal("analista.benguela", 2, Role.SELLER_ANALYST),
    "admin.plataforma": Principal("admin.plataforma", 1, Role.PLATFORM_ADMIN),
}


def issue_token(
    principal: Principal,
    secret: str,
    *,
    now: int | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    issued_at = int(time.time()) if now is None else now
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": principal.user,
        "seller_id": principal.seller_id,
        "role": principal.role.value,
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def verify_token(token: object, secret: str) -> Principal:
    if not isinstance(token, str) or not token or not secret:
        raise AuthError("token inválido")
    options = {"require": ["exp", "iat", "iss", "aud", "sub"]}
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise AuthError("token inválido") from exc
    return _principal_from_claims(claims)


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    user = claims.get("sub")
    seller_id = claims.get("seller_id")
    role_raw = claims.get("role")
    # Validação de tipos: nunca assumir o tipo de um valor vindo do token.
    if not isinstance(user, str) or not user:
        raise AuthError("token inválido")
    if not isinstance(seller_id, int) or isinstance(seller_id, bool) or seller_id <= 0:
        raise AuthError("token inválido")
    if not isinstance(role_raw, str):
        raise AuthError("token inválido")
    try:
        role = Role(role_raw)
    except ValueError as exc:
        raise AuthError("token inválido") from exc
    return Principal(user=user, seller_id=seller_id, role=role)
