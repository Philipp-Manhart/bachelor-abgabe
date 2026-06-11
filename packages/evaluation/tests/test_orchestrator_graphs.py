from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_orchestrator.llm import LlmResponse
from agent_orchestrator.mcp_client import FastMcpClient
from agent_orchestrator.nodes import (
    OrchestratorDependencies,
    _candidate_terms,
    _filter_columns_for_table,
    _select_tables,
)
from agent_orchestrator.runner import (
    run_mcp_critic_with_dependencies,
    run_mcp_single_shot_with_dependencies,
    stream_mcp_critic_with_dependencies,
)


@dataclass
class FakeLlm:
    responses: list[str]
    calls: list[dict[str, str]] = field(default_factory=list)

    def complete(self, *, system: str, user: str) -> LlmResponse:
        self.calls.append({"system": system, "user": user})
        return LlmResponse(
            content=self.responses.pop(0),
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


@dataclass
class FakeMcp:
    validation_by_sql: dict[str, dict[str, Any]]
    execute_result: dict[str, Any] = field(
        default_factory=lambda: {
            "success": True,
            "columns": ["contract_count"],
            "rows": [[3]],
            "row_count": 1,
            "truncated": False,
        }
    )
    calls: list[str] = field(default_factory=list)

    def schema_overview(self) -> list[dict[str, Any]]:
        self.calls.append("schema_overview")
        return [{"name": "fact_contracts", "comment": "Contracts", "row_count": 3}]

    def table_dictionary(self, table_name: str) -> dict[str, Any]:
        self.calls.append(f"table_dictionary:{table_name}")
        return {
            "name": table_name,
            "columns": [{"name": "contract_id", "data_type": "INTEGER", "nullable": False}],
        }

    def schema_relationships(self) -> list[dict[str, Any]]:
        self.calls.append("schema_relationships")
        return []

    def business_glossary_term(self, term: str) -> dict[str, Any]:
        self.calls.append(f"business_glossary_term:{term}")
        return {term: {"formula": "COUNT(*)"}}

    def sample_data(self, table_name: str, limit: int = 3) -> list[dict[str, Any]]:
        self.calls.append(f"sample_data:{table_name}:{limit}")
        return [{"contract_id": 1}]

    def categorical_values(self, table_name: str, column: str) -> list[str]:
        self.calls.append(f"categorical_values:{table_name}:{column}")
        return []

    def numeric_summary(self, table_name: str, column: str) -> dict[str, Any]:
        self.calls.append(f"numeric_summary:{table_name}:{column}")
        return {"table_name": table_name, "column": column, "null_count": 0}

    def validate_sql(self, query: str) -> dict[str, Any]:
        self.calls.append(f"validate_sql:{query}")
        return self.validation_by_sql[query]

    def execute_sql(self, query: str) -> dict[str, Any]:
        self.calls.append(f"execute_sql:{query}")
        return self.execute_result

    def prompt(self, name: str) -> str:
        self.calls.append(f"prompt:{name}")
        return name

    def close(self) -> None:
        return None


def test_fastmcp_client_uses_server_resources_tools_and_prompts(tmp_path) -> None:
    import duckdb

    from mcp_server import DatabaseSettings, create_server

    database_path = tmp_path / "transport-test.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("CREATE TABLE contracts (contract_id INTEGER)")
        connection.execute("COMMENT ON TABLE contracts IS 'Synthetic contracts'")
        connection.execute("INSERT INTO contracts VALUES (1), (2)")

    server = create_server(DatabaseSettings.from_path(database_path))
    with FastMcpClient(server) as client:
        overview = client.schema_overview()
        sample = client.sample_data("contracts", limit=1)
        validation = client.validate_sql("SELECT COUNT(*) FROM contracts")
        prompt = client.prompt("sql_generation_rules")

    assert overview == [
        {
            "name": "contracts",
            "comment": "Synthetic contracts",
            "row_count": 2,
        }
    ]
    assert sample == [{"contract_id": 1}]
    assert validation["valid"] is True
    assert "Generate DuckDB SQL only from verified MCP context" in prompt


def test_single_shot_returns_error_without_critic_repair() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT missing_column FROM fact_contracts",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={
            "SELECT missing_column FROM fact_contracts": {
                "valid": False,
                "error": {
                    "error_type": "BinderException",
                    "message": "Referenced column not found",
                    "stacktrace": "stack",
                },
            }
        }
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_single_shot_with_dependencies("Wie viele Verträge?", deps)

    assert result["system"] == "B"
    assert result["status"] == "ERROR"
    assert result["final_generated_sql"] == "SELECT missing_column FROM fact_contracts"
    assert result["last_error"] == "BinderException: Referenced column not found"
    assert result["iterations"] == 0
    assert not any("Current SQL" in call["user"] for call in llm.calls)
    assert not any(call.startswith("execute_sql") for call in mcp.calls)


def test_retrieval_selects_relevant_fact_table_from_question_terms() -> None:
    overview = [
        {"name": "dim_cashflow_type", "comment": "Cashflow classification dimension"},
        {"name": "dim_contract_status", "comment": "Contract lifecycle status dimension"},
        {"name": "dim_customer", "comment": "Customer dimension"},
        {"name": "fact_leasing_contracts", "comment": "Leasing contract fact table"},
        {"name": "fact_loan_contracts", "comment": "Loan contract fact table"},
    ]
    dictionaries = {
        "dim_cashflow_type": {"columns": [{"name": "cashflow_type_code"}]},
        "dim_contract_status": {"columns": [{"name": "status_code"}]},
        "dim_customer": {"columns": [{"name": "customer_id"}]},
        "fact_leasing_contracts": {"columns": [{"name": "agreed_annual_mileage_km"}]},
        "fact_loan_contracts": {"columns": [{"name": "annual_percentage_rate_effective"}]},
    }

    selected = _select_tables(
        {
            "user_question": "What is the average annual mileage allowance in leasing contracts?",
            "analysis_plan": {},
        },
        overview,
        dictionaries,
        [],
    )

    assert selected[0] == "fact_leasing_contracts"
    assert "fact_leasing_contracts" in selected


def test_retrieval_uses_relationship_neighbors_for_join_context() -> None:
    overview = [
        {"name": "fact_loan_contracts", "comment": "Loan contract fact table"},
        {"name": "dim_dealer", "comment": "Dealer dimension"},
        {"name": "dim_date", "comment": "Calendar dimension"},
    ]
    dictionaries = {
        "fact_loan_contracts": {"columns": [{"name": "financed_amount_net"}]},
        "dim_dealer": {"columns": [{"name": "legal_entity_name"}]},
        "dim_date": {"columns": [{"name": "calendar_year"}]},
    }
    relationships = [
        {"from_table": "fact_loan_contracts", "to_table": "dim_dealer"},
        {"from_table": "fact_loan_contracts", "to_table": "dim_date"},
    ]

    selected = _select_tables(
        {
            "user_question": "Which dealers generated the largest net new loan volume in 2024?",
            "analysis_plan": {},
        },
        overview,
        dictionaries,
        relationships,
    )

    assert "fact_loan_contracts" in selected
    assert "dim_dealer" in selected
    assert "dim_date" in selected


def test_retrieval_forces_contract_status_for_lifecycle_terms() -> None:
    overview = [
        {"name": "dim_contract_status", "comment": "Contract lifecycle status dimension"},
        {"name": "fact_leasing_contracts", "comment": "Leasing contract fact table"},
        {"name": "fact_loan_contracts", "comment": "Loan contract fact table"},
    ]
    dictionaries = {
        "dim_contract_status": {"columns": [{"name": "is_active_flag"}]},
        "fact_leasing_contracts": {"columns": [{"name": "interest_rate_effective"}]},
        "fact_loan_contracts": {"columns": [{"name": "annual_percentage_rate_effective"}]},
    }

    selected = _select_tables(
        {
            "user_question": (
                "For active leases, calculate the portfolio-weighted effective customer rate."
            ),
            "analysis_plan": {},
        },
        overview,
        dictionaries,
        [],
    )

    assert "dim_contract_status" in selected


def test_candidate_terms_map_payment_receipt_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "What net cash did the bank successfully receive in 2023 from leasing contracts?"
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Successful Payment"


def test_candidate_terms_map_missed_installments_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "Find customers who missed planned loan installments for "
                "three consecutive calendar months."
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Missed Installment"


def test_candidate_terms_map_returned_refinanced_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "How many vehicles from successfully ended 2023 leases have been "
                "returned and are currently refinanced in an active contract?"
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Returned Refinanced Vehicle"


def test_candidate_terms_map_business_customer_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": "How many current business customers are in the warehouse?",
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Business Customer"


def test_candidate_terms_map_net_current_balance_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "What is the net current balance for customers whose preferred "
                "servicing channel is online?"
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Net Current Balance"


def test_candidate_terms_map_overdraft_run_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "Using account snapshots, identify accounts that crossed from "
                "positive available balance into overdraft and report their "
                "longest overdraft run."
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Overdraft Run"


def test_candidate_terms_map_customer_risk_class_phrase_to_glossary_term() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "How many private customers currently hold an active account "
                "and are in the riskiest customer class?"
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Customer Risk Class"


def test_candidate_terms_map_point_in_time_dealer_attribute_phrase() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "For loan originations, report net financed amount by the dealer "
                "risk rating valid at origination rather than the current rating."
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Point-in-Time Attribute"


def test_candidate_terms_map_newly_financed_after_early_lease_phrase() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "Which five newly financed vehicle models appear most often "
                "after customers previously ended a lease early?"
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Newly Financed Vehicle After Early Lease End"


def test_candidate_terms_map_late_lease_installment_phrase() -> None:
    terms = _candidate_terms(
        {
            "user_question": (
                "Find lease installments due in 2024 that were paid more than "
                "15 days late and total the collected late-fee cash."
            ),
            "analysis_plan": {"candidate_terms": []},
        }
    )

    assert terms[0] == "Late Lease Installment"


def test_profile_column_selection_includes_matching_categorical_codes() -> None:
    metadata_context = {
        "table_dictionaries": {
            "dim_dealer": {
                "columns": [
                    {
                        "name": "risk_rating_code",
                        "data_type": "VARCHAR",
                        "comment": "Internal dealer risk rating.",
                    },
                    {
                        "name": "dealer_status_code",
                        "data_type": "VARCHAR",
                        "comment": "Operational dealer status.",
                    },
                    {
                        "name": "legal_entity_name",
                        "data_type": "VARCHAR",
                        "comment": "Registered legal entity of the dealer.",
                    },
                ]
            }
        }
    }

    columns = _filter_columns_for_table(
        {"filters": [], "candidate_terms": []},
        metadata_context,
        "dim_dealer",
        "List current dealers with the strongest internal risk rating.",
    )

    assert columns == [
        {"name": "risk_rating_code", "data_type": "VARCHAR"},
        {"name": "dealer_status_code", "data_type": "VARCHAR"},
    ]


def test_profile_column_selection_avoids_high_cardinality_name_columns() -> None:
    metadata_context = {
        "table_dictionaries": {
            "dim_dealer": {
                "columns": [
                    {
                        "name": "legal_entity_name",
                        "data_type": "VARCHAR",
                        "comment": "Registered legal entity of the dealer.",
                    },
                    {
                        "name": "dealer_name",
                        "data_type": "VARCHAR",
                        "comment": "Commercial dealer name.",
                    },
                ]
            }
        }
    }

    columns = _filter_columns_for_table(
        {"filters": [], "candidate_terms": []},
        metadata_context,
        "dim_dealer",
        "List legal names of current dealers.",
    )

    assert columns == []


def test_single_shot_does_not_retry_after_execution_error() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT contract_id FROM fact_contracts",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={"SELECT contract_id FROM fact_contracts": {"valid": True}},
        execute_result={
            "success": False,
            "error": {
                "error_type": "ExecutionException",
                "message": "Execution failed",
                "stacktrace": "stack",
            },
        },
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_single_shot_with_dependencies("Liste Verträge.", deps)

    assert result["system"] == "B"
    assert result["status"] == "ERROR"
    assert result["iterations"] == 0
    assert result["last_error"] == "ExecutionException: Execution failed"
    assert not any("Current SQL" in call["user"] for call in llm.calls)


def test_critic_repairs_validation_error_and_executes_sql() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT missing_column FROM fact_contracts",
            '{"decision": "REGENERATE_SQL", "correction_hint": "Use COUNT(*)."}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={
            "SELECT missing_column FROM fact_contracts": {
                "valid": False,
                "error": {
                    "error_type": "BinderException",
                    "message": "Referenced column not found",
                    "stacktrace": "stack",
                },
            },
            "SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True},
        }
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Wie viele Verträge?", deps, max_iterations=3)

    assert result["system"] == "C"
    assert result["status"] == "SUCCESS"
    assert result["first_generated_sql"] == "SELECT missing_column FROM fact_contracts"
    assert result["final_generated_sql"] == "SELECT COUNT(*) AS contract_count FROM fact_contracts"
    assert result["final_answer"] == "Es gibt 3 Verträge."
    assert result["last_error"] is None
    assert result["iterations"] == 1
    assert result["critic_calls"] == 2
    assert result["trace"]["critic_calls"] == 2
    assert result["trace"]["llm_calls"] == 6
    assert result["trace"]["sql_stage_llm_calls"] == 5
    assert result["trace"]["answer_synthesis_llm_calls"] == 1
    assert result["trace"]["end_to_end_llm_calls"] == 6
    assert result["trace"]["sql_executions"] == 1
    assert result["trace"]["sql_stage_sql_executions"] == 1
    assert result["trace"]["mcp_calls"] >= 5
    assert result["trace"]["retrieved_tables"] == ["fact_contracts"]


def test_critic_iteration_count_tracks_repairs_not_accept_reviews() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT first_missing FROM fact_contracts",
            '{"decision": "REGENERATE_SQL", "correction_hint": "First repair."}',
            "SELECT second_missing FROM fact_contracts",
            '{"decision": "REGENERATE_SQL", "correction_hint": "Second repair."}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={
            "SELECT first_missing FROM fact_contracts": {
                "valid": False,
                "error": {"error_type": "BinderException", "message": "first", "stacktrace": "s1"},
            },
            "SELECT second_missing FROM fact_contracts": {
                "valid": False,
                "error": {"error_type": "BinderException", "message": "second", "stacktrace": "s2"},
            },
            "SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True},
        }
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Wie viele Verträge?", deps, max_iterations=3)

    assert result["status"] == "SUCCESS"
    assert result["first_generated_sql"] == "SELECT first_missing FROM fact_contracts"
    assert result["final_generated_sql"] == "SELECT COUNT(*) AS contract_count FROM fact_contracts"
    assert result["iterations"] == 2
    assert result["critic_calls"] == 3


def test_critic_accept_review_does_not_increment_repair_iterations() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={"SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True}}
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Wie viele Verträge?", deps, max_iterations=3)

    assert result["status"] == "SUCCESS"
    assert result["critic_decision"] == "ACCEPT"
    assert result["iterations"] == 0
    assert result["critic_calls"] == 1
    assert result["trace"]["critic_calls"] == 1


def test_critic_challenges_unanswerable_before_final_rejection() -> None:
    llm = FakeLlm(
        [
            '{"metric": null, "candidate_tables": [], "candidate_terms": [], '
            '"needs_profiling": false}',
            "UNANSWERABLE",
            '{"decision": "REGENERATE_SQL", "correction_hint": "Use available fact table."}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={"SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True}}
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Wie viele Verträge?", deps, max_iterations=3)

    assert result["status"] == "SUCCESS"
    assert result["first_generated_sql"] == "UNANSWERABLE"
    assert result["final_generated_sql"] == "SELECT COUNT(*) AS contract_count FROM fact_contracts"
    assert result["last_error"] is None
    assert result["iterations"] == 1
    assert result["critic_calls"] == 2
    assert any("Last error:\nUNANSWERABLE" in call["user"] for call in llm.calls)


def test_critic_repairs_execution_error_and_executes_sql_again() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "REGENERATE_SQL", "correction_hint": "Use executable table."}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts_fixed",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={
            "SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True},
            "SELECT COUNT(*) AS contract_count FROM fact_contracts_fixed": {"valid": True},
        },
        execute_result={
            "success": False,
            "error": {
                "error_type": "ExecutionException",
                "message": "Execution failed",
                "stacktrace": "stack",
            },
        },
    )

    def execute_sql(query: str) -> dict[str, object]:
        mcp.calls.append(f"execute_sql:{query}")
        if query == "SELECT COUNT(*) AS contract_count FROM fact_contracts_fixed":
            return {
                "success": True,
                "columns": ["contract_count"],
                "rows": [[3]],
                "row_count": 1,
                "truncated": False,
            }
        return {
            "success": False,
            "error": {
                "error_type": "ExecutionException",
                "message": "Execution failed",
                "stacktrace": "stack",
            },
        }

    mcp.execute_sql = execute_sql  # type: ignore[method-assign]
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Wie viele Verträge?", deps, max_iterations=3)

    assert result["status"] == "SUCCESS"
    assert result["first_generated_sql"] == "SELECT COUNT(*) AS contract_count FROM fact_contracts"
    assert (
        result["final_generated_sql"]
        == "SELECT COUNT(*) AS contract_count FROM fact_contracts_fixed"
    )
    assert result["last_error"] is None
    assert result["iterations"] == 1
    assert result["critic_calls"] == 2
    assert result["trace"]["sql_executions"] == 2


def test_unanswerable_is_rejected_after_critic_abort() -> None:
    llm = FakeLlm(
        [
            '{"metric": null, "candidate_tables": [], "candidate_terms": [], '
            '"needs_profiling": false}',
            "UNANSWERABLE",
            '{"decision": "ABORT", "correction_hint": "Required entity is absent."}',
        ]
    )
    mcp = FakeMcp(validation_by_sql={})
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    result = run_mcp_critic_with_dependencies("Was ist der Marktanteil?", deps)

    assert result["status"] == "CORRECT_REJECTION"
    assert result["last_error"] == "UNANSWERABLE"
    assert result["first_generated_sql"] == "UNANSWERABLE"
    assert result["final_generated_sql"] is None
    assert result["iterations"] == 0
    assert result["critic_calls"] == 1
    assert result["trace"]["sql_executions"] == 0
    assert (
        result["final_answer"]
        == "Die Frage ist mit dem verfügbaren Schema nicht zuverlässig beantwortbar."
    )
    assert not any(call.startswith("validate_sql") for call in mcp.calls)
    assert not any(call.startswith("execute_sql") for call in mcp.calls)


def test_streaming_runner_emits_node_events_and_final_result() -> None:
    llm = FakeLlm(
        [
            '{"metric": "contracts", "candidate_tables": ["fact_contracts"], '
            '"candidate_terms": [], "needs_profiling": false}',
            "SELECT COUNT(*) AS contract_count FROM fact_contracts",
            '{"decision": "ACCEPT", "correction_hint": null}',
            "Es gibt 3 Verträge.",
        ]
    )
    mcp = FakeMcp(
        validation_by_sql={"SELECT COUNT(*) AS contract_count FROM fact_contracts": {"valid": True}}
    )
    deps = OrchestratorDependencies(llm=llm, mcp=mcp)

    events = list(stream_mcp_critic_with_dependencies("Wie viele Verträge?", deps))

    node_events = [event for event in events if event["event_type"] == "node"]
    assert [event["node"] for event in node_events] == [
        "interpret_request",
        "retrieve_context",
        "profile_data",
        "generate_sql",
        "validate_sql",
        "execute_sql",
        "critic_reflection",
        "synthesize_answer",
    ]
    assert events[-1]["event_type"] == "final"
    assert events[-1]["result"] is not None
    assert events[-1]["result"]["status"] == "SUCCESS"
    assert events[-1]["result"]["final_generated_sql"] == (
        "SELECT COUNT(*) AS contract_count FROM fact_contracts"
    )
