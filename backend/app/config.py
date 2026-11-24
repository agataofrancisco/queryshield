"""Configuração da aplicação, lida de variáveis de ambiente (nunca de ficheiros .env).

Todos os valores são validados na leitura: um valor inválido falha ao arrancar, com uma mensagem
que não inclui segredos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

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


def _parse_seller_ids(raw: str | None) -> tuple[int, ...]:
    if raw is None or raw.strip() == "":
        return (1, 2, 3)
    try:
        ids = tuple(int(part) for part in raw.split(","))
    except ValueError as exc:
        raise ConfigError("QS_SELLER_IDS deve ser uma lista de inteiros") from exc
    if (
        not ids
        or any(i not in {1, 2, 3} for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ConfigError("QS_SELLER_IDS deve conter IDs únicos entre 1 e 3 (migração 006)")
    return ids


def _parse_seller_passwords(env: Mapping[str, str], seller_ids: tuple[int, ...]) -> dict[int, str]:
    passwords = {seller_id: env.get(f"QS_READER_PASSWORD_S{seller_id}", "") for seller_id in seller_ids}
    if any(len(password) < 24 for password in passwords.values()):
        raise ConfigError("defina passwords distintas com pelo menos 24 caracteres para cada role")
    if len(set(passwords.values())) != len(passwords):
        raise ConfigError("cada role de vendedor tem de usar uma password diferente")
    return passwords


def seller_role_name(seller_id: int) -> str:
    """Nome do role de login do vendedor (criado pela migração 006)."""
    return f"qs_reader_s{seller_id}"


def seller_dsn(
    template: str, seller_id: int, passwords: Mapping[int, str] | None = None
) -> str:
    """Materializa a ligação de um vendedor, sem reutilizar credenciais entre roles."""
    if "{role}" not in template:
        raise ConfigError("QS_READER_DSN_TEMPLATE tem de conter {role}")
    dsn = template.replace("{role}", seller_role_name(seller_id))
    if "{password}" in dsn:
        password = (passwords or {}).get(seller_id)
        if not password:
            raise ConfigError(f"password não configurada para o role do vendedor {seller_id}")
        dsn = dsn.replace("{password}", quote(password, safe=""))
    return dsn


@dataclass(frozen=True)
class Settings:
    # Modelo de ligação: contém o token {role}, substituído por qs_reader_s<N> em cada vendedor.
    reader_dsn_template: str | None = field(default=None, repr=False)
    seller_passwords: Mapping[int, str] = field(default_factory=dict, repr=False)
    seller_ids: tuple[int, ...] = (1, 2, 3)
    deadline_margin_ms: int = 1000
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
        seller_ids = _parse_seller_ids(env.get("QS_SELLER_IDS"))
        reader_dsn_template = env.get("QS_READER_DSN_TEMPLATE") or None
        seller_passwords = (
            _parse_seller_passwords(env, seller_ids)
            if reader_dsn_template and "{password}" in reader_dsn_template
            else {}
        )
        return cls(
            reader_dsn_template=reader_dsn_template,
            seller_passwords=seller_passwords,
            seller_ids=seller_ids,
            deadline_margin_ms=_parse_int(
                "QS_DEADLINE_MARGIN_MS", env.get("QS_DEADLINE_MARGIN_MS"), 1000, 0, 60_000
            ),
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
