from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import torch
import torch.nn as nn
import torch.optim as optim


@dataclass(frozen=True)
class DatasetConfig:
    n_samples: int = 2000
    split_ratio: float = 0.8


@dataclass(frozen=True)
class TrainingConfig:
    config_id: str
    epochs: int
    learning_rate: float
    n_input_neurons: int


class SingleLayerPerceptron(nn.Module):
    def __init__(self, input_size: int):
        super().__init__()
        self.layer = nn.Linear(input_size, 1)

    def forward(self, x):
        return torch.sigmoid(self.layer(x))


def set_reproducibility(seed: int = 42) -> dict[str, Any]:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    return {
        "seed": seed,
        "python_random_seeded": True,
        "torch_manual_seeded": True,
        "torch_cuda_manual_seeded": torch.cuda.is_available(),
    }


def default_dataset_config() -> DatasetConfig:
    return DatasetConfig(n_samples=10000000, split_ratio=0.8)


def default_gridsearch_configs(n_configs: int = 5) -> list[TrainingConfig]:
    configs = [
        TrainingConfig(config_id="cfg_1", epochs=20, learning_rate=0.01, n_input_neurons=1),
        TrainingConfig(config_id="cfg_2", epochs=40, learning_rate=0.03, n_input_neurons=1),
        TrainingConfig(config_id="cfg_3", epochs=60, learning_rate=0.08, n_input_neurons=2),
        TrainingConfig(config_id="cfg_4", epochs=100, learning_rate=0.12, n_input_neurons=2),
        TrainingConfig(config_id="cfg_5", epochs=140, learning_rate=0.20, n_input_neurons=2),
    ]
    return configs[:n_configs]


def generate_dataset(config: DatasetConfig):
    generator = torch.Generator().manual_seed(torch.initial_seed())
    half = config.n_samples // 2
    x = torch.cat(
        [
            torch.randn(half, 2, generator=generator) + 2,
            torch.randn(half, 2, generator=generator) - 2,
        ]
    )
    y = torch.cat([torch.zeros(half), torch.ones(half)]).unsqueeze(1)
    n_train = int(config.n_samples * config.split_ratio)
    return x[:n_train], y[:n_train], x[n_train:], y[n_train:]


def dataset_summary(x_train, y_train, x_val, y_val, dataset_id: str) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "x_train_shape": tuple(x_train.shape),
        "y_train_shape": tuple(y_train.shape),
        "x_val_shape": tuple(x_val.shape),
        "y_val_shape": tuple(y_val.shape),
    }


def validate(model, criterion, x_val, y_val) -> tuple[float, float]:
    model.eval()
    with torch.no_grad():
        outputs = model(x_val)
        loss = criterion(outputs, y_val)
        predictions = outputs.round()
        accuracy = predictions.eq(y_val).sum().item() / y_val.size(0)
    return loss.item(), accuracy


def train_and_validate(
    config: TrainingConfig,
    x_train,
    y_train,
    x_val,
    y_val,
    artifact_dir: Path,
    checkpoint_check: int = 2,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir_name = artifact_dir.name
    model = SingleLayerPerceptron(input_size=config.n_input_neurons)
    criterion = nn.BCELoss()
    optimizer = optim.SGD(model.parameters(), lr=config.learning_rate)
    best_val_loss = float("inf")
    best_checkpoint_path = None
    x_train_cfg = x_train[:, : config.n_input_neurons]
    x_val_cfg = x_val[:, : config.n_input_neurons]

    for epoch in range(1, config.epochs + 1):
        model.train()
        outputs = model(x_train_cfg)
        loss = criterion(outputs, y_train)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        current_val_loss, _ = validate(model, criterion, x_val_cfg, y_val)
        if epoch % checkpoint_check == 0 and current_val_loss < best_val_loss:
            best_val_loss = current_val_loss
            best_checkpoint_path = artifact_dir / f"{config.config_id}_best.pt"
            torch.save(
                {
                    "config": config.__dict__,
                    "epoch": epoch,
                    "state_dict": model.state_dict(),
                    "best_val_loss": best_val_loss,
                },
                best_checkpoint_path,
            )

    final_val_loss, final_val_accuracy = validate(model, criterion, x_val_cfg, y_val)
    return {
        "config_id": config.config_id,
        "val_loss": final_val_loss,
        "val_accuracy": final_val_accuracy,
        "best_val_loss": best_val_loss,
        "model_artifact_id": (
            str(Path(artifact_dir_name) / best_checkpoint_path.name) if best_checkpoint_path else None
        ),
    }


def select_best_model(results: list[dict[str, Any]]) -> dict[str, Any]:
    best = min(results, key=lambda item: float(item["best_val_loss"]))
    return {
        "selected_model_artifact_id": best["model_artifact_id"],
        "selected_config_id": best["config_id"],
        "selected_loss": best["best_val_loss"],
        "selection_reason": "lowest validation loss among candidate configurations",
    }


def new_dataset_id() -> str:
    return f"dataset_{uuid4()}"
