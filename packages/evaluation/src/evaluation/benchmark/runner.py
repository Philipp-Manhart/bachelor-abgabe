from __future__ import annotations

import argparse
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from agent_orchestrator.config import get_database_path
from agent_orchestrator.llm import LiteLlmClient
from agent_orchestrator.mcp_client import FastMcpClient
from agent_orchestrator.nodes import OrchestratorDependencies
from agent_orchestrator.runner import (
    run_mcp_critic_with_dependencies,
    run_mcp_single_shot_with_dependencies,
)
from evaluation.benchmark.baseline import run_system_a
from evaluation.benchmark.evaluator import evaluate_run, flatten_result, normalize_runner_result
from evaluation.benchmark.io import load_questions
from evaluation.benchmark.models import EvaluationResult, QuestionSpec
from evaluation.benchmark.reporting import write_outputs


def run_benchmark(
    *,
    questions_path: str | Path,
    systems: list[str],
    output_dir: str | Path,
    max_iterations: int = 3,
    limit: int | None = None,
    limit_per_difficulty: int | None = None,
    seed: int = 42,
    database_path: str | Path | None = None,
    skip_plots: bool = False,
    show_progress: bool = False,
    workers: int = 1,
) -> list[dict[str, Any]]:
    db_path = Path(database_path or get_database_path())
    questions = load_questions(questions_path)
    random.Random(seed).shuffle(questions)
    questions = _limit_questions(
        questions,
        limit=limit,
        limit_per_difficulty=limit_per_difficulty,
    )

    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    total_runs = len(questions) * len(systems)
    workers = max(1, workers)
    _progress(
        show_progress,
        (
            f"Benchmark started: {len(questions)} questions, {len(systems)} systems, "
            f"{total_runs} runs, workers={workers}."
        ),
    )
    completed = _run_tasks(
        questions=questions,
        systems=systems,
        max_iterations=max_iterations,
        database_path=db_path,
        workers=workers,
        show_progress=show_progress,
    )
    for _question_index, _system_index, flat, trace in completed:
        rows.append(flat)
        traces.append(trace)

    run_dir = Path(output_dir)
    raw_results_dir = run_dir / "results"
    _progress(show_progress, f"Writing benchmark outputs to {run_dir.resolve()}")
    write_outputs(raw_results_dir, rows, traces)
    if not skip_plots:
        from evaluation.plotting import write_plots

        _progress(show_progress, "Writing benchmark tables and figures.")
        write_plots(raw_results_dir, run_dir)
    _progress(show_progress, "Benchmark outputs complete.")
    return rows


def _run_tasks(
    *,
    questions: list[QuestionSpec],
    systems: list[str],
    max_iterations: int,
    database_path: Path,
    workers: int,
    show_progress: bool,
) -> list[tuple[int, int, dict[str, Any], dict[str, Any]]]:
    completed: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    total_runs = len(questions) * len(systems)
    completed_runs = 0
    for question_index, question in enumerate(questions, start=1):
        _progress(
            show_progress,
            (
                f"[question {question_index}/{len(questions)}] "
                f"{question.question_id} ({question.difficulty}): {question.question}"
            ),
        )

        if workers > 1 and len(systems) > 1:
            question_completed = _run_question_systems_parallel(
                question_index=question_index,
                question=question,
                systems=systems,
                max_iterations=max_iterations,
                database_path=database_path,
                workers=min(workers, len(systems)),
                show_progress=show_progress,
                completed_runs=completed_runs,
                total_runs=total_runs,
            )
        else:
            question_completed = _run_question_systems_sequential(
                question_index=question_index,
                question=question,
                systems=systems,
                max_iterations=max_iterations,
                database_path=database_path,
                show_progress=show_progress,
                completed_runs=completed_runs,
                total_runs=total_runs,
            )

        completed.extend(question_completed)
        completed_runs += len(question_completed)
    return completed


def _run_question_systems_sequential(
    *,
    question_index: int,
    question: QuestionSpec,
    systems: list[str],
    max_iterations: int,
    database_path: Path,
    show_progress: bool,
    completed_runs: int,
    total_runs: int,
) -> list[tuple[int, int, dict[str, Any], dict[str, Any]]]:
    completed: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for system_index, system in enumerate(systems):
        run_started_at = time.perf_counter()
        _progress(
            show_progress,
            f"  -> system {system} started ({completed_runs + system_index + 1}/{total_runs})",
        )
        flat, trace = _run_and_evaluate(
            system,
            question,
            max_iterations=max_iterations,
            database_path=database_path,
        )
        completed.append((question_index, system_index, flat, trace))
        _progress(
            show_progress,
            (
                f"  <- system {system} finished: outcome={flat['outcome']}, "
                f"status={flat['status']}, elapsed={time.perf_counter() - run_started_at:.2f}s"
            ),
        )
    return completed


def _run_question_systems_parallel(
    *,
    question_index: int,
    question: QuestionSpec,
    systems: list[str],
    max_iterations: int,
    database_path: Path,
    workers: int,
    show_progress: bool,
    completed_runs: int,
    total_runs: int,
) -> list[tuple[int, int, dict[str, Any], dict[str, Any]]]:
    completed: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        started_at: dict[int, float] = {}
        futures = {
            executor.submit(
                _run_and_evaluate,
                system,
                question,
                max_iterations=max_iterations,
                database_path=database_path,
            ): (system_index, system)
            for system_index, system in enumerate(systems)
        }
        for system_index, system in enumerate(systems):
            started_at[system_index] = time.perf_counter()
            _progress(
                show_progress,
                f"  -> system {system} started ({completed_runs + system_index + 1}/{total_runs})",
            )
        for future in as_completed(futures):
            system_index, system = futures[future]
            run_finished_at = time.perf_counter()
            try:
                flat, trace = future.result()
            except Exception as exc:
                result = _runtime_error_result(
                    system,
                    question,
                    exc,
                    max_iterations=max_iterations,
                )
                evaluation = EvaluationResult(
                    first_pass_success=False,
                    ultimate_success=False,
                    correct_rejection=False,
                    false_answer=False,
                    outcome="RUNTIME_ERROR",
                    error_type="runtime_error",
                )
                flat = flatten_result(result, evaluation)
                trace = _trace_row(flat, result)
            completed.append((question_index, system_index, flat, trace))
            _progress(
                show_progress,
                (
                    f"  <- system {system} finished: "
                    f"outcome={flat['outcome']}, status={flat['status']}, "
                    f"elapsed={run_finished_at - started_at[system_index]:.2f}s"
                ),
            )
    return sorted(completed, key=lambda item: (item[0], item[1]))


def main() -> None:
    args = _parse_args()
    systems = [system.strip() for system in args.systems.split(",") if system.strip()]
    run_benchmark(
        questions_path=args.questions,
        systems=systems,
        output_dir=args.output,
        max_iterations=args.max_iterations,
        limit=args.limit,
        limit_per_difficulty=args.limit_per_difficulty,
        seed=args.seed,
        skip_plots=args.skip_plots,
        show_progress=True,
        workers=args.workers,
    )


def _run_one(
    system: str,
    question: QuestionSpec,
    *,
    max_iterations: int,
    database_path: Path,
) -> dict[str, Any]:
    dependencies: OrchestratorDependencies | None = None
    try:
        if system == "A":
            raw = run_system_a(question, database_path=database_path)
            return normalize_runner_result(raw, question, system="A")
        dependencies = _mcp_dependencies()
        if system == "B":
            raw = run_mcp_single_shot_with_dependencies(
                question.question,
                dependencies,
                max_iterations=0,
            )
            return normalize_runner_result(raw, question, system="B")
        if system == "C":
            raw = run_mcp_critic_with_dependencies(
                question.question,
                dependencies,
                max_iterations=max_iterations,
            )
            return normalize_runner_result(raw, question, system="C")
        msg = f"Unknown system: {system}"
        raise ValueError(msg)
    except Exception as exc:
        return _runtime_error_result(system, question, exc, max_iterations=max_iterations)
    finally:
        if dependencies is not None:
            dependencies.mcp.close()


def _run_and_evaluate(
    system: str,
    question: QuestionSpec,
    *,
    max_iterations: int,
    database_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _run_one(
        system,
        question,
        max_iterations=max_iterations,
        database_path=database_path,
    )
    try:
        evaluation = evaluate_run(result, question, database_path=database_path)
    except Exception as exc:
        result = _runtime_error_result(
            system,
            question,
            exc,
            max_iterations=max_iterations,
        )
        evaluation = EvaluationResult(
            first_pass_success=False,
            ultimate_success=False,
            correct_rejection=False,
            false_answer=False,
            outcome="RUNTIME_ERROR",
            error_type="runtime_error",
        )
    flat = flatten_result(result, evaluation)
    return flat, _trace_row(flat, result)


def _trace_row(flat: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        **flat,
        "trace": result.get("trace"),
        "error_history": result.get("error_history"),
        "final_answer": result.get("final_answer"),
        "execution_result": result.get("execution_result"),
        "analysis_plan": result.get("analysis_plan"),
        "metadata_context_summary": _metadata_context_summary(result.get("metadata_context")),
        "profiling_observations": result.get("profiling_observations"),
        "critic_decision": result.get("critic_decision"),
    }


def _mcp_dependencies() -> OrchestratorDependencies:
    return OrchestratorDependencies(
        llm=LiteLlmClient(),
        mcp=FastMcpClient(),
    )


def _limit_questions(
    questions: list[QuestionSpec],
    *,
    limit: int | None,
    limit_per_difficulty: int | None,
) -> list[QuestionSpec]:
    selected = questions
    if limit_per_difficulty is not None:
        counts: dict[str, int] = {}
        selected = []
        for question in questions:
            count = counts.get(question.difficulty, 0)
            if count >= limit_per_difficulty:
                continue
            selected.append(question)
            counts[question.difficulty] = count + 1
    return selected[:limit] if limit is not None else selected


def _progress(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


def _runtime_error_result(
    system: str, question: QuestionSpec, exc: Exception, *, max_iterations: int
) -> dict[str, Any]:
    return {
        "system": system,
        "status": "ERROR",
        "question_id": question.question_id,
        "difficulty": question.difficulty,
        "answerable": question.answerable,
        "question": question.question,
        "first_generated_sql": None,
        "final_generated_sql": None,
        "final_answer": None,
        "execution_result": None,
        "last_error": f"RUNTIME_ERROR: {exc}",
        "error_history": [f"RUNTIME_ERROR: {exc}"],
        "iterations": 0,
        "max_iterations": max_iterations if system == "C" else 0,
        "trace": {
            "llm_calls": 0,
            "mcp_calls": 0,
            "sql_executions": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "runtime_seconds": 0.0,
            "retrieved_tables": [],
            "profiling_calls": 0,
        },
    }


def _metadata_context_summary(metadata_context: Any) -> dict[str, Any]:
    if not isinstance(metadata_context, dict):
        return {}
    table_dictionaries = metadata_context.get("table_dictionaries")
    glossary_terms = metadata_context.get("business_glossary_terms")
    return {
        "schema_overview_count": len(metadata_context.get("schema_overview") or []),
        "table_dictionaries": sorted(table_dictionaries.keys())
        if isinstance(table_dictionaries, dict)
        else [],
        "relationships_count": len(metadata_context.get("relationships") or []),
        "business_glossary_terms": sorted(glossary_terms.keys())
        if isinstance(glossary_terms, dict)
        else [],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Text-to-SQL benchmark.")
    parser.add_argument("--questions", required=True)
    parser.add_argument("--systems", default="A,B,C")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--limit-per-difficulty", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    started_at = time.perf_counter()
    main()
    print(f"Benchmark finished in {time.perf_counter() - started_at:.2f}s")
