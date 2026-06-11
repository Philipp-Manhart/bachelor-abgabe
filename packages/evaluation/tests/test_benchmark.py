from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from agent_orchestrator.llm import LlmResponse
from evaluation.benchmark.artifacts import (
    _frontier_average_points,
    _frontier_run_points,
    _run_level_metrics,
    _run_level_sql_stage_call_breakdown,
    _sql_stage_call_breakdown,
    write_selected_figure_artifacts,
    write_selected_table_artifacts,
)
from evaluation.benchmark.baseline import build_static_schema_context, run_system_a
from evaluation.benchmark.evaluator import (
    evaluate_run,
    flatten_result,
    is_correct_rejection,
    normalize_runner_result,
)
from evaluation.benchmark.io import load_questions
from evaluation.benchmark.metrics import aggregate_metrics, unanswerable_scores
from evaluation.benchmark.models import QuestionSpec
from evaluation.benchmark.runner import _limit_questions, run_benchmark
from evaluation.benchmark.sql_utils import (
    compare_result_details,
    compare_results,
    execute_for_evaluation,
    extract_tables,
    table_f1,
)
from evaluation.plotting import write_paper_figures


class FakeLlm:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, *, system: str, user: str) -> LlmResponse:
        return LlmResponse(
            content=self.content,
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        )


class FakeTransportMcp:
    server_url = "http://mcp.test/sse"

    def close(self) -> None:
        return None


def test_load_questions_normalizes_csv(tmp_path: Path) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql,order_required,evaluation_note\n"
        "1,easy,How many?,SELECT 1,true,Chosen interpretation\n"
        "46,unanswerable,Missing data?,\n",
        encoding="utf-8",
    )

    questions = load_questions(corpus)

    assert questions[0].question_id == "Q001"
    assert questions[0].answerable is True
    assert questions[0].expected_sql == "SELECT 1"
    assert questions[0].requires_ordered_result is True
    assert questions[0].evaluation_note == "Chosen interpretation"
    assert questions[1].question_id == "Q046"
    assert questions[1].answerable is False
    assert questions[1].expected_behavior == "REJECT"


def test_benchmark_corpus_keeps_balanced_categories() -> None:
    questions = load_questions(Path("database/test_queries.csv"))

    counts: dict[str, int] = {}
    for question in questions:
        counts[question.difficulty] = counts.get(question.difficulty, 0) + 1

    assert counts == {"easy": 15, "medium": 15, "hard": 15, "unanswerable": 15}


def test_limit_questions_can_sample_per_difficulty() -> None:
    questions = [
        QuestionSpec("Q001", "easy", "Easy 1", True),
        QuestionSpec("Q002", "easy", "Easy 2", True),
        QuestionSpec("Q003", "medium", "Medium 1", True),
        QuestionSpec("Q004", "medium", "Medium 2", True),
        QuestionSpec("Q005", "hard", "Hard 1", True),
        QuestionSpec("Q006", "hard", "Hard 2", True),
    ]

    limited = _limit_questions(questions, limit=None, limit_per_difficulty=1)

    assert [question.question_id for question in limited] == ["Q001", "Q003", "Q005"]


def test_selected_reporting_artifacts_are_written(tmp_path: Path) -> None:
    tables = {
        "T3": pd.DataFrame({"system": ["A"], "ultimate_success_rate": [1.0]}),
        "T5": pd.DataFrame({"system": ["A"], "difficulty": ["easy"]}),
        "T10": pd.DataFrame({"system": ["A"], "avg_sql_stage_llm_calls": [1.0]}),
        "T15": pd.DataFrame(
            {
                "system": ["C"],
                "reviewed_cases": [10],
                "avg_critic_calls": [1.2],
                "acceptance_rate": [0.7],
                "intervention_rate": [0.3],
                "abort_rate": [0.1],
            }
        ),
        "T16": pd.DataFrame(
            {
                "system": ["C"],
                "repair_cases": [3],
                "avg_repair_iterations": [0.8],
                "recovery_rate": [0.4],
                "failed_after_max_iterations": [1],
            }
        ),
        "T17": pd.DataFrame({"system": ["C"], "regression_cases": [1], "regression_rate": [0.1]}),
        "T28": pd.DataFrame({"system": ["A"], "unanswerable_f1": [1.0]}),
    }

    selected_tables = write_selected_table_artifacts(tables, tmp_path / "tables" / "selection")

    assert selected_tables["T3"].name == "01_full_summary_by_system.csv"
    assert selected_tables["critic_system_c"].name == "04_critic_review_details_system_c.csv"
    critic = pd.read_csv(selected_tables["critic_system_c"])
    assert critic.loc[0, "system"] == "C"
    assert critic.loc[0, "avg_repair_iterations"] == 0.8
    assert critic.loc[0, "regression_cases"] == 1

    source_figure = tmp_path / "source.svg"
    source_figure.write_text("<svg />", encoding="utf-8")
    split_source_figure = tmp_path / "split.svg"
    split_source_figure.write_text("<svg>split</svg>", encoding="utf-8")
    selected_figures = write_selected_figure_artifacts(
        {"F1": source_figure, "F17": split_source_figure},
        tmp_path / "figures" / "selected",
    )

    assert selected_figures["F1"].name == "01_first_pass_vs_ultimate_success_by_system.svg"
    assert selected_figures["F1"].read_text(encoding="utf-8") == "<svg />"
    assert selected_figures["F17"].name == "07_sql_stage_calls_by_system_mean_std.svg"


def test_sql_stage_call_breakdown_splits_mcp_resources_and_tools() -> None:
    frame = pd.DataFrame(
        {
            "system": ["B", "B", "C"],
            "sql_stage_llm_calls": [2, 4, 3],
            "sql_stage_mcp_calls": [10, 12, 20],
            "profiling_calls_count": [3, 5, 8],
            "sql_stage_sql_executions": [1, 1, 2],
        }
    )

    result = _sql_stage_call_breakdown(frame)

    system_b = result[result["system"].eq("B")].iloc[0]
    assert system_b["avg_sql_stage_llm_calls"] == 3
    assert system_b["avg_sql_stage_mcp_resource_calls"] == 7
    assert system_b["avg_sql_stage_mcp_tool_calls"] == 4
    assert system_b["avg_sql_stage_sql_executions"] == 1


def test_run_level_plot_data_preserves_repeated_observations_for_error_bars() -> None:
    frame = pd.DataFrame(
        {
            "run_id": ["run_1", "run_1", "run_2", "run_2"],
            "system": ["A", "A", "A", "A"],
            "difficulty": ["easy", "easy", "easy", "easy"],
            "answerable": [True, True, True, True],
            "first_pass_success": [True, False, True, True],
            "ultimate_success": [True, False, True, True],
            "correct_rejection": [False, False, False, False],
            "false_answer": [False, False, False, False],
            "outcome": ["SUCCESS", "ERROR", "SUCCESS", "SUCCESS"],
            "error_type": ["none", "wrong_result", "none", "none"],
            "iterations": [0, 0, 0, 0],
            "critic_calls": [0, 0, 0, 0],
            "critic_llm_calls": [0, 0, 0, 0],
            "critic_input_tokens": [0, 0, 0, 0],
            "critic_output_tokens": [0, 0, 0, 0],
            "critic_total_tokens": [0, 0, 0, 0],
            "llm_calls": [1, 1, 1, 1],
            "mcp_calls": [0, 0, 0, 0],
            "sql_executions": [1, 1, 1, 1],
            "input_tokens": [10, 10, 10, 10],
            "output_tokens": [5, 5, 5, 5],
            "total_tokens": [15, 15, 15, 15],
            "runtime_seconds": [1.0, 1.0, 1.0, 1.0],
            "sql_stage_llm_calls": [1, 1, 2, 2],
            "sql_stage_mcp_calls": [3, 3, 5, 5],
            "profiling_calls_count": [1, 1, 2, 2],
            "sql_stage_sql_executions": [1, 1, 1, 1],
            "table_f1_first": [1.0, 0.0, 1.0, 1.0],
            "table_f1_final": [1.0, 0.0, 1.0, 1.0],
        }
    )

    success_data = _run_level_metrics(frame, "by_system")
    call_data = _run_level_sql_stage_call_breakdown(frame)

    assert success_data["run_id"].tolist() == ["run_1", "run_2"]
    assert success_data["ultimate_success_rate"].tolist() == [0.5, 1.0]
    assert call_data["run_id"].tolist() == ["run_1", "run_2"]
    assert call_data["avg_sql_stage_mcp_resource_calls"].tolist() == [2.0, 3.0]


def test_frontier_scatter_points_keep_runs_and_system_averages() -> None:
    frame = pd.DataFrame(
        {
            "run_id": ["run_1", "run_1", "run_2", "run_2"],
            "system": ["A", "A", "A", "A"],
            "sql_stage_total_tokens": [100, 300, 200, 400],
            "ultimate_success_rate": [1.0, 0.0, 1.0, 1.0],
        }
    )

    run_points = _frontier_run_points(frame, "sql_stage_total_tokens", "ultimate_success_rate")
    average_points = _frontier_average_points(
        frame, "sql_stage_total_tokens", "ultimate_success_rate"
    )

    assert run_points["sql_stage_total_tokens"].tolist() == [200, 300]
    assert run_points["ultimate_success_rate"].tolist() == [0.5, 1.0]
    assert average_points.loc[0, "sql_stage_total_tokens"] == 250
    assert average_points.loc[0, "ultimate_success_rate"] == 0.75


def test_benchmark_limit_is_applied_after_shuffle(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n1,easy,Easy?,\n2,easy,Easy again?,\n3,hard,Hard?,\n",
        encoding="utf-8",
    )

    def fake_shuffle(self, items):
        items.reverse()

    monkeypatch.setattr("evaluation.benchmark.runner.random.Random.shuffle", fake_shuffle)
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_system_a",
        lambda question, **kwargs: _unanswerable_raw_result("A"),
    )

    rows = run_benchmark(
        questions_path=corpus,
        systems=["A"],
        output_dir=tmp_path / "out",
        limit=1,
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
    )

    assert rows[0]["question_id"] == "Q003"


def test_benchmark_reference_sql_executes_for_answerable_questions() -> None:
    database_path = Path("database/benchmark.duckdb")
    if not database_path.exists():
        pytest.skip("benchmark.duckdb fixture is not available")

    questions = load_questions(Path("database/test_queries.csv"))
    for question in questions:
        if not question.answerable:
            continue

        result = execute_for_evaluation(database_path, question.expected_sql or "")

        assert result["success"] is True, question.question_id


def test_ranked_multirow_references_declare_order_required() -> None:
    questions = load_questions(Path("database/test_queries.csv"))

    missing = [
        question.question_id
        for question in questions
        if question.expected_sql
        and _has_multirow_limit(question.expected_sql)
        and not question.requires_ordered_result
    ]

    assert missing == []


def test_ordered_references_use_deterministic_tie_breakers() -> None:
    questions = load_questions(Path("database/test_queries.csv"))

    missing_tie_breakers = [
        question.question_id
        for question in questions
        if question.requires_ordered_result
        and question.expected_sql
        and len(_order_by_expressions(question.expected_sql)) < 2
    ]

    assert missing_tie_breakers == []


def test_system_a_static_context_excludes_metadata_comments_and_glossary() -> None:
    database_path = Path("database/benchmark.duckdb")
    if not database_path.exists():
        pytest.skip("benchmark.duckdb fixture is not available")

    context = build_static_schema_context(database_path)

    assert "Table: dim_customer" in context
    assert "customer_sk BIGINT" in context
    assert "SCD Type 2 customer dimension" not in context
    assert "suffix intentionally marks gross amount ambiguity" not in context
    assert "Stornoquote" not in context
    assert "Cash Realization Rate" not in context


def test_system_a_result_format_for_unanswerable(tmp_path: Path) -> None:
    question = QuestionSpec(
        question_id="Q999",
        difficulty="unanswerable",
        question="Missing?",
        answerable=False,
        expected_behavior="REJECT",
    )

    result = run_system_a(
        question,
        database_path=tmp_path / "unused.duckdb",
        llm=FakeLlm('{"status": "UNANSWERABLE", "sql": null, "reason": "missing"}'),
        schema_context="Table: example",
    )

    assert result["system"] == "A"
    assert result["status"] == "CORRECT_REJECTION"
    assert result["first_generated_sql"] is None
    assert result["trace"]["llm_calls"] == 1
    assert result["trace"]["mcp_calls"] == 0


def test_normalize_runner_result_adds_question_metadata() -> None:
    question = QuestionSpec("Q001", "easy", "How many?", True)
    raw = {"system": "B", "final_generated_sql": "SELECT 1", "trace": {"llm_calls": 1}}

    result = normalize_runner_result(raw, question, system="B")

    assert result["question_id"] == "Q001"
    assert result["difficulty"] == "easy"
    assert result["first_generated_sql"] == "SELECT 1"
    assert result["trace"]["llm_calls"] == 1
    assert result["trace"]["mcp_calls"] == 0
    assert result["trace"]["sql_stage_llm_calls"] == 1
    assert result["trace"]["end_to_end_llm_calls"] == 1


def test_compare_results_ignores_row_order_aliases_and_numeric_noise() -> None:
    actual = {"columns": ["label", "metric"], "rows": [["b", 2.0000001], ["a", 1.0]]}
    expected = {"columns": ["name", "value"], "rows": [["a", 1.0], ["b", 2.0]]}

    assert compare_results(actual, expected)


def test_compare_results_preserves_projection_order_when_columns_are_not_checked() -> None:
    actual = {"columns": ["name", "value", "extra"], "rows": [["a", 1.0, "ignored"]]}
    expected = {"columns": ["value", "name"], "rows": [[1.0, "a"]]}

    details = compare_result_details(actual, expected, allow_projection_match=True)

    assert details.matches is True
    assert details.matched_by_projection is True
    assert details.projection_exact is False


def test_compare_results_accepts_column_name_reordering_without_extra_columns() -> None:
    actual = {
        "columns": ["total_financed", "customer_id", "avg_balance"],
        "rows": [[100.0, "CUST-1", 5.5]],
    }
    expected = {
        "columns": ["customer_id", "total_financed", "avg_balance"],
        "rows": [["CUST-1", 100.0, 5.5]],
    }

    details = compare_result_details(actual, expected)

    assert details.matches is True
    assert details.matched_by_name_reorder is True
    assert details.matched_by_projection is False


def test_compare_results_rejects_extra_columns_by_default() -> None:
    actual = {
        "columns": ["customer_id", "first_name", "last_name", "total_financed", "avg_balance"],
        "rows": [["CUST-1", "Mia", "Wagner", 100.0, 5.5]],
    }
    expected = {
        "columns": ["customer_id", "total_financed", "avg_balance"],
        "rows": [["CUST-1", 100.0, 5.5]],
    }

    details = compare_result_details(actual, expected)

    assert details.matches is False
    assert details.extra_columns is True
    assert details.matched_by_projection is False


def test_compare_results_can_report_legacy_projection_match() -> None:
    actual = {
        "columns": ["customer_id", "first_name", "last_name", "total_financed", "avg_balance"],
        "rows": [["CUST-1", "Mia", "Wagner", 100.0, 5.5]],
    }
    expected = {
        "columns": ["customer_id", "total_financed", "avg_balance"],
        "rows": [["CUST-1", 100.0, 5.5]],
    }

    details = compare_result_details(actual, expected, allow_projection_match=True)

    assert details.matches is True
    assert details.matched_by_projection is True


def test_compare_results_rejects_extra_intermediate_dimension_by_default() -> None:
    actual = {
        "columns": ["calendar_year", "calendar_month", "calendar_month_name", "variance"],
        "rows": [[2023, 1, "January", 12.5]],
    }
    expected = {
        "columns": ["calendar_year", "calendar_month", "gross_interest_variance"],
        "rows": [[2023, 1, 12.5]],
    }

    assert not compare_results(actual, expected)


def test_compare_results_rejects_truncated_results() -> None:
    actual = {
        "success": True,
        "columns": ["value"],
        "rows": [[1]],
        "row_count": 2,
        "truncated": True,
    }
    expected = {
        "success": True,
        "columns": ["value"],
        "rows": [[1]],
        "row_count": 1,
        "truncated": False,
    }

    details = compare_result_details(actual, expected)

    assert details.matches is False
    assert details.result_truncated is True


def test_compare_results_rejects_extra_columns_when_expected_values_are_absent() -> None:
    actual = {
        "columns": ["customer_id", "avg_balance"],
        "rows": [["CUST-1", 5.5]],
    }
    expected = {
        "columns": ["customer_id", "total_financed", "avg_balance"],
        "rows": [["CUST-1", 100.0, 5.5]],
    }

    assert not compare_results(actual, expected)


def test_compare_results_can_enforce_columns_and_row_order() -> None:
    actual = {"success": True, "columns": ["value"], "rows": [[2], [1]]}
    expected = {"success": True, "columns": ["value"], "rows": [[1], [2]]}

    assert compare_results(actual, expected)
    assert not compare_results(actual, expected, respect_row_order=True)
    assert not compare_results(
        {"success": True, "columns": ["other"], "rows": [[1], [2]]},
        expected,
        check_columns=True,
    )


def test_compare_results_rejects_failed_sql_execution_results() -> None:
    actual = {
        "success": False,
        "columns": [],
        "rows": [],
        "error": {"error_type": "BinderException", "message": "missing column"},
    }
    expected = {"success": False, "columns": [], "rows": []}

    assert not compare_results(actual, expected)


def test_unanswerable_detection_and_outcome() -> None:
    question = QuestionSpec("Q046", "unanswerable", "Missing?", False, expected_behavior="REJECT")
    result = {
        "status": "CORRECT_REJECTION",
        "last_error": "UNANSWERABLE",
        "first_generated_sql": None,
        "final_generated_sql": None,
        "final_answer": "not available",
    }

    evaluation = evaluate_run(result, question, database_path="database/benchmark.duckdb")

    assert is_correct_rejection(result)
    assert evaluation.outcome == "CORRECT_REJECTION"
    assert evaluation.ultimate_success is True
    assert evaluation.correct_rejection_evidence == "status:CORRECT_REJECTION"
    assert evaluation.outcome != "UNKNOWN"


def test_free_text_unanswerable_answer_is_not_a_correct_rejection() -> None:
    question = QuestionSpec("Q046", "unanswerable", "Missing?", False, expected_behavior="REJECT")
    result = {
        "status": "ERROR",
        "last_error": None,
        "first_generated_sql": None,
        "final_generated_sql": None,
        "final_answer": "not available",
    }

    evaluation = evaluate_run(result, question, database_path="database/benchmark.duckdb")

    assert not is_correct_rejection(result)
    assert evaluation.outcome == "FALSE_ANSWER"
    assert evaluation.correct_rejection_evidence is None


def test_system_c_first_pass_wrong_ultimate_right(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "How many?",
        True,
        expected_sql="SELECT 1 AS value",
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT 2 AS value",
        "final_generated_sql": "SELECT 1 AS value",
        "execution_result": {"success": True, "columns": ["value"], "rows": [[1]]},
        "last_error": None,
        "iterations": 1,
    }

    def fake_execute(database_path: str | Path, sql: str):
        value = 2 if "SELECT 2" in sql else 1
        return {"success": True, "columns": ["value"], "rows": [[value]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.first_pass_success is False
    assert evaluation.ultimate_success is True
    assert evaluation.outcome == "SUCCESS"


def test_ultimate_success_reexecutes_final_sql_when_stored_result_is_truncated(
    monkeypatch,
) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "List values.",
        True,
        expected_sql="SELECT value FROM example ORDER BY value",
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT value FROM example ORDER BY value",
        "final_generated_sql": "SELECT value FROM example ORDER BY value",
        "execution_result": {
            "success": True,
            "columns": ["value"],
            "rows": [[1]],
            "row_count": 2,
            "truncated": True,
        },
        "last_error": None,
        "iterations": 0,
        "trace": {"retrieved_tables": [], "profiling_calls": 0},
    }

    def fake_execute(database_path: str | Path, sql: str):
        return {
            "success": True,
            "columns": ["value"],
            "rows": [[1], [2]],
            "row_count": 2,
            "truncated": False,
        }

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")
    flat = flatten_result(result, evaluation)

    assert evaluation.ultimate_success is True
    assert flat["stored_result_truncated"] is True
    assert flat["stored_result_row_count"] == 2


def test_ordered_reference_requires_ordered_actual_result(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "Which three values have the highest metric?",
        True,
        expected_sql="SELECT value, metric FROM example ORDER BY metric DESC, value",
        requires_ordered_result=True,
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT value, metric FROM example ORDER BY value DESC",
        "final_generated_sql": "SELECT value, metric FROM example ORDER BY value DESC",
        "execution_result": {
            "success": True,
            "columns": ["value", "metric"],
            "rows": [["b", 1], ["a", 1]],
        },
        "last_error": None,
        "iterations": 0,
    }

    def fake_execute(database_path: str | Path, sql: str):
        if "value DESC" in sql:
            return {
                "success": True,
                "columns": ["value", "metric"],
                "rows": [["b", 1], ["a", 1]],
            }
        return {
            "success": True,
            "columns": ["value", "metric"],
            "rows": [["a", 1], ["b", 1]],
        }

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.ultimate_success is False
    assert evaluation.outcome == "WRONG_RESULT"


def test_reference_aliases_do_not_have_to_match_by_default(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "How many?",
        True,
        expected_sql="SELECT 1 AS expected_value",
    )
    result = {
        "system": "B",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT 1 AS other_value",
        "final_generated_sql": "SELECT 1 AS other_value",
        "execution_result": {"success": True, "columns": ["other_value"], "rows": [[1]]},
        "last_error": None,
    }

    def fake_execute(database_path: str | Path, sql: str):
        return {"success": True, "columns": ["expected_value"], "rows": [[1]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.ultimate_success is True
    assert evaluation.outcome == "SUCCESS"


def test_expected_columns_are_enforced_when_declared(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "How many?",
        True,
        expected_sql="SELECT 1 AS expected_value",
        expected_columns=["expected_value"],
    )
    result = {
        "system": "B",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT 1 AS other_value",
        "final_generated_sql": "SELECT 1 AS other_value",
        "execution_result": {"success": True, "columns": ["other_value"], "rows": [[1]]},
        "last_error": None,
    }

    def fake_execute(database_path: str | Path, sql: str):
        columns = ["expected_value"] if sql == "SELECT 1 AS expected_value" else ["other_value"]
        return {"success": True, "columns": columns, "rows": [[1]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.ultimate_success is False
    assert evaluation.outcome == "WRONG_RESULT"


def test_reference_order_is_not_required_for_plain_lists(monkeypatch) -> None:
    question = QuestionSpec(
        "Q004",
        "easy",
        "List the legal names of current dealers with strongest risk rating.",
        True,
        expected_sql="SELECT name FROM expected ORDER BY name",
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT name FROM actual",
        "final_generated_sql": "SELECT name FROM actual",
        "execution_result": {"success": True, "columns": ["name"], "rows": [["b"], ["a"]]},
        "last_error": None,
    }

    def fake_execute(database_path: str | Path, sql: str):
        if "expected" in sql:
            return {"success": True, "columns": ["name"], "rows": [["a"], ["b"]]}
        return {"success": True, "columns": ["name"], "rows": [["b"], ["a"]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.ultimate_success is True
    assert evaluation.order_required is False
    assert evaluation.order_exact is False


def test_question_order_is_required_for_ranked_results(monkeypatch) -> None:
    question = QuestionSpec(
        "Q021",
        "medium",
        "Which five brands have the most defaulted loan contracts?",
        True,
        expected_sql="SELECT brand, count FROM expected ORDER BY count DESC, brand",
        requires_ordered_result=True,
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT brand, count FROM actual",
        "final_generated_sql": "SELECT brand, count FROM actual",
        "execution_result": {
            "success": True,
            "columns": ["brand", "count"],
            "rows": [["B", 1], ["A", 1]],
        },
        "last_error": None,
    }

    def fake_execute(database_path: str | Path, sql: str):
        if "expected" in sql:
            return {
                "success": True,
                "columns": ["brand", "count"],
                "rows": [["A", 1], ["B", 1]],
            }
        return {
            "success": True,
            "columns": ["brand", "count"],
            "rows": [["B", 1], ["A", 1]],
        }

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.ultimate_success is False
    assert evaluation.order_required is True


def test_system_a_and_b_first_pass_equals_ultimate(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "How many?",
        True,
        expected_sql="SELECT 1 AS value",
    )

    def fake_execute(database_path: str | Path, sql: str):
        value = 2 if "SELECT 2" in sql else 1
        return {"success": True, "columns": ["value"], "rows": [[value]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    for system in ("A", "B"):
        evaluation = evaluate_run(
            {
                "system": system,
                "first_generated_sql": "SELECT 2 AS value",
                "final_generated_sql": "SELECT 1 AS value",
                "execution_result": {"success": True, "columns": ["value"], "rows": [[1]]},
                "last_error": None,
            },
            question,
            database_path="unused.duckdb",
        )

        assert evaluation.first_pass_success == evaluation.ultimate_success
        assert evaluation.first_pass_success is True


def test_answerable_without_reference_warns_and_is_unknown() -> None:
    question = QuestionSpec("Q002", "easy", "How many?", True)
    result = {
        "system": "B",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT 1",
        "final_generated_sql": "SELECT 1",
        "last_error": None,
    }

    with pytest.warns(RuntimeWarning, match="outcome is UNKNOWN"):
        evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.outcome == "UNKNOWN"
    assert evaluation.error_type == "unknown"
    assert evaluation.first_pass_success is None
    assert evaluation.ultimate_success is None


def test_unanswerable_false_answer_is_not_unknown() -> None:
    question = QuestionSpec("Q046", "unanswerable", "Missing?", False, expected_behavior="REJECT")
    result = {
        "system": "A",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT 1",
        "final_generated_sql": "SELECT 1",
        "execution_result": {"success": True, "columns": ["value"], "rows": [[1]]},
        "last_error": None,
        "final_answer": "1",
    }

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.outcome == "FALSE_ANSWER"
    assert evaluation.outcome != "UNKNOWN"
    assert evaluation.ultimate_success is False


def test_answerable_rejection_counts_as_unanswerable_false_positive() -> None:
    question = QuestionSpec("Q001", "easy", "How many?", True, expected_sql="SELECT 1")
    result = {
        "system": "A",
        "status": "CORRECT_REJECTION",
        "first_generated_sql": None,
        "final_generated_sql": None,
        "execution_result": None,
        "last_error": "UNANSWERABLE",
        "final_answer": "UNANSWERABLE",
    }

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")
    rows = [
        {
            "system": "A",
            "answerable": True,
            "correct_rejection": evaluation.correct_rejection,
            "status": result["status"],
            "last_error": result["last_error"],
            "final_answer": result["final_answer"],
            "error_type": evaluation.error_type,
        }
    ]

    assert evaluation.outcome == "FALSE_REJECTION"
    assert evaluation.error_type == "unanswerable"
    assert unanswerable_scores(rows)["A"]["unanswerable_precision"] == 0.0


def test_normalize_answerable_unanswerable_status_is_error() -> None:
    question = QuestionSpec("Q001", "easy", "How many?", True, expected_sql="SELECT 1")
    result = normalize_runner_result(
        {
            "status": "CORRECT_REJECTION",
            "last_error": "UNANSWERABLE",
            "final_answer": "UNANSWERABLE",
        },
        question,
        system="B",
    )

    assert result["status"] == "ERROR"
    assert result["last_error"] == "UNANSWERABLE"


def test_table_f1() -> None:
    precision, recall, f1 = table_f1(
        "SELECT * FROM fact_contracts JOIN dim_customer USING (customer_id)",
        ["fact_contracts", "dim_customer", "dim_date"],
    )

    assert precision == 1.0
    assert recall == 2 / 3
    assert round(f1 or 0, 2) == 0.8


def test_extract_tables_handles_comments_quoted_identifiers_and_subqueries() -> None:
    sql = """
    WITH scoped AS (
      SELECT * FROM cte_source
    )
    SELECT *
    FROM "main"."fact_contracts" AS fc
    JOIN dim_customer AS c ON c.customer_id = fc.customer_id
    JOIN (SELECT 1 AS id FROM nested_source) AS nested ON TRUE
    -- FROM comment_source
    """

    assert extract_tables(sql) == {
        "cte_source",
        "fact_contracts",
        "dim_customer",
        "nested_source",
    }


def test_extract_tables_excludes_cte_names() -> None:
    sql = """
    WITH customer_scope AS (
      SELECT customer_id FROM dim_customer
    )
    SELECT *
    FROM fact_loan_contracts AS l
    JOIN customer_scope AS c ON c.customer_id = l.customer_id
    """

    assert extract_tables(sql) == {"dim_customer", "fact_loan_contracts"}


def test_execute_for_evaluation_passes_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResult:
        def model_dump(self, mode: str):
            return {"success": True, "columns": ["value"], "rows": [[1]]}

    def fake_execute_sql(settings, request):
        captured["timeout_ms"] = request.timeout_ms
        captured["max_rows"] = request.max_rows
        return FakeResult()

    monkeypatch.setenv("EVALUATION_SQL_TIMEOUT_MS", "1234")
    monkeypatch.setattr("evaluation.benchmark.sql_utils.execute_sql", fake_execute_sql)

    result = execute_for_evaluation("unused.duckdb", "SELECT 1")

    assert result["success"] is True
    assert captured == {"timeout_ms": 1234, "max_rows": 1000}


def test_table_f1_uses_reference_sql_when_expected_tables_missing(monkeypatch) -> None:
    question = QuestionSpec(
        "Q001",
        "easy",
        "How many?",
        True,
        expected_sql="SELECT COUNT(*) FROM fact_contracts JOIN dim_customer USING (customer_id)",
    )
    result = {
        "system": "C",
        "status": "SUCCESS",
        "first_generated_sql": "SELECT COUNT(*) FROM fact_contracts",
        "final_generated_sql": (
            "SELECT COUNT(*) FROM fact_contracts JOIN dim_customer USING (customer_id)"
        ),
        "execution_result": {"success": True, "columns": ["count_star()"], "rows": [[1]]},
        "last_error": None,
        "iterations": 1,
    }

    def fake_execute(database_path: str | Path, sql: str):
        return {"success": True, "columns": ["count_star()"], "rows": [[1]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.table_precision_first == 1.0
    assert evaluation.table_recall_first == 0.5
    assert evaluation.table_f1_final == 1.0


def test_system_c_failed_after_max_iterations_gets_specific_outcome(monkeypatch) -> None:
    question = QuestionSpec("Q001", "easy", "How many?", True, expected_sql="SELECT 1 AS value")
    result = {
        "system": "C",
        "status": "ERROR",
        "first_generated_sql": "SELECT missing_column",
        "final_generated_sql": "SELECT missing_column",
        "execution_result": None,
        "last_error": "BinderException: missing column",
        "iterations": 3,
        "max_iterations": 3,
    }

    def fake_execute(database_path: str | Path, sql: str):
        value = 1 if sql == "SELECT 1 AS value" else 2
        return {"success": True, "columns": ["value"], "rows": [[value]]}

    monkeypatch.setattr("evaluation.benchmark.evaluator.execute_for_evaluation", fake_execute)

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.outcome == "MAX_ITERATIONS_FAILED"
    assert evaluation.error_type == "schema_error"
    assert evaluation.ultimate_success is False


def test_runtime_error_is_not_counted_as_unanswerable_false_answer() -> None:
    question = QuestionSpec("Q046", "unanswerable", "Missing?", False, expected_behavior="REJECT")
    result = {
        "system": "B",
        "status": "ERROR",
        "first_generated_sql": None,
        "final_generated_sql": None,
        "last_error": "RUNTIME_ERROR: boom",
        "final_answer": None,
    }

    evaluation = evaluate_run(result, question, database_path="unused.duckdb")

    assert evaluation.outcome == "RUNTIME_ERROR"
    assert evaluation.error_type == "runtime_error"
    assert evaluation.false_answer is False


def test_aggregation_handles_unknown_and_unanswerable_scores() -> None:
    rows = [
        {
            "system": "A",
            "difficulty": "easy",
            "answerable": True,
            "outcome": "UNKNOWN",
            "first_pass_success": None,
            "ultimate_success": None,
            "correct_rejection": False,
            "false_answer": False,
            "iterations": 0,
            "llm_calls": 1,
            "mcp_calls": 0,
            "sql_executions": 0,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "runtime_seconds": 0.1,
            "table_f1_first": None,
            "table_f1_final": None,
        },
        {
            "system": "A",
            "difficulty": "unanswerable",
            "answerable": False,
            "outcome": "CORRECT_REJECTION",
            "first_pass_success": True,
            "ultimate_success": True,
            "correct_rejection": True,
            "false_answer": False,
            "iterations": 0,
            "llm_calls": 1,
            "mcp_calls": 0,
            "sql_executions": 0,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "runtime_seconds": 0.1,
            "table_f1_first": None,
            "table_f1_final": None,
        },
    ]

    summaries = aggregate_metrics(rows)
    scores = unanswerable_scores(rows)

    assert summaries["by_system"].iloc[0]["unknown_rate"] == 0.5
    assert summaries["by_system"].iloc[0]["ultimate_success_rate"] == 1.0
    assert scores["A"]["unanswerable_recall"] == 1.0


def test_critic_recovery_rate_uses_active_critic_cases_only() -> None:
    rows = [
        _metric_row(
            system="C",
            first_pass_success=False,
            ultimate_success=True,
            iterations=1,
            critic_calls=1,
            outcome="SUCCESS",
        ),
        _metric_row(
            system="C",
            first_pass_success=True,
            ultimate_success=True,
            iterations=0,
            outcome="SUCCESS",
        ),
        _metric_row(
            system="C",
            first_pass_success=False,
            ultimate_success=False,
            iterations=2,
            critic_calls=2,
            outcome="SQL_ERROR",
        ),
        _metric_row(
            system="C",
            answerable=False,
            first_pass_success=False,
            ultimate_success=False,
            iterations=1,
            critic_calls=1,
            outcome="CORRECT_REJECTION",
            correct_rejection=True,
        ),
    ]

    summary = aggregate_metrics(rows)["by_system"].iloc[0]

    assert summary["critic_activation_rate"] == 3 / 4
    assert summary["critic_recovery_rate"] == 1 / 3
    assert summary["critic_recovery_rate_answerable"] == 0.5
    assert summary["avg_critic_calls_when_critic_active"] == 4 / 3


def test_failed_after_max_iterations_uses_row_max_iterations() -> None:
    rows = [
        _metric_row(
            system="C",
            first_pass_success=False,
            ultimate_success=False,
            iterations=2,
            max_iterations=2,
            outcome="SQL_ERROR",
        ),
        _metric_row(
            system="C",
            first_pass_success=False,
            ultimate_success=False,
            iterations=2,
            max_iterations=3,
            outcome="SQL_ERROR",
        ),
    ]

    summary = aggregate_metrics(rows)["by_system"].iloc[0]

    assert summary["failed_after_max_iterations"] == 1


def test_benchmark_separates_evaluation_database_from_mcp_transport(
    tmp_path: Path, monkeypatch
) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n", encoding="utf-8"
    )
    database_path = tmp_path / "benchmark.duckdb"
    captured: dict[str, Path | str | None] = {}

    def fake_system_a(question, *, database_path=None, **kwargs):
        captured["A"] = Path(database_path) if database_path is not None else None
        return _unanswerable_raw_result("A")

    def fake_single_shot(question: str, deps, max_iterations: int = 0):
        captured["B"] = deps.mcp.server_url
        return _unanswerable_raw_result("B")

    def fake_critic(question: str, deps, max_iterations: int = 3):
        captured["C"] = deps.mcp.server_url
        return _unanswerable_raw_result("C")

    monkeypatch.setattr("evaluation.benchmark.runner.run_system_a", fake_system_a)
    monkeypatch.setattr(
        "evaluation.benchmark.runner._mcp_dependencies",
        lambda: SimpleNamespace(llm=None, mcp=FakeTransportMcp()),
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_mcp_single_shot_with_dependencies",
        fake_single_shot,
    )
    monkeypatch.setattr("evaluation.benchmark.runner.run_mcp_critic_with_dependencies", fake_critic)

    run_benchmark(
        questions_path=corpus,
        systems=["A", "B", "C"],
        output_dir=tmp_path / "out",
        database_path=database_path,
        skip_plots=True,
    )

    assert captured == {
        "A": database_path,
        "B": "http://mcp.test/sse",
        "C": "http://mcp.test/sse",
    }


def test_benchmark_progress_reports_current_question_and_system(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_system_a",
        lambda question, **kwargs: _unanswerable_raw_result("A"),
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner._mcp_dependencies",
        lambda: SimpleNamespace(llm=None, mcp=FakeTransportMcp()),
    )

    run_benchmark(
        questions_path=corpus,
        systems=["A"],
        output_dir=tmp_path / "out",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
        show_progress=True,
    )

    output = capsys.readouterr().out
    assert "Benchmark started: 1 questions, 1 systems, 1 runs, workers=1." in output
    assert "[question 1/1] Q001 (unanswerable): Missing?" in output
    assert "-> system A started (1/1)" in output
    assert "<- system A finished: outcome=CORRECT_REJECTION" in output


def test_benchmark_progress_groups_parallel_system_results_by_question(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_system_a",
        lambda question, **kwargs: _unanswerable_raw_result("A"),
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner._mcp_dependencies",
        lambda: SimpleNamespace(llm=None, mcp=FakeTransportMcp()),
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_mcp_single_shot_with_dependencies",
        lambda question, deps, max_iterations=0: _unanswerable_raw_result("B"),
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_mcp_critic_with_dependencies",
        lambda question, deps, max_iterations=3: _unanswerable_raw_result("C"),
    )

    rows = run_benchmark(
        questions_path=corpus,
        systems=["A", "B", "C"],
        output_dir=tmp_path / "out",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
        show_progress=True,
        workers=3,
    )

    output = capsys.readouterr().out
    question_position = output.index("[question 1/1] Q001 (unanswerable): Missing?")
    assert question_position < output.index("-> system A started (1/3)")
    assert question_position < output.index("-> system B started (2/3)")
    assert question_position < output.index("-> system C started (3/3)")
    assert "<- system A finished: outcome=CORRECT_REJECTION" in output
    assert "<- system B finished: outcome=CORRECT_REJECTION" in output
    assert "<- system C finished: outcome=CORRECT_REJECTION" in output
    assert [row["system"] for row in rows] == ["A", "B", "C"]


def test_benchmark_parallel_workers_preserve_output_order(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n"
        "1,unanswerable,Missing one?,\n"
        "2,unanswerable,Missing two?,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_system_a",
        lambda question, **kwargs: _unanswerable_raw_result("A"),
    )

    rows = run_benchmark(
        questions_path=corpus,
        systems=["A"],
        output_dir=tmp_path / "out",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
        seed=1,
        workers=2,
    )

    assert [row["question_id"] for row in rows] == ["Q002", "Q001"]
    assert all(row["outcome"] == "CORRECT_REJECTION" for row in rows)


def test_benchmark_continues_when_one_system_raises(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n", encoding="utf-8"
    )

    def broken(question: str, deps, max_iterations: int = 0):
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr("evaluation.benchmark.runner.run_mcp_single_shot_with_dependencies", broken)

    rows = run_benchmark(
        questions_path=corpus,
        systems=["B"],
        output_dir=tmp_path / "out",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
    )

    assert rows[0]["outcome"] == "RUNTIME_ERROR"
    assert rows[0]["error_type"] == "runtime_error"
    assert "RUNTIME_ERROR" in rows[0]["last_error"]
    assert (tmp_path / "out" / "results" / "benchmark_summary_by_error_type.csv").exists()


def test_benchmark_continues_when_evaluation_raises(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text("id,difficulty,question,reference_sql\n1,easy,How many?,SELECT 1\n")

    def broken_evaluate(result, question, *, database_path):
        msg = "reference failed"
        raise RuntimeError(msg)

    monkeypatch.setattr("evaluation.benchmark.runner.evaluate_run", broken_evaluate)

    rows = run_benchmark(
        questions_path=corpus,
        systems=["B"],
        output_dir=tmp_path / "out",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
    )

    assert rows[0]["outcome"] == "RUNTIME_ERROR"
    assert rows[0]["error_type"] == "runtime_error"


def test_benchmark_writes_plots_unless_skipped(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text("id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n")
    calls: list[Path] = []

    def fake_write_plots(input_dir, output_dir=None):
        calls.append((Path(input_dir), Path(output_dir)))

    monkeypatch.setattr("evaluation.plotting.write_plots", fake_write_plots)

    run_benchmark(
        questions_path=corpus,
        systems=["B"],
        output_dir=tmp_path / "with_plots",
        database_path=tmp_path / "unused.duckdb",
    )
    run_benchmark(
        questions_path=corpus,
        systems=["B"],
        output_dir=tmp_path / "without_plots",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=True,
    )

    assert calls == [(tmp_path / "with_plots" / "results", tmp_path / "with_plots")]


def test_benchmark_output_directory_is_self_contained(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text("id,difficulty,question,reference_sql\n1,unanswerable,Missing?,\n")
    monkeypatch.setattr(
        "evaluation.benchmark.runner.run_system_a",
        lambda question, **kwargs: _unanswerable_raw_result("A"),
    )

    run_benchmark(
        questions_path=corpus,
        systems=["A"],
        output_dir=tmp_path / "run_001",
        database_path=tmp_path / "unused.duckdb",
        skip_plots=False,
    )

    assert (tmp_path / "run_001" / "results" / "benchmark_results.csv").exists()
    assert (tmp_path / "run_001" / "tables" / "T01_benchmark_metadata_summary.csv").exists()
    assert (
        tmp_path / "run_001" / "figures" / "01_first_pass_vs_ultimate_success_by_system.svg"
    ).exists()


def test_write_paper_figures_exports_svg_files(tmp_path: Path) -> None:
    rows = [
        _metric_row(system="A", difficulty="easy", ultimate_success=True),
        _metric_row(system="B", difficulty="medium", ultimate_success=True),
        _metric_row(
            system="C",
            difficulty="hard",
            first_pass_success=False,
            ultimate_success=True,
            iterations=1,
        ),
        _metric_row(
            system="C",
            difficulty="unanswerable",
            answerable=False,
            outcome="CORRECT_REJECTION",
            correct_rejection=True,
        ),
    ]

    paths = write_paper_figures(pd.DataFrame(rows), tmp_path)

    assert paths["success_rates"].suffix == ".svg"
    assert paths["success_rates"].exists()
    assert paths["critic_metrics"].exists()
    assert not list(tmp_path.glob("*.png"))


def test_write_paper_figures_uses_readable_display_labels(tmp_path: Path) -> None:
    rows = [
        _metric_row(system="A", difficulty="easy", ultimate_success=True),
        _metric_row(system="B", difficulty="medium", ultimate_success=False),
        _metric_row(
            system="C",
            difficulty="hard",
            first_pass_success=False,
            ultimate_success=True,
            iterations=1,
        ),
    ]

    paths = write_paper_figures(pd.DataFrame(rows), tmp_path)
    svg = paths["success_rates"].read_text(encoding="utf-8")

    assert "first_pass_success_rate" not in svg
    assert "ultimate_success_rate" not in svg
    assert "First Pass" in svg
    assert "Final" in svg


def test_write_paper_figures_uses_aggregate_frontier_scatterplots(tmp_path: Path) -> None:
    rows = [
        _metric_row(system="A", difficulty="easy", ultimate_success=True),
        _metric_row(system="B", difficulty="medium", ultimate_success=False),
        _metric_row(
            system="C",
            difficulty="hard",
            first_pass_success=False,
            ultimate_success=True,
            iterations=1,
        ),
    ]

    paths = write_paper_figures(pd.DataFrame(rows), tmp_path)
    svg = paths["F21"].read_text(encoding="utf-8")

    assert "Average SQL-Stage Tokens" in svg
    assert "Ultimate Success Rate (%)" in svg
    assert "System A" in svg
    assert "ultimate_success" not in svg
    assert "sql_stage_total_tokens" not in svg


def _metric_row(
    *,
    system: str = "A",
    difficulty: str = "easy",
    answerable: bool = True,
    first_pass_success: bool | None = True,
    ultimate_success: bool | None = True,
    iterations: int = 0,
    critic_calls: int = 0,
    max_iterations: int = 3,
    outcome: str = "SUCCESS",
    correct_rejection: bool = False,
    false_answer: bool = False,
) -> dict[str, object]:
    return {
        "system": system,
        "difficulty": difficulty,
        "answerable": answerable,
        "outcome": outcome,
        "first_pass_success": first_pass_success,
        "ultimate_success": ultimate_success,
        "correct_rejection": correct_rejection,
        "false_answer": false_answer,
        "iterations": iterations,
        "critic_calls": critic_calls,
        "max_iterations": max_iterations,
        "llm_calls": 1,
        "mcp_calls": 0,
        "sql_executions": 1,
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
        "runtime_seconds": 0.1,
        "table_f1_first": None,
        "table_f1_final": None,
    }


def _unanswerable_raw_result(system: str) -> dict[str, object]:
    return {
        "system": system,
        "status": "CORRECT_REJECTION",
        "first_generated_sql": None,
        "final_generated_sql": None,
        "final_answer": "UNANSWERABLE",
        "execution_result": None,
        "last_error": "UNANSWERABLE",
        "error_history": ["UNANSWERABLE"],
        "iterations": 0,
        "max_iterations": 0,
        "trace": {
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
        },
    }


def _has_multirow_limit(sql: str) -> bool:
    match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    return bool(match and int(match.group(1)) > 1 and re.search(r"\border\s+by\b", sql, re.I))


def _order_by_expressions(sql: str) -> list[str]:
    match = re.search(
        r"\border\s+by\s+(.*?)(?:\blimit\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return []
    return [part.strip() for part in match.group(1).split(",") if part.strip()]
