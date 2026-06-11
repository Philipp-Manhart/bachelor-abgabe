from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from fastmcp import Client

from mcp_server import DatabaseSettings
from mcp_server.server import create_server


@pytest.mark.anyio
async def test_mcp_client_smoke_interacts_with_server_primitives(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE smoke_table (
                id INTEGER,
                status_code VARCHAR
            )
            """
        )
        connection.execute("INSERT INTO smoke_table VALUES (1, 'ACTIVE')")
        connection.execute("COMMENT ON TABLE smoke_table IS 'MCP smoke-test table.'")
        connection.execute("COMMENT ON COLUMN smoke_table.id IS 'Synthetic identifier.'")

    server = create_server(DatabaseSettings.from_path(database_path))

    async with Client(server) as client:
        await client.ping()

        tools = {tool.name for tool in await client.list_tools()}
        assert {"execute_sql", "get_sample_data", "validate_sql"} <= tools

        resources = {str(resource.uri) for resource in await client.list_resources()}
        assert {"dwh://business_glossary", "dwh://schema/overview"} <= resources

        resource_templates = {
            template.uriTemplate for template in await client.list_resource_templates()
        }
        assert "dwh://schema/tables/{name}" in resource_templates

        overview = await client.read_resource("dwh://schema/overview")
        assert json.loads(overview[0].text)[0]["name"] == "smoke_table"

        table_dictionary = await client.read_resource("dwh://schema/tables/smoke_table")
        assert json.loads(table_dictionary[0].text)["columns"][0]["comment"] == (
            "Synthetic identifier."
        )

        query_result = await client.call_tool(
            "execute_sql",
            {"query": "SELECT id FROM smoke_table"},
        )
        assert json.loads(query_result[0].text)["rows"] == [[1]]

        prompt = await client.get_prompt("bi_eda_workflow")
        assert "Discovery" in prompt[0].content.text
