from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from agent_orchestrator.config import get_database_path
from agent_orchestrator.llm import LiteLlmClient, LlmClient
from evaluation.benchmark.models import QuestionSpec
from evaluation.benchmark.sql_utils import execute_for_evaluation
from mcp_server import DatabaseSettings, get_schema, get_schema_relationships


def run_system_a(
    question_spec: QuestionSpec,
    *,
    database_path: str | Path | None = None,
    llm: LlmClient | None = None,
    schema_context: str | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    client = llm or LiteLlmClient()
    db_path = Path(database_path or get_database_path())
    trace = _initial_trace()
    errors: list[str] = []
    generated_sql: str | None = None
    execution_result: dict[str, Any] | None = None
    last_error: str | None = None

    try:
        response = client.complete(
            system=_baseline_system_prompt(schema_context or build_static_schema_context(db_path)),
            user=question_spec.question,
        )
        trace["llm_calls"] = 1
        _merge_usage(trace, response.usage)
        parsed = _parse_baseline_response(response.content)
        if parsed["parse_error"]:
            errors.append("json_parse_error")
        if parsed["status"] == "UNANSWERABLE":
            last_error = "UNANSWERABLE"
        else:
            generated_sql = parsed["sql"]
            if generated_sql:
                execution_result = execute_for_evaluation(db_path, generated_sql)
                trace["sql_executions"] = 1
                if not execution_result.get("success"):
                    last_error = _error_to_text(execution_result.get("error"))
                    errors.append(last_error)
    except Exception as exc:
        last_error = f"RUNTIME_ERROR: {exc}"
        errors.append(last_error)

    trace["runtime_seconds"] = round(time.perf_counter() - started_at, 6)
    status = _status(last_error)
    return {
        "system": "A",
        "status": status,
        "question": question_spec.question,
        "first_generated_sql": generated_sql,
        "final_generated_sql": generated_sql,
        "final_answer": None if generated_sql else last_error,
        "execution_result": execution_result,
        "last_error": last_error,
        "error_history": errors,
        "iterations": 0,
        "trace": trace,
    }


def build_static_schema_context(database_path: str | Path) -> str:
    settings = DatabaseSettings.from_path(database_path)
    schema = get_schema(settings)
    relationships = get_schema_relationships(settings)
    table_blocks = []
    for table in schema.metadata.tables:
        lines = [f"Table: {table.name}"]
        lines.append("Columns:")
        for column in table.columns:
            nullable = "nullable" if column.nullable else "not null"
            lines.append(f" - {column.name} {column.data_type} {nullable}")
        table_blocks.append("\n".join(lines))
    relationship_lines = [
        f"- {item['from_table']}.{','.join(item['from_columns'])} -> "
        f"{item['to_table']}.{','.join(item['to_columns'])}"
        for item in relationships
    ]
    return "\n\n".join(
        [
            "Static structural schema context for baseline System A.",
            "Table and column comments are intentionally excluded from this baseline.",
            "\n\n".join(table_blocks),
            "Relationships:",
            "\n".join(relationship_lines) if relationship_lines else "- none",
        ]
    )


def _baseline_system_prompt(schema_context: str) -> str:
    return f"""\
You are a Text-to-SQL system for analytical BI questions.
Use only the static schema below. Do not use tools. Do not invent tables or columns.
Return JSON only with either:
{{"status": "SQL", "sql": "SELECT ...", "reason": null}}
or:
{{"status": "UNANSWERABLE", "sql": null, "reason": "Required data is absent from the schema."}}

When the question cannot be answered from the schema, use the UNANSWERABLE JSON
object exactly. Do not express refusal only in free text.

Only read-only SELECT or WITH queries are allowed.

{schema_context}
"""


def _parse_baseline_response(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_fence(content))
        status = str(payload.get("status") or "").upper()
        sql = payload.get("sql")
        return {
            "status": "UNANSWERABLE" if status == "UNANSWERABLE" else "SQL",
            "sql": str(sql).strip() if sql else None,
            "parse_error": False,
        }
    except Exception:
        sql = _extract_sql(content)
        return {"status": "SQL" if sql else "UNANSWERABLE", "sql": sql, "parse_error": True}


def _strip_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def _extract_sql(content: str) -> str | None:
    stripped = _strip_fence(content)
    if stripped.upper() == "UNANSWERABLE":
        return None
    match = re.search(r"\b(?:select|with)\b.*", stripped, flags=re.IGNORECASE | re.DOTALL)
    return match.group(0).strip().rstrip(";") if match else None


def _initial_trace() -> dict[str, Any]:
    return {
        "llm_calls": 0,
        "mcp_calls": 0,
        "sql_executions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "runtime_seconds": 0.0,
        "retrieved_tables": [],
        "profiling_calls": 0,
    }


def _merge_usage(trace: dict[str, Any], usage: dict[str, int | None]) -> None:
    trace["input_tokens"] = usage.get("prompt_tokens") or 0
    trace["output_tokens"] = usage.get("completion_tokens") or 0
    trace["total_tokens"] = usage.get("total_tokens") or 0


def _status(last_error: str | None) -> str:
    if last_error == "UNANSWERABLE":
        return "CORRECT_REJECTION"
    return "ERROR" if last_error else "SUCCESS"


def _error_to_text(error: Any) -> str:
    if isinstance(error, dict):
        return f"{error.get('error_type') or 'SqlError'}: {error.get('message') or 'SQL failed'}"
    return str(error or "SQL failed")
