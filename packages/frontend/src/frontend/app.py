from __future__ import annotations

import csv
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal, TypedDict

import pandas as pd
import streamlit as st

from agent_orchestrator import stream_mcp_critic, stream_mcp_single_shot
from agent_orchestrator.config import PROJECT_ROOT
from agent_orchestrator.types import RunnerEvent, RunnerResult

SystemId = Literal["B", "C"]
StreamRunner = Callable[[str, int], Iterator[RunnerEvent]]

QUESTIONS_PATH = PROJECT_ROOT / "database" / "test_queries.csv"


class QuestionExample(TypedDict):
    label: str
    question: str
    difficulty: str
    answerable: bool


class Activity(TypedDict):
    node: str
    title: str
    detail: str
    calls: list[str]
    status: Literal["ok", "error", "running"]


NODE_TITLES = {
    "interpret_request": "Anfrage interpretieren",
    "retrieve_context": "Schema und Glossar abrufen",
    "profile_data": "Datenprofil prüfen",
    "generate_sql": "SQL generieren",
    "validate_sql": "SQL validieren",
    "execute_sql": "SQL ausführen",
    "critic_reflection": "Critic-Reflection",
    "synthesize_answer": "Antwort synthetisieren",
}

NODE_CALLS = {
    "interpret_request": ["LLM: bi_eda_workflow"],
    "retrieve_context": [
        "Resource: dwh://schema/overview",
        "Resource: dwh://schema/tables/{name}",
        "Resource: dwh://schema/relationships",
        "Resource: dwh://business_glossary/{term}",
    ],
    "profile_data": [
        "Tool: get_sample_data",
        "Tool: get_categorical_values",
        "Tool: get_numeric_summary",
    ],
    "generate_sql": ["LLM: sql_generation_rules"],
    "validate_sql": ["Tool: validate_sql"],
    "execute_sql": ["Tool: execute_sql"],
    "critic_reflection": ["LLM: critic_reflection_rules"],
    "synthesize_answer": ["LLM: Antwortsynthese"],
}

CHART_LABELS = {
    "bar": "Balkendiagramm",
    "line": "Liniendiagramm",
    "area": "Flächendiagramm",
    "scatter": "Streudiagramm",
}


def render_app() -> None:
    st.set_page_config(
        page_title="Agentic BI MCP Demo",
        page_icon="BI",
        layout="centered",
    )
    _inject_styles()

    examples = load_question_examples(QUESTIONS_PATH)

    _render_intro()

    question, system, max_iterations, run_requested = _question_input(examples)

    if run_requested:
        st.session_state["latest_question"] = question.strip()
        st.session_state["latest_activities"] = []
        st.session_state["latest_result"] = None
        with st.chat_message("user"):
            st.write(question.strip())
        with st.chat_message("assistant"):
            activity_panel = st.expander("Analyse läuft...", expanded=True)
            with activity_panel:
                activity_slot = st.empty()
            result_slot = st.empty()
        _run_streamed_demo(
            question=question.strip(),
            system=system,
            max_iterations=0 if system == "B" else max_iterations,
            activity_slot=activity_slot,
            result_slot=result_slot,
        )
        return

    activities = st.session_state.get("latest_activities", [])
    result = st.session_state.get("latest_result")
    latest_question = st.session_state.get("latest_question")
    if latest_question:
        with st.chat_message("user"):
            st.write(str(latest_question))
    if result is None:
        return

    with st.chat_message("assistant"):
        with st.expander("Analyseverlauf", expanded=False):
            activity_slot = st.empty()
            _render_activities(activity_slot, activities, running=False)
        _render_result(result, str(latest_question or ""))


def load_question_examples(path: str | Path) -> list[QuestionExample]:
    question_path = Path(path)
    if not question_path.exists():
        return []

    examples: list[QuestionExample] = []
    with question_path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            question = str(row.get("question") or "").strip()
            if not question:
                continue
            difficulty = str(row.get("difficulty") or "unknown").strip()
            raw_id = str(row.get("id") or row.get("question_id") or "").strip()
            question_id = raw_id if raw_id.startswith("Q") else f"Q{int(raw_id):03d}"
            answerable = difficulty.casefold() != "unanswerable"
            examples.append(
                {
                    "label": f"{question_id} | {difficulty}",
                    "question": question,
                    "difficulty": difficulty,
                    "answerable": answerable,
                }
            )
    return examples


def result_to_dataframe(result: RunnerResult) -> pd.DataFrame | None:
    execution_result = result.get("execution_result")
    if not isinstance(execution_result, dict):
        return None
    if execution_result.get("success") is not True:
        return None

    columns = execution_result.get("columns")
    rows = execution_result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None
    return pd.DataFrame(rows, columns=[str(column) for column in columns])


def trace_rows(result: RunnerResult) -> list[dict[str, Any]]:
    trace = result.get("trace") or {}
    return [
        {"Metrik": "LLM Calls", "Wert": trace.get("llm_calls", 0)},
        {"Metrik": "MCP Calls", "Wert": trace.get("mcp_calls", 0)},
        {"Metrik": "SQL Executions", "Wert": trace.get("sql_executions", 0)},
        {"Metrik": "Critic Reviews", "Wert": trace.get("critic_calls", 0)},
        {"Metrik": "Repair Iterationen", "Wert": result.get("iterations", 0)},
        {"Metrik": "Input Tokens", "Wert": trace.get("input_tokens")},
        {"Metrik": "Output Tokens", "Wert": trace.get("output_tokens")},
        {"Metrik": "Total Tokens", "Wert": trace.get("total_tokens")},
        {"Metrik": "Runtime Seconds", "Wert": trace.get("runtime_seconds", 0.0)},
        {"Metrik": "Profiling Calls", "Wert": trace.get("profiling_calls", 0)},
    ]


def activity_from_event(event: RunnerEvent) -> Activity | None:
    node = event.get("node")
    update = event.get("update") or {}
    if not node:
        return None

    status: Literal["ok", "error", "running"] = "ok"
    if update.get("last_error"):
        status = "error"

    return {
        "node": node,
        "title": NODE_TITLES.get(node, node),
        "detail": _activity_detail(node, update),
        "calls": NODE_CALLS.get(node, []),
        "status": status,
    }


def _question_input(examples: list[QuestionExample]) -> tuple[str, SystemId, int, bool]:
    selected_example: QuestionExample | None = None
    if examples:
        with st.expander("Testfrage auswählen", expanded=False):
            labels = ["Freitext"] + [example["label"] for example in examples]
            selected_label = st.selectbox("Beispielfrage", labels, label_visibility="collapsed")
            selected_example = next(
                (example for example in examples if example["label"] == selected_label),
                None,
            )
            if selected_example is not None:
                status = "beantwortbar" if selected_example["answerable"] else "unanswerable"
                st.caption(f"Schwierigkeit: {selected_example['difficulty']} | Erwartung: {status}")

    default_question = selected_example["question"] if selected_example else ""
    with st.container(key="question_composer"):
        question = st.text_area(
            "Frage",
            value=default_question,
            height=74,
            placeholder="Frage an den BI-Agenten eingeben...",
            label_visibility="collapsed",
        )
        selected_system = st.session_state.get("selected_system", "C")
        column_widths = [3.6, 1.65, 0.72] if selected_system == "B" else [3.6, 1.65, 1.2, 0.72]
        columns = st.columns(column_widths)
        spacer, system_column = columns[:2]
        send_column = columns[-1]
        with spacer:
            st.caption("Frage an die Daten")
        with system_column:
            system = st.selectbox(
                "System",
                options=["B", "C"],
                format_func=lambda value: {
                    "B": "Single-Shot",
                    "C": "MCP + Critic",
                }[value],
                index=1,
                key="selected_system",
                label_visibility="collapsed",
            )
        max_iterations = 0
        if system == "C":
            with columns[2]:
                max_iterations = st.selectbox(
                    "Iterationen",
                    options=list(range(6)),
                    index=3,
                    format_func=lambda value: f"{value} Iter.",
                    label_visibility="collapsed",
                )
        with send_column:
            run_requested = st.button(
                "➜",
                type="primary",
                disabled=not question.strip(),
                help="Frage senden",
                key="send_question",
            )
    return question, system, max_iterations, run_requested


def _run_streamed_demo(
    *,
    question: str,
    system: SystemId,
    max_iterations: int,
    activity_slot,
    result_slot,
) -> None:
    runner = _stream_runner_for_system(system)
    activities: list[Activity] = []
    final_result: RunnerResult | None = None

    with result_slot.container():
        st.info("Der Agent arbeitet...")

    for event in runner(question, max_iterations):
        activity = activity_from_event(event)
        if activity is not None:
            activities.append(activity)
            _render_activities(activity_slot, activities, running=True)
        if event.get("event_type") == "final":
            final_result = event.get("result")

    st.session_state["latest_activities"] = activities
    st.session_state["latest_result"] = final_result
    _render_activities(activity_slot, activities, running=False)
    with result_slot.container():
        if final_result is None:
            st.error("Der Lauf wurde ohne Ergebnis beendet.")
        else:
            _render_result(final_result, question)


def _stream_runner_for_system(system: SystemId) -> StreamRunner:
    if system == "B":
        return stream_mcp_single_shot
    return stream_mcp_critic


def _render_intro() -> None:
    st.markdown(
        """
        <div class="intro">
          <h2>Was möchtest du über die Daten wissen?</h2>
          <p>Stelle eine Frage in natürlicher Sprache oder wähle eine Testfrage aus.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_activities(activity_slot, activities: list[Activity], *, running: bool) -> None:
    with activity_slot.container():
        if not activities:
            st.write("Noch keine Aktivitäten.")
            return

        for index, activity in enumerate(activities, start=1):
            status_class = {
                "ok": "activity-ok",
                "error": "activity-error",
                "running": "activity-running",
            }[activity["status"]]
            st.markdown(
                f"""
                <div class="activity {status_class}">
                  <div class="activity-index">{index:02d}</div>
                  <div>
                    <div class="activity-title">{activity["title"]}</div>
                    <div class="activity-detail">{activity["detail"]}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if activity["calls"]:
                st.caption(" · ".join(activity["calls"]))

        if running:
            st.caption("Stream läuft...")


def _render_result(result: RunnerResult, question: str = "") -> None:
    status = result.get("status", "ERROR")
    if status == "ERROR":
        st.error("Die Anfrage konnte nicht abgeschlossen werden.")
    elif status == "CORRECT_REJECTION":
        st.warning("Diese Frage lässt sich mit den verfügbaren Daten nicht beantworten.")

    st.write(result.get("final_answer") or "Keine finale Antwort vorhanden.")

    frame = result_to_dataframe(result)
    if frame is not None:
        _render_data_and_chart(frame, question)
        execution_result = result.get("execution_result") or {}
        if isinstance(execution_result, dict) and execution_result.get("truncated"):
            st.caption("Resultat wurde durch die SQL-Ausführung limitiert.")

    with st.expander("Verwendete Tools und Ressourcen", expanded=False):
        _render_used_primitives(result)

    with st.expander("SQL anzeigen", expanded=False):
        first_sql = result.get("first_generated_sql")
        final_sql = result.get("final_generated_sql")
        if first_sql and first_sql != final_sql:
            st.caption("First-pass SQL")
            st.code(first_sql, language="sql")
        st.caption("Finales SQL")
        st.code(final_sql or "-- kein SQL generiert", language="sql")

    if frame is not None:
        with st.expander("Rohdaten anzeigen", expanded=False):
            st.dataframe(frame, width="stretch", hide_index=True)

    with st.expander("Technischen Trace anzeigen", expanded=False):
        st.dataframe(pd.DataFrame(trace_rows(result)), width="stretch", hide_index=True)
        trace = result.get("trace") or {}
        retrieved_tables = trace.get("retrieved_tables") or []
        if retrieved_tables:
            st.caption("Genutzte Tabellen")
            st.write(", ".join(str(table) for table in retrieved_tables))

    error_history = result.get("error_history") or []
    if error_history or result.get("last_error"):
        with st.expander("Fehlerdetails anzeigen", expanded=False):
            if result.get("last_error"):
                st.caption("Letzter Fehler")
                st.code(str(result["last_error"]))
            if error_history:
                st.caption("Fehlerhistorie")
                for index, error in enumerate(error_history, start=1):
                    st.code(f"{index}. {error}")


def choose_chart_type(question: str, frame: pd.DataFrame) -> str | None:
    normalized = question.casefold()
    requested_types = {
        "scatter": ("scatter", "streu", "punktdiagramm"),
        "area": ("area", "fläche", "flaeche"),
        "line": ("line", "linie", "zeitverlauf", "trend"),
        "bar": ("bar", "balken", "säulen", "saeulen"),
    }
    numeric_columns = [
        column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])
    ]
    for chart_type, keywords in requested_types.items():
        if any(keyword in normalized for keyword in keywords):
            return chart_type if numeric_columns else None
    if not numeric_columns or len(frame.index) <= 1:
        return None
    dimension = _first_dimension_column(frame, numeric_columns)
    if dimension and pd.api.types.is_datetime64_any_dtype(frame[dimension]):
        return "line"
    if dimension:
        dimension_values = frame[dimension].astype(str).str.casefold()
        if dimension_values.str.contains(r"\b(?:19|20)\d{2}\b|q[1-4]|monat|month|jahr|year").any():
            return "line"
        return "bar"
    if len(numeric_columns) >= 2:
        return "scatter"
    return None


def _render_data_and_chart(frame: pd.DataFrame, question: str) -> None:
    chart_type = choose_chart_type(question, frame)
    if chart_type is None:
        st.dataframe(frame, width="stretch", hide_index=True)
        return

    numeric_columns = [
        column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])
    ]
    x_column = _first_dimension_column(frame, numeric_columns)
    y_column = numeric_columns[0]
    st.caption(CHART_LABELS[chart_type])
    if chart_type == "scatter" and len(numeric_columns) >= 2:
        st.scatter_chart(frame, x=numeric_columns[0], y=numeric_columns[1])
        return
    chart_data = frame[[x_column, y_column]].set_index(x_column) if x_column else frame[[y_column]]
    if chart_type == "line":
        st.line_chart(chart_data)
    elif chart_type == "area":
        st.area_chart(chart_data)
    else:
        st.bar_chart(chart_data)


def _render_used_primitives(result: RunnerResult) -> None:
    trace = result.get("trace") or {}
    retrieved_tables = trace.get("retrieved_tables") or []
    st.markdown("**Ressourcen**")
    if retrieved_tables:
        st.write("Schema-Metadaten: " + ", ".join(str(table) for table in retrieved_tables))
        st.write("Business-Glossar und Tabellenbeziehungen")
    else:
        st.write("Keine Ressourcen protokolliert.")
    st.markdown("**Tools**")
    st.write(f"SQL-Ausführungen: {trace.get('sql_executions', 0)}")
    st.write(f"Profiling-Aufrufe: {trace.get('profiling_calls', 0)}")


def _first_dimension_column(frame: pd.DataFrame, numeric_columns: list[str]) -> str | None:
    for column in frame.columns:
        if column not in numeric_columns:
            return str(column)
    return str(frame.columns[0]) if len(frame.columns) > 1 else None


def _activity_detail(node: str, update: dict[str, Any]) -> str:
    if update.get("last_error"):
        return str(update["last_error"])
    if node == "interpret_request":
        plan = update.get("analysis_plan") or {}
        metric = plan.get("metric") or "keine Metrik erkannt"
        return f"Analyseplan erstellt: {metric}"
    if node == "retrieve_context":
        context = update.get("metadata_context") or {}
        dictionaries = context.get("table_dictionaries") or {}
        return f"{len(dictionaries)} Tabellendictionaries im Kontext"
    if node == "profile_data":
        observations = update.get("profiling_observations") or {}
        return f"{len(observations)} Tabellen profiliert"
    if node == "generate_sql":
        sql = str(update.get("generated_sql") or "")
        return sql[:120] if sql else "kein SQL generiert"
    if node == "validate_sql":
        result = update.get("validation_result") or {}
        return "SQL ist valide" if result.get("ok") else str(result.get("error"))
    if node == "execute_sql":
        result = update.get("execution_result") or {}
        return f"{result.get('row_count', 0)} Zeilen geliefert"
    if node == "critic_reflection":
        return f"Entscheidung: {update.get('critic_decision') or 'ABORT'}"
    if node == "synthesize_answer":
        return "Finale Antwort erstellt"
    return "Schritt abgeschlossen"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #ffffff;
            color: #1f2937;
        }
        .block-container {
            padding-top: 2.2rem;
            padding-bottom: 4rem;
            max-width: 780px;
        }
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            display: none;
        }
        .intro {
            color: #6b7280;
            margin-bottom: 1.45rem;
            text-align: center;
        }
        .intro h2 {
            color: #1f2937;
            font-size: 1.8rem;
            font-weight: 500;
            letter-spacing: -0.035em;
            margin: 0 0 0.4rem;
        }
        .intro p {
            font-size: 0.96rem;
            margin: 0;
        }
        .st-key-question_composer {
            background: #ffffff;
            border: 1px solid #dbe1ea;
            border-radius: 22px;
            box-shadow: 0 7px 22px rgba(15, 23, 42, 0.06);
            padding: 0.45rem 0.6rem 0.35rem;
        }
        .st-key-question_composer textarea {
            background: transparent;
            border: 0;
            box-shadow: none;
            min-height: 72px;
            padding: 0.55rem 0.45rem;
        }
        .st-key-question_composer textarea:focus {
            box-shadow: none;
        }
        .st-key-question_composer [data-testid="stHorizontalBlock"] {
            align-items: center;
            gap: 0.45rem;
        }
        .st-key-question_composer [data-testid="stCaptionContainer"] {
            color: #94a3b8;
            padding-left: 0.45rem;
        }
        .st-key-question_composer [data-baseweb="select"] > div {
            background: #f8fafc;
            border-color: #e5e7eb;
            border-radius: 999px;
            min-height: 2.25rem;
        }
        .st-key-question_composer button[kind="primary"] {
            background: #2563eb;
            border-color: #2563eb;
            border-radius: 999px;
            color: #ffffff;
            font-size: 1.08rem;
            height: 2.35rem;
            min-height: 2.35rem;
            padding: 0;
            width: 2.35rem;
        }
        .st-key-question_composer button[kind="primary"]:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #ffffff;
        }
        .st-key-question_composer button[kind="primary"]:focus {
            box-shadow: 0 0 0 0.2rem rgba(37, 99, 235, 0.2);
            color: #ffffff;
        }
        .st-key-question_composer button[kind="primary"]:disabled {
            color: #ffffff;
        }
        .st-key-question_composer [data-baseweb="select"] > div:focus-within {
            border-color: #2563eb;
            box-shadow: 0 0 0 1px #2563eb;
        }
        ::selection {
            background: #bfdbfe;
            color: #1e3a8a;
        }
        [data-baseweb="popover"] [role="option"][aria-selected="true"],
        [data-baseweb="menu"] [role="option"][aria-selected="true"] {
            background: #dbeafe;
            color: #1d4ed8;
        }
        [data-baseweb="popover"] [role="option"]:hover,
        [data-baseweb="menu"] [role="option"]:hover {
            background: #eff6ff;
            color: #1d4ed8;
        }
        div[data-testid="stExpander"]:focus-within,
        div[data-testid="stExpander"]:has(details[open]) {
            border-color: #2563eb;
            box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.16);
        }
        input:focus,
        textarea:focus {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 1px #2563eb !important;
        }
        .st-key-question_composer textarea:focus {
            box-shadow: none !important;
        }
        div[data-testid="stCodeBlock"] pre {
            border-radius: 10px;
        }
        div[data-testid="stExpander"] {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            margin-top: 0.65rem;
        }
        div[data-testid="stChatMessage"] {
            background: transparent;
            padding: 0.55rem 0;
        }
        div[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"],
        div[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"],
        div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"],
        div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
            display: none;
        }
        div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
            margin-left: 0;
        }
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            background: #f1f5f9;
            border-radius: 18px;
            margin-left: auto;
            padding: 0.7rem 1rem;
            width: fit-content;
            max-width: 82%;
        }
        textarea {
            border-radius: 18px !important;
        }
        .activity {
            display: grid;
            grid-template-columns: 1.8rem 1fr;
            gap: 0.65rem;
            align-items: start;
            padding: 0.58rem 0;
            border-bottom: 1px solid #e5e7eb;
        }
        .activity-index {
            color: #64748b;
            font-size: 0.74rem;
            font-weight: 700;
            line-height: 1.45;
        }
        .activity-title {
            color: #0f172a;
            font-size: 0.9rem;
            font-weight: 700;
            line-height: 1.35;
        }
        .activity-detail {
            color: #475569;
            font-size: 0.82rem;
            line-height: 1.42;
            overflow-wrap: anywhere;
        }
        .activity-ok .activity-title {
            color: #334155;
        }
        .activity-error .activity-title {
            color: #991b1b;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    render_app()
