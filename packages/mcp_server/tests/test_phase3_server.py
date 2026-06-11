import pytest
from fastmcp import FastMCP

from mcp_server import SERVER_INSTRUCTIONS, SERVER_NAME, create_server


@pytest.mark.anyio
async def test_create_server_initializes_fastmcp_with_tool_primitives() -> None:
    server = create_server()

    assert isinstance(server, FastMCP)
    assert server.name == SERVER_NAME
    assert server.instructions == SERVER_INSTRUCTIONS

    assert set(await server.get_resources()) == {
        "dwh://business_glossary",
        "dwh://schema/relationships",
        "dwh://schema/overview",
    }
    assert set(await server.get_resource_templates()) == {
        "dwh://business_glossary/{term}",
        "dwh://schema/tables/{name}",
    }

    assert set(await server.get_tools()) == {
        "execute_sql",
        "generate_chart_config",
        "get_categorical_values",
        "get_numeric_summary",
        "get_sample_data",
        "validate_sql",
    }

    assert set(await server.get_prompts()) == {
        "bi_eda_workflow",
        "chart_decision_rules",
        "critic_reflection_rules",
        "sql_generation_rules",
    }


@pytest.mark.anyio
async def test_prompt_primitives_render_methodological_instructions() -> None:
    prompts = await create_server().get_prompts()

    eda_messages = await prompts["bi_eda_workflow"].render()
    eda_text = eda_messages[0].content.text
    assert "Discovery" in eda_text
    assert "Profiling" in eda_text
    assert "categorical filters or rankings" in eda_text
    assert "status, rating, type, class, code, flag" in eda_text
    assert "validate_sql before execute_sql" in eda_text

    sql_messages = await prompts["sql_generation_rules"].render()
    sql_text = sql_messages[0].content.text
    assert "verified MCP context" in sql_text
    assert "Do not assume table names" in sql_text
    assert "Apply known business glossary semantics before considering refusal" in sql_text
    assert "non-reversed payment transactions" in sql_text
    assert "loan book" in sql_text
    assert "final SELECT must project only" in sql_text
    assert "deterministic secondary ORDER" in sql_text
    assert "displayed text or identifier dimensions in ascending order" in sql_text
    assert "plain list without a metric" in sql_text
    assert "Return exactly UNANSWERABLE" in sql_text
    assert "with no surrounding prose or Markdown" in sql_text
    assert "SELECT and WITH" in sql_text

    critic_messages = await prompts["critic_reflection_rules"].render()
    critic_text = critic_messages[0].content.text
    assert "error log as the primary evidence" in critic_text
    assert "reinterpret" in critic_text
    assert "business question" in critic_text

    chart_messages = await prompts["chart_decision_rules"].render()
    chart_text = chart_messages[0].content.text
    assert "line charts for time series" in chart_text
    assert "bar charts for categorical comparisons" in chart_text
