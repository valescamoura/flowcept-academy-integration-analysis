from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from experiment_utils import CONFIG_DIR, save_yaml, utc_now_iso


DEFAULT_SOURCE = CONFIG_DIR / "mapping.md"
DEFAULT_OUTPUT = CONFIG_DIR / "coverage_mapping.yaml"

FIELD_ALIASES = {
    "status": "task.execution_metadata.status",
    "stderr": "task.execution_metadata.stderr",
    "stdout": "task.execution_metadata.stdout",
    "task.provenance_data.custom_metadata": "task.execution_metadata.custom_metadata",
}

PSEUDO_FIELDS = {
    "task.record_type.subtype.agent_communication": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agentic"],
        "notes": "Synthetic record-presence indicator. Counted when at least one task has subtype='agent_communication'.",
    },
    "task.record_type.subtype.academy_lifecycle": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agentic"],
        "notes": "Synthetic record-presence indicator. Counted when at least one task has subtype='academy_lifecycle'.",
    },
}

CONDITIONAL_FIELDS = {
    "task.execution_metadata.stderr": {
        "condition": "requires_error_stderr",
        "notes": "Included in the denominator only for approaches that produced at least one errored task with non-empty stderr.",
    }
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build coverage_mapping.yaml from mapping.md.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Official markdown table path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Generated YAML mapping path.")
    return parser.parse_args()


def canonical_field(field: str) -> str:
    field = field.strip()
    return FIELD_ALIASES.get(field, field)


def markdown_rows(section: str, text: str) -> list[list[str]]:
    match = re.search(rf"^##\s+(?:Tabela|Table)\s+{re.escape(section)}\b.*$", text, re.MULTILINE)
    if not match:
        return []
    following = text[match.start() :].splitlines()
    rows: list[list[str]] = []
    for line in following:
        if line.startswith("## ") and not re.match(rf"^##\s+(?:Tabela|Table)\s+{re.escape(section)}\b", line):
            break
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] in {"Analytical Capability", "Provenance Data Category", "Persona"}:
            continue
        rows.append(cells)
    return rows


def extract_fields(cell: str) -> list[str]:
    return [canonical_field(match) for match in re.findall(r"`([^`]+)`", cell)]


def split_kpis(cell: str) -> list[str]:
    return [part.strip() for part in re.split(r";|<br>", cell) if part.strip()]


def ensure_field(fields: dict[str, dict[str, Any]], field: str) -> dict[str, Any]:
    return fields.setdefault(
        field,
        {
            "provenance_data_categories": [],
            "analytical_capabilities": [],
            "conditional": None,
            "notes": "",
        },
    )


def append_unique(entry: dict[str, Any], key: str, value: str) -> None:
    values = entry.setdefault(key, [])
    if value not in values:
        values.append(value)


def build_mapping(source: Path) -> dict[str, Any]:
    text = source.read_text()
    fields: dict[str, dict[str, Any]] = {}
    capabilities: dict[str, str] = {}
    categories: dict[str, str] = {}
    questions: dict[str, dict[str, Any]] = {}

    for capability, description, field_cell in markdown_rows("1", text):
        capabilities[capability] = description
        for field in extract_fields(field_cell):
            append_unique(ensure_field(fields, field), "analytical_capabilities", capability)

    for category, description, field_cell in markdown_rows("2", text):
        categories[category] = description
        for field in extract_fields(field_cell):
            append_unique(ensure_field(fields, field), "provenance_data_categories", category)

    for row in markdown_rows("3", text):
        if len(row) < 4:
            continue
        persona, question, required_field_cell, kpi_cell = row[:4]
        required_fields = extract_fields(required_field_cell)
        questions[question] = {
            "persona": persona,
            "required_fields": required_fields,
            "kpis": split_kpis(kpi_cell),
        }
        for field in required_fields:
            entry = ensure_field(fields, field)
            append_unique(entry, "personas", persona)
            append_unique(entry, "questions", question)
            for kpi in split_kpis(kpi_cell):
                append_unique(entry, "kpis", kpi)

    for field, extra in PSEUDO_FIELDS.items():
        entry = ensure_field(fields, field)
        for category in extra["provenance_data_categories"]:
            append_unique(entry, "provenance_data_categories", category)
        for capability in extra["analytical_capabilities"]:
            append_unique(entry, "analytical_capabilities", capability)
        entry["notes"] = extra["notes"]

    for field, condition in CONDITIONAL_FIELDS.items():
        entry = ensure_field(fields, field)
        entry["conditional"] = condition["condition"]
        entry["notes"] = condition["notes"]

    return {
        "generated_from": str(source),
        "generated_at": utc_now_iso(),
        "notes": [
            "Generated mapping used by the current coverage scripts.",
            "Edit mapping.md, then rerun build_coverage_mapping.py.",
            "Synthetic subtype record-presence indicators are included as pseudo-fields.",
            "task.execution_metadata.stderr is conditional and does not count when no errored task has stderr.",
        ],
        "provenance_data_categories": categories,
        "analytical_capabilities": capabilities,
        "questions": dict(sorted(questions.items())),
        "fields": dict(sorted(fields.items())),
        "custom_fields": {},
    }


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    mapping = build_mapping(source)
    save_yaml(output, mapping)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
