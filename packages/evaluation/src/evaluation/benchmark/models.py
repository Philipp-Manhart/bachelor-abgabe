from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SystemName = Literal["A", "B", "C"]
Outcome = Literal[
    "SUCCESS",
    "SQL_ERROR",
    "WRONG_RESULT",
    "CORRECT_REJECTION",
    "FALSE_REJECTION",
    "FALSE_ANSWER",
    "MAX_ITERATIONS_FAILED",
    "RUNTIME_ERROR",
    "UNKNOWN",
]
ErrorType = Literal[
    "none",
    "syntax_error",
    "schema_error",
    "join_error",
    "filter_error",
    "aggregation_error",
    "empty_result",
    "unanswerable",
    "security_error",
    "runtime_error",
    "json_parse_error",
    "missing_reference",
    "unknown",
]


@dataclass(frozen=True)
class QuestionSpec:
    question_id: str
    difficulty: str
    question: str
    answerable: bool
    expected_sql: str | None = None
    expected_result: Any | None = None
    expected_behavior: Literal["ANSWER", "REJECT"] = "ANSWER"
    expected_tables: list[str] = field(default_factory=list)
    expected_columns: list[str] = field(default_factory=list)
    requires_ordered_result: bool = False
    evaluation_note: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    first_pass_success: bool | None
    ultimate_success: bool | None
    correct_rejection: bool
    false_answer: bool
    outcome: Outcome
    error_type: ErrorType
    table_precision_first: float | None = None
    table_recall_first: float | None = None
    table_f1_first: float | None = None
    table_precision_final: float | None = None
    table_recall_final: float | None = None
    table_f1_final: float | None = None
    order_required: bool | None = None
    order_exact: bool | None = None
    projection_exact: bool | None = None
    extra_columns: bool | None = None
    missing_expected_columns: bool | None = None
    matched_by_projection: bool | None = None
    matched_by_name_reorder: bool | None = None
    result_truncated: bool | None = None
    correct_rejection_evidence: str | None = None
