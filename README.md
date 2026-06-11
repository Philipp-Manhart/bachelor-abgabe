# Agentic Text-to-SQL via MCP

Prototype for a bachelor thesis evaluating a LangGraph Text-to-SQL system with
FastMCP, LiteLLM and DuckDB. All included banking data is synthetic and contains
no real customer information.

## Structure

- `packages/mcp_server`: MCP resources, tools, prompts and DuckDB access
- `packages/agent_orchestrator`: LangGraph generator, executor and critic loop
- `packages/evaluation`: benchmark runner, metrics and plots
- `packages/frontend`: Streamlit demo
- `database`: schema, synthetic data generator and benchmark questions

## Setup

Requires Python 3.14 and `uv`.

```bash
uv sync
cp .env.example .env
uv run database/generate_data.py demo
```

Start the MCP server:

```bash
MCP_TRANSPORT=sse uv run --package mcp-server python -m mcp_server.server
```

In another terminal, run the demo or evaluation:

```bash
uv run --package frontend streamlit run packages/frontend/src/frontend/app.py
uv run --package evaluation python -m evaluation.benchmark.runner \
  --questions database/test_queries.csv \
  --systems A,B,C \
  --max-iterations 3 \
  --seed 42 \
  --output evaluation_results/benchmark
```

The client uses `http://127.0.0.1:8000/sse` by default. Configure another endpoint
with `MCP_SERVER_URL`.

## Quality Checks

```bash
uv run ruff format .
uv run ruff check .
uv run --package evaluation pytest
```
