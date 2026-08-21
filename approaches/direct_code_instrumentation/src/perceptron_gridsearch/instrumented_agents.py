from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

from academy.agent import Agent, action
from flowcept import Flowcept, flowcept_task

from use_cases.perceptron_gridsearch.core import (
    DatasetConfig,
    TrainingConfig,
    default_dataset_config,
    default_gridsearch_configs,
    dataset_summary,
    generate_dataset as generate_dataset_data,
    new_dataset_id,
    select_best_model,
    set_reproducibility,
    train_and_validate,
)


logger = logging.getLogger(__name__)
_GENERATED_DATASETS = {}


def domain_args_handler(**kwargs):
    return {
        key: value
        for key, value in kwargs.items()
        if key
        not in {
            "self",
            "agent",
            "training_worker",
            "evaluator",
            "x_train",
            "y_train",
            "x_val",
            "y_val",
        }
    }


@contextmanager
def flowcept_worker_context():
    workflow_id = os.environ.get("FLOWCEPT_DIRECT_WORKFLOW_ID")
    campaign_id = os.environ.get("FLOWCEPT_DIRECT_CAMPAIGN_ID")
    with Flowcept(
        workflow_id=workflow_id,
        campaign_id=campaign_id,
        workflow_name="academy_perceptron_gridsearch_direct_code_instrumentation_worker",
        workflow_subtype="academy_perceptron_gridsearch_worker",
        start_persistence=False,
        check_safe_stops=False,
        save_workflow=False,
    ):
        yield


class InstrumentedTrainingWorkerAgent(Agent):
    @action
    async def prepare_gridsearch(self, n_configs: int = 5, source_agent_id: str | None = None):
        agent_id = str(self.agent_id.uid)
        with flowcept_worker_context():
            return await prepare_gridsearch(
                n_configs=n_configs,
                agent_id=agent_id,
                source_agent_id=source_agent_id,
            )

    @action
    async def generate_dataset(self, dataset_config, source_agent_id: str | None = None):
        agent_id = str(self.agent_id.uid)
        with flowcept_worker_context():
            summary = await generate_dataset(
                dataset_config=dataset_config,
                agent_id=agent_id,
                source_agent_id=source_agent_id,
            )
        dataset_id = summary["dataset_id"]
        x_train, y_train, x_val, y_val = _GENERATED_DATASETS.pop(dataset_id)
        self._dataset = {
            "x_train": x_train,
            "y_train": y_train,
            "x_val": x_val,
            "y_val": y_val,
            "dataset_id": dataset_id,
        }
        summary["agent_pid"] = os.getpid()
        return summary

    @action
    async def train_config(
        self,
        config,
        artifact_dir: str,
        checkpoint_check: int = 2,
        source_agent_id: str | None = None,
    ):
        dataset = self._dataset
        agent_id = str(self.agent_id.uid)
        with flowcept_worker_context():
            result = await train_config(
                config=config,
                dataset_id=dataset["dataset_id"],
                x_train=dataset["x_train"],
                y_train=dataset["y_train"],
                x_val=dataset["x_val"],
                y_val=dataset["y_val"],
                artifact_dir=artifact_dir,
                checkpoint_check=checkpoint_check,
                agent_id=agent_id,
                source_agent_id=source_agent_id,
            )
        logger.info(
            "trained gridsearch config",
            extra={
                "academy.agent_id": self.agent_id,
                "pid": os.getpid(),
                "config_id": config["config_id"],
            },
        )
        return result


class InstrumentedEvaluatorAgent(Agent):
    @action
    async def select_best(self, results, source_agent_id: str | None = None):
        agent_id = str(self.agent_id.uid)
        with flowcept_worker_context():
            selection = await select_best(
                results=results,
                agent_id=agent_id,
                source_agent_id=source_agent_id,
            )
        selection["agent_pid"] = os.getpid()
        return selection


class InstrumentedOrchestratorAgent(Agent):
    def __init__(self, training_worker, evaluator):
        super().__init__()
        self.training_worker = training_worker
        self.evaluator = evaluator

    @action
    async def run_gridsearch(self, artifact_dir: str, n_configs: int = 5, checkpoint_check: int = 2):
        agent_id = str(self.agent_id.uid)
        with flowcept_worker_context():
            return await run_gridsearch(
                agent=self,
                training_worker=self.training_worker,
                evaluator=self.evaluator,
                artifact_dir=artifact_dir,
                n_configs=n_configs,
                checkpoint_check=checkpoint_check,
                agent_id=agent_id,
            )


@flowcept_task(
    output_names="gridsearch_plan",
    args_handler=domain_args_handler,
    subtype="academy_action",
    tags=["academy", "perceptron_gridsearch", "agent-action", "domain"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "prepare_gridsearch",
    },
)
async def prepare_gridsearch(
    n_configs: int,
    agent_id: str,
    source_agent_id: str | None,
):
    dataset_config = default_dataset_config()
    configs = default_gridsearch_configs(n_configs=n_configs)
    logger.info("prepared gridsearch configs", extra={"academy.agent_id": agent_id, "pid": os.getpid()})
    return {
        "dataset_config": dataset_config.__dict__,
        "configs": [cfg.__dict__ for cfg in configs],
        "agent_pid": os.getpid(),
    }


@flowcept_task(
    output_names="dataset_summary",
    args_handler=domain_args_handler,
    subtype="academy_action",
    tags=["academy", "perceptron_gridsearch", "agent-action", "domain", "data"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "generate_dataset",
    },
)
async def generate_dataset(
    dataset_config,
    agent_id: str,
    source_agent_id: str | None,
):
    x_train, y_train, x_val, y_val = generate_dataset_data(DatasetConfig(**dataset_config))
    dataset_id = new_dataset_id()
    _GENERATED_DATASETS[dataset_id] = (x_train, y_train, x_val, y_val)
    logger.info("generated dataset", extra={"academy.agent_id": agent_id, "pid": os.getpid()})
    return dataset_summary(x_train, y_train, x_val, y_val, dataset_id)


@flowcept_task(
    args_handler=domain_args_handler,
    subtype="academy_action",
    tags=["academy", "perceptron_gridsearch", "agent-action", "domain", "training"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "train_config",
    },
)
async def train_config(
    config,
    dataset_id: str,
    x_train,
    y_train,
    x_val,
    y_val,
    artifact_dir: str,
    checkpoint_check: int,
    agent_id: str,
    source_agent_id: str | None,
):
    cfg = TrainingConfig(**config)
    result = train_and_validate(
        config=cfg,
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        artifact_dir=Path(artifact_dir),
        checkpoint_check=checkpoint_check,
    )
    result["agent_pid"] = os.getpid()
    logger.info(
        "trained gridsearch config",
        extra={
            "academy.agent_id": agent_id,
            "pid": os.getpid(),
            "dataset_id": dataset_id,
            "config_id": cfg.config_id,
        },
    )
    return result


@flowcept_task(
    output_names="selection",
    args_handler=domain_args_handler,
    subtype="academy_action",
    tags=["academy", "perceptron_gridsearch", "agent-action", "domain", "evaluation"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "select_best",
    },
)
async def select_best(
    results,
    agent_id: str,
    source_agent_id: str | None,
):
    selection = select_best_model(results)
    logger.info("selected best model", extra={"academy.agent_id": agent_id, "pid": os.getpid()})
    return selection


@flowcept_task(
    output_names="gridsearch_summary",
    args_handler=domain_args_handler,
    subtype="academy_action",
    tags=["academy", "perceptron_gridsearch", "agent-action", "orchestration"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "instrumented_layer": "agent_orchestration_code",
        "academy_action": "run_gridsearch",
    },
)
async def run_gridsearch(
    agent,
    training_worker,
    evaluator,
    artifact_dir,
    n_configs,
    checkpoint_check,
    agent_id: str,
):
    orchestrator_pid = os.getpid()
    logger.info(
        "started perceptron gridsearch orchestration",
        extra={"academy.agent_id": agent.agent_id, "pid": orchestrator_pid},
    )
    reproducibility = set_reproducibility(seed=42)

    plan = await training_worker.prepare_gridsearch(
        n_configs=n_configs,
        source_agent_id=agent_id,
    )
    dataset = await training_worker.generate_dataset(
        plan["dataset_config"],
        source_agent_id=agent_id,
    )
    results = []
    for config in plan["configs"]:
        result = await training_worker.train_config(
            config=config,
            artifact_dir=artifact_dir,
            checkpoint_check=checkpoint_check,
            source_agent_id=agent_id,
        )
        results.append(result)
    selection = await evaluator.select_best(
        results=results,
        source_agent_id=agent_id,
    )

    return {
        "workflow_name": "Academy Perceptron GridSearch Direct Code Instrumentation",
        "reproducibility": reproducibility,
        "agents": {
            "orchestrator": str(agent.agent_id.uid),
            "training_worker": str(training_worker.agent_id.uid),
            "evaluator": str(evaluator.agent_id.uid),
        },
        "agent_pids": {
            "orchestrator": orchestrator_pid,
            "training_worker_prepare": plan.get("agent_pid"),
            "training_worker_dataset": dataset.get("agent_pid"),
            "training_worker_train": sorted(
                {result["agent_pid"] for result in results if result.get("agent_pid") is not None}
            ),
            "evaluator": selection.get("agent_pid"),
        },
        "dataset": dataset,
        "configs": plan["configs"],
        "results": results,
        "selection": selection,
    }
