from __future__ import annotations

import re
import threading
import time
import traceback
from datetime import date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from typing import Any

import duckdb

from mcp_server.db import DuckDBConnection
from mcp_server.models import (
    DatabaseSettings,
    ExecuteSqlRequest,
    ExecuteSqlResult,
    SqlExecutionError,
    ValidateSqlRequest,
    ValidateSqlResult,
)

ALLOWED_START_KEYWORDS = frozenset({"select", "with"})
BLOCKED_KEYWORDS = frozenset(
    {
        "alter",
        "attach",
        "call",
        "copy",
        "create",
        "delete",
        "detach",
        "drop",
        "export",
        "import",
        "insert",
        "install",
        "load",
        "merge",
        "pragma",
        "reset",
        "set",
        "truncate",
        "update",
        "vacuum",
    }
)


def execute_sql(settings: DatabaseSettings, request: ExecuteSqlRequest) -> ExecuteSqlResult:
    started_at = time.perf_counter()
    sql = _normalize_sql(request.sql)
    error = _validate_read_only_sql(sql)
    if error is not None:
        return _failure(error, started_at)

    read_only_settings = settings.model_copy(update={"read_only": True})
    try:
        with DuckDBConnection(read_only_settings) as connection:
            timed_out = False

            def interrupt_query() -> None:
                nonlocal timed_out
                timed_out = True
                connection.interrupt()

            timer = (
                threading.Timer(request.timeout_ms / 1000, interrupt_query)
                if request.timeout_ms is not None
                else None
            )
            try:
                if timer is not None:
                    timer.start()
                result = connection.execute(sql)
                columns = _get_column_names(result)
                fetched_rows = result.fetchmany(request.max_rows + 1)
            except duckdb.Error as exc:
                if timed_out:
                    return _failure(
                        SqlExecutionError(
                            error_type="QueryTimeoutError",
                            message=f"SQL execution exceeded timeout of {request.timeout_ms} ms.",
                            stacktrace=traceback.format_exc(),
                        ),
                        started_at,
                    )
                raise exc
            finally:
                if timer is not None:
                    timer.cancel()
    except duckdb.Error as exc:
        return _failure(
            SqlExecutionError(
                error_type=type(exc).__name__,
                message=str(exc),
                stacktrace=traceback.format_exc(),
            ),
            started_at,
        )

    truncated = len(fetched_rows) > request.max_rows
    rows = [[_jsonable_value(value) for value in row] for row in fetched_rows[: request.max_rows]]
    return ExecuteSqlResult(
        success=True,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=_elapsed_ms(started_at),
    )


def validate_sql(settings: DatabaseSettings, request: ValidateSqlRequest) -> ValidateSqlResult:
    sql = _normalize_sql(request.query)
    error = _validate_read_only_sql(sql)
    if error is not None:
        return ValidateSqlResult(valid=False, error=error)

    read_only_settings = settings.model_copy(update={"read_only": True})
    try:
        with DuckDBConnection(read_only_settings) as connection:
            connection.execute(f"EXPLAIN {sql}")
    except duckdb.Error as exc:
        return ValidateSqlResult(
            valid=False,
            error=SqlExecutionError(
                error_type=type(exc).__name__,
                message=str(exc),
                stacktrace=traceback.format_exc(),
            ),
        )

    return ValidateSqlResult(valid=True)


def _normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def _validate_read_only_sql(sql: str) -> SqlExecutionError | None:
    sql_for_scan = _sql_for_keyword_scan(sql)

    if _has_multiple_statements(sql_for_scan):
        return SqlExecutionError(
            error_type="UnsafeSqlError",
            message="Only a single SQL statement is allowed.",
        )

    first_keyword = _first_keyword(sql_for_scan)
    if first_keyword not in ALLOWED_START_KEYWORDS:
        return SqlExecutionError(
            error_type="UnsafeSqlError",
            message="Only SELECT and WITH queries are allowed.",
        )

    blocked_keyword = _find_blocked_keyword(sql_for_scan)
    if blocked_keyword is not None:
        return SqlExecutionError(
            error_type="UnsafeSqlError",
            message=f"Blocked SQL keyword found: {blocked_keyword.upper()}",
        )

    return None


def _has_multiple_statements(sql: str) -> bool:
    return ";" in sql


def _sql_for_keyword_scan(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"'(?:''|[^'])*'", " ", sql)
    return re.sub(r'"(?:""|[^"])*"', " ", sql)


def _first_keyword(sql: str) -> str | None:
    match = re.match(r"\s*(?P<keyword>[a-zA-Z_]+)", sql)
    if match is None:
        return None
    return match.group("keyword").lower()


def _find_blocked_keyword(sql: str) -> str | None:
    lowered_sql = sql.lower()
    for keyword in sorted(BLOCKED_KEYWORDS):
        if re.search(rf"\b{re.escape(keyword)}\b", lowered_sql):
            return keyword
    return None


def _get_column_names(result: duckdb.DuckDBPyConnection) -> list[str]:
    if result.description is None:
        return []
    return [column[0] for column in result.description]


def _failure(error: SqlExecutionError, started_at: float) -> ExecuteSqlResult:
    return ExecuteSqlResult(
        success=False,
        error=error,
        elapsed_ms=_elapsed_ms(started_at),
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date | datetime_time):
        return value.isoformat()
    return value
