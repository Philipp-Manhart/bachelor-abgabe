from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from mcp_server import (
    DatabaseSettings,
    create_server,
    get_business_glossary,
    get_business_glossary_term,
    get_schema_overview,
    get_schema_relationships,
    get_table_dictionary,
)


@pytest.fixture
def documented_warehouse_path(tmp_path: Path) -> Path:
    database_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE dim_example (
                example_id INTEGER PRIMARY KEY,
                status_code VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE fact_example (
                fact_id INTEGER,
                example_id INTEGER,
                CONSTRAINT fk_fact_example_dim_example
                    FOREIGN KEY (example_id) REFERENCES dim_example(example_id)
            )
            """
        )
        connection.execute("COMMENT ON TABLE dim_example IS 'Example dimension table.'")
        connection.execute("COMMENT ON COLUMN dim_example.example_id IS 'Synthetic key.'")
        connection.execute("COMMENT ON COLUMN dim_example.status_code IS 'Business status code.'")
    return database_path


def test_schema_overview_resource_returns_tables_with_comments(
    documented_warehouse_path: Path,
) -> None:
    overview = get_schema_overview(DatabaseSettings.from_path(documented_warehouse_path))

    assert overview == [
        {
            "name": "dim_example",
            "comment": "Example dimension table.",
            "row_count": 0,
        },
        {
            "name": "fact_example",
            "comment": None,
            "row_count": 0,
        },
    ]


def test_table_dictionary_resource_returns_column_metadata(
    documented_warehouse_path: Path,
) -> None:
    dictionary = get_table_dictionary(
        DatabaseSettings.from_path(documented_warehouse_path),
        "dim_example",
    )

    assert dictionary["name"] == "dim_example"
    assert dictionary["comment"] == "Example dimension table."
    assert dictionary["columns"] == [
        {
            "name": "example_id",
            "data_type": "INTEGER",
            "nullable": False,
            "comment": "Synthetic key.",
        },
        {
            "name": "status_code",
            "data_type": "VARCHAR",
            "nullable": True,
            "comment": "Business status code.",
        },
    ]


def test_business_glossary_resource_returns_kpi_json() -> None:
    glossary = json.loads(get_business_glossary())

    assert "Stornoquote" in glossary
    assert "formula" in glossary["Stornoquote"]
    assert "Neugeschaeftsvolumen" in glossary
    assert "Cash Realization Rate" in glossary


def test_schema_relationships_resource_returns_foreign_keys(
    documented_warehouse_path: Path,
) -> None:
    relationships = get_schema_relationships(DatabaseSettings.from_path(documented_warehouse_path))

    assert relationships == [
        {
            "from_table": "fact_example",
            "from_columns": ["example_id"],
            "to_table": "dim_example",
            "to_columns": ["example_id"],
            "constraint_name": "fact_example_example_id_example_id_fkey",
        }
    ]


def test_business_glossary_term_resource_returns_matching_kpi() -> None:
    glossary = get_business_glossary_term("cancelled contract share")

    assert list(glossary) == ["Stornoquote"]
    assert "formula" in glossary["Stornoquote"]


def test_business_glossary_term_resource_searches_aliases() -> None:
    glossary = get_business_glossary_term("ueberfinanzierung")

    assert list(glossary) == ["High-LTV Exposure"]
    assert "loan_to_value_effective > 0.8" in glossary["High-LTV Exposure"]["formula"]


def test_business_glossary_term_resource_returns_business_customer_semantics() -> None:
    glossary = get_business_glossary_term("business customer")

    assert list(glossary) == ["Business Customer"]
    assert "Corporate" in glossary["Business Customer"]["formula"]


def test_business_glossary_term_resource_returns_overdraft_run_semantics() -> None:
    glossary = get_business_glossary_term("longest overdraft run")

    assert list(glossary) == ["Overdraft Run"]
    assert "available_balance_effective < 0" in glossary["Overdraft Run"]["notes"]


def test_business_glossary_term_resource_returns_customer_risk_semantics() -> None:
    glossary = get_business_glossary_term("riskiest customer class")

    assert list(glossary) == ["Customer Risk Class"]
    assert "A, B, C, D, and E" in glossary["Customer Risk Class"]["notes"]


def test_business_glossary_term_resource_returns_late_installment_semantics() -> None:
    glossary = get_business_glossary_term("paid more than 15 days late")

    assert list(glossary) == ["Late Lease Installment"]
    assert "value_date_sk" in glossary["Late Lease Installment"]["date_basis"]


@pytest.mark.anyio
async def test_fastmcp_resource_primitives_read_discovery_content(
    documented_warehouse_path: Path,
) -> None:
    server = create_server(DatabaseSettings.from_path(documented_warehouse_path))

    resources = await server.get_resources()
    overview_text = await resources["dwh://schema/overview"].read()
    assert json.loads(overview_text)[0]["name"] == "dim_example"

    glossary_text = await resources["dwh://business_glossary"].read()
    assert "Stornoquote" in json.loads(glossary_text)

    relationships_text = await resources["dwh://schema/relationships"].read()
    assert json.loads(relationships_text)[0]["to_table"] == "dim_example"

    templates = await server.get_resource_templates()
    table_template = templates["dwh://schema/tables/{name}"]
    params = table_template.matches("dwh://schema/tables/dim_example")
    assert params == {"name": "dim_example"}

    table_resource = await table_template.create_resource(
        "dwh://schema/tables/dim_example",
        params,
    )
    table_text = await table_resource.read()
    assert json.loads(table_text)["columns"][0]["comment"] == "Synthetic key."

    glossary_template = templates["dwh://business_glossary/{term}"]
    glossary_params = glossary_template.matches("dwh://business_glossary/cancelled contract share")
    assert glossary_params == {"term": "cancelled contract share"}

    glossary_resource = await glossary_template.create_resource(
        "dwh://business_glossary/cancelled contract share",
        glossary_params,
    )
    term_text = await glossary_resource.read()
    assert list(json.loads(term_text)) == ["Stornoquote"]
