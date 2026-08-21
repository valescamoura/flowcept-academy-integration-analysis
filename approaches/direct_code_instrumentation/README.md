# Direct Code Instrumentation

Paper label: **Direct Application Instrumentation**

This approach embeds Flowcept calls/decorators directly in the application
workflow code.

Implementation:

```text
approaches/direct_code_instrumentation/src/perceptron_gridsearch
```

Configured experiment name:

```text
direct_code_instrumentation_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_direct_code_instrumentation_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/direct_code_instrumentation_perceptron_gridsearch/flowcept_settings.yaml
```

## Instrumentation and Configuration

Instrumentation is written directly in the use-case code with Flowcept API calls
and decorators. There is no separate observer process and no adapter to start.

The setup installs Flowcept from:

```text
https://github.com/ORNL/flowcept@fc_ui
```

The generated YAML controls MongoDB, Redis, telemetry, and Flowcept runtime
settings. The run script creates this YAML from
`experiments/config/approaches.yaml` before executing the experiment.

## Run

Run from the repository root. MongoDB and Redis should already be running.

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach direct_code_instrumentation_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach direct_code_instrumentation_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach direct_code_instrumentation_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. If you need
to change MongoDB, Redis, telemetry, or Flowcept options, edit
`experiments/config/approaches.yaml` or the generated settings YAML.
