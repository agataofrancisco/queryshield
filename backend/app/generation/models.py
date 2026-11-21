"""Contrato de saída do gerador de SQL e parsing defensivo.

A saída de um LLM é um dado não confiável: é parseada com limites de tamanho e tipos explícitos.
Qualquer falha vira GenerationError com um código genérico (nunca o conteúdo bruto).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_SQL = 20_000
MAX_TEXT = 300


class GenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


Scalar = str | int | float | bool | None
ShortText = Annotated[str, Field(max_length=MAX_TEXT)]


class Clarification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: Annotated[str, Field(max_length=MAX_TEXT)]
    options: Annotated[list[ShortText], Field(min_length=1, max_length=6)]


class GenerationOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sql: Annotated[str | None, Field(max_length=MAX_SQL)] = None
    parameters: dict[Annotated[str, Field(max_length=63)], Scalar] = Field(default_factory=dict)
    metrics_used: Annotated[list[ShortText], Field(max_length=10)] = Field(default_factory=list)
    tables_used: Annotated[list[ShortText], Field(max_length=10)] = Field(default_factory=list)
    assumptions: Annotated[list[ShortText], Field(max_length=10)] = Field(default_factory=list)
    rationale: Annotated[str, Field(max_length=1000)] = ""
    needs_clarification: Clarification | None = None


def parse_generation_json(content: object) -> GenerationOutput:
    """Converte o texto devolvido pelo modelo num GenerationOutput validado."""
    if not isinstance(content, str) or not content.strip():
        raise GenerationError(
            "generation_invalid_output", "O gerador não devolveu conteúdo válido."
        )
    try:
        data: Any = json.loads(content)
    except ValueError as exc:
        raise GenerationError(
            "generation_invalid_output", "Resposta do gerador não é JSON."
        ) from exc
    if not isinstance(data, dict):
        raise GenerationError("generation_invalid_output", "Resposta do gerador não é um objeto.")
    try:
        return GenerationOutput.model_validate(data)
    except ValidationError as exc:
        raise GenerationError(
            "generation_invalid_output", "Resposta do gerador fora do formato."
        ) from exc
