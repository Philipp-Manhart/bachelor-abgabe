import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
        # Benchmark Figures

        Dieses Notebook nutzt denselben Reporting-Generator wie die CLI. Nach einem
        Benchmark-Lauf reichen die Dateien in `results/benchmark...` aus, um alle
        Tabellen und Grafiken erneut zu erzeugen und hier z.B. Farben oder Stil zu
        ändern.
        """
    )
    return (mo,)


@app.cell
def _():
    from pathlib import Path

    import pandas as pd

    from agent_orchestrator.config import PROJECT_ROOT
    from evaluation.benchmark.artifacts import (
        FIGURE_SPECS,
        TABLE_SPECS,
        build_tables,
        generate_benchmark_artifacts,
        load_metadata,
        load_results,
        load_traces,
    )

    INPUT_DIR = PROJECT_ROOT / "results" / "benchmark_full_1"
    OUTPUT_DIR = PROJECT_ROOT / "results" / "plots"

    artifact_paths = generate_benchmark_artifacts(INPUT_DIR, OUTPUT_DIR)
    results = load_results(INPUT_DIR)
    traces = load_traces(INPUT_DIR)
    metadata = load_metadata(INPUT_DIR)
    tables = build_tables(results, traces, metadata)

    def relative(path: Path) -> str:
        return str(path.relative_to(PROJECT_ROOT))

    return (
        FIGURE_SPECS,
        OUTPUT_DIR,
        PROJECT_ROOT,
        TABLE_SPECS,
        artifact_paths,
        pd,
        relative,
        results,
        tables,
    )


@app.cell
def _(mo, results):
    mo.md(f"Geladene Benchmark-Zeilen: **{len(results)}**")
    return


@app.cell
def _(TABLE_SPECS, artifact_paths, mo, pd, relative):
    rows = [
        {
            "ID": spec.artifact_id,
            "Table": spec.title,
            "File": relative(artifact_paths["tables"][spec.artifact_id]),
            "Main use": spec.main_use,
        }
        for spec in TABLE_SPECS
    ]
    mo.md("## Tables")
    mo.ui.table(pd.DataFrame(rows))
    return


@app.cell
def _(TABLE_SPECS, mo, tables):
    outputs = []
    for spec in TABLE_SPECS:
        outputs.append(mo.md(f"### {spec.artifact_id}. {spec.title}"))
        outputs.append(mo.ui.table(tables[spec.artifact_id]))
    mo.vstack(outputs)
    return


@app.cell
def _(FIGURE_SPECS, artifact_paths, mo, pd, relative):
    rows = [
        {
            "ID": spec.artifact_id,
            "Figure": spec.title,
            "File": relative(path),
            "Main use": spec.main_use,
        }
        for spec in FIGURE_SPECS
        if (path := artifact_paths["figures"].get(spec.artifact_id)) is not None
    ]
    mo.md("## Figures")
    mo.ui.table(pd.DataFrame(rows))
    return


@app.cell
def _(FIGURE_SPECS, PROJECT_ROOT, artifact_paths, mo, relative):
    outputs = []
    for spec in FIGURE_SPECS:
        path = artifact_paths["figures"].get(spec.artifact_id)
        if path is None:
            outputs.append(
                mo.md(
                    f"### {spec.artifact_id}. {spec.title}\n\n"
                    "Nicht erzeugt: keine verwertbaren Daten."
                )
            )
            continue
        outputs.append(mo.md(f"### {spec.artifact_id}. {spec.title}\n\n`{relative(path)}`"))
        outputs.append(mo.image(src=str(path)))
    mo.vstack(outputs)
    return


if __name__ == "__main__":
    app.run()
