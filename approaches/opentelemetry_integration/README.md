# OpenTelemetry + OpenInference Integration

This approach uses the Academy OpenInference instrumentor to generate
OpenTelemetry traces and an OpenTelemetry Collector exporter to convert those
spans into Flowcept objects.

The example runs a small distributed-style Academy Fibonacci use case:

- `FibonacciCoordinator` is an Academy `AGENT`.
- `FibonacciWorker` is another Academy `AGENT`.
- `FibonacciCoordinator.generate()` calls `FibonacciWorker.next_fibonacci()`.
- OpenInference emits:
  - one `CHAIN` span for the workflow,
  - one `AGENT` span for the coordinator,
  - one nested `AGENT` span for the worker,
  - one `TOOL` span per Academy action call.
- The Collector exporter publishes Flowcept `workflow` and `task` objects to
  Redis.
- The Flowcept consumer persists those objects in the configured Flowcept DB.

## Expected Mapping

```text
OpenInference CHAIN -> Flowcept WorkflowObject
OpenInference TOOL  -> Flowcept TaskObject
OpenInference AGENT -> Flowcept AgentObject
```

The generated Flowcept tasks should include:

- `subtype = academy_action`
- `agent_id`, `agent_name`
- `source_agent_id`, `source_agent_name` when the source is another agent
- `telemetry_at_start`
- `telemetry_at_end`
- `custom_metadata.telemetry_runtime_at_start`
- `custom_metadata.telemetry_runtime_at_end`

The generated Flowcept agents should include:

- `agent_id`
- `name`
- `workflow_id`
- `campaign_id`

## Requirements

- Redis running on `127.0.0.1:6379`.
- A Flowcept environment that can run the consumer and query the configured DB.
- Go installed for running the Collector from source.
- `uv` installed for running the Python example.

The Perceptron GridSearch service manager clones/updates the Collector from:

- `https://github.com/valescamoura/opentelemetry-collector/tree/flowcept_academy_exporter`

The OpenInference dependency comes from:

- `https://github.com/valescamoura/openinference/tree/academy`

The Academy dependency comes from:

- `https://github.com/valescamoura/academy/tree/openinference_instrumentation`

## 1. Start Redis

If Redis is already running for your experiments, keep using that instance.

Quick check:

```bash
redis-cli ping
```

Expected:

```text
PONG
```

## 2. Start Flowcept Consumption Services

Run this in the Python environment where Flowcept is configured:

```bash
uv run flowcept --start-consumption-services
```

Check which DB Flowcept is using:

```bash
uv run flowcept --show-settings
```

The Collector publishes to Redis channel `interception`, so the Flowcept
consumer must be running while the example sends traces.

## 3. Run the Collector

For the manual Fibonacci example, clone the same Collector branch used by the
service manager:

```bash
mkdir -p /tmp/flowcept-academy-otel
cd /tmp/flowcept-academy-otel

git clone --branch flowcept_academy_exporter \
  https://github.com/valescamoura/opentelemetry-collector.git

cd opentelemetry-collector/cmd/otelcorecol

go run . \
  --config /Users/valesca/Documents/projects/flowcept-academy-integration-playground/approaches/opentelemetry_integration/otelcol-flowcept-academy.yaml
```

To test an unpublished local Collector checkout instead, set:

```bash
OTEL_COLLECTOR_DIR=/path/to/opentelemetry-collector/cmd/otelcorecol
```

Leave this process running. It listens for OTLP traces on:

- gRPC: `127.0.0.1:14317`
- HTTP: `127.0.0.1:14318`

It publishes Flowcept objects to:

- Redis: `127.0.0.1:6379`
- channel: `interception`
- campaign: `academy-openinference-fibonacci`

## 4. Run the Academy Fibonacci Example

In another terminal:

```bash
cd /Users/valesca/Documents/projects/flowcept-academy-integration-playground/approaches/opentelemetry_integration

OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:14317 \
OTEL_EXPORTER_OTLP_INSECURE=true \
OTEL_SERVICE_NAME=academy-openinference-fibonacci \
FLOWCEPT_CAMPAIGN_ID=academy-openinference-fibonacci \
FIBONACCI_LIMIT=1000 \
uv run \
  --with "academy-py" \
  --with "psutil" \
  --with "opentelemetry-sdk" \
  --with "opentelemetry-exporter-otlp-proto-grpc" \
  --with "openinference-instrumentation @ git+https://github.com/valescamoura/openinference.git@academy#subdirectory=python/openinference-instrumentation" \
  --with "openinference-semantic-conventions @ git+https://github.com/valescamoura/openinference.git@academy#subdirectory=python/openinference-semantic-conventions" \
  --with "openinference-instrumentation-academy @ git+https://github.com/valescamoura/openinference.git@academy#subdirectory=python/instrumentation/openinference-instrumentation-academy" \
  src/fibonacci_openinference.py
```

`psutil` is included so the telemetry snapshots contain richer CPU, memory,
disk, network, and process information. Without `psutil`, the instrumentor still
captures a smaller stdlib-only process snapshot.

Expected console output:

```text
Fibonacci values below 1000: [1, 1, 2, 3, 5, ...]
```

## 5. Query Flowcept

After the example finishes and the consumer has processed the Redis messages:

```bash
cd flowcept-academy-integration-playground/approaches/opentelemetry_integration

FLOWCEPT_CAMPAIGN_ID=academy-openinference-fibonacci \
uv run \
  --with "flowcept" \
  src/query_flowcept.py
```

If you are using a local editable Flowcept checkout for development, run the
same script from that environment instead:

```bash
FLOWCEPT_CAMPAIGN_ID=academy-openinference-fibonacci \
uv run python src/query_flowcept.py
```

You should see one workflow and several `academy.action` tasks. The worker tasks
should show:

- `agent_name = FibonacciWorker`
- `source_agent_name = FibonacciCoordinator`
- non-empty `telemetry_at_start`
- non-empty `telemetry_at_end`

## Perceptron GridSearch Use Case

The Perceptron GridSearch experiment is integrated with the shared experiment
runner:

```bash
cd /Users/valesca/Documents/projects/flowcept-academy-integration-playground

.venv/bin/python experiments/scripts/setup_approach.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --start

.venv/bin/python experiments/scripts/run_approach.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --runs 1 \
  --clean-db

.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --stop
```

The service manager starts the Flowcept consumption services and clones/updates
the Collector branch configured in `experiments/config/approaches.yaml`.
`run_approach.py` runs only the three Academy agent processes and the workflow,
so run timing does not include service startup.

For local Collector development, override the checkout with `OTEL_COLLECTOR_DIR`:

```bash
OTEL_COLLECTOR_DIR=/path/to/opentelemetry-collector/cmd/otelcorecol \
.venv/bin/python experiments/scripts/manage_approach_services.py \
  --approach opentelemetry_integration_perceptron_gridsearch \
  --start
```

## 6. Stop Services

Stop the Collector with `Ctrl+C`.

Stop Flowcept consumption services:

```bash
uv run flowcept --stop-consumption-services
```

## Notes

This example uses `LocalExchangeFactory` for Academy agent communication. Redis
is used only by the Flowcept ingestion path:

```text
Academy -> OpenInference spans -> OTLP Collector -> Redis -> Flowcept consumer -> Flowcept DB
```

That keeps the experiment focused on the new OpenTelemetry/OpenInference
integration rather than on Redis-backed Academy exchange behavior.
