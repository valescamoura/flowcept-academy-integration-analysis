from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from experiment_utils import (
    CONFIG_DIR,
    RESULTS_DIR,
    approach_display_label,
    docs_field_inventory,
    load_approaches,
    load_approach_labels,
    load_yaml,
    mongo_client,
    read_runs_csv,
    save_yaml,
    use_case_display_label,
    utc_now_iso,
    write_json,
)


SOURCE_ANALYSIS_PATH = CONFIG_DIR / "mapping.md"
DEFAULT_MAPPING_PATH = CONFIG_DIR / "coverage_mapping.yaml"
COLLECTION_PREFIXES = {
    "workflows": "workflow",
    "tasks": "task",
    "objects": "object",
    "agents": "agent",
}

ERROR_STATUSES = {"ERROR", "FAILED", "FAILURE", "EXCEPTION"}
SUBTYPE_PSEUDO_FIELDS = {
    "agent_communication": "task.record_type.subtype.agent_communication",
    "academy_lifecycle": "task.record_type.subtype.academy_lifecycle",
}


FIELD_ALIASES = {
    "workflow.type": "workflow.record_type.type",
    "workflow.workflow_id": "workflow.identifiers.workflow_id",
    "workflow.parent_workflow_id": "workflow.identifiers.parent_workflow_id",
    "workflow.campaign_id": "workflow.identifiers.campaign_id",
    "workflow.adapter_id": "workflow.identifiers.adapter_id",
    "workflow.interceptor_ids": "workflow.identifiers.interceptor_ids",
    "workflow.agent_id": "workflow.identifiers.agent_id",
    "workflow.name": "workflow.user_facing_metadata.name",
    "workflow.workflow_description": "workflow.user_facing_metadata.workflow_description",
    "workflow.subtype": "workflow.user_facing_metadata.subtype",
    "workflow.custom_metadata": "workflow.user_facing_metadata.custom_metadata",
    "workflow.used": "workflow.inputs_outputs_repository.used",
    "workflow.generated": "workflow.inputs_outputs_repository.generated",
    "workflow.code_repository": "workflow.inputs_outputs_repository.code_repository",
    "workflow.machine_info": "workflow.runtime_context.machine_info",
    "workflow.conf": "workflow.runtime_context.conf",
    "workflow.flowcept_settings": "workflow.runtime_context.flowcept_settings",
    "workflow.flowcept_version": "workflow.runtime_context.flowcept_version",
    "workflow.utc_timestamp": "workflow.runtime_context.utc_timestamp",
    "workflow.user": "workflow.runtime_context.user",
    "workflow.environment_id": "workflow.runtime_context.environment_id",
    "workflow.sys_name": "workflow.runtime_context.sys_name",
    "workflow.extra_metadata": "workflow.runtime_context.extra_metadata",
    "task.type": "task.record_type.type",
    "task.subtype": "task.record_type.subtype",
    "task.task_id": "task.identifiers.task_id",
    "task.workflow_id": "task.identifiers.workflow_id",
    "task.workflow_name": "task.identifiers.workflow_name",
    "task.campaign_id": "task.identifiers.campaign_id",
    "task.activity_id": "task.identifiers.activity_id",
    "task.group_id": "task.identifiers.group_id",
    "task.parent_task_id": "task.identifiers.parent_task_id",
    "task.agent_id": "task.identifiers.agent_id",
    "task.source_agent_id": "task.identifiers.source_agent_id",
    "task.adapter_id": "task.identifiers.adapter_id",
    "task.environment_id": "task.identifiers.environment_id",
    "task.utc_timestamp": "task.timing.utc_timestamp",
    "task.submitted_at": "task.timing.submitted_at",
    "task.started_at": "task.timing.started_at",
    "task.ended_at": "task.timing.ended_at",
    "task.registered_at": "task.timing.registered_at",
    "task.used": "task.provenance_data.used",
    "task.generated": "task.provenance_data.generated",
    "task.dependencies": "task.provenance_data.dependencies",
    "task.dependents": "task.provenance_data.dependents",
    "task.status": "task.execution_metadata.status",
    "task.stdout": "task.execution_metadata.stdout",
    "task.stderr": "task.execution_metadata.stderr",
    "task.data": "task.execution_metadata.data",
    "task.custom_metadata": "task.execution_metadata.custom_metadata",
    "task.tags": "task.execution_metadata.tags",
    "task.user": "task.user_and_system_context.user",
    "task.login_name": "task.user_and_system_context.login_name",
    "task.node_name": "task.user_and_system_context.node_name",
    "task.hostname": "task.user_and_system_context.hostname",
    "task.public_ip": "task.user_and_system_context.public_ip",
    "task.private_ip": "task.user_and_system_context.private_ip",
    "task.address": "task.user_and_system_context.address",
    "task.mq_host": "task.user_and_system_context.mq_host",
    "task.telemetry_at_start.cpu": "task.telemetry_data.telemetry_at_start.cpu",
    "task.telemetry_at_start.process": "task.telemetry_data.telemetry_at_start.process",
    "task.telemetry_at_start.memory": "task.telemetry_data.telemetry_at_start.memory",
    "task.telemetry_at_start.disk": "task.telemetry_data.telemetry_at_start.disk",
    "task.telemetry_at_start.network": "task.telemetry_data.telemetry_at_start.network",
    "task.telemetry_at_start.gpu": "task.telemetry_data.telemetry_at_start.gpu",
    "task.telemetry_at_end.cpu": "task.telemetry_data.telemetry_at_end.cpu",
    "task.telemetry_at_end.process": "task.telemetry_data.telemetry_at_end.process",
    "task.telemetry_at_end.memory": "task.telemetry_data.telemetry_at_end.memory",
    "task.telemetry_at_end.disk": "task.telemetry_data.telemetry_at_end.disk",
    "task.telemetry_at_end.network": "task.telemetry_data.telemetry_at_end.network",
    "task.telemetry_at_end.gpu": "task.telemetry_data.telemetry_at_end.gpu",
    "agent.type": "agent.record_type.type",
    "agent.agent_id": "agent.identifiers.agent_id",
    "agent.workflow_id": "agent.identifiers.workflow_id",
    "agent.campaign_id": "agent.identifiers.campaign_id",
    "agent.name": "agent.user_facing_metadata.name",
    "agent.custom_metadata": "agent.user_facing_metadata.custom_metadata",
    "agent.registered_at": "agent.timing.registered_at",
    "agent.user": "agent.runtime_context.user",
}


AGENT_FIELD_MAPPING = {
    "agent.record_type.type": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agent-responsibility"],
        "kpis": ["agent object coverage"],
        "personas": ["AI Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.identifiers.agent_id": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agent-responsibility"],
        "kpis": ["participating agent count", "agent coverage"],
        "personas": ["AI Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.identifiers.workflow_id": {
        "provenance_data_categories": ["agentic", "workflow-control"],
        "analytical_capabilities": ["agent-responsibility", "execution-traceability"],
        "kpis": ["agents per workflow", "agent coverage"],
        "personas": ["AI Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.identifiers.campaign_id": {
        "provenance_data_categories": ["agentic", "workflow-control"],
        "analytical_capabilities": ["agent-responsibility", "reproducibility-analysis"],
        "kpis": ["agents per campaign", "comparable run count"],
        "personas": ["AI Engineer", "Domain Specialist"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.user_facing_metadata.name": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agent-responsibility"],
        "kpis": ["named agent coverage", "participating agent count"],
        "personas": ["AI Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.user_facing_metadata.custom_metadata": {
        "provenance_data_categories": ["agentic"],
        "analytical_capabilities": ["agent-responsibility", "agent-interaction"],
        "kpis": ["agent metadata coverage", "agent context coverage"],
        "personas": ["AI Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.timing.registered_at": {
        "provenance_data_categories": ["agentic", "telemetry"],
        "analytical_capabilities": ["agent-responsibility", "execution-time-analysis"],
        "kpis": ["agent registration coverage", "agent registration time"],
        "personas": ["AI Engineer", "Platform Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
    "agent.runtime_context.user": {
        "provenance_data_categories": ["agentic", "telemetry"],
        "analytical_capabilities": ["agent-responsibility", "platform-context-analysis"],
        "kpis": ["agents per user", "user attribution coverage"],
        "personas": ["AI Engineer", "Platform Engineer"],
        "questions": ["Which agents participated in this execution?"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze unique observed field coverage by approach.")
    parser.add_argument("--approach", default="all", help="Approach name or 'all'.")
    parser.add_argument("--use-case", help="Filter approaches by use case suffix, for example perceptron_gridsearch.")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING_PATH), help="Editable YAML mapping path.")
    parser.add_argument("--source-analysis", default=str(SOURCE_ANALYSIS_PATH), help="fields_analysis_v2.md path.")
    parser.add_argument("--init-mapping", action="store_true", help="Create the editable mapping YAML from the markdown analysis.")
    parser.add_argument(
        "--force-init-mapping",
        action="store_true",
        help="Allow --init-mapping to overwrite an existing mapping YAML.",
    )
    parser.add_argument("--output-prefix", default="field_coverage", help="Output filename prefix under experiments/results/_analysis.")
    return parser.parse_args()


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_markdown_tables(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    lines = path.read_text().splitlines()
    questions: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    in_questions = False
    in_fields = False

    for line in lines:
        if line.startswith("| Persona | Question | Required Fields |"):
            in_questions = True
            in_fields = False
            continue
        if line.startswith("### Ignored fields"):
            in_questions = False
            continue
        if line.startswith("| Field | Provenance Data Category |"):
            in_fields = True
            in_questions = False
            continue
        if not line.startswith("|") or line.startswith("|---") or line.startswith("|----------"):
            continue

        cells = split_table_row(line)
        if in_questions and len(cells) == 6:
            persona, question, required, categories, capabilities, kpis = cells
            questions[question] = {
                "persona": persona,
                "required_fields": comma_list(required),
                "provenance_data_categories": comma_list(categories),
                "analytical_capabilities": comma_list(capabilities),
                "kpis": semicolon_list(kpis),
            }
        elif in_fields and len(cells) == 6:
            field, categories, capabilities, kpis, personas, question = cells
            fields[field] = {
                "provenance_data_categories": comma_list(categories),
                "analytical_capabilities": comma_list(capabilities),
                "kpis": semicolon_list(kpis),
                "personas": comma_list(personas),
                "questions": [question],
            }

    fields.update(AGENT_FIELD_MAPPING)
    return questions, fields


def comma_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def semicolon_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def write_initial_mapping(mapping_path: Path, source_analysis_path: Path) -> dict[str, Any]:
    questions, fields = parse_markdown_tables(source_analysis_path)
    payload = {
        "generated_from": str(source_analysis_path),
        "generated_at": utc_now_iso(),
        "notes": [
            "Editable mapping used by analyze_field_coverage.py.",
            "Observed custom fields not listed here are reported in unmapped_fields CSV for review.",
            "Counts are based on unique field presence per approach, not per-document frequency.",
        ],
        "provenance_data_categories": ["domain-dataflow", "workflow-control", "telemetry", "agentic"],
        "analytical_capabilities": [
            "dataflow-provenance",
            "execution-traceability",
            "reproducibility-analysis",
            "execution-time-analysis",
            "resource-analysis",
            "failure-analysis",
            "platform-context-analysis",
            "agent-responsibility",
            "agent-interaction",
            "ai-model-usage",
        ],
        "questions": questions,
        "fields": fields,
        "custom_fields": {},
    }
    save_yaml(mapping_path, payload)
    return payload


def write_custom_candidate_mapping(path: Path, rows: list[dict[str, Any]]) -> None:
    candidates: dict[str, Any] = {}
    for row in rows:
        field = row["field"]
        entry = candidates.setdefault(
            field,
            {
                "status": "review",
                "promote_to_mapping": False,
                "provenance_data_categories": [],
                "analytical_capabilities": [],
                "kpis": [],
                "personas": [],
                "questions": [],
                "covered_by_parent": row.get("covered_by_parent") or "",
                "observed_in_approaches": [],
                "raw_examples": [],
            },
        )
        approach_label = row.get("approach_label") or row.get("approach")
        if approach_label and approach_label not in entry["observed_in_approaches"]:
            entry["observed_in_approaches"].append(approach_label)
        for raw_example in str(row.get("raw_examples", "")).split("; "):
            if raw_example and raw_example not in entry["raw_examples"]:
                entry["raw_examples"].append(raw_example)

    for entry in candidates.values():
        entry["observed_in_approaches"] = sorted(entry["observed_in_approaches"])
        entry["raw_examples"] = sorted(entry["raw_examples"])[:10]

    payload = {
        "generated_at": utc_now_iso(),
        "notes": [
            "Review-only YAML for custom/nested observed fields.",
            "Review-only file. The maintained mapping source is experiments/config/mapping.md.",
            "Regenerate experiments/config/coverage_mapping.yaml with build_coverage_mapping.py after editing the official table.",
        ],
        "custom_field_candidates": dict(sorted(candidates.items())),
    }
    save_yaml(path, payload)


def infer_custom_field_mapping(field: str) -> dict[str, Any]:
    lowered = field.lower()
    categories: set[str] = set()
    capabilities: set[str] = set()
    kpis: set[str] = set()
    personas: set[str] = set()
    questions: set[str] = set()
    confidence = "review"

    def add(
        cats: list[str],
        caps: list[str],
        metrics: list[str],
        people: list[str],
        qs: list[str],
        level: str = "suggested",
    ) -> None:
        nonlocal confidence
        categories.update(cats)
        capabilities.update(caps)
        kpis.update(metrics)
        personas.update(people)
        questions.update(qs)
        if confidence == "review" or level == "high":
            confidence = level

    if any(token in lowered for token in ["agent", "source_agent", "target_agent", "delegat"]):
        add(
            ["agentic"],
            ["agent-responsibility", "agent-interaction"],
            ["agent coverage", "delegation count", "cross-agent handoff count"],
            ["AI Engineer"],
            ["Which agents participated in this execution?", "How was work delegated across agents?"],
            "high",
        )
    if any(token in lowered for token in ["message", "msg", "label", "tag", "request", "response"]):
        add(
            ["agentic"],
            ["agent-interaction"],
            ["message count", "interaction frequency", "message payload coverage"],
            ["AI Engineer"],
            ["What messages were exchanged between agents, and how did interactions evolve over time?"],
            "high",
        )
    if any(token in lowered for token in ["action", "activity"]):
        add(
            ["workflow-control", "agentic"],
            ["execution-traceability", "agent-responsibility"],
            ["activity frequency", "actions per agent", "trace completeness"],
            ["AI Engineer", "Domain Specialist"],
            ["Which agent invoked each action and produced each output?", "Which sequence of workflow activities led to this result?"],
        )
    if any(token in lowered for token in ["dataset", "config", "parameter", "learning_rate", "epochs", "n_input", "split_ratio", "samples"]):
        add(
            ["domain-dataflow"],
            ["dataflow-provenance", "reproducibility-analysis"],
            ["input parameter completeness", "configuration ranking", "comparable run count"],
            ["Domain Specialist"],
            ["What inputs, parameters, and code version were used to produce this result?", "Which parameter configuration produced the best result?"],
            "high",
        )
    if any(token in lowered for token in ["loss", "accuracy", "metric", "best", "result", "score"]):
        add(
            ["domain-dataflow"],
            ["dataflow-provenance"],
            ["best metric value", "output variance", "successful configuration rate"],
            ["Domain Specialist"],
            ["Which parameter configuration produced the best result?", "How did changes in inputs or parameters affect the final outputs across executions?"],
            "high",
        )
    if any(token in lowered for token in ["model", "artifact", "checkpoint"]):
        add(
            ["domain-dataflow"],
            ["dataflow-provenance", "reproducibility-analysis"],
            ["output artifact count", "code/model artifact coverage", "reproducibility metadata coverage"],
            ["Domain Specialist", "AI Engineer"],
            ["What outputs and intermediate results were generated throughout the workflow?", "Which agent invoked each action and produced each output?"],
        )
    if any(token in lowered for token in ["pid", "process", "runtime", "host", "node", "environment", "platform", "cpu", "memory", "disk", "network", "gpu"]):
        add(
            ["telemetry"],
            ["resource-analysis", "platform-context-analysis"],
            ["runtime context coverage", "resource variance by host", "process-level resource usage"],
            ["Platform Engineer"],
            ["Did resource usage vary across nodes, hosts, or runtime environments?", "Which tasks consumed the most CPU, memory, disk, network, or GPU resources?"],
        )
    if any(token in lowered for token in ["openinference", "span", "trace", "parent", "chain", "workflow"]):
        add(
            ["workflow-control", "telemetry"],
            ["execution-traceability", "execution-time-analysis"],
            ["trace completeness", "workflow hierarchy depth", "critical path length"],
            ["Platform Engineer", "AI Engineer", "Domain Specialist"],
            ["Which sequence of workflow activities led to this result?", "How long did each task and workflow take to execute?"],
        )
    if any(token in lowered for token in ["error", "exception", "failed", "failure", "stderr", "status"]):
        add(
            ["telemetry"],
            ["failure-analysis"],
            ["failure count", "failure rate", "error message coverage"],
            ["Platform Engineer", "AI Engineer"],
            ["Which tasks failed, and what error messages were produced?", "Which agent was responsible for a failure?"],
            "high",
        )
    if any(token in lowered for token in ["stdout", "stderr", "log"]):
        add(
            ["telemetry"],
            ["failure-analysis"],
            ["diagnostic output coverage", "failure evidence coverage"],
            ["Platform Engineer"],
            ["Which tasks failed, and what error messages were produced?"],
        )
    if "academy" in lowered or "framework" in lowered:
        add(
            ["agentic", "workflow-control"],
            ["agent-responsibility", "execution-traceability"],
            ["framework metadata coverage", "agent context coverage"],
            ["AI Engineer"],
            ["Which agents participated in this execution?"],
        )
    if any(token in lowered for token in ["flowcept", "adapter", "capture_method", "source"]):
        add(
            ["workflow-control"],
            ["execution-traceability"],
            ["capture method coverage", "adapter coverage"],
            ["Platform Engineer", "AI Engineer"],
            ["Which sequence of workflow activities led to this result?"],
        )

    return {
        "status": confidence,
        "promote_to_mapping": confidence == "high",
        "provenance_data_categories": sorted(categories),
        "analytical_capabilities": sorted(capabilities),
        "kpis": sorted(kpis),
        "personas": sorted(personas),
        "questions": sorted(questions),
    }


def write_suggested_custom_mapping(path: Path, rows: list[dict[str, Any]]) -> None:
    candidates: dict[str, Any] = {}
    for row in rows:
        field = row["field"]
        entry = candidates.setdefault(
            field,
            {
                **infer_custom_field_mapping(field),
                "covered_by_parent": row.get("covered_by_parent") or "",
                "observed_in_approaches": [],
                "raw_examples": [],
            },
        )
        approach_label = row.get("approach_label") or row.get("approach")
        if approach_label and approach_label not in entry["observed_in_approaches"]:
            entry["observed_in_approaches"].append(approach_label)
        for raw_example in str(row.get("raw_examples", "")).split("; "):
            if raw_example and raw_example not in entry["raw_examples"]:
                entry["raw_examples"].append(raw_example)

    for entry in candidates.values():
        entry["observed_in_approaches"] = sorted(entry["observed_in_approaches"])
        entry["raw_examples"] = sorted(entry["raw_examples"])[:10]

    payload = {
        "generated_at": utc_now_iso(),
        "notes": [
            "Suggested YAML for custom/nested observed fields.",
            "Suggestions are heuristic. The maintained mapping source is experiments/config/mapping.md.",
            "promote_to_mapping true means the heuristic had relatively high confidence.",
        ],
        "custom_fields": dict(sorted(candidates.items())),
    }
    save_yaml(path, payload)


def selected_approaches_for_analysis(approach_name: str, use_case: str | None) -> dict[str, dict[str, Any]]:
    _, approaches = load_approaches()
    if approach_name != "all":
        if approach_name not in approaches:
            raise SystemExit(f"Unknown approach '{approach_name}'.")
        return {approach_name: approaches[approach_name]}

    selected = {}
    for name, approach in approaches.items():
        if not approach.get("uses_flowcept", True):
            continue
        if use_case and not name.endswith(f"_{use_case}"):
            continue
        if not use_case and not approach.get("enabled", False):
            continue
        selected[name] = approach
    return selected


def canonical_path(raw_path: str) -> str:
    if raw_path in FIELD_ALIASES:
        return FIELD_ALIASES[raw_path]
    for raw_prefix, canonical_prefix in sorted(FIELD_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        prefix = f"{raw_prefix}."
        if raw_path.startswith(prefix):
            return f"{canonical_prefix}.{raw_path[len(prefix):]}"
    return raw_path


def observed_fields_for_approach(defaults: dict[str, Any], approach: dict[str, Any]) -> dict[str, Any]:
    client = mongo_client(defaults, approach)
    db = client[approach["mongo_db"]]
    by_collection = {}
    observed: set[str] = set()
    raw_to_canonical: dict[str, str] = {}

    conditional_context = {
        "requires_error_stderr": False,
    }

    for collection_name, prefix in COLLECTION_PREFIXES.items():
        docs = list(db[collection_name].find({}))
        if collection_name == "tasks":
            conditional_context["requires_error_stderr"] = any(
                str(doc.get("status", "")).upper() in ERROR_STATUSES and bool(doc.get("stderr"))
                for doc in docs
            )
            for doc in docs:
                pseudo_field = SUBTYPE_PSEUDO_FIELDS.get(str(doc.get("subtype")))
                if pseudo_field:
                    observed.add(pseudo_field)
                    raw_to_canonical[f"{prefix}.subtype.{doc.get('subtype')}"] = pseudo_field
        inventory = docs_field_inventory(docs)
        collection_fields = {}
        for raw_field, stats in inventory["fields"].items():
            prefixed_raw = f"{prefix}.{raw_field}"
            canonical = canonical_path(prefixed_raw)
            if canonical == "task.execution_metadata.stderr" and not conditional_context["requires_error_stderr"]:
                continue
            observed.add(canonical)
            raw_to_canonical[prefixed_raw] = canonical
            collection_fields[prefixed_raw] = {
                "canonical_field": canonical,
                "document_count": stats["count"],
                "document_presence": stats["presence"],
            }
        by_collection[collection_name] = {
            "document_count": inventory["document_count"],
            "fields": collection_fields,
        }

    return {
        "observed_fields": sorted(observed),
        "raw_to_canonical": raw_to_canonical,
        "conditional_context": conditional_context,
        "collections": by_collection,
    }


def mapping_fields(mapping: dict[str, Any]) -> dict[str, Any]:
    fields = dict(mapping.get("fields") or {})
    fields.update(mapping.get("custom_fields") or {})
    return fields


def mapped_ancestor(field: str, mapped: dict[str, Any]) -> str | None:
    parts = field.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in mapped:
            return candidate
    return None


def is_custom_field_candidate(field: str) -> bool:
    custom_segments = (
        ".custom_metadata.",
        ".used.",
        ".generated.",
        ".data.",
        ".stdout.",
        ".stderr.",
    )
    return any(segment in field for segment in custom_segments)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0])
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_markdown_summary(path: Path, rows: list[dict[str, Any]], mapping_path: Path, use_case: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table_rows = [
        [
            row["approach_label"],
            str(row["observed_field_count"]),
            str(row["mapped_observed_field_count"]),
            str(row["unmapped_observed_field_count"]),
            str(row["custom_candidate_field_count"]),
            f"{row['mapping_coverage_percent']:.2f}",
        ]
        for row in rows
    ]
    lines = [
        "# Field Coverage Inventory",
        "",
        f"Generated at: `{utc_now_iso()}`",
        f"Use case: {use_case or 'n/a'}",
        f"Editable mapping: `{mapping_path}`",
        "",
        "Counts are based on unique field presence per approach, not on the number of documents containing each field.",
        "",
        markdown_table(
            [
                "Approach",
                "Observed Fields",
                "Mapped Fields",
                "Unmapped Fields",
                "Custom Field Candidates",
                "Mapping Coverage (%)",
            ],
            table_rows,
        ),
        "",
        "## Notes",
        "",
        "- `Mapped Fields` counts observed fields that match the editable mapping directly or through a mapped parent field.",
        "- `Custom Field Candidates` lists observed nested fields under payload-like containers such as `custom_metadata`, `used`, `generated`, and `data` for manual review.",
        "- `Unmapped Fields` lists observed fields that do not match a mapped field or mapped parent field.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    mapping_path = Path(args.mapping)
    source_analysis_path = Path(args.source_analysis)

    if args.init_mapping:
        if mapping_path.exists() and not args.force_init_mapping:
            raise SystemExit(
                f"{mapping_path} already exists. Refusing to overwrite it. "
                "Use --force-init-mapping if you really want to regenerate it."
            )
        mapping = write_initial_mapping(mapping_path, source_analysis_path)
        print(f"Wrote editable mapping {mapping_path}")
    elif not mapping_path.exists():
        raise SystemExit(
            f"Mapping file {mapping_path} does not exist. "
            "Run once with --init-mapping to create it."
        )
    else:
        mapping = load_yaml(mapping_path)

    defaults, _ = load_approaches()
    labels = load_approach_labels()
    approaches = selected_approaches_for_analysis(args.approach, args.use_case)
    mapped_fields = mapping_fields(mapping)

    rows = []
    unmapped_rows = []
    custom_candidate_rows = []
    observed_payload = {}

    for approach_name, approach in approaches.items():
        observed = observed_fields_for_approach(defaults, approach)
        observed_set = set(observed["observed_fields"])
        mapped_observed = set()
        covered_by_parent = {}
        custom_candidates = set()
        unmapped = set()
        for field in observed_set:
            ancestor = mapped_ancestor(field, mapped_fields)
            if ancestor is not None:
                mapped_observed.add(ancestor)
                if ancestor != field:
                    covered_by_parent[field] = ancestor
                    if is_custom_field_candidate(field):
                        custom_candidates.add(field)
            else:
                unmapped.add(field)
                if is_custom_field_candidate(field):
                    custom_candidates.add(field)

        mapped_observed_list = sorted(mapped_observed)
        unmapped_list = sorted(unmapped)
        custom_candidate_list = sorted(custom_candidates)
        approach_label = approach_display_label(approach_name, labels)
        use_case_label = use_case_display_label(approach_name, labels)

        observed_payload[approach_name] = {
            "approach_label": approach_label,
            "use_case_label": use_case_label,
            "mongo_db": approach["mongo_db"],
            "observed_field_count": len(observed_set),
            "mapped_observed_field_count": len(mapped_observed_list),
            "unmapped_observed_field_count": len(unmapped_list),
            "custom_candidate_field_count": len(custom_candidate_list),
            "observed_fields": sorted(observed_set),
            "mapped_observed_fields": mapped_observed_list,
            "unmapped_observed_fields": unmapped_list,
            "custom_candidate_fields": custom_candidate_list,
            "covered_by_parent": covered_by_parent,
            "collections": observed["collections"],
        }
        rows.append(
            {
                "approach": approach_name,
                "approach_label": approach_label,
                "use_case": use_case_label,
                "mongo_db": approach["mongo_db"],
                "observed_field_count": len(observed_set),
                "mapped_observed_field_count": len(mapped_observed_list),
                "unmapped_observed_field_count": len(unmapped_list),
                "custom_candidate_field_count": len(custom_candidate_list),
                "mapping_coverage_percent": round((len(mapped_observed_list) / len(mapped_fields)) * 100, 2) if mapped_fields else 0.0,
            }
        )
        for field in unmapped_list:
            raw_examples = sorted(raw for raw, canonical in observed["raw_to_canonical"].items() if canonical == field)
            unmapped_rows.append(
                {
                    "approach": approach_name,
                    "approach_label": approach_label,
                    "use_case": use_case_label,
                    "field": field,
                    "raw_examples": "; ".join(raw_examples[:5]),
                }
            )
        for field in custom_candidate_list:
            raw_examples = sorted(raw for raw, canonical in observed["raw_to_canonical"].items() if canonical == field)
            custom_candidate_rows.append(
                {
                    "approach": approach_name,
                    "approach_label": approach_label,
                    "use_case": use_case_label,
                    "field": field,
                    "covered_by_parent": covered_by_parent.get(field, ""),
                    "already_mapped": field in mapped_fields,
                    "raw_examples": "; ".join(raw_examples[:5]),
                }
            )

    output_root = RESULTS_DIR / "_analysis"
    prefix = args.output_prefix
    if args.use_case and prefix == "field_coverage":
        prefix = f"field_coverage_{args.use_case}"
    write_json(
        output_root / f"{prefix}_observed_fields.json",
        {
            "generated_at": utc_now_iso(),
            "mapping_path": str(mapping_path),
            "approach": args.approach,
            "use_case": args.use_case,
            "approaches": observed_payload,
        },
    )
    write_csv(output_root / f"{prefix}_summary.csv", rows)
    write_csv(output_root / f"{prefix}_unmapped_fields.csv", unmapped_rows)
    write_csv(output_root / f"{prefix}_custom_field_candidates.csv", custom_candidate_rows)
    write_custom_candidate_mapping(output_root / f"{prefix}_custom_field_candidates.yaml", custom_candidate_rows)
    write_suggested_custom_mapping(output_root / f"{prefix}_suggested_custom_mapping.yaml", custom_candidate_rows)
    write_markdown_summary(output_root / f"{prefix}_summary.md", rows, mapping_path, args.use_case)

    print(f"Wrote {output_root / f'{prefix}_observed_fields.json'}")
    print(f"Wrote {output_root / f'{prefix}_summary.csv'}")
    print(f"Wrote {output_root / f'{prefix}_summary.md'}")
    print(f"Wrote {output_root / f'{prefix}_unmapped_fields.csv'}")
    print(f"Wrote {output_root / f'{prefix}_custom_field_candidates.csv'}")
    print(f"Wrote {output_root / f'{prefix}_custom_field_candidates.yaml'}")
    print(f"Wrote {output_root / f'{prefix}_suggested_custom_mapping.yaml'}")
    for row in rows:
        print(
            f"{row['approach']}: observed={row['observed_field_count']} "
            f"mapped={row['mapped_observed_field_count']} "
            f"unmapped={row['unmapped_observed_field_count']} "
            f"custom_candidates={row['custom_candidate_field_count']}"
        )


if __name__ == "__main__":
    main()
