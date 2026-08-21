# Baseline

Paper label: **Baseline**

This approach runs the Perceptron GridSearch use case without Flowcept
instrumentation. It is the no-provenance baseline used for runtime/resource
comparison.

Implementation:

```text
approaches/baseline/src/perceptron_gridsearch
```

Configured experiment name:

```text
baseline_perceptron_gridsearch
```

Configured MongoDB name:

```text
flowcept_baseline_perceptron_gridsearch
```

## Instrumentation and Configuration

This is the no-provenance baseline. It installs the same Academy version used by
the other non-native approaches:

```text
https://github.com/academy-agents/academy@1c9dd5bbe030e562101a30dd4dfa1b5b0dffff4d
```

No Flowcept handler, adapter, plugin, or UI is configured for this approach.
The run script only records experiment logs and runtime/resource measurements.

The baseline does not use Flowcept, so there is no Flowcept UI for this
approach. The runner still records logs and runtime/resource measurements under
`experiments/results/baseline_perceptron_gridsearch/`.

## Run

Run from the repository root:

```bash
.venv/bin/python experiments/scripts/setup_approach.py \
  --approach baseline_perceptron_gridsearch \
  --force

.venv/bin/python experiments/scripts/run_approach.py \
  --approach baseline_perceptron_gridsearch \
  --runs 3 \
  --clean-db
```

Per-run outputs are written to:

```text
experiments/results/baseline_perceptron_gridsearch/run_001/
experiments/results/baseline_perceptron_gridsearch/run_002/
experiments/results/baseline_perceptron_gridsearch/run_003/
```
