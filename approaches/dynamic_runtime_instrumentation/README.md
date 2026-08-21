# Dynamic Runtime Instrumentation

Paper label: **Dynamic Framework Instrumentation**

This approach enables Flowcept capture through a runtime Academy plugin. The
application code stays close to the baseline; instrumentation is activated from
Flowcept settings.

Implementation:

```text
approaches/dynamic_runtime_instrumentation/src/perceptron_gridsearch
```

Configured experiment name:

```text
dynamic_runtime_instrumentation_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_dynamic_runtime_instrumentation_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/dynamic_runtime_instrumentation_perceptron_gridsearch/flowcept_settings.yaml
```

## Instrumentation and Configuration

Instrumentation is activated by Flowcept's runtime Academy plugin, not by edits
inside the application workflow. The setup installs the Flowcept implementation
that provides this plugin:

```text
https://github.com/GueroudjiAmal/flowcept@merge-fc-ui-into-agentic
```

The generated settings include the Academy plugin block:

```yaml
plugins:
  academy:
    enabled: true
    kind: academy
```

The run script generates this YAML from `experiments/config/approaches.yaml`.
Advanced users can edit either file to change the plugin, MongoDB, Redis, or
telemetry configuration.

## Run

Run from the repository root. MongoDB and Redis should already be running.

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach dynamic_runtime_instrumentation_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach dynamic_runtime_instrumentation_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach dynamic_runtime_instrumentation_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. Advanced
Flowcept users can edit the generated settings YAML or
`experiments/config/approaches.yaml`.
