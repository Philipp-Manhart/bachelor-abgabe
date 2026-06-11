from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from agent_orchestrator.config import PROJECT_ROOT
from evaluation.benchmark.metrics import aggregate_metrics, unanswerable_scores
from evaluation.paper_plot_style import (
    COLORS_ACCENT,
    COLORS_SECONDARY,
    SYSTEM_COLORS,
    add_minor_y_grid,
    set_paper_style,
    typst_figsize,
)

DEFAULT_INPUT_DIR = PROJECT_ROOT / "results" / "benchmark"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "plots"
SYSTEM_ORDER = ["A", "B", "C"]
SUCCESS_COLOR = COLORS_ACCENT[2]
ERROR_COLOR = COLORS_ACCENT[0]
OTHER_COLOR = COLORS_ACCENT[1]
SEMANTIC_FALLBACK_COLORS = [
    COLORS_SECONDARY[2],
    COLORS_SECONDARY[0],
    COLORS_SECONDARY[1],
]
SEMANTIC_COLOR_SEQUENCES = {
    "success": [SUCCESS_COLOR, COLORS_SECONDARY[2], OTHER_COLOR],
    "error": [ERROR_COLOR, COLORS_SECONDARY[0], OTHER_COLOR],
    "other": [OTHER_COLOR, COLORS_SECONDARY[1], SUCCESS_COLOR],
}
STRONG_TEAL = SYSTEM_COLORS["B"]
STRONG_PURPLE = SYSTEM_COLORS["C"]
STRONG_GRAY = SYSTEM_COLORS["A"]
LIGHT_TEAL = SUCCESS_COLOR
DIFFICULTY_ORDER = ["easy", "medium", "hard", "unanswerable"]
OUTCOME_ORDER = [
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
ERROR_TYPE_ORDER = [
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
    "none",
    "unknown",
]
DISPLAY_LABELS = {
    "A": "System A",
    "B": "System B",
    "C": "System C",
    "first_pass_success_rate": "First pass",
    "ultimate_success_rate": "Final",
    "correct_rejection_rate": "Correct rejection",
    "false_answer_rate": "False answer",
    "unanswerable_precision": "Precision",
    "unanswerable_recall": "Recall",
    "unanswerable_f1": "F1",
    "acceptance_rate": "Accepted",
    "intervention_rate": "Intervened",
    "abort_rate": "Aborted",
    "avg_sql_stage_llm_calls": "LLM calls",
    "avg_sql_stage_mcp_calls": "MCP calls",
    "avg_sql_stage_mcp_resource_calls": "MCP resource calls",
    "avg_sql_stage_mcp_tool_calls": "MCP tool calls",
    "avg_sql_stage_sql_executions": "SQL executions",
    "avg_sql_stage_total_tokens": "SQL stage",
    "avg_critic_total_tokens": "Critic",
    "avg_answer_synthesis_total_tokens": "Answer synthesis",
    "table_f1_first": "First pass",
    "table_f1_final": "Final",
    "mcp_calls": "MCP calls",
    "profiling_calls": "Profiling calls",
    "sql_executions": "SQL executions",
    "recovered": "Recovered",
    "regressed": "Regressed",
    "intervened_failed": "Intervened, failed",
    "accepted_correct": "Accepted correct",
    "accepted_wrong": "Accepted wrong",
    "intervened_recovered": "Intervened, recovered",
    "SUCCESS": "Success",
    "SQL_ERROR": "SQL error",
    "WRONG_RESULT": "Wrong result",
    "CORRECT_REJECTION": "Correct rejection",
    "FALSE_REJECTION": "False rejection",
    "FALSE_ANSWER": "False answer",
    "MAX_ITERATIONS_FAILED": "Max iterations failed",
    "RUNTIME_ERROR": "Runtime error",
    "UNKNOWN": "Unknown",
    "ACCEPT": "Accept",
    "REPAIR": "Repair",
    "ABORT": "Abort",
    "MISSING": "Missing",
    "syntax_error": "Syntax error",
    "schema_error": "Schema error",
    "join_error": "Join error",
    "filter_error": "Filter error",
    "aggregation_error": "Aggregation error",
    "empty_result": "Empty result",
    "unanswerable": "Unanswerable",
    "security_error": "Security error",
    "runtime_error": "Runtime error",
    "json_parse_error": "JSON parse error",
    "missing_reference": "Missing reference",
    "none": "None",
    "unknown": "Unknown",
}


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    title: str
    filename: str
    main_use: str


TABLE_SPECS = [
    Artifact("T1", "Benchmark metadata summary", "benchmark_metadata_summary.csv", "Run metadata."),
    Artifact(
        "T2",
        "Test corpus composition",
        "test_corpus_composition.csv",
        "Questions by difficulty and answerability.",
    ),
    Artifact(
        "T3", "Full summary by system", "summary_by_system_mean_std.csv", "Main result table."
    ),
    Artifact(
        "T4",
        "Summary by difficulty",
        "summary_by_difficulty_mean_std.csv",
        "Success rates by difficulty.",
    ),
    Artifact(
        "T5",
        "Summary by system x difficulty",
        "summary_by_system_difficulty_mean_std.csv",
        "Per-system difficulty results.",
    ),
    Artifact(
        "T6",
        "Answerability summary by system",
        "summary_answerability_mean_std.csv",
        "Answerable vs. unanswerable performance.",
    ),
    Artifact(
        "T7",
        "Outcome counts by system",
        "outcome_counts_mean_std.csv",
        "Absolute outcome counts.",
    ),
    Artifact(
        "T8",
        "Outcome rates by system",
        "outcome_rates_mean_std.csv",
        "Normalized outcome rates.",
    ),
    Artifact(
        "T9",
        "Error type summary by system",
        "error_type_summary_mean_std.csv",
        "Failure mode counts and rates.",
    ),
    Artifact(
        "T10",
        "Efficiency metrics by system - SQL stage",
        "sql_stage_efficiency_mean_std.csv",
        "SQL-stage efficiency.",
    ),
    Artifact(
        "T11",
        "Efficiency metrics by system - end-to-end",
        "end_to_end_efficiency_mean_std.csv",
        "End-to-end efficiency.",
    ),
    Artifact(
        "T12",
        "Token breakdown by system",
        "token_breakdown_phase_mean_std.csv",
        "Token usage split.",
    ),
    Artifact(
        "T13",
        "Runtime breakdown by system",
        "runtime_breakdown_phase_mean_std.csv",
        "Runtime split.",
    ),
    Artifact(
        "T14", "Call breakdown by system", "call_breakdown_phase_mean_std.csv", "Call usage split."
    ),
    Artifact(
        "T15",
        "Critic review summary",
        "critic_review_summary_mean_std.csv",
        "Review count, acceptance, intervention, and abort rates.",
    ),
    Artifact(
        "T16",
        "Critic repair summary",
        "critic_repair_summary_mean_std.csv",
        "Repair iterations, recovery, and max-iteration failures.",
    ),
    Artifact(
        "T17",
        "Critic regression summary",
        "critic_regression_summary_mean_std.csv",
        "Cases where critic intervention regressed a correct first pass.",
    ),
    Artifact(
        "T18",
        "Critic details on answerable questions only",
        "critic_answerable_only_mean_std.csv",
        "Critic usefulness on answerable cases.",
    ),
    Artifact(
        "T19",
        "Critic details by difficulty",
        "critic_by_difficulty_mean_std.csv",
        "Critic behavior by difficulty.",
    ),
    Artifact(
        "T20",
        "Critic decision counts",
        "critic_decision_counts_mean_std.csv",
        "Critic decision distribution.",
    ),
    Artifact(
        "T21",
        "Critic decision counts by difficulty",
        "critic_decision_counts_by_difficulty_mean_std.csv",
        "Decision distribution by difficulty.",
    ),
    Artifact(
        "T22",
        "Critic intervention cases",
        "critic_intervention_cases.csv",
        "Questions where the critic did not accept.",
    ),
    Artifact("T23", "Critic recovery cases", "critic_recovery_cases.csv", "Recovered questions."),
    Artifact(
        "T24",
        "Critic regression cases",
        "critic_regression_cases.csv",
        "First pass succeeded but final result failed.",
    ),
    Artifact(
        "T25",
        "Failed after critic cases",
        "failed_after_critic_cases.csv",
        "Unrecovered critic cases.",
    ),
    Artifact(
        "T26",
        "False rejection cases",
        "false_rejection_cases.csv",
        "Answerable questions rejected.",
    ),
    Artifact(
        "T27",
        "False answer cases",
        "false_answer_cases.csv",
        "Unanswerable questions answered.",
    ),
    Artifact(
        "T28",
        "Unanswerable Precision/Recall/F1 by system",
        "unanswerable_prf_mean_std.csv",
        "Hallucination-control metric.",
    ),
    Artifact(
        "T29",
        "Table Selection Precision/Recall/F1 by system",
        "table_selection_f1_by_system_mean_std.csv",
        "Table-selection diagnostic.",
    ),
    Artifact(
        "T30",
        "Table Selection F1 by difficulty",
        "table_selection_f1_by_difficulty_mean_std.csv",
        "Table selection by difficulty.",
    ),
    Artifact(
        "T31",
        "First-pass vs. final table F1",
        "table_selection_first_vs_final_mean_std.csv",
        "Critic table-selection effect.",
    ),
    Artifact(
        "T32",
        "Top failed questions",
        "top_failed_questions.csv",
        "Questions failed by most systems.",
    ),
    Artifact(
        "T33",
        "System disagreement table",
        "system_disagreement_table.csv",
        "Differing system outcomes.",
    ),
    Artifact(
        "T34",
        "Per-question result matrix",
        "per_question_result_matrix.csv",
        "Question x system outcomes.",
    ),
    Artifact(
        "T35",
        "Per-question SQL-stage cost matrix",
        "per_question_sql_stage_cost.csv",
        "Question x system costs.",
    ),
    Artifact("T36", "Unknown cases", "unknown_cases.csv", "Unevaluable cases."),
    Artifact(
        "T37",
        "Reference SQL validation summary",
        "reference_sql_validation_summary.csv",
        "Reference availability/execution status.",
    ),
    Artifact(
        "T38",
        "Result-size summary",
        "result_size_summary_mean_std.csv",
        "Rows, truncation, empty results.",
    ),
    Artifact(
        "T39",
        "Profiling usage summary",
        "profiling_usage_summary_mean_std.csv",
        "Profiling usage by system and difficulty.",
    ),
    Artifact(
        "T40",
        "Retrieved tables summary",
        "retrieved_tables_summary_mean_std.csv",
        "Retrieved table counts and frequency.",
    ),
    Artifact(
        "T41",
        "MCP resource/tool usage summary",
        "mcp_usage_summary_mean_std.csv",
        "MCP usage counts.",
    ),
    Artifact(
        "T42",
        "SQL execution count distribution",
        "sql_execution_distribution_mean_std.csv",
        "SQL execution effort.",
    ),
    Artifact(
        "T43",
        "Repair iteration distribution for System C",
        "repair_iteration_distribution_mean_std.csv",
        "System C repair effort.",
    ),
    Artifact(
        "T44",
        "Cost per successful answer",
        "cost_per_success_mean_std.csv",
        "Efficiency-normalized cost.",
    ),
    Artifact(
        "T45",
        "Efficiency-normalized success",
        "efficiency_normalized_success_mean_std.csv",
        "Success per cost unit.",
    ),
    Artifact(
        "T46",
        "Critic acceptance vs correctness table",
        "critic_acceptance_correctness.csv",
        "Accepted/intervened correctness outcomes.",
    ),
]

FIGURE_SPECS = [
    Artifact(f"F{index}", title, f"F{index:02d}_{slug}.svg", use)
    for index, title, slug, use in [
        (
            1,
            "First-pass vs. ultimate success by system",
            "first_pass_vs_ultimate_success_by_system",
            "Core ablation result.",
        ),
        (
            2,
            "Ultimate success by difficulty",
            "ultimate_success_by_difficulty",
            "Complexity degradation.",
        ),
        (
            3,
            "Answerable success by system",
            "answerable_success_by_system",
            "Answerable-only success.",
        ),
        (
            4,
            "Correct rejection vs. false answer by system",
            "correct_rejection_vs_false_answer_by_system",
            "Unanswerable behavior.",
        ),
        (
            5,
            "Unanswerable Precision/Recall/F1 by system",
            "unanswerable_precision_recall_f1_by_system",
            "Rejection quality.",
        ),
        (6, "Outcome distribution by system", "outcome_distribution_by_system", "Outcome mix."),
        (
            7,
            "Error type distribution by system",
            "error_type_distribution_by_system",
            "Dominant failure modes.",
        ),
        (
            8,
            "Error type distribution by difficulty",
            "error_type_distribution_by_difficulty",
            "Failure modes by complexity.",
        ),
        (
            9,
            "Critic acceptance vs. intervention rate",
            "critic_acceptance_vs_intervention_rate",
            "Critic review behavior.",
        ),
        (
            10,
            "Critic decision distribution",
            "critic_decision_distribution",
            "Decision mix.",
        ),
        (11, "Critic recovery vs. regression", "critic_recovery_vs_regression", "Critic effect."),
        (
            12,
            "Critic recovery by difficulty",
            "critic_recovery_by_difficulty",
            "Critic usefulness by difficulty.",
        ),
        (13, "Repair iteration distribution", "repair_iteration_distribution", "Repair effort."),
        (
            14,
            "Critic intervention rate by difficulty",
            "critic_intervention_rate_by_difficulty",
            "Review behavior by difficulty.",
        ),
        (15, "SQL-stage runtime by system", "sql_stage_runtime_by_system", "Efficiency."),
        (16, "SQL-stage total tokens by system", "sql_stage_total_tokens_by_system", "Cost."),
        (17, "SQL-stage calls by system", "sql_stage_calls_by_system", "Call effort."),
        (18, "End-to-end runtime by system", "end_to_end_runtime_by_system", "Product-path cost."),
        (
            19,
            "End-to-end total tokens by system",
            "end_to_end_total_tokens_by_system",
            "Product-path cost.",
        ),
        (
            20,
            "Phase cost split by system",
            "phase_cost_split_by_system",
            "Phase split.",
        ),
        (
            21,
            "Success vs. tokens scatterplot",
            "success_vs_tokens_scatterplot",
            "Quality-cost tradeoff.",
        ),
        (
            22,
            "Success vs. runtime scatterplot",
            "success_vs_runtime_scatterplot",
            "Quality-latency tradeoff.",
        ),
        (
            23,
            "Cost per successful answer by system",
            "cost_per_successful_answer_by_system",
            "Efficiency-normalized quality.",
        ),
        (24, "Table Selection F1 by system", "table_selection_f1_by_system", "Diagnostic."),
        (
            25,
            "Table Selection F1 by difficulty",
            "table_selection_f1_by_difficulty",
            "Diagnostic by complexity.",
        ),
        (
            26,
            "First-pass vs. final Table F1",
            "first_pass_vs_final_table_f1",
            "Critic table-selection effect.",
        ),
        (
            27,
            "False rejections by system",
            "false_rejections_by_system",
            "Over-conservative behavior.",
        ),
        (
            28,
            "False rejection cases by difficulty",
            "false_rejection_cases_by_difficulty",
            "False rejection localization.",
        ),
        (
            29,
            "Empty result rate by system",
            "empty_result_rate_by_system",
            "Empty output frequency.",
        ),
        (
            30,
            "Retrieved tables count by system",
            "retrieved_tables_count_by_system",
            "Retrieval behavior.",
        ),
        (
            31,
            "Profiling calls by system_difficulty",
            "profiling_calls_by_system_difficulty",
            "Profiling contribution.",
        ),
        (32, "MCP calls by type", "mcp_calls_by_type", "MCP usage distribution."),
        (33, "Per-question outcome heatmap", "per_question_outcome_heatmap", "Outcome matrix."),
        (
            34,
            "Per-question success heatmap",
            "per_question_success_heatmap",
            "Binary success matrix.",
        ),
        (35, "Difficulty x system heatmap", "difficulty_system_heatmap", "Success-rate matrix."),
        (
            36,
            "Token distribution boxplot by system",
            "token_distribution_boxplot_by_system",
            "Robust cost distribution.",
        ),
        (
            37,
            "Runtime distribution boxplot by system",
            "runtime_distribution_boxplot_by_system",
            "Robust latency distribution.",
        ),
        (
            38,
            "SQL executions distribution by system",
            "sql_executions_distribution_by_system",
            "Execution effort.",
        ),
        (
            39,
            "Iterations vs. recovery scatter/bar",
            "iterations_vs_recovery",
            "Iteration usefulness.",
        ),
        (
            40,
            "Top error messages / error types bar chart",
            "top_error_messages_error_types",
            "Diagnostic.",
        ),
        (
            41,
            "Most frequently retrieved tables",
            "most_frequently_retrieved_tables",
            "Retrieval diagnostic.",
        ),
        (
            42,
            "Most frequently used tables in final SQL",
            "most_frequently_used_tables_in_final_sql",
            "SQL behavior diagnostic.",
        ),
    ]
]

LEGACY_TABLE_FILENAMES = {
    "T1": "T01_benchmark_metadata_summary.csv",
    "T2": "T02_test_corpus_composition.csv",
    "T3": "T03_full_summary_by_system.csv",
    "T4": "T04_summary_by_difficulty.csv",
    "T5": "T05_summary_by_system_difficulty.csv",
    "T6": "T06_answerability_summary_by_system.csv",
    "T7": "T07_outcome_counts_by_system.csv",
    "T8": "T08_outcome_rates_by_system.csv",
    "T9": "T09_error_type_summary_by_system.csv",
    "T10": "T10_efficiency_sql_stage_by_system.csv",
    "T11": "T11_efficiency_end_to_end_by_system.csv",
    "T12": "T12_token_breakdown_by_system.csv",
    "T13": "T13_runtime_breakdown_by_system.csv",
    "T14": "T14_call_breakdown_by_system.csv",
    "T15": "T15_critic_review_summary.csv",
    "T16": "T16_critic_repair_summary.csv",
    "T17": "T17_critic_regression_summary.csv",
    "T18": "T18_critic_details_answerable_only.csv",
    "T19": "T19_critic_details_by_difficulty.csv",
    "T20": "T20_critic_decision_counts.csv",
    "T21": "T21_critic_decision_counts_by_difficulty.csv",
    "T22": "T22_critic_intervention_cases.csv",
    "T23": "T23_critic_recovery_cases.csv",
    "T24": "T24_critic_regression_cases.csv",
    "T25": "T25_failed_after_critic_cases.csv",
    "T26": "T26_false_rejection_cases.csv",
    "T27": "T27_false_answer_cases.csv",
    "T28": "T28_unanswerable_precision_recall_f1_by_system.csv",
    "T29": "T29_table_selection_prf_by_system.csv",
    "T30": "T30_table_selection_f1_by_difficulty.csv",
    "T31": "T31_first_pass_vs_final_table_f1.csv",
    "T32": "T32_top_failed_questions.csv",
    "T33": "T33_system_disagreement_table.csv",
    "T34": "T34_per_question_result_matrix.csv",
    "T35": "T35_per_question_sql_stage_cost_matrix.csv",
    "T36": "T36_unknown_cases.csv",
    "T37": "T37_reference_sql_validation_summary.csv",
    "T38": "T38_result_size_summary.csv",
    "T39": "T39_profiling_usage_summary.csv",
    "T40": "T40_retrieved_tables_summary.csv",
    "T41": "T41_mcp_resource_tool_usage_summary.csv",
    "T42": "T42_sql_execution_count_distribution.csv",
    "T43": "T43_repair_iteration_distribution_system_c.csv",
    "T44": "T44_cost_per_successful_answer.csv",
    "T45": "T45_efficiency_normalized_success.csv",
    "T46": "T46_critic_acceptance_vs_correctness.csv",
}

FIGURE_OUTPUT_FILENAMES = {
    "F1": "01_first_pass_vs_ultimate_success_by_system.svg",
    "F2": "02_ultimate_success_by_difficulty_mean_std.svg",
    # "F3": "03_answerable_success_by_system_mean_std.svg",
    "F4": "03_correct_rejection_vs_false_answer_by_system.svg",
    # "F5": "05_unanswerable_prf_mean_std.svg",
    # "F6": "06_outcome_distribution_by_system.svg",
    # "F7": "07_error_type_distribution_by_system.svg",
    # "F8": "08_error_type_distribution_by_difficulty.svg",
    "F9": "04_critic_diagnostics.svg",
    "F10": "06_critic_decision_distribution_mean_std.svg",
    # "F11": "05_critic_recovery_regression.svg",
    # "F12": "12_critic_recovery_by_difficulty_mean_std.svg",
    # "F13": "13_repair_iteration_distribution_mean_std.svg",
    # "F14": "14_critic_intervention_by_difficulty_mean_std.svg",
    # "F15": "15_sql_stage_runtime_by_system_mean_std.svg",
    # "F16": "16_sql_stage_tokens_by_system_mean_std.svg",
    "F17": "07_sql_stage_calls_by_system_mean_std.svg",
    # "F18": "18_end_to_end_runtime_by_system_mean_std.svg",
    # "F19": "19_end_to_end_tokens_by_system_mean_std.svg",
    # "F20": "20_phase_cost_split_by_system_mean_std.svg",
    "F21": "08_success_vs_tokens.svg",
    # "F22": "22_success_vs_runtime.svg",
    # "F23": "23_cost_per_success_mean_std.svg",
    # "F24": "24_table_selection_f1_by_system_mean_std.svg",
    # "F25": "25_table_selection_f1_by_difficulty_mean_std.svg",
    # "F26": "26_table_f1_first_vs_final_mean_std.svg",
    "F27": "09_false_rejections_by_system.svg",
    # "F28": "28_false_rejections_by_difficulty.svg",
    # "F29": "29_empty_result_rate_by_system_mean_std.svg",
    # "F30": "30_retrieved_tables_count_by_system.svg",
    # "F31": "31_profiling_calls_by_system_difficulty.svg",
    # "F32": "32_mcp_calls_by_type.svg",
    # "F33": "33_per_question_outcome_heatmap.svg",
    # "F34": "34_per_question_success_heatmap.svg",
    # "F35": "35_difficulty_system_heatmap.svg",
    # "F36": "36_token_distribution_boxplot.svg",
    # "F37": "37_runtime_distribution_boxplot.svg",
    # "F38": "38_sql_executions_distribution.svg",
    # "F39": "39_iterations_vs_recovery.svg",
    # "F40": "40_top_error_messages.svg",
    # "F41": "41_most_frequent_retrieved_tables.svg",
    # "F42": "42_most_frequent_final_sql_tables.svg",
}

ACTIVE_FIGURE_IDS = ("F1", "F2", "F4", "F9", "F10", "F17", "F21", "F27")

SELECTED_TABLE_FILENAMES = {
    "T3": "01_full_summary_by_system.csv",
    "T5": "02_summary_by_system_difficulty.csv",
    "T10": "03_sql_stage_efficiency_by_system.csv",
    "critic_system_c": "04_critic_review_details_system_c.csv",
    "T28": "05_unanswerable_precision_recall_f1_by_system.csv",
}

SELECTED_FIGURE_FILENAMES = {
    "F1": "01_first_pass_vs_ultimate_success_by_system.svg",
    "F2": "02_ultimate_success_by_difficulty_mean_std.svg",
    "F4": "03_correct_rejection_vs_false_answer_by_system.svg",
    "F9": "04_critic_diagnostics.svg",
    "F10": "06_critic_decision_distribution_mean_std.svg",
    "F17": "07_sql_stage_calls_by_system_mean_std.svg",
    "F21": "08_success_vs_tokens.svg",
    "F27": "09_false_rejections_by_system.svg",
}


def generate_benchmark_artifacts(
    input_dir: str | Path = DEFAULT_INPUT_DIR,
    output_dir: str | Path | None = None,
) -> dict[str, dict[str, Path]]:
    source_dir = _resolve_results_dir(input_dir)
    target_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    tables_dir = target_dir / "tables"
    figures_dir = target_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    results = load_results(source_dir)
    traces = load_traces(source_dir)
    metadata = load_metadata(source_dir)
    table_frames = build_tables(results, traces, metadata)
    written_tables = write_table_artifacts(table_frames, tables_dir)
    written_figures = write_figure_artifacts(results, table_frames, figures_dir, traces=traces)
    selected_tables = write_selected_table_artifacts(table_frames, tables_dir / "selection")
    manifest = {
        "source_dir": str(source_dir),
        "tables": {spec.artifact_id: str(written_tables[spec.artifact_id]) for spec in TABLE_SPECS},
        "figures": {key: str(value) for key, value in written_figures.items()},
        "selected_tables": {key: str(value) for key, value in selected_tables.items()},
        "selected_figures": {},
    }
    (target_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {
        "tables": written_tables,
        "figures": written_figures,
        "selected_tables": selected_tables,
        "selected_figures": {},
    }


def load_results(input_dir: str | Path = DEFAULT_INPUT_DIR) -> pd.DataFrame:
    return pd.read_csv(_resolve_results_dir(input_dir) / "benchmark_results.csv")


def load_traces(input_dir: str | Path = DEFAULT_INPUT_DIR) -> list[dict[str, Any]]:
    path = _resolve_results_dir(input_dir) / "benchmark_traces.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_metadata(input_dir: str | Path = DEFAULT_INPUT_DIR) -> dict[str, Any]:
    path = _resolve_results_dir(input_dir) / "benchmark_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_results_dir(input_dir: str | Path) -> Path:
    directory = Path(input_dir)
    if (directory / "benchmark_results.csv").exists():
        return directory
    nested = directory / "results"
    if (nested / "benchmark_results.csv").exists():
        return nested
    return directory


def build_tables(
    results: pd.DataFrame,
    traces: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, pd.DataFrame]:
    traces = traces or []
    metadata = metadata or {}
    frame = _with_defaults(results.copy())
    summaries = aggregate_metrics(frame.to_dict(orient="records"))
    tables: dict[str, pd.DataFrame] = {}
    tables["T1"] = _metadata_table(frame, metadata)
    tables["T2"] = _composition_table(frame)
    tables["T3"] = summaries["by_system"]
    tables["T4"] = summaries["by_difficulty"]
    tables["T5"] = summaries["by_system_difficulty"]
    tables["T6"] = summaries["answerability"]
    outcome_counts = _counts_pivot(frame, "outcome", OUTCOME_ORDER)
    tables["T7"] = outcome_counts
    tables["T8"] = _row_rates(outcome_counts, ["system"])
    tables["T9"] = _error_type_summary(frame)
    tables["T10"] = _select(
        summaries["by_system"],
        [
            "system",
            "avg_sql_stage_llm_calls",
            "avg_sql_stage_mcp_calls",
            "avg_sql_stage_sql_executions",
            "avg_sql_stage_total_tokens",
            "avg_sql_stage_runtime_seconds",
        ],
    )
    tables["T11"] = _select(
        summaries["by_system"],
        [
            "system",
            "avg_end_to_end_llm_calls",
            "avg_end_to_end_total_tokens",
            "avg_end_to_end_runtime_seconds",
        ],
    )
    tables["T12"] = _select(
        summaries["by_system"],
        [
            "system",
            "avg_sql_stage_input_tokens",
            "avg_sql_stage_output_tokens",
            "avg_sql_stage_total_tokens",
            "avg_critic_calls",
            "avg_critic_input_tokens",
            "avg_critic_output_tokens",
            "avg_critic_total_tokens",
            "avg_answer_synthesis_input_tokens",
            "avg_answer_synthesis_output_tokens",
            "avg_answer_synthesis_total_tokens",
            "avg_end_to_end_total_tokens",
        ],
    )
    tables["T13"] = _select(
        summaries["by_system"],
        [
            "system",
            "avg_sql_stage_runtime_seconds",
            "avg_answer_synthesis_runtime_seconds",
            "avg_end_to_end_runtime_seconds",
        ],
    )
    tables["T14"] = _select(
        summaries["by_system"],
        [
            "system",
            "avg_sql_stage_llm_calls",
            "avg_sql_stage_mcp_calls",
            "avg_sql_stage_sql_executions",
            "avg_critic_llm_calls",
            "avg_answer_synthesis_llm_calls",
            "avg_end_to_end_llm_calls",
            "avg_profiling_calls",
            "avg_critic_calls",
        ],
    )
    tables["T15"] = _critic_review_summary(frame)
    tables["T16"] = _critic_repair_summary(frame)
    tables["T17"] = _critic_regression_summary(frame)
    tables["T18"] = _critic_overall(frame[frame["answerable"].eq(True)])
    tables["T19"] = _critic_by_difficulty(frame)
    tables["T20"] = _value_counts(frame[frame["system"].eq("C")], ["critic_decision"])
    tables["T21"] = _value_counts(frame[frame["system"].eq("C")], ["difficulty", "critic_decision"])
    tables["T22"] = _case_list(frame, _critic_intervention_mask(frame))
    tables["T23"] = _case_list(
        frame, frame["first_pass_success"].eq(False) & frame["ultimate_success"].eq(True)
    )
    tables["T24"] = _case_list(frame, _critic_regression_mask(frame))
    tables["T25"] = _case_list(
        frame,
        frame["system"].eq("C") & frame["iterations"].gt(0) & frame["ultimate_success"].ne(True),
    )
    tables["T26"] = _case_list(frame, frame["answerable"].eq(True) & _predicted_rejection(frame))
    tables["T27"] = _case_list(
        frame, frame["answerable"].eq(False) & frame["false_answer"].eq(True)
    )
    tables["T28"] = (
        pd.DataFrame.from_dict(unanswerable_scores(frame.to_dict(orient="records")), orient="index")
        .rename_axis("system")
        .reset_index()
    )
    tables["T29"] = _table_selection_prf(frame, ["system"])
    tables["T30"] = _table_selection_prf(frame, ["difficulty"])
    tables["T31"] = _table_selection_prf(frame, ["system"])[
        ["system", "table_f1_first", "table_f1_final"]
    ]
    tables["T32"] = _top_failed_questions(frame)
    tables["T33"] = _system_disagreement(frame)
    tables["T34"] = _pivot_matrix(frame, "outcome")
    tables["T35"] = _cost_matrix(frame)
    tables["T36"] = _case_list(frame, frame["outcome"].eq("UNKNOWN"))
    tables["T37"] = _reference_validation_summary(frame)
    tables["T38"] = _result_size_summary(frame)
    tables["T39"] = _profiling_usage_summary(frame)
    tables["T40"] = _retrieved_tables_summary(frame, traces)
    tables["T41"] = _mcp_usage_summary(frame, traces)
    tables["T42"] = _bucket_distribution(frame, "sql_stage_sql_executions", "sql_executions_bucket")
    tables["T43"] = _value_counts(frame[frame["system"].eq("C")], ["iterations"])
    tables["T44"] = _cost_per_success(frame)
    tables["T45"] = _efficiency_normalized_success(frame)
    tables["T46"] = _critic_acceptance_vs_correctness(frame)
    return tables


def write_table_artifacts(
    tables: dict[str, pd.DataFrame], output_dir: str | Path
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = {}
    for spec in TABLE_SPECS:
        path = target / spec.filename
        tables.get(spec.artifact_id, pd.DataFrame()).to_csv(path, index=False)
        legacy_filename = LEGACY_TABLE_FILENAMES.get(spec.artifact_id)
        if legacy_filename and legacy_filename != spec.filename:
            tables.get(spec.artifact_id, pd.DataFrame()).to_csv(
                target / legacy_filename, index=False
            )
        paths[spec.artifact_id] = path
    return paths


def write_selected_table_artifacts(
    tables: dict[str, pd.DataFrame], output_dir: str | Path
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for artifact_id in ("T3", "T5", "T10", "T28"):
        path = target / SELECTED_TABLE_FILENAMES[artifact_id]
        tables.get(artifact_id, pd.DataFrame()).to_csv(path, index=False)
        paths[artifact_id] = path

    critic_path = target / SELECTED_TABLE_FILENAMES["critic_system_c"]
    _critic_review_details_system_c(tables).to_csv(critic_path, index=False)
    paths["critic_system_c"] = critic_path
    return paths


def write_selected_figure_artifacts(
    figures: dict[str, Path], output_dir: str | Path
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for artifact_id, filename in SELECTED_FIGURE_FILENAMES.items():
        source = figures.get(artifact_id)
        if source is None:
            continue
        destination = target / filename
        shutil.copyfile(source, destination)
        paths[artifact_id] = destination
    return paths


def write_figure_artifacts(
    results: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    output_dir: str | Path,
    traces: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    set_paper_style()
    frame = _with_defaults(results.copy())
    if not tables:
        tables = build_tables(frame)
    paths: dict[str, Path] = {}
    plotters = _figure_plotters(frame, tables, target, traces or [])
    active_specs = [spec for spec in FIGURE_SPECS if spec.artifact_id in ACTIVE_FIGURE_IDS]
    for spec in active_specs:
        path = plotters.get(spec.artifact_id, lambda: None)()
        if path is not None:
            output_path = target / FIGURE_OUTPUT_FILENAMES.get(spec.artifact_id, path.name)
            if output_path != path:
                shutil.copyfile(path, output_path)
                path.unlink()
            paths[spec.artifact_id] = output_path
    return paths


def _critic_review_details_system_c(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    review = tables.get("T15", pd.DataFrame())
    repair = tables.get("T16", pd.DataFrame())
    regression = tables.get("T17", pd.DataFrame())

    selected_columns = [
        "system",
        "reviewed_cases",
        "avg_critic_calls",
        "acceptance_rate",
        "intervention_rate",
        "abort_rate",
        "repair_cases",
        "avg_repair_iterations",
        "recovery_rate",
        "regression_cases",
        "regression_rate",
        "failed_after_max_iterations",
    ]

    merged = _system_c_row(review)
    for frame in (repair, regression):
        row = _system_c_row(frame)
        if row.empty:
            continue
        merged = row if merged.empty else merged.merge(row, on="system", how="outer")

    for column in selected_columns:
        if column not in merged:
            merged[column] = pd.NA
    return merged[selected_columns]


def _system_c_row(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "system" not in frame:
        return pd.DataFrame()
    return frame[frame["system"].eq("C")].reset_index(drop=True)


def _figure_plotters(
    frame: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    target: Path,
    traces: list[dict[str, Any]],
):
    by_system = aggregate_metrics(frame.to_dict(orient="records"))["by_system"]
    by_system_diff = aggregate_metrics(frame.to_dict(orient="records"))["by_system_difficulty"]
    run_by_system = _run_level_metrics(frame, "by_system")
    run_by_system_diff = _run_level_metrics(frame, "by_system_difficulty")
    return {
        "F1": lambda: _bar(
            _melt(
                run_by_system if not run_by_system.empty else by_system,
                ["run_id", "system"],
                ["first_pass_success_rate", "ultimate_success_rate"],
                "metric",
                "rate",
            ),
            target / "F01_first_pass_vs_ultimate_success_by_system.svg",
            "system",
            "rate",
            "Rate",
            "metric",
            True,
            y_limit=(0.4, 1.0),
        ),
        "F2": lambda: _bar(
            run_by_system_diff if not run_by_system_diff.empty else by_system_diff,
            target / "F02_ultimate_success_by_difficulty.svg",
            "difficulty",
            "ultimate_success_rate",
            "Ultimate Success Rate (%)",
            "system",
            True,
            DIFFICULTY_ORDER,
        ),
        "F3": lambda: _bar(
            _answerable_success(frame),
            target / "F03_answerable_success_by_system.svg",
            "system",
            "ultimate_success_rate",
            "Answerable Success Rate (%)",
            None,
            True,
        ),
        "F4": lambda: _bar(
            _melt(
                _run_level_unanswerable_summary(frame),
                ["run_id", "system"],
                ["correct_rejection_rate", "false_answer_rate"],
                "metric",
                "rate",
            ),
            target / "F04_correct_rejection_vs_false_answer_by_system.svg",
            "system",
            "rate",
            "Rate On Unanswerable Cases (%)",
            "metric",
            True,
            palette_override={
                "correct_rejection_rate": STRONG_TEAL,
                "false_answer_rate": STRONG_PURPLE,
            },
        ),
        "F5": lambda: _bar(
            _unanswerable_prf_plot_data(frame, tables["T28"]),
            target / "F05_unanswerable_precision_recall_f1_by_system.svg",
            "system",
            "score",
            "Score",
            "metric",
            True,
            palette_override={
                "unanswerable_precision": COLORS_ACCENT[2],
                "unanswerable_recall": COLORS_ACCENT[1],
                "unanswerable_f1": COLORS_ACCENT[0],
            },
        ),
        "F6": lambda: _stacked(
            tables["T8"].set_index("system"),
            target / "F06_outcome_distribution_by_system.svg",
            "Share Of Runs (%)",
            True,
        ),
        "F7": lambda: _stacked(
            _error_pivot(frame, "system"),
            target / "F07_error_type_distribution_by_system.svg",
            "Share Of Runs (%)",
            True,
        ),
        "F8": lambda: _stacked_grouped(
            _error_distribution_by_difficulty_system(frame),
            target / "F08_error_type_distribution_by_difficulty.svg",
            "Share Of Runs (%)",
            True,
        ),
        "F9": lambda: _critic_diagnostics_figure(
            frame, tables, target / "F09_critic_diagnostics.svg"
        ),
        "F10": lambda: _bar(
            tables["T20"],
            target / "F10_critic_decision_distribution.svg",
            "critic_decision",
            "count",
            "Cases",
            None,
            False,
            palette_override=_critic_decision_palette(tables["T20"]),
        ),
        "F11": lambda: _bar(
            _critic_recovery_regression_plot(frame),
            target / "F11_critic_recovery_vs_regression.svg",
            "metric",
            "count",
            "Cases",
            None,
            False,
            palette_override={
                "recovered": STRONG_TEAL,
                "regressed": STRONG_GRAY,
                "intervened_failed": STRONG_PURPLE,
            },
        ),
        "F12": lambda: _bar(
            tables["T19"],
            target / "F12_critic_recovery_by_difficulty.svg",
            "difficulty",
            "critic_recovery_rate",
            "Recovery Rate (%)",
            None,
            True,
            DIFFICULTY_ORDER,
        ),
        "F13": lambda: _bar(
            tables["T43"],
            target / "F13_repair_iteration_distribution.svg",
            "iterations",
            "count",
            "Cases",
            None,
            False,
        ),
        "F14": lambda: _bar(
            _critic_intervention_by_difficulty(frame),
            target / "F14_critic_intervention_rate_by_difficulty.svg",
            "difficulty",
            "intervention_rate",
            "Intervention Rate (%)",
            None,
            True,
            DIFFICULTY_ORDER,
        ),
        "F15": lambda: _bar(
            by_system,
            target / "F15_sql_stage_runtime_by_system.svg",
            "system",
            "avg_sql_stage_runtime_seconds",
            "Average SQL-Stage Runtime (s)",
            None,
            False,
        ),
        "F16": lambda: _bar(
            by_system,
            target / "F16_sql_stage_total_tokens_by_system.svg",
            "system",
            "avg_sql_stage_total_tokens",
            "Average SQL-Stage Total Tokens",
            None,
            False,
        ),
        "F17": lambda: _bar(
            _melt(
                _run_level_sql_stage_call_breakdown(frame),
                ["run_id", "system"],
                [
                    "avg_sql_stage_llm_calls",
                    "avg_sql_stage_mcp_resource_calls",
                    "avg_sql_stage_mcp_tool_calls",
                    "avg_sql_stage_sql_executions",
                ],
                "metric",
                "calls",
            ),
            target / "F17_sql_stage_calls_by_system.svg",
            "system",
            "calls",
            "Average Calls",
            "metric",
            False,
            palette_override={
                "avg_sql_stage_llm_calls": STRONG_GRAY,
                "avg_sql_stage_mcp_resource_calls": STRONG_TEAL,
                "avg_sql_stage_mcp_tool_calls": STRONG_PURPLE,
                "avg_sql_stage_sql_executions": LIGHT_TEAL,
            },
        ),
        "F18": lambda: _bar(
            by_system,
            target / "F18_end_to_end_runtime_by_system.svg",
            "system",
            "avg_end_to_end_runtime_seconds",
            "Average End-To-End Runtime (s)",
            None,
            False,
        ),
        "F19": lambda: _bar(
            _exclude_unanswerable_difficulty(by_system_diff),
            target / "F19_end_to_end_total_tokens_by_system.svg",
            "system",
            "avg_end_to_end_total_tokens",
            "Average End-To-End Tokens",
            "difficulty",
            False,
        ),
        "F20": lambda: _bar(
            _melt(
                by_system,
                ["system"],
                [
                    "avg_sql_stage_total_tokens",
                    "avg_critic_total_tokens",
                    "avg_answer_synthesis_total_tokens",
                ],
                "metric",
                "tokens",
            ),
            target / "F20_phase_cost_split_by_system.svg",
            "system",
            "tokens",
            "Average Tokens",
            "metric",
            False,
        ),
        "F21": lambda: _frontier_scatter_with_runs(
            frame,
            target / "F21_success_vs_tokens_scatterplot.svg",
            "sql_stage_total_tokens",
            "ultimate_success",
            "Average SQL-Stage Tokens",
            "Ultimate Success Rate (%)",
        ),
        "F22": lambda: _frontier_scatter(
            by_system,
            target / "F22_success_vs_runtime_scatterplot.svg",
            "avg_sql_stage_runtime_seconds",
            "ultimate_success_rate",
            "Average SQL-Stage Runtime (s)",
            "Ultimate Success Rate (%)",
        ),
        "F23": lambda: _bar(
            tables["T44"],
            target / "F23_cost_per_successful_answer_by_system.svg",
            "system",
            "tokens_per_success",
            "Tokens Per Successful Answer",
            None,
            False,
        ),
        "F24": lambda: _bar(
            _melt(tables["T29"], ["system"], ["table_f1_first", "table_f1_final"], "metric", "f1"),
            target / "F24_table_selection_f1_by_system.svg",
            "system",
            "f1",
            "Table Selection F1 (%)",
            "metric",
            True,
        ),
        "F25": lambda: _bar(
            _melt(tables["T30"], ["difficulty"], ["table_f1_final"], "metric", "f1"),
            target / "F25_table_selection_f1_by_difficulty.svg",
            "difficulty",
            "f1",
            "Final Table Selection F1 (%)",
            None,
            True,
            DIFFICULTY_ORDER,
        ),
        "F26": lambda: _bar(
            _melt(tables["T31"], ["system"], ["table_f1_first", "table_f1_final"], "metric", "f1"),
            target / "F26_first_pass_vs_final_table_f1.svg",
            "system",
            "f1",
            "Table Selection F1 (%)",
            "metric",
            True,
        ),
        "F27": lambda: _bar(
            _false_rejection_share_by_system(frame),
            target / "F27_false_rejections_by_system.svg",
            "system",
            "share",
            "Share Of False Rejections (%)",
            None,
            True,
        ),
        "F28": lambda: _bar(
            _false_rejections_by_difficulty(frame),
            target / "F28_false_rejection_cases_by_difficulty.svg",
            "difficulty",
            "count",
            "False Rejections",
            None,
            False,
            DIFFICULTY_ORDER,
        ),
        "F29": lambda: _bar(
            tables["T38"],
            target / "F29_empty_result_rate_by_system.svg",
            "system",
            "empty_result_rate",
            "Empty Result Rate (%)",
            None,
            True,
        ),
        "F30": lambda: _bar(
            tables["T40"],
            target / "F30_retrieved_tables_count_by_system.svg",
            "system",
            "avg_retrieved_tables",
            "Average Retrieved Tables",
            None,
            False,
        ),
        "F31": lambda: _bar(
            tables["T39"],
            target / "F31_profiling_calls_by_system_difficulty.svg",
            "difficulty",
            "avg_profiling_calls",
            "Average Profiling Calls",
            "system",
            False,
            DIFFICULTY_ORDER,
        ),
        "F32": lambda: _bar(
            tables["T41"],
            target / "F32_mcp_calls_by_type.svg",
            "usage_type",
            "count",
            "Calls",
            "system",
            False,
        ),
        "F33": lambda: _heatmap(
            tables["T34"], target / "F33_per_question_outcome_heatmap.svg", categorical=True
        ),
        "F34": lambda: _heatmap(
            _success_matrix(frame),
            target / "F34_per_question_success_heatmap.svg",
            categorical=False,
        ),
        "F35": lambda: _heatmap(
            _difficulty_system_matrix(by_system_diff),
            target / "F35_difficulty_system_heatmap.svg",
            categorical=False,
            colorbar_label="Final Success Rate By Difficulty And System",
            cmap=_teal_to_purple_cmap(),
        ),
        "F36": lambda: _box(
            frame,
            target / "F36_token_distribution_boxplot_by_system.svg",
            "system",
            "sql_stage_total_tokens",
            "SQL-Stage Total Tokens",
        ),
        "F37": lambda: _box(
            frame,
            target / "F37_runtime_distribution_boxplot_by_system.svg",
            "system",
            "sql_stage_runtime_seconds",
            "SQL-Stage Runtime (s)",
        ),
        "F38": lambda: _box(
            frame,
            target / "F38_sql_executions_distribution_by_system.svg",
            "system",
            "sql_stage_sql_executions",
            "SQL Executions",
        ),
        "F39": lambda: _bar(
            _iterations_recovery(frame),
            target / "F39_iterations_vs_recovery.svg",
            "iterations",
            "recovery_rate",
            "Recovery Rate (%)",
            None,
            True,
            y_limit=(0, 0.6),
        ),
        "F40": lambda: _bar(
            _top_errors(frame),
            target / "F40_top_error_messages_error_types.svg",
            "error_type",
            "count",
            "Cases",
            None,
            False,
        ),
        "F41": lambda: _bar(
            _top_retrieved_tables(traces),
            target / "F41_most_frequently_retrieved_tables.svg",
            "table",
            "count",
            "Retrievals",
            None,
            False,
        ),
        "F42": lambda: _bar(
            _top_sql_tables(frame),
            target / "F42_most_frequently_used_tables_in_final_sql.svg",
            "table",
            "count",
            "Uses",
            None,
            False,
        ),
    }


def _with_defaults(frame: pd.DataFrame) -> pd.DataFrame:
    for column, default in {
        "question_id": "",
        "question": "",
        "system": "",
        "difficulty": "",
        "answerable": True,
        "outcome": "UNKNOWN",
        "error_type": "unknown",
        "critic_decision": "",
        "critic_calls": 0,
        "critic_llm_calls": 0,
        "critic_input_tokens": 0,
        "critic_output_tokens": 0,
        "critic_total_tokens": 0,
        "retrieved_tables_count": 0,
        "profiling_calls_count": 0,
        "stored_result_row_count": 0,
        "stored_result_truncated": False,
        "sql_stage_sql_executions": frame.get("sql_executions", 0),
        "sql_stage_total_tokens": frame.get("total_tokens", 0),
        "sql_stage_runtime_seconds": frame.get("runtime_seconds", 0.0),
        "end_to_end_total_tokens": frame.get("total_tokens", 0),
        "end_to_end_runtime_seconds": frame.get("runtime_seconds", 0.0),
    }.items():
        if column not in frame:
            frame[column] = default
    return frame


def _metadata_table(frame: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "run_date", "value": metadata.get("run_date", "")},
            {"metric": "model", "value": metadata.get("model", "")},
            {"metric": "database", "value": metadata.get("database_path", "")},
            {"metric": "num_questions", "value": frame["question_id"].nunique()},
            {"metric": "num_runs", "value": len(frame)},
            {
                "metric": "max_iterations",
                "value": frame.get("max_iterations", pd.Series(dtype=int)).max(),
            },
            {
                "metric": "systems",
                "value": ", ".join(sorted(frame["system"].dropna().astype(str).unique())),
            },
            {"metric": "critic_mode", "value": "mandatory semantic review gate"},
        ]
    )


def _composition_table(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.drop_duplicates("question_id")
        .groupby(["difficulty", "answerable"], as_index=False)
        .size()
        .rename(columns={"size": "questions"})
    )


def _counts_pivot(frame: pd.DataFrame, column: str, order: list[str]) -> pd.DataFrame:
    data = (
        frame.groupby(["system", column], as_index=False).size().rename(columns={"size": "count"})
    )
    pivot = (
        data.pivot(index="system", columns=column, values="count")
        .reindex(SYSTEM_ORDER)
        .fillna(0)
        .reset_index()
    )
    return pivot[["system", *[item for item in order if item in pivot.columns]]]


def _row_rates(counts: pd.DataFrame, id_columns: list[str]) -> pd.DataFrame:
    value_columns = [column for column in counts.columns if column not in id_columns]
    rates = counts.copy()
    totals = rates[value_columns].sum(axis=1).replace(0, pd.NA)
    rates[value_columns] = rates[value_columns].div(totals, axis=0).fillna(0)
    return rates


def _error_type_summary(frame: pd.DataFrame) -> pd.DataFrame:
    counts = (
        frame.groupby(["system", "error_type"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    counts["rate"] = counts["count"] / counts.groupby("system")["count"].transform("sum")
    return counts


def _select(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[[column for column in columns if column in frame.columns]].copy()


def _critic_overall(frame: pd.DataFrame) -> pd.DataFrame:
    summary = aggregate_metrics(frame.to_dict(orient="records"))["by_system"]
    if summary.empty or "system" not in summary:
        return summary
    return summary[summary["system"].eq("C")].reset_index(drop=True)


def _critic_by_difficulty(frame: pd.DataFrame) -> pd.DataFrame:
    summary = aggregate_metrics(frame.to_dict(orient="records"))["by_system_difficulty"]
    if summary.empty or "system" not in summary:
        return summary
    return summary[summary["system"].eq("C")].reset_index(drop=True)


def _system_c(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["system"].eq("C")].copy()


def _critic_review_summary(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    if data.empty:
        return pd.DataFrame(
            columns=[
                "system",
                "reviewed_cases",
                "avg_critic_calls",
                "acceptance_rate",
                "intervention_rate",
                "abort_rate",
            ]
        )
    reviewed = data["critic_calls"].gt(0) if "critic_calls" in data else data.index == data.index
    reviewed_data = data[reviewed]
    total = len(reviewed_data)
    decisions = reviewed_data["critic_decision"].fillna("")
    return pd.DataFrame(
        [
            {
                "system": "C",
                "reviewed_cases": total,
                "avg_critic_calls": pd.to_numeric(
                    reviewed_data.get("critic_calls", pd.Series(dtype=float)), errors="coerce"
                ).mean(),
                "acceptance_rate": _safe_ratio(decisions.eq("ACCEPT").sum(), total),
                "intervention_rate": _safe_ratio(
                    _critic_intervention_mask(reviewed_data).sum(), total
                ),
                "abort_rate": _safe_ratio(decisions.eq("ABORT").sum(), total),
            }
        ]
    )


def _critic_repair_summary(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    repair = data[data["iterations"].gt(0)]
    return pd.DataFrame(
        [
            {
                "system": "C",
                "repair_cases": len(repair),
                "avg_repair_iterations": pd.to_numeric(data["iterations"], errors="coerce").mean()
                if not data.empty
                else 0.0,
                "recovery_rate": _safe_ratio(
                    (
                        repair["first_pass_success"].eq(False) & repair["ultimate_success"].eq(True)
                    ).sum(),
                    len(repair),
                ),
                "failed_after_max_iterations": int(
                    (
                        repair["max_iterations"].notna()
                        & (
                            pd.to_numeric(repair["iterations"], errors="coerce")
                            >= pd.to_numeric(repair["max_iterations"], errors="coerce")
                        )
                        & repair["ultimate_success"].ne(True)
                    ).sum()
                ),
            }
        ]
    )


def _critic_regression_summary(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    regressions = _critic_regression_mask(data)
    return pd.DataFrame(
        [
            {
                "system": "C",
                "regression_cases": int(regressions.sum()),
                "regression_rate": _safe_ratio(regressions.sum(), len(data)),
            }
        ]
    )


def _critic_intervention_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    decision = frame.get("critic_decision", pd.Series("", index=frame.index)).fillna("")
    iterations = pd.to_numeric(
        frame.get("iterations", pd.Series(0, index=frame.index)), errors="coerce"
    ).fillna(0)
    return frame["system"].eq("C") & decision.ne("") & (decision.ne("ACCEPT") | iterations.gt(0))


def _critic_regression_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    return (
        frame["system"].eq("C")
        & frame["first_pass_success"].eq(True)
        & frame["ultimate_success"].ne(True)
        & _critic_intervention_mask(frame)
    )


def _critic_acceptance_vs_correctness(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    if data.empty:
        return pd.DataFrame(columns=["category", "count"])
    accepted = data["critic_decision"].fillna("").eq("ACCEPT")
    intervened = _critic_intervention_mask(data)
    rows = [
        {
            "category": "accepted_correct",
            "count": int((accepted & data["ultimate_success"].eq(True)).sum()),
        },
        {
            "category": "accepted_wrong",
            "count": int((accepted & data["ultimate_success"].ne(True)).sum()),
        },
        {
            "category": "intervened_recovered",
            "count": int(
                (
                    intervened
                    & data["first_pass_success"].eq(False)
                    & data["ultimate_success"].eq(True)
                ).sum()
            ),
        },
        {
            "category": "intervened_failed",
            "count": int((intervened & data["ultimate_success"].ne(True)).sum()),
        },
    ]
    return pd.DataFrame(rows)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if not denominator else float(numerator) / float(denominator)


def _value_counts(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty or not all(column in frame.columns for column in columns):
        return pd.DataFrame(columns=[*columns, "count"])
    return (
        frame.groupby(columns, dropna=False, as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )


def _case_list(frame: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    columns = [
        "question_id",
        "system",
        "difficulty",
        "answerable",
        "question",
        "outcome",
        "error_type",
        "critic_decision",
        "critic_calls",
        "iterations",
        "first_generated_sql",
        "final_generated_sql",
        "last_error",
    ]
    return frame.loc[mask, [column for column in columns if column in frame.columns]].copy()


def _predicted_rejection(frame: pd.DataFrame) -> pd.Series:
    status = frame.get("status", pd.Series("", index=frame.index)).fillna("").astype(str)
    error_type = frame.get("error_type", pd.Series("", index=frame.index)).fillna("").astype(str)
    last_error = frame.get("last_error", pd.Series("", index=frame.index)).fillna("").astype(str)
    return (
        frame["correct_rejection"].eq(True)
        | status.isin(["UNANSWERABLE", "CORRECT_REJECTION"])
        | error_type.eq("unanswerable")
        | last_error.eq("UNANSWERABLE")
    )


def _table_selection_prf(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in frame.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(group_cols, key, strict=True))
        for metric in ["precision", "recall", "f1"]:
            for phase in ["first", "final"]:
                column = f"table_{metric}_{phase}"
                row[f"table_{metric}_{phase}"] = pd.to_numeric(
                    group.get(column), errors="coerce"
                ).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def _top_failed_questions(frame: pd.DataFrame) -> pd.DataFrame:
    failed = frame[frame["ultimate_success"].ne(True) & frame["correct_rejection"].ne(True)]
    return (
        failed.groupby(["question_id", "question", "difficulty"], as_index=False)
        .size()
        .rename(columns={"size": "failed_systems"})
        .sort_values(["failed_systems", "question_id"], ascending=[False, True])
    )


def _system_disagreement(frame: pd.DataFrame) -> pd.DataFrame:
    matrix = _pivot_matrix(frame, "outcome")
    if matrix.empty:
        return matrix
    system_columns = [column for column in SYSTEM_ORDER if column in matrix.columns]
    matrix["distinct_outcomes"] = matrix[system_columns].nunique(axis=1)
    return matrix[matrix["distinct_outcomes"].gt(1)]


def _pivot_matrix(frame: pd.DataFrame, value: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return frame.pivot_table(
        index=["question_id", "difficulty", "question"],
        columns="system",
        values=value,
        aggfunc="first",
    ).reset_index()


def _cost_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "question_id",
        "difficulty",
        "question",
        "system",
        "sql_stage_runtime_seconds",
        "sql_stage_total_tokens",
        "sql_stage_llm_calls",
        "sql_stage_mcp_calls",
        "sql_stage_sql_executions",
    ]
    return frame[[column for column in columns if column in frame.columns]].copy()


def _reference_validation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    questions = frame.drop_duplicates("question_id")
    return pd.DataFrame(
        [
            {
                "questions": len(questions),
                "answerable_questions": int(questions["answerable"].sum()),
                "unknown_cases": int(frame["outcome"].eq("UNKNOWN").sum()),
            }
        ]
    )


def _result_size_summary(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby("system", as_index=False).agg(
        avg_rows_returned=("stored_result_row_count", "mean"),
        truncated_rate=("stored_result_truncated", "mean"),
    )
    grouped["empty_result_rate"] = (
        frame.assign(empty=frame["stored_result_row_count"].eq(0))
        .groupby("system")["empty"]
        .mean()
        .values
    )
    return grouped


def _profiling_usage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.groupby(["system", "difficulty"], as_index=False).agg(
        avg_profiling_calls=("profiling_calls_count", "mean"),
        profiling_used_rate=("profiling_calls_count", lambda s: s.gt(0).mean()),
    )


def _retrieved_tables_summary(frame: pd.DataFrame, traces: list[dict[str, Any]]) -> pd.DataFrame:
    rows = frame.groupby("system", as_index=False).agg(
        avg_retrieved_tables=("retrieved_tables_count", "mean")
    )
    counter: Counter[str] = Counter()
    for trace in traces:
        for table in (trace.get("trace") or {}).get("retrieved_tables", []):
            counter[str(table)] += 1
    rows["most_frequent_retrieved_tables"] = ", ".join(
        table for table, _ in counter.most_common(10)
    )
    return rows


def _mcp_usage_summary(frame: pd.DataFrame, traces: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for system, group in frame.groupby("system"):
        rows.extend(
            [
                {
                    "system": system,
                    "usage_type": "mcp_calls",
                    "count": group["sql_stage_mcp_calls"].sum()
                    if "sql_stage_mcp_calls" in group
                    else group["mcp_calls"].sum(),
                },
                {
                    "system": system,
                    "usage_type": "profiling_calls",
                    "count": group["profiling_calls_count"].sum(),
                },
                {
                    "system": system,
                    "usage_type": "sql_executions",
                    "count": group["sql_stage_sql_executions"].sum(),
                },
            ]
        )
    return pd.DataFrame(rows)


def _bucket_distribution(frame: pd.DataFrame, source: str, label: str) -> pd.DataFrame:
    values = pd.to_numeric(frame[source], errors="coerce").fillna(0)
    bucketed = frame.assign(
        **{label: values.map(lambda value: "3+" if value >= 3 else str(int(value)))}
    )
    return (
        bucketed.groupby(["system", label], as_index=False).size().rename(columns={"size": "count"})
    )


def _cost_per_success(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for system, group in frame.groupby("system"):
        successes = max(int(group["ultimate_success"].eq(True).sum()), 1)
        rows.append(
            {
                "system": system,
                "tokens_per_success": group["sql_stage_total_tokens"].sum() / successes,
                "runtime_seconds_per_success": group["sql_stage_runtime_seconds"].sum() / successes,
            }
        )
    return pd.DataFrame(rows)


def _efficiency_normalized_success(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for system, group in frame.groupby("system"):
        successes = group["ultimate_success"].eq(True).sum()
        tokens = pd.to_numeric(group["sql_stage_total_tokens"], errors="coerce").sum()
        runtime = pd.to_numeric(group["sql_stage_runtime_seconds"], errors="coerce").sum()
        rows.append(
            {
                "system": system,
                "successes_per_1k_tokens": successes / (tokens / 1000) if tokens else 0.0,
                "successes_per_second": successes / runtime if runtime else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _melt(
    data: pd.DataFrame, id_vars: list[str], value_vars: list[str], var_name: str, value_name: str
) -> pd.DataFrame:
    columns = [column for column in value_vars if column in data.columns]
    if data.empty or not columns:
        return pd.DataFrame(columns=[*id_vars, var_name, value_name])
    return data.melt(
        id_vars=[column for column in id_vars if column in data.columns],
        value_vars=columns,
        var_name=var_name,
        value_name=value_name,
    ).dropna(subset=[value_name])


def _sql_stage_call_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for system, group in frame.groupby("system", dropna=False):
        llm_calls = _numeric_group_column(group, "sql_stage_llm_calls", "llm_calls")
        mcp_calls = _numeric_group_column(group, "sql_stage_mcp_calls", "mcp_calls")
        mcp_tool_calls = _numeric_group_column(group, "profiling_calls_count")
        sql_executions = _numeric_group_column(group, "sql_stage_sql_executions", "sql_executions")
        mcp_resource_calls = (mcp_calls - mcp_tool_calls).clip(lower=0)
        rows.append(
            {
                "system": system,
                "avg_sql_stage_llm_calls": llm_calls.mean(),
                "avg_sql_stage_mcp_resource_calls": mcp_resource_calls.mean(),
                "avg_sql_stage_mcp_tool_calls": mcp_tool_calls.mean(),
                "avg_sql_stage_sql_executions": sql_executions.mean(),
            }
        )
    return pd.DataFrame(rows)


def _run_level_sql_stage_call_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    if "run_id" not in frame:
        return _sql_stage_call_breakdown(frame)

    rows = []
    for run_id, group in frame.groupby("run_id", dropna=False):
        summary = _sql_stage_call_breakdown(group)
        if summary.empty:
            continue
        summary = summary.copy()
        summary.insert(0, "run_id", run_id)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else _sql_stage_call_breakdown(frame)


def _numeric_group_column(
    group: pd.DataFrame, column: str, fallback_column: str | None = None
) -> pd.Series:
    if column in group:
        values = group[column]
    elif fallback_column and fallback_column in group:
        values = group[fallback_column]
    else:
        values = pd.Series(0, index=group.index)
    return pd.to_numeric(values, errors="coerce").fillna(0)


def _bar(
    data: pd.DataFrame,
    path: Path,
    x: str,
    y: str,
    ylabel: str,
    hue: str | None,
    percent: bool,
    order: list[str] | None = None,
    palette_override: dict[str, str] | None = None,
    y_limit: tuple[float, float] | None = None,
) -> Path | None:
    if data.empty or x not in data or y not in data:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize())
    _bar_on_axis(
        axis,
        data,
        x=x,
        y=y,
        ylabel=ylabel,
        hue=hue,
        percent=percent,
        order=order,
        palette_override=palette_override,
        y_limit=y_limit,
    )
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _bar_on_axis(
    axis: plt.Axes,
    data: pd.DataFrame,
    *,
    x: str,
    y: str,
    ylabel: str,
    hue: str | None,
    percent: bool,
    order: list[str] | None = None,
    palette_override: dict[str, str] | None = None,
    y_limit: tuple[float, float] | None = None,
    title: str | None = None,
) -> None:
    palette = palette_override or _bar_palette(data, x=x, hue=hue)
    plot_hue = hue
    legend = "auto"
    if palette is not None and hue is None:
        plot_hue = x
        legend = False
    sns.barplot(
        data=data,
        x=x,
        y=y,
        hue=plot_hue,
        order=order,
        hue_order=_hue_order(plot_hue, data),
        palette=palette,
        legend=legend,
        estimator="mean",
        errorbar="sd",
        capsize=0.08,
        saturation=1,
        err_kws={
            "color": "#000000",
            "linewidth": 0.55,
            "alpha": 0.68,
        },
        ax=axis,
    )
    axis.set_xlabel("")
    axis.set_ylabel(_axis_label(ylabel, percent=percent))
    if title is not None:
        axis.set_title(title, pad=8)
    if percent:
        axis.set_ylim(*(y_limit or (0, 1)))
        axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    elif y_limit is not None:
        axis.set_ylim(*y_limit)
    add_minor_y_grid(axis, percent=percent)
    if hue:
        _place_legend_above(axis)
    else:
        legend = axis.get_legend()
        if legend is not None:
            legend.remove()
    _format_categorical_xticklabels(axis)


def _hue_order(hue: str | None, data: pd.DataFrame) -> list[str] | None:
    if hue == "difficulty":
        return [difficulty for difficulty in DIFFICULTY_ORDER if difficulty in set(data[hue])]
    if hue == "system":
        return [system for system in SYSTEM_ORDER if system in set(data[hue])]
    return None


def _stacked(data: pd.DataFrame, path: Path, ylabel: str, percent: bool) -> Path | None:
    if data.empty:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize())
    color = _semantic_colors(data.columns)
    data.plot(kind="bar", stacked=True, ax=axis, width=0.72, color=color)
    axis.set_xlabel("")
    axis.set_ylabel(_axis_label(ylabel, percent=percent))
    if percent:
        axis.set_ylim(0, 1)
        axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    add_minor_y_grid(axis, percent=percent)
    _place_legend_above(axis)
    _format_categorical_xticklabels(axis)
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _stacked_grouped(data: pd.DataFrame, path: Path, ylabel: str, percent: bool) -> Path | None:
    if data.empty:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize(ratio=0.72))
    color = _semantic_colors(data.columns)
    data.plot(kind="bar", stacked=True, ax=axis, width=0.72, color=color)
    axis.set_xlabel("")
    axis.set_ylabel(_axis_label(ylabel, percent=percent))
    if percent:
        axis.set_ylim(0, 1)
        axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    add_minor_y_grid(axis, percent=percent)
    _place_legend_above(axis)
    _format_categorical_xticklabels(axis)
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _frontier_scatter(
    data: pd.DataFrame, path: Path, x: str, y: str, xlabel: str, ylabel: str
) -> Path | None:
    if data.empty or x not in data or y not in data or "system" not in data:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize())
    plot_data = data.assign(
        **{
            x: pd.to_numeric(data[x], errors="coerce"),
            y: pd.to_numeric(data[y], errors="coerce"),
        }
    ).dropna(subset=[x, y])
    if plot_data.empty:
        plt.close(figure)
        return None
    sns.scatterplot(
        data=plot_data,
        x=x,
        y=y,
        hue="system",
        hue_order=SYSTEM_ORDER,
        palette=SYSTEM_COLORS,
        s=70,
        ax=axis,
    )
    for _, row in plot_data.iterrows():
        axis.annotate(
            _display_label(row["system"]),
            (row[x], row[y]),
            xytext=(5, 4),
            textcoords="offset points",
            fontsize=10,
        )
    axis.set_xlabel(_axis_label(xlabel))
    axis.set_ylabel(_axis_label(ylabel, percent=True))
    axis.set_ylim(0, 1)
    axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    add_minor_y_grid(axis, percent=True)
    legend = axis.get_legend()
    if legend is not None:
        legend.remove()
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _frontier_scatter_with_runs(
    frame: pd.DataFrame, path: Path, x: str, y: str, xlabel: str, ylabel: str
) -> Path | None:
    if frame.empty or x not in frame or y not in frame or "system" not in frame:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize())
    plot_frame = frame.assign(
        **{
            x: pd.to_numeric(frame[x], errors="coerce"),
            y: pd.to_numeric(frame[y], errors="coerce"),
        }
    ).dropna(subset=[x, y])
    if plot_frame.empty:
        plt.close(figure)
        return None

    run_data = _frontier_run_points(plot_frame, x, y)
    average_data = _frontier_average_points(plot_frame, x, y)
    if run_data.empty and average_data.empty:
        plt.close(figure)
        return None

    for system in SYSTEM_ORDER:
        color = SYSTEM_COLORS.get(system)
        system_runs = run_data[run_data["system"].eq(system)]
        if not system_runs.empty:
            axis.scatter(
                system_runs[x],
                system_runs[y],
                color=color,
                alpha=0.35,
                s=46,
                linewidths=0,
                label=None,
            )

        system_average = average_data[average_data["system"].eq(system)]
        if not system_average.empty:
            axis.scatter(
                system_average[x],
                system_average[y],
                color=color,
                edgecolors="white",
                linewidths=0.9,
                s=92,
                label=_display_label(system),
            )

    axis.set_xlabel(_axis_label(xlabel))
    axis.set_ylabel(_axis_label(ylabel, percent=True))
    axis.set_ylim(0, 1)
    axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    add_minor_y_grid(axis, percent=True)
    _place_legend_above(axis)
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _frontier_run_points(frame: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    if "run_id" not in frame:
        return pd.DataFrame(columns=["system", x, y])
    return (
        frame.groupby(["run_id", "system"], as_index=False, dropna=False)
        .agg(
            **{
                x: pd.NamedAgg(column=x, aggfunc="mean"),
                y: pd.NamedAgg(column=y, aggfunc="mean"),
            }
        )
        .drop(columns=["run_id"])
    )


def _frontier_average_points(frame: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    return frame.groupby("system", as_index=False, dropna=False).agg(
        **{
            x: pd.NamedAgg(column=x, aggfunc="mean"),
            y: pd.NamedAgg(column=y, aggfunc="mean"),
        }
    )


def _box(data: pd.DataFrame, path: Path, x: str, y: str, ylabel: str) -> Path | None:
    if data.empty or x not in data or y not in data:
        return None
    figure, axis = plt.subplots(figsize=typst_figsize())
    palette = SYSTEM_COLORS if x == "system" else None
    plot_hue = x if palette is not None else None
    sns.boxplot(
        data=data,
        x=x,
        y=y,
        hue=plot_hue,
        order=SYSTEM_ORDER,
        palette=palette,
        legend=False,
        ax=axis,
    )
    axis.set_xlabel("")
    axis.set_ylabel(_axis_label(ylabel))
    add_minor_y_grid(axis)
    _format_categorical_xticklabels(axis)
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _critic_diagnostics_figure(
    frame: pd.DataFrame, tables: dict[str, pd.DataFrame], path: Path
) -> Path | None:
    review_data = _melt(
        tables["T15"],
        ["system"],
        ["acceptance_rate", "intervention_rate", "abort_rate"],
        "metric",
        "rate",
    )
    recovery_data = _critic_recovery_regression_plot(frame)
    if review_data.empty and recovery_data.empty:
        return None

    figure, axes = plt.subplots(1, 2, figsize=typst_figsize())
    _bar_on_axis(
        axes[0],
        review_data,
        x="metric",
        y="rate",
        ylabel="Rate",
        hue=None,
        percent=True,
        palette_override={
            "acceptance_rate": STRONG_TEAL,
            "intervention_rate": STRONG_PURPLE,
            "abort_rate": STRONG_GRAY,
        },
        title="Critic action",
    )
    _rotate_categorical_xticklabels(axes[0], long_label_threshold=0)
    _bar_on_axis(
        axes[1],
        recovery_data,
        x="metric",
        y="count",
        ylabel="Cases",
        hue=None,
        percent=False,
        palette_override={
            "recovered": STRONG_TEAL,
            "regressed": STRONG_GRAY,
            "intervened_failed": STRONG_PURPLE,
        },
        title="Critic effect",
    )
    figure.tight_layout(w_pad=1.5)
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _critic_decision_palette(data: pd.DataFrame) -> dict[str, str]:
    base = {
        "ACCEPT": STRONG_TEAL,
        "REPAIR": STRONG_PURPLE,
        "ABORT": STRONG_GRAY,
        "MISSING": LIGHT_TEAL,
        "PROFILE_VALUES": LIGHT_TEAL,
        "REGENERATE_SQL": STRONG_PURPLE,
    }
    if "critic_decision" not in data:
        return base
    return {
        str(decision): base.get(str(decision), STRONG_GRAY)
        for decision in data["critic_decision"].dropna().unique()
    }


def _bar_palette(data: pd.DataFrame, *, x: str, hue: str | None) -> dict[str, str] | None:
    semantic_column = hue or x
    if semantic_column in data:
        semantic_palette = _semantic_palette(data[semantic_column].dropna().astype(str).unique())
        if semantic_palette is not None:
            return semantic_palette
    return _system_palette(data, x=x, hue=hue)


def _system_palette(data: pd.DataFrame, *, x: str, hue: str | None) -> dict[str, str] | None:
    if hue == "system":
        return SYSTEM_COLORS
    if hue is None and x == "system":
        return {
            system: SYSTEM_COLORS[system]
            for system in SYSTEM_ORDER
            if system in set(data[x].dropna().astype(str))
        }
    return None


def _semantic_palette(labels: Any) -> dict[str, str] | None:
    label_list = [str(label) for label in labels]
    if not label_list:
        return None
    categories = {label: _semantic_category(label) for label in label_list}
    if all(category is None for category in categories.values()):
        return None
    fallback = iter(SEMANTIC_FALLBACK_COLORS)
    color_offsets = {category: 0 for category in SEMANTIC_COLOR_SEQUENCES}
    palette = {}
    for label, category in categories.items():
        if category in SEMANTIC_COLOR_SEQUENCES:
            colors = SEMANTIC_COLOR_SEQUENCES[category]
            offset = color_offsets[category]
            palette[label] = colors[offset] if offset < len(colors) else next(fallback, colors[-1])
            color_offsets[category] += 1
        else:
            palette[label] = next(fallback, OTHER_COLOR)
    return palette


def _semantic_colors(labels: Any) -> list[str] | None:
    label_list = [str(label) for label in labels]
    palette = _semantic_palette(label_list)
    if palette is None:
        return None
    return [palette[label] for label in label_list]


def _semantic_category(label: str) -> str | None:
    normalized = label.lower()
    success_terms = (
        "success",
        "correct_rejection",
        "recovered",
        "accepted_correct",
        "precision",
        "recall",
        "f1",
    )
    error_terms = (
        "error",
        "wrong",
        "false",
        "failed",
        "failure",
        "regressed",
        "abort",
        "rejection",
        "unknown",
        "empty_result",
        "max_iterations",
    )
    other_terms = (
        "acceptance",
        "intervention",
        "mcp",
        "profiling",
        "sql_execution",
        "token",
        "runtime",
        "calls",
    )
    if any(term in normalized for term in success_terms):
        return "success"
    if any(term in normalized for term in error_terms):
        return "error"
    if normalized == "none" or any(term in normalized for term in other_terms):
        return "other"
    return None


def _place_legend_above(axis: plt.Axes) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if not labels:
        return
    display_labels = [_legend_label(label) for label in labels]
    legend = axis.get_legend()
    if legend is not None:
        legend.remove()
    square_handles = [_square_legend_handle(handle) for handle in handles]
    axis.legend(
        square_handles,
        display_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=len(display_labels),
        frameon=False,
        handlelength=0.9,
        handleheight=0.9,
        columnspacing=1.4,
        handletextpad=0.6,
        borderaxespad=0.0,
    )


def _legend_label(label: str) -> str:
    return _display_label(label)


def _display_label(label: object) -> str:
    text = str(label)
    return _title_display_label(DISPLAY_LABELS.get(text, text.replace("_", " ")))


def _title_display_label(label: str) -> str:
    formatted = label.title()
    replacements = {
        "Sql": "SQL",
        "Mcp": "MCP",
        "Llm": "LLM",
        "Json": "JSON",
        "F1": "F1",
    }
    for old, new in replacements.items():
        formatted = formatted.replace(old, new)
    return formatted


def _axis_label(label: str, *, percent: bool = False) -> str:
    formatted = label.title()
    replacements = {
        "Sql": "SQL",
        "Mcp": "MCP",
        "Llm": "LLM",
        "Sql-Stage": "SQL-Stage",
        "(S)": "(s)",
        "1K": "1k",
    }
    for old, new in replacements.items():
        formatted = formatted.replace(old, new)
    if percent and "%" not in formatted:
        formatted = f"{formatted} (%)"
    return formatted


def _format_categorical_xticklabels(axis: plt.Axes) -> None:
    ticks = axis.get_xticks()
    display_labels = [_display_label(label.get_text()) for label in axis.get_xticklabels()]
    axis.set_xticks(ticks)
    axis.set_xticklabels(display_labels)
    _rotate_categorical_xticklabels(axis)


def _format_categorical_yticklabels(axis: plt.Axes) -> None:
    ticks = axis.get_yticks()
    display_labels = [_display_label(label.get_text()) for label in axis.get_yticklabels()]
    axis.set_yticks(ticks)
    axis.set_yticklabels(display_labels)


def _rotate_categorical_xticklabels(axis: plt.Axes, long_label_threshold: int = 12) -> None:
    labels = axis.get_xticklabels()
    if not labels:
        return
    has_long_label = any(len(label.get_text()) > long_label_threshold for label in labels)
    rotation = 45 if has_long_label else 0
    horizontal_alignment = "right" if has_long_label else "center"
    for label in labels:
        label.set_rotation(rotation)
        label.set_horizontalalignment(horizontal_alignment)
        label.set_rotation_mode("anchor")


def _square_legend_handle(handle: Any) -> Patch:
    color = _legend_color(handle)
    return Patch(facecolor=color, edgecolor=color, linewidth=1.1)


def _legend_color(handle: Any) -> Any:
    if hasattr(handle, "get_facecolor"):
        color = handle.get_facecolor()
        if isinstance(color, list | tuple) and len(color) > 0:
            return color[0] if not isinstance(color[0], float) else color
        if hasattr(color, "__len__") and len(color) > 0:
            return color[0]
    if hasattr(handle, "patches") and handle.patches:
        return handle.patches[0].get_facecolor()
    if hasattr(handle, "get_color"):
        return handle.get_color()
    return "#4e4e4e"


def _heatmap(
    data: pd.DataFrame,
    path: Path,
    categorical: bool,
    colorbar_label: str | None = None,
    cmap: Any | None = None,
) -> Path | None:
    if data.empty:
        return None
    matrix = data.set_index(data.columns[0])
    matrix = matrix[[column for column in matrix.columns if column in SYSTEM_ORDER]]
    if matrix.empty:
        return None
    if categorical:
        matrix = matrix.fillna("MISSING").astype(str)
        categories = {
            value: index for index, value in enumerate(sorted(pd.unique(matrix.values.ravel())))
        }
        plot_data = matrix.replace(categories).astype(float)
    else:
        plot_data = matrix.apply(pd.to_numeric, errors="coerce")
    figure, axis = plt.subplots(figsize=typst_figsize(ratio=0.8))
    heatmap = sns.heatmap(plot_data, annot=False, cmap=cmap or "viridis", cbar=True, ax=axis)
    if categorical and heatmap.collections:
        colorbar = heatmap.collections[0].colorbar
        if colorbar is not None:
            labels_by_index = {index: value for value, index in categories.items()}
            ticks = sorted(labels_by_index)
            colorbar.set_ticks(ticks)
            colorbar.set_ticklabels([_display_label(labels_by_index[tick]) for tick in ticks])
    elif colorbar_label and heatmap.collections:
        colorbar = heatmap.collections[0].colorbar
        if colorbar is not None:
            colorbar.set_label(colorbar_label)
    axis.set_xlabel("")
    axis.set_ylabel("")
    _format_categorical_xticklabels(axis)
    _format_categorical_yticklabels(axis)
    figure.tight_layout()
    figure.savefig(path, format="svg")
    plt.close(figure)
    return path


def _answerable_success(frame: pd.DataFrame) -> pd.DataFrame:
    return aggregate_metrics(frame[frame["answerable"].eq(True)].to_dict(orient="records"))[
        "by_system"
    ]


def _unanswerable_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return aggregate_metrics(frame[frame["answerable"].eq(False)].to_dict(orient="records"))[
        "by_system"
    ]


def _run_level_metrics(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    if "run_id" not in frame:
        return pd.DataFrame()

    rows = []
    for run_id, group in frame.groupby("run_id", dropna=False):
        summary = aggregate_metrics(group.to_dict(orient="records")).get(key, pd.DataFrame())
        if summary.empty:
            continue
        summary = summary.copy()
        summary.insert(0, "run_id", run_id)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _run_level_unanswerable_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if "run_id" not in frame:
        return _unanswerable_summary(frame)

    rows = []
    for run_id, group in frame[frame["answerable"].eq(False)].groupby("run_id", dropna=False):
        summary = _unanswerable_summary(group)
        if summary.empty:
            continue
        summary = summary.copy()
        summary.insert(0, "run_id", run_id)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else _unanswerable_summary(frame)


def _error_pivot(frame: pd.DataFrame, index: str) -> pd.DataFrame:
    counts = (
        frame.groupby([index, "error_type"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    pivot = counts.pivot(index=index, columns="error_type", values="count").fillna(0)
    return _row_rates(pivot.reset_index(), [index]).set_index(index)


def _error_distribution_by_difficulty_system(frame: pd.DataFrame) -> pd.DataFrame:
    data = _exclude_unanswerable_difficulty(frame)
    data = data[data["error_type"].ne("unanswerable")]
    if data.empty:
        return pd.DataFrame()
    counts = (
        data.groupby(["difficulty", "system", "error_type"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    pivot = counts.pivot_table(
        index=["difficulty", "system"],
        columns="error_type",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )
    pivot = _row_rates(pivot.reset_index(), ["difficulty", "system"])
    pivot["label"] = pivot.apply(
        lambda row: f"{_display_label(row['difficulty'])}\n{_display_label(row['system'])}",
        axis=1,
    )
    pivot["difficulty_order"] = pivot["difficulty"].map(
        {difficulty: index for index, difficulty in enumerate(DIFFICULTY_ORDER)}
    )
    pivot["system_order"] = pivot["system"].map(
        {system: index for index, system in enumerate(SYSTEM_ORDER)}
    )
    pivot = pivot.sort_values(["difficulty_order", "system_order"])
    value_columns = [
        column for column in ERROR_TYPE_ORDER if column in pivot.columns and pivot[column].sum() > 0
    ]
    return pivot.set_index("label")[value_columns]


def _exclude_unanswerable_difficulty(frame: pd.DataFrame) -> pd.DataFrame:
    if "difficulty" not in frame:
        return frame.copy()
    return frame[frame["difficulty"].ne("unanswerable")].copy()


def _false_rejections_by_system(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[frame["answerable"].eq(True) & _predicted_rejection(frame)]
        .groupby("system", as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )


def _false_rejection_share_by_system(frame: pd.DataFrame) -> pd.DataFrame:
    counts = _false_rejections_by_system(frame)
    total = counts["count"].sum() if "count" in counts else 0
    if counts.empty or total == 0:
        return pd.DataFrame({"system": SYSTEM_ORDER, "share": [0.0, 0.0, 0.0]})
    counts["share"] = counts["count"] / total
    return counts


def _false_rejections_by_difficulty(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[frame["answerable"].eq(True) & _predicted_rejection(frame)]
        .groupby("difficulty", as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )


def _success_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.assign(success=frame["ultimate_success"].astype(int))
        .pivot_table(index="question_id", columns="system", values="success", aggfunc="first")
        .reset_index()
    )


def _difficulty_system_matrix(summary: pd.DataFrame) -> pd.DataFrame:
    matrix = summary.pivot(
        index="difficulty", columns="system", values="ultimate_success_rate"
    ).reset_index()
    matrix["difficulty_order"] = matrix["difficulty"].map(
        {difficulty: index for index, difficulty in enumerate(DIFFICULTY_ORDER)}
    )
    return matrix.sort_values("difficulty_order").drop(columns=["difficulty_order"])


def _iterations_recovery(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame[frame["system"].eq("C")].copy()
    data["recovered"] = data["first_pass_success"].eq(False) & data["ultimate_success"].eq(True)
    recovered = data.groupby("iterations", as_index=False).agg(
        recovery_rate=("recovered", "mean"), count=("recovered", "size")
    )
    return recovered[recovered["iterations"].gt(0)].reset_index(drop=True)


def _unanswerable_prf_plot_data(frame: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    metric_columns = ["unanswerable_precision", "unanswerable_recall", "unanswerable_f1"]
    if "run_id" not in frame:
        return _melt(fallback, ["system"], metric_columns, "metric", "score")

    rows = []
    for run_id, group in frame.groupby("run_id"):
        scores = unanswerable_scores(group.to_dict(orient="records"))
        for system, metrics in scores.items():
            rows.append(
                {
                    "run_id": run_id,
                    "system": system,
                    **{metric: metrics.get(metric) for metric in metric_columns},
                }
            )
    return _melt(pd.DataFrame(rows), ["run_id", "system"], metric_columns, "metric", "score")


def _teal_to_purple_cmap() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(
        "teal_to_purple",
        [SYSTEM_COLORS["B"], "#77b5b6", "#9671bd", SYSTEM_COLORS["C"]],
    )


def _critic_recovery_regression_plot(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    intervention = _critic_intervention_mask(data)
    recovered = (
        intervention & data["first_pass_success"].eq(False) & data["ultimate_success"].eq(True)
    )
    regressed = _critic_regression_mask(data)
    return pd.DataFrame(
        [
            {"metric": "recovered", "count": int(recovered.sum())},
            {"metric": "regressed", "count": int(regressed.sum())},
            {
                "metric": "intervened_failed",
                "count": int((intervention & data["ultimate_success"].ne(True)).sum()),
            },
        ]
    )


def _critic_intervention_by_difficulty(frame: pd.DataFrame) -> pd.DataFrame:
    data = _system_c(frame)
    if data.empty:
        return pd.DataFrame(columns=["difficulty", "intervention_rate"])
    data = data.assign(intervened=_critic_intervention_mask(data))
    return data.groupby("difficulty", as_index=False).agg(intervention_rate=("intervened", "mean"))


def _top_errors(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[frame["error_type"].ne("none")]
        .groupby("error_type", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
        .head(10)
    )


def _top_retrieved_tables(traces: list[dict[str, Any]]) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for trace in traces:
        for table in (trace.get("trace") or {}).get("retrieved_tables", []):
            counter[str(table)] += 1
    return pd.DataFrame(
        [{"table": table, "count": count} for table, count in counter.most_common(10)]
    )


def _top_sql_tables(frame: pd.DataFrame) -> pd.DataFrame:
    from evaluation.benchmark.sql_utils import extract_tables

    counter: Counter[str] = Counter()
    for sql in frame.get("final_generated_sql", pd.Series(dtype=object)).dropna():
        for table in extract_tables(str(sql)):
            counter[table] += 1
    return pd.DataFrame(
        [{"table": table, "count": count} for table, count in counter.most_common(10)]
    )
