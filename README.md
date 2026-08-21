# Instrumentation vs. Observability Experiments

This repository contains the experiment harness for the paper
**Instrumentation vs. Observability: Provenance Capture Trade-offs in Agentic Workflows**.

It includes the use case used in the paper, ready-to-run implementations of each
provenance capture approach, configured dependency environments, run scripts,
MongoDB/Flowcept settings generation, and analysis scripts.

## Repository Layout

- `use_cases/`: shared use-case code used by the approaches.
- `approaches/`: one implementation per provenance capture approach.
- `experiments/config/approaches.yaml`: source of truth for commands, MongoDB
  names, environment variables, setup commands, and generated Flowcept settings.
- `experiments/scripts/`: setup, run, UI, service, and analysis scripts.
- `experiments/results/`: generated logs, metrics, settings, DB snapshots, and
  analysis outputs.

The current paper use case is `perceptron_gridsearch`. Each approach directory
contains the implementation for that approach; the step-by-step commands are in
the approach README. Each approach README also notes where its instrumentation
comes from, such as direct Flowcept calls, a logging handler, an Academy branch,
a Flowcept plugin, or OpenTelemetry services.

## Names in Code vs. Paper

Directory/config names are implementation-oriented. The paper labels are:

| Config prefix | Paper label |
| --- | --- |
| `baseline` | Baseline |
| `direct_code_instrumentation` | Direct Application Instrumentation |
| `academy_native_provenance_generation` | Direct Framework Instrumentation |
| `dynamic_runtime_instrumentation` | Dynamic Framework Instrumentation |
| `event_log_observability` | Log Handler-based Observability |
| `message_stream_observability` | Message Stream Observability |
| `opentelemetry_integration` | Third-party Adapters |

For the paper use case, the full config names add the suffix
`_perceptron_gridsearch`, for example
`direct_code_instrumentation_perceptron_gridsearch`.

## Basic Setup

Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install pymongo pyyaml psutil
```

MongoDB must be running and reachable using the host/port in
`experiments/config/approaches.yaml` (`localhost:27017` by default). Flowcept
approaches also expect Redis on `localhost:6379`.

## Running Experiments

Use this pattern for any configured approach:

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach <approach_name> \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach <approach_name> \
  --runs 3 \
  --clean-db
```

For Flowcept approaches, the runner writes generated settings to:

```text
experiments/results/<approach_name>/flowcept_settings.yaml
```

If you know Flowcept well, edit that YAML or
`experiments/config/approaches.yaml` to change DBs, Redis, telemetry, plugins,
or other settings.

Per-approach instructions:

- `approaches/baseline/README.md`
- `approaches/direct_code_instrumentation/README.md`
- `approaches/academy_native_provenance_generation/README.md`
- `approaches/dynamic_runtime_instrumentation/README.md`
- `approaches/event_log_observability/README.md`
- `approaches/message_stream_observability/README.md`
- `approaches/opentelemetry_integration/README.md`

## Viewing Captured Data

For approaches that use Flowcept:

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach <approach_name>
```

The script prints the MongoDB database, settings path, and UI URL. If using a
local Flowcept checkout without packaged UI assets, install UI dependencies once:

```bash
npm install --prefix /path/to/flowcept/ui
```

Then either set `FLOWCEPT_SOURCE_DIR=/path/to/flowcept` or pass
`--flowcept-source /path/to/flowcept`.

## Analysis Commands

After runs are complete:

```bash
.venv/bin/python experiments/scripts/build_coverage_mapping.py

.venv/bin/python experiments/scripts/summarize_mongodb_data_volume.py \
  --approach all \
  --use-case perceptron_gridsearch

.venv/bin/python experiments/scripts/analyze_overhead.py \
  --use-case perceptron_gridsearch

.venv/bin/python experiments/scripts/generate_field_coverage_tables.py \
  --approach all \
  --use-case perceptron_gridsearch

.venv/bin/python experiments/scripts/generate_field_coverage_figures.py \
  --use-case perceptron_gridsearch

.venv/bin/python experiments/scripts/generate_executive_html_reports.py \
  --use-case perceptron_gridsearch
```

Main outputs are written under:

```text
experiments/results/_analysis/
```

Paper-ready figures are under:

```text
experiments/resultspaper/
```
