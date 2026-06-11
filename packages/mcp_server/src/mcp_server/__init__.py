from mcp_server.charting import generate_chart_config
from mcp_server.db import DatabaseConfig, DuckDBConnection
from mcp_server.models import (
    CategoricalValuesRequest,
    ChartConfig,
    ChartConfigRequest,
    ColumnMetadata,
    DatabaseSettings,
    ExecuteSqlRequest,
    ExecuteSqlResult,
    NumericSummaryRequest,
    NumericSummaryResult,
    SampleDataRequest,
    SchemaMetadata,
    SchemaResponse,
    SqlExecutionError,
    TableMetadata,
    ValidateSqlRequest,
    ValidateSqlResult,
)
from mcp_server.profiling import get_categorical_values, get_numeric_summary, get_sample_data
from mcp_server.prompts import (
    BI_EDA_WORKFLOW_PROMPT,
    CHART_DECISION_RULES_PROMPT,
    CRITIC_REFLECTION_RULES_PROMPT,
    SQL_GENERATION_RULES_PROMPT,
    bi_eda_workflow,
    chart_decision_rules,
    critic_reflection_rules,
    sql_generation_rules,
)
from mcp_server.resources import (
    get_business_glossary,
    get_business_glossary_term,
    get_schema_overview,
    get_schema_relationships,
    get_table_dictionary,
)
from mcp_server.schema import format_schema_context, get_schema
from mcp_server.sql import execute_sql, validate_sql

__all__ = [
    "BI_EDA_WORKFLOW_PROMPT",
    "CHART_DECISION_RULES_PROMPT",
    "CRITIC_REFLECTION_RULES_PROMPT",
    "SERVER_INSTRUCTIONS",
    "SERVER_NAME",
    "SQL_GENERATION_RULES_PROMPT",
    "CategoricalValuesRequest",
    "ChartConfig",
    "ChartConfigRequest",
    "ColumnMetadata",
    "DatabaseConfig",
    "DatabaseSettings",
    "DuckDBConnection",
    "ExecuteSqlRequest",
    "ExecuteSqlResult",
    "NumericSummaryRequest",
    "NumericSummaryResult",
    "SampleDataRequest",
    "SchemaMetadata",
    "SchemaResponse",
    "SqlExecutionError",
    "TableMetadata",
    "ValidateSqlRequest",
    "ValidateSqlResult",
    "bi_eda_workflow",
    "chart_decision_rules",
    "create_server",
    "critic_reflection_rules",
    "execute_sql",
    "format_schema_context",
    "generate_chart_config",
    "get_business_glossary",
    "get_business_glossary_term",
    "get_categorical_values",
    "get_numeric_summary",
    "get_sample_data",
    "get_schema",
    "get_schema_overview",
    "get_schema_relationships",
    "get_table_dictionary",
    "sql_generation_rules",
    "validate_sql",
]


def __getattr__(name: str) -> object:
    if name in {"SERVER_INSTRUCTIONS", "SERVER_NAME", "create_server"}:
        from mcp_server import server

        return getattr(server, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
