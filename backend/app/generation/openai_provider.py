"""Gerador compatível com a API de chat completions da OpenAI (via httpx).

A chave só é enviada no cabeçalho Authorization. Nunca aparece em erros, respostas ou logs.
O arranque exige chave e modelo quando este provider está activo (validado em create_app).
"""

from __future__ import annotations

import httpx

from backend.app.generation.models import GenerationError, GenerationOutput, parse_generation_json
from backend.app.generation.prompt import build_messages
from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import Role


class OpenAICompatibleGenerator:
    name = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def generate(self, question: str, role: Role, model: SemanticModel) -> GenerationOutput:
        body = {
            "model": self._model,
            "messages": build_messages(question, role, model),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = self._client.post("/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise GenerationError(
                "provider_unavailable", "O gerador de SQL não está disponível."
            ) from exc
        if response.status_code != 200:
            raise GenerationError("provider_unavailable", "O gerador de SQL devolveu um erro.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise GenerationError(
                "generation_invalid_output", "Resposta do gerador inválida."
            ) from exc
        return parse_generation_json(content)
