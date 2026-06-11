from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.benchmark.io import write_jsonl
from evaluation.benchmark.metrics import aggregate_metrics


def write_outputs(
    output_dir: str | Path, rows: list[dict[str, Any]], traces: list[dict[str, Any]]
) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(rows).to_csv(directory / "benchmark_results.csv", index=False)
    write_jsonl(directory / "benchmark_traces.jsonl", traces)

    summaries = aggregate_metrics(rows)
    summaries["by_system"].to_csv(directory / "benchmark_summary_by_system.csv", index=False)
    summaries["by_difficulty"].to_csv(
        directory / "benchmark_summary_by_difficulty.csv", index=False
    )
    summaries["by_system_difficulty"].to_csv(
        directory / "benchmark_summary_by_system_difficulty.csv",
        index=False,
    )
    summaries["answerability"].to_csv(
        directory / "benchmark_summary_answerability.csv", index=False
    )
    summaries["by_error_type"].to_csv(
        directory / "benchmark_summary_by_error_type.csv", index=False
    )

    metadata = {
        "num_runs": len(rows),
        "num_questions": pd.DataFrame(rows)["question_id"].nunique() if rows else 0,
        "systems": sorted(pd.DataFrame(rows)["system"].dropna().unique().tolist()) if rows else [],
        "max_iterations": int(pd.DataFrame(rows)["max_iterations"].max()) if rows else None,
    }
    with (directory / "benchmark_metadata.json").open("w", encoding="utf-8") as file:
        import json

        json.dump(metadata, file, indent=2)
