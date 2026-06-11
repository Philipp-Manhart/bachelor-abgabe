from __future__ import annotations

import argparse
import time
from pathlib import Path

from agent_orchestrator.config import PROJECT_ROOT
from evaluation.benchmark.runner import run_benchmark

DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "database" / "test_queries.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "benchmark"


def run_evaluation(
    *,
    questions_path: str | Path = DEFAULT_QUESTIONS_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    systems: str = "A,B,C",
    max_iterations: int = 3,
    limit: int | None = None,
    limit_per_difficulty: int | None = None,
    seed: int = 42,
    skip_plots: bool = False,
    show_progress: bool = False,
    workers: int = 3,
) -> list[dict[str, object]]:
    selected_systems = [system.strip() for system in systems.split(",") if system.strip()]
    return run_benchmark(
        questions_path=questions_path,
        systems=selected_systems,
        output_dir=output_dir,
        max_iterations=max_iterations,
        limit=limit,
        limit_per_difficulty=limit_per_difficulty,
        seed=seed,
        skip_plots=skip_plots,
        show_progress=show_progress,
        workers=workers,
    )


def main() -> None:
    args = _parse_args()
    started_at = time.perf_counter()
    rows = run_evaluation(
        questions_path=args.questions,
        output_dir=args.output,
        systems=args.systems,
        max_iterations=args.max_iterations,
        limit=args.limit,
        limit_per_difficulty=args.limit_per_difficulty,
        seed=args.seed,
        skip_plots=args.skip_plots,
        show_progress=True,
        workers=args.workers,
    )
    print(
        f"Evaluation finished: {len(rows)} system-question runs written to "
        f"{Path(args.output).resolve()} in {time.perf_counter() - started_at:.2f}s"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Text-to-SQL A/B/C evaluation.")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS_PATH))
    parser.add_argument("--systems", default="A,B,C")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--limit-per-difficulty", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    main()
