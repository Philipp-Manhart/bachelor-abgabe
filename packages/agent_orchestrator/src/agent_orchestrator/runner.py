from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Literal

from agent_orchestrator.graphs import (
    build_mcp_critic_graph,
    build_mcp_single_shot_graph,
)
from agent_orchestrator.nodes import OrchestratorDependencies, default_dependencies
from agent_orchestrator.state import AgentState, copy_trace, initial_state, state_int
from agent_orchestrator.types import RunnerEvent, RunnerResult, RunStatus


def run_mcp_single_shot(question: str, max_iterations: int = 0) -> RunnerResult:
    dependencies = default_dependencies()
    try:
        graph = build_mcp_single_shot_graph(dependencies)
        return _run_graph("B", graph, question, max_iterations)
    finally:
        dependencies.mcp.close()


def run_mcp_critic(question: str, max_iterations: int = 3) -> RunnerResult:
    dependencies = default_dependencies()
    try:
        graph = build_mcp_critic_graph(dependencies)
        return _run_graph("C", graph, question, max_iterations)
    finally:
        dependencies.mcp.close()


def stream_mcp_single_shot(question: str, max_iterations: int = 0) -> Iterator[RunnerEvent]:
    dependencies = default_dependencies()
    try:
        graph = build_mcp_single_shot_graph(dependencies)
        yield from _stream_graph("B", graph, question, max_iterations)
    finally:
        dependencies.mcp.close()


def stream_mcp_critic(question: str, max_iterations: int = 3) -> Iterator[RunnerEvent]:
    dependencies = default_dependencies()
    try:
        graph = build_mcp_critic_graph(dependencies)
        yield from _stream_graph("C", graph, question, max_iterations)
    finally:
        dependencies.mcp.close()


def stream_mcp_single_shot_with_dependencies(
    question: str,
    deps: OrchestratorDependencies,
    max_iterations: int = 0,
) -> Iterator[RunnerEvent]:
    graph = build_mcp_single_shot_graph(deps)
    yield from _stream_graph("B", graph, question, max_iterations)


def stream_mcp_critic_with_dependencies(
    question: str,
    deps: OrchestratorDependencies,
    max_iterations: int = 3,
) -> Iterator[RunnerEvent]:
    graph = build_mcp_critic_graph(deps)
    yield from _stream_graph("C", graph, question, max_iterations)


def run_mcp_single_shot_with_dependencies(
    question: str,
    deps: OrchestratorDependencies,
    max_iterations: int = 0,
) -> RunnerResult:
    graph = build_mcp_single_shot_graph(deps)
    return _run_graph("B", graph, question, max_iterations)


def run_mcp_critic_with_dependencies(
    question: str,
    deps: OrchestratorDependencies,
    max_iterations: int = 3,
) -> RunnerResult:
    graph = build_mcp_critic_graph(deps)
    return _run_graph("C", graph, question, max_iterations)


def _run_graph(
    system: Literal["B", "C"],
    graph,
    question: str,
    max_iterations: int,
) -> RunnerResult:
    started_at = time.perf_counter()
    state = initial_state(question, max_iterations) | {"started_at_monotonic": started_at}
    try:
        final_state = graph.invoke(state)
    except Exception as exc:
        final_state = state | {
            "last_error": f"GRAPH_FAILED: {exc}",
            "error_history": [*state.get("error_history", []), f"GRAPH_FAILED: {exc}"],
            "final_answer": f"Die Anfrage konnte nicht erfolgreich ausgeführt werden: {exc}",
        }

    final_state = _with_runtime(final_state, started_at)
    return _format_result(system, final_state)


def _stream_graph(
    system: Literal["B", "C"],
    graph,
    question: str,
    max_iterations: int,
) -> Iterator[RunnerEvent]:
    started_at = time.perf_counter()
    state = initial_state(question, max_iterations) | {"started_at_monotonic": started_at}
    try:
        for chunk in graph.stream(state, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                state = state | update
                yield {
                    "event_type": "node",
                    "node": str(node),
                    "update": update,
                    "result": None,
                }
    except Exception as exc:
        state = state | {
            "last_error": f"GRAPH_FAILED: {exc}",
            "error_history": [*state.get("error_history", []), f"GRAPH_FAILED: {exc}"],
            "final_answer": f"Die Anfrage konnte nicht erfolgreich ausgeführt werden: {exc}",
        }

    final_state = _with_runtime(state, started_at)
    yield {
        "event_type": "final",
        "node": None,
        "update": {},
        "result": _format_result(system, final_state),
    }


def _with_runtime(state: AgentState, started_at: float) -> AgentState:
    trace = copy_trace(state)
    trace["runtime_seconds"] = round(time.perf_counter() - started_at, 6)
    return state | {"trace": _with_phase_metrics(trace, state)}


def _format_result(system: Literal["B", "C"], state: AgentState) -> RunnerResult:
    return {
        "system": system,
        "status": _status_for_state(state),
        "question": state.get("user_question", ""),
        "first_generated_sql": state.get("first_generated_sql"),
        "final_generated_sql": state.get("generated_sql"),
        "final_answer": state.get("final_answer") or "",
        "execution_result": state.get("execution_result"),
        "last_error": state.get("last_error"),
        "error_history": list(state.get("error_history") or []),
        "iterations": state_int(state, "iteration_count"),
        "max_iterations": state_int(state, "max_iterations"),
        "trace": copy_trace(state),
        "critic_calls": copy_trace(state)["critic_calls"],
        "analysis_plan": state.get("analysis_plan") or {},
        "metadata_context": state.get("metadata_context") or {},
        "profiling_observations": state.get("profiling_observations") or {},
        "critic_decision": state.get("critic_decision"),
    }


def _with_phase_metrics(trace: dict[str, object], state: AgentState) -> dict[str, object]:
    sql_stage_trace = copy_trace({"trace": state.get("sql_stage_trace") or {}})
    if not state.get("sql_stage_trace"):
        sql_stage_trace = copy_trace({"trace": trace})
    answer_input_tokens = _phase_delta(trace, sql_stage_trace, "input_tokens")
    answer_output_tokens = _phase_delta(trace, sql_stage_trace, "output_tokens")
    answer_total_tokens = _phase_delta(trace, sql_stage_trace, "total_tokens")
    answer_llm_calls = _phase_delta(trace, sql_stage_trace, "llm_calls")
    trace.update(
        {
            "sql_stage_llm_calls": sql_stage_trace["llm_calls"],
            "sql_stage_mcp_calls": sql_stage_trace["mcp_calls"],
            "sql_stage_sql_executions": sql_stage_trace["sql_executions"],
            "sql_stage_input_tokens": sql_stage_trace["input_tokens"],
            "sql_stage_output_tokens": sql_stage_trace["output_tokens"],
            "sql_stage_total_tokens": sql_stage_trace["total_tokens"],
            "sql_stage_runtime_seconds": sql_stage_trace["runtime_seconds"],
            "answer_synthesis_llm_calls": answer_llm_calls,
            "answer_synthesis_input_tokens": answer_input_tokens,
            "answer_synthesis_output_tokens": answer_output_tokens,
            "answer_synthesis_total_tokens": answer_total_tokens,
            "answer_synthesis_runtime_seconds": max(
                0.0,
                float(trace["runtime_seconds"]) - float(sql_stage_trace["runtime_seconds"]),
            ),
            "end_to_end_llm_calls": trace["llm_calls"],
            "end_to_end_total_tokens": trace["total_tokens"],
            "end_to_end_runtime_seconds": trace["runtime_seconds"],
        }
    )
    return trace


def _phase_delta(
    end_to_end_trace: dict[str, object],
    sql_stage_trace: dict[str, object],
    key: str,
) -> int:
    end_value = end_to_end_trace.get(key)
    sql_value = sql_stage_trace.get(key)
    if not isinstance(end_value, int) or not isinstance(sql_value, int):
        return 0
    return max(0, end_value - sql_value)


def _status_for_state(state: AgentState) -> RunStatus:
    if state.get("last_error") == "UNANSWERABLE":
        return "CORRECT_REJECTION"
    if state.get("last_error"):
        return "ERROR"
    return "SUCCESS"
