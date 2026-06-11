from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from evaluation.benchmark.artifacts import (
    ACTIVE_FIGURE_IDS,
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    FIGURE_SPECS,
    generate_benchmark_artifacts,
    load_results,
    write_figure_artifacts,
)


def write_plots(
    input_dir: str | Path = DEFAULT_INPUT_DIR, output_dir: str | Path | None = None
) -> dict[str, Path]:
    return generate_benchmark_artifacts(input_dir, output_dir)["figures"]


def write_paper_figures(results: pd.DataFrame, output_dir: str | Path) -> dict[str, Path]:
    paths = write_figure_artifacts(results, {}, Path(output_dir))
    aliases = {
        "success_rates": "F1",
        "ultimate_success_by_difficulty": "F2",
        "unanswerable_rejection": "F4",
        "critic_metrics": "F9",
        "critic_recovery": "F9",
        "critic_decisions": "F10",
        "calls": "F17",
        "success_vs_tokens": "F21",
        "false_rejections": "F27",
    }
    return {alias: paths[key] for alias, key in aliases.items() if key in paths} | paths


def paper_figure_specs() -> list[str]:
    return [spec.artifact_id for spec in FIGURE_SPECS if spec.artifact_id in ACTIVE_FIGURE_IDS]


def main() -> None:
    args = _parse_args()
    paths = write_plots(args.input, args.output)
    print(f"Plots written to {Path(args.output or DEFAULT_OUTPUT_DIR).resolve()}")
    for path in paths.values():
        print(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create benchmark result plots and tables.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


__all__ = [
    "DEFAULT_INPUT_DIR",
    "DEFAULT_OUTPUT_DIR",
    "load_results",
    "paper_figure_specs",
    "write_paper_figures",
    "write_plots",
]


if __name__ == "__main__":
    main()
