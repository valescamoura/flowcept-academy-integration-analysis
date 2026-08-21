# OpenTelemetry Integration

Paper label: **Third-party Adapters**

This approach captures provenance through an OpenTelemetry/OpenInference path.
The experiment runner starts the required local services for this approach,
runs the Perceptron GridSearch use case, and persists the converted Flowcept
records.

Implementation:

```text
approaches/opentelemetry_integration/src/perceptron_gridsearch
```

Configured experiment name:

```text
opentelemetry_integration_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_opentelemetry_perceptron_gridsearch
```

Generated Flowcept settings:

```text
experiments/results/opentelemetry_integration_perceptron_gridsearch/flowcept_settings.yaml
```

Service logs are written under:

```text
experiments/results/opentelemetry_integration_perceptron_gridsearch/services
```

## Instrumentation and Configuration

This approach uses Academy instrumentation through OpenInference and exports
spans through OpenTelemetry. The service manager starts the OpenTelemetry
Collector and Flowcept consumption services for this approach.

The setup installs Academy and OpenInference from the experiment branches:

```text
academy-py @ git+https://github.com/valescamoura/academy@openinference_instrumentation
openinference-* @ git+https://github.com/valescamoura/openinference@academy
```

The Collector source is configured in `experiments/config/approaches.yaml`:

```text
https://github.com/valescamoura/opentelemetry-collector@flowcept_academy_exporter
```

The generated YAML controls MongoDB, Redis, telemetry, and Flowcept runtime
settings. The OpenTelemetry endpoint and service name are also configured by
the approach environment.

## Requirements

Run from the repository root. MongoDB and Redis should already be running.
This approach also needs Go because the service manager runs the configured
OpenTelemetry Collector from source.

The setup script installs the Python dependencies declared for this approach.
The service manager prepares and starts the OpenTelemetry Collector and
Flowcept consumption services.

## Run

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --start

.venv/bin/python experiments/scripts/run_approach.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --runs 3 \
  --clean-db

.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --stop
```

To inspect service status while debugging:

```bash
.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --status
```

## UI

```bash
.venv/bin/python experiments/scripts/start_approach_ui.py \
  --approach opentelemetry_integration_perceptron_gridsearch
```

The script prints the UI URL, MongoDB database, and settings path. Advanced
Flowcept users can edit the generated settings YAML or
`experiments/config/approaches.yaml`.
