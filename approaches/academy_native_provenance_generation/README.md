# Academy Native Provenance Generation

Paper label: **Direct Framework Instrumentation**

This approach uses an Academy version that emits/manages Flowcept provenance
inside the framework.

Implementation:

```text
approaches/academy_native_provenance_generation/src/perceptron_gridsearch
```

Configured experiment name:

```text
academy_native_provenance_generation_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_academy_native_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/academy_native_provenance_generation_perceptron_gridsearch/flowcept_settings.yaml
```

## Instrumentation and Configuration

Instrumentation comes from the installed Academy version itself. The setup uses:

```text
academy-py @ git+https://github.com/valescamoura/academy@flowcept_integration
```

The experiment enables the native Academy/Flowcept path with:

```text
ACADEMY_FLOWCEPT_ENABLED=1
```

There is no separate handler or message-stream observer to start. The generated
YAML controls MongoDB, Redis, telemetry, and Flowcept runtime settings.

## Run

Run from the repository root. MongoDB and Redis should already be running.

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach academy_native_provenance_generation_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach academy_native_provenance_generation_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach academy_native_provenance_generation_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. If you know
Flowcept and want to tune capture behavior, edit the generated YAML or
`experiments/config/approaches.yaml`.
