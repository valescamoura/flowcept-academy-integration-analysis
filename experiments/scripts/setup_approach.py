from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any

from experiment_utils import (
    REPO_ROOT,
    approach_results_dir,
    load_approaches,
    merged_env,
    selected_approaches,
    utc_now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run setup commands for configured approaches.")
    parser.add_argument("--approach", required=True, help="Approach name or 'all'.")
    parser.add_argument("--force", action="store_true", help="Run setup even if a prior setup succeeded.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="Timeout per setup command.")
    return parser.parse_args()


def command_to_text(command: list[str]) -> str:
    return " ".join(command)


def setup_done_path(approach_name: str) -> Path:
    return approach_results_dir(approach_name) / "setup_done.json"


def run_setup_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    stdout_log,
    stderr_log,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    stdout_log.write(f"\n$ {command_to_text(command)}\n")
    stdout_log.flush()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=stdout_log,
        stderr=stderr_log,
        timeout=timeout,
    )
    ended_at = utc_now_iso()
    return {
        "command": command,
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": proc.returncode,
        "success": proc.returncode == 0,
    }


def force_clear_venv_command(command: list[str], force: bool) -> list[str]:
    if not force:
        return command
    if len(command) >= 4 and command[1:3] == ["-m", "venv"] and "--clear" not in command:
        return command[:3] + ["--clear"] + command[3:]
    return command


def setup_one(
    name: str,
    approach: dict[str, Any],
    defaults: dict[str, Any],
    timeout: int,
    force: bool,
    dry_run: bool,
) -> None:
    result_root = approach_results_dir(name)
    result_root.mkdir(parents=True, exist_ok=True)
    done_path = setup_done_path(name)
    if done_path.exists() and not force and not dry_run:
        print(f"{name}: setup already marked successful. Use --force to rerun.")
        return

    cwd = REPO_ROOT / approach["cwd"]
    if not cwd.exists():
        raise SystemExit(f"Approach '{name}' cwd does not exist: {cwd}")

    commands = approach.get("setup", {}).get("commands", [])
    if not commands:
        print(f"{name}: no setup.commands configured.")
        return

    print(f"{name}: setup cwd={cwd}")
    for command in commands:
        print(f"  $ {command_to_text(command)}")
    if dry_run:
        return

    env = merged_env(
        os.environ,
        approach,
        {
            "EXPERIMENT_APPROACH": name,
            "EXPERIMENT_SETUP": "1",
        },
        defaults,
    )

    stdout_path = result_root / "setup_stdout.log"
    stderr_path = result_root / "setup_stderr.log"
    command_results = []
    with stdout_path.open("a") as stdout_log, stderr_path.open("a") as stderr_log:
        stdout_log.write(f"\n=== setup {name} {utc_now_iso()} ===\n")
        stderr_log.write(f"\n=== setup {name} {utc_now_iso()} ===\n")
        for command in commands:
            effective_command = force_clear_venv_command(command, force)
            result = run_setup_command(effective_command, cwd, env, timeout, stdout_log, stderr_log)
            command_results.append(result)
            print(f"{name}: {command_to_text(effective_command)} -> {result['exit_code']}")
            if result["exit_code"] != 0:
                metadata = {
                    "approach": name,
                    "success": False,
                    "cwd": str(cwd),
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                    "commands": command_results,
                    "ended_at": utc_now_iso(),
                }
                write_json(result_root / "setup_failed.json", metadata)
                raise SystemExit(f"{name}: setup failed. See {stderr_path}")

    metadata = {
        "approach": name,
        "success": True,
        "cwd": str(cwd),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "commands": command_results,
        "ended_at": utc_now_iso(),
    }
    write_json(done_path, metadata)


def main() -> None:
    args = parse_args()
    defaults, _all = load_approaches()
    approaches = selected_approaches(args.approach)
    for name, approach in approaches.items():
        setup_one(name, approach, defaults, args.timeout_seconds, args.force, args.dry_run)


if __name__ == "__main__":
    main()
