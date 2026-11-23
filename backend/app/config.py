"""Configuração da aplicação, lida de variáveis de ambiente (nunca de ficheiros .env).

Todos os valores são validados na leitura: um valor inválido falha ao arrancar, com uma mensagem
que não inclui segredos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SEMANTIC_DIR = ROOT_DIR / "semantic"
DEV_JWT_SECRET_MIN_LENGTH = 32


class ConfigError(ValueError):
    """Configuração inválida. A mensagem nunca contém valores secretos."""


def _parse_bool(name: str, raw: str | None, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} deve ser true ou false")


def _parse_int(name: str, raw: str | None, default: int, minimum: int, maximum: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve ser um inteiro") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} fora do intervalo {minimum}-{maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    reader_dsn: str | None = None
    jwt_secret: str = field(default="", repr=False)
    demo_auth: bool = False
    demo_mode: bool = False
    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ("http://localhost:13200",)
    semantic_dir: Path = DEFAULT_SEMANTIC_DIR
    statement_timeout_ms: int = 3000
    max_rows: int = 500
    max_result_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if self.llm_provider not in {"mock", "openai"}:
            raise ConfigError("QS_LLM_PROVIDER deve ser mock ou openai")
        if self.jwt_secret and len(self.jwt_secret) < DEV_JWT_SECRET_MIN_LENGTH:
            raise ConfigError(
                f"QS_JWT_SECRET deve ter pelo menos {DEV_JWT_SECRET_MIN_LENGTH} caracteres"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        origins_raw = env.get("QS_CORS_ORIGINS", "http://localhost:13200")
        origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip())
        semantic_dir = Path(env["QS_SEMANTIC_DIR"]) if env.get("QS_SEMANTIC_DIR") else None
        return cls(
            reader_dsn=env.get("QS_READER_DSN") or None,
            jwt_secret=env.get("QS_JWT_SECRET", ""),
            demo_auth=_parse_bool("QS_DEMO_AUTH", env.get("QS_DEMO_AUTH"), False),
            demo_mode=_parse_bool("QS_DEMO_MODE", env.get("QS_DEMO_MODE"), False),
            llm_provider=(env.get("QS_LLM_PROVIDER") or "mock").strip().lower(),
            llm_base_url=env.get("QS_LLM_BASE_URL", "https://api.openai.com/v1").strip(),
            llm_model=env.get("QS_LLM_MODEL", "").strip(),
            llm_api_key=env.get("QS_LLM_API_KEY", ""),
            cors_origins=origins,
            semantic_dir=semantic_dir or DEFAULT_SEMANTIC_DIR,
            statement_timeout_ms=_parse_int(
                "QS_STATEMENT_TIMEOUT_MS", env.get("QS_STATEMENT_TIMEOUT_MS"), 3000, 100, 10_000
            ),
            max_rows=_parse_int("QS_MAX_ROWS", env.get("QS_MAX_ROWS"), 500, 1, 5000),
            max_result_bytes=_parse_int(
                "QS_MAX_RESULT_BYTES", env.get("QS_MAX_RESULT_BYTES"), 1_000_000, 1000, 50_000_000
            ),
        )
