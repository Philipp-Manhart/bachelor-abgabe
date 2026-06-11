import marimo

__generated_with = "0.23.6"
app = marimo.App(width="wide")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
        # Combined Benchmark Runs

        This notebook aggregates all currently available `results/run_*` benchmark
        outputs. It combines raw observations first, computes metrics per run, and
        only then reports mean and standard deviation across runs.

        This is the defensible thesis workflow: stochastic benchmark variation is
        represented at the run level instead of hidden by averaging already exported
        summary tables.
        """
    )
    return (mo,)


@app.cell
def _():
    import json
    from pathlib import Path

    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    from agent_orchestrator.config import PROJECT_ROOT
    from evaluation.benchmark.artifacts import (
        FIGURE_OUTPUT_FILENAMES,
        LEGACY_TABLE_FILENAMES,
        SYSTEM_COLORS,
        TABLE_SPECS,
        _bar_palette,
        _format_categorical_xticklabels,
        _place_legend_above,
        generate_benchmark_artifacts,
    )
    from evaluation.paper_plot_style import add_minor_y_grid, set_paper_style, typst_figsize

    BASE_DIR = PROJECT_ROOT / "results"
    COMBINED_DIR = BASE_DIR / "combined"
    TABLES_DIR = COMBINED_DIR / "tables"
    FIGURES_DIR = COMBINED_DIR / "figures"

    for directory in (COMBINED_DIR, TABLES_DIR, FIGURES_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    set_paper_style()

    SYSTEM_ORDER = ["A", "B", "C"]
    DIFFICULTY_ORDER = ["easy", "medium", "hard"]

    def relative(path: Path) -> str:
        return str(path.relative_to(PROJECT_ROOT))

    return (
        BASE_DIR,
        COMBINED_DIR,
        DIFFICULTY_ORDER,
        FIGURES_DIR,
        FIGURE_OUTPUT_FILENAMES,
        LEGACY_TABLE_FILENAMES,
        PROJECT_ROOT,
        SYSTEM_COLORS,
        SYSTEM_ORDER,
        TABLES_DIR,
        TABLE_SPECS,
        _bar_palette,
        _format_categorical_xticklabels,
        _place_legend_above,
        add_minor_y_grid,
        generate_benchmark_artifacts,
        json,
        np,
        pd,
        plt,
        relative,
        typst_figsize,
    )


@app.cell
def _(BASE_DIR, COMBINED_DIR, generate_benchmark_artifacts, json, pd):
    run_dirs = sorted(path for path in BASE_DIR.glob("run_*") if path.is_dir())

    result_frames = []
    combined_traces = []
    skipped_runs = []

    for run_dir in run_dirs:
        results_path = run_dir / "results" / "benchmark_results.csv"
        traces_path = run_dir / "results" / "benchmark_traces.jsonl"

        if not results_path.exists():
            skipped_runs.append(run_dir.name)
            continue

        frame = pd.read_csv(results_path)
        frame["run_id"] = run_dir.name
        result_frames.append(frame)

        if traces_path.exists():
            for line in traces_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                trace = json.loads(line)
                trace["run_id"] = run_dir.name
                combined_traces.append(trace)

    if not result_frames:
        raise FileNotFoundError(f"No benchmark_results.csv files found below {BASE_DIR}")

    results = pd.concat(result_frames, ignore_index=True)

    combined_results_path = COMBINED_DIR / "combined_benchmark_results.csv"
    combined_traces_path = COMBINED_DIR / "combined_benchmark_traces.jsonl"
    results.to_csv(combined_results_path, index=False)
    results.to_csv(COMBINED_DIR / "benchmark_results.csv", index=False)
    combined_traces_path.write_text(
        "\n".join(json.dumps(trace, ensure_ascii=False) for trace in combined_traces) + "\n",
        encoding="utf-8",
    )
    (COMBINED_DIR / "benchmark_traces.jsonl").write_text(
        "\n".join(json.dumps(trace, ensure_ascii=False) for trace in combined_traces) + "\n",
        encoding="utf-8",
    )
    combined_artifact_paths = generate_benchmark_artifacts(COMBINED_DIR, COMBINED_DIR)

    return (
        combined_artifact_paths,
        combined_results_path,
        combined_traces,
        combined_traces_path,
        results,
        run_dirs,
        skipped_runs,
    )


@app.cell
def _(combined_results_path, combined_traces_path, mo, relative, results, run_dirs, skipped_runs):
    mo.md(
        f"""
        ## Loaded Runs

        - Detected run directories: **{len(run_dirs)}**
        - Combined raw result rows: **{len(results)}**
        - Runs represented in raw results: **{results["run_id"].nunique()}**
        - Combined results: `{relative(combined_results_path)}`
        - Combined traces: `{relative(combined_traces_path)}`
        - Skipped run directories without raw results: **{", ".join(skipped_runs) or "none"}**
        """
    )
    return


@app.cell
def _(DIFFICULTY_ORDER, SYSTEM_ORDER, np, pd, results):
    def _mean_std_table(
        frame: pd.DataFrame,
        group_cols: list[str],
        metrics: dict[str, tuple[str, str]],
    ) -> pd.DataFrame:
        per_run_aggregations = {
            name: pd.NamedAgg(column=column, aggfunc=func)
            for name, (column, func) in metrics.items()
        }
        per_run = (
            frame.groupby(["run_id", *group_cols], dropna=False)
            .agg(**per_run_aggregations)
            .reset_index()
        )

        summary = (
            per_run.groupby(group_cols, dropna=False)
            .agg(
                **{
                    f"{metric}_{suffix}": pd.NamedAgg(column=metric, aggfunc=suffix)
                    for metric in metrics
                    for suffix in ("mean", "std")
                },
                runs=pd.NamedAgg(column="run_id", aggfunc="nunique"),
            )
            .reset_index()
        )

        std_defaults = {column: 0.0 for column in summary.columns if column.endswith("_std")}
        return summary.fillna(std_defaults)

    def _ordered(frame: pd.DataFrame, column: str, order: list[str]) -> pd.DataFrame:
        if column not in frame:
            return frame
        data = frame.copy()
        rank = {value: index for index, value in enumerate(order)}
        data["_sort_rank"] = data[column].astype(str).map(rank).fillna(len(order))
        return (
            data.sort_values(["_sort_rank", column])
            .drop(columns="_sort_rank")
            .reset_index(drop=True)
        )

    def _mean_std(mean: float, std: float, percent: bool = False, digits: int = 2) -> str:
        if pd.isna(mean):
            return ""
        std = 0.0 if pd.isna(std) else std
        if percent:
            return f"{mean * 100:.1f}% +/- {std * 100:.1f}"
        return f"{mean:.{digits}f} +/- {std:.{digits}f}"

    core_metrics = {
        "first_pass_success_rate": ("first_pass_success", "mean"),
        "ultimate_success_rate": ("ultimate_success", "mean"),
        "correct_rejection_rate": ("correct_rejection", "mean"),
        "false_answer_rate": ("false_answer", "mean"),
        "avg_iterations": ("iterations", "mean"),
        "avg_sql_stage_tokens": ("sql_stage_total_tokens", "mean"),
        "avg_sql_stage_runtime": ("sql_stage_runtime_seconds", "mean"),
        "avg_end_to_end_tokens": ("end_to_end_total_tokens", "mean"),
        "avg_end_to_end_runtime": ("end_to_end_runtime_seconds", "mean"),
    }

    summary_by_system = _ordered(
        _mean_std_table(results, ["system"], core_metrics), "system", SYSTEM_ORDER
    )
    summary_by_difficulty = _ordered(
        _mean_std_table(results, ["difficulty"], core_metrics), "difficulty", DIFFICULTY_ORDER
    )
    summary_by_system_difficulty = _ordered(
        _mean_std_table(results, ["system", "difficulty"], core_metrics),
        "difficulty",
        DIFFICULTY_ORDER,
    )
    summary_by_system_difficulty = _ordered(summary_by_system_difficulty, "system", SYSTEM_ORDER)

    summary_by_system_display = pd.DataFrame(
        {
            "system": summary_by_system["system"],
            "first_pass_success": [
                _mean_std(m, s, percent=True)
                for m, s in zip(
                    summary_by_system["first_pass_success_rate_mean"],
                    summary_by_system["first_pass_success_rate_std"],
                    strict=False,
                )
            ],
            "ultimate_success": [
                _mean_std(m, s, percent=True)
                for m, s in zip(
                    summary_by_system["ultimate_success_rate_mean"],
                    summary_by_system["ultimate_success_rate_std"],
                    strict=False,
                )
            ],
            "correct_rejection": [
                _mean_std(m, s, percent=True)
                for m, s in zip(
                    summary_by_system["correct_rejection_rate_mean"],
                    summary_by_system["correct_rejection_rate_std"],
                    strict=False,
                )
            ],
            "false_answer": [
                _mean_std(m, s, percent=True)
                for m, s in zip(
                    summary_by_system["false_answer_rate_mean"],
                    summary_by_system["false_answer_rate_std"],
                    strict=False,
                )
            ],
            "avg_iterations": [
                _mean_std(m, s)
                for m, s in zip(
                    summary_by_system["avg_iterations_mean"],
                    summary_by_system["avg_iterations_std"],
                    strict=False,
                )
            ],
            "avg_sql_stage_tokens": [
                _mean_std(m, s)
                for m, s in zip(
                    summary_by_system["avg_sql_stage_tokens_mean"],
                    summary_by_system["avg_sql_stage_tokens_std"],
                    strict=False,
                )
            ],
            "avg_sql_stage_runtime_seconds": [
                _mean_std(m, s)
                for m, s in zip(
                    summary_by_system["avg_sql_stage_runtime_mean"],
                    summary_by_system["avg_sql_stage_runtime_std"],
                    strict=False,
                )
            ],
        }
    )

    return (
        core_metrics,
        summary_by_difficulty,
        summary_by_system,
        summary_by_system_difficulty,
        summary_by_system_display,
        _mean_std,
        _mean_std_table,
        _ordered,
    )


@app.cell
def _(COMBINED_DIR, pd, results):
    answerability_per_run = (
        results.groupby(["run_id", "system", "answerable"], dropna=False)
        .agg(
            first_pass_success_rate=("first_pass_success", "mean"),
            ultimate_success_rate=("ultimate_success", "mean"),
            correct_rejection_rate=("correct_rejection", "mean"),
            false_answer_rate=("false_answer", "mean"),
            cases=("question_id", "count"),
        )
        .reset_index()
    )
    summary_answerability = (
        answerability_per_run.groupby(["system", "answerable"], dropna=False)
        .agg(
            first_pass_success_rate_mean=("first_pass_success_rate", "mean"),
            first_pass_success_rate_std=("first_pass_success_rate", "std"),
            ultimate_success_rate_mean=("ultimate_success_rate", "mean"),
            ultimate_success_rate_std=("ultimate_success_rate", "std"),
            correct_rejection_rate_mean=("correct_rejection_rate", "mean"),
            correct_rejection_rate_std=("correct_rejection_rate", "std"),
            false_answer_rate_mean=("false_answer_rate", "mean"),
            false_answer_rate_std=("false_answer_rate", "std"),
            cases_mean=("cases", "mean"),
            cases_std=("cases", "std"),
            runs=("run_id", "nunique"),
        )
        .reset_index()
        .fillna(0.0)
    )

    efficiency_per_run = (
        results.groupby(["run_id", "system"], dropna=False)
        .agg(
            avg_sql_stage_llm_calls=("sql_stage_llm_calls", "mean"),
            avg_sql_stage_mcp_calls=("sql_stage_mcp_calls", "mean"),
            avg_sql_stage_sql_executions=("sql_stage_sql_executions", "mean"),
            avg_sql_stage_total_tokens=("sql_stage_total_tokens", "mean"),
            avg_sql_stage_runtime_seconds=("sql_stage_runtime_seconds", "mean"),
            avg_end_to_end_total_tokens=("end_to_end_total_tokens", "mean"),
            avg_end_to_end_runtime_seconds=("end_to_end_runtime_seconds", "mean"),
        )
        .reset_index()
    )
    summary_efficiency = (
        efficiency_per_run.groupby("system", dropna=False)
        .agg(
            **{
                f"{column}_{suffix}": pd.NamedAgg(column=column, aggfunc=suffix)
                for column in efficiency_per_run.columns
                if column not in {"run_id", "system"}
                for suffix in ("mean", "std")
            },
            runs=pd.NamedAgg(column="run_id", aggfunc="nunique"),
        )
        .reset_index()
        .fillna(0.0)
    )

    outcome_counts_total = (
        results.groupby(["system", "outcome"], dropna=False).size().reset_index(name="total_count")
    )
    outcome_counts_per_run = (
        results.groupby(["run_id", "system", "outcome"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    summary_outcomes = (
        outcome_counts_per_run.groupby(["system", "outcome"], dropna=False)
        .agg(
            mean_count=("count", "mean"),
            std_count=("count", "std"),
            total_count=("count", "sum"),
            runs=("run_id", "nunique"),
        )
        .reset_index()
        .fillna(0.0)
    )
    summary_outcomes = summary_outcomes.merge(
        outcome_counts_total, on=["system", "outcome"], suffixes=("", "_check")
    )

    return (
        answerability_per_run,
        efficiency_per_run,
        outcome_counts_per_run,
        outcome_counts_total,
        summary_answerability,
        summary_efficiency,
        summary_outcomes,
    )


@app.cell
def _(pd, results):
    system_c = results[results["system"].eq("C")].copy()
    critic_decision = system_c["critic_decision"].fillna("")
    critic_intervened = critic_decision.ne("") & (
        critic_decision.ne("ACCEPT") | system_c["iterations"].gt(0)
    )

    critic_frame = system_c.assign(
        critic_accepted=critic_decision.eq("ACCEPT"),
        critic_intervened=critic_intervened,
        critic_recovered=system_c["first_pass_success"].eq(False)
        & system_c["ultimate_success"].eq(True),
        critic_regressed=system_c["first_pass_success"].eq(True)
        & system_c["ultimate_success"].ne(True)
        & critic_intervened,
    )

    critic_per_run = (
        critic_frame.groupby("run_id", dropna=False)
        .agg(
            reviewed_cases=("question_id", "count"),
            critic_acceptance_rate=("critic_accepted", "mean"),
            critic_intervention_rate=("critic_intervened", "mean"),
            critic_recovery_rate=("critic_recovered", "mean"),
            critic_regression_rate=("critic_regressed", "mean"),
            avg_repair_iterations=("iterations", "mean"),
            avg_critic_calls=("critic_calls", "mean"),
            avg_critic_total_tokens=("critic_total_tokens", "mean"),
        )
        .reset_index()
    )

    critic_summary = (
        critic_per_run.agg(
            {
                "reviewed_cases": ["mean", "std"],
                "critic_acceptance_rate": ["mean", "std"],
                "critic_intervention_rate": ["mean", "std"],
                "critic_recovery_rate": ["mean", "std"],
                "critic_regression_rate": ["mean", "std"],
                "avg_repair_iterations": ["mean", "std"],
                "avg_critic_calls": ["mean", "std"],
                "avg_critic_total_tokens": ["mean", "std"],
            }
        )
        .transpose()
        .reset_index(names="metric")
        .fillna(0.0)
    )

    return critic_frame, critic_per_run, critic_summary


@app.cell
def _(
    COMBINED_DIR,
    summary_answerability,
    summary_by_difficulty,
    summary_by_system,
    summary_by_system_difficulty,
    summary_efficiency,
    summary_outcomes,
    critic_summary,
):
    summary_paths = {
        "combined_summary_by_system": COMBINED_DIR / "combined_summary_by_system.csv",
        "combined_summary_by_difficulty": COMBINED_DIR / "combined_summary_by_difficulty.csv",
        "combined_summary_by_system_difficulty": COMBINED_DIR
        / "combined_summary_by_system_difficulty.csv",
        "combined_summary_answerability": COMBINED_DIR / "combined_summary_answerability.csv",
        "combined_summary_efficiency": COMBINED_DIR / "combined_summary_efficiency.csv",
        "combined_summary_critic": COMBINED_DIR / "combined_summary_critic.csv",
        "combined_summary_outcomes": COMBINED_DIR / "combined_summary_outcomes.csv",
    }

    summary_by_system.to_csv(summary_paths["combined_summary_by_system"], index=False)
    summary_by_difficulty.to_csv(summary_paths["combined_summary_by_difficulty"], index=False)
    summary_by_system_difficulty.to_csv(
        summary_paths["combined_summary_by_system_difficulty"], index=False
    )
    summary_answerability.to_csv(summary_paths["combined_summary_answerability"], index=False)
    summary_efficiency.to_csv(summary_paths["combined_summary_efficiency"], index=False)
    critic_summary.to_csv(summary_paths["combined_summary_critic"], index=False)
    summary_outcomes.to_csv(summary_paths["combined_summary_outcomes"], index=False)

    return (summary_paths,)


@app.cell
def _(BASE_DIR, LEGACY_TABLE_FILENAMES, TABLES_DIR, TABLE_SPECS, pd):
    def _combine_exported_table(artifact_id: str, filename: str) -> pd.DataFrame:
        frames = []
        for run_dir in sorted(path for path in BASE_DIR.glob("run_*") if path.is_dir()):
            table_path = run_dir / "tables" / filename
            if not table_path.exists():
                legacy_filename = LEGACY_TABLE_FILENAMES.get(artifact_id)
                table_path = run_dir / "tables" / legacy_filename if legacy_filename else table_path
            if not table_path.exists():
                continue
            frame = pd.read_csv(table_path)
            frame["run_id"] = run_dir.name
            frames.append(frame)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        numeric_columns = [
            column
            for column in combined.select_dtypes(include="number").columns
            if column != "run_id"
        ]
        key_columns = [
            column
            for column in combined.columns
            if column not in numeric_columns and column != "run_id"
        ]

        raw_path = TABLES_DIR / filename.replace(".csv", "_combined_raw.csv")
        summary_path = TABLES_DIR / filename
        combined.to_csv(raw_path, index=False)

        if not numeric_columns:
            combined.drop_duplicates(key_columns).to_csv(summary_path, index=False)
            return combined.drop_duplicates(key_columns)

        if key_columns:
            summary = (
                combined.groupby(key_columns, dropna=False)
                .agg(
                    **{
                        f"{column}_{suffix}": pd.NamedAgg(column=column, aggfunc=suffix)
                        for column in numeric_columns
                        for suffix in ("mean", "std")
                    },
                    runs=pd.NamedAgg(column="run_id", aggfunc="nunique"),
                )
                .reset_index()
                .fillna(0.0)
            )
        else:
            summary = (
                combined.agg({column: ["mean", "std"] for column in numeric_columns})
                .transpose()
                .reset_index(names="metric")
                .fillna(0.0)
            )

        summary.to_csv(summary_path, index=False)
        return summary

    combined_table_summaries = {
        spec.artifact_id: _combine_exported_table(spec.artifact_id, spec.filename)
        for spec in TABLE_SPECS
    }

    return (combined_table_summaries,)


@app.cell
def _(
    FIGURES_DIR,
    SYSTEM_COLORS,
    SYSTEM_ORDER,
    _bar_palette,
    _format_categorical_xticklabels,
    _place_legend_above,
    add_minor_y_grid,
    np,
    pd,
    plt,
    typst_figsize,
):
    def _metric_plot_frame(
        per_run: pd.DataFrame,
        id_vars: list[str],
        value_vars: list[str],
    ) -> pd.DataFrame:
        melted = per_run.melt(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name="metric",
            value_name="value",
        )
        return (
            melted.groupby([*id_vars[1:], "metric"], dropna=False)
            .agg(mean=("value", "mean"), std=("value", "std"))
            .reset_index()
            .fillna(0.0)
        )

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

    def _save_grouped_bars(
        data: pd.DataFrame,
        path,
        x_col: str,
        y_col: str,
        hue_col: str | None,
        ylabel: str,
        title: str,
        x_order: list[str] | None = None,
        hue_order: list[str] | None = None,
        percent: bool = False,
    ):
        fig, ax = plt.subplots(figsize=typst_figsize())
        x_values = x_order or list(data[x_col].dropna().astype(str).unique())
        x = np.arange(len(x_values))
        mean_column = f"{y_col}_mean" if f"{y_col}_mean" in data.columns else "mean"
        std_column = f"{y_col}_std" if f"{y_col}_std" in data.columns else "std"
        palette = _bar_palette(data, x=x_col, hue=hue_col)
        error_style = {
            "ecolor": "#000000",
            "elinewidth": 0.55,
            "capthick": 0.55,
            "alpha": 0.68,
        }

        if hue_col is None:
            subset = data.set_index(x_col).reindex(x_values)
            y = subset[mean_column].fillna(0.0)
            err = subset[std_column].fillna(0.0)
            colors = None
            if palette is not None:
                colors = [palette.get(str(value)) for value in x_values]
            ax.bar(
                x,
                y,
                yerr=err,
                capsize=2,
                color=colors,
                width=0.72,
                error_kw=error_style,
            )
        else:
            hue_values = hue_order or list(data[hue_col].dropna().astype(str).unique())
            width = min(0.8 / max(len(hue_values), 1), 0.35)
            for index, hue_value in enumerate(hue_values):
                subset = (
                    data[data[hue_col].astype(str).eq(str(hue_value))]
                    .set_index(x_col)
                    .reindex(x_values)
                )
                y = subset[mean_column].fillna(0.0)
                err = subset[std_column].fillna(0.0)
                offset = (index - (len(hue_values) - 1) / 2) * width
                color = palette.get(str(hue_value)) if palette is not None else None
                ax.bar(
                    x + offset,
                    y,
                    width,
                    yerr=err,
                    capsize=2,
                    label=str(hue_value),
                    color=color,
                    error_kw=error_style,
                )
            _place_legend_above(ax)

        ax.set_xticks(x)
        ax.set_xticklabels(x_values)
        ax.set_xlabel("")
        ax.set_ylabel(_axis_label(ylabel, percent=percent))
        if percent:
            ax.set_ylim(0, 1)
            ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        add_minor_y_grid(ax, percent=percent)
        _format_categorical_xticklabels(ax)
        fig.tight_layout()
        fig.savefig(path, format="svg")
        plt.close(fig)
        return path

    def _save_run_mean_scatter(
        data: pd.DataFrame,
        path,
        x_col: str,
        xlabel: str,
    ):
        if data.empty or x_col not in data or "ultimate_success_rate" not in data:
            return path

        accent_colors = {
            "A": "#7e7e7e",
            "B": "#77b5b6",
            "C": "#9671bd",
        }
        secondary_colors = {
            "A": "#4e4e4e",
            "B": "#378d94",
            "C": "#6a408d",
        }
        means = (
            data.groupby("system", dropna=False)
            .agg(
                **{
                    x_col: (x_col, "mean"),
                    "ultimate_success_rate": ("ultimate_success_rate", "mean"),
                }
            )
            .reset_index()
        )

        fig, ax = plt.subplots(figsize=typst_figsize())
        for system in SYSTEM_ORDER:
            subset = data[data["system"].eq(system)]
            if subset.empty:
                continue
            ax.scatter(
                subset[x_col],
                subset["ultimate_success_rate"],
                s=34,
                alpha=0.42,
                color=accent_colors.get(system),
                linewidths=0,
            )
            mean = means[means["system"].eq(system)]
            if mean.empty:
                continue
            ax.scatter(
                mean[x_col],
                mean["ultimate_success_rate"],
                s=78,
                color=secondary_colors.get(system),
                edgecolors="white",
                linewidths=0.7,
                label=system,
                zorder=3,
            )

        ax.set_xlabel(_axis_label(xlabel))
        ax.set_ylabel(_axis_label("Ultimate Success Rate", percent=True))
        ax.set_ylim(-0.03, 1.03)
        ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        add_minor_y_grid(ax, percent=True)
        _place_legend_above(ax)
        fig.tight_layout()
        fig.savefig(path, format="svg")
        plt.close(fig)
        return path

    return _metric_plot_frame, _save_grouped_bars, _save_run_mean_scatter


@app.cell
def _(
    combined_artifact_paths,
    FIGURES_DIR,
    SYSTEM_ORDER,
    _metric_plot_frame,
    _save_grouped_bars,
    _save_run_mean_scatter,
    critic_per_run,
    efficiency_per_run,
    outcome_counts_per_run,
    pd,
    results,
):
    per_run_system = (
        results.groupby(["run_id", "system"], dropna=False)
        .agg(
            first_pass_success_rate=("first_pass_success", "mean"),
            ultimate_success_rate=("ultimate_success", "mean"),
            correct_rejection_rate=("correct_rejection", "mean"),
            false_answer_rate=("false_answer", "mean"),
        )
        .reset_index()
    )

    success_plot = _metric_plot_frame(
        per_run_system,
        ["run_id", "system"],
        ["first_pass_success_rate", "ultimate_success_rate"],
    )
    success_plot["metric"] = success_plot["metric"].map(
        {
            "first_pass_success_rate": "First-pass",
            "ultimate_success_rate": "Ultimate",
        }
    )

    rejection_plot = _metric_plot_frame(
        per_run_system,
        ["run_id", "system"],
        ["correct_rejection_rate", "false_answer_rate"],
    )
    rejection_plot["metric"] = rejection_plot["metric"].map(
        {
            "correct_rejection_rate": "Correct rejection",
            "false_answer_rate": "False answer",
        }
    )

    per_run_difficulty = (
        results.groupby(["run_id", "system", "difficulty"], dropna=False)
        .agg(ultimate_success_rate=("ultimate_success", "mean"))
        .reset_index()
    )
    difficulty_plot = (
        per_run_difficulty.groupby(["difficulty", "system"], dropna=False)
        .agg(
            ultimate_success_rate_mean=("ultimate_success_rate", "mean"),
            ultimate_success_rate_std=("ultimate_success_rate", "std"),
        )
        .reset_index()
        .fillna(0.0)
    )

    critic_review_plot = _metric_plot_frame(
        critic_per_run,
        ["run_id"],
        ["critic_acceptance_rate", "critic_intervention_rate"],
    )
    critic_review_plot["metric"] = critic_review_plot["metric"].map(
        {
            "critic_acceptance_rate": "Acceptance",
            "critic_intervention_rate": "Intervention",
        }
    )
    critic_review_plot["group"] = "System C"

    critic_effect_plot = _metric_plot_frame(
        critic_per_run,
        ["run_id"],
        ["critic_recovery_rate", "critic_regression_rate"],
    )
    critic_effect_plot["metric"] = critic_effect_plot["metric"].map(
        {
            "critic_recovery_rate": "Recovery",
            "critic_regression_rate": "Regression",
        }
    )
    critic_effect_plot["group"] = "System C"

    efficiency_plot = _metric_plot_frame(
        efficiency_per_run,
        ["run_id", "system"],
        ["avg_sql_stage_total_tokens", "avg_sql_stage_runtime_seconds"],
    )
    efficiency_plot["metric"] = efficiency_plot["metric"].map(
        {
            "avg_sql_stage_total_tokens": "Tokens",
            "avg_sql_stage_runtime_seconds": "Runtime (s)",
        }
    )

    figure_paths = dict(combined_artifact_paths["figures"])
    figure_paths["F1"] = _save_grouped_bars(
        success_plot,
        FIGURES_DIR / "01_first_pass_vs_ultimate_success_mean_std.svg",
        "system",
        "value",
        "metric",
        "Success Rate (%)",
        "First-pass vs. ultimate success by system",
        x_order=SYSTEM_ORDER,
        hue_order=["First-pass", "Ultimate"],
        percent=True,
    )
    figure_paths["F2"] = _save_grouped_bars(
        difficulty_plot,
        FIGURES_DIR / "02_ultimate_success_by_difficulty_mean_std.svg",
        "difficulty",
        "ultimate_success_rate",
        "system",
        "Ultimate Success Rate (%)",
        "Ultimate success by difficulty",
        x_order=["easy", "medium", "hard"],
        hue_order=SYSTEM_ORDER,
        percent=True,
    )
    figure_paths["F4"] = _save_grouped_bars(
        rejection_plot,
        FIGURES_DIR / "04_correct_rejection_false_answer_mean_std.svg",
        "system",
        "value",
        "metric",
        "Rate (%)",
        "Correct rejection vs. false answer by system",
        x_order=SYSTEM_ORDER,
        hue_order=["Correct rejection", "False answer"],
        percent=True,
    )
    figure_paths["F9"] = _save_grouped_bars(
        critic_review_plot,
        FIGURES_DIR / "09_critic_acceptance_intervention_mean_std.svg",
        "metric",
        "value",
        None,
        "Rate (%)",
        "Critic acceptance and intervention",
        x_order=["Acceptance", "Intervention"],
        percent=True,
    )
    figure_paths["F11"] = _save_grouped_bars(
        critic_effect_plot,
        FIGURES_DIR / "11_critic_recovery_regression_mean_std.svg",
        "metric",
        "value",
        None,
        "Rate (%)",
        "Critic recovery and regression",
        x_order=["Recovery", "Regression"],
        percent=True,
    )

    token_data = efficiency_plot[efficiency_plot["metric"].eq("Tokens")].copy()
    runtime_data = efficiency_plot[efficiency_plot["metric"].eq("Runtime (s)")].copy()
    token_path = _save_grouped_bars(
        token_data,
        FIGURES_DIR / "16_sql_stage_tokens_by_system_mean_std.svg",
        "system",
        "value",
        None,
        "Average SQL-Stage Tokens",
        "SQL-stage token efficiency",
        x_order=SYSTEM_ORDER,
    )
    runtime_path = _save_grouped_bars(
        runtime_data,
        FIGURES_DIR / "15_sql_stage_runtime_by_system_mean_std.svg",
        "system",
        "value",
        None,
        "Average SQL-Stage Runtime (s)",
        "SQL-stage runtime efficiency",
        x_order=SYSTEM_ORDER,
    )
    figure_paths["F16"] = token_path
    figure_paths["F15"] = runtime_path

    run_efficiency = (
        results.groupby(["run_id", "system"], dropna=False)
        .agg(
            ultimate_success_rate=("ultimate_success", "mean"),
            avg_sql_stage_total_tokens=("sql_stage_total_tokens", "mean"),
            avg_sql_stage_runtime_seconds=("sql_stage_runtime_seconds", "mean"),
        )
        .reset_index()
    )
    figure_paths["F21"] = _save_run_mean_scatter(
        run_efficiency,
        FIGURES_DIR / "21_success_vs_tokens.svg",
        "avg_sql_stage_total_tokens",
        "Average SQL-Stage Tokens",
    )
    figure_paths["F22"] = _save_run_mean_scatter(
        run_efficiency,
        FIGURES_DIR / "22_success_vs_runtime.svg",
        "avg_sql_stage_runtime_seconds",
        "Average SQL-Stage Runtime (s)",
    )

    outcome_distribution_path = FIGURES_DIR / "outcome_counts_mean_std.csv"
    outcome_counts_per_run.to_csv(outcome_distribution_path, index=False)

    return (
        critic_effect_plot,
        critic_review_plot,
        difficulty_plot,
        efficiency_plot,
        figure_paths,
        rejection_plot,
        success_plot,
    )


@app.cell
def _(
    TABLES_DIR,
    combined_table_summaries,
    figure_paths,
    mo,
    pd,
    relative,
    summary_by_system_display,
    summary_paths,
):
    summary_rows = [
        {"artifact": name, "path": relative(path)} for name, path in summary_paths.items()
    ]
    figure_rows = [
        {"artifact": name, "path": relative(path)} for name, path in figure_paths.items()
    ]
    table_rows = [
        {
            "artifact": artifact_id,
            "rows": len(frame),
            "path": relative(
                TABLES_DIR
                / next(
                    spec.filename
                    for spec in __import__(
                        "evaluation.benchmark.artifacts", fromlist=["TABLE_SPECS"]
                    ).TABLE_SPECS
                    if spec.artifact_id == artifact_id
                )
            ),
        }
        for artifact_id, frame in combined_table_summaries.items()
    ]

    mo.vstack(
        [
            mo.md("## Thesis Summary Table"),
            mo.ui.table(summary_by_system_display),
            mo.md("## Combined Summary CSVs"),
            mo.ui.table(pd.DataFrame(summary_rows)),
            mo.md("## Mean/Std Figures"),
            mo.ui.table(pd.DataFrame(figure_rows)),
            mo.md("## Combined Versions of Existing Table Artifacts"),
            mo.ui.table(pd.DataFrame(table_rows)),
        ]
    )
    return


@app.cell
def _(PROJECT_ROOT, figure_paths, mo):
    outputs = []
    for name, path in figure_paths.items():
        outputs.append(mo.md(f"### {name}\n\n`{path.relative_to(PROJECT_ROOT)}`"))
        outputs.append(mo.image(src=str(path)))
    mo.vstack(outputs)
    return


if __name__ == "__main__":
    app.run()
