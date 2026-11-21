"""Gerador mock determinístico: sem rede, sem LLM, cobre um conjunto fixo de intenções.

Não é um modelo. Serve para demonstração offline e para testar o pipeline. O serviço marca
todas as respostas com provider "mock". Fora das intenções suportadas devolve sql = null.
"""

from __future__ import annotations

import re
from datetime import date

from backend.app.generation.models import Clarification, GenerationOutput
from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import Role

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
PERIOD_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(?:de\s+)?(\d{4})\b")
VALID_STATUS = "('paid', 'shipped', 'delivered')"

RECEITA_SQL = (
    "SELECT ROUND(SUM(oi.line_total) - SUM(COALESCE(r.refund, 0)), 2) AS receita\n"
    "FROM orders o\n"
    "JOIN order_items oi ON oi.order_id = o.id\n"
    "LEFT JOIN (SELECT order_item_id, SUM(refund_amount) AS refund FROM returns\n"
    "           GROUP BY order_item_id) r ON r.order_item_id = oi.id\n"
    f"WHERE o.status IN {VALID_STATUS} AND o.currency = 'AOA'"
)
ENCOMENDAS_SQL = (
    "SELECT COUNT(DISTINCT o.id) AS encomendas\n"
    "FROM orders o\n"
    f"WHERE o.status IN {VALID_STATUS} AND o.currency = 'AOA'"
)
DEVOLUCOES_SQL = "SELECT ROUND(SUM(r.refund_amount), 2) AS devolucoes\nFROM returns r"


def parse_period(question: str) -> tuple[date, date] | None:
    """Mês e ano por extenso (ex.: 'março de 2026'). Devolve [início, fim) ou None."""
    match = PERIOD_RE.search(question.lower())
    if not match:
        return None
    month = MONTHS[match.group(1)]
    year = int(match.group(2))
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


class MockGenerator:
    name = "mock"

    def generate(self, question: str, role: Role, model: SemanticModel) -> GenerationOutput:
        text = question.lower()
        if "email" in text or "e-mail" in text or "telefone" in text:
            # Simula um pedido indevido de contactos de clientes: a validação tem de o bloquear.
            return GenerationOutput(
                sql="SELECT email FROM customers LIMIT 50",
                tables_used=["customers"],
                rationale="Pedido de contactos de clientes (simulação de pedido não autorizado).",
            )
        if "melhores clientes" in text and "receita" not in text and "encomenda" not in text:
            return GenerationOutput(
                needs_clarification=Clarification(
                    question="Como queres medir os melhores clientes?",
                    options=["Por receita", "Por número de encomendas", "Por período"],
                ),
                rationale="A métrica de ranking não está definida na pergunta.",
            )
        period = parse_period(question)
        assumptions: list[str] = []
        params: dict[str, str] = {}
        if period is not None:
            params = {"start": period[0].isoformat(), "end": period[1].isoformat()}
        else:
            assumptions.append("Sem período indicado: considerado todo o histórico disponível.")

        if "devolu" in text:
            sql = DEVOLUCOES_SQL
            if period is not None:
                sql += "\nWHERE r.returned_on >= %(start)s AND r.returned_on < %(end)s"
            return GenerationOutput(
                sql=sql,
                parameters=params,
                metrics_used=["devolucao"],
                tables_used=["returns"],
                assumptions=assumptions,
                rationale="Soma dos reembolsos registados nas devoluções.",
            )
        if "receita" in text:
            sql = RECEITA_SQL + _period_clause("o.ordered_on", period)
            return GenerationOutput(
                sql=sql,
                parameters=params,
                metrics_used=["receita"],
                tables_used=["orders", "order_items", "returns"],
                assumptions=assumptions,
                rationale="Receita líquida: itens de encomendas válidas em AOA menos devoluções.",
            )
        if "encomenda" in text and any(k in text for k in ("quantas", "número", "numero", "conta")):
            sql = ENCOMENDAS_SQL + _period_clause("o.ordered_on", period)
            return GenerationOutput(
                sql=sql,
                parameters=params,
                metrics_used=["encomenda_valida"],
                tables_used=["orders"],
                assumptions=assumptions,
                rationale="Contagem de encomendas válidas em AOA.",
            )
        return GenerationOutput(
            rationale="Pergunta fora das intenções suportadas pelo gerador mock."
        )


def _period_clause(column: str, period: tuple[date, date] | None) -> str:
    if period is None:
        return ""
    return f" AND {column} >= %(start)s AND {column} < %(end)s"
