from __future__ import annotations

from pathlib import Path

import duckdb

from mcp_server import (
    CategoricalValuesRequest,
    ChartConfigRequest,
    DatabaseSettings,
    ExecuteSqlRequest,
    NumericSummaryRequest,
    SampleDataRequest,
    ValidateSqlRequest,
    execute_sql,
    generate_chart_config,
    get_categorical_values,
    get_numeric_summary,
    get_sample_data,
    validate_sql,
)


def test_data_profiling_tools_return_json_safe_context(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE tool_table (
                id INTEGER,
                category VARCHAR,
                amount DECIMAL(10, 2),
                event_date DATE
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tool_table VALUES
                (1, 'active', 10.50, DATE '2026-01-01'),
                (2, 'closed', 20.00, DATE '2026-01-02'),
                (3, 'active', NULL, NULL)
            """
        )

    settings = DatabaseSettings.from_path(database_path)

    sample = get_sample_data(settings, SampleDataRequest(table_name="tool_table", limit=2))
    assert sample == [
        {"id": 1, "category": "active", "amount": 10.5, "event_date": "2026-01-01"},
        {"id": 2, "category": "closed", "amount": 20.0, "event_date": "2026-01-02"},
    ]

    categories = get_categorical_values(
        settings,
        CategoricalValuesRequest(table_name="tool_table", column="category"),
    )
    assert categories == ["active", "closed"]

    numeric_summary = get_numeric_summary(
        settings,
        NumericSummaryRequest(table_name="tool_table", column="amount"),
    )
    assert numeric_summary.min == 10.5
    assert numeric_summary.max == 20.0
    assert numeric_summary.avg == 15.25
    assert numeric_summary.null_count == 1

    date_summary = get_numeric_summary(
        settings,
        NumericSummaryRequest(table_name="tool_table", column="event_date"),
    )
    assert date_summary.min == "2026-01-01"
    assert date_summary.max == "2026-01-02"
    assert date_summary.avg is None
    assert date_summary.null_count == 1


def test_validate_and_execute_sql_tools_keep_select_only_boundary(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE TABLE tool_table (id INTEGER, amount DECIMAL(10, 2), event_date DATE)"
        )
        connection.execute(
            "INSERT INTO tool_table VALUES (1, 10.50, DATE '2026-01-01'), (2, 20.00, NULL)"
        )

    settings = DatabaseSettings.from_path(database_path)

    valid = validate_sql(settings, ValidateSqlRequest(query="SELECT id FROM tool_table"))
    assert valid.valid is True

    invalid = validate_sql(settings, ValidateSqlRequest(query="DROP TABLE tool_table"))
    assert invalid.valid is False
    assert invalid.error is not None
    assert invalid.error.error_type == "UnsafeSqlError"

    result = execute_sql(
        settings,
        ExecuteSqlRequest(sql="SELECT id, amount, event_date FROM tool_table ORDER BY id"),
    )
    assert result.success is True
    assert result.rows == [[1, 10.5, "2026-01-01"], [2, 20.0, None]]


def test_generate_chart_config_returns_frontend_configuration() -> None:
    config = generate_chart_config(
        ChartConfigRequest(type="bar", x_axis="category", y_axis="contract_count")
    )

    assert config.model_dump() == {
        "mark": "bar",
        "encoding": {
            "x": {"field": "category", "type": "nominal"},
            "y": {"field": "contract_count", "type": "quantitative"},
        },
    }
