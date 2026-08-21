from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from experiment_utils import (
    REPO_ROOT,
    load_approaches,
    make_flowcept_settings,
    resolve_python_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Flowcept UI for one configured approach.")
    parser.add_argument("--approach", required=True, help="Approach name from experiments/config/approaches.yaml.")
    parser.add_argument(
        "--flowcept-source",
        type=Path,
        help="Flowcept source checkout containing ui/package.json. Usually auto-detected.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Flowcept webservice host.")
    parser.add_argument("--port", type=int, default=8008, help="Flowcept webservice port.")
    return parser.parse_args()


def find_flowcept_source(explicit_path: Path | None) -> Path | None:
    candidates = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    if os.environ.get("FLOWCEPT_SOURCE_DIR"):
        candidates.append(Path(os.environ["FLOWCEPT_SOURCE_DIR"]))
    candidates.extend([REPO_ROOT.parent / "flowcept", Path.cwd()])

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / "ui" / "package.json").is_file():
            return resolved
    return None


def packaged_ui_exists(python: Path) -> bool:
    probe = (
        "from pathlib import Path; import flowcept; "
        "print(int((Path(flowcept.__file__).parent / 'webservice' / 'ui_build' / 'index.html').is_file()))"
    )
    result = subprocess.run(
        [str(python), "-c", probe],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "1"


def ensure_webservice_dependencies(python: Path) -> None:
    result = subprocess.run(
        [str(python), "-c", "import fastapi, uvicorn, sse_starlette"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Flowcept webservice dependencies are missing from this approach venv. "
            "Run setup_approach.py --approach <name> --force after adding/installing the webservice extra."
        )


def main() -> None:
    args = parse_args()
    defaults, approaches = load_approaches()
    if args.approach not in approaches:
        raise SystemExit(f"Unknown approach '{args.approach}'. Known: {', '.join(sorted(approaches))}")

    approach = approaches[args.approach]
    if not approach.get("uses_flowcept", True):
        raise SystemExit(f"Approach '{args.approach}' does not use Flowcept and has no Flowcept UI database.")

    # Keep the venv executable path intact. Path.resolve() follows bin/python's
    # symlink to the system interpreter and loses the virtual environment.
    python = Path(os.path.abspath(resolve_python_path(defaults, approach)))
    if not python.is_file():
        raise SystemExit(f"Approach Python was not found: {python}. Run setup_approach.py first.")

    ensure_webservice_dependencies(python)
    settings_path = make_flowcept_settings(args.approach, defaults, approach).resolve()
    env = os.environ.copy()
    env["FLOWCEPT_SETTINGS_PATH"] = str(settings_path)

    base_command = [
        str(python),
        "-m",
        "flowcept.cli",
    ]
    server_args = ["--webservice-host", args.host, "--webservice-port", str(args.port)]

    print(f"Approach: {args.approach}")
    print(f"MongoDB: {approach['mongo_db']}")
    print(f"Settings: {settings_path}")

    if packaged_ui_exists(python):
        print(f"UI: http://{args.host}:{args.port}")
        command = [*base_command, "--start-webservice", *server_args]
        subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
        return

    source_dir = find_flowcept_source(args.flowcept_source)
    if source_dir is None:
        raise SystemExit(
            "The installed Flowcept has no bundled UI and no Flowcept source checkout was found. "
            "Pass --flowcept-source /path/to/flowcept or set FLOWCEPT_SOURCE_DIR."
        )

    ui_dir = source_dir / "ui"
    if not (ui_dir / "node_modules").exists():
        raise SystemExit(f"UI dependencies are missing. Run: npm install --prefix {ui_dir}")

    print("UI: http://localhost:5173")
    print(f"API: http://{args.host}:{args.port}")
    command = [*base_command, "--start-ui", *server_args, "--ui-dir", str(ui_dir)]
    subprocess.run(command, cwd=source_dir, env=env, check=False)


if __name__ == "__main__":
    main()
