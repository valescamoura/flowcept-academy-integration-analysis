from __future__ import annotations

import argparse
import csv
import html
import textwrap
from pathlib import Path
from typing import Any

from experiment_utils import RESULTS_DIR, utc_now_iso


DEFAULT_ANALYSIS_DIR = RESULTS_DIR / "_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SVG figures from field coverage CSV tables.")
    parser.add_argument("--use-case", default="perceptron_gridsearch", help="Use case suffix used in coverage table filenames.")
    parser.add_argument("--analysis-dir", default=str(DEFAULT_ANALYSIS_DIR), help="Directory containing coverage CSV files.")
    parser.add_argument("--output-dir", help="Figure output directory. Defaults to <analysis-dir>/field_coverage_figures_<use-case>.")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def coverage_color(value: float, domain_min: float = 0.0, domain_max: float = 100.0) -> str:
    value = max(0.0, min(100.0, value))
    if domain_max > domain_min:
        value = (value - domain_min) / (domain_max - domain_min) * 100.0
    value = max(0.0, min(100.0, value))
    stops = [
        (0.0, (247, 251, 255)),
        (25.0, (198, 219, 239)),
        (50.0, (107, 174, 214)),
        (75.0, (33, 113, 181)),
        (100.0, (8, 48, 107)),
    ]
    for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
        if value <= v1:
            ratio = 0.0 if v1 == v0 else (value - v0) / (v1 - v0)
            rgb = tuple(round(c0[i] + (c1[i] - c0[i]) * ratio) for i in range(3))
            return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
    rgb = stops[-1][1]
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def text_color(value: float) -> str:
    return "#f8fafc" if value >= 65 else "#0f172a"


def write_svg(path: Path, width: int, height: int, body: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
        ".title { font-size: 24px; font-weight: 700; fill: #0f172a; }",
        ".subtitle { font-size: 15px; fill: #475569; }",
        ".axis { font-size: 18px; fill: #334155; }",
        ".axis-title { font-size: 18px; font-weight: 800; fill: #334155; }",
        ".cell-label { font-size: 21px; font-weight: 800; }",
        ".small { font-size: 14px; fill: #475569; }",
        ".persona-label { font-size: 14px; font-weight: 700; fill: #334155; }",
        ".legend-persona { font-size: 17px; font-weight: 800; fill: #0f172a; }",
        "</style>",
        *body,
        "</svg>",
    ]
    path.write_text("\n".join(svg) + "\n")


def wrap_text(text: str, max_chars: int) -> list[str]:
    chunks = textwrap.wrap(
        str(text).replace("-", "- "),
        width=max_chars,
        break_long_words=False,
        break_on_hyphens=True,
    )
    return [chunk.replace("- ", "-") for chunk in chunks] or [str(text)]


def tint_color(hex_color: str, tint: float) -> str:
    """Blend a color with white. tint=0 keeps the original color; tint=1 is white."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = round(r + (255 - r) * tint)
    g = round(g + (255 - g) * tint)
    b = round(b + (255 - b) * tint)
    return f"#{r:02x}{g:02x}{b:02x}"


def heatmap(
    rows: list[dict[str, str]],
    dimension_column: str,
    value_column: str,
    title: str,
    subtitle: str,
    x_axis_label: str,
    y_axis_label: str,
    output_path: Path,
) -> None:
    approaches = sorted({row["approach_label"] for row in rows})
    dimensions = sorted({row[dimension_column] for row in rows})
    lookup = {(row["approach_label"], row[dimension_column]): float(row[value_column]) for row in rows}
    values = [float(row[value_column]) for row in rows]
    observed_min = min(values) if values else 0.0
    observed_max = max(values) if values else 100.0
    adaptive_scale = observed_min >= 50.0 and (observed_max - observed_min) <= 40.0
    color_min = observed_min if adaptive_scale else 0.0
    color_max = observed_max if adaptive_scale else 100.0

    left = 390
    top = 170
    cell_w = 245 if len(dimensions) <= 3 else 205
    cell_h = 74
    right = 55
    bottom = 68
    width = left + len(dimensions) * cell_w + right
    height = top + len(approaches) * cell_h + bottom
    body: list[str] = [
        f'<text class="title" x="24" y="34">{esc(title)}</text>',
        f'<text class="subtitle" x="24" y="58">{esc(subtitle)}</text>',
        f'<text class="axis-title" text-anchor="middle" x="{left + (len(dimensions) * cell_w) / 2}" y="{top - 78}">{esc(x_axis_label)}</text>',
        f'<text class="axis-title" text-anchor="middle" transform="translate(58,{top + (len(approaches) * cell_h) / 2}) rotate(-90)">{esc(y_axis_label)}</text>',
    ]

    for i, dimension in enumerate(dimensions):
        x = left + i * cell_w + cell_w / 2
        for j, line in enumerate(wrap_text(dimension, 18)[:3]):
            body.append(f'<text class="axis" text-anchor="middle" x="{x}" y="{top - 58 + j * 20}">{esc(line)}</text>')

    for r, approach in enumerate(approaches):
        y = top + r * cell_h
        body.append(f'<text class="axis" text-anchor="end" x="{left - 22}" y="{y + 47}">{esc(approach)}</text>')
        for c, dimension in enumerate(dimensions):
            value = lookup.get((approach, dimension), 0.0)
            x = left + c * cell_w
            color = coverage_color(value, color_min, color_max)
            body.append(f'<rect x="{x}" y="{y}" width="{cell_w - 3}" height="{cell_h - 3}" fill="{color}" rx="5"/>')
            body.append(
                f'<text class="cell-label" text-anchor="middle" x="{x + cell_w / 2}" y="{y + 47}" fill="{text_color((value - color_min) / max(color_max - color_min, 1) * 100 if adaptive_scale else value)}">{value:.1f}%</text>'
            )

    write_svg(output_path, width, height, body)


def grouped_bar_question_coverage(rows: list[dict[str, str]], output_path: Path) -> None:
    approaches = sorted({row["approach_label"] for row in rows})
    question_persona = {row["question"]: row.get("persona", "Unassigned") or "Unassigned" for row in rows}
    preferred_personas = ["Domain Specialist", "Platform Engineer", "AI Engineer"]
    personas = [
        persona
        for persona in preferred_personas
        if persona in set(question_persona.values())
    ] + sorted(set(question_persona.values()) - set(preferred_personas))
    question_mean_coverage: dict[str, float] = {}
    for question in question_persona:
        values = [float(row["coverage_percent"]) for row in rows if row["question"] == question]
        question_mean_coverage[question] = sum(values) / len(values) if values else 0.0
    questions_by_persona = {
        persona: sorted(
            (question for question, q_persona in question_persona.items() if q_persona == persona),
            key=lambda question: (question_mean_coverage[question], question),
        )
        for persona in personas
    }
    questions = [question for persona in personas for question in questions_by_persona[persona]]
    lookup = {(row["approach_label"], row["question"]): float(row["coverage_percent"]) for row in rows}

    left = 150
    top = 118
    chart_h = 390
    bar_gap = 3
    bar_w = 8
    persona_gap = 16
    group_pad = 20
    subgroup_offsets: dict[str, tuple[int, int]] = {}
    question_offsets: dict[str, int] = {}
    cursor = group_pad
    for persona in personas:
        start = cursor
        for question in questions_by_persona[persona]:
            question_offsets[question] = cursor
            cursor += bar_w + bar_gap
        end = cursor - bar_gap
        subgroup_offsets[persona] = (start, end)
        cursor += persona_gap
    group_w = max(190, cursor + group_pad)
    legend_top = top + 32
    legend_x = left + len(approaches) * group_w + 54
    legend_text_x = legend_x + 18
    legend_width_chars = 60
    legend_line_h = 13
    legend_gap = 9
    persona_legend_gap = 18
    legend_items = [
        (
            persona,
            [
                (question, wrap_text(question, legend_width_chars))
                for question in questions_by_persona[persona]
            ],
        )
        for persona in personas
    ]
    legend_h = 0
    for _, items in legend_items:
        legend_h += 22
        legend_h += sum(max(18, len(lines) * legend_line_h) + legend_gap for _, lines in items)
        legend_h += persona_legend_gap
    width = left + len(approaches) * group_w + 700
    height = max(top + chart_h + 100, legend_top + legend_h + 30)
    persona_colors = {
        "Domain Specialist": "#2563eb",
        "Platform Engineer": "#0f766e",
        "AI Engineer": "#ea580c",
        "Unassigned": "#64748b",
    }
    fallback_colors = ["#7c3aed", "#be123c", "#0891b2"]
    for idx, persona in enumerate(personas):
        persona_colors.setdefault(persona, fallback_colors[idx % len(fallback_colors)])
    question_colors: dict[str, str] = {}
    tint_steps = [0.0, 0.13, 0.25, 0.37, 0.49]
    for persona in personas:
        for q_idx, question in enumerate(questions_by_persona[persona]):
            question_colors[question] = tint_color(persona_colors[persona], tint_steps[q_idx % len(tint_steps)])
    short_persona = {
        "Domain Specialist": "Domain",
        "Platform Engineer": "Platform",
        "AI Engineer": "AI",
    }

    body: list[str] = [
        '<text class="title" x="24" y="34">Approach vs Question Coverage</text>',
        '<text class="subtitle" x="24" y="58">Grouped bar plot: each group is an approach; bars are questions, colored and grouped by persona.</text>',
        f'<line x1="{left}" y1="{top + chart_h}" x2="{left + len(approaches) * group_w}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<text class="axis" text-anchor="middle" transform="translate(42,{top + chart_h / 2}) rotate(-90)">Question coverage (%)</text>',
    ]
    for tick in range(0, 101, 25):
        y = top + chart_h - (tick / 100) * chart_h
        body.append(f'<line x1="{left - 5}" y1="{y}" x2="{left + len(approaches) * group_w}" y2="{y}" stroke="#e2e8f0"/>')
        body.append(f'<text class="small" text-anchor="end" x="{left - 10}" y="{y + 4}">{tick}%</text>')

    for a_idx, approach in enumerate(approaches):
        group_x = left + a_idx * group_w
        for persona in personas:
            start, end = subgroup_offsets[persona]
            label_x = group_x + (start + end) / 2
            body.append(
                f'<text class="persona-label" text-anchor="middle" x="{label_x}" y="{top - 12}">{esc(short_persona.get(persona, persona))}</text>'
            )
            body.append(
                f'<line x1="{group_x + start}" y1="{top - 7}" x2="{group_x + end}" y2="{top - 7}" stroke="{persona_colors[persona]}" stroke-width="2"/>'
            )
        for question in questions:
            persona = question_persona[question]
            value = lookup.get((approach, question), 0.0)
            bar_h = (value / 100) * chart_h
            x = group_x + question_offsets[question]
            y = top + chart_h - bar_h
            body.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{question_colors[question]}"/>')
        for line_idx, line in enumerate(wrap_text(approach, 16)[:3]):
            body.append(
                f'<text class="axis" text-anchor="middle" x="{left + a_idx * group_w + group_w / 2}" y="{top + chart_h + 22 + line_idx * 14}">{esc(line)}</text>'
            )

    body.append(f'<text class="axis" x="{legend_x}" y="{top - 8}">Questions</text>')
    y = legend_top
    question_number = 1
    for persona, items in legend_items:
        body.append(f'<rect x="{legend_x}" y="{y - 12}" width="12" height="12" fill="{persona_colors[persona]}"/>')
        body.append(f'<text class="legend-persona" x="{legend_text_x}" y="{y - 2}">{esc(persona)}</text>')
        y += 22
        for _, lines in items:
            question = questions[question_number - 1]
            body.append(f'<rect x="{legend_x + 2}" y="{y - 10}" width="8" height="8" fill="{question_colors[question]}"/>')
            for line_idx, line in enumerate(lines):
                prefix = f"Q{question_number}: " if line_idx == 0 else "   "
                body.append(
                    f'<text class="small" x="{legend_text_x}" y="{y + line_idx * legend_line_h}">{esc(prefix + line)}</text>'
                )
            y += max(18, len(lines) * legend_line_h) + legend_gap
            question_number += 1
        y += persona_legend_gap

    write_svg(output_path, width, height, body)


def grouped_bar_question_coverage_bottom_legend(rows: list[dict[str, str]], output_path: Path) -> None:
    approaches = sorted({row["approach_label"] for row in rows})
    question_persona = {row["question"]: row.get("persona", "Unassigned") or "Unassigned" for row in rows}
    preferred_personas = ["Domain Specialist", "Platform Engineer", "AI Engineer"]
    personas = [
        persona
        for persona in preferred_personas
        if persona in set(question_persona.values())
    ] + sorted(set(question_persona.values()) - set(preferred_personas))
    question_mean_coverage: dict[str, float] = {}
    for question in question_persona:
        values = [float(row["coverage_percent"]) for row in rows if row["question"] == question]
        question_mean_coverage[question] = sum(values) / len(values) if values else 0.0
    questions_by_persona = {
        persona: sorted(
            (question for question, q_persona in question_persona.items() if q_persona == persona),
            key=lambda question: (question_mean_coverage[question], question),
        )
        for persona in personas
    }
    questions = [question for persona in personas for question in questions_by_persona[persona]]
    lookup = {(row["approach_label"], row["question"]): float(row["coverage_percent"]) for row in rows}

    left = 150
    top = 118
    chart_h = 390
    bar_gap = 3
    bar_w = 8
    persona_gap = 16
    group_pad = 20
    right = 70
    subgroup_offsets: dict[str, tuple[int, int]] = {}
    question_offsets: dict[str, int] = {}
    cursor = group_pad
    for persona in personas:
        start = cursor
        for question in questions_by_persona[persona]:
            question_offsets[question] = cursor
            cursor += bar_w + bar_gap
        end = cursor - bar_gap
        subgroup_offsets[persona] = (start, end)
        cursor += persona_gap
    group_w = max(190, cursor + group_pad)
    chart_w = len(approaches) * group_w
    width = left + chart_w + right
    legend_top = top + chart_h + 92
    legend_column_gap = 34
    legend_column_w = (width - left - right - legend_column_gap * (len(personas) - 1)) / max(1, len(personas))
    legend_width_chars = max(30, int(legend_column_w / 8.8))
    legend_line_h = 13
    legend_gap = 9
    legend_heights: list[int] = []
    legend_items: list[tuple[str, list[tuple[str, list[str]]]]] = []
    for persona in personas:
        items = [(question, wrap_text(question, legend_width_chars)) for question in questions_by_persona[persona]]
        legend_items.append((persona, items))
        legend_heights.append(24 + sum(max(18, len(lines) * legend_line_h) + legend_gap for _, lines in items))
    height = legend_top + (max(legend_heights) if legend_heights else 0) + 38

    persona_colors = {
        "Domain Specialist": "#2563eb",
        "Platform Engineer": "#0f766e",
        "AI Engineer": "#ea580c",
        "Unassigned": "#64748b",
    }
    fallback_colors = ["#7c3aed", "#be123c", "#0891b2"]
    for idx, persona in enumerate(personas):
        persona_colors.setdefault(persona, fallback_colors[idx % len(fallback_colors)])
    question_colors: dict[str, str] = {}
    tint_steps = [0.0, 0.13, 0.25, 0.37, 0.49]
    for persona in personas:
        for q_idx, question in enumerate(questions_by_persona[persona]):
            question_colors[question] = tint_color(persona_colors[persona], tint_steps[q_idx % len(tint_steps)])
    short_persona = {
        "Domain Specialist": "Domain",
        "Platform Engineer": "Platform",
        "AI Engineer": "AI",
    }

    body: list[str] = [
        '<text class="title" x="24" y="34">Approach vs Question Coverage</text>',
        '<text class="subtitle" x="24" y="58">Grouped bar plot: each group is an approach; bars are questions, colored and grouped by persona.</text>',
        f'<line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<text class="axis" text-anchor="middle" transform="translate(42,{top + chart_h / 2}) rotate(-90)">Question coverage (%)</text>',
    ]
    for tick in range(0, 101, 25):
        y = top + chart_h - (tick / 100) * chart_h
        body.append(f'<line x1="{left - 5}" y1="{y}" x2="{left + chart_w}" y2="{y}" stroke="#e2e8f0"/>')
        body.append(f'<text class="small" text-anchor="end" x="{left - 10}" y="{y + 4}">{tick}%</text>')

    for a_idx, approach in enumerate(approaches):
        group_x = left + a_idx * group_w
        for persona in personas:
            start, end = subgroup_offsets[persona]
            label_x = group_x + (start + end) / 2
            body.append(
                f'<text class="persona-label" text-anchor="middle" x="{label_x}" y="{top - 12}">{esc(short_persona.get(persona, persona))}</text>'
            )
            body.append(
                f'<line x1="{group_x + start}" y1="{top - 7}" x2="{group_x + end}" y2="{top - 7}" stroke="{persona_colors[persona]}" stroke-width="2"/>'
            )
        for question in questions:
            persona = question_persona[question]
            value = lookup.get((approach, question), 0.0)
            bar_h = (value / 100) * chart_h
            x = group_x + question_offsets[question]
            y = top + chart_h - bar_h
            body.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{question_colors[question]}"/>')
        for line_idx, line in enumerate(wrap_text(approach, 16)[:3]):
            body.append(
                f'<text class="axis" text-anchor="middle" x="{left + a_idx * group_w + group_w / 2}" y="{top + chart_h + 22 + line_idx * 14}">{esc(line)}</text>'
            )

    question_number = 1
    for persona_idx, (persona, items) in enumerate(legend_items):
        legend_x = left + persona_idx * (legend_column_w + legend_column_gap)
        legend_text_x = legend_x + 18
        y = legend_top
        body.append(f'<rect x="{legend_x}" y="{y - 12}" width="12" height="12" fill="{persona_colors[persona]}"/>')
        body.append(f'<text class="legend-persona" x="{legend_text_x}" y="{y - 2}">{esc(persona)}</text>')
        y += 24
        for question, lines in items:
            body.append(f'<rect x="{legend_x + 2}" y="{y - 10}" width="8" height="8" fill="{question_colors[question]}"/>')
            for line_idx, line in enumerate(lines):
                prefix = f"Q{question_number}: " if line_idx == 0 else "   "
                body.append(
                    f'<text class="small" x="{legend_text_x}" y="{y + line_idx * legend_line_h}">{esc(prefix + line)}</text>'
                )
            y += max(18, len(lines) * legend_line_h) + legend_gap
            question_number += 1

    write_svg(output_path, width, height, body)


def grouped_bar_question_coverage_qid_legend(rows: list[dict[str, str]], output_path: Path) -> None:
    approaches = sorted({row["approach_label"] for row in rows})
    question_persona = {row["question"]: row.get("persona", "Unassigned") or "Unassigned" for row in rows}
    preferred_personas = ["Domain Specialist", "Platform Engineer", "AI Engineer"]
    personas = [
        persona
        for persona in preferred_personas
        if persona in set(question_persona.values())
    ] + sorted(set(question_persona.values()) - set(preferred_personas))
    question_mean_coverage: dict[str, float] = {}
    for question in question_persona:
        values = [float(row["coverage_percent"]) for row in rows if row["question"] == question]
        question_mean_coverage[question] = sum(values) / len(values) if values else 0.0
    questions_by_persona = {
        persona: sorted(
            (question for question, q_persona in question_persona.items() if q_persona == persona),
            key=lambda question: (question_mean_coverage[question], question),
        )
        for persona in personas
    }
    questions = [question for persona in personas for question in questions_by_persona[persona]]
    question_ids = {question: f"Q{idx + 1}" for idx, question in enumerate(questions)}
    lookup = {(row["approach_label"], row["question"]): float(row["coverage_percent"]) for row in rows}

    left = 150
    top = 118
    chart_h = 390
    bar_gap = 3
    bar_w = 8
    persona_gap = 16
    group_pad = 20
    right = 70
    subgroup_offsets: dict[str, tuple[int, int]] = {}
    question_offsets: dict[str, int] = {}
    cursor = group_pad
    for persona in personas:
        start = cursor
        for question in questions_by_persona[persona]:
            question_offsets[question] = cursor
            cursor += bar_w + bar_gap
        end = cursor - bar_gap
        subgroup_offsets[persona] = (start, end)
        cursor += persona_gap
    group_w = max(190, cursor + group_pad)
    chart_w = len(approaches) * group_w
    width = left + chart_w + right
    legend_top = top + chart_h + 92
    legend_column_gap = 34
    legend_column_w = (width - left - right - legend_column_gap * (len(personas) - 1)) / max(1, len(personas))
    height = legend_top + 95

    persona_colors = {
        "Domain Specialist": "#2563eb",
        "Platform Engineer": "#0f766e",
        "AI Engineer": "#ea580c",
        "Unassigned": "#64748b",
    }
    fallback_colors = ["#7c3aed", "#be123c", "#0891b2"]
    for idx, persona in enumerate(personas):
        persona_colors.setdefault(persona, fallback_colors[idx % len(fallback_colors)])
    question_colors: dict[str, str] = {}
    tint_steps = [0.0, 0.13, 0.25, 0.37, 0.49]
    for persona in personas:
        for q_idx, question in enumerate(questions_by_persona[persona]):
            question_colors[question] = tint_color(persona_colors[persona], tint_steps[q_idx % len(tint_steps)])
    short_persona = {
        "Domain Specialist": "Domain",
        "Platform Engineer": "Platform",
        "AI Engineer": "AI",
    }

    body: list[str] = [
        '<text class="title" x="24" y="34">Approach vs Question Coverage</text>',
        '<text class="subtitle" x="24" y="58">Grouped bar plot: each group is an approach; bars are question IDs, colored and grouped by persona.</text>',
        f'<line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#94a3b8"/>',
        f'<text class="axis" text-anchor="middle" transform="translate(42,{top + chart_h / 2}) rotate(-90)">Question coverage (%)</text>',
    ]
    for tick in range(0, 101, 25):
        y = top + chart_h - (tick / 100) * chart_h
        body.append(f'<line x1="{left - 5}" y1="{y}" x2="{left + chart_w}" y2="{y}" stroke="#e2e8f0"/>')
        body.append(f'<text class="small" text-anchor="end" x="{left - 10}" y="{y + 4}">{tick}%</text>')

    for a_idx, approach in enumerate(approaches):
        group_x = left + a_idx * group_w
        for persona in personas:
            start, end = subgroup_offsets[persona]
            label_x = group_x + (start + end) / 2
            body.append(
                f'<text class="persona-label" text-anchor="middle" x="{label_x}" y="{top - 12}">{esc(short_persona.get(persona, persona))}</text>'
            )
            body.append(
                f'<line x1="{group_x + start}" y1="{top - 7}" x2="{group_x + end}" y2="{top - 7}" stroke="{persona_colors[persona]}" stroke-width="2"/>'
            )
        for question in questions:
            value = lookup.get((approach, question), 0.0)
            bar_h = (value / 100) * chart_h
            x = group_x + question_offsets[question]
            y = top + chart_h - bar_h
            body.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{question_colors[question]}"/>')
        for line_idx, line in enumerate(wrap_text(approach, 16)[:3]):
            body.append(
                f'<text class="axis" text-anchor="middle" x="{left + a_idx * group_w + group_w / 2}" y="{top + chart_h + 22 + line_idx * 14}">{esc(line)}</text>'
            )

    for persona_idx, persona in enumerate(personas):
        legend_x = left + persona_idx * (legend_column_w + legend_column_gap)
        legend_text_x = legend_x + 18
        y = legend_top
        body.append(f'<rect x="{legend_x}" y="{y - 12}" width="12" height="12" fill="{persona_colors[persona]}"/>')
        body.append(f'<text class="legend-persona" x="{legend_text_x}" y="{y - 2}">{esc(persona)}</text>')
        y += 27
        x = legend_x
        for question in questions_by_persona[persona]:
            qid = question_ids[question]
            body.append(f'<rect x="{x}" y="{y - 11}" width="10" height="10" fill="{question_colors[question]}"/>')
            body.append(f'<text class="small" x="{x + 15}" y="{y - 2}">{esc(qid)}</text>')
            x += 52

    write_svg(output_path, width, height, body)


def write_index(output_dir: Path, use_case: str, figures: list[tuple[str, Path]]) -> None:
    lines = [
        f"# Field Coverage Figures: {use_case}",
        "",
        f"Generated at: `{utc_now_iso()}`",
        "",
        "These SVG figures are generated from the CSV coverage tables. Regenerate the tables first if the MongoDB data or YAML mapping changes.",
        "",
    ]
    for title, path in figures:
        lines.extend([f"## {title}", "", f"![{title}]({path.name})", ""])
    (output_dir / "README.md").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    analysis_dir = Path(args.analysis_dir)
    output_dir = Path(args.output_dir) if args.output_dir else analysis_dir / f"field_coverage_figures_{args.use_case}"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = analysis_dir / f"field_coverage_tables_{args.use_case}"

    provenance_rows = read_csv(prefix.with_name(f"{prefix.name}_approach_vs_provenance_category.csv"))
    capability_rows = read_csv(prefix.with_name(f"{prefix.name}_approach_vs_analytical_capability.csv"))
    persona_rows = read_csv(prefix.with_name(f"{prefix.name}_approach_vs_persona.csv"))
    question_rows = read_csv(prefix.with_name(f"{prefix.name}_approach_vs_question_coverage.csv"))

    figures = [
        ("Approach vs Provenance Data Category", output_dir / "approach_vs_provenance_data_category.svg"),
        ("Approach vs Analytical Capabilities", output_dir / "approach_vs_analytical_capabilities.svg"),
    ]

    heatmap(
        provenance_rows,
        "provenance_data_category",
        "coverage_percent",
        "Approach vs Provenance Data Category",
        "Coverage of unique mapped fields by provenance data type.",
        "Provenance data category",
        "Approach",
        figures[0][1],
    )
    heatmap(
        capability_rows,
        "analytical_capability",
        "coverage_percent",
        "Approach vs Analytical Capabilities",
        "Coverage of unique mapped fields by analytical capability.",
        "Analytical capability",
        "Approach",
        figures[1][1],
    )
    persona_path = output_dir / "approach_vs_personas.svg"
    question_path = output_dir / "approach_vs_question_coverage.svg"
    if persona_rows:
        figures.append(("Approach vs Personas", persona_path))
        heatmap(
            persona_rows,
            "persona",
            "mean_question_coverage_percent",
            "Approach vs Personas",
            "Mean question coverage per persona, based on unique mapped fields.",
            "Persona",
            "Approach",
            persona_path,
        )
    elif persona_path.exists():
        persona_path.unlink()

    if question_rows:
        figures.append(("Approach vs Question Coverage", question_path))
        grouped_bar_question_coverage(question_rows, question_path)
        grouped_bar_question_coverage_bottom_legend(
            question_rows,
            output_dir / "approach_vs_question_coverage_bottom_legend.svg",
        )
        grouped_bar_question_coverage_qid_legend(
            question_rows,
            output_dir / "approach_vs_question_coverage_qid_legend.svg",
        )
    elif question_path.exists():
        question_path.unlink()
    write_index(output_dir, args.use_case, figures)

    for _, path in figures:
        print(f"Wrote {path}")
    print(f"Wrote {output_dir / 'README.md'}")


if __name__ == "__main__":
    main()
