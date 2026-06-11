from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from agent_orchestrator.types import AnalysisPlan, TraceState

TraceCounterKey = Literal[
    "llm_calls",
    "mcp_calls",
    "sql_executions",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "profiling_calls",
    "critic_calls",
    "critic_llm_calls",
    "critic_input_tokens",
    "critic_output_tokens",
    "critic_total_tokens",
    "sql_stage_llm_calls",
    "sql_stage_mcp_calls",
    "sql_stage_sql_executions",
    "sql_stage_input_tokens",
    "sql_stage_output_tokens",
    "sql_stage_total_tokens",
    "answer_synthesis_llm_calls",
    "answer_synthesis_input_tokens",
    "answer_synthesis_output_tokens",
    "answer_synthesis_total_tokens",
    "end_to_end_llm_calls",
    "end_to_end_total_tokens",
]


class AgentState(TypedDict, total=False):
    user_question: str
    analysis_plan: AnalysisPlan
    metadata_context: dict[str, Any]
    profiling_observations: dict[str, Any]
    generated_sql: str | None
    first_generated_sql: str | None
    validation_result: dict[str, Any] | None
    execution_result: Any | None
    last_error: str | None
    last_error_details: dict[str, Any] | None
    error_history: list[str]
    iteration_count: int
    max_iterations: int
    started_at_monotonic: float
    critic_decision: str | None
    final_answer: str | None
    chart_config: dict[str, Any] | None
    sql_stage_trace: TraceState | None
    trace: TraceState


def initial_trace() -> TraceState:
    return {
        "llm_calls": 0,
        "mcp_calls": 0,
        "sql_executions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "runtime_seconds": 0.0,
        "retrieved_tables": [],
        "profiling_calls": 0,
        "critic_calls": 0,
        "critic_llm_calls": 0,
        "critic_input_tokens": 0,
        "critic_output_tokens": 0,
        "critic_total_tokens": 0,
        "sql_stage_llm_calls": 0,
        "sql_stage_mcp_calls": 0,
        "sql_stage_sql_executions": 0,
        "sql_stage_input_tokens": 0,
        "sql_stage_output_tokens": 0,
        "sql_stage_total_tokens": 0,
        "sql_stage_runtime_seconds": 0.0,
        "answer_synthesis_llm_calls": 0,
        "answer_synthesis_input_tokens": 0,
        "answer_synthesis_output_tokens": 0,
        "answer_synthesis_total_tokens": 0,
        "answer_synthesis_runtime_seconds": 0.0,
        "end_to_end_llm_calls": 0,
        "end_to_end_total_tokens": 0,
        "end_to_end_runtime_seconds": 0.0,
    }


def initial_state(question: str, max_iterations: int) -> AgentState:
    return {
        "user_question": question,
        "analysis_plan": {},
        "metadata_context": {},
        "profiling_observations": {},
        "generated_sql": None,
        "first_generated_sql": None,
        "validation_result": None,
        "execution_result": None,
        "last_error": None,
        "last_error_details": None,
        "error_history": [],
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "started_at_monotonic": 0.0,
        "critic_decision": None,
        "final_answer": None,
        "chart_config": None,
        "sql_stage_trace": None,
        "trace": initial_trace(),
    }


def copy_trace(state: AgentState) -> TraceState:
    return cast(TraceState, initial_trace() | dict(state.get("trace") or {}))


def append_error(state: AgentState, error: str) -> list[str]:
    history = list(state.get("error_history") or [])
    history.append(error)
    return history


def merge_trace(state: AgentState, **increments: int) -> TraceState:
    trace = copy_trace(state)
    for key, increment in increments.items():
        counter_key = cast(TraceCounterKey, key)
        trace[counter_key] = trace_int(trace, counter_key) + increment
    return cast(TraceState, trace)


def merge_token_usage(state: AgentState, usage: dict[str, int | None]) -> TraceState:
    trace = copy_trace(state)
    token_fields: tuple[tuple[TraceCounterKey, str], ...] = (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    )
    for trace_key, usage_key in token_fields:
        value = usage.get(usage_key)
        if value is not None:
            trace[trace_key] = trace_int(trace, trace_key) + value
    trace["llm_calls"] = trace_int(trace, "llm_calls") + 1
    return cast(TraceState, trace)


def trace_int(trace: TraceState, key: TraceCounterKey) -> int:
    value = trace[key]
    return value if isinstance(value, int) else 0


def state_int(
    state: AgentState, key: Literal["iteration_count", "max_iterations", "critic_calls"]
) -> int:
    value = state.get(key)
    return value if isinstance(value, int) else 0
