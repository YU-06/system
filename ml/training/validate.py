import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.losses import BCEDiceLoss
from training.metrics import BinaryMetrics, binary_metrics
from training.preprocess import load_original_mask
from training.protocol import TrainingConfig, load_config, sha256_file, write_hashed_json
from training.reconstruct_volume import patient_metrics, save_volume
from training.run_io import checkpoint_model, config_hash


@dataclass
class EvaluationResult:
    loss: float
    patient_metrics: dict[str, BinaryMetrics]
    slice_metrics: list[dict]
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
        return {
            "loss": self.loss,
            "mean_patient": self.mean_patient.model_dump(),
            "patients": {
                identifier: value.model_dump() for identifier, value in self.patient_metrics.items()
            },
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
    torch.set_num_threads(config.cpu_threads)
    model.eval()
    criterion = BCEDiceLoss(config.bce_weight, config.dice_smoothing)
    loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=False, num_workers=0)
    patient_results: dict[str, BinaryMetrics] = {}
    slice_results: list[dict] = []
    case_times: dict[str, float] = {}
    current_patient: str | None = None
    current_masks: dict[int, np.ndarray] = {}
    loss_sum = 0.0
    count = 0
    started = time.perf_counter()

    def finish_patient(identifier: str, predictions: dict[int, np.ndarray]) -> None:
        expected, affine = load_original_mask(dataset.index_path, identifier, dataset.cache)
        volume, values = patient_metrics(predictions, expected)
        patient_results[identifier] = values
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
            logits = model(batch["image"])
            elapsed = (time.perf_counter() - batch_started) * 1000
            if not torch.isfinite(logits).all():
                raise ValueError("Model emitted non-finite validation logits.")
            loss = criterion(logits, batch["mask"])
            batch_count = len(batch["patient_id"])
            loss_sum += float(loss.item()) * batch_count
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
                slice_results.append(
                    {
                        "patient_id": identifier,
                        "slice_index": slice_index,
                        **binary_metrics(
                            predicted[offset, 0], expected_slices[offset, 0]
                        ).model_dump(),
                    }
                )
        if current_patient is not None:
            finish_patient(current_patient, current_masks)
    expected_patients = {record.patient_id for record in dataset.records}
    if set(patient_results) != expected_patients or not count:
        raise ValueError("Evaluation did not process every requested patient.")
    return EvaluationResult(
        loss_sum / count,
        patient_results,
        slice_results,
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
    config: TrainingConfig, checkpoint_path: Path, output: Path, freeze_path: Path | None = None
) -> EvaluationResult:
    if freeze_path is not None and freeze_path.parent.resolve() != output.parent.resolve():
        raise ValueError(
            "Freeze and validation report must remain in the same portable artifact directory."
        )
    model, checkpoint = checkpoint_model(checkpoint_path, config)
    dataset = Brats2DDataset(Path(config.cache_index), "validation")
    candidates = []
    for threshold in config.validation_thresholds:
        candidate_config = TrainingConfig.model_validate(
            {**config.model_dump(), "threshold": threshold}
        )
        candidates.append((threshold, evaluate_model(model, dataset, candidate_config)))
    threshold, result = max(
        candidates,
        key=lambda item: (item[1].mean_patient.dice, -abs(item[0] - config.threshold), -item[0]),
    )
    selected_config = TrainingConfig.model_validate({**config.model_dump(), "threshold": threshold})
    report = evaluation_report(result, selected_config, "validation")
    report["validation_threshold_search"] = [
        {"threshold": value, "validation_patient_dice": candidate.mean_patient.dice}
        for value, candidate in candidates
    ]
    report.update(
        architecture=checkpoint["architecture"],
        seed=checkpoint["seed"],
        checkpoint_sha256=sha256_file(checkpoint_path),
    )
    write_hashed_json(output, report)
    if freeze_path is not None:
        write_hashed_json(
            freeze_path,
            {
                "kind": "validation_protocol_freeze",
                "config_hash": config_hash(config),
                "split_sha256": sha256_file(Path(config.split_manifest)),
                "cache_sha256": sha256_file(Path(config.cache_index)),
                "checkpoint_sha256": sha256_file(checkpoint_path),
                "validation_report_sha256": sha256_file(output),
                "validation_report": output.name,
                "architecture": checkpoint["architecture"],
                "seed": checkpoint["seed"],
                "threshold": threshold,
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
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    result = run_validation(config, arguments.checkpoint, arguments.output, arguments.freeze)
    print(
        f"Validation processed {len(result.patient_metrics)} complete patients; "
        f"execution_mode={config.execution_mode}"
    )


if __name__ == "__main__":
    main()
