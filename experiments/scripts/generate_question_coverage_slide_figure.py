from __future__ import annotations

import argparse
import csv
import html
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from experiment_utils import RESULTS_DIR


DEFAULT_ANALYSIS_DIR = RESULTS_DIR / "_analysis"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def wrap_text(text: str, width: int) -> list[str]:
    return textwrap.wrap(str(text), width=width, break_long_words=False) or [str(text)]


def tint_color(hex_color: str, tint: float) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = round(r + (255 - r) * tint)
    g = round(g + (255 - g) * tint)
    b = round(b + (255 - b) * tint)
    return f"#{r:02x}{g:02x}{b:02x}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def build_svg(rows: list[dict[str, str]]) -> str:
    approaches = sorted({row["approach_label"] for row in rows})
    question_persona = {row["question"]: row.get("persona", "Unassigned") or "Unassigned" for row in rows}
    preferred_personas = ["Domain Specialist", "Platform Engineer", "AI Engineer"]
    personas = [p for p in preferred_personas if p in set(question_persona.values())]
    personas += sorted(set(question_persona.values()) - set(preferred_personas))

    question_mean: dict[str, float] = {}
    for question in question_persona:
        vals = [float(row["coverage_percent"]) for row in rows if row["question"] == question]
        question_mean[question] = sum(vals) / len(vals) if vals else 0.0
    questions_by_persona = {
        persona: sorted(
            [q for q, p in question_persona.items() if p == persona],
            key=lambda q: (question_mean[q], q),
        )
        for persona in personas
    }
    questions = [q for persona in personas for q in questions_by_persona[persona]]
    lookup = {(row["approach_label"], row["question"]): float(row["coverage_percent"]) for row in rows}

    width, height = 2400, 1350
    left, right = 180, 80
    top, chart_h = 150, 560
    chart_w = width - left - right
    group_w = chart_w / len(approaches)
    bar_w, bar_gap, persona_gap = 13, 4, 24

    persona_colors = {
        "Domain Specialist": "#2563eb",
        "Platform Engineer": "#0f766e",
        "AI Engineer": "#ea580c",
        "Unassigned": "#64748b",
    }
    tint_steps = [0.0, 0.13, 0.25, 0.37, 0.49]
    question_colors: dict[str, str] = {}
    for persona in personas:
        for idx, question in enumerate(questions_by_persona[persona]):
            question_colors[question] = tint_color(persona_colors[persona], tint_steps[idx % len(tint_steps)])

    question_offsets: dict[str, float] = {}
    subgroup_offsets: dict[str, tuple[float, float]] = {}
    cursor = 26.0
    for persona in personas:
        start = cursor
        for question in questions_by_persona[persona]:
            question_offsets[question] = cursor
            cursor += bar_w + bar_gap
        subgroup_offsets[persona] = (start, cursor - bar_gap)
        cursor += persona_gap

    short_persona = {
        "Domain Specialist": "Domain",
        "Platform Engineer": "Platform",
        "AI Engineer": "AI",
    }

    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: Arial, Helvetica, sans-serif; fill: #0f172a; }",
        ".title { font-size: 36px; font-weight: 700; }",
        ".subtitle { font-size: 20px; fill: #475569; }",
        ".axis { font-size: 18px; fill: #334155; }",
        ".tick { font-size: 16px; fill: #475569; }",
        ".small { font-size: 17px; fill: #475569; }",
        ".persona { font-size: 18px; font-weight: 700; fill: #0f172a; }",
        ".persona-mini { font-size: 14px; font-weight: 700; fill: #334155; }",
        "</style>",
        '<text class="title" x="34" y="48">Approach vs Question Coverage</text>',
        '<text class="subtitle" x="34" y="80">Question coverage by approach, grouped and colored by persona.</text>',
        f'<line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#94a3b8" stroke-width="2"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#94a3b8" stroke-width="2"/>',
        f'<text class="axis" text-anchor="middle" transform="translate(54,{top + chart_h / 2}) rotate(-90)">Question coverage (%)</text>',
    ]

    for tick in range(0, 101, 25):
        y = top + chart_h - tick / 100 * chart_h
        body.append(f'<line x1="{left - 8}" y1="{y}" x2="{left + chart_w}" y2="{y}" stroke="#e2e8f0" stroke-width="1.4"/>')
        body.append(f'<text class="tick" text-anchor="end" x="{left - 15}" y="{y + 5}">{tick}%</text>')

    for a_idx, approach in enumerate(approaches):
        group_x = left + a_idx * group_w + 10
        for persona in personas:
            start, end = subgroup_offsets[persona]
            label_x = group_x + (start + end) / 2
            color = persona_colors[persona]
            body.append(f'<text class="persona-mini" text-anchor="middle" x="{label_x}" y="{top - 18}">{esc(short_persona.get(persona, persona))}</text>')
            body.append(f'<line x1="{group_x + start}" y1="{top - 10}" x2="{group_x + end}" y2="{top - 10}" stroke="{color}" stroke-width="3"/>')
        for question in questions:
            value = lookup.get((approach, question), 0.0)
            x = group_x + question_offsets[question]
            bar_h = value / 100 * chart_h
            y = top + chart_h - bar_h
            body.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{question_colors[question]}"/>')
        for line_idx, line in enumerate(wrap_text(approach, 16)[:3]):
            body.append(f'<text class="axis" text-anchor="middle" x="{left + a_idx * group_w + group_w / 2}" y="{top + chart_h + 34 + line_idx * 22}">{esc(line)}</text>')

    legend_top = 835
    col_gap = 42
    col_w = (width - 90 - col_gap * 2) / 3
    q_number = 1
    for p_idx, persona in enumerate(personas):
        x = 50 + p_idx * (col_w + col_gap)
        y = legend_top
        body.append(f'<rect x="{x}" y="{y - 18}" width="20" height="20" fill="{persona_colors[persona]}"/>')
        body.append(f'<text class="persona" x="{x + 30}" y="{y}">{esc(persona)}</text>')
        y += 38
        for question in questions_by_persona[persona]:
            lines = wrap_text(question, 52)
            body.append(f'<rect x="{x + 4}" y="{y - 16}" width="14" height="14" fill="{question_colors[question]}"/>')
            for line_idx, line in enumerate(lines):
                prefix = f"Q{q_number}: " if line_idx == 0 else "   "
                body.append(f'<text class="small" x="{x + 30}" y="{y + line_idx * 21}">{esc(prefix + line)}</text>')
            y += max(24, len(lines) * 21) + 13
            q_number += 1

    body.append("</svg>")
    return "\n".join(body) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate slide-friendly question coverage figure.")
    parser.add_argument("--use-case", default="perceptron_gridsearch")
    parser.add_argument("--analysis-dir", default=str(DEFAULT_ANALYSIS_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analysis_dir = Path(args.analysis_dir)
    csv_path = analysis_dir / f"field_coverage_tables_{args.use_case}_approach_vs_question_coverage.csv"
    output_dir = analysis_dir / f"field_coverage_figures_{args.use_case}"
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / "approach_vs_question_coverage_slide.svg"
    png_path = output_dir / "approach_vs_question_coverage_slide_4k.png"
    svg_path.write_text(build_svg(read_csv(csv_path)))
    subprocess.run(["rsvg-convert", "-f", "png", "-w", "3840", "-o", str(png_path), str(svg_path)], check=True)
    print(f"Wrote {svg_path}")
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
