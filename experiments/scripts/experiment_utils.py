from __future__ import annotations

import csv
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pymongo import MongoClient
from bson.json_util import dumps


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
CONFIG_DIR = EXPERIMENTS_DIR / "config"
RESULTS_DIR = EXPERIMENTS_DIR / "results"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return data


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def load_approaches() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    cfg = load_yaml(CONFIG_DIR / "approaches.yaml")
    return cfg.get("defaults", {}), cfg.get("approaches", {})


def load_approach_labels() -> dict[str, Any]:
    path = CONFIG_DIR / "approach_labels.yaml"
    if not path.exists():
        return {"approaches": {}, "use_cases": {}}
    return load_yaml(path)


def split_approach_use_case(approach_name: str, labels: dict[str, Any] | None = None) -> tuple[str, str]:
    labels = labels or load_approach_labels()
    use_cases = labels.get("use_cases", {})
    for use_case in sorted(use_cases, key=len, reverse=True):
        suffix = f"_{use_case}"
        if approach_name.endswith(suffix):
            return approach_name[: -len(suffix)], use_case
    return approach_name, "fibonacci"


def approach_display_label(approach_name: str, labels: dict[str, Any] | None = None) -> str:
    labels = labels or load_approach_labels()
    approach_key, _ = split_approach_use_case(approach_name, labels)
    return labels.get("approaches", {}).get(approach_key, approach_key)


def use_case_display_label(approach_name: str, labels: dict[str, Any] | None = None) -> str:
    labels = labels or load_approach_labels()
    _, use_case = split_approach_use_case(approach_name, labels)
    return labels.get("use_cases", {}).get(use_case, use_case)


def selected_approaches(name: str) -> dict[str, dict[str, Any]]:
    _, approaches = load_approaches()
    if name == "all":
        return {k: v for k, v in approaches.items() if v.get("enabled", False)}
    if name not in approaches:
        raise SystemExit(f"Unknown approach '{name}'. Known: {', '.join(sorted(approaches))}")
    return {name: approaches[name]}


def approach_results_dir(approach_name: str) -> Path:
    return RESULTS_DIR / approach_name


def runs_csv_path(approach_name: str) -> Path:
    return approach_results_dir(approach_name) / "runs.csv"


def read_runs_csv(approach_name: str) -> list[dict[str, str]]:
    path = runs_csv_path(approach_name)
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def append_run_row(approach_name: str, row: dict[str, Any]) -> None:
    path = runs_csv_path(approach_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = list(row.keys())
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def mongo_client(defaults: dict[str, Any], approach: dict[str, Any]) -> MongoClient:
    mongo_defaults = defaults.get("mongo", {})
    mongo_cfg = approach.get("mongo", {})
    uri = mongo_cfg.get("uri") or mongo_defaults.get("uri")
    kwargs = {
        "serverSelectionTimeoutMS": int(mongo_cfg.get("timeout_ms", mongo_defaults.get("timeout_ms", 3000))),
        "connectTimeoutMS": int(mongo_cfg.get("timeout_ms", mongo_defaults.get("timeout_ms", 3000))),
        "socketTimeoutMS": int(mongo_cfg.get("socket_timeout_ms", mongo_defaults.get("socket_timeout_ms", 10000))),
    }
    if uri:
        return MongoClient(uri, **kwargs)
    host = mongo_cfg.get("host", mongo_defaults.get("host", "localhost"))
    port = int(mongo_cfg.get("port", mongo_defaults.get("port", 27017)))
    return MongoClient(host, port, **kwargs)


def collection_counts(client: MongoClient, db_name: str) -> dict[str, int]:
    db = client[db_name]
    return {
        "workflows": db["workflows"].count_documents({}),
        "tasks": db["tasks"].count_documents({}),
        "objects": db["objects"].count_documents({}),
    }


def id_set(client: MongoClient, db_name: str, collection: str, field: str) -> set[str]:
    return {str(x) for x in client[db_name][collection].distinct(field) if x is not None}


def export_database_snapshot(client: MongoClient, db_name: str, output_path: Path) -> None:
    db = client[db_name]
    payload = {
        "database": db_name,
        "exported_at": utc_now_iso(),
        "workflows": list(db["workflows"].find({})),
        "tasks": list(db["tasks"].find({})),
        "objects": list(db["objects"].find({})),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dumps(payload, indent=2))


def resolve_path_for_cwd(path_value: str, cwd: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cwd / path


def resolve_python_path(defaults: dict[str, Any], approach: dict[str, Any] | None = None) -> str:
    configured = (approach or {}).get("python", defaults.get("python", "python"))
    cwd = REPO_ROOT / (approach or {}).get("cwd", ".")
    python_path = Path(configured)
    if not python_path.is_absolute():
        if approach and "python" in approach:
            python_path = cwd / python_path
        else:
            python_path = REPO_ROOT / python_path
    if python_path.exists():
        return str(python_path)
    return configured


def resolve_python(command: list[str], defaults: dict[str, Any], approach: dict[str, Any] | None = None) -> list[str]:
    if not command:
        raise ValueError("Approach command cannot be empty.")
    python = resolve_python_path(defaults, approach)
    return [python if part == "{python}" else part for part in command]


def approach_venv_site_packages(defaults: dict[str, Any], approach: dict[str, Any]) -> str:
    python_path = Path(resolve_python_path(defaults, approach))
    if python_path.parent.name == "bin":
        venv_root = python_path.parent.parent
        candidates = sorted((venv_root / "lib").glob("python*/site-packages"))
        if candidates:
            return str(candidates[0])
    return ""


def current_flowcept_settings_path() -> Path | None:
    env_path = os.environ.get("FLOWCEPT_SETTINGS_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    user_path = Path.home() / ".flowcept" / "settings.yaml"
    if user_path.exists():
        return user_path
    return None


def minimal_flowcept_settings(db_name: str, defaults: dict[str, Any], approach: dict[str, Any]) -> dict[str, Any]:
    mongo_defaults = defaults.get("mongo", {})
    mongo_cfg = approach.get("mongo", {})
    return {
        "log": {"log_file_level": "disable", "log_stream_level": "disable"},
        "project": {
            "db_flush_mode": "online",
            "dump_buffer": {"enabled": False, "path": "flowcept_buffer.jsonl"},
            "enrich_messages": True,
        },
        "telemetry_capture": flowcept_telemetry_capture(defaults, approach),
        "instrumentation": {"enabled": True},
        "experiment": {},
        "mq": {
            "enabled": True,
            "type": "redis",
            "host": "localhost",
            "port": 6379,
            "channel": "interception",
        },
        "kv_db": {"enabled": True, "host": "localhost", "port": 6379},
        "web_server": {},
        "sys_metadata": {},
        "extra_metadata": {},
        "analytics": {},
        "db_buffer": {"buffer_size": 50, "insertion_buffer_time_secs": 1},
        "databases": {
            "mongodb": {
                "enabled": True,
                "host": mongo_cfg.get("host", mongo_defaults.get("host", "localhost")),
                "port": int(mongo_cfg.get("port", mongo_defaults.get("port", 27017))),
                "db": db_name,
                "create_collection_index": True,
            },
            "lmdb": {"enabled": False},
        },
        "adapters": {},
        "agent": {},
    }


def make_flowcept_settings(approach_name: str, defaults: dict[str, Any], approach: dict[str, Any]) -> Path:
    db_name = approach["mongo_db"]
    settings = minimal_flowcept_settings(db_name, defaults, approach)
    approach_flowcept = approach.get("flowcept", {})
    telemetry_capture = flowcept_telemetry_capture(defaults, approach)
    if telemetry_capture is not None:
        settings["telemetry_capture"] = telemetry_capture
    if approach_flowcept.get("plugins") is not None:
        settings["plugins"] = deepcopy(approach_flowcept["plugins"])
    settings.setdefault("databases", {})
    settings["databases"].setdefault("mongodb", {})
    settings["databases"]["mongodb"]["enabled"] = True
    settings["databases"]["mongodb"]["db"] = db_name

    mongo_defaults = defaults.get("mongo", {})
    mongo_cfg = approach.get("mongo", {})
    if "host" in mongo_cfg or "host" in mongo_defaults:
        settings["databases"]["mongodb"]["host"] = mongo_cfg.get("host", mongo_defaults.get("host", "localhost"))
    if "port" in mongo_cfg or "port" in mongo_defaults:
        settings["databases"]["mongodb"]["port"] = int(mongo_cfg.get("port", mongo_defaults.get("port", 27017)))
    if "uri" in mongo_cfg or "uri" in mongo_defaults:
        settings["databases"]["mongodb"]["uri"] = mongo_cfg.get("uri", mongo_defaults.get("uri"))

    out = approach_results_dir(approach_name) / "flowcept_settings.yaml"
    save_yaml(out, settings)
    return out


def flowcept_telemetry_capture(defaults: dict[str, Any], approach: dict[str, Any]) -> dict[str, Any] | None:
    default_flowcept = defaults.get("flowcept", {})
    approach_flowcept = approach.get("flowcept", {})
    if approach_flowcept.get("telemetry_capture") is not None:
        return deepcopy(approach_flowcept.get("telemetry_capture"))
    if default_flowcept.get("telemetry_capture") is not None:
        return deepcopy(default_flowcept.get("telemetry_capture"))
    return None


def flatten_keys(document: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in document.items():
        if key == "_id":
            continue
        path = f"{prefix}.{key}" if prefix else str(key)
        keys.add(path)
        if isinstance(value, dict):
            keys.update(flatten_keys(value, path))
    return keys


def docs_field_inventory(docs: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for doc in docs:
        for key in flatten_keys(doc):
            counts[key] = counts.get(key, 0) + 1
    total = len(docs)
    return {
        "document_count": total,
        "fields": {
            key: {
                "count": count,
                "presence": (count / total if total else 0.0),
            }
            for key, count in sorted(counts.items())
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def merged_env(
    base_env: dict[str, str],
    approach: dict[str, Any],
    extra: dict[str, str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, str]:
    env = base_env.copy()
    cwd = REPO_ROOT / approach.get("cwd", ".")
    approach_root = cwd.parent if cwd.name == "src" else cwd
    site_packages = approach_venv_site_packages(defaults or {}, approach)
    for key, value in (approach.get("env") or {}).items():
        rendered = str(value).replace("{repo_root}", str(REPO_ROOT))
        rendered = rendered.replace("{approach_cwd}", str(cwd))
        rendered = rendered.replace("{approach_root}", str(approach_root))
        rendered = rendered.replace("{approach_venv_site_packages}", site_packages)
        rendered = rendered.replace("{pathsep}", os.pathsep)
        if "{env:" in rendered:
            for env_key in list(env):
                rendered = rendered.replace(f"{{env:{env_key}}}", env.get(env_key, ""))
        env[str(key)] = rendered
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    return env
