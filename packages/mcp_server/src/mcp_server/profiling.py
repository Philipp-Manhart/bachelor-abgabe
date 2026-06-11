from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from mcp_server.db import DuckDBConnection
from mcp_server.models import (
    CategoricalValuesRequest,
    DatabaseSettings,
    NumericSummaryRequest,
    NumericSummaryResult,
    SampleDataRequest,
)

NUMERIC_TYPE_PREFIXES = (
    "BIGINT",
    "DECIMAL",
    "DOUBLE",
    "FLOAT",
    "HUGEINT",
    "INTEGER",
    "REAL",
    "SMALLINT",
    "TINYINT",
    "UBIGINT",
    "UHUGEINT",
    "UINTEGER",
    "USMALLINT",
    "UTINYINT",
)


def get_sample_data(settings: DatabaseSettings, request: SampleDataRequest) -> list[dict[str, Any]]:
    table_name = _resolve_table_name(settings, request.table_name)
    query = f"SELECT * FROM {_quote_identifier(table_name)} LIMIT ?"

    with DuckDBConnection(settings) as connection:
        result = connection.execute(query, [request.limit])
        columns = [column[0] for column in result.description or []]
        rows = result.fetchall()

    return [
        {column: _jsonable_value(value) for column, value in zip(columns, row, strict=True)}
        for row in rows
    ]


def get_categorical_values(
    settings: DatabaseSettings,
    request: CategoricalValuesRequest,
) -> list[str]:
    table_name, column_name, _data_type = _resolve_column(
        settings, request.table_name, request.column
    )
    query = (
        f"SELECT DISTINCT {_quote_identifier(column_name)} "
        f"FROM {_quote_identifier(table_name)} "
        f"WHERE {_quote_identifier(column_name)} IS NOT NULL "
        f"ORDER BY {_quote_identifier(column_name)}"
    )

    with DuckDBConnection(settings) as connection:
        rows = connection.execute(query).fetchall()

    return [str(row[0]) for row in rows]


def get_numeric_summary(
    settings: DatabaseSettings,
    request: NumericSummaryRequest,
) -> NumericSummaryResult:
    table_name, column_name, data_type = _resolve_column(
        settings, request.table_name, request.column
    )
    column_identifier = _quote_identifier(column_name)
    table_identifier = _quote_identifier(table_name)
    avg_expression = f"AVG({column_identifier})" if _is_numeric_type(data_type) else "NULL"
    query = (
        f"SELECT MIN({column_identifier}), MAX({column_identifier}), {avg_expression}, "
        f"SUM(CASE WHEN {column_identifier} IS NULL THEN 1 ELSE 0 END) "
        f"FROM {table_identifier}"
    )

    with DuckDBConnection(settings) as connection:
        row = connection.execute(query).fetchone()

    if row is None:
        msg = f"Could not summarize {table_name}.{column_name}"
        raise RuntimeError(msg)

    minimum, maximum, average, null_count = row
    return NumericSummaryResult(
        table_name=table_name,
        column=column_name,
        data_type=data_type,
        min=_jsonable_value(minimum),
        max=_jsonable_value(maximum),
        avg=None if average is None else float(average),
        null_count=int(null_count or 0),
    )


def _resolve_table_name(settings: DatabaseSettings, table_name: str) -> str:
    with DuckDBConnection(settings) as connection:
        row = connection.execute(
            """
            SELECT table_name
            FROM duckdb_tables()
            WHERE schema_name = 'main'
              AND internal = FALSE
              AND table_name = ?
            """,
            [table_name],
        ).fetchone()

    if row is None:
        msg = f"Unknown table: {table_name}"
        raise ValueError(msg)
    return str(row[0])


def _resolve_column(
    settings: DatabaseSettings, table_name: str, column_name: str
) -> tuple[str, str, str]:
    with DuckDBConnection(settings) as connection:
        row = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM duckdb_columns()
            WHERE schema_name = 'main'
              AND table_name = ?
              AND column_name = ?
            """,
            [table_name, column_name],
        ).fetchone()

    if row is None:
        msg = f"Unknown column: {table_name}.{column_name}"
        raise ValueError(msg)
    return str(row[0]), str(row[1]), str(row[2])


def _is_numeric_type(data_type: str) -> bool:
    normalized_type = data_type.upper()
    return any(normalized_type.startswith(prefix) for prefix in NUMERIC_TYPE_PREFIXES)


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value
