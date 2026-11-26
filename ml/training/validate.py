import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.experiment_protocol import (
    apply_ablation_condition,
    condition_metadata,
    load_ablation_matrix,
    load_experiment_protocol,
    protocol_sha256,
    select_validation_threshold,
    validate_training_config,
)
from training.losses import BoundaryDeepSupervisionLoss
from training.metrics import (
    BinaryMetrics,
    ConfusionCounts,
    binary_confusion,
    macro_metrics,
    metrics_from_confusion,
)
from training.models.unet import SegmentationOutput
from training.preprocess import load_original_mask
from training.protocol import TrainingConfig, load_config, sha256_file, write_hashed_json
from training.reconstruct_volume import patient_metrics, patient_spatial_metrics, save_volume
from training.run_io import checkpoint_model, config_hash


@dataclass
class EvaluationResult:
    loss: float
    region_loss: float
    auxiliary_loss: float
    edge_loss: float
    patient_metrics: dict[str, BinaryMetrics]
    patient_spatial_metrics: dict[str, dict[str, float | str | None]]
    patient_confusions: dict[str, ConfusionCounts]
    slice_metrics: list[dict]
    slice_confusions: list[ConfusionCounts]
    single_slice_inference_milliseconds: float
    case_inference_milliseconds: dict[str, float]
    total_seconds: float

    @property
    def mean_patient(self) -> BinaryMetrics:
        return BinaryMetrics(
            **{
                name: float(
                    np.mean([getattr(value, name) for value in self.patient_metrics.values()])
                )
                for name in ("dice", "iou", "precision", "recall")
            }
        )

    def serializable(self) -> dict:
        patient_macro = macro_metrics(list(self.patient_metrics.values()))
        slice_macro = macro_metrics(
            [BinaryMetrics.model_validate(item) for item in self.slice_metrics]
        )
        pooled = sum(self.patient_confusions.values(), ConfusionCounts())
        return {
            "loss": self.loss,
            "loss_breakdown": {
                "region": self.region_loss,
                "auxiliary": self.auxiliary_loss,
                "edge": self.edge_loss,
            },
            "mean_patient": self.mean_patient.model_dump(),
            "aggregation": {
                "slice_level_macro": slice_macro.model_dump(),
                "patient_level_macro": patient_macro.model_dump(),
                "pooled_overall_pixels": metrics_from_confusion(pooled).model_dump(),
                "pooled_confusion_counts": pooled.model_dump(),
                "units": {
                    "slice_level_macro": "unweighted arithmetic mean of axial-slice scores",
                    "patient_level_macro": (
                        "unweighted arithmetic mean of reconstructed patient-volume scores"
                    ),
                    "pooled_overall_pixels": (
                        "confusion counts pooled over every voxel in every patient"
                    ),
                },
                "independent_statistical_unit": "patient",
                "empty_both": 1.0,
                "empty_gt_nonempty_prediction": 0.0,
                "nonempty_gt_empty_prediction": 0.0,
            },
            "patients": {
                identifier: value.model_dump() for identifier, value in self.patient_metrics.items()
            },
            "patient_spatial_metrics": self.patient_spatial_metrics,
            "slices": self.slice_metrics,
            "single_slice_inference_milliseconds": self.single_slice_inference_milliseconds,
            "case_batched_inference_milliseconds": self.case_inference_milliseconds,
            "total_seconds": self.total_seconds,
            "timing_scope": "cached CPU inference; preprocessing excluded",
        }


def evaluate_model(
    model: torch.nn.Module,
    dataset: Brats2DDataset,
    config: TrainingConfig,
    output_directory: Path | None = None,
) -> EvaluationResult:
    if dataset.transform is not None or any(record.subset == "train" for record in dataset.records):
        raise ValueError("Evaluation requires an unaugmented complete validation or test dataset.")
    if dataset.input_mode != config.input_mode or dataset.context_slices != config.context_slices:
        raise ValueError(
            "Evaluation dataset input mode differs from the frozen model configuration."
        )
    torch.set_num_threads(config.cpu_threads)
    model.eval()
    criterion = BoundaryDeepSupervisionLoss(
        config.bce_weight,
        config.dice_smoothing,
        config.aux_loss_weight,
        config.edge_loss_weight,
        config.edge_positive_weight,
        config.boundary_radius,
    )
    loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=False, num_workers=0)
    patient_results: dict[str, BinaryMetrics] = {}
    patient_spatial_results: dict[str, dict[str, float | str | None]] = {}
    patient_confusions: dict[str, ConfusionCounts] = {}
    slice_results: list[dict] = []
    slice_confusions: list[ConfusionCounts] = []
    case_times: dict[str, float] = {}
    current_patient: str | None = None
    current_masks: dict[int, np.ndarray] = {}
    loss_sum = region_loss_sum = auxiliary_loss_sum = edge_loss_sum = 0.0
    count = 0
    started = time.perf_counter()

    def finish_patient(identifier: str, predictions: dict[int, np.ndarray]) -> None:
        expected, affine = load_original_mask(dataset.index_path, identifier, dataset.cache)
        volume, values = patient_metrics(predictions, expected)
        patient_results[identifier] = values
        patient = dataset.cache.patients[identifier]
        geometry = dataset.patient_geometry[identifier]
        patient_spatial_results[identifier] = patient_spatial_metrics(
            volume,
            expected,
            tuple(float(value) for value in geometry.spacing.tolist()),
            patient.spatial_unit,
            geometry.qform,
            patient.qform_code,
            geometry.sform,
            patient.sform_code,
            affine,
        )
        patient_confusions[identifier] = binary_confusion(volume, expected)
        if output_directory is not None:
            save_volume(volume, affine, output_directory / f"{identifier}_pred.nii.gz")

    with torch.inference_mode():
        sample = dataset[0]["image"].unsqueeze(0)
        model(sample)
        single_started = time.perf_counter()
        model(sample)
        single_time = (time.perf_counter() - single_started) * 1000
        for batch in loader:
            batch_started = time.perf_counter()
            output = model(batch["image"], return_outputs=True)
            elapsed = (time.perf_counter() - batch_started) * 1000
            if not isinstance(output, SegmentationOutput):
                raise ValueError("Model did not return the configured structured output.")
            logits = output.segmentation_logits
            if not torch.isfinite(logits).all():
                raise ValueError("Model emitted non-finite validation logits.")
            losses = criterion(output, batch["mask"])
            batch_count = len(batch["patient_id"])
            loss_sum += float(losses.total.item()) * batch_count
            region_loss_sum += float(losses.region.item()) * batch_count
            auxiliary_loss_sum += float(losses.auxiliary.item()) * batch_count
            edge_loss_sum += float(losses.edge.item()) * batch_count
            count += batch_count
            predicted = (logits.sigmoid() >= config.threshold).cpu().numpy().astype(np.uint8)
            expected_slices = batch["mask"].cpu().numpy().astype(np.uint8)
            for offset, identifier in enumerate(batch["patient_id"]):
                slice_index = int(batch["slice_index"][offset].item())
                if current_patient is not None and identifier != current_patient:
                    finish_patient(current_patient, current_masks)
                    current_masks = {}
                current_patient = identifier
                if slice_index in current_masks or identifier in patient_results:
                    raise ValueError(
                        "Evaluation slices must be complete, unique and grouped by patient."
                    )
                current_masks[slice_index] = predicted[offset, 0]
                case_times[identifier] = case_times.get(identifier, 0.0) + elapsed / batch_count
                slice_count = binary_confusion(predicted[offset, 0], expected_slices[offset, 0])
                slice_confusions.append(slice_count)
                slice_results.append(
                    {
                        "patient_id": identifier,
                        "slice_index": slice_index,
                        **metrics_from_confusion(slice_count).model_dump(),
                        "confusion_counts": slice_count.model_dump(),
                    }
                )
        if current_patient is not None:
            finish_patient(current_patient, current_masks)
    expected_patients = {record.patient_id for record in dataset.records}
    if set(patient_results) != expected_patients or not count:
        raise ValueError("Evaluation did not process every requested patient.")
    return EvaluationResult(
        loss_sum / count,
        region_loss_sum / count,
        auxiliary_loss_sum / count,
        edge_loss_sum / count,
        patient_results,
        patient_spatial_results,
        patient_confusions,
        slice_results,
        slice_confusions,
        single_time,
        case_times,
        time.perf_counter() - started,
    )


def evaluation_report(result: EvaluationResult, config: TrainingConfig, subset: str) -> dict:
    observed = result.serializable()
    return {
        "subset": subset,
        "data_kind": "synthetic" if config.execution_mode == "smoke" else "research",
        "research_metrics": observed
        if config.execution_mode == "research"
        else {"status": "NotRun"},
        "synthetic_smoke_measurements": observed if config.execution_mode == "smoke" else None,
        "threshold": config.threshold,
        "disclaimer": DISCLAIMER,
    }


def run_validation(
    config: TrainingConfig,
    checkpoint_path: Path,
    output: Path,
    freeze_path: Path | None = None,
    selection_mode: str = "search",
) -> EvaluationResult:
    if freeze_path is not None and freeze_path.parent.resolve() != output.parent.resolve():
        raise ValueError(
            "Freeze and validation report must remain in the same portable artifact directory."
        )
    protocol = load_experiment_protocol(Path(config.experiment_protocol_path))
    if config.execution_mode == "research":
        validate_training_config(protocol, config)
    model, checkpoint = checkpoint_model(checkpoint_path, config)
    condition_name, model_version, matrix_digest = condition_metadata(
        protocol, config, checkpoint["architecture"]
    )
    if (
        checkpoint.get("model_version") != model_version
        or checkpoint.get("condition_id", "baseline") != config.condition_id
        or checkpoint.get("ablation_matrix_sha256") != matrix_digest
    ):
        raise ValueError(
            "Checkpoint implementation version differs from the preregistered model condition."
        )
    dataset = Brats2DDataset(
        Path(config.cache_index),
        "validation",
        input_mode=config.input_mode,
        context_slices=config.context_slices,
    )
    if selection_mode not in {"search", "fixed_050"}:
        raise ValueError("Threshold selection mode must be search or fixed_050.")
    thresholds = config.validation_thresholds if selection_mode == "search" else [0.50]
    candidates = []
    for threshold in thresholds:
        candidate_config = TrainingConfig.model_validate(
            {**config.model_dump(), "threshold": threshold}
        )
        candidates.append((threshold, evaluate_model(model, dataset, candidate_config)))
    scores = {threshold: candidate.mean_patient.dice for threshold, candidate in candidates}
    threshold = select_validation_threshold(scores, protocol, selection_mode)
    result = next(candidate for value, candidate in candidates if value == threshold)
    selected_config = TrainingConfig.model_validate({**config.model_dump(), "threshold": threshold})
    report = evaluation_report(result, selected_config, "validation")
    report["validation_threshold_search"] = [
        {"threshold": value, "validation_patient_dice": candidate.mean_patient.dice}
        for value, candidate in candidates
    ]
    report["threshold_selection_mode"] = selection_mode
    report["threshold_selection_rule"] = protocol.model_selection["tie_break"]
    report["evaluation_protocol"] = protocol.protocol_id
    git_commit = checkpoint.get("git_commit", "NotRun")
    if config.execution_mode == "research" and git_commit == "NotRun":
        raise ValueError("Research validation freeze requires a recorded Git commit.")
    run_id = checkpoint["run_id"]
    report.update(
        architecture=checkpoint["architecture"],
        condition_name=condition_name,
        model_version=model_version,
        condition_id=config.condition_id,
        run_id=run_id,
        seed=checkpoint["seed"],
        git_commit=git_commit,
        ablation_matrix_sha256=matrix_digest,
        model_weight_sha256=checkpoint["model_weight_sha256"],
        checkpoint_sha256=sha256_file(checkpoint_path),
        protocol_sha256=protocol_sha256(Path(config.experiment_protocol_path)),
    )
    write_hashed_json(output, report)
    if freeze_path is not None:
        write_hashed_json(
            freeze_path,
            {
                "kind": "validation_protocol_freeze",
                "git_commit": git_commit,
                "run_id": run_id,
                "condition_name": condition_name,
                "condition_id": config.condition_id,
                "architecture": checkpoint["architecture"],
                "model_version": model_version,
                "ablation_matrix_sha256": matrix_digest,
                "preprocessing_version": config.preprocessing_version,
                "seed": checkpoint["seed"],
                "evaluation_protocol": protocol.protocol_id,
                "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
                "config_hash": config_hash(config),
                "split_sha256": sha256_file(Path(config.split_manifest)),
                "cache_sha256": sha256_file(Path(config.cache_index)),
                "checkpoint_sha256": sha256_file(checkpoint_path),
                "model_weight_sha256": checkpoint["model_weight_sha256"],
                "validation_report_sha256": sha256_file(output),
                "validation_report": output.name,
                "threshold": threshold,
                "threshold_selection_mode": selection_mode,
                "threshold_source": "validation_only",
                "training_threshold": config.threshold,
                "data_kind": report["data_kind"],
                "disclaimer": DISCLAIMER,
            },
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--selection-mode", choices=["search", "fixed_050"], default="search")
    parser.add_argument("--condition", choices=["A0", "A1", "A2", "A3"])
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    if arguments.condition:
        config = apply_ablation_condition(config, load_ablation_matrix(), arguments.condition)
    result = run_validation(
        config, arguments.checkpoint, arguments.output, arguments.freeze, arguments.selection_mode
    )
    print(
        f"Validation processed {len(result.patient_metrics)} complete patients; "
        f"execution_mode={config.execution_mode}"
    )


if __name__ == "__main__":
    main()
