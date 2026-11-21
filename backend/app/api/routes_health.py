"""GET /health: estado do serviço. Não é autenticado e não revela detalhes de infra."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
