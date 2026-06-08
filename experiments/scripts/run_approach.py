from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Thread

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is optional for the runner.
    psutil = None

from experiment_utils import (
    REPO_ROOT,
    append_run_row,
    approach_results_dir,
    collection_counts,
    copy_if_exists,
    export_database_snapshot,
    id_set,
    load_approaches,
    make_flowcept_settings,
    mongo_client,
    resolve_python,
    selected_approaches,
    utc_now_iso,
    write_json,
    merged_env,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run configured integration approaches.")
    parser.add_argument("--approach", required=True, help="Approach name or 'all'.")
    parser.add_argument("--runs", type=int, default=None, help="Number of repetitions.")
    parser.add_argument("--clean-db", action="store_true", help="Drop the approach Mongo database before running.")
    parser.add_argument(
        "--clean-results",
        action="store_true",
        help="Delete local result files for the approach before running.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Per-run timeout.")
    parser.add_argument("--export-db", action="store_true", help="Export a Mongo snapshot after all runs.")
    parser.add_argument(
        "--no-resource-metrics",
        action="store_true",
        help="Disable runner-level CPU/memory sampling. By default psutil is required.",
    )
    return parser.parse_args()


def clean_local_results(result_root: Path) -> None:
    if not result_root.exists():
        return
    for child in result_root.iterdir():
        if child.name == "flowcept_settings.yaml":
            continue
        if child.name == "setup_done.json":
            continue
        if child.name.startswith("setup_"):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _empty_resource_metrics() -> dict:
    return {
        "resource_sampling_enabled": False,
        "resource_sample_count": 0,
        "memory_peak_rss_bytes": None,
        "memory_mean_rss_bytes": None,
        "cpu_time_user_seconds": None,
        "cpu_time_system_seconds": None,
        "cpu_time_total_seconds": None,
        "cpu_time_per_wall_second": None,
        "cpu_utilization_percent_max": None,
        "cpu_utilization_percent_mean": None,
    }


def _sample_process_tree(proc: subprocess.Popen, stop_flag: dict, interval: float = 0.2) -> dict:
    metrics = _empty_resource_metrics()
    if psutil is None:
        return metrics

    metrics["resource_sampling_enabled"] = True
    rss_samples: list[int] = []
    cpu_total_samples: list[tuple[float, float]] = []

    try:
        root = psutil.Process(proc.pid)
    except psutil.Error:
        return metrics

    while not stop_flag.get("stop"):
        try:
            processes = [root, *root.children(recursive=True)]
            rss = 0
            user = 0.0
            system = 0.0
            for process in processes:
                try:
                    mem = process.memory_info()
                    cpu = process.cpu_times()
                except psutil.Error:
                    continue
                rss += getattr(mem, "rss", 0)
                user += getattr(cpu, "user", 0.0)
                system += getattr(cpu, "system", 0.0)
            rss_samples.append(rss)
            cpu_total_samples.append((time.perf_counter(), user + system))
        except psutil.Error:
            pass
        time.sleep(interval)

    if rss_samples:
        metrics["resource_sample_count"] = len(rss_samples)
        metrics["memory_peak_rss_bytes"] = max(rss_samples)
        metrics["memory_mean_rss_bytes"] = sum(rss_samples) / len(rss_samples)

    if cpu_total_samples:
        total_cpu = max(total for _, total in cpu_total_samples)
        metrics["cpu_time_total_seconds"] = total_cpu
        metrics["cpu_time_user_seconds"] = None
        metrics["cpu_time_system_seconds"] = None

        instantaneous = []
        for (prev_t, prev_cpu), (next_t, next_cpu) in zip(cpu_total_samples, cpu_total_samples[1:]):
            dt = next_t - prev_t
            if dt > 0:
                instantaneous.append(((next_cpu - prev_cpu) / dt) * 100.0)
        if instantaneous:
            metrics["cpu_utilization_percent_max"] = max(instantaneous)
            metrics["cpu_utilization_percent_mean"] = sum(instantaneous) / len(instantaneous)

    return metrics


def _run_command_with_metrics(
    command: list[str],
    cwd: Path,
    env: dict,
    timeout: int,
    collect_resources: bool,
) -> tuple[int, str, str, bool, dict]:
    if not collect_resources:
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr, False, _empty_resource_metrics()
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            return 124, stdout, stderr, True, _empty_resource_metrics()

    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stop_flag = {"stop": False}
    metrics_holder: dict[str, dict] = {}

    def sampler() -> None:
        metrics_holder["metrics"] = _sample_process_tree(proc, stop_flag)

    sampler_thread = Thread(target=sampler, daemon=True)
    sampler_thread.start()
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = 124
        proc.kill()
        stdout, stderr = proc.communicate()
    finally:
        stop_flag["stop"] = True
        sampler_thread.join(timeout=1.0)

    return exit_code, stdout or "", stderr or "", timed_out, metrics_holder.get("metrics", _empty_resource_metrics())


def run_one(
    approach_name: str,
    approach: dict,
    defaults: dict,
    runs: int,
    timeout: int,
    clean_db: bool,
    clean_results: bool,
    collect_resources: bool,
) -> None:
    result_root = approach_results_dir(approach_name)
    result_root.mkdir(parents=True, exist_ok=True)
    if clean_results:
        clean_local_results(result_root)

    client = mongo_client(defaults, approach)
    db_name = approach["mongo_db"]
    if clean_db:
        client.drop_database(db_name)

    uses_flowcept = approach.get("uses_flowcept", True)
    settings_path = make_flowcept_settings(approach_name, defaults, approach) if uses_flowcept else None

    cwd = REPO_ROOT / approach["cwd"]
    command = resolve_python(list(approach["command"]), defaults, approach)
    if not cwd.exists():
        raise SystemExit(f"Approach '{approach_name}' cwd does not exist: {cwd}")

    for run_index in range(1, runs + 1):
        run_id = f"run_{run_index:03d}"
        run_dir = result_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        before_counts = collection_counts(client, db_name)
        before_workflows = id_set(client, db_name, "workflows", "workflow_id")
        before_tasks = id_set(client, db_name, "tasks", "task_id")

        extra_env = {
            "EXPERIMENT_APPROACH": approach_name,
            "EXPERIMENT_RUN_INDEX": str(run_index),
            "EXPERIMENT_RUN_ID": run_id,
        }
        if settings_path is not None:
            extra_env["FLOWCEPT_SETTINGS_PATH"] = str(settings_path)
        env = merged_env(os.environ, approach, extra_env, defaults)
        command_python = Path(command[0])
        if command_python.parent.name == "bin":
            env["PATH"] = f"{command_python.parent}{os.pathsep}{env.get('PATH', '')}"

        started_at = utc_now_iso()
        t0 = time.perf_counter()
        exit_code, stdout, stderr, timed_out, resource_metrics = _run_command_with_metrics(
            command,
            cwd,
            env,
            timeout,
            collect_resources,
        )
        runtime = time.perf_counter() - t0
        ended_at = utc_now_iso()
        if resource_metrics["cpu_time_total_seconds"] is not None and runtime > 0:
            resource_metrics["cpu_time_per_wall_second"] = resource_metrics["cpu_time_total_seconds"] / runtime

        (run_dir / "stdout.log").write_text(stdout)
        (run_dir / "stderr.log").write_text(stderr)

        after_counts = collection_counts(client, db_name)
        after_workflows = id_set(client, db_name, "workflows", "workflow_id")
        after_tasks = id_set(client, db_name, "tasks", "task_id")
        new_workflows = sorted(after_workflows - before_workflows)
        new_tasks = sorted(after_tasks - before_tasks)

        for artifact in ["flowcept_buffer.jsonl", "PROVENANCE_CARD.md", "workflow_card.md"]:
            copy_if_exists(cwd / artifact, run_dir / artifact)

        metadata = {
            "approach": approach_name,
            "run_id": run_id,
            "run_index": run_index,
            "description": approach.get("description", ""),
            "command": command,
            "cwd": str(cwd),
            "uses_flowcept": uses_flowcept,
            "mongo_db": db_name,
            "flowcept_settings_path": str(settings_path) if settings_path is not None else None,
            "approach_env": approach.get("env", {}),
            "started_at": started_at,
            "ended_at": ended_at,
            "runtime_seconds": runtime,
            "exit_code": exit_code,
            "success": exit_code == 0 and not timed_out,
            "timed_out": timed_out,
            "stdout_bytes": len(stdout.encode()),
            "stderr_bytes": len(stderr.encode()),
            "before_counts": before_counts,
            "after_counts": after_counts,
            "new_workflow_ids": new_workflows,
            "new_task_ids": new_tasks,
            "resource_metrics": resource_metrics,
        }
        write_json(run_dir / "run_metadata.json", metadata)

        row = {
            "approach": approach_name,
            "run_id": run_id,
            "run_index": run_index,
            "started_at": started_at,
            "ended_at": ended_at,
            "runtime_seconds": f"{runtime:.9f}",
            "exit_code": exit_code,
            "success": exit_code == 0 and not timed_out,
            "timed_out": timed_out,
            "stdout_bytes": len(stdout.encode()),
            "stderr_bytes": len(stderr.encode()),
            "mongo_db": db_name,
            "workflow_count_delta": after_counts["workflows"] - before_counts["workflows"],
            "task_count_delta": after_counts["tasks"] - before_counts["tasks"],
            "object_count_delta": after_counts["objects"] - before_counts["objects"],
            "new_workflow_ids": json.dumps(new_workflows),
            "new_task_count": len(new_tasks),
            "resource_sampling_enabled": resource_metrics["resource_sampling_enabled"],
            "resource_sample_count": resource_metrics["resource_sample_count"],
            "memory_peak_rss_bytes": resource_metrics["memory_peak_rss_bytes"],
            "memory_mean_rss_bytes": resource_metrics["memory_mean_rss_bytes"],
            "cpu_time_total_seconds": resource_metrics["cpu_time_total_seconds"],
            "cpu_time_per_wall_second": resource_metrics["cpu_time_per_wall_second"],
            "cpu_utilization_percent_max": resource_metrics["cpu_utilization_percent_max"],
            "cpu_utilization_percent_mean": resource_metrics["cpu_utilization_percent_mean"],
        }
        append_run_row(approach_name, row)
        print(f"{approach_name} {run_id}: {runtime:.3f}s exit={exit_code} tasks+={len(new_tasks)}")


def main() -> None:
    args = parse_args()
    collect_resources = not args.no_resource_metrics
    if collect_resources and psutil is None:
        raise SystemExit(
            "Runner resource metrics require psutil in the root experiment environment. "
            "Install it with: python -m pip install psutil. "
            "Use --no-resource-metrics only if you intentionally want CPU/memory columns empty."
        )
    defaults, _ = load_approaches()
    approaches = selected_approaches(args.approach)
    runs = args.runs if args.runs is not None else int(defaults.get("runs", 30))
    timeout = args.timeout_seconds if args.timeout_seconds is not None else int(defaults.get("timeout_seconds", 300))

    for name, approach in approaches.items():
        run_one(name, approach, defaults, runs, timeout, args.clean_db, args.clean_results, collect_resources)
        if args.export_db and approach.get("uses_flowcept", True):
            client = mongo_client(defaults, approach)
            export_database_snapshot(
                client,
                approach["mongo_db"],
                approach_results_dir(name) / "mongo_snapshot.json",
            )


if __name__ == "__main__":
    main()
