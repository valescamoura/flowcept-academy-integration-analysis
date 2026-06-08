from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from experiment_utils import (
    CONFIG_DIR,
    REPO_ROOT,
    approach_results_dir,
    load_approaches,
    load_yaml,
    make_flowcept_settings,
    merged_env,
    read_runs_csv,
    resolve_python,
    selected_approaches,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze schema coverage through the Flowcept Python DB API.")
    parser.add_argument("--approach", required=True, help="Approach name or 'all'.")
    parser.add_argument(
        "--use-case",
        default=None,
        help="Use case key for domain-specific analytical category indicators.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Timeout for each Flowcept query worker.",
    )
    return parser.parse_args()


def worker_code() -> str:
    return r'''
import json
import os
from pathlib import Path
from typing import Any

import yaml
from flowcept import Flowcept


def flatten_keys(document: dict[str, Any], prefix: str = "") -> set[str]:
    keys = set()
    for key, value in document.items():
        if key == "_id":
            continue
        path = f"{prefix}.{key}" if prefix else str(key)
        keys.add(path)
        if isinstance(value, dict):
            keys.update(flatten_keys(value, path))
    return keys


def docs_field_inventory(docs):
    counts = {}
    for doc in docs:
        for key in flatten_keys(doc):
            counts[key] = counts.get(key, 0) + 1
    total = len(docs)
    return {
        "document_count": total,
        "fields": {
            key: {"count": count, "presence": (count / total if total else 0.0)}
            for key, count in sorted(counts.items())
        },
    }


def has_field(inventory, field):
    return field in inventory.get("fields", {})


def nested_values(document, path):
    current = document
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return []
    return [current]


def iter_content(value, prefix):
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            yield key_path, key
            yield from iter_content(item, key_path)
    elif isinstance(value, list | tuple | set):
        for index, item in enumerate(value):
            item_path = f"{prefix}[{index}]"
            yield from iter_content(item, item_path)
    else:
        yield prefix, value


def content_indicator_evidence(docs, field_path, indicator):
    schema_name, _, local_path = field_path.partition(".")
    matches = []
    indicator_text = str(indicator).lower()
    for doc in docs.get(schema_name, []):
        for value in nested_values(doc, local_path):
            for value_path, value_part in iter_content(value, field_path):
                if indicator_text in str(value_part).lower():
                    matches.append(value_path)
    return sorted(set(matches))


def field_observed(schemas, field_path):
    schema_name, _, local_path = field_path.partition(".")
    schema = schemas.get(schema_name)
    if not schema:
        return False
    return local_path in schema.get("field_presence", {})


def expand_analytical_fields(expectations, analytical_config, use_case):
    fields_by_category = {name: {} for name in analytical_config.get("categories", {})}
    schema_category_mapping = analytical_config.get("schema_category_mapping", {})
    field_category_mapping = analytical_config.get("field_category_mapping", {})
    use_case_cfg = analytical_config.get("use_cases", {}).get(use_case, {})
    domain_indicators = use_case_cfg.get("domain_content_indicators", {})

    for schema_name, schema_expectations in expectations.items():
        category_mappings = schema_category_mapping.get(schema_name, {})
        for schema_category, fields in schema_expectations.get("categories", {}).items():
            for field in fields:
                path = f"{schema_name}.{field}"
                analytical_categories = field_category_mapping.get(
                    path,
                    category_mappings.get(schema_category, []),
                )
                for analytical_category in analytical_categories:
                    if analytical_category not in fields_by_category:
                        continue
                    indicators = (
                        domain_indicators.get(path, [])
                        if analytical_category == "domain_information"
                        else []
                    )
                    fields_by_category[analytical_category][path] = {
                        "path": path,
                        "source_schema": schema_name,
                        "source_schema_category": schema_category,
                        "content_indicators": indicators,
                    }

    for category_name, category in analytical_config.get("categories", {}).items():
        for field in category.get("fields", []):
            if isinstance(field, str):
                path = field
                field_spec = {"path": path, "content_indicators": []}
            else:
                path = field.get("path")
                field_spec = dict(field)
            if path:
                fields_by_category[category_name][path] = field_spec

    return {
        category_name: sorted(fields.values(), key=lambda field: field["path"])
        for category_name, fields in fields_by_category.items()
    }


def analytical_category_coverage(schemas, docs, expectations, analytical_config, use_case):
    categories = analytical_config.get("categories", {})
    fields_by_category = expand_analytical_fields(expectations, analytical_config, use_case)
    output = {}
    for category_name, category in categories.items():
        fields = fields_by_category.get(category_name, [])
        expected_items = []
        observed_items = []
        observed_fields = []
        source_schema_categories = {}
        evidence = []
        missing_items = []
        for field in fields:
            if isinstance(field, str):
                path = field
                indicators = []
            else:
                path = field.get("path")
                indicators = field.get("content_indicators") or []
            if not path:
                continue

            present = field_observed(schemas, path)
            if present:
                observed_fields.append(path)
            source_schema_category = field.get("source_schema_category")
            source_schema = field.get("source_schema")
            if source_schema and source_schema_category:
                source_key = f"{source_schema}.{source_schema_category}"
                source_schema_categories.setdefault(source_key, {"total": 0, "observed": 0})
                source_schema_categories[source_key]["total"] += 1
                if present:
                    source_schema_categories[source_key]["observed"] += 1

            if indicators:
                for indicator in indicators:
                    item = f"{path} contains {indicator}"
                    expected_items.append(item)
                    paths = content_indicator_evidence(docs, path, indicator)
                    if paths:
                        observed_items.append(item)
                        evidence.append(
                            {
                                "field": path,
                                "indicator": indicator,
                                "paths": paths,
                            }
                        )
                    else:
                        missing_items.append(item)
            else:
                expected_items.append(path)
                if present:
                    observed_items.append(path)
                    evidence.append({"field": path, "indicator": None, "paths": [path]})
                else:
                    missing_items.append(path)

        output[category_name] = {
            "label": category.get("label", category_name),
            "question": category.get("question", ""),
            "expected_total": len(expected_items),
            "observed_total": len(observed_items),
            "coverage": len(observed_items) / len(expected_items) if expected_items else None,
            "observed_fields": sorted(set(observed_fields)),
            "observed_items": observed_items,
            "missing_items": missing_items,
            "source_schema_categories": source_schema_categories,
            "evidence": evidence,
        }
    return output


def coverage_for_schema(inventory, expectations):
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


expectations = yaml.safe_load(Path(os.environ["SCHEMA_FIELDS_PATH"]).read_text())
analytical_config = yaml.safe_load(Path(os.environ["ANALYTICAL_CATEGORIES_PATH"]).read_text())
use_case = os.environ["EXPERIMENT_USE_CASE"]

workflows = Flowcept.db.workflow_query({})
tasks = Flowcept.db.task_query({})
objects = Flowcept.db.blob_object_query({})
docs = {
    "workflow": workflows or [],
    "task": tasks or [],
    "object": objects or [],
}
schemas = {
    "workflow": coverage_for_schema(docs_field_inventory(docs["workflow"]), expectations.get("workflow", {})),
    "task": coverage_for_schema(docs_field_inventory(docs["task"]), expectations.get("task", {})),
    "object": coverage_for_schema(docs_field_inventory(docs["object"]), expectations.get("object", {})),
}

result = {
    "approach": os.environ["EXPERIMENT_APPROACH"],
    "mongo_db": os.environ["EXPERIMENT_MONGO_DB"],
    "query_backend": "flowcept.db",
    "use_case": use_case,
    "schemas": schemas,
    "analytical_categories": analytical_category_coverage(
        schemas,
        docs,
        expectations,
        analytical_config,
        use_case,
    ),
}
print(json.dumps(result, default=str))
'''


def run_flowcept_worker(
    name: str,
    approach: dict[str, Any],
    defaults: dict[str, Any],
    use_case: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    settings_path = make_flowcept_settings(name, defaults, approach)
    command = resolve_python(["{python}", "-c", worker_code()], defaults, approach)
    env = merged_env(
        os.environ,
        approach,
        {
            "FLOWCEPT_SETTINGS_PATH": str(settings_path),
            "SCHEMA_FIELDS_PATH": str(CONFIG_DIR / "schema_fields.yaml"),
            "ANALYTICAL_CATEGORIES_PATH": str(CONFIG_DIR / "analytical_categories.yaml"),
            "EXPERIMENT_APPROACH": name,
            "EXPERIMENT_MONGO_DB": approach["mongo_db"],
            "EXPERIMENT_USE_CASE": use_case,
        },
        defaults,
    )

    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Flowcept schema worker timed out for {name} after {timeout_seconds}s"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"Flowcept schema worker failed for {name}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    result = json.loads(proc.stdout)
    runs = read_runs_csv(name)
    successful_runs = [run for run in runs if str(run.get("success", "")).lower() == "true"]
    result["run_summary"] = {
        "recorded_runs": len(runs),
        "successful_runs": len(successful_runs),
    }
    return result


def write_markdown(path: Path, results: list[dict[str, Any]]) -> None:
    def format_coverage(value: float | None) -> str:
        return "" if value is None else f"{value:.2%}"

    use_case = results[0].get("use_case", "") if results else ""
    lines = [
        "# Analysis 2: Schema and Analytical Category Coverage",
        "",
        "Query backend: `Flowcept.db`",
        f"Use case: `{use_case}`" if use_case else "",
        "",
        "This analysis has two levels. First, it compares observed records against the Flowcept `workflow`, `task`, and `object` schemas. Second, it maps observed fields and use-case-specific content indicators into three analytical categories: Provenance Information, Domain Information, and Telemetry Information.",
        "",
        "## Document Counts",
        "",
        "Counts are totals currently stored in the approach Mongo database for all recorded runs. Per-run averages are computed as `total documents / recorded runs` from the approach `runs.csv`.",
        "",
        "| Approach | Recorded runs | Successful runs | Workflow docs total | Workflow docs/run | Task docs total | Task docs/run | Object docs total | Object docs/run |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        schemas = result["schemas"]
        run_summary = result.get("run_summary", {})
        recorded_runs = int(run_summary.get("recorded_runs") or 0)
        successful_runs = int(run_summary.get("successful_runs") or 0)
        workflow_docs = schemas["workflow"]["document_count"]
        task_docs = schemas["task"]["document_count"]
        object_docs = schemas["object"]["document_count"]

        def docs_per_run(count: int) -> str:
            return "" if recorded_runs == 0 else f"{count / recorded_runs:.2f}"

        lines.append(
            f"| {result['approach']} | "
            f"{recorded_runs} | "
            f"{successful_runs} | "
            f"{workflow_docs} | "
            f"{docs_per_run(workflow_docs)} | "
            f"{task_docs} | "
            f"{docs_per_run(task_docs)} | "
            f"{object_docs} | "
            f"{docs_per_run(object_docs)} |"
        )

    lines.extend(
        [
            "",
            "## Flowcept Expected Catalog Coverage",
            "",
            "The expected catalog is the union of the `required` and `optional` fields configured for each Flowcept schema. Coverage is based on field presence at least once in the documents for that approach.",
            "",
            "| Approach | Schema | Required present | Required total | Required coverage | Optional present | Optional total | Optional coverage | Expected present | Expected total | Expected coverage | Distinct observed fields |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        for schema_name, schema in result["schemas"].items():
            req = schema["required"]
            opt = schema["optional"]
            catalog = schema["expected_catalog"]
            req_cov = format_coverage(req["coverage"])
            opt_cov = format_coverage(opt["coverage"])
            catalog_cov = format_coverage(catalog["coverage"])
            lines.append(
                f"| {result['approach']} | {schema_name} | "
                f"{len(req['present'])} | {req['total']} | {req_cov} | "
                f"{len(opt['present'])} | {opt['total']} | {opt_cov} | "
                f"{len(catalog['present'])} | {catalog['total']} | {catalog_cov} | "
                f"{schema['field_count']} |"
            )

    lines.extend(["", "## Missing Required and Optional Fields", ""])
    for result in results:
        lines.append(f"### {result['approach']}")
        for schema_name, schema in result["schemas"].items():
            missing_required = schema["required"]["missing"]
            missing_optional = schema["optional"]["missing"]
            lines.append(f"#### {schema_name}")
            lines.append(
                "- Missing required: "
                + (", ".join(missing_required) if missing_required else "none")
            )
            lines.append(
                "- Missing optional: "
                + (", ".join(missing_optional) if missing_optional else "none")
            )
        lines.append("")

    lines.extend(["", "## Flowcept Coverage by Schema Category", ""])
    lines.append("| Approach | Schema | Category | Present | Total | Coverage |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for result in results:
        for schema_name, schema in result["schemas"].items():
            for category_name, category in schema.get("categories", {}).items():
                cov = format_coverage(category["coverage"])
                lines.append(
                    f"| {result['approach']} | {schema_name} | {category_name} | "
                    f"{len(category['present'])} | {category['total']} | "
                    f"{cov} |"
                )

    lines.extend(["", "## Observed Fields by Flowcept Category", ""])
    for result in results:
        lines.append(f"### {result['approach']}")
        for schema_name, schema in result["schemas"].items():
            lines.append(f"#### {schema_name}")
            for category_name, category in schema.get("categories", {}).items():
                present = ", ".join(category["present"]) if category["present"] else "none"
                lines.append(f"- {category_name}: {present}")
        lines.append("")

    lines.extend(
        [
            "",
            "## Analytical Category Coverage",
            "",
            "For fields without content indicators, one expected item is counted for the field itself. For fields with content indicators, each expected indicator counts as one item. This lets Domain Information be evaluated against use-case-specific content, not just generic field presence.",
            "",
            "| Approach | Analytical Category | Expected Items | Observed Items | Coverage |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        for category in result.get("analytical_categories", {}).values():
            cov = format_coverage(category["coverage"])
            lines.append(
                f"| {result['approach']} | {category['label']} | "
                f"{category['expected_total']} | {category['observed_total']} | "
                f"{cov} |"
            )

    lines.extend(["", "## Analytical Category Evidence", ""])
    for result in results:
        lines.append(f"### {result['approach']}")
        for category_name, category in result.get("analytical_categories", {}).items():
            lines.append(f"#### {category['label']}")
            question = category.get("question")
            if question:
                lines.append(f"- Question: {question}")
            fields = category.get("observed_fields", [])
            lines.append(
                "- Observed mapped fields: "
                + (", ".join(fields) if fields else "none")
            )
            evidence = category.get("evidence", [])
            if evidence:
                lines.append("- Observed evidence:")
                for item in evidence:
                    indicator = item.get("indicator")
                    paths = item.get("paths") or []
                    if indicator is None:
                        lines.append(f"  - {item['field']}")
                    else:
                        preview = ", ".join(paths[:5])
                        suffix = "" if len(paths) <= 5 else f" (+{len(paths) - 5} more)"
                        lines.append(
                            f"  - {item['field']} contains `{indicator}`: {preview}{suffix}"
                        )
            else:
                lines.append("- Observed evidence: none")
            missing = category.get("missing_items", [])
            lines.append(
                "- Missing expected items: "
                + (", ".join(missing) if missing else "none")
            )
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    defaults, _ = load_approaches()
    approaches = selected_approaches(args.approach)
    analytical_config = load_yaml(CONFIG_DIR / "analytical_categories.yaml")
    use_case = args.use_case or analytical_config.get("default_use_case", "fibonacci")
    results = [
        run_flowcept_worker(name, approach, defaults, use_case, args.timeout_seconds)
        for name, approach in approaches.items()
        if approach.get("uses_flowcept", True)
    ]

    output_root = approach_results_dir("_analysis")
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "analysis_2_schema_coverage_flowcept.json", results)
    write_markdown(output_root / "analysis_2_schema_coverage_flowcept.md", results)
    print(f"Wrote {output_root / 'analysis_2_schema_coverage_flowcept.md'}")


if __name__ == "__main__":
    main()
