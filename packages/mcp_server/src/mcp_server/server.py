from __future__ import annotations

import os
from functools import partial
from pathlib import Path

import anyio
from fastmcp import FastMCP

from mcp_server.charting import generate_chart_config as build_chart_config
from mcp_server.models import (
    CategoricalValuesRequest,
    ChartConfigRequest,
    DatabaseSettings,
    ExecuteSqlRequest,
    NumericSummaryRequest,
    SampleDataRequest,
    ValidateSqlRequest,
)
from mcp_server.profiling import (
    get_categorical_values as fetch_categorical_values,
)
from mcp_server.profiling import (
    get_numeric_summary as fetch_numeric_summary,
)
from mcp_server.profiling import (
    get_sample_data as fetch_sample_data,
)
from mcp_server.prompts import (
    bi_eda_workflow as build_bi_eda_workflow_prompt,
)
from mcp_server.prompts import (
    chart_decision_rules as build_chart_decision_rules_prompt,
)
from mcp_server.prompts import (
    critic_reflection_rules as build_critic_reflection_rules_prompt,
)
from mcp_server.prompts import (
    sql_generation_rules as build_sql_generation_rules_prompt,
)
from mcp_server.resources import get_business_glossary as read_business_glossary
from mcp_server.resources import get_business_glossary_term as read_business_glossary_term
from mcp_server.resources import get_schema_overview as read_schema_overview
from mcp_server.resources import get_schema_relationships as read_schema_relationships
from mcp_server.resources import get_table_dictionary as read_table_dictionary
from mcp_server.sql import execute_sql as run_sql
from mcp_server.sql import validate_sql as dry_run_sql

SERVER_NAME = "agentic-bi-duckdb"
SERVER_INSTRUCTIONS = (
    "MCP server for deterministic DuckDB schema inspection and SQL execution. "
    "Agentic reasoning, critic loops, and model decisions belong in the orchestrator."
)


def create_server(settings: DatabaseSettings | None = None) -> FastMCP:
    database_settings = settings or DatabaseSettings.from_path(_configured_database_path())
    server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
    )

    @server.tool()
    def get_sample_data(table_name: str, limit: int = 3) -> list[dict[str, object]]:
        request = SampleDataRequest(table_name=table_name, limit=limit)
        return fetch_sample_data(database_settings, request)

    @server.tool()
    def get_categorical_values(table_name: str, column: str) -> list[str]:
        request = CategoricalValuesRequest(table_name=table_name, column=column)
        return fetch_categorical_values(database_settings, request)

    @server.tool()
    def get_numeric_summary(table_name: str, column: str) -> dict[str, object]:
        request = NumericSummaryRequest(table_name=table_name, column=column)
        return fetch_numeric_summary(database_settings, request).model_dump(mode="json")

    @server.tool()
    def validate_sql(query: str) -> dict[str, object]:
        request = ValidateSqlRequest(query=query)
        return dry_run_sql(database_settings, request).model_dump(mode="json")

    @server.tool()
    def execute_sql(query: str) -> dict[str, object]:
        request = ExecuteSqlRequest(sql=query)
        return run_sql(database_settings, request).model_dump(mode="json")

    @server.tool()
    def generate_chart_config(type: str, x_axis: str, y_axis: str) -> dict[str, object]:
        request = ChartConfigRequest(type=type, x_axis=x_axis, y_axis=y_axis)
        return build_chart_config(request).model_dump(mode="json")

    @server.resource(
        "dwh://schema/overview",
        description="Lists DWH tables with table comments for semantic discovery.",
        mime_type="application/json",
    )
    def schema_overview() -> list[dict[str, object]]:
        return read_schema_overview(database_settings)

    @server.resource(
        "dwh://schema/tables/{name}",
        description="Returns a table-level data dictionary with columns, types, and comments.",
        mime_type="application/json",
    )
    def table_dictionary(name: str) -> dict[str, object]:
        return read_table_dictionary(database_settings, name)

    @server.resource(
        "dwh://schema/relationships",
        description="Lists primary-key and foreign-key relationships between DWH tables.",
        mime_type="application/json",
    )
    def schema_relationships() -> list[dict[str, object]]:
        return read_schema_relationships(database_settings)

    @server.resource(
        "dwh://business_glossary",
        description="Returns KPI definitions and calculation formulas for controlling metrics.",
        mime_type="application/json",
    )
    def business_glossary() -> str:
        return read_business_glossary()

    @server.resource(
        "dwh://business_glossary/{term}",
        description="Returns matching business terms, KPI definitions, and calculation formulas.",
        mime_type="application/json",
    )
    def business_glossary_term(term: str) -> dict[str, object]:
        return read_business_glossary_term(term)

    @server.prompt()
    def bi_eda_workflow() -> str:
        return build_bi_eda_workflow_prompt()

    @server.prompt()
    def sql_generation_rules() -> str:
        return build_sql_generation_rules_prompt()

    @server.prompt()
    def critic_reflection_rules() -> str:
        return build_critic_reflection_rules_prompt()

    @server.prompt()
    def chart_decision_rules() -> str:
        return build_chart_decision_rules_prompt()

    return server


def _configured_database_path() -> Path:
    configured_path = os.getenv("DUCKDB_DATABASE_PATH") or os.getenv("DATABASE_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return Path.cwd() / "database" / "benchmark.duckdb"


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        server = create_server()
        anyio.run(
            partial(
                server.run_async,
                "sse",
                host=os.getenv("MCP_HOST", "127.0.0.1"),
                port=int(os.getenv("MCP_PORT", "8000")),
            )
        )
        return
    create_server().run("stdio")


if __name__ == "__main__":
    main()
