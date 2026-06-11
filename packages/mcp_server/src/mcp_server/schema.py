from __future__ import annotations

import duckdb

from mcp_server.db import DuckDBConnection
from mcp_server.models import (
    ColumnMetadata,
    DatabaseSettings,
    SchemaMetadata,
    SchemaResponse,
    TableMetadata,
)


def get_schema(settings: DatabaseSettings) -> SchemaResponse:
    with DuckDBConnection(settings) as connection:
        tables = _load_tables(connection)

    metadata = SchemaMetadata(database_path=settings.database_path, tables=tables)
    return SchemaResponse(metadata=metadata, context=format_schema_context(metadata))


def format_schema_context(metadata: SchemaMetadata) -> str:
    lines: list[str] = []
    for table in metadata.tables:
        row_count = "unknown" if table.row_count is None else str(table.row_count)
        lines.append(f"Table: {table.name} ({row_count} rows)")
        if table.comment:
            lines.append(f"Purpose: {table.comment}")
        lines.append("Columns:")
        for column in table.columns:
            nullable = "nullable" if column.nullable else "not null"
            description = f" - {column.name} {column.data_type} {nullable}"
            if column.comment:
                description = f"{description}: {column.comment}"
            lines.append(description)
        lines.append("")
    return "\n".join(lines).strip()


def _load_tables(connection: duckdb.DuckDBPyConnection) -> list[TableMetadata]:
    table_rows = connection.execute(
        """
        SELECT table_name, comment
        FROM duckdb_tables()
        WHERE schema_name = 'main'
          AND internal = FALSE
        ORDER BY table_name
        """
    ).fetchall()

    column_rows = connection.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, comment
        FROM duckdb_columns()
        WHERE schema_name = 'main'
        ORDER BY table_name, column_index
        """
    ).fetchall()

    columns_by_table: dict[str, list[ColumnMetadata]] = {}
    for table_name, column_name, data_type, is_nullable, comment in column_rows:
        columns_by_table.setdefault(table_name, []).append(
            ColumnMetadata(
                name=column_name,
                data_type=data_type,
                nullable=bool(is_nullable),
                comment=comment,
            )
        )

    return [
        TableMetadata(
            name=table_name,
            comment=comment,
            columns=columns_by_table.get(table_name, []),
            row_count=_count_rows(connection, table_name),
        )
        for table_name, comment in table_rows
    ]


def _count_rows(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    quoted_table_name = _quote_identifier(table_name)
    row = connection.execute(f"SELECT COUNT(*) FROM {quoted_table_name}").fetchone()
    if row is None:
        msg = f"Could not count rows for table {table_name}"
        raise RuntimeError(msg)
    return int(row[0])


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'
