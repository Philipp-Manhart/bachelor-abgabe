from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, cast

from agent_orchestrator.llm import LiteLlmClient, LlmClient
from agent_orchestrator.mcp_client import FastMcpClient, McpClient
from agent_orchestrator.state import (
    AgentState,
    append_error,
    copy_trace,
    merge_token_usage,
    merge_trace,
    state_int,
    trace_int,
)
from agent_orchestrator.types import AnalysisPlan, TraceState


@dataclass(frozen=True)
class OrchestratorDependencies:
    llm: LlmClient
    mcp: McpClient


StateUpdate = dict[str, Any]
MAX_RETRIEVED_TABLES = 6
MAX_PROFILE_COLUMNS_PER_TABLE = 2
CATEGORICAL_PROFILE_COLUMN_HINTS = (
    "code",
    "status",
    "type",
    "class",
    "rating",
    "flag",
    "channel",
    "region",
)
HIGH_CARDINALITY_COLUMN_HINTS = (
    "id",
    "sk",
    "name",
    "vin",
    "address",
    "postal",
    "email",
    "phone",
)
DOMAIN_TABLE_HINTS: dict[str, tuple[str, ...]] = {
    "fact_leasing_contracts": (
        "lease",
        "leasing",
        "mileage",
        "residual",
        "returned",
        "return",
        "early termination",
    ),
    "fact_loan_contracts": (
        "loan",
        "apr",
        "ltv",
        "principal",
        "financed",
        "financing",
        "interest rate",
    ),
    "fact_payment_transactions": (
        "payment",
        "paid",
        "received",
        "cash",
        "missed",
        "reversal",
        "settlement",
        "actual",
    ),
    "fact_contract_cashflows": (
        "cashflow",
        "cash flow",
        "installment",
        "planned",
        "due",
        "outstanding",
        "missed",
        "fee",
    ),
    "fact_banking_accounts": (
        "account",
        "balance",
        "overdraft",
        "blocked",
        "snapshot",
    ),
    "dim_customer": ("customer", "business", "private", "retail", "corporate", "risk class"),
    "dim_dealer": ("dealer", "broker", "franchise", "independent"),
    "dim_vehicle": ("vehicle", "brand", "model", "bev", "suv", "sedan"),
    "dim_date": ("date", "year", "month", "quarter", "q1", "q4", "2022", "2023", "2024"),
    "dim_contract_status": ("active", "defaulted", "performing", "closed", "status"),
    "dim_product": ("product", "family", "bundle", "insurance"),
    "dim_cashflow_type": ("cashflow type", "recurring", "inflow", "commission", "late fee"),
}
KNOWN_GLOSSARY_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Successful Payment",
        (
            "successfully receive",
            "successfully received",
            "successful payment",
            "settled payment",
            "cash received",
            "net cash",
        ),
    ),
    (
        "Missed Installment",
        (
            "missed planned",
            "missed payment",
            "missed installment",
            "missed instalment",
            "unpaid installment",
            "unpaid instalment",
        ),
    ),
    (
        "Outstanding Principal",
        (
            "outstanding principal",
            "open principal",
            "remaining principal",
            "principal scheduled",
        ),
    ),
    (
        "Business Customer",
        (
            "business customer",
            "business customers",
            "current business customers",
            "business customers from",
            "corporate customer",
            "corporate customers",
        ),
    ),
    (
        "Net Current Balance",
        (
            "net current balance",
            "current net balance",
            "current account balance",
            "net balance across",
        ),
    ),
    (
        "Overdraft Run",
        (
            "longest overdraft run",
            "consecutive overdrawn days",
            "crossed from positive available balance into overdraft",
            "crossed into overdraft",
        ),
    ),
    (
        "Customer Risk Class",
        (
            "customer risk class",
            "risk class c",
            "best risk class",
            "riskiest customer class",
        ),
    ),
    (
        "Point-in-Time Attribute",
        (
            "valid at origination",
            "at origination rather than the current",
            "dealer risk rating valid at origination",
            "point in time",
        ),
    ),
    (
        "Newly Financed Vehicle After Early Lease End",
        (
            "newly financed vehicle models",
            "previously ended a lease early",
            "after customers previously ended a lease early",
            "new loan after early lease termination",
        ),
    ),
    (
        "Late Lease Installment",
        (
            "lease installments due",
            "paid more than 15 days late",
            "late-fee cash",
            "late lease installment",
        ),
    ),
    (
        "Cash Realization After Reversals",
        (
            "after accounting for signed reversals",
            "cash realization after reversals",
            "reversal-adjusted cash realization",
            "signed reversals",
        ),
    ),
    (
        "Blocked Funds",
        (
            "blocked funds",
            "blocked amount",
            "active account with blocked funds",
        ),
    ),
    (
        "Approved Overdraft Facility",
        (
            "approved overdraft facility",
            "approved overdraft",
            "authorized overdraft",
            "overdraft facility",
        ),
    ),
    (
        "Returned Refinanced Vehicle",
        (
            "returned and currently refinanced",
            "returned vehicles in active contracts",
            "currently refinanced in an active contract",
            "successfully ended 2023 leases have been returned",
        ),
    ),
    (
        "Dealer Legal Name",
        (
            "dealer legal name",
            "dealer legal names",
            "legal names of current dealers",
            "legal names of dealers",
        ),
    ),
    (
        "Dealer Risk Rating",
        (
            "strongest internal risk rating",
            "internal risk rating",
            "dealer risk rating",
            "riskiest dealer rating",
        ),
    ),
)


def default_dependencies() -> OrchestratorDependencies:
    return OrchestratorDependencies(llm=LiteLlmClient(), mcp=FastMcpClient())


def interpret_request(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    question = state.get("user_question", "")
    user_prompt = f"""\
Return a JSON object with this shape:
{{
  "metric": string or null,
  "dimensions": [string],
  "filters": [{{"field": string, "operator": string, "value": string}}],
  "time_reference": string or null,
  "candidate_tables": [string],
  "candidate_terms": [string],
  "needs_profiling": boolean
}}

Business question:
{question}
    """
    try:
        response = deps.llm.complete(system=deps.mcp.prompt("bi_eda_workflow"), user=user_prompt)
        plan = _extract_json_object(response.content)
        return {
            "analysis_plan": _normalize_analysis_plan(plan),
            "trace": merge_trace(
                {"trace": merge_token_usage(state, response.usage)},
                mcp_calls=1,
            ),
        }
    except Exception as exc:
        error = f"INTERPRET_REQUEST_FAILED: {exc}"
        return {
            "analysis_plan": _fallback_analysis_plan(question),
            "last_error": error,
            "error_history": append_error(state, error),
        }


def retrieve_context(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    trace = merge_trace(state)
    context = _metadata_context(state)
    mcp_calls = 0

    try:
        overview = context.get("schema_overview") or deps.mcp.schema_overview()
        context["schema_overview"] = overview
        mcp_calls += 1 if "schema_overview" not in _metadata_context(state) else 0

        selection_dictionaries: dict[str, dict[str, Any]] = {}
        for table_name in _retrievable_table_names(_list_of_dicts(overview)):
            selection_dictionaries[table_name] = deps.mcp.table_dictionary(table_name)
            mcp_calls += 1

        relationships = context.get("relationships") or deps.mcp.schema_relationships()
        context["relationships"] = relationships
        mcp_calls += 1 if "relationships" not in _metadata_context(state) else 0

        selected_tables = _select_tables(
            state,
            _list_of_dicts(overview),
            selection_dictionaries,
            _list_of_dicts(relationships),
        )
        table_dictionaries = _dict_value(context.get("table_dictionaries"))
        for table_name in selected_tables:
            if table_name not in table_dictionaries:
                table_dictionaries[table_name] = selection_dictionaries.get(
                    table_name
                ) or deps.mcp.table_dictionary(table_name)
                mcp_calls += 0 if table_name in selection_dictionaries else 1
        context["table_dictionaries"] = table_dictionaries

        glossary_terms = _dict_value(context.get("business_glossary_terms"))
        for term in _candidate_terms(state):
            if term not in glossary_terms:
                try:
                    glossary_terms[term] = deps.mcp.business_glossary_term(term)
                    mcp_calls += 1
                except Exception as exc:
                    glossary_terms[term] = {"error": str(exc)}
        context["business_glossary_terms"] = glossary_terms

        retrieved_tables = sorted(set(trace.get("retrieved_tables") or []) | set(selected_tables))
        trace["retrieved_tables"] = retrieved_tables
        trace["mcp_calls"] = trace_int(trace, "mcp_calls") + mcp_calls
        return {"metadata_context": context, "trace": trace, "last_error": None}
    except Exception as exc:
        error = f"RETRIEVE_CONTEXT_FAILED: {exc}"
        return {"last_error": error, "error_history": append_error(state, error), "trace": trace}


def profile_data(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    plan = _analysis_plan(state)
    should_profile = (
        bool(plan.get("needs_profiling")) or state.get("critic_decision") == "PROFILE_VALUES"
    )
    if not should_profile:
        return {"profiling_observations": state.get("profiling_observations") or {}}

    trace = merge_trace(state)
    observations = _dict_value(state.get("profiling_observations"))
    metadata_context = _metadata_context(state)
    table_names = list(_dict_value(metadata_context.get("table_dictionaries")).keys())
    mcp_calls = 0
    profiling_calls = 0

    try:
        for table_name in table_names:
            if table_name not in observations:
                observations[table_name] = {"sample_data": deps.mcp.sample_data(table_name)}
                mcp_calls += 1
                profiling_calls += 1
            raw_table_profile = observations.setdefault(table_name, {})
            if isinstance(raw_table_profile, dict):
                table_profile = raw_table_profile
            else:
                table_profile = {}
                observations[table_name] = table_profile
            query_text = _profiling_query_text(state)
            for column in _filter_columns_for_table(
                plan,
                metadata_context,
                str(table_name),
                query_text,
            ):
                profile_key = f"column:{column['name']}"
                if profile_key in table_profile:
                    continue
                if _is_categorical_type(column.get("data_type")):
                    table_profile[profile_key] = {
                        "categorical_values": deps.mcp.categorical_values(
                            table_name,
                            column["name"],
                        )
                    }
                else:
                    table_profile[profile_key] = {
                        "numeric_summary": deps.mcp.numeric_summary(table_name, column["name"])
                    }
                mcp_calls += 1
                profiling_calls += 1
        trace["mcp_calls"] = trace_int(trace, "mcp_calls") + mcp_calls
        trace["profiling_calls"] = trace_int(trace, "profiling_calls") + profiling_calls
        return {"profiling_observations": observations, "trace": trace}
    except Exception as exc:
        error = f"PROFILE_DATA_FAILED: {exc}"
        return {"last_error": error, "error_history": append_error(state, error), "trace": trace}


def generate_sql(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    user_prompt = f"""\
Generate one DuckDB SQL query for the business question. Return only SQL.
If the available context is insufficient, return exactly the single token
UNANSWERABLE with no prose, Markdown, or explanation.

Business question:
{state.get("user_question", "")}

Analysis plan:
{_to_json(state.get("analysis_plan") or {})}

Metadata context:
{_to_json(state.get("metadata_context") or {})}

Profiling observations:
{_to_json(state.get("profiling_observations") or {})}

Error history:
{_to_json(state.get("error_history") or [])}
    """
    try:
        response = deps.llm.complete(
            system=deps.mcp.prompt("sql_generation_rules"), user=user_prompt
        )
        sql = _extract_sql(response.content)
        trace = merge_trace(
            {"trace": merge_token_usage(state, response.usage)},
            mcp_calls=1,
        )
        if not sql or sql.upper() == "UNANSWERABLE":
            error = "UNANSWERABLE"
            return {
                "generated_sql": None,
                "first_generated_sql": state.get("first_generated_sql") or "UNANSWERABLE",
                "last_error": error,
                "error_history": append_error(state, error),
                "trace": trace,
            }

        first_sql = state.get("first_generated_sql") or sql
        return {
            "generated_sql": sql,
            "first_generated_sql": first_sql,
            "last_error": None,
            "last_error_details": None,
            "critic_decision": None,
            "trace": trace,
        }
    except Exception as exc:
        error = f"GENERATE_SQL_FAILED: {exc}"
        return {"last_error": error, "error_history": append_error(state, error)}


def validate_sql(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    sql = state.get("generated_sql")
    trace = merge_trace(state)
    if not sql:
        error = "SQL_MISSING"
        return {
            "validation_result": {"ok": False, "error": error},
            "last_error": error,
            "error_history": append_error(state, error),
            "trace": trace,
        }

    try:
        result = deps.mcp.validate_sql(sql)
        trace = merge_trace(state, mcp_calls=1)
        if result.get("valid") is True:
            return {"validation_result": {"ok": True}, "last_error": None, "trace": trace}
        error_details = result.get("error") or {"message": "SQL validation failed."}
        error = _error_details_to_text(error_details)
        return {
            "validation_result": {"ok": False, "error": error, "details": error_details},
            "last_error": error,
            "last_error_details": error_details,
            "error_history": append_error(state, error),
            "trace": trace,
        }
    except Exception as exc:
        error = f"VALIDATE_SQL_FAILED: {exc}"
        return {"last_error": error, "error_history": append_error(state, error), "trace": trace}


def execute_sql(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    sql = state.get("generated_sql")
    trace = merge_trace(state)
    if not sql:
        error = "SQL_MISSING"
        return {"last_error": error, "error_history": append_error(state, error), "trace": trace}

    try:
        result = deps.mcp.execute_sql(sql)
        trace = merge_trace(state, mcp_calls=1, sql_executions=1)
        if result.get("success") is True:
            return {
                "execution_result": result,
                "last_error": None,
                "last_error_details": None,
                "trace": trace,
            }
        error_details = result.get("error") or {"message": "SQL execution failed."}
        error = _error_details_to_text(error_details)
        return {
            "execution_result": result,
            "last_error": error,
            "last_error_details": error_details,
            "error_history": append_error(state, error),
            "trace": trace,
        }
    except Exception as exc:
        error = f"EXECUTE_SQL_FAILED: {exc}"
        return {"last_error": error, "error_history": append_error(state, error), "trace": trace}


def critic_reflection(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    user_prompt = f"""\
Return JSON with this shape:
{{
  "decision": "ACCEPT" | "REGENERATE_SQL" | "RETRIEVE_MORE_CONTEXT" | "PROFILE_VALUES" | "ABORT",
  "correction_hint": string or null,
  "candidate_tables": [string],
  "candidate_terms": [string],
  "needs_profiling": boolean
}}

Business question:
{state.get("user_question", "")}

Analysis plan:
{_to_json(state.get("analysis_plan") or {})}

Metadata context:
{_to_json(state.get("metadata_context") or {})}

Current SQL:
{state.get("generated_sql") or ""}

Execution result:
{_to_json(state.get("execution_result") or {})}

Last error:
{state.get("last_error") or ""}

Last error details:
{_to_json(state.get("last_error_details") or {})}

Error history:
{_to_json(state.get("error_history") or [])}
    """
    try:
        response = deps.llm.complete(
            system=deps.mcp.prompt("critic_reflection_rules"),
            user=user_prompt,
        )
        decision_payload = _extract_json_object(response.content)
        decision = str(decision_payload.get("decision") or "ABORT")
        if decision not in {
            "ACCEPT",
            "REGENERATE_SQL",
            "RETRIEVE_MORE_CONTEXT",
            "PROFILE_VALUES",
            "ABORT",
        }:
            decision = "ABORT"
        plan = _copy_analysis_plan(state.get("analysis_plan"))
        if decision_payload.get("correction_hint"):
            plan["correction_hint"] = str(decision_payload["correction_hint"])
        if decision_payload.get("candidate_tables"):
            plan["candidate_tables"] = _merge_unique(
                plan.get("candidate_tables") or [],
                decision_payload["candidate_tables"],
            )
        if decision_payload.get("candidate_terms"):
            plan["candidate_terms"] = _merge_unique(
                plan.get("candidate_terms") or [],
                decision_payload["candidate_terms"],
            )
        if "needs_profiling" in decision_payload:
            plan["needs_profiling"] = bool(decision_payload["needs_profiling"])
        repair_iteration = decision in {"REGENERATE_SQL", "RETRIEVE_MORE_CONTEXT", "PROFILE_VALUES"}
        return {
            "critic_decision": decision,
            "analysis_plan": plan,
            "iteration_count": state_int(state, "iteration_count") + int(repair_iteration),
            "trace": merge_trace(
                {"trace": merge_token_usage(state, response.usage)},
                mcp_calls=1,
                critic_calls=1,
                critic_llm_calls=1,
                critic_input_tokens=response.usage.get("prompt_tokens") or 0,
                critic_output_tokens=response.usage.get("completion_tokens") or 0,
                critic_total_tokens=response.usage.get("total_tokens") or 0,
            ),
        }
    except Exception as exc:
        error = f"CRITIC_REFLECTION_FAILED: {exc}"
        return {
            "critic_decision": "ABORT",
            "last_error": error,
            "error_history": append_error(state, error),
        }


def synthesize_answer(state: AgentState, deps: OrchestratorDependencies) -> StateUpdate:
    sql_stage_trace = _sql_stage_trace(state)
    if state.get("last_error") or state.get("critic_decision") == "ABORT":
        answer = _failure_answer(state)
        return {"final_answer": answer, "chart_config": None, "sql_stage_trace": sql_stage_trace}

    result = state.get("execution_result")
    if not result:
        return {
            "final_answer": "Es liegt kein ausführbares Ergebnis vor.",
            "chart_config": None,
            "sql_stage_trace": sql_stage_trace,
        }

    try:
        user_prompt = f"""\
Answer the business question concisely in German using only this SQL result.
Do not invent values not present in the result.

Business question:
{state.get("user_question", "")}

Generated SQL:
{state.get("generated_sql") or ""}

SQL result:
{_to_json(result)}

Chart guidance:
{deps.mcp.prompt("chart_decision_rules")}
"""
        response = deps.llm.complete(
            system=deps.mcp.prompt("bi_eda_workflow"),
            user=user_prompt,
        )
        return {
            "final_answer": response.content.strip(),
            "sql_stage_trace": sql_stage_trace,
            "trace": merge_trace(
                {"trace": merge_token_usage(state, response.usage)},
                mcp_calls=2,
            ),
        }
    except Exception:
        return {
            "final_answer": _result_answer(result),
            "chart_config": None,
            "sql_stage_trace": sql_stage_trace,
        }


def _sql_stage_trace(state: AgentState) -> TraceState:
    existing = state.get("sql_stage_trace")
    if isinstance(existing, dict):
        return cast(TraceState, existing)
    trace = copy_trace(state)
    started_at = state.get("started_at_monotonic")
    if isinstance(started_at, float) and started_at > 0:
        trace["runtime_seconds"] = round(time.perf_counter() - started_at, 6)
    return trace


def _normalize_analysis_plan(plan: dict[str, Any]) -> AnalysisPlan:
    return {
        "metric": _optional_string(plan.get("metric")),
        "dimensions": _string_list(plan.get("dimensions")),
        "filters": _filter_list(plan.get("filters")),
        "time_reference": _optional_string(plan.get("time_reference")),
        "candidate_tables": _string_list(plan.get("candidate_tables")),
        "candidate_terms": _string_list(plan.get("candidate_terms")),
        "needs_profiling": bool(plan.get("needs_profiling")),
    }


def _fallback_analysis_plan(question: str) -> AnalysisPlan:
    return {
        "metric": None,
        "dimensions": [],
        "filters": [],
        "time_reference": None,
        "candidate_tables": [],
        "candidate_terms": _merge_unique(
            _known_glossary_terms(question),
            re.findall(r"[A-ZÄÖÜ][\wÄÖÜäöüß-]{3,}", question),
        ),
        "needs_profiling": False,
    }


def _select_tables(
    state: AgentState,
    overview: list[dict[str, Any]],
    table_dictionaries: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
) -> list[str]:
    available_names = _retrievable_table_names(overview)
    requested_names = set(_string_list(_analysis_plan(state).get("candidate_tables")))
    question = state.get("user_question", "")
    plan = _analysis_plan(state)
    query_text = " ".join(
        [
            question,
            str(plan.get("metric") or ""),
            " ".join(_string_list(plan.get("dimensions"))),
            " ".join(_candidate_terms(state)),
            _to_json(plan.get("filters") or []),
        ]
    )
    scores = {
        name: _table_relevance_score(
            name,
            _overview_for_table(overview, name),
            table_dictionaries.get(name, {}),
            requested_names,
            query_text,
        )
        for name in available_names
    }
    selected = [
        name
        for name, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0
    ][:MAX_RETRIEVED_TABLES]
    if not selected:
        selected = _fallback_fact_tables(available_names)
    selected = _ensure_required_domain_tables(selected, available_names, query_text)
    return _with_relationship_neighbors(selected, available_names, relationships or [])[
        :MAX_RETRIEVED_TABLES
    ]


def _retrievable_table_names(overview: list[dict[str, Any]]) -> list[str]:
    names = [str(table.get("name")) for table in overview if table.get("name")]
    return [name for name in names if not name.startswith("stg_")]


def _table_relevance_score(
    table_name: str,
    overview: dict[str, Any],
    table_dictionary: dict[str, Any],
    requested_names: set[str],
    query_text: str,
) -> int:
    normalized_query = _search_text(query_text)
    score = 0
    if table_name in requested_names:
        score += 100
    table_tokens = _identifier_tokens(table_name)
    score += 8 * _token_overlap(table_tokens, normalized_query)
    comment_tokens = _text_tokens(str(overview.get("comment") or ""))
    score += 3 * _token_overlap(comment_tokens, normalized_query)
    for column in _list_of_dicts(table_dictionary.get("columns")):
        column_tokens = _identifier_tokens(str(column.get("name") or ""))
        score += 5 * _token_overlap(column_tokens, normalized_query)
        column_comment_tokens = _text_tokens(str(column.get("comment") or ""))
        score += 2 * _token_overlap(column_comment_tokens, normalized_query)
    for hint in DOMAIN_TABLE_HINTS.get(table_name, ()):
        if _search_text(hint) in normalized_query:
            score += 35 if table_name == "dim_date" else 20
    if table_name.startswith("fact_") and score > 0:
        score += 5
    return score


def _overview_for_table(overview: list[dict[str, Any]], table_name: str) -> dict[str, Any]:
    for table in overview:
        if table.get("name") == table_name:
            return table
    return {}


def _fallback_fact_tables(available_names: list[str]) -> list[str]:
    facts = [name for name in available_names if name.startswith("fact_")]
    return facts[:MAX_RETRIEVED_TABLES] if facts else available_names[:MAX_RETRIEVED_TABLES]


def _ensure_required_domain_tables(
    selected: list[str],
    available_names: list[str],
    query_text: str,
) -> list[str]:
    required: list[str] = []
    normalized_query = _search_text(query_text)
    if re.search(r"\b(?:20\d{2}|q[1-4]|month|quarter|year)\b", normalized_query):
        required.append("dim_date")
    for table_name, tokens in {
        "dim_dealer": ("dealer", "dealers"),
        "dim_customer": ("customer", "customers"),
        "dim_vehicle": ("vehicle", "vehicles", "brand", "model"),
        "dim_contract_status": (
            "active",
            "closed",
            "defaulted",
            "performing",
            "successfully ended",
            "status",
        ),
        "fact_payment_transactions": ("payment", "payments", "paid", "received", "cash"),
    }.items():
        if any(token in normalized_query for token in tokens):
            required.append(table_name)
    adjusted = [name for name in selected if name not in required]
    for table_name in reversed(required):
        if table_name in available_names:
            adjusted.insert(0, table_name)
    return adjusted[:MAX_RETRIEVED_TABLES]


def _with_relationship_neighbors(
    selected: list[str],
    available_names: list[str],
    relationships: list[dict[str, Any]],
) -> list[str]:
    ordered = list(selected)
    if len(ordered) >= MAX_RETRIEVED_TABLES:
        return ordered
    for table_name in selected:
        for neighbor in _relationship_neighbors(table_name, available_names, relationships):
            if neighbor not in ordered:
                ordered.append(neighbor)
            if len(ordered) >= MAX_RETRIEVED_TABLES:
                return ordered
    return ordered


def _relationship_neighbors(
    table_name: str,
    available_names: list[str],
    relationships: list[dict[str, Any]],
) -> list[str]:
    neighbors: list[str] = []
    for relationship in relationships:
        from_table = str(relationship.get("from_table") or "")
        to_table = str(relationship.get("to_table") or "")
        if from_table == table_name and to_table in available_names:
            neighbors.append(to_table)
        if to_table == table_name and from_table in available_names:
            neighbors.append(from_table)
    return sorted(neighbors, key=lambda name: (not name.startswith("dim_"), name))


def _search_text(value: str) -> str:
    return " ".join(_text_tokens(value))


def _text_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9]+", value.casefold()) if len(token) >= 2]


def _identifier_tokens(value: str) -> list[str]:
    return _text_tokens(value.replace("_", " "))


def _token_overlap(tokens: list[str], normalized_query: str) -> int:
    return sum(1 for token in set(tokens) if token in normalized_query)


def _candidate_terms(state: AgentState) -> list[str]:
    plan = _analysis_plan(state)
    terms = _merge_unique(
        _known_glossary_terms(str(state.get("user_question") or "")),
        plan.get("candidate_terms") or [],
    )
    metric = plan.get("metric")
    if isinstance(metric, str) and metric:
        terms.append(metric)
    return _merge_unique([], terms)[:5]


def _known_glossary_terms(question: str) -> list[str]:
    normalized_question = _search_text(question)
    terms: list[str] = []
    for term, phrases in KNOWN_GLOSSARY_PHRASES:
        if any(_search_text(phrase) in normalized_question for phrase in phrases):
            terms.append(term)
    return terms


def _filter_columns_for_table(
    plan: AnalysisPlan,
    metadata_context: dict[str, Any],
    table_name: str,
    query_text: str = "",
) -> list[dict[str, str]]:
    filters = plan.get("filters")
    filter_fields = {
        str(item.get("field")).strip()
        for item in filters or []
        if isinstance(item, dict) and str(item.get("field") or "").strip()
    }

    table_dictionaries = _dict_value(metadata_context.get("table_dictionaries"))
    table_dictionary = _dict_value(table_dictionaries.get(table_name))
    columns = table_dictionary.get("columns") if isinstance(table_dictionary, dict) else []
    if not isinstance(columns, list):
        return []

    selected_columns = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "")
        if name in filter_fields:
            selected_columns.append({"name": name, "data_type": str(column.get("data_type") or "")})
    selected_names = {column["name"] for column in selected_columns}
    normalized_query = _search_text(query_text)
    candidates: list[tuple[int, dict[str, str]]] = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "")
        if not name or name in selected_names:
            continue
        data_type = str(column.get("data_type") or "")
        if not _is_categorical_type(data_type):
            continue
        if not _is_low_cardinality_candidate(name):
            continue
        score = _profiling_column_score(column, normalized_query)
        if score > 0:
            candidates.append((score, {"name": name, "data_type": data_type}))
    selected_columns.extend(
        column
        for _score, column in sorted(candidates, key=lambda item: (-item[0], item[1]["name"]))
    )
    return selected_columns[:MAX_PROFILE_COLUMNS_PER_TABLE]


def _is_text_type(data_type: Any) -> bool:
    normalized_type = str(data_type).upper()
    return any(token in normalized_type for token in ("CHAR", "TEXT", "STRING", "VARCHAR"))


def _is_categorical_type(data_type: Any) -> bool:
    normalized_type = str(data_type).upper()
    return _is_text_type(normalized_type) or "BOOL" in normalized_type


def _is_low_cardinality_candidate(column_name: str) -> bool:
    tokens = _identifier_tokens(column_name)
    if any(token in HIGH_CARDINALITY_COLUMN_HINTS for token in tokens):
        return False
    return any(token in CATEGORICAL_PROFILE_COLUMN_HINTS for token in tokens)


def _profiling_column_score(column: dict[str, Any], normalized_query: str) -> int:
    name = str(column.get("name") or "")
    comment = str(column.get("comment") or "")
    score = 4 * _token_overlap(_identifier_tokens(name), normalized_query)
    score += 2 * _token_overlap(_text_tokens(comment), normalized_query)
    return score


def _profiling_query_text(state: AgentState) -> str:
    plan = _analysis_plan(state)
    return " ".join(
        [
            str(state.get("user_question") or ""),
            str(plan.get("metric") or ""),
            " ".join(_string_list(plan.get("dimensions"))),
            " ".join(_candidate_terms(state)),
            _to_json(plan.get("filters") or []),
        ]
    )


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match is None:
        return {}
    loaded = json.loads(match.group(0))
    return loaded if isinstance(loaded, dict) else {}


def _extract_sql(content: str) -> str:
    stripped = content.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    return stripped.rstrip(";").strip()


def _error_details_to_text(error_details: Any) -> str:
    if isinstance(error_details, dict):
        error_type = error_details.get("error_type") or "SqlError"
        message = error_details.get("message") or "SQL failed."
        return f"{error_type}: {message}"
    return str(error_details)


def _failure_answer(state: AgentState) -> str:
    if state.get("last_error") == "UNANSWERABLE":
        return "Die Frage ist mit dem verfügbaren Schema nicht zuverlässig beantwortbar."
    return f"Die Anfrage konnte nicht erfolgreich ausgeführt werden: {state.get('last_error')}"


def _result_answer(result: Any) -> str:
    if not isinstance(result, dict):
        return "Die SQL-Abfrage wurde erfolgreich ausgeführt."
    columns = _string_list(result.get("columns"))
    rows = result.get("rows")
    row_count = len(rows) if isinstance(rows, list) else 0
    return f"Die SQL-Abfrage lieferte {row_count} Zeilen mit den Spalten: {', '.join(columns)}."


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _merge_unique(left: Any, right: Any) -> list[str]:
    values: list[str] = []
    for item in [*_string_list(left), *_string_list(right)]:
        text = str(item).strip()
        if text and text not in values:
            values.append(text)
    return values


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _filter_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _copy_analysis_plan(plan: AnalysisPlan | None) -> AnalysisPlan:
    if plan is None:
        return {}
    return dict(plan)


def _analysis_plan(state: AgentState) -> AnalysisPlan:
    return state.get("analysis_plan") or {}


def _metadata_context(state: AgentState) -> dict[str, Any]:
    return dict(state.get("metadata_context") or {})


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
