# Message Stream Observability

Paper label: **Message Stream Observability**

This approach observes Academy Redis/message-stream activity externally and
turns observed messages into Flowcept provenance records.

Implementation:

```text
approaches/message_stream_observability/src/perceptron_gridsearch
```

Configured experiment name:

```text
message_stream_observability_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_message_stream_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/message_stream_observability_perceptron_gridsearch/flowcept_settings.yaml
```

## Instrumentation and Configuration

This approach observes Academy's Redis/message stream externally and converts
observed messages into Flowcept records. The application is not directly
instrumented with Flowcept calls.

The setup installs the Flowcept implementation that contains the Academy
message-stream adapter:

```text
https://github.com/valescamoura/flowcept@academy_plugin
```

The adapter/configuration is prepared from `experiments/config/approaches.yaml`
and written into the generated Flowcept settings YAML. MongoDB and Redis must be
running before the experiment starts.

## Run

Run from the repository root. MongoDB and Redis should already be running.

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach message_stream_observability_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach message_stream_observability_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach message_stream_observability_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. To customize
capture behavior, edit `experiments/config/approaches.yaml` or the generated
Flowcept settings YAML.
