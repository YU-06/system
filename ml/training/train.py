import argparse
import csv
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.losses import BCEDiceLoss
from training.models import build_model
from training.protocol import (
    TrainingConfig,
    load_config,
    set_global_seed,
    sha256_file,
    write_hashed_json,
)
from training.run_io import (
    capture_rng,
    checked_cache,
    config_hash,
    initialize_run,
    load_checkpoint,
    reconcile_history,
    restore_rng,
    save_checkpoint,
)
from training.transforms import SynchronizedTransforms
from training.validate import evaluate_model


def seed_worker(worker_id: int) -> None:
    seed = torch.initial_seed() % (2**32)
    np.random.seed(seed)
    random.seed(seed)


class EarlyStopping:
    def __init__(
        self, patience: int, minimum_delta: float = 0.0, best: float = -1.0, stale_epochs: int = 0
    ) -> None:
        self.patience = patience
        self.minimum_delta = minimum_delta
        self.best = best
        self.stale_epochs = stale_epochs

    def update(self, value: float) -> tuple[bool, bool]:
        if not np.isfinite(value):
            raise ValueError("Validation Dice must be finite.")
        improved = value > self.best + self.minimum_delta
        if improved:
            self.best, self.stale_epochs = value, 0
        else:
            self.stale_epochs += 1
        return improved, self.stale_epochs >= self.patience


def run_training(
    config: TrainingConfig,
    architecture: str,
    seed: int,
    resume: Path | None = None,
    stop_after_epoch: int | None = None,
) -> Path:
    checked_cache(config)
    if architecture not in config.architectures or seed not in config.experiment_seeds:
        raise ValueError("Model and seed must belong to the shared experiment protocol.")
    if stop_after_epoch is not None and not 1 <= stop_after_epoch <= config.max_epochs:
        raise ValueError("Interruption epoch must lie within the configured training protocol.")
    directory = Path(config.output_directory) / architecture / f"seed_{seed}"
    if resume is None and directory.exists() and any(directory.iterdir()):
        raise FileExistsError("An existing run must be resumed explicitly, not overwritten.")
    set_global_seed(seed)
    torch.set_num_threads(config.cpu_threads)
    transform = SynchronizedTransforms(
        config.horizontal_flip_probability, config.vertical_flip_probability, config.rotate_90
    )
    training = Brats2DDataset(
        Path(config.cache_index), "train", transform, config.train_empty_fraction, seed
    )
    validation = Brats2DDataset(Path(config.cache_index), "validation")
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        training,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        worker_init_fn=seed_worker,
        generator=generator,
    )
    model = build_model(architecture, config.channels)
    criterion = BCEDiceLoss(config.bce_weight, config.dice_smoothing)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    stopping = EarlyStopping(config.early_stopping_patience, config.early_stopping_min_delta)
    completed_epoch = 0
    if resume is not None:
        checkpoint = load_checkpoint(resume, config)
        if checkpoint["architecture"] != architecture or checkpoint["seed"] != seed:
            raise ValueError("Resume model and seed do not match the selected run.")
        if resume.resolve().parent != directory.resolve():
            raise ValueError("Resume must continue the original run directory.")
        model.load_state_dict(checkpoint["model_state"], strict=True)
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        stopping.best, stopping.stale_epochs = (
            checkpoint["best_validation_dice"],
            checkpoint["stale_epochs"],
        )
        completed_epoch = checkpoint["epoch"]
        generator.set_state(checkpoint["loader_generator_state"])
        restore_rng(checkpoint["rng"])
    else:
        initialize_run(directory, config)
        write_hashed_json(
            directory / "training_slice_selection.json",
            [record.model_dump() for record in training.records],
        )
    metrics_path = directory / "metrics.csv"
    fields = [
        "epoch",
        "data_kind",
        "train_loss",
        "validation_loss",
        "validation_patient_dice",
        "validation_patient_iou",
        "learning_rate",
        "stale_epochs",
    ]
    if resume is not None:
        reconcile_history(metrics_path, checkpoint, fields)
    with metrics_path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if metrics_path.stat().st_size == 0:
            writer.writeheader()
        for epoch in range(completed_epoch + 1, config.max_epochs + 1):
            if stopping.stale_epochs >= stopping.patience:
                break
            model.train()
            loss_sum, count = 0.0, 0
            for batch in loader:
                optimizer.zero_grad(set_to_none=True)
                logits = model(batch["image"])
                loss = criterion(logits, batch["mask"])
                if not torch.isfinite(loss):
                    raise ValueError("Training loss became non-finite.")
                loss.backward()
                optimizer.step()
                loss_sum += float(loss.item()) * batch["image"].shape[0]
                count += batch["image"].shape[0]
            result = evaluate_model(model, validation, config)
            improved, stop = stopping.update(result.mean_patient.dice)
            row = {
                "epoch": epoch,
                "data_kind": training.cache.data_kind,
                "train_loss": loss_sum / count,
                "validation_loss": result.loss,
                "validation_patient_dice": result.mean_patient.dice,
                "validation_patient_iou": result.mean_patient.iou,
                "learning_rate": optimizer.param_groups[0]["lr"],
                "stale_epochs": stopping.stale_epochs,
            }
            checkpoint = {
                "schema_version": 1,
                "architecture": architecture,
                "seed": seed,
                "epoch": epoch,
                "config_hash": config_hash(config),
                "split_sha256": sha256_file(Path(config.split_manifest)),
                "cache_sha256": sha256_file(Path(config.cache_index)),
                "data_kind": training.cache.data_kind,
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "best_validation_dice": stopping.best,
                "stale_epochs": stopping.stale_epochs,
                "loader_generator_state": generator.get_state(),
                "rng": capture_rng(),
                "disclaimer": DISCLAIMER,
                "epoch_metrics": row,
            }
            save_checkpoint(directory / "last.ckpt", checkpoint)
            if improved:
                save_checkpoint(directory / "best.ckpt", checkpoint)
            writer.writerow(row)
            stream.flush()
            completed_epoch = epoch
            if stop or stop_after_epoch is not None and epoch >= stop_after_epoch:
                break
    status = {
        "architecture": architecture,
        "seed": seed,
        "completed_epoch": completed_epoch,
        "data_kind": training.cache.data_kind,
        "config_hash": config_hash(config),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "best_checkpoint_bytes": (directory / "best.ckpt").stat().st_size,
        "test_metrics": {"status": "NotRun"},
        "disclaimer": DISCLAIMER,
    }
    status_path = directory / "run_status.json"
    if status_path.exists():
        status_path.unlink()
        status_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(status_path, status)
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    parser.add_argument("--architecture", choices=["UNet", "AttentionUNet"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--stop-after-epochs", type=int)
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    if arguments.resume and (arguments.architecture is None or arguments.seed is None):
        parser.error("Resuming requires an explicit architecture and seed.")
    for architecture in (
        [arguments.architecture] if arguments.architecture else config.architectures
    ):
        for seed in [arguments.seed] if arguments.seed is not None else config.experiment_seeds:
            directory = run_training(
                config, architecture, seed, arguments.resume, arguments.stop_after_epochs
            )
            print(
                f"Training artifacts: {directory}; mode={config.execution_mode}; "
                "test_metrics=NotRun"
            )


if __name__ == "__main__":
    main()
