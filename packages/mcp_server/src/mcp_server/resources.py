from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_server.db import DuckDBConnection
from mcp_server.models import DatabaseSettings, TableMetadata
from mcp_server.schema import get_schema

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_GLOSSARY_PATH = PROJECT_ROOT / "database" / "metadata" / "kpi_glossary.json"


def get_schema_overview(settings: DatabaseSettings) -> list[dict[str, Any]]:
    schema = get_schema(settings)
    return [
        {
            "name": table.name,
            "comment": table.comment,
            "row_count": table.row_count,
        }
        for table in schema.metadata.tables
    ]


def get_table_dictionary(settings: DatabaseSettings, table_name: str) -> dict[str, Any]:
    schema = get_schema(settings)
    table = _find_table(schema.metadata.tables, table_name)
    return {
        "name": table.name,
        "comment": table.comment,
        "row_count": table.row_count,
        "columns": [
            {
                "name": column.name,
                "data_type": column.data_type,
                "nullable": column.nullable,
                "comment": column.comment,
            }
            for column in table.columns
        ],
    }


def get_schema_relationships(settings: DatabaseSettings) -> list[dict[str, Any]]:
    with DuckDBConnection(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                table_name,
                constraint_column_names,
                referenced_table,
                referenced_column_names,
                constraint_name
            FROM duckdb_constraints()
            WHERE schema_name = 'main'
              AND constraint_type = 'FOREIGN KEY'
            ORDER BY table_name, constraint_name
            """
        ).fetchall()

    return [
        {
            "from_table": table_name,
            "from_columns": list(column_names),
            "to_table": referenced_table,
            "to_columns": list(referenced_column_names),
            "constraint_name": constraint_name,
        }
        for (
            table_name,
            column_names,
            referenced_table,
            referenced_column_names,
            constraint_name,
        ) in rows
    ]


def get_business_glossary() -> str:
    return DEFAULT_GLOSSARY_PATH.read_text(encoding="utf-8")


def get_business_glossary_term(term: str) -> dict[str, Any]:
    glossary = json.loads(get_business_glossary())
    normalized_term = term.casefold()
    matches = {
        glossary_term: definition
        for glossary_term, definition in glossary.items()
        if normalized_term in glossary_term.casefold()
    }
    if matches:
        return matches

    for glossary_term, definition in glossary.items():
        searchable_text = " ".join(_iter_searchable_values(definition)).casefold()
        if normalized_term in searchable_text:
            matches[glossary_term] = definition

    if matches:
        return matches

    msg = f"Unknown business glossary term: {term}"
    raise ValueError(msg)


def _iter_searchable_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_iter_searchable_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_iter_searchable_values(item))
        return values
    return []


def _find_table(tables: list[TableMetadata], table_name: str) -> TableMetadata:
    for table in tables:
        if table.name == table_name:
            return table

    msg = f"Unknown table: {table_name}"
    raise ValueError(msg)
