from __future__ import annotations

from typing import Any, Literal, TypedDict

CriticDecision = Literal[
    "ACCEPT", "REGENERATE_SQL", "RETRIEVE_MORE_CONTEXT", "PROFILE_VALUES", "ABORT"
]
RunStatus = Literal["SUCCESS", "ERROR", "CORRECT_REJECTION"]

type AnalysisPlan = dict[str, Any]


class TraceState(TypedDict):
    llm_calls: int
    mcp_calls: int
    sql_executions: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    runtime_seconds: float
    retrieved_tables: list[str]
    profiling_calls: int
    critic_calls: int
    critic_llm_calls: int
    critic_input_tokens: int | None
    critic_output_tokens: int | None
    critic_total_tokens: int | None
    sql_stage_llm_calls: int
    sql_stage_mcp_calls: int
    sql_stage_sql_executions: int
    sql_stage_input_tokens: int | None
    sql_stage_output_tokens: int | None
    sql_stage_total_tokens: int | None
    sql_stage_runtime_seconds: float
    answer_synthesis_llm_calls: int
    answer_synthesis_input_tokens: int | None
    answer_synthesis_output_tokens: int | None
    answer_synthesis_total_tokens: int | None
    answer_synthesis_runtime_seconds: float
    end_to_end_llm_calls: int
    end_to_end_total_tokens: int | None
    end_to_end_runtime_seconds: float


class RunnerResult(TypedDict):
    system: Literal["B", "C"]
    status: RunStatus
    question: str
    first_generated_sql: str | None
    final_generated_sql: str | None
    final_answer: str
    execution_result: Any | None
    last_error: str | None
    error_history: list[str]
    iterations: int
    critic_calls: int
    trace: TraceState


class RunnerEvent(TypedDict):
    event_type: Literal["node", "final"]
    node: str | None
    update: dict[str, Any]
    result: RunnerResult | None
