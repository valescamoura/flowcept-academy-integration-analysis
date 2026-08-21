from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from experiment_utils import (
    REPO_ROOT,
    approach_results_dir,
    load_approaches,
    make_flowcept_settings,
    merged_env,
    resolve_python_path,
    selected_approaches,
    utc_now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start or stop long-running services for one approach.")
    parser.add_argument("--approach", required=True, help="Approach name from experiments/config/approaches.yaml.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--start", action="store_true", help="Start services for the approach.")
    action.add_argument("--stop", action="store_true", help="Stop services for the approach.")
    action.add_argument("--status", action="store_true", help="Show service status for the approach.")
    return parser.parse_args()


def services_dir(approach_name: str) -> Path:
    path = approach_results_dir(approach_name) / "services"
    path.mkdir(parents=True, exist_ok=True)
    return path


def services_state_path(approach_name: str) -> Path:
    return services_dir(approach_name) / "services.json"


def read_state(approach_name: str) -> dict[str, Any]:
    path = services_state_path(approach_name)
    if not path.exists():
        return {"approach": approach_name, "services": {}}
    return json.loads(path.read_text())


def is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def require_opentelemetry_approach(name: str) -> None:
    if name != "opentelemetry_integration_perceptron_gridsearch":
        raise SystemExit(
            f"Approach '{name}' has no managed long-running services configured. "
            "For now only opentelemetry_integration_perceptron_gridsearch uses this script."
        )


def collector_config_path() -> Path:
    return REPO_ROOT / "approaches" / "opentelemetry_integration" / "otelcol-flowcept-academy-perceptron.yaml"


def collector_checkout_dir(approach_name: str) -> Path:
    return services_dir(approach_name) / "opentelemetry-collector"


def run_checked(command: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        command_text = " ".join(command)
        raise SystemExit(
            f"Command failed: {command_text}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def resolve_collector_dir(approach_name: str, env: dict[str, str]) -> Path:
    explicit_dir = env.get("OTEL_COLLECTOR_DIR")
    if explicit_dir:
        collector_dir = Path(explicit_dir).expanduser().resolve()
        if not collector_dir.exists():
            raise SystemExit(f"Collector directory not found: {collector_dir}")
        return collector_dir

    git_url = env.get("OTEL_COLLECTOR_GIT_URL", "https://github.com/valescamoura/opentelemetry-collector.git")
    git_branch = env.get("OTEL_COLLECTOR_GIT_BRANCH", "flowcept_academy_exporter")
    checkout_dir = collector_checkout_dir(approach_name)
    if not (checkout_dir / ".git").exists():
        checkout_dir.parent.mkdir(parents=True, exist_ok=True)
        run_checked(["git", "clone", "--branch", git_branch, git_url, str(checkout_dir)])
    else:
        run_checked(["git", "fetch", "origin", git_branch], cwd=checkout_dir)
        run_checked(["git", "checkout", git_branch], cwd=checkout_dir)
        run_checked(["git", "pull", "--ff-only", "origin", git_branch], cwd=checkout_dir)

    collector_dir = checkout_dir / "cmd" / "otelcorecol"
    if not collector_dir.exists():
        raise SystemExit(f"Collector command directory not found after checkout: {collector_dir}")
    return collector_dir


def start_service(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_dir: Path,
    wait_seconds: float,
) -> dict[str, Any]:
    stdout_path = log_dir / f"{name}_stdout.log"
    stderr_path = log_dir / f"{name}_stderr.log"
    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    finally:
        stdout.close()
        stderr.close()

    time.sleep(wait_seconds)
    if process.poll() is not None:
        raise RuntimeError(f"{name} exited during startup. See {stderr_path}")

    return {
        "name": name,
        "pid": process.pid,
        "pgid": os.getpgid(process.pid),
        "command": command,
        "cwd": str(cwd),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "started_at": utc_now_iso(),
    }


def start_opentelemetry_services(approach_name: str, approach: dict[str, Any], defaults: dict[str, Any]) -> None:
    state = read_state(approach_name)
    running = {
        name: svc
        for name, svc in state.get("services", {}).items()
        if is_running(svc.get("pid"))
    }
    if running:
        names = ", ".join(sorted(running))
        raise SystemExit(f"Services already running for {approach_name}: {names}. Use --stop first.")

    result_dir = services_dir(approach_name)
    settings_path = make_flowcept_settings(approach_name, defaults, approach).resolve()
    env = merged_env(
        os.environ,
        approach,
        {
            "EXPERIMENT_APPROACH": approach_name,
            "FLOWCEPT_SETTINGS_PATH": str(settings_path),
        },
        defaults,
    )
    python = Path(os.path.abspath(resolve_python_path(defaults, approach)))
    collector_dir = resolve_collector_dir(approach_name, env)

    services = {}
    services["flowcept_consumer"] = start_service(
        name="flowcept_consumer",
        command=[str(python), "-m", "flowcept.cli", "--start-consumption-services"],
        cwd=REPO_ROOT,
        env=env,
        log_dir=result_dir,
        wait_seconds=2,
    )
    services["otel_collector"] = start_service(
        name="otel_collector",
        command=["go", "run", ".", "--config", str(collector_config_path())],
        cwd=collector_dir,
        env=env,
        log_dir=result_dir,
        wait_seconds=3,
    )

    write_json(
        services_state_path(approach_name),
        {
            "approach": approach_name,
            "settings_path": str(settings_path),
            "collector_config_path": str(collector_config_path()),
            "collector_dir": str(collector_dir),
            "services": services,
            "updated_at": utc_now_iso(),
        },
    )
    print(f"Started services for {approach_name}:")
    for service in services.values():
        print(f"  {service['name']}: pid={service['pid']} log={service['stdout_log']}")


def stop_service(service: dict[str, Any]) -> str:
    pid = service.get("pid")
    pgid = service.get("pgid")
    name = service.get("name", "service")
    if not is_running(pid):
        return f"{name}: already stopped"

    target = pgid or pid
    try:
        os.killpg(target, signal.SIGINT)
    except ProcessLookupError:
        return f"{name}: already stopped"

    deadline = time.time() + 8
    while time.time() < deadline:
        if not is_running(pid):
            return f"{name}: stopped"
        time.sleep(0.2)

    try:
        os.killpg(target, signal.SIGTERM)
    except ProcessLookupError:
        return f"{name}: stopped"

    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_running(pid):
            return f"{name}: stopped"
        time.sleep(0.2)

    try:
        os.killpg(target, signal.SIGKILL)
    except ProcessLookupError:
        return f"{name}: stopped"
    return f"{name}: killed"


def stop_services(approach_name: str) -> None:
    state = read_state(approach_name)
    services = state.get("services", {})
    if not services:
        print(f"No recorded services for {approach_name}.")
        return
    for service in reversed(list(services.values())):
        print(stop_service(service))
    state["stopped_at"] = utc_now_iso()
    state["services"] = {}
    write_json(services_state_path(approach_name), state)


def show_status(approach_name: str) -> None:
    state = read_state(approach_name)
    services = state.get("services", {})
    if not services:
        print(f"No recorded services for {approach_name}.")
        return
    for service in services.values():
        status = "running" if is_running(service.get("pid")) else "stopped"
        print(f"{service.get('name')}: {status} pid={service.get('pid')} log={service.get('stdout_log')}")


def main() -> None:
    args = parse_args()
    require_opentelemetry_approach(args.approach)
    defaults, approaches = load_approaches()
    selected = selected_approaches(args.approach)
    approach = selected[args.approach]
    if args.start:
        start_opentelemetry_services(args.approach, approach, defaults)
    elif args.stop:
        stop_services(args.approach)
    else:
        show_status(args.approach)


if __name__ == "__main__":
    main()
