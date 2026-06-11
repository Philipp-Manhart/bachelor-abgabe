from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "benchmark.duckdb"
DEFAULT_MCP_SERVER_URL = "http://127.0.0.1:8000/sse"


@dataclass(frozen=True)
class OrchestratorSettings:
    database_path: Path
    model: str
    temperature: float
    api_key: str | None
    base_url: str | None


def load_settings() -> OrchestratorSettings:
    load_dotenv()
    return OrchestratorSettings(
        database_path=get_database_path(),
        model=os.getenv("TEXT_TO_SQL_MODEL")
        or os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"),
        temperature=float(os.getenv("TEXT_TO_SQL_TEMPERATURE", "0")),
        api_key=os.getenv("TEXT_TO_SQL_API_KEY") or os.getenv("LLM_API_KEY") or None,
        base_url=os.getenv("TEXT_TO_SQL_BASE_URL") or os.getenv("LLM_BASE_URL") or None,
    )


def get_database_path() -> Path:
    configured_path = os.getenv("DUCKDB_DATABASE_PATH") or os.getenv("DATABASE_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


def get_mcp_server_url() -> str:
    return os.getenv("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)
