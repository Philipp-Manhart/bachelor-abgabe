from __future__ import annotations

import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evaluation.benchmark.models import EvaluationResult, QuestionSpec
from evaluation.benchmark.sql_utils import (
    ComparisonResult,
    compare_result_details,
    execute_for_evaluation,
    extract_tables,
    table_f1,
)


def normalize_runner_result(
    raw: Mapping[str, Any], question: QuestionSpec, *, system: str
) -> dict[str, Any]:
    trace = _complete_trace(raw.get("trace") if isinstance(raw.get("trace"), dict) else {})
    iterations = int(raw.get("iterations") or 0)
    if system in {"A", "B"}:
        iterations = 0
    status = raw.get("status") or _status_from_error(raw.get("last_error"))
    if question.answerable and status == "CORRECT_REJECTION":
        status = "ERROR"
    return {
        "system": system,
        "status": status,
        "question_id": question.question_id,
        "difficulty": question.difficulty,
        "answerable": question.answerable,
        "question": question.question,
        "first_generated_sql": raw.get("first_generated_sql") or raw.get("final_generated_sql"),
        "final_generated_sql": raw.get("final_generated_sql"),
        "final_answer": raw.get("final_answer"),
        "execution_result": raw.get("execution_result"),
        "last_error": raw.get("last_error"),
        "error_history": list(raw.get("error_history") or []),
        "iterations": iterations,
        "max_iterations": raw.get("max_iterations"),
        "trace": trace,
        "analysis_plan": raw.get("analysis_plan"),
        "metadata_context": raw.get("metadata_context"),
        "profiling_observations": raw.get("profiling_observations"),
        "critic_decision": raw.get("critic_decision"),
        "critic_calls": int(raw.get("critic_calls") or trace.get("critic_calls") or 0),
        "evaluation_note": question.evaluation_note,
    }


def evaluate_run(
    result: dict[str, Any], question: QuestionSpec, *, database_path: str | Path
) -> EvaluationResult:
    expected_tables = _expected_tables(question)
    rejection_evidence = correct_rejection_evidence(result)
    first_precision, first_recall, first_f1 = table_f1(
        result.get("first_generated_sql"), expected_tables
    )
    final_precision, final_recall, final_f1 = table_f1(
        result.get("final_generated_sql"), expected_tables
    )

    if _is_runtime_error(result.get("last_error")):
        return _result(
            False,
            False,
            False,
            False,
            "RUNTIME_ERROR",
            "runtime_error",
            first_precision,
            first_recall,
            first_f1,
            final_precision,
            final_recall,
            final_f1,
        )

    if not question.answerable:
        correct_rejection = rejection_evidence is not None
        false_answer = not correct_rejection
        return EvaluationResult(
            first_pass_success=correct_rejection,
            ultimate_success=correct_rejection,
            correct_rejection=correct_rejection,
            false_answer=false_answer,
            outcome="CORRECT_REJECTION" if correct_rejection else "FALSE_ANSWER",
            error_type="unanswerable" if correct_rejection else "unknown",
            table_precision_first=first_precision,
            table_recall_first=first_recall,
            table_f1_first=first_f1,
            table_precision_final=final_precision,
            table_recall_final=final_recall,
            table_f1_final=final_f1,
            correct_rejection_evidence=rejection_evidence,
        )

    if rejection_evidence is not None:
        return _result(
            False,
            False,
            False,
            False,
            "FALSE_REJECTION",
            "unanswerable",
            first_precision,
            first_recall,
            first_f1,
            final_precision,
            final_recall,
            final_f1,
            correct_rejection_evidence=rejection_evidence,
        )

    if not question.expected_sql and question.expected_result is None:
        warnings.warn(
            (
                f"{question.question_id} is answerable but has no reference_sql or "
                "expected_result; benchmark outcome is UNKNOWN."
            ),
            RuntimeWarning,
            stacklevel=2,
        )
        return _result(
            None,
            None,
            False,
            False,
            "UNKNOWN",
            "unknown",
            first_precision,
            first_recall,
            first_f1,
            final_precision,
            final_recall,
            final_f1,
        )

    first_comparison = _sql_matches_reference(
        result.get("first_generated_sql"), question, database_path
    )
    ultimate_comparison = _ultimate_success(result, question, database_path)
    first_success = first_comparison.matches
    ultimate_success = ultimate_comparison.matches
    if result.get("system") in {"A", "B"}:
        first_success = ultimate_success
    if ultimate_success:
        outcome = "SUCCESS"
        error_type = "none"
    elif _failed_after_max_iterations(result):
        outcome = "MAX_ITERATIONS_FAILED"
        error_type = classify_error(result.get("last_error"))
    elif result.get("last_error"):
        outcome = "SQL_ERROR"
        error_type = classify_error(result.get("last_error"))
    else:
        outcome = "WRONG_RESULT"
        error_type = "unknown"
    return _result(
        first_success,
        ultimate_success,
        False,
        False,
        outcome,
        error_type,
        first_precision,
        first_recall,
        first_f1,
        final_precision,
        final_recall,
        final_f1,
        ultimate_comparison.order_required,
        ultimate_comparison.order_exact,
        ultimate_comparison.projection_exact,
        ultimate_comparison.extra_columns,
        ultimate_comparison.missing_expected_columns,
        ultimate_comparison.matched_by_projection,
        ultimate_comparison.matched_by_name_reorder,
        ultimate_comparison.result_truncated,
        rejection_evidence,
    )


def is_correct_rejection(result: dict[str, Any]) -> bool:
    return correct_rejection_evidence(result) is not None


def correct_rejection_evidence(result: dict[str, Any]) -> str | None:
    if result.get("status") == "CORRECT_REJECTION":
        return "status:CORRECT_REJECTION"
    if result.get("status") == "UNANSWERABLE":
        return "status:UNANSWERABLE"
    if result.get("last_error") == "UNANSWERABLE":
        return "last_error:UNANSWERABLE"
    return None


def classify_error(error: Any) -> str:
    text = str(error or "").casefold()
    if "syntax" in text or "parser" in text:
        return "syntax_error"
    if "binder" in text or "column" in text or "table" in text:
        return "schema_error"
    if "unsafe" in text or "blocked" in text:
        return "security_error"
    if "runtime" in text:
        return "runtime_error"
    return "unknown"


def flatten_result(result: dict[str, Any], evaluation: EvaluationResult) -> dict[str, Any]:
    trace = _complete_trace(result.get("trace"))
    stored_execution_result = result.get("execution_result")
    return {
        **{
            key: value
            for key, value in result.items()
            if key
            not in {
                "trace",
                "execution_result",
                "error_history",
                "analysis_plan",
                "metadata_context",
                "profiling_observations",
            }
        },
        "first_pass_success": evaluation.first_pass_success,
        "ultimate_success": evaluation.ultimate_success,
        "correct_rejection": evaluation.correct_rejection,
        "false_answer": evaluation.false_answer,
        "outcome": evaluation.outcome,
        "error_type": evaluation.error_type,
        "llm_calls": trace["llm_calls"],
        "mcp_calls": trace["mcp_calls"],
        "sql_executions": trace["sql_executions"],
        "input_tokens": trace["input_tokens"],
        "output_tokens": trace["output_tokens"],
        "total_tokens": trace["total_tokens"],
        "runtime_seconds": trace["runtime_seconds"],
        "sql_stage_llm_calls": trace["sql_stage_llm_calls"],
        "sql_stage_mcp_calls": trace["sql_stage_mcp_calls"],
        "sql_stage_sql_executions": trace["sql_stage_sql_executions"],
        "sql_stage_input_tokens": trace["sql_stage_input_tokens"],
        "sql_stage_output_tokens": trace["sql_stage_output_tokens"],
        "sql_stage_total_tokens": trace["sql_stage_total_tokens"],
        "sql_stage_runtime_seconds": trace["sql_stage_runtime_seconds"],
        "answer_synthesis_llm_calls": trace["answer_synthesis_llm_calls"],
        "answer_synthesis_input_tokens": trace["answer_synthesis_input_tokens"],
        "answer_synthesis_output_tokens": trace["answer_synthesis_output_tokens"],
        "answer_synthesis_total_tokens": trace["answer_synthesis_total_tokens"],
        "answer_synthesis_runtime_seconds": trace["answer_synthesis_runtime_seconds"],
        "end_to_end_llm_calls": trace["end_to_end_llm_calls"],
        "end_to_end_total_tokens": trace["end_to_end_total_tokens"],
        "end_to_end_runtime_seconds": trace["end_to_end_runtime_seconds"],
        "retrieved_tables_count": len(trace["retrieved_tables"]),
        "profiling_calls_count": trace["profiling_calls"],
        "critic_calls": trace["critic_calls"],
        "critic_llm_calls": trace["critic_llm_calls"],
        "critic_input_tokens": trace["critic_input_tokens"],
        "critic_output_tokens": trace["critic_output_tokens"],
        "critic_total_tokens": trace["critic_total_tokens"],
        "stored_result_truncated": _stored_result_truncated(stored_execution_result),
        "stored_result_row_count": _stored_result_row_count(stored_execution_result),
        "table_precision_first": evaluation.table_precision_first,
        "table_recall_first": evaluation.table_recall_first,
        "table_f1_first": evaluation.table_f1_first,
        "table_precision_final": evaluation.table_precision_final,
        "table_recall_final": evaluation.table_recall_final,
        "table_f1_final": evaluation.table_f1_final,
        "order_required": evaluation.order_required,
        "order_exact": evaluation.order_exact,
        "projection_exact": evaluation.projection_exact,
        "extra_columns": evaluation.extra_columns,
        "missing_expected_columns": evaluation.missing_expected_columns,
        "matched_by_projection": evaluation.matched_by_projection,
        "matched_by_name_reorder": evaluation.matched_by_name_reorder,
        "result_truncated": evaluation.result_truncated,
        "correct_rejection_evidence": evaluation.correct_rejection_evidence,
    }


def _ultimate_success(
    result: dict[str, Any], question: QuestionSpec, database_path: str | Path
) -> ComparisonResult:
    actual = (
        execute_for_evaluation(database_path, result["final_generated_sql"])
        if result.get("final_generated_sql")
        else result.get("execution_result")
    )
    expected = _expected_result(question, database_path)
    return compare_result_details(
        actual,
        expected,
        check_columns=bool(question.expected_columns),
        expected_columns=question.expected_columns,
        respect_row_order=_requires_ordered_result(question),
    )


def _sql_matches_reference(
    sql: str | None, question: QuestionSpec, database_path: str | Path
) -> ComparisonResult:
    if not sql:
        expected = _expected_result(question, database_path)
        return compare_result_details(
            None,
            expected,
            check_columns=bool(question.expected_columns),
            expected_columns=question.expected_columns,
            respect_row_order=_requires_ordered_result(question),
        )
    expected = _expected_result(question, database_path)
    actual = execute_for_evaluation(database_path, sql)
    return compare_result_details(
        actual,
        expected,
        check_columns=bool(question.expected_columns),
        expected_columns=question.expected_columns,
        respect_row_order=_requires_ordered_result(question),
    )


def _expected_result(question: QuestionSpec, database_path: str | Path) -> Any:
    if question.expected_sql:
        return execute_for_evaluation(database_path, question.expected_sql)
    return question.expected_result


def _requires_ordered_result(question: QuestionSpec) -> bool:
    return question.requires_ordered_result


def _stored_result_truncated(execution_result: Any) -> bool:
    return bool(execution_result.get("truncated")) if isinstance(execution_result, dict) else False


def _stored_result_row_count(execution_result: Any) -> int | None:
    if not isinstance(execution_result, dict):
        return None
    row_count = execution_result.get("row_count")
    if isinstance(row_count, int):
        return row_count
    rows = execution_result.get("rows")
    return len(rows) if isinstance(rows, list) else None


def _expected_tables(question: QuestionSpec) -> list[str]:
    if question.expected_tables:
        return question.expected_tables
    return sorted(extract_tables(question.expected_sql))


def _is_runtime_error(error: Any) -> bool:
    return classify_error(error) == "runtime_error"


def _failed_after_max_iterations(result: dict[str, Any]) -> bool:
    if result.get("system") != "C":
        return False
    max_iterations = int(result.get("max_iterations") or 3)
    return int(result.get("iterations") or 0) >= max_iterations and result.get("last_error")


def _result(
    first: bool | None,
    ultimate: bool | None,
    correct_rejection: bool,
    false_answer: bool,
    outcome,
    error_type,
    first_precision: float | None,
    first_recall: float | None,
    first_f1: float | None,
    final_precision: float | None,
    final_recall: float | None,
    final_f1: float | None,
    order_required: bool | None = None,
    order_exact: bool | None = None,
    projection_exact: bool | None = None,
    extra_columns: bool | None = None,
    missing_expected_columns: bool | None = None,
    matched_by_projection: bool | None = None,
    matched_by_name_reorder: bool | None = None,
    result_truncated: bool | None = None,
    correct_rejection_evidence: str | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        first,
        ultimate,
        correct_rejection,
        false_answer,
        outcome,
        error_type,
        first_precision,
        first_recall,
        first_f1,
        final_precision,
        final_recall,
        final_f1,
        order_required,
        order_exact,
        projection_exact,
        extra_columns,
        missing_expected_columns,
        matched_by_projection,
        matched_by_name_reorder,
        result_truncated,
        correct_rejection_evidence,
    )


def _complete_trace(trace: Any) -> dict[str, Any]:
    source = trace if isinstance(trace, dict) else {}
    completed = {
        "llm_calls": int(source.get("llm_calls") or 0),
        "mcp_calls": int(source.get("mcp_calls") or 0),
        "sql_executions": int(source.get("sql_executions") or 0),
        "input_tokens": source.get("input_tokens"),
        "output_tokens": source.get("output_tokens"),
        "total_tokens": source.get("total_tokens"),
        "runtime_seconds": float(source.get("runtime_seconds") or 0.0),
        "retrieved_tables": list(source.get("retrieved_tables") or []),
        "profiling_calls": int(source.get("profiling_calls") or 0),
        "critic_calls": int(source.get("critic_calls") or 0),
        "critic_llm_calls": int(source.get("critic_llm_calls") or 0),
        "critic_input_tokens": _optional_int(source.get("critic_input_tokens")) or 0,
        "critic_output_tokens": _optional_int(source.get("critic_output_tokens")) or 0,
        "critic_total_tokens": _optional_int(source.get("critic_total_tokens")) or 0,
    }
    sql_stage_total_tokens = source.get("sql_stage_total_tokens")
    if sql_stage_total_tokens is None:
        sql_stage_total_tokens = completed["total_tokens"]
    completed.update(
        {
            "sql_stage_llm_calls": int(
                source.get("sql_stage_llm_calls", completed["llm_calls"]) or 0
            ),
            "sql_stage_mcp_calls": int(
                source.get("sql_stage_mcp_calls", completed["mcp_calls"]) or 0
            ),
            "sql_stage_sql_executions": int(
                source.get("sql_stage_sql_executions", completed["sql_executions"]) or 0
            ),
            "sql_stage_input_tokens": _optional_int(
                source.get("sql_stage_input_tokens", completed["input_tokens"])
            ),
            "sql_stage_output_tokens": _optional_int(
                source.get("sql_stage_output_tokens", completed["output_tokens"])
            ),
            "sql_stage_total_tokens": _optional_int(sql_stage_total_tokens),
            "sql_stage_runtime_seconds": float(
                source.get("sql_stage_runtime_seconds", completed["runtime_seconds"]) or 0.0
            ),
            "answer_synthesis_llm_calls": int(source.get("answer_synthesis_llm_calls") or 0),
            "answer_synthesis_input_tokens": _optional_int(
                source.get("answer_synthesis_input_tokens")
            ),
            "answer_synthesis_output_tokens": _optional_int(
                source.get("answer_synthesis_output_tokens")
            ),
            "answer_synthesis_total_tokens": _optional_int(
                source.get("answer_synthesis_total_tokens")
            ),
            "answer_synthesis_runtime_seconds": float(
                source.get("answer_synthesis_runtime_seconds") or 0.0
            ),
            "end_to_end_llm_calls": int(
                source.get("end_to_end_llm_calls", completed["llm_calls"]) or 0
            ),
            "end_to_end_total_tokens": _optional_int(
                source.get("end_to_end_total_tokens", completed["total_tokens"])
            ),
            "end_to_end_runtime_seconds": float(
                source.get("end_to_end_runtime_seconds", completed["runtime_seconds"]) or 0.0
            ),
        }
    )
    return completed


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _status_from_error(error: Any) -> str:
    if error == "UNANSWERABLE":
        return "CORRECT_REJECTION"
    return "ERROR" if error else "SUCCESS"
