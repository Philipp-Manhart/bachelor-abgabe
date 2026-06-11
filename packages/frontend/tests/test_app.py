from __future__ import annotations

from pathlib import Path

import pandas as pd

from frontend.app import choose_chart_type, load_question_examples, result_to_dataframe, trace_rows


def test_load_question_examples_from_csv(tmp_path: Path) -> None:
    corpus = tmp_path / "questions.csv"
    corpus.write_text(
        "id,difficulty,question,reference_sql\n"
        "1,easy,How many?,SELECT 1\n"
        "46,unanswerable,Missing?,\n",
        encoding="utf-8",
    )

    examples = load_question_examples(corpus)

    assert examples[0]["label"] == "Q001 | easy"
    assert examples[0]["answerable"] is True
    assert examples[1]["label"] == "Q046 | unanswerable"
    assert examples[1]["answerable"] is False


def test_result_to_dataframe_for_successful_execution() -> None:
    frame = result_to_dataframe(
        {
            "system": "C",
            "status": "SUCCESS",
            "question": "How many?",
            "first_generated_sql": "SELECT 1 AS value",
            "final_generated_sql": "SELECT 1 AS value",
            "final_answer": "1",
            "execution_result": {
                "success": True,
                "columns": ["value"],
                "rows": [[1]],
            },
            "last_error": None,
            "error_history": [],
            "iterations": 0,
            "trace": {
                "llm_calls": 1,
                "mcp_calls": 2,
                "sql_executions": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "runtime_seconds": 0.1,
                "retrieved_tables": [],
                "profiling_calls": 0,
            },
        }
    )

    assert frame is not None
    assert frame.to_dict(orient="records") == [{"value": 1}]


def test_trace_rows_preserve_core_counters() -> None:
    rows = trace_rows(
        {
            "system": "B",
            "status": "ERROR",
            "question": "Broken?",
            "first_generated_sql": None,
            "final_generated_sql": None,
            "final_answer": "",
            "execution_result": None,
            "last_error": "boom",
            "error_history": ["boom"],
            "iterations": 2,
            "trace": {
                "llm_calls": 3,
                "mcp_calls": 4,
                "sql_executions": 5,
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "runtime_seconds": 1.25,
                "retrieved_tables": ["dim_customer"],
                "profiling_calls": 1,
                "critic_calls": 3,
            },
        }
    )

    values = {row["Metrik"]: row["Wert"] for row in rows}

    assert values["LLM Calls"] == 3
    assert values["MCP Calls"] == 4
    assert values["SQL Executions"] == 5
    assert values["Critic Reviews"] == 3
    assert values["Repair Iterationen"] == 2


def test_choose_chart_type_honors_explicit_request() -> None:
    frame = pd.DataFrame({"segment": ["A", "B"], "customers": [10, 20]})

    assert choose_chart_type("Zeige die Kunden als Liniendiagramm", frame) == "line"


def test_choose_chart_type_picks_bar_chart_for_categories() -> None:
    frame = pd.DataFrame({"segment": ["A", "B"], "customers": [10, 20]})

    assert choose_chart_type("Vergleiche die Kunden nach Segment", frame) == "bar"


def test_choose_chart_type_keeps_single_value_as_table() -> None:
    frame = pd.DataFrame({"customers": [20]})

    assert choose_chart_type("Wie viele Kunden gibt es?", frame) is None
