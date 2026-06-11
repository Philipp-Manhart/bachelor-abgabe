from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from agent_orchestrator.nodes import OrchestratorDependencies, default_dependencies
from agent_orchestrator.nodes import (
    critic_reflection as critic_reflection_node,
)
from agent_orchestrator.nodes import (
    execute_sql as execute_sql_node,
)
from agent_orchestrator.nodes import (
    generate_sql as generate_sql_node,
)
from agent_orchestrator.nodes import (
    interpret_request as interpret_request_node,
)
from agent_orchestrator.nodes import (
    profile_data as profile_data_node,
)
from agent_orchestrator.nodes import (
    retrieve_context as retrieve_context_node,
)
from agent_orchestrator.nodes import (
    synthesize_answer as synthesize_answer_node,
)
from agent_orchestrator.nodes import (
    validate_sql as validate_sql_node,
)
from agent_orchestrator.state import AgentState, state_int

Route = Literal[
    "validate_sql",
    "execute_sql",
    "critic_reflection",
    "generate_sql",
    "retrieve_context",
    "profile_data",
    "synthesize_answer",
]


def build_mcp_single_shot_graph(deps: OrchestratorDependencies | None = None):
    dependencies = deps or default_dependencies()
    graph: Any = StateGraph(AgentState)
    _add_common_nodes(graph, dependencies)

    graph.add_edge(START, "interpret_request")
    graph.add_edge("interpret_request", "retrieve_context")
    graph.add_edge("retrieve_context", "profile_data")
    graph.add_edge("profile_data", "generate_sql")
    graph.add_conditional_edges(
        "generate_sql",
        route_after_generation,
        {"validate_sql": "validate_sql", "synthesize_answer": "synthesize_answer"},
    )
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validation_single_shot,
        {"execute_sql": "execute_sql", "synthesize_answer": "synthesize_answer"},
    )
    graph.add_edge("execute_sql", "synthesize_answer")
    graph.add_edge("synthesize_answer", END)
    return graph.compile()


def build_mcp_critic_graph(deps: OrchestratorDependencies | None = None):
    dependencies = deps or default_dependencies()
    graph: Any = StateGraph(AgentState)
    _add_common_nodes(graph, dependencies)

    graph.add_edge(START, "interpret_request")
    graph.add_edge("interpret_request", "retrieve_context")
    graph.add_edge("retrieve_context", "profile_data")
    graph.add_edge("profile_data", "generate_sql")
    graph.add_conditional_edges(
        "generate_sql",
        route_after_generation_critic,
        {
            "validate_sql": "validate_sql",
            "critic_reflection": "critic_reflection",
            "synthesize_answer": "synthesize_answer",
        },
    )
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validation,
        {
            "execute_sql": "execute_sql",
            "critic_reflection": "critic_reflection",
            "synthesize_answer": "synthesize_answer",
        },
    )
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execution,
        {"critic_reflection": "critic_reflection", "synthesize_answer": "synthesize_answer"},
    )
    graph.add_conditional_edges(
        "critic_reflection",
        route_after_critic,
        {
            "generate_sql": "generate_sql",
            "retrieve_context": "retrieve_context",
            "profile_data": "profile_data",
            "synthesize_answer": "synthesize_answer",
        },
    )
    graph.add_edge("synthesize_answer", END)
    return graph.compile()


def route_after_generation(state: AgentState) -> Route:
    if state.get("last_error") == "UNANSWERABLE" or not state.get("generated_sql"):
        return "synthesize_answer"
    return "validate_sql"


def route_after_generation_critic(state: AgentState) -> Route:
    if state.get("last_error") == "UNANSWERABLE" or not state.get("generated_sql"):
        if _iterations_left(state):
            return "critic_reflection"
        return "synthesize_answer"
    return "validate_sql"


def route_after_validation_single_shot(state: AgentState) -> Route:
    result = state.get("validation_result") or {}
    if result.get("ok") is True:
        return "execute_sql"
    return "synthesize_answer"


def route_after_validation(state: AgentState) -> Route:
    result = state.get("validation_result") or {}
    if result.get("ok") is True:
        return "execute_sql"
    if _iterations_left(state):
        return "critic_reflection"
    return "synthesize_answer"


def route_after_execution(state: AgentState) -> Route:
    if state.get("last_error"):
        if _iterations_left(state):
            return "critic_reflection"
        return "synthesize_answer"
    if state.get("execution_result"):
        return "critic_reflection"
    return "synthesize_answer"


def route_after_critic(state: AgentState) -> Route:
    decision = state.get("critic_decision")
    if decision == "ACCEPT":
        return "synthesize_answer"
    if decision == "REGENERATE_SQL":
        return (
            "generate_sql" if _repair_budget_consumed_within_limit(state) else "synthesize_answer"
        )
    if decision == "RETRIEVE_MORE_CONTEXT":
        return (
            "retrieve_context"
            if _repair_budget_consumed_within_limit(state)
            else "synthesize_answer"
        )
    if decision == "PROFILE_VALUES":
        return (
            "profile_data" if _repair_budget_consumed_within_limit(state) else "synthesize_answer"
        )
    return "synthesize_answer"


def _iterations_left(state: AgentState) -> bool:
    return state_int(state, "iteration_count") < state_int(state, "max_iterations")


def _repair_budget_consumed_within_limit(state: AgentState) -> bool:
    max_iterations = state_int(state, "max_iterations")
    return max_iterations > 0 and state_int(state, "iteration_count") <= max_iterations


def _add_common_nodes(
    graph: Any,
    deps: OrchestratorDependencies,
) -> None:
    graph.add_node("interpret_request", _bind(interpret_request_node, deps))
    graph.add_node("retrieve_context", _bind(retrieve_context_node, deps))
    graph.add_node("profile_data", _bind(profile_data_node, deps))
    graph.add_node("generate_sql", _bind(generate_sql_node, deps))
    graph.add_node("validate_sql", _bind(validate_sql_node, deps))
    graph.add_node("execute_sql", _bind(execute_sql_node, deps))
    graph.add_node("critic_reflection", _bind(critic_reflection_node, deps))
    graph.add_node("synthesize_answer", _bind(synthesize_answer_node, deps))


def _bind(
    node: Callable[[AgentState, OrchestratorDependencies], dict[str, Any]],
    deps: OrchestratorDependencies,
) -> Callable[[AgentState], dict[str, Any]]:
    def bound(state: AgentState) -> dict[str, Any]:
        return node(state, deps)

    return bound
