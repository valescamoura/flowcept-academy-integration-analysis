from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from experiment_utils import (
    CONFIG_DIR,
    approach_results_dir,
    docs_field_inventory,
    load_approaches,
    load_yaml,
    mongo_client,
    selected_approaches,
    write_json,
)


COLLECTIONS = {
    "workflow": "workflows",
    "task": "tasks",
    "object": "objects",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Flowcept schema field coverage from Mongo.")
    parser.add_argument("--approach", required=True, help="Approach name or 'all'.")
    return parser.parse_args()


def has_field(inventory: dict[str, Any], field: str) -> bool:
    return field in inventory.get("fields", {})


def coverage_for_schema(inventory: dict[str, Any], expectations: dict[str, list[str]]) -> dict[str, Any]:
    required = expectations.get("required", [])
    optional = expectations.get("optional", [])
    not_applicable = expectations.get("not_applicable", [])
    present_required = [f for f in required if has_field(inventory, f)]
    missing_required = [f for f in required if not has_field(inventory, f)]
    present_optional = [f for f in optional if has_field(inventory, f)]
    missing_optional = [f for f in optional if not has_field(inventory, f)]
    expected_catalog = sorted(set(required) | set(optional))
    present_expected = [f for f in expected_catalog if has_field(inventory, f)]
    missing_expected = [f for f in expected_catalog if not has_field(inventory, f)]
    categories = {}
    for category_name, fields in expectations.get("categories", {}).items():
        present = [f for f in fields if has_field(inventory, f)]
        missing = [f for f in fields if not has_field(inventory, f)]
        categories[category_name] = {
            "total": len(fields),
            "present": present,
            "missing": missing,
            "coverage": len(present) / len(fields) if fields else None,
        }
    return {
        "document_count": inventory["document_count"],
        "field_count": len(inventory["fields"]),
        "required": {
            "total": len(required),
            "present": present_required,
            "missing": missing_required,
            "coverage": len(present_required) / len(required) if required else None,
        },
        "expected_catalog": {
            "total": len(expected_catalog),
            "present": present_expected,
            "missing": missing_expected,
            "coverage": len(present_expected) / len(expected_catalog) if expected_catalog else None,
        },
        "optional": {
            "total": len(optional),
            "present": present_optional,
            "missing": missing_optional,
            "coverage": len(present_optional) / len(optional) if optional else None,
        },
        "not_applicable": not_applicable,
        "categories": categories,
        "all_observed_fields": sorted(inventory["fields"]),
        "field_presence": inventory["fields"],
    }


def analyze_approach(name: str, approach: dict[str, Any], defaults: dict[str, Any], expectations: dict[str, Any]) -> dict:
    client = mongo_client(defaults, approach)
    db = client[approach["mongo_db"]]
    result = {
        "approach": name,
        "mongo_db": approach["mongo_db"],
        "schemas": {},
    }
    for schema_name, collection in COLLECTIONS.items():
        docs = list(db[collection].find({}))
        inventory = docs_field_inventory(docs)
        result["schemas"][schema_name] = coverage_for_schema(inventory, expectations.get(schema_name, {}))
    return result


def write_markdown(path: Path, results: list[dict]) -> None:
    lines = [
        "# Analysis 2: Flowcept Schema Coverage",
        "",
        "The `required` and `optional` sets are experiment expectations, not hard validation rules. Missing fields do not fail the analysis; they indicate data that Flowcept supports but this approach/run did not capture.",
        "",
        "| Approach | Schema | Docs | Observed fields | Required coverage | Optional coverage |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        for schema_name, schema in result["schemas"].items():
            req = schema["required"]["coverage"]
            opt = schema["optional"]["coverage"]
            lines.append(
                "| {approach} | {schema_name} | {docs} | {fields} | {req} | {opt} |".format(
                    approach=result["approach"],
                    schema_name=schema_name,
                    docs=schema["document_count"],
                    fields=schema["field_count"],
                    req="" if req is None else f"{req:.2%}",
                    opt="" if opt is None else f"{opt:.2%}",
                )
            )

    lines.extend(["", "## Missing Required Fields", ""])
    for result in results:
        lines.append(f"### {result['approach']}")
        for schema_name, schema in result["schemas"].items():
            missing = schema["required"]["missing"]
            if missing:
                lines.append(f"- {schema_name}: {', '.join(missing)}")
            else:
                lines.append(f"- {schema_name}: none")
        lines.append("")

    lines.extend(["", "## Expected Catalog Coverage", ""])
    lines.append("| Approach | Schema | Present | Total | Coverage |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for result in results:
        for schema_name, schema in result["schemas"].items():
            catalog = schema.get("expected_catalog", {})
            cov = catalog.get("coverage")
            lines.append(
                f"| {result['approach']} | {schema_name} | "
                f"{len(catalog.get('present', []))} | {catalog.get('total', 0)} | "
                f"{'' if cov is None else f'{cov:.2%}'} |"
            )

    lines.extend(["", "## Coverage by Flowcept Schema Category", ""])
    lines.append("| Approach | Schema | Category | Present | Total | Coverage |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for result in results:
        for schema_name, schema in result["schemas"].items():
            for category_name, category in schema.get("categories", {}).items():
                cov = category["coverage"]
                lines.append(
                    f"| {result['approach']} | {schema_name} | {category_name} | "
                    f"{len(category['present'])} | {category['total']} | "
                    f"{'' if cov is None else f'{cov:.2%}'} |"
                )

    lines.extend(["", "## Observed Fields by Category", ""])
    for result in results:
        lines.append(f"### {result['approach']}")
        for schema_name, schema in result["schemas"].items():
            lines.append(f"#### {schema_name}")
            for category_name, category in schema.get("categories", {}).items():
                present = ", ".join(category["present"]) if category["present"] else "none"
                lines.append(f"- {category_name}: {present}")
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    defaults, _ = load_approaches()
    approaches = selected_approaches(args.approach)
    expectations = load_yaml(CONFIG_DIR / "schema_fields.yaml")

    results = [
        analyze_approach(name, approach, defaults, expectations)
        for name, approach in approaches.items()
        if approach.get("uses_flowcept", True)
    ]

    output_root = approach_results_dir("_analysis")
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "analysis_2_schema_coverage.json", results)
    write_markdown(output_root / "analysis_2_schema_coverage.md", results)
    print(f"Wrote {output_root / 'analysis_2_schema_coverage.md'}")


if __name__ == "__main__":
    main()
