"""Modelos tipados da semantic layer (validados na leitura dos YAML)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    SELLER_ANALYST = "seller_analyst"
    SELLER_FINANCE = "seller_finance"
    PLATFORM_ADMIN = "platform_admin"


class ColumnSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    type: str
    description: str
    roles: frozenset[Role] | None = None


class TableSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    roles: frozenset[Role]
    columns: dict[str, ColumnSpec]

    def visible_columns(self, role: Role) -> list[ColumnSpec]:
        if role not in self.roles:
            return []
        return [c for c in self.columns.values() if c.roles is None or role in c.roles]


class JoinEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_table: str
    from_column: str
    to_table: str
    to_column: str

    def key(self) -> frozenset[tuple[str, str]]:
        return frozenset({(self.from_table, self.from_column), (self.to_table, self.to_column)})

    def as_text(self) -> str:
        return f"{self.from_table}.{self.from_column} = {self.to_table}.{self.to_column}"


class Signature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    aggregate: Literal["SUM", "COUNT", "AVG"]
    column: str


class MetricSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    title: str
    description: str
    unit: str
    canonical_sql: str
    signature: Signature | None = None
    requires_tables: tuple[str, ...] = Field(default_factory=tuple)
    requires_filter_columns: tuple[str, ...] = Field(default_factory=tuple)
    filter_column: str | None = None
