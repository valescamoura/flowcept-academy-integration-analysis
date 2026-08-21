# Experiments Harness

Utilities to run the Flowcept + Academy integration approaches, keep one MongoDB
database per approach, and generate comparable analysis artifacts.

## Layout

```text
experiments/
  config/
    approaches.yaml              # approach commands, cwd, Mongo database names
    approach_labels.yaml         # labels used in tables and reports
    mapping.md                   # human-editable official coverage mapping
    coverage_mapping.yaml        # generated YAML consumed by coverage scripts
  scripts/
    run_approach.py
    setup_approach.py
    summarize_mongodb_data_volume.py
    analyze_overhead.py
    build_coverage_mapping.py
    generate_field_coverage_tables.py
    generate_field_coverage_figures.py
    generate_executive_html_reports.py
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

## Current Analysis Workflow

These are the maintained analysis commands for the Perceptron GridSearch use case.
Run them from the repository root with the root `.venv` active.

### Amount of Data

```bash
.venv/bin/python experiments/scripts/summarize_mongodb_data_volume.py \
  --approach all \
  --use-case perceptron_gridsearch
```

Main output:

```text
experiments/results/_analysis/mongodb_data_volume_perceptron_gridsearch.md
```

### Overhead

```bash
.venv/bin/python experiments/scripts/analyze_overhead.py \
  --use-case perceptron_gridsearch
```

Main output:

```text
experiments/results/_analysis/overhead_perceptron_gridsearch.md
```

### Coverage

The human-editable official mapping is:

```text
experiments/config/mapping.md
```

It contains the mapping for analytical capabilities, provenance data categories,
and persona questions. The persona-question table drives the persona heatmap and
the question coverage grouped bar plot.

The scripts consume the generated YAML mapping:

```text
experiments/config/coverage_mapping.yaml
```

Regenerate the YAML after editing the official markdown table:

```bash
.venv/bin/python experiments/scripts/build_coverage_mapping.py
```

Then regenerate coverage tables:

```bash
.venv/bin/python experiments/scripts/generate_field_coverage_tables.py \
  --approach all \
  --use-case perceptron_gridsearch
```

Main outputs:

```text
experiments/results/_analysis/field_coverage_tables_perceptron_gridsearch.md
experiments/results/_analysis/approach_field_coverage_perceptron_gridsearch/README.md
```

Coverage includes four views:

- Semanticless unique field count.
- Flowcept schema groups.
- Analytical capabilities.
- Provenance data categories.

Two semantic record-presence indicators are counted as pseudo-fields:

- `task.record_type.subtype.agent_communication`: counted when at least one task has `subtype="agent_communication"`.
- `task.record_type.subtype.academy_lifecycle`: counted when at least one task has `subtype="academy_lifecycle"`.

`task.execution_metadata.stderr` is conditional: it is included only for approaches
that produced at least one errored task with non-empty `stderr`.

### Visualizations

```bash
.venv/bin/python experiments/scripts/generate_field_coverage_figures.py \
  --use-case perceptron_gridsearch
```

Main output:

```text
experiments/results/_analysis/field_coverage_figures_perceptron_gridsearch/README.md
```

### HTML Reports

```bash
.venv/bin/python experiments/scripts/generate_executive_html_reports.py \
  --use-case perceptron_gridsearch
```

Main outputs:

```text
experiments/results/_analysis/perceptron_gridsearch_executive_plots.html
experiments/results/_analysis/perceptron_gridsearch_executive_summary.html
```

## Methodological Notes

- MongoDB is treated as the canonical post-execution store.
- Redis and JSONL are transport/debug artifacts.
- One Mongo database is used per approach.
- Multiple runs of the same approach are stored in the same approach database.
- Baseline runs can be configured with `uses_flowcept: false`; they still produce
  runtime/log metrics but no Flowcept schema/queryability metrics.
