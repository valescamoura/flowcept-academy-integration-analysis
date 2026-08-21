from __future__ import annotations

import argparse
import csv
import html
import subprocess
from pathlib import Path
from typing import Any

from experiment_utils import RESULTS_DIR


DEFAULT_INPUT = RESULTS_DIR / "mongodb_data_volume_summary.csv"
DEFAULT_OUTPUT_DIR = RESULTS_DIR / "_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a provenance data volume figure.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="CSV produced by summarize_mongodb_data_volume.py.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for SVG/PNG outputs.")
    parser.add_argument("--use-case", default="perceptron_gridsearch", help="Use case suffix for output filenames.")
    parser.add_argument("--png-scale", type=float, default=2.0, help="Scale factor used when converting SVG to PNG.")
    return parser.parse_args()


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def kb(value: Any) -> float:
    return float(value or 0) / 1024.0


def write_svg(path: Path, rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda row: kb(row["total_flowcept_bytes_mean_per_run"]), reverse=True)
    max_value = max((kb(row["total_flowcept_bytes_mean_per_run"]) for row in rows), default=0.0)
    max_value = max(max_value, 1.0)

    width = 1360
    left = 470
    right = 180
    top = 92
    row_h = 62
    chart_w = width - left - right
    height = top + len(rows) * row_h + 86
    axis_y = top + len(rows) * row_h + 14

    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #0f172a; }",
        ".title { font-size: 24px; font-weight: 700; }",
        ".subtitle { font-size: 15px; fill: #475569; }",
        ".axis { font-size: 20px; fill: #334155; }",
        ".small { font-size: 16px; fill: #475569; }",
        ".bar-label { font-size: 20px; font-weight: 800; fill: #0f172a; }",
        ".bar-docs { font-size: 17px; font-weight: 800; fill: #ffffff; }",
        "</style>",
        '<text class="title" x="24" y="34">Stored Provenance Volume by Approach</text>',
        '<text class="subtitle" x="24" y="58">Mean persisted provenance data per run; labels show mean Flowcept documents per run.</text>',
        f'<text class="axis" text-anchor="middle" x="{left + chart_w / 2}" y="{height - 18}">Mean Provenance Data per Run (KB)</text>',
        f'<line x1="{left}" y1="{axis_y}" x2="{left + chart_w}" y2="{axis_y}" stroke="#94a3b8"/>',
    ]

    for tick in range(0, 5):
        value = max_value * tick / 4
        x = left + chart_w * tick / 4
        body.append(f'<line x1="{x}" y1="{top - 8}" x2="{x}" y2="{axis_y}" stroke="#e2e8f0"/>')
        body.append(f'<text class="small" text-anchor="middle" x="{x}" y="{axis_y + 18}">{value:.0f}</text>')

    for idx, row in enumerate(rows):
        y = top + idx * row_h
        value = kb(row["total_flowcept_bytes_mean_per_run"])
        bar_w = (value / max_value) * chart_w
        runs = max(float(row.get("runs") or 1), 1.0)
        mean_docs = float(row["total_flowcept_documents"]) / runs
        body.append(f'<text class="axis" text-anchor="end" x="{left - 24}" y="{y + 35}">{esc(row["approach_label"])}</text>')
        body.append(f'<rect x="{left}" y="{y + 9}" width="{bar_w}" height="38" fill="#2563eb" rx="5"/>')
        label_x = min(left + bar_w + 12, left + chart_w + 8)
        body.append(f'<text class="bar-label" x="{label_x}" y="{y + 33}">{value:.1f} KB</text>')
        docs_text = f"Mean docs/run: {mean_docs:.1f}"
        docs_x = left + max(16, min(bar_w - 210, bar_w * 0.5 - 78))
        body.append(f'<text class="bar-docs" x="{docs_x}" y="{y + 33}">{esc(docs_text)}</text>')

    body.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n")


def convert_png(svg_path: Path, png_path: Path, scale: float) -> None:
    try:
        subprocess.run(
            ["rsvg-convert", "-f", "png", "-z", str(scale), "-o", str(png_path), str(svg_path)],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    rows = read_rows(input_path)
    svg_path = output_dir / f"data_volume_by_approach_{args.use_case}.svg"
    png_path = output_dir / f"data_volume_by_approach_{args.use_case}.png"
    write_svg(svg_path, rows)
    convert_png(svg_path, png_path, args.png_scale)
    print(f"Wrote {svg_path}")
    if png_path.exists():
        print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
