# Event Log Observability

Paper label: **Log Handler-based Observability**

This approach observes structured Academy log events and translates them into
Flowcept provenance records.

Implementation:

```text
approaches/event_log_observability/src/perceptron_gridsearch
```

Configured experiment name:

```text
event_log_observability_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_event_log_observability_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/event_log_observability_perceptron_gridsearch/flowcept_settings.yaml
```

## Instrumentation and Configuration

This approach uses the `FlowceptLogging` handler from:

```text
https://github.com/valescamoura/academy-flowcept
```

The handler is instantiated inside the experiment code and attached through
Academy's logging context. You do not need to configure or start it manually:
`setup_approach.py` installs the handler package, and `run_approach.py` executes
the code path that creates it.

The generated YAML controls MongoDB, Redis, telemetry, and Flowcept runtime
settings. The run script creates this YAML from
`experiments/config/approaches.yaml` before executing the experiment.

## Run

Run from the repository root. MongoDB and Redis should already be running.

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach event_log_observability_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach event_log_observability_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach event_log_observability_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. To change DB,
Redis, telemetry, or Flowcept settings, edit `experiments/config/approaches.yaml`
or the generated settings YAML.
