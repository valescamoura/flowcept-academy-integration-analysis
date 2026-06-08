# Experiments Harness

Utilities to run the Flowcept + Academy integration approaches, keep one MongoDB
database per approach, and generate comparable analysis artifacts.

## Layout

```text
experiments/
  config/
    approaches.yaml      # approach commands, cwd, Mongo database names
    schema_fields.yaml   # required/optional/not-applicable field expectations
  scripts/
    run_approach.py
    analyze_overhead.py
    analyze_schema_coverage.py
    analyze_queryability.py
  results/
    <approach>/
      runs.csv
      run_001/
        stdout.log
        stderr.log
        run_metadata.json
```

## Prepare Root Experiment Environment

The root environment runs the experiment harness itself: setup scripts, runner,
analysis scripts, Mongo queries, and runner-level CPU/memory sampling. Each
approach still has its own venv under `approaches/<approach>/.venv`.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install pymongo pyyaml psutil
python -m pip install flowcept==0.10.4 flowcept[extras]
```

`psutil` is required by `run_approach.py` to collect runner-level CPU and memory
metrics. The runner fails before starting experiments when `psutil` is missing,
so long batches do not silently produce empty CPU/memory columns. Use
`--no-resource-metrics` only when you intentionally want to skip these metrics.

## Run Experiments

Run setup for one approach:

```bash
python experiments/scripts/setup_approach.py --approach event_log_observability
```

Preview setup commands without executing them:

```bash
python experiments/scripts/setup_approach.py --approach all --dry-run
```

Run one approach:

```bash
python experiments/scripts/run_approach.py --approach event_log_observability --runs 30
```

Run every enabled approach in `config/approaches.yaml`:

```bash
python experiments/scripts/run_approach.py --approach all --runs 30
```

Use `--clean-db` to drop the approach Mongo database before running:

```bash
python experiments/scripts/run_approach.py --approach event_log_observability --runs 30 --clean-db
```

Use `--clean-results` to remove local run logs/CSV before running:

```bash
python experiments/scripts/run_approach.py --approach event_log_observability --runs 30 --clean-db --clean-results
```

The runner creates a Flowcept settings file per approach under
`experiments/results/<approach>/flowcept_settings.yaml` and executes the approach
with `FLOWCEPT_SETTINGS_PATH` pointing to that file. The settings file is copied
from the current Flowcept settings when available, then only the Mongo database
name is changed.

Flowcept telemetry is configured in `approaches.yaml` under
`defaults.flowcept.telemetry_capture` and can be overridden per approach. The
generated Flowcept settings file receives that block as `telemetry_capture`.

In `approaches.yaml`, use `{python}` in `command` to refer to the configured
Python for that approach. Setup commands are executed literally, so they should
call the venv path explicitly after creating it.

Approach-level `env` entries are merged into the current process environment.
They add or override only the configured keys; the rest of the environment is
preserved. The value `{repo_root}` expands to the repository root.

## Run Analyses

Overhead and terminal/runtime metrics:

```bash
python experiments/scripts/analyze_overhead.py --approach all
```

Schema/data coverage from Mongo:

```bash
python experiments/scripts/analyze_schema_coverage.py --approach all
```

Schema/data coverage through the official Flowcept Python DB API:

```bash
python experiments/scripts/analyze_schema_coverage_flowcept.py --approach all
```

Queryability benchmark:

```bash
python experiments/scripts/analyze_queryability.py --approach all
```

## Methodological Notes

- MongoDB is treated as the canonical post-execution store.
- Redis and JSONL are transport/debug artifacts.
- One Mongo database is used per approach.
- Multiple runs of the same approach are stored in the same approach database.
- Baseline runs can be configured with `uses_flowcept: false`; they still produce
  runtime/log metrics but no Flowcept schema/queryability metrics.
