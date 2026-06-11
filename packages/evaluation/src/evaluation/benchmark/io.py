from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from evaluation.benchmark.models import QuestionSpec


def load_questions(path: str | Path, *, limit: int | None = None) -> list[QuestionSpec]:
    question_path = Path(path)
    if question_path.suffix.lower() == ".jsonl":
        questions = _load_jsonl(question_path)
    else:
        questions = _load_csv(question_path)
    return questions[:limit] if limit is not None else questions


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str))
            file.write("\n")


def _load_csv(path: Path) -> list[QuestionSpec]:
    with path.open(encoding="utf-8", newline="") as file:
        return [_row_to_question(row) for row in csv.DictReader(file)]


def _load_jsonl(path: Path) -> list[QuestionSpec]:
    questions: list[QuestionSpec] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                questions.append(_row_to_question(json.loads(line)))
    return questions


def _row_to_question(row: dict[str, Any]) -> QuestionSpec:
    raw_id = str(row.get("question_id") or row.get("id") or "").strip()
    question_id = raw_id if raw_id.startswith("Q") else f"Q{int(raw_id):03d}"
    difficulty = str(row.get("difficulty") or "unknown").strip()
    answerable = _bool_value(row.get("answerable"), default=difficulty != "unanswerable")
    expected_sql = _optional_text(row.get("expected_sql") or row.get("reference_sql"))
    expected_behavior = "ANSWER" if answerable else "REJECT"
    return QuestionSpec(
        question_id=question_id,
        difficulty=difficulty,
        question=str(row.get("question") or "").strip(),
        answerable=answerable,
        expected_sql=expected_sql,
        expected_result=row.get("expected_result"),
        expected_behavior=expected_behavior,
        expected_tables=_list_value(row.get("expected_tables")),
        expected_columns=_list_value(row.get("expected_columns")),
        requires_ordered_result=_bool_value(row.get("order_required"), default=False),
        evaluation_note=_optional_text(row.get("evaluation_note")),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _list_value(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if text.startswith("["):
        parsed = json.loads(text)
        return [str(item) for item in parsed if str(item).strip()]
    return [item.strip() for item in text.split(";") if item.strip()]
