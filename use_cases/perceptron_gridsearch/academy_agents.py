from __future__ import annotations

import logging
import os
from pathlib import Path

from academy.agent import Agent, action

from use_cases.perceptron_gridsearch.core import (
    DatasetConfig,
    TrainingConfig,
    default_dataset_config,
    default_gridsearch_configs,
    dataset_summary,
    generate_dataset,
    new_dataset_id,
    select_best_model,
    set_reproducibility,
    train_and_validate,
)


logger = logging.getLogger(__name__)


class TrainingWorkerAgent(Agent):
    @action
    async def prepare_gridsearch(self, n_configs: int = 5):
        dataset_config = default_dataset_config()
        configs = default_gridsearch_configs(n_configs=n_configs)
        logger.info(
            "prepared gridsearch configs",
            extra={"academy.agent_id": self.agent_id, "pid": os.getpid()},
        )
        return {
            "dataset_config": dataset_config.__dict__,
            "configs": [cfg.__dict__ for cfg in configs],
            "agent_pid": os.getpid(),
        }

    @action
    async def generate_dataset(self, dataset_config):
        x_train, y_train, x_val, y_val = generate_dataset(DatasetConfig(**dataset_config))
        dataset_id = new_dataset_id()
        self._dataset = {
            "x_train": x_train,
            "y_train": y_train,
            "x_val": x_val,
            "y_val": y_val,
            "dataset_id": dataset_id,
        }
        logger.info(
            "generated dataset",
            extra={"academy.agent_id": self.agent_id, "pid": os.getpid()},
        )
        summary = dataset_summary(x_train, y_train, x_val, y_val, dataset_id)
        summary["agent_pid"] = os.getpid()
        return summary

    @action
    async def train_config(self, config, dataset_id: str, artifact_dir: str, checkpoint_check: int = 2):
        dataset = self._dataset
        if dataset_id != dataset["dataset_id"]:
            raise ValueError(f"Unknown dataset_id: {dataset_id}")
        cfg = TrainingConfig(**config)
        result = train_and_validate(
            config=cfg,
            x_train=dataset["x_train"],
            y_train=dataset["y_train"],
            x_val=dataset["x_val"],
            y_val=dataset["y_val"],
            artifact_dir=Path(artifact_dir),
            checkpoint_check=checkpoint_check,
        )
        result["agent_pid"] = os.getpid()
        logger.info(
            "trained gridsearch config",
            extra={
                "academy.agent_id": self.agent_id,
                "pid": os.getpid(),
                "config_id": cfg.config_id,
            },
        )
        return result


class EvaluatorAgent(Agent):
    @action
    async def select_best(self, results):
        selection = select_best_model(results)
        selection["agent_pid"] = os.getpid()
        logger.info(
            "selected best model",
            extra={"academy.agent_id": self.agent_id, "pid": os.getpid()},
        )
        return selection


class OrchestratorAgent(Agent):
    def __init__(self, training_worker, evaluator):
        super().__init__()
        self.training_worker = training_worker
        self.evaluator = evaluator

    @action
    async def run_gridsearch(self, artifact_dir: str, n_configs: int = 5, checkpoint_check: int = 2):
        orchestrator_pid = os.getpid()
        logger.info(
            "started perceptron gridsearch orchestration",
            extra={"academy.agent_id": self.agent_id, "pid": orchestrator_pid},
        )
        set_reproducibility(seed=42)

        plan = await self.training_worker.prepare_gridsearch(n_configs=n_configs)
        dataset = await self.training_worker.generate_dataset(plan["dataset_config"])
        results = []
        for config in plan["configs"]:
            result = await self.training_worker.train_config(
                config=config,
                dataset_id=dataset["dataset_id"],
                artifact_dir=artifact_dir,
                checkpoint_check=checkpoint_check,
            )
            results.append(result)
        selection = await self.evaluator.select_best(results=results)

        return {
            "workflow_name": "Academy Perceptron GridSearch Baseline",
            "agents": {
                "orchestrator": str(self.agent_id.uid),
                "training_worker": str(self.training_worker.agent_id.uid),
                "evaluator": str(self.evaluator.agent_id.uid),
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
