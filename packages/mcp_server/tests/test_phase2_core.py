from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from mcp_server import (
    DatabaseSettings,
    DuckDBConnection,
    ExecuteSqlRequest,
    ExecuteSqlResult,
    SqlExecutionError,
    execute_sql,
    get_schema,
)


@pytest.fixture
def warehouse_path(tmp_path: Path) -> Path:
    project_root = Path(__file__).resolve().parents[3]
    schema_sql = (project_root / "database" / "schema.sql").read_text(encoding="utf-8")
    database_path = tmp_path / "warehouse.duckdb"

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(schema_sql)

    return database_path


def test_connection_opens_existing_database(warehouse_path: Path) -> None:
    settings = DatabaseSettings.from_path(warehouse_path)

    with DuckDBConnection(settings) as connection:
        result = connection.execute("SELECT 1").fetchone()

    assert result == (1,)


def test_connection_rejects_missing_database(tmp_path: Path) -> None:
    settings = DatabaseSettings.from_path(tmp_path / "missing.duckdb")

    with pytest.raises(FileNotFoundError), DuckDBConnection(settings):
        pass


def test_pydantic_contracts_validate_sql_request_and_result_shape() -> None:
    request = ExecuteSqlRequest(sql="  SELECT 1  ")
    assert request.sql == "SELECT 1"

    with pytest.raises(ValidationError):
        ExecuteSqlRequest(sql="")

    error = SqlExecutionError(error_type="ParserException", message="bad sql")
    failed_result = ExecuteSqlResult(success=False, error=error)
    assert failed_result.error == error

    with pytest.raises(ValidationError):
        ExecuteSqlResult(success=False)

    with pytest.raises(ValidationError):
        ExecuteSqlResult(success=True, error=error)


def test_get_schema_returns_comments_columns_and_context(warehouse_path: Path) -> None:
    response = get_schema(DatabaseSettings.from_path(warehouse_path))
    tables = {table.name: table for table in response.metadata.tables}

    assert "dim_customer" in tables
    assert tables["dim_customer"].comment
    assert tables["dim_customer"].row_count == 0

    columns = {column.name: column for column in tables["dim_customer"].columns}
    assert columns["customer_id"].data_type == "VARCHAR"
    assert columns["customer_id"].comment
    assert "Table: dim_customer" in response.context
    assert "customer_id VARCHAR" in response.context


def test_execute_sql_returns_limited_rows_and_truncation(warehouse_path: Path) -> None:
    result = execute_sql(
        DatabaseSettings.from_path(warehouse_path),
        ExecuteSqlRequest(sql="SELECT * FROM range(5)", max_rows=2),
    )

    assert result.success is True
    assert result.columns == ["range"]
    assert result.rows == [[0], [1]]
    assert result.row_count == 2
    assert result.truncated is True
    assert result.elapsed_ms is not None


def test_execute_sql_returns_structured_duckdb_errors(warehouse_path: Path) -> None:
    result = execute_sql(
        DatabaseSettings.from_path(warehouse_path),
        ExecuteSqlRequest(sql="SELECT FROM missing_table"),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.error_type
    assert result.error.stacktrace


def test_execute_sql_blocks_unsafe_or_multiple_statements(warehouse_path: Path) -> None:
    settings = DatabaseSettings.from_path(warehouse_path)

    mutation = execute_sql(settings, ExecuteSqlRequest(sql="DROP TABLE dim_customer"))
    assert mutation.success is False
    assert mutation.error is not None
    assert mutation.error.error_type == "UnsafeSqlError"

    multiple = execute_sql(settings, ExecuteSqlRequest(sql="SELECT 1; SELECT 2"))
    assert multiple.success is False
    assert multiple.error is not None
    assert multiple.error.message == "Only a single SQL statement is allowed."


def test_execute_sql_does_not_block_keywords_inside_string_literals(warehouse_path: Path) -> None:
    result = execute_sql(
        DatabaseSettings.from_path(warehouse_path),
        ExecuteSqlRequest(sql="SELECT 'drop' AS keyword_text"),
    )

    assert result.success is True
    assert result.rows == [["drop"]]
