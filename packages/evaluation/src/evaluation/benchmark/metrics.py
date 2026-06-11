from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Any

import pandas as pd


def aggregate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, pd.DataFrame]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {
            "by_system": pd.DataFrame(),
            "by_difficulty": pd.DataFrame(),
            "by_system_difficulty": pd.DataFrame(),
            "answerability": pd.DataFrame(),
            "by_error_type": pd.DataFrame(),
        }
    if "error_type" not in frame:
        frame["error_type"] = "unknown"
    else:
        frame["error_type"] = frame["error_type"].fillna("unknown")
    _ensure_metric_columns(frame)
    return {
        "by_system": _aggregate(frame, ["system"]),
        "by_difficulty": _aggregate(frame, ["difficulty"]),
        "by_system_difficulty": _aggregate(frame, ["system", "difficulty"]),
        "answerability": _answerability_metrics(frame),
        "by_error_type": _aggregate(frame, ["system", "error_type"]),
    }


def _ensure_metric_columns(frame: pd.DataFrame) -> None:
    defaults: dict[str, Any] = {
        "sql_stage_llm_calls": frame.get("llm_calls", 0),
        "sql_stage_mcp_calls": frame.get("mcp_calls", 0),
        "sql_stage_sql_executions": frame.get("sql_executions", 0),
        "sql_stage_input_tokens": frame.get("input_tokens"),
        "sql_stage_output_tokens": frame.get("output_tokens"),
        "sql_stage_total_tokens": frame.get("total_tokens"),
        "sql_stage_runtime_seconds": frame.get("runtime_seconds", 0.0),
        "answer_synthesis_llm_calls": 0,
        "answer_synthesis_input_tokens": 0,
        "answer_synthesis_output_tokens": 0,
        "answer_synthesis_total_tokens": 0,
        "answer_synthesis_runtime_seconds": 0.0,
        "end_to_end_llm_calls": frame.get("llm_calls", 0),
        "end_to_end_total_tokens": frame.get("total_tokens"),
        "end_to_end_runtime_seconds": frame.get("runtime_seconds", 0.0),
    }
    for column, default in defaults.items():
        if column not in frame:
            frame[column] = default


def unanswerable_scores(
    rows: Sequence[Mapping[str, Any] | Mapping[Hashable, Any]],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for system, system_rows in pd.DataFrame(rows).groupby("system"):
        predicted_rejection = _predicted_unanswerable(system_rows)
        tp = len(system_rows[system_rows["answerable"].eq(False) & predicted_rejection])
        fp = len(system_rows[system_rows["answerable"].eq(True) & predicted_rejection])
        fn = len(system_rows[system_rows["answerable"].eq(False) & ~predicted_rejection])
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        scores[str(system)] = {
            "unanswerable_precision": precision,
            "unanswerable_recall": recall,
            "unanswerable_f1": _safe_div(2 * precision * recall, precision + recall),
        }
    return scores


def _predicted_unanswerable(frame: pd.DataFrame) -> pd.Series:
    last_error = _string_column(frame, "last_error")
    status = _string_column(frame, "status")
    error_type = _string_column(frame, "error_type")
    evidence = _string_column(frame, "correct_rejection_evidence")
    return (
        frame["correct_rejection"].eq(True)
        | evidence.ne("")
        | status.eq("UNANSWERABLE")
        | status.eq("CORRECT_REJECTION")
        | last_error.eq("UNANSWERABLE")
        | error_type.eq("unanswerable")
    )


def _string_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series("", index=frame.index)
    return frame[column].fillna("").astype(str)


def _aggregate(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped_rows: list[dict[str, Any]] = []
    for group_key, group in frame.groupby(group_cols, dropna=False):
        row = _base_group_row(group)
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        row.update(dict(zip(group_cols, group_key, strict=True)))
        if "system" in group_cols and row.get("system") == "C":
            row.update(_critic_metrics(group))
        grouped_rows.append(row)
    return pd.DataFrame(grouped_rows)


def _answerability_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    rows = _aggregate(frame, ["system", "answerable"])
    scores = unanswerable_scores(frame.to_dict(orient="records"))
    if rows.empty:
        return rows
    for index, row in rows.iterrows():
        for key, value in scores.get(str(row["system"]), {}).items():
            rows.loc[index, key] = value
    return rows


def _base_group_row(group: pd.DataFrame) -> dict[str, Any]:
    evaluable = group[group["outcome"] != "UNKNOWN"]
    return {
        "num_cases": len(group),
        "num_evaluable_cases": len(evaluable),
        "first_pass_success_rate": _mean_bool(evaluable["first_pass_success"]),
        "ultimate_success_rate": _mean_bool(evaluable["ultimate_success"]),
        "correct_rejection_rate": _mean_bool(group["correct_rejection"]),
        "false_answer_rate": _mean_bool(group["false_answer"]),
        "unknown_rate": _safe_div(len(group[group["outcome"] == "UNKNOWN"]), len(group)),
        "avg_iterations": _mean_number(group["iterations"]),
        "avg_critic_calls": _mean_number(group.get("critic_calls", pd.Series(dtype=float))),
        "avg_critic_llm_calls": _mean_number(group.get("critic_llm_calls", pd.Series(dtype=float))),
        "avg_critic_input_tokens": _mean_number(
            group.get("critic_input_tokens", pd.Series(dtype=float))
        ),
        "avg_critic_output_tokens": _mean_number(
            group.get("critic_output_tokens", pd.Series(dtype=float))
        ),
        "avg_critic_total_tokens": _mean_number(
            group.get("critic_total_tokens", pd.Series(dtype=float))
        ),
        "avg_llm_calls": _mean_number(group["llm_calls"]),
        "avg_mcp_calls": _mean_number(group["mcp_calls"]),
        "avg_sql_executions": _mean_number(group["sql_executions"]),
        "avg_input_tokens": _mean_number(group["input_tokens"]),
        "avg_output_tokens": _mean_number(group["output_tokens"]),
        "avg_total_tokens": _mean_number(group["total_tokens"]),
        "avg_runtime_seconds": _mean_number(group["runtime_seconds"]),
        "avg_sql_stage_llm_calls": _mean_number(group["sql_stage_llm_calls"]),
        "avg_sql_stage_mcp_calls": _mean_number(group["sql_stage_mcp_calls"]),
        "avg_sql_stage_sql_executions": _mean_number(group["sql_stage_sql_executions"]),
        "avg_sql_stage_input_tokens": _mean_number(group["sql_stage_input_tokens"]),
        "avg_sql_stage_output_tokens": _mean_number(group["sql_stage_output_tokens"]),
        "avg_sql_stage_total_tokens": _mean_number(group["sql_stage_total_tokens"]),
        "avg_sql_stage_runtime_seconds": _mean_number(group["sql_stage_runtime_seconds"]),
        "avg_answer_synthesis_llm_calls": _mean_number(group["answer_synthesis_llm_calls"]),
        "avg_answer_synthesis_input_tokens": _mean_number(group["answer_synthesis_input_tokens"]),
        "avg_answer_synthesis_output_tokens": _mean_number(group["answer_synthesis_output_tokens"]),
        "avg_answer_synthesis_total_tokens": _mean_number(group["answer_synthesis_total_tokens"]),
        "avg_answer_synthesis_runtime_seconds": _mean_number(
            group["answer_synthesis_runtime_seconds"]
        ),
        "avg_end_to_end_llm_calls": _mean_number(group["end_to_end_llm_calls"]),
        "avg_end_to_end_total_tokens": _mean_number(group["end_to_end_total_tokens"]),
        "avg_end_to_end_runtime_seconds": _mean_number(group["end_to_end_runtime_seconds"]),
        "stored_result_truncation_rate": _mean_bool(group["stored_result_truncated"])
        if "stored_result_truncated" in group
        else 0.0,
        "avg_stored_result_row_count": _mean_number(group["stored_result_row_count"])
        if "stored_result_row_count" in group
        else None,
        "avg_table_f1_first": _mean_number(group["table_f1_first"]),
        "avg_table_f1_final": _mean_number(group["table_f1_final"]),
    }


def _critic_metrics(group: pd.DataFrame) -> dict[str, Any]:
    critic_calls = pd.to_numeric(
        group.get("critic_calls", pd.Series(index=group.index, dtype=float)),
        errors="coerce",
    ).fillna(0)
    active = group[critic_calls > 0]
    recovered = active[active["first_pass_success"].eq(False) & active["ultimate_success"].eq(True)]
    active_answerable = active[active["answerable"].eq(True)]
    recovered_answerable = active_answerable[
        active_answerable["first_pass_success"].eq(False)
        & active_answerable["ultimate_success"].eq(True)
    ]
    max_iterations_source = group.get("max_iterations", pd.Series(index=group.index, dtype=float))
    max_iterations = pd.to_numeric(max_iterations_source, errors="coerce")
    exhausted = group[
        max_iterations.notna()
        & (pd.to_numeric(group["iterations"], errors="coerce") >= max_iterations)
        & group["ultimate_success"].ne(True)
    ]
    return {
        "critic_activation_rate": _safe_div(len(active), len(group)),
        "critic_recovery_rate": _safe_div(len(recovered), len(active)),
        "critic_recovery_rate_answerable": _safe_div(
            len(recovered_answerable), len(active_answerable)
        ),
        "avg_iterations_when_critic_active": _mean_number(active["iterations"]),
        "avg_critic_calls_when_critic_active": _mean_number(active["critic_calls"])
        if "critic_calls" in active
        else None,
        "failed_after_max_iterations": len(exhausted),
    }


def _mean_bool(series: pd.Series) -> float:
    clean = series.dropna()
    return 0.0 if clean.empty else float(clean.astype(bool).mean())


def _mean_number(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return None if clean.empty else float(clean.mean())


def _safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else float(numerator / denominator)
