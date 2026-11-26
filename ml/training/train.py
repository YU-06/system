import argparse
import csv
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.experiment_protocol import (
    ablation_matrix_sha256,
    apply_ablation_condition,
    assert_ablation_matrix_differences,
    assert_only_declared_condition_differences,
    build_condition_run_config,
    condition_for_architecture,
    load_ablation_matrix,
    load_experiment_protocol,
    protocol_sha256,
    validate_training_config,
)
from training.losses import BoundaryDeepSupervisionLoss
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
    state_dict_sha256,
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
    condition_id: str | None = None,
) -> Path:
    if condition_id is not None:
        config = apply_ablation_condition(config, load_ablation_matrix(), condition_id)
    protocol = load_experiment_protocol(Path(config.experiment_protocol_path))
    if config.execution_mode == "research":
        validate_training_config(protocol, config)
    if config.condition_id == "baseline":
        paired_configs = [
            build_condition_run_config(protocol, config.model_dump(mode="json"), name, seed)
            for name in protocol.conditions
        ]
        assert_only_declared_condition_differences(paired_configs[0], paired_configs[1], protocol)
        condition_name, condition = condition_for_architecture(protocol, architecture)
        model_matrix_digest = None
        run_id = f"{condition.run_id_prefix}-seed-{seed}"
        run_directory = architecture
        model_version = condition.model_version
    else:
        matrix = load_ablation_matrix()
        if matrix.base_protocol_id != protocol.protocol_id:
            raise ValueError("Ablation matrix references a different base training protocol.")
        expected_config = apply_ablation_condition(config, matrix, config.condition_id)
        if expected_config.model_dump() != config.model_dump():
            raise ValueError("Training config does not match the selected ablation condition.")
        assert_ablation_matrix_differences(config, matrix, seed)
        condition = matrix.conditions[config.condition_id]
        if architecture != condition.architecture:
            raise ValueError("Selected architecture differs from the ablation matrix.")
        condition_name = config.condition_id
        model_matrix_digest = ablation_matrix_sha256()
        run_id = f"{condition.run_id_prefix}-seed-{seed}"
        run_directory = f"{condition_name}/{architecture}"
        model_version = condition.model_version
    checked_cache(config)
    if architecture not in config.architectures or seed not in config.experiment_seeds:
        raise ValueError("Model and seed must belong to the shared experiment protocol.")
    if stop_after_epoch is not None and not 1 <= stop_after_epoch <= config.max_epochs:
        raise ValueError("Interruption epoch must lie within the configured training protocol.")
    directory = Path(config.output_directory) / run_directory / f"seed_{seed}"
    if resume is None and directory.exists() and any(directory.iterdir()):
        raise FileExistsError("An existing run must be resumed explicitly, not overwritten.")
    set_global_seed(seed)
    torch.set_num_threads(config.cpu_threads)
    transform = SynchronizedTransforms(
        config.horizontal_flip_probability,
        config.vertical_flip_probability,
        config.rotate_90,
        config.intensity_augmentation,
        config.intensity_transform_mode,
    )
    training = Brats2DDataset(
        Path(config.cache_index),
        "train",
        transform,
        config.train_empty_fraction,
        seed,
        config.input_mode,
        config.context_slices,
    )
    validation = Brats2DDataset(
        Path(config.cache_index),
        "validation",
        input_mode=config.input_mode,
        context_slices=config.context_slices,
    )
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        training,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        worker_init_fn=seed_worker,
        generator=generator,
    )
    model = build_model(
        architecture,
        config.channels,
        input_mode=config.input_mode,
        context_slices=config.context_slices,
        slice_fusion=config.slice_fusion,
        boundary_head=config.boundary_head,
        deep_supervision=config.deep_supervision,
    )
    criterion = BoundaryDeepSupervisionLoss(
        config.bce_weight,
        config.dice_smoothing,
        config.aux_loss_weight,
        config.edge_loss_weight,
        config.edge_positive_weight,
        config.boundary_radius,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    stopping = EarlyStopping(config.early_stopping_patience, config.early_stopping_min_delta)
    completed_epoch = 0
    if resume is not None:
        checkpoint = load_checkpoint(resume, config)
        if checkpoint["architecture"] != architecture or checkpoint["seed"] != seed:
            raise ValueError("Resume model and seed do not match the selected run.")
        if (
            checkpoint.get("run_id") != run_id
            or checkpoint.get("condition_name") != condition_name
            or checkpoint.get("model_version") != condition.model_version
        ):
            raise ValueError("Resume run identity differs from the preregistered model condition.")
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
        "train_region_loss",
        "train_aux_loss",
        "train_edge_loss",
        "validation_loss",
        "validation_region_loss",
        "validation_aux_loss",
        "validation_edge_loss",
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
            loss_sum = region_loss_sum = auxiliary_loss_sum = edge_loss_sum = 0.0
            count = 0
            for batch in loader:
                optimizer.zero_grad(set_to_none=True)
                output = model(batch["image"], return_outputs=True)
                losses = criterion(output, batch["mask"])
                if not torch.isfinite(losses.total):
                    raise ValueError("Training loss became non-finite.")
                losses.total.backward()
                optimizer.step()
                batch_size = batch["image"].shape[0]
                loss_sum += float(losses.total.item()) * batch_size
                region_loss_sum += float(losses.region.item()) * batch_size
                auxiliary_loss_sum += float(losses.auxiliary.item()) * batch_size
                edge_loss_sum += float(losses.edge.item()) * batch_size
                count += batch["image"].shape[0]
            result = evaluate_model(model, validation, config)
            improved, stop = stopping.update(result.mean_patient.dice)
            model_state = model.state_dict()
            git_commit = (directory / "git_commit.txt").read_text(encoding="ascii").strip()
            row = {
                "epoch": epoch,
                "data_kind": training.cache.data_kind,
                "train_loss": loss_sum / count,
                "train_region_loss": region_loss_sum / count,
                "train_aux_loss": auxiliary_loss_sum / count,
                "train_edge_loss": edge_loss_sum / count,
                "validation_loss": result.loss,
                "validation_region_loss": result.region_loss,
                "validation_aux_loss": result.auxiliary_loss,
                "validation_edge_loss": result.edge_loss,
                "validation_patient_dice": result.mean_patient.dice,
                "validation_patient_iou": result.mean_patient.iou,
                "learning_rate": optimizer.param_groups[0]["lr"],
                "stale_epochs": stopping.stale_epochs,
            }
            checkpoint = {
                "schema_version": 1,
                "architecture": architecture,
                "condition_name": condition_name,
                "condition_id": config.condition_id,
                "model_version": model_version,
                "ablation_matrix_sha256": model_matrix_digest,
                "run_id": run_id,
                "git_commit": git_commit,
                "seed": seed,
                "epoch": epoch,
                "config_hash": config_hash(config),
                "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
                "input_mode": config.input_mode,
                "context_slices": config.context_slices,
                "slice_fusion": config.slice_fusion,
                "boundary_head": config.boundary_head,
                "deep_supervision": config.deep_supervision,
                "split_sha256": sha256_file(Path(config.split_manifest)),
                "cache_sha256": sha256_file(Path(config.cache_index)),
                "data_kind": training.cache.data_kind,
                "model_state": model_state,
                "model_weight_sha256": state_dict_sha256(model_state),
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
        "condition_name": condition_name,
        "condition_id": config.condition_id,
        "model_version": model_version,
        "ablation_matrix_sha256": model_matrix_digest,
        "run_id": run_id,
        "seed": seed,
        "completed_epoch": completed_epoch,
        "data_kind": training.cache.data_kind,
        "config_hash": config_hash(config),
        "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
        "git_commit": (directory / "git_commit.txt").read_text(encoding="ascii").strip(),
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "best_checkpoint_bytes": (directory / "best.ckpt").stat().st_size,
        "best_model_weight_sha256": load_checkpoint(directory / "best.ckpt", config)[
            "model_weight_sha256"
        ],
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
    parser.add_argument("--condition", choices=["A0", "A1", "A2", "A3"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--stop-after-epochs", type=int)
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    if arguments.condition:
        matrix = load_ablation_matrix()
        config = apply_ablation_condition(config, matrix, arguments.condition)
        selected_architecture = matrix.conditions[arguments.condition].architecture
        if arguments.architecture and arguments.architecture != selected_architecture:
            parser.error("--architecture conflicts with the selected ablation condition.")
    else:
        selected_architecture = arguments.architecture
    if arguments.resume and (
        (arguments.architecture is None and not arguments.condition) or arguments.seed is None
    ):
        parser.error("Resuming requires an explicit architecture and seed.")
    for architecture in [selected_architecture] if selected_architecture else config.architectures:
        for seed in [arguments.seed] if arguments.seed is not None else config.experiment_seeds:
            directory = run_training(
                config,
                architecture,
                seed,
                arguments.resume,
                arguments.stop_after_epochs,
                arguments.condition,
            )
            print(
                f"Training artifacts: {directory}; mode={config.execution_mode}; "
                "test_metrics=NotRun"
            )


if __name__ == "__main__":
    main()
