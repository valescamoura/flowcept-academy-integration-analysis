# Academy Perceptron GridSearch

This use case demonstrates an Academy multi-agent workflow around a small
single-layer perceptron grid search. The baseline implementation intentionally
does not import or call Flowcept.

The baseline entrypoint launches all three agents as independent Python
subprocesses. Each subprocess runs one Academy `Runtime`, and all agent actions
are exchanged through Redis. This simulates a distributed deployment without
using Parsl or another workflow/HPC launcher.

## Agents

- `OrchestratorAgent`: receives handles to the other agents, requests the
  grid-search plan, sends the training work, and asks for final model
  selection.
- `TrainingWorkerAgent`: prepares dataset/config values, generates the toy
  binary-classification dataset, trains one candidate model per config, and
  writes checkpoint artifacts.
- `EvaluatorAgent`: receives training results and selects the model with the
  lowest validation loss.

## Baseline Outputs

The baseline entrypoint writes:

- `perceptron_gridsearch_summary.json`
- `artifacts/*.pt`

The default baseline uses 2,000 synthetic samples and five candidate
configurations with 20, 40, 60, 100, and 140 training epochs. This keeps the
workflow small enough for repeated local runs while making the training phase
visible relative to Academy, Redis, and subprocess startup overhead.

## Future Approach Ports

The same `use_cases.perceptron_gridsearch` core should be reused by the
Flowcept-enabled approaches so the experimental behavior stays comparable and
only the instrumentation strategy changes.
