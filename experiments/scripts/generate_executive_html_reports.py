from __future__ import annotations

import argparse
import csv
import html
import json
import re
from pathlib import Path
from typing import Any

from analyze_field_coverage import mapped_ancestor, mapping_fields
from experiment_utils import CONFIG_DIR, RESULTS_DIR, load_yaml, utc_now_iso


ANALYSIS_DIR = RESULTS_DIR / "_analysis"
MAPPING_PATH = CONFIG_DIR / "coverage_mapping.yaml"
ARCHITECTURE_PATH = CONFIG_DIR / "architecture_mapping.md"


PLOTS = [
    {
        "title": "Approach vs Provenance Data Category",
        "file": "approach_vs_provenance_data_category.svg",
        "description": "Compares provenance data category coverage across instrumentation approaches.",
    },
    {
        "title": "Approach vs Analytical Capabilities",
        "file": "approach_vs_analytical_capabilities.svg",
        "description": "Shows analytical capability coverage enabled by each approach.",
    },
    {
        "title": "Approach vs Personas",
        "file": "approach_vs_personas.svg",
        "description": "Summarizes persona-level question coverage by approach.",
    },
    {
        "title": "Approach vs Question Coverage",
        "file": "approach_vs_question_coverage.svg",
        "description": "Shows question-level coverage for every approach.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate executive HTML reports for Perceptron GridSearch analysis.")
    parser.add_argument("--use-case", default="perceptron_gridsearch")
    parser.add_argument("--analysis-dir", default=str(ANALYSIS_DIR))
    parser.add_argument("--mapping", default=str(MAPPING_PATH))
    parser.add_argument("--architecture", default=str(ARCHITECTURE_PATH), help="Markdown table with architecture trade-offs.")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def kb(bytes_value: Any) -> str:
    return f"{float(bytes_value or 0) / 1024:.1f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def load_svg(path: Path) -> str:
    text = path.read_text()
    text = re.sub(r"<\\?xml[^>]*>", "", text).strip()
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text).strip()
    return text


def table(headers: list[str], rows: list[list[Any]], compact: bool = False) -> str:
    classes = "data-table compact" if compact else "data-table"
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def markdown_table_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    if not path.exists():
        return [], []
    lines = path.read_text().splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows: list[list[str]] = []
        for row_line in lines[idx + 1 :]:
            if not row_line.startswith("|"):
                if rows:
                    break
                continue
            cells = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            if len(cells) == len(headers):
                rows.append(cells)
        return headers, rows
    return [], []


def architecture_section(architecture_path: Path) -> str:
    headers, rows = markdown_table_rows(architecture_path)
    if not headers or not rows:
        return ""
    return f"""
      <section class="table-card">
        <h3>Architecture Trade-offs</h3>
        <p class="description">Qualitative comparison of where each approach observes the system and the cost of deploying it.</p>
        {table(headers, rows, compact=True)}
      </section>
    """


def plot_card(plot: dict[str, str], figures_dir: Path) -> str:
    figure_path = figures_dir / plot["file"]
    if not figure_path.exists():
        return ""
    svg = load_svg(figure_path)
    return f"""
      <section class="plot-card">
        <div class="plot-copy">
          <p class="eyebrow">Visualization</p>
          <h2>{esc(plot["title"])}</h2>
          <p class="description">{esc(plot["description"])}</p>
          <p class="takeaway"><span>Main takeaway:</span> [add takeaway]</p>
        </div>
        <div class="plot-frame">{svg}</div>
      </section>
    """


def css() -> str:
    return """
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --panel: #ffffff;
      --soft: #f5f7fb;
      --accent: #2058c9;
      --accent-2: #0f766e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #eef2f7;
      color: var(--ink);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    .page {
      max-width: 1320px;
      margin: 0 auto;
      padding: 42px 32px 64px;
    }
    header {
      padding: 28px 0 30px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 30px;
    }
    .kicker {
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 750;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    h1 {
      margin: 0;
      font-size: 38px;
      line-height: 1.08;
      letter-spacing: 0;
    }
    .subtitle {
      max-width: 900px;
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 17px;
    }
    .section-title {
      margin: 34px 0 14px;
      font-size: 24px;
    }
    .note {
      margin: 12px 0 20px;
      padding: 14px 16px;
      background: #fff8e6;
      border: 1px solid #f2d27b;
      border-radius: 8px;
      color: #6d5200;
    }
    .plot-grid {
      display: grid;
      gap: 22px;
    }
    .plot-card {
      display: grid;
      grid-template-columns: minmax(260px, 330px) minmax(0, 1fr);
      gap: 18px;
      align-items: stretch;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 12px 30px rgba(23, 32, 51, .06);
    }
    .plot-copy {
      padding: 10px 8px 10px 4px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .eyebrow {
      margin: 0 0 8px;
      color: var(--accent-2);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .07em;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 22px;
      line-height: 1.2;
    }
    .description {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 14px;
    }
    .takeaway {
      margin: 0;
      padding: 13px 14px;
      background: var(--soft);
      border-left: 4px solid var(--accent);
      border-radius: 6px;
      color: #2f3a4f;
      font-size: 14px;
    }
    .takeaway span { font-weight: 800; color: var(--ink); }
    .plot-frame {
      overflow: auto;
      padding: 8px;
      background: #fbfcff;
      border: 1px solid #e7edf5;
      border-radius: 10px;
    }
    .plot-frame svg {
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }
    .table-card {
      margin: 18px 0 28px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 12px 30px rgba(23, 32, 51, .05);
      overflow-x: auto;
    }
    .table-card h3 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 760px;
    }
    .data-table th {
      text-align: left;
      color: #344054;
      background: #f3f6fb;
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      white-space: nowrap;
    }
    .data-table td {
      border-bottom: 1px solid #ecf0f6;
      padding: 9px 12px;
      vertical-align: top;
    }
    .data-table tr:last-child td { border-bottom: 0; }
    .compact { min-width: 640px; }
    footer {
      margin-top: 34px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 860px) {
      .page { padding: 28px 16px 48px; }
      h1 { font-size: 30px; }
      .plot-card { grid-template-columns: 1fr; }
    }
    """


def html_doc(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>{css()}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="kicker">Perceptron GridSearch</p>
      <h1>{esc(title)}</h1>
      <p class="subtitle">{esc(subtitle)}</p>
    </header>
    {body}
    <footer>Generated at {esc(utc_now_iso())}. Source: Flowcept Academy Integration Playground.</footer>
  </main>
</body>
</html>
"""


def make_plots_html(figures_dir: Path, architecture_path: Path) -> str:
    body = architecture_section(architecture_path)
    body += '<div class="plot-grid">' + "\n".join(plot_card(plot, figures_dir) for plot in PLOTS) + "</div>"
    return html_doc(
        "Provenance Coverage Plots",
        "A concise visual comparison of how each instrumentation approach captures provenance value.",
        body,
    )


def coverage_cell(captured: set[str], possible: set[str]) -> str:
    if not possible:
        return "n/a"
    return f"{pct((len(captured) / len(possible)) * 100)} ({len(captured)}/{len(possible)})"


def dimension_universe(fields: dict[str, Any], key: str) -> dict[str, set[str]]:
    universe: dict[str, set[str]] = {}
    for field, entry in fields.items():
        for value in entry.get(key) or []:
            universe.setdefault(value, set()).add(field)
    return dict(sorted(universe.items()))


def schema_universe(fields: dict[str, Any]) -> dict[str, set[str]]:
    universe = {"workflow": set(), "task": set(), "agent": set(), "object": set()}
    for field in fields:
        prefix = field.split(".", 1)[0]
        if prefix in universe:
            universe[prefix].add(field)
    return universe


def title_label(value: str) -> str:
    return value.replace("-", " ").title()


def coverage_summary_rows(
    mapping: dict[str, Any],
    observed_payload: dict[str, Any],
) -> tuple[
    list[list[Any]],
    list[list[Any]],
    list[str],
    list[list[Any]],
    list[str],
    list[list[Any]],
]:
    all_mapped = mapping_fields(mapping)
    official_fields = set(mapping.get("fields") or {})
    schema_dimensions = schema_universe(mapping.get("fields") or {})
    capability_dimensions = dimension_universe(all_mapped, "analytical_capabilities")
    provenance_dimensions = dimension_universe(all_mapped, "provenance_data_categories")
    capability_headers = [title_label(value) for value in capability_dimensions]
    provenance_headers = [title_label(value) for value in provenance_dimensions]

    semantic_rows: list[list[Any]] = []
    schema_rows: list[list[Any]] = []
    capability_rows: list[list[Any]] = []
    provenance_rows: list[list[Any]] = []

    for _, approach in sorted(observed_payload["approaches"].items(), key=lambda item: item[1]["approach_label"]):
        label = approach["approach_label"]
        observed = set(approach["observed_fields"])
        mapped_observed = {ancestor for field in observed if (ancestor := mapped_ancestor(field, all_mapped))}

        semantic_rows.append([label, approach["observed_field_count"]])
        schema_rows.append(
            [
                label,
                *[
                    coverage_cell(mapped_observed & official_fields & possible, possible)
                    for _, possible in schema_dimensions.items()
                ],
            ]
        )
        capability_rows.append(
            [
                label,
                *[
                    coverage_cell(mapped_observed & possible, possible)
                    for _, possible in capability_dimensions.items()
                ],
            ]
        )
        provenance_rows.append(
            [
                label,
                *[
                    coverage_cell(mapped_observed & possible, possible)
                    for _, possible in provenance_dimensions.items()
                ],
            ]
        )

    return semantic_rows, schema_rows, capability_headers, capability_rows, provenance_headers, provenance_rows


def make_full_html(use_case: str, analysis_dir: Path, figures_dir: Path, mapping_path: Path, architecture_path: Path) -> str:
    volume_rows = read_csv(RESULTS_DIR / "perceptron_mongodb_data_volume_summary.csv")
    overhead_rows = read_csv(analysis_dir / f"analysis_1_overhead_{use_case}.csv")
    observed_payload = json.loads((analysis_dir / f"field_coverage_{use_case}_observed_fields.json").read_text())
    mapping = load_yaml(mapping_path)
    semantic_rows, schema_rows, capability_headers, capability_rows, provenance_headers, provenance_rows = coverage_summary_rows(
        mapping,
        observed_payload,
    )

    amount_rows = [
        [
            row["approach_label"],
            row["runs"],
            kb(row["total_flowcept_bytes_total"]),
            kb(row["total_flowcept_bytes_mean_per_run"]),
            row["total_flowcept_documents"],
        ]
        for row in volume_rows
    ]
    overhead_table_rows = [
        [
            row["approach_label"],
            row["selected_run_count"],
            f"{float(row['mean_runtime_seconds']):.2f}",
            f"{float(row['runtime_difference_from_baseline_percent']):.1f}%",
            f"{float(row['mean_memory_peak_rss_mib']):.1f}",
            f"{float(row['mean_new_task_count']):.1f}",
        ]
        for row in overhead_rows
    ]

    body = '<div class="plot-grid">' + "\n".join(plot_card(plot, figures_dir) for plot in PLOTS) + "</div>"
    body += architecture_section(architecture_path)
    body += """
      <h2 class="section-title">Supporting Tables</h2>
      <section class="table-card">
        <h3>Amount of Data</h3>
    """
    body += table(["Approach", "Runs", "Total Data (KB)", "Mean/Run (KB)", "Total Docs"], amount_rows, compact=True)
    body += """
      </section>
      <section class="table-card">
        <h3>Execution Overhead</h3>
        <p class="note">This use case is not representative for definitive overhead analysis; measurements are included for transparency.</p>
    """
    body += table(["Approach", "Runs", "Mean Runtime (s)", "Runtime vs Baseline", "Peak RSS (MiB)", "Flowcept Tasks"], overhead_table_rows, compact=True)
    body += """
      </section>
      <section class="table-card">
        <h3>Coverage Summary</h3>
    """
    body += "<h3>Semanticless Field Count</h3>"
    body += table(["Approach", "Unique Fields Captured"], semantic_rows, compact=True)
    body += "<h3>Flowcept Schema Coverage</h3>"
    body += table(["Approach", "Workflow", "Task", "Agent", "Object"], schema_rows, compact=True)
    body += "<h3>Analytical Capability Coverage</h3>"
    body += table(["Approach", *capability_headers], capability_rows, compact=True)
    body += "<h3>Provenance Data Type Coverage</h3>"
    body += table(["Approach", *provenance_headers], provenance_rows, compact=True)
    body += "</section>"

    return html_doc(
        "Provenance Capture Summary",
        "Visual findings plus compact evidence tables for data volume, overhead, and coverage.",
        body,
    )


def main() -> None:
    args = parse_args()
    analysis_dir = Path(args.analysis_dir)
    figures_dir = analysis_dir / f"field_coverage_figures_{args.use_case}"
    mapping_path = Path(args.mapping)
    architecture_path = Path(args.architecture)
    plots_out = analysis_dir / f"{args.use_case}_executive_plots.html"
    full_out = analysis_dir / f"{args.use_case}_executive_summary.html"

    plots_out.write_text(make_plots_html(figures_dir, architecture_path))
    full_out.write_text(make_full_html(args.use_case, analysis_dir, figures_dir, mapping_path, architecture_path))
    print(f"Wrote {plots_out}")
    print(f"Wrote {full_out}")


if __name__ == "__main__":
    main()
