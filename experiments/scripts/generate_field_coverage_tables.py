from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

from analyze_field_coverage import (
    DEFAULT_MAPPING_PATH,
    mapped_ancestor,
    mapping_fields,
    observed_fields_for_approach,
    selected_approaches_for_analysis,
)
from experiment_utils import (
    RESULTS_DIR,
    approach_display_label,
    load_approach_labels,
    load_approaches,
    load_yaml,
    use_case_display_label,
    utc_now_iso,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate field coverage tables and per-approach reports.")
    parser.add_argument("--approach", default="all", help="Approach name or 'all'.")
    parser.add_argument("--use-case", default="perceptron_gridsearch", help="Use case suffix to analyze.")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING_PATH), help="Editable field mapping YAML.")
    parser.add_argument("--output-dir", default=str(RESULTS_DIR / "_analysis"), help="Directory for generated tables.")
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def percent_cell(observed: int, possible: int) -> str:
    if possible == 0:
        return "n/a"
    return f"{(observed / possible) * 100:.1f}% ({observed}/{possible})"


def observed_mapped_fields(observed_fields: set[str], mapped_fields: dict[str, Any]) -> set[str]:
    mapped = set()
    for field in observed_fields:
        ancestor = mapped_ancestor(field, mapped_fields)
        if ancestor is not None:
            mapped.add(ancestor)
    return mapped


def conditional_excluded_fields(mapped_fields: dict[str, Any], conditional_context: dict[str, Any]) -> set[str]:
    excluded: set[str] = set()
    for field, entry in mapped_fields.items():
        condition = entry.get("conditional")
        if condition and not conditional_context.get(condition, False):
            excluded.add(field)
    return excluded


def collect_approach_fields(
    approach_name: str,
    use_case: str,
    mapping: dict[str, Any],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    defaults, approaches_cfg = load_approaches()
    labels = load_approach_labels()
    approaches = selected_approaches_for_analysis(approach_name, use_case)
    mapped = mapping_fields(mapping)
    approach_sets: dict[str, set[str]] = {}
    approach_raw_sets: dict[str, set[str]] = {}
    approach_possible_exclusions: dict[str, set[str]] = {}
    approach_labels: dict[str, str] = {}

    for name, approach in approaches.items():
        observed = observed_fields_for_approach(defaults, approach)
        observed_set = set(observed["observed_fields"])
        excluded = conditional_excluded_fields(mapped, observed.get("conditional_context") or {})
        approach_sets[name] = observed_mapped_fields(observed_set, mapped) - excluded
        approach_raw_sets[name] = observed_set
        approach_possible_exclusions[name] = excluded
        approach_labels[name] = approach_display_label(name, labels)

    return {
        "mapped": approach_sets,
        "raw": approach_raw_sets,
        "possible_exclusions": approach_possible_exclusions,
    }, approach_labels


def value_universe(mapped: dict[str, Any], key: str) -> dict[str, set[str]]:
    universe: dict[str, set[str]] = {}
    for field, entry in mapped.items():
        for value in entry.get(key) or []:
            universe.setdefault(value, set()).add(field)
    return dict(sorted(universe.items()))


def coverage_rows(
    approach_sets: dict[str, set[str]],
    approach_labels: dict[str, str],
    universe: dict[str, set[str]],
    dimension_column: str,
    possible_exclusions: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for approach_name, fields in sorted(approach_sets.items(), key=lambda item: approach_labels[item[0]]):
        for value, possible_fields in universe.items():
            effective_possible = possible_fields - (possible_exclusions or {}).get(approach_name, set())
            observed = fields & effective_possible
            possible_count = len(effective_possible)
            observed_count = len(observed)
            rows.append(
                {
                    "approach": approach_name,
                    "approach_label": approach_labels[approach_name],
                    dimension_column: value,
                    "observed_fields": observed_count,
                    "possible_fields": possible_count,
                    "coverage_percent": round((observed_count / possible_count) * 100, 2) if possible_count else 0.0,
                }
            )
    return rows


def matrix_markdown(
    title: str,
    description: str,
    rows: list[dict[str, Any]],
    dimension_column: str,
) -> str:
    labels = sorted({row["approach_label"] for row in rows})
    dimensions = sorted({row[dimension_column] for row in rows})
    lookup = {
        (row["approach_label"], row[dimension_column]): (int(row["observed_fields"]), int(row["possible_fields"]))
        for row in rows
    }
    table_rows = []
    for label in labels:
        table_rows.append([label] + [percent_cell(*lookup[(label, dimension)]) for dimension in dimensions])
    return "\n".join(
        [
            f"## {title}",
            "",
            description,
            "",
            markdown_table(["Approach"] + dimensions, table_rows),
            "",
        ]
    )


def question_universe(mapping: dict[str, Any], mapped: dict[str, Any]) -> dict[str, dict[str, Any]]:
    questions = {question: dict(entry) for question, entry in (mapping.get("questions") or {}).items()}
    for question, entry in questions.items():
        entry["field_set"] = set(entry.get("required_fields") or [])

    for field, entry in mapped.items():
        for question in entry.get("questions") or []:
            questions.setdefault(question, {"persona": "", "field_set": set()})
            questions[question].setdefault("field_set", set())
            questions[question]["field_set"].add(field)

    return dict(sorted(questions.items()))


def question_coverage_rows(
    approach_sets: dict[str, set[str]],
    approach_labels: dict[str, str],
    questions: dict[str, dict[str, Any]],
    possible_exclusions: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for approach_name, fields in sorted(approach_sets.items(), key=lambda item: approach_labels[item[0]]):
        for question, entry in questions.items():
            possible_fields = set(entry.get("field_set") or []) - (possible_exclusions or {}).get(approach_name, set())
            observed = fields & possible_fields
            possible_count = len(possible_fields)
            observed_count = len(observed)
            rows.append(
                {
                    "approach": approach_name,
                    "approach_label": approach_labels[approach_name],
                    "persona": entry.get("persona") or "",
                    "question": question,
                    "observed_fields": observed_count,
                    "possible_fields": possible_count,
                    "coverage_percent": round((observed_count / possible_count) * 100, 2) if possible_count else 0.0,
                }
            )
    return rows


def persona_rows_from_questions(question_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in question_rows:
        persona = row["persona"] or "Unassigned"
        key = (row["approach"], row["approach_label"], persona)
        grouped.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    for (approach, approach_label, persona), entries in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][2])):
        coverage_values = [float(entry["coverage_percent"]) for entry in entries]
        observed_total = sum(int(entry["observed_fields"]) for entry in entries)
        possible_total = sum(int(entry["possible_fields"]) for entry in entries)
        rows.append(
            {
                "approach": approach,
                "approach_label": approach_label,
                "persona": persona,
                "questions": len(entries),
                "observed_question_fields": observed_total,
                "possible_question_fields": possible_total,
                "mean_question_coverage_percent": round(sum(coverage_values) / len(coverage_values), 2) if coverage_values else 0.0,
            }
        )
    return rows


def persona_matrix_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    labels = sorted({row["approach_label"] for row in rows})
    personas = sorted({row["persona"] for row in rows})
    lookup = {
        (row["approach_label"], row["persona"]): (
            float(row["mean_question_coverage_percent"]),
            int(row["observed_question_fields"]),
            int(row["possible_question_fields"]),
        )
        for row in rows
    }
    table_rows = []
    for label in labels:
        cells = []
        for persona in personas:
            coverage, observed, possible = lookup.get((label, persona), (0.0, 0, 0))
            cells.append(f"{coverage:.1f}% ({observed}/{possible})")
        table_rows.append([label] + cells)

    return "\n".join(
        [
            "## Approach vs Personas",
            "",
            "This table aggregates question coverage by persona. Each cell shows the mean coverage across that persona's questions, followed by the total observed/possible question-linked fields.",
            "",
            markdown_table(["Approach"] + personas, table_rows),
            "",
        ]
    )


def question_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    table_rows = [
        [
            row["approach_label"],
            row["persona"],
            row["question"],
            str(row["observed_fields"]),
            str(row["possible_fields"]),
            f"{float(row['coverage_percent']):.1f}",
        ]
        for row in sorted(rows, key=lambda row: (row["approach_label"], row["persona"], row["question"]))
    ]
    return "\n".join(
        [
            "## Approach vs Question Coverage",
            "",
            "This table is the grouped-bar-plot source. Each row is one approach/question pair, with coverage computed from unique mapped fields linked to that question.",
            "",
            markdown_table(
                [
                    "Approach",
                    "Persona",
                    "Question",
                    "Observed Fields",
                    "Possible Fields",
                    "Coverage (%)",
                ],
                table_rows,
            ),
            "",
        ]
    )


def schema_group(field: str) -> str:
    parts = field.split(".")
    if len(parts) == 1:
        return field
    if parts[0] == "task" and parts[1] in {"telemetry_at_start", "telemetry_at_end", "telemetry_summary"}:
        return "task.telemetry_data"
    if len(parts) >= 2 and parts[1] in {"record_type", "identifiers", "timing", "provenance_data", "execution_metadata", "user_and_system_context", "telemetry_data", "user_facing_metadata", "runtime_context", "inputs_outputs_repository"}:
        return ".".join(parts[:2])
    return ".".join(parts[:2])


def count_by_mapping_values(fields: set[str], mapped: dict[str, Any], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for field in fields:
        for value in mapped.get(field, {}).get(key) or []:
            counter[value] += 1
    return counter


def write_per_approach_reports(
    output_dir: Path,
    use_case: str,
    field_sets: dict[str, dict[str, set[str]]],
    approach_labels: dict[str, str],
    mapped: dict[str, Any],
) -> None:
    report_dir = output_dir / f"approach_field_coverage_{use_case}"
    report_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[list[str]] = []

    for approach_name, mapped_fields_for_approach in sorted(field_sets["mapped"].items(), key=lambda item: approach_labels[item[0]]):
        raw_fields = field_sets["raw"][approach_name]
        unmapped_raw_fields = {field for field in raw_fields if mapped_ancestor(field, mapped) is None}
        schema_counts = Counter(schema_group(field) for field in raw_fields)
        capability_counts = count_by_mapping_values(mapped_fields_for_approach, mapped, "analytical_capabilities")
        category_counts = count_by_mapping_values(mapped_fields_for_approach, mapped, "provenance_data_categories")
        safe_name = approach_name.replace("/", "_")
        report_path = report_dir / f"{safe_name}.md"
        index_rows.append([approach_labels[approach_name], str(report_path)])

        lines = [
            f"# Field Coverage Report: {approach_labels[approach_name]}",
            "",
            f"Generated at: `{utc_now_iso()}`",
            f"Use case: `{use_case}`",
            "",
            "This report counts unique fields observed in MongoDB for this approach. Semanticless totals count fields without interpreting them; capability and data category totals count unique mapped fields.",
            "",
            "## Semanticless Field Count",
            "",
            markdown_table(
                ["Metric", "Value"],
                [
                    ["Unique observed fields", str(len(raw_fields))],
                    ["Unique mapped fields", str(len(mapped_fields_for_approach))],
                    ["Unique unmapped fields", str(len(unmapped_raw_fields))],
                ],
            ),
            "",
            "## Flowcept Schema Groups",
            "",
            markdown_table(["Schema Group", "Unique Fields"], [[key, str(value)] for key, value in sorted(schema_counts.items())]),
            "",
            "## Analytical Capabilities",
            "",
            markdown_table(["Analytical Capability", "Unique Mapped Fields"], [[key, str(value)] for key, value in sorted(capability_counts.items())]),
            "",
            "## Provenance Data Types",
            "",
            markdown_table(["Provenance Data Type", "Unique Mapped Fields"], [[key, str(value)] for key, value in sorted(category_counts.items())]),
            "",
        ]
        report_path.write_text("\n".join(lines))

    index_path = report_dir / "README.md"
    index_path.write_text(
        "\n".join(
            [
                f"# Per-Approach Field Coverage Reports: {use_case}",
                "",
                f"Generated at: `{utc_now_iso()}`",
                "",
                markdown_table(["Approach", "Report Path"], index_rows),
                "",
            ]
        )
    )


def write_combined_markdown(
    path: Path,
    use_case: str,
    mapping_path: Path,
    category_rows: list[dict[str, Any]],
    capability_rows: list[dict[str, Any]],
    persona_rows: list[dict[str, Any]],
    question_rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Provenance Field Coverage Tables",
        "",
        f"Generated at: `{utc_now_iso()}`",
        f"Use case: `{use_case}`",
        f"Editable mapping: `{mapping_path}`",
        "",
        "Coverage is computed from unique mapped fields observed in MongoDB. A field is counted once per approach even if it appears in many documents. Custom metadata fields are included when they exist in the official editable mapping.",
        "",
        matrix_markdown(
            "Approach vs Provenance Data Category",
            "Each cell shows coverage for a provenance data category as `percent (observed unique mapped fields / possible mapped fields)`.",
            category_rows,
            "provenance_data_category",
        ),
        matrix_markdown(
            "Approach vs Analytical Capabilities",
            "Each cell shows coverage for an analytical capability as `percent (observed unique mapped fields / possible mapped fields)`.",
            capability_rows,
            "analytical_capability",
        ),
    ]
    if persona_rows:
        lines.append(persona_matrix_markdown(persona_rows))
    if question_rows:
        lines.append(question_markdown(question_rows))
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    mapping_path = Path(args.mapping)
    output_dir = Path(args.output_dir)
    mapping = load_yaml(mapping_path)
    mapped = mapping_fields(mapping)
    field_sets, approach_labels = collect_approach_fields(args.approach, args.use_case, mapping)

    category_rows = coverage_rows(
        field_sets["mapped"],
        approach_labels,
        value_universe(mapped, "provenance_data_categories"),
        "provenance_data_category",
        field_sets["possible_exclusions"],
    )
    capability_rows = coverage_rows(
        field_sets["mapped"],
        approach_labels,
        value_universe(mapped, "analytical_capabilities"),
        "analytical_capability",
        field_sets["possible_exclusions"],
    )
    questions = question_universe(mapping, mapped)
    question_rows = question_coverage_rows(field_sets["mapped"], approach_labels, questions, field_sets["possible_exclusions"])
    persona_rows = persona_rows_from_questions(question_rows)

    prefix = output_dir / f"field_coverage_tables_{args.use_case}"
    write_csv(prefix.with_name(f"{prefix.name}_approach_vs_provenance_category.csv"), category_rows)
    write_csv(prefix.with_name(f"{prefix.name}_approach_vs_analytical_capability.csv"), capability_rows)
    write_csv(prefix.with_name(f"{prefix.name}_approach_vs_persona.csv"), persona_rows)
    write_csv(prefix.with_name(f"{prefix.name}_approach_vs_question_coverage.csv"), question_rows)
    write_combined_markdown(prefix.with_suffix(".md"), args.use_case, mapping_path, category_rows, capability_rows, persona_rows, question_rows)
    write_per_approach_reports(output_dir, args.use_case, field_sets, approach_labels, mapped)

    print(f"Wrote {prefix.with_suffix('.md')}")
    print(f"Wrote {prefix.with_name(f'{prefix.name}_approach_vs_provenance_category.csv')}")
    print(f"Wrote {prefix.with_name(f'{prefix.name}_approach_vs_analytical_capability.csv')}")
    print(f"Wrote {prefix.with_name(f'{prefix.name}_approach_vs_persona.csv')}")
    print(f"Wrote {prefix.with_name(f'{prefix.name}_approach_vs_question_coverage.csv')}")
    print(f"Wrote {output_dir / f'approach_field_coverage_{args.use_case}'}")


if __name__ == "__main__":
    main()
