from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bson import BSON

from experiment_utils import (
    RESULTS_DIR,
    approach_display_label,
    load_approaches,
    load_approach_labels,
    mongo_client,
    read_runs_csv,
    selected_approaches,
    use_case_display_label,
    utc_now_iso,
    write_json,
)


FLOWCEPT_COLLECTIONS = {
    "workflows": "workflow_bytes",
    "tasks": "task_bytes",
    "objects": "object_bytes",
    "agents": "agent_bytes",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize persisted MongoDB data volume for Flowcept approaches.")
    parser.add_argument("--approach", default="all", help="Approach name or 'all'.")
    parser.add_argument(
        "--use-case",
        help=(
            "Filter approaches by use case substring in the approach name, "
            "for example 'perceptron_gridsearch'."
        ),
    )
    parser.add_argument(
        "--runs",
        type=int,
        help="Override the run count used for mean-per-run.",
    )
    parser.add_argument(
        "--runs-source",
        choices=["root_workflow_count", "campaign_count", "runs_csv", "workflow_count", "manual"],
        default="root_workflow_count",
        help=(
            "How to infer run count when --runs is not provided. "
            "root_workflow_count counts workflow documents without parent_workflow_id and is the default because "
            "some approaches create multiple workflow documents per run."
        ),
    )
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        help="Include approaches with uses_flowcept=false. They normally report zero bytes.",
    )
    parser.add_argument(
        "--output-prefix",
        default="mongodb_data_volume_summary",
        help="Output filename prefix under experiments/results.",
    )
    return parser.parse_args()


def successful_run_count(approach_name: str) -> int:
    rows = read_runs_csv(approach_name)
    return sum(1 for row in rows if str(row.get("success", "")).lower() == "true")


def document_bson_size(document: dict[str, Any]) -> int:
    return len(BSON.encode(document))


def collection_bson_summary(db, collection_name: str) -> dict[str, int]:
    total_bytes = 0
    count = 0
    for document in db[collection_name].find({}):
        total_bytes += document_bson_size(document)
        count += 1
    return {"count": count, "bytes": total_bytes}


def infer_run_count(
    approach_name: str,
    db,
    run_count_override: int | None,
    runs_source: str,
) -> int:
    if run_count_override is not None:
        return run_count_override
    if runs_source == "manual":
        raise SystemExit("--runs is required when --runs-source manual is used.")
    if runs_source == "root_workflow_count":
        return db["workflows"].count_documents({"parent_workflow_id": {"$exists": False}})
    if runs_source == "campaign_count":
        campaign_ids = {
            campaign_id
            for collection_name in FLOWCEPT_COLLECTIONS
            for campaign_id in db[collection_name].distinct("campaign_id")
            if campaign_id
        }
        return len(campaign_ids)
    if runs_source == "workflow_count":
        return db["workflows"].count_documents({})
    return successful_run_count(approach_name)


def summarize_approach(
    approach_name: str,
    approach: dict[str, Any],
    defaults: dict[str, Any],
    labels: dict[str, Any],
    run_count_override: int | None,
    runs_source: str,
) -> dict[str, Any]:
    client = mongo_client(defaults, approach)
    db_name = approach["mongo_db"]
    db = client[db_name]

    run_count = infer_run_count(approach_name, db, run_count_override, runs_source)
    if run_count <= 0:
        run_count = 1

    row: dict[str, Any] = {
        "approach": approach_name,
        "approach_label": approach_display_label(approach_name, labels),
        "use_case_label": use_case_display_label(approach_name, labels),
        "mongo_db": db_name,
        "runs": run_count,
        "runs_source": "manual" if run_count_override is not None else runs_source,
    }

    total_bytes = 0
    total_documents = 0
    for collection_name, byte_key in FLOWCEPT_COLLECTIONS.items():
        summary = collection_bson_summary(db, collection_name)
        count_key = f"{collection_name}_count"
        mean_key = f"{byte_key}_mean_per_run"
        row[count_key] = summary["count"]
        row[f"{byte_key}_total"] = summary["bytes"]
        row[mean_key] = summary["bytes"] / run_count
        total_documents += summary["count"]
        total_bytes += summary["bytes"]

    row["total_flowcept_documents"] = total_documents
    row["total_flowcept_bytes_total"] = total_bytes
    row["total_flowcept_bytes_mean_per_run"] = total_bytes / run_count
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_bytes(value: Any) -> str:
    numeric = float(value or 0)
    units = ["B", "KB", "MB", "GB"]
    unit_index = 0
    while numeric >= 1024 and unit_index < len(units) - 1:
        numeric /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(numeric)} {units[unit_index]}"
    return f"{numeric:.2f} {units[unit_index]}"


def format_kb(value: Any) -> str:
    return f"{float(value or 0) / 1024:.2f}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    use_cases = sorted({str(row["use_case_label"]) for row in rows})
    run_sources = sorted({str(row["runs_source"]) for row in rows})
    lines = [
        "# MongoDB Data Volume Summary",
        "",
        f"Generated at: `{utc_now_iso()}`",
        "",
        "Data volume is measured as BSON-encoded MongoDB document size.",
        f"Use case: {', '.join(use_cases) if use_cases else 'n/a'}",
        f"Runs source: {', '.join(run_sources) if run_sources else 'n/a'}",
        "",
    ]

    overview_headers = [
        "Approach",
        "Runs",
        "Total Amount of Data (KB)",
        "Mean Amount of Data (KB)",
        "Workflow Docs",
        "Task Docs",
        "Agent Docs",
        "Object Docs",
        "Total Docs",
    ]
    overview_rows = []
    for row in rows:
        overview_rows.append(
            [
                row["approach_label"],
                str(row["runs"]),
                format_kb(row["total_flowcept_bytes_total"]),
                format_kb(row["total_flowcept_bytes_mean_per_run"]),
                str(row["workflows_count"]),
                str(row["tasks_count"]),
                str(row["agents_count"]),
                str(row["objects_count"]),
                str(row["total_flowcept_documents"]),
            ]
        )
    lines.append("## Overview")
    lines.append("")
    lines.append(markdown_table(overview_headers, overview_rows))
    lines.append("")

    collection_headers = [
        "Approach",
        "Workflow Total (KB)",
        "Workflow Mean / Run (KB)",
        "Task Total (KB)",
        "Task Mean / Run (KB)",
        "Agent Total (KB)",
        "Agent Mean / Run (KB)",
        "Object Total (KB)",
        "Object Mean / Run (KB)",
    ]
    collection_rows = []
    for row in rows:
        collection_rows.append(
            [
                row["approach_label"],
                format_kb(row["workflow_bytes_total"]),
                format_kb(row["workflow_bytes_mean_per_run"]),
                format_kb(row["task_bytes_total"]),
                format_kb(row["task_bytes_mean_per_run"]),
                format_kb(row["agent_bytes_total"]),
                format_kb(row["agent_bytes_mean_per_run"]),
                format_kb(row["object_bytes_total"]),
                format_kb(row["object_bytes_mean_per_run"]),
            ]
        )
    lines.append("## By Collection")
    lines.append("")
    lines.append(markdown_table(collection_headers, collection_rows))
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    defaults, all_approaches = load_approaches()
    labels = load_approach_labels()
    approaches = all_approaches if args.approach == "all" else selected_approaches(args.approach)
    if args.use_case:
        approaches = {
            name: approach
            for name, approach in approaches.items()
            if args.use_case in name
        }
    rows = []
    for approach_name, approach in approaches.items():
        if not args.include_baseline and not approach.get("uses_flowcept", True):
            continue
        rows.append(summarize_approach(approach_name, approach, defaults, labels, args.runs, args.runs_source))

    output_csv = RESULTS_DIR / f"{args.output_prefix}.csv"
    output_json = RESULTS_DIR / f"{args.output_prefix}.json"
    output_md = RESULTS_DIR / f"{args.output_prefix}.md"
    write_csv(output_csv, rows)
    write_markdown(output_md, rows)
    write_json(
        output_json,
        {
            "generated_at": utc_now_iso(),
            "approach": args.approach,
            "use_case": args.use_case,
            "runs_source": args.runs_source,
            "rows": rows,
        },
    )

    print(f"Wrote {output_csv}")
    print(f"Wrote {output_md}")
    print(f"Wrote {output_json}")
    for row in rows:
        print(
            f"{row['approach']}: runs={row['runs']} "
            f"total={row['total_flowcept_bytes_total']} bytes "
            f"mean/run={row['total_flowcept_bytes_mean_per_run']:.2f} bytes"
        )


if __name__ == "__main__":
    main()
