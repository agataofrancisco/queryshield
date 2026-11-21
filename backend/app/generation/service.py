"""Serviço de geração: chama o gerador e devolve a proposta. Nunca executa SQL."""

from __future__ import annotations

from typing import Any, Protocol

from backend.app.generation.models import GenerationError, GenerationOutput
from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import Role

MAX_QUESTION_CHARS = 500


class QueryGenerator(Protocol):
    name: str

    def generate(self, question: str, role: Role, model: SemanticModel) -> GenerationOutput: ...


def normalise_question(raw: object) -> str:
    """Valida a pergunta na fronteira: tipo, tamanho e espaços."""
    if not isinstance(raw, str):
        raise GenerationError("invalid_input", "A pergunta tem de ser texto.")
    text = " ".join(raw.split())
    if len(text) < 3 or len(text) > MAX_QUESTION_CHARS:
        raise GenerationError("invalid_input", "A pergunta deve ter entre 3 e 500 caracteres.")
    return text


def build_proposal(
    question: str, role: Role, model: SemanticModel, generator: QueryGenerator
) -> dict[str, Any]:
    output = generator.generate(normalise_question(question), role, model)
    clarification = output.needs_clarification
    if clarification is not None:
        status = "needs_clarification"
    elif output.sql is None:
        status = "unsupported"
    else:
        status = "generated"
    return {
        "status": status,
        "provider": generator.name,
        "sql": output.sql,
        "parameters": output.parameters,
        "metrics_used": output.metrics_used,
        "tables_used": output.tables_used,
        "assumptions": output.assumptions,
        "rationale": output.rationale,
        "clarification": (
            {"question": clarification.question, "options": clarification.options}
            if clarification
            else None
        ),
    }
