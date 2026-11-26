import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import yaml

from training import DISCLAIMER
from training.create_split import SplitManifest, load_split
from training.experiment_protocol import (
    PROTOCOL_SCRIPT_VERSION,
    ExperimentProtocol,
    load_experiment_protocol,
    protocol_sha256,
    validate_training_config,
)
from training.paired_statistics import summarize_paired_seed_metrics
from training.preprocess import load_cache, load_original_mask
from training.preprocessing import resize_mask
from training.protocol import (
    TrainingConfig,
    config_hash,
    read_hashed_json,
    sha256_file,
    write_hashed_json,
)


@dataclass(frozen=True)
class ResearchRun:
    report_path: Path
    run_directory: Path
    condition: str
    seed: int
    run_id: str
    patient_dice: dict[str, float]
    patient_metrics: dict[str, dict[str, float]]
    report: dict[str, Any]


def _not_run_manifest(
    protocol: ExperimentProtocol, protocol_digest: str, reasons: list[str]
) -> dict[str, Any]:
    templates = {
        "split_statistics": ["subset", "patients", "lesion_patients", "slices", "lesion_slices"],
        "model_parameters_and_size": [
            "condition",
            "seed",
            "run_id",
            "parameters",
            "checkpoint_bytes",
            "weight_bytes",
        ],
        "training_validation_curves": [
            "condition",
            "seed",
            "epoch",
            "train_loss",
            "validation_loss",
            "validation_patient_dice",
        ],
        "model_comparison_and_gate_ablation": [
            "patient-level paired Dice",
            "mean±std across seeds",
            "Wilcoxon",
            "bootstrap 95% CI",
        ],
        "patient_dice_distribution": ["patient_id", "condition", "three-seed mean Dice"],
        "patient_metrics_across_seeds": [
            "patient_id",
            "condition",
            "Dice",
            "IoU",
            "Precision",
            "Recall",
        ],
        "aggregation_metrics": [
            "run_id",
            "aggregation scope",
            "Dice",
            "IoU",
            "Precision",
            "Recall",
        ],
        "lesion_volume_relationship": ["patient_id", "lesion volume", "unit", "patient Dice"],
        "inference_timing_distribution": ["run_id", "patient_id", "milliseconds per case"],
        "single_slice_inference_timing": ["run_id", "milliseconds per slice"],
        "typical_best_median_worst_cases": [
            "predeclared rank",
            "patient_id",
            "slice_index",
            "ground truth",
            "predictions",
        ],
    }
    return {
        "status": "NotRun",
        "data_kind": "research_required",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol_digest,
        "reporting_script_version": PROTOCOL_SCRIPT_VERSION,
        "sections": {
            name: {"status": "NotRun", "template_columns": columns, "reason": reasons}
            for name, columns in templates.items()
        },
        "not_run_checklist": reasons,
        "generated_figures": [],
        "disclaimer": DISCLAIMER,
    }


def _load_run(
    report_path: Path,
    protocol: ExperimentProtocol,
    protocol_digest: str,
    split_digest: str,
    cache_digest: str,
    threshold_mode: str,
) -> ResearchRun:
    report = read_hashed_json(report_path)
    if (
        not isinstance(report, dict)
        or report.get("data_kind") != "research"
        or report.get("subset") != "test"
    ):
        raise ValueError(
            "Only research test artifacts are accepted; synthetic/validation outputs are excluded."
        )
    condition, seed = report.get("condition_name"), report.get("seed")
    if condition not in protocol.conditions or seed not in protocol.seeds:
        raise ValueError("Condition or seed is not part of the preregistered paired design.")
    condition_spec = protocol.conditions[condition]
    expected_run_id = f"{condition_spec.run_id_prefix}-seed-{seed}"
    run_directory = report_path.parent.parent
    freeze_path = run_directory / "protocol_frozen.json"
    freeze = read_hashed_json(freeze_path)
    checkpoint_path = run_directory / "best.ckpt"
    expected = {
        "run_id": expected_run_id,
        "condition_name": condition,
        "architecture": condition_spec.architecture,
        "model_version": condition_spec.model_version,
        "seed": seed,
        "evaluation_protocol": protocol.protocol_id,
        "protocol_sha256": protocol_digest,
        "config_hash": freeze.get("config_hash"),
        "split_sha256": split_digest,
        "cache_sha256": cache_digest,
        "preprocessing_version": protocol.preprocessing_version,
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "model_weight_sha256": report.get("model_weight_sha256"),
        "threshold_source": "validation_only",
        "threshold_selection_mode": threshold_mode,
        "data_kind": "research",
    }
    if any(freeze.get(key) != value for key, value in expected.items()):
        raise ValueError(
            f"Validation freeze does not match expected source metadata for {expected_run_id}."
        )
    if sha256_file(freeze_path) != report.get("frozen_protocol_sha256"):
        raise ValueError("Test report does not match its validation freeze digest.")
    report_expected = {key: value for key, value in expected.items() if key != "threshold_source"}
    report_expected.update(
        {
            "git_commit": freeze.get("git_commit"),
            "threshold": freeze.get("threshold"),
            "threshold_selection_mode": freeze.get("threshold_selection_mode"),
            "frozen_protocol_sha256": sha256_file(freeze_path),
        }
    )
    if any(report.get(key) != value for key, value in report_expected.items()):
        raise ValueError(
            f"Test report metadata does not match the preregistered source for {expected_run_id}."
        )
    if freeze.get("model_weight_sha256") != report.get("model_weight_sha256"):
        raise ValueError("Frozen model tensor digest does not match the test report.")
    if freeze.get("preprocessing_version") != report.get("preprocessing_version"):
        raise ValueError("Test report preprocessing version does not match its validation freeze.")
    config_path = run_directory / "config.yaml"
    if not config_path.is_file():
        raise ValueError("Resolved run configuration is missing or invalid.")
    run_config = TrainingConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    if config_hash(run_config) != freeze.get("config_hash"):
        raise ValueError("Run configuration does not match the validation freeze.")
    validate_training_config(protocol, run_config)
    metrics = report.get("research_metrics")
    patients = metrics.get("patients") if isinstance(metrics, dict) else None
    if (
        not isinstance(patients, dict)
        or not patients
        or any(
            not isinstance(values, dict)
            or any(metric not in values for metric in ("dice", "iou", "precision", "recall"))
            for values in patients.values()
        )
    ):
        raise ValueError("Patient-level research Dice values are missing.")
    scores = {str(patient): float(values["dice"]) for patient, values in patients.items()}
    metrics_by_patient = {
        str(patient): {
            metric: float(values[metric]) for metric in ("dice", "iou", "precision", "recall")
        }
        for patient, values in patients.items()
    }
    if any(not np.isfinite(value) or not 0 <= value <= 1 for value in scores.values()):
        raise ValueError("Patient-level Dice values must be finite and within [0, 1].")
    if any(
        not np.isfinite(value) or not 0 <= value <= 1
        for patient_metrics in metrics_by_patient.values()
        for value in patient_metrics.values()
    ):
        raise ValueError("Patient-level metrics must be finite and within [0, 1].")
    return ResearchRun(
        report_path,
        run_directory,
        condition,
        seed,
        expected_run_id,
        scores,
        metrics_by_patient,
        report,
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    report_columns = columns if "disclaimer" in columns else [*columns, "disclaimer"]
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=report_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**row, "disclaimer": DISCLAIMER} for row in rows)


def _source_record(
    path: Path,
    run_ids: list[str],
    protocol_digest: str,
    split_digest: str,
    scope: str,
    units: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "file": path.name,
        "sha256": sha256_file(path),
        "source_run_ids": run_ids,
        "protocol_sha256": protocol_digest,
        "split_sha256": split_digest,
        "metric_scope": scope,
        "units": units,
        "parameters": parameters or {},
        "reporting_script_version": PROTOCOL_SCRIPT_VERSION,
        "disclaimer": DISCLAIMER,
    }


def _save_figure(figure: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    figure.text(0.5, 0.005, DISCLAIMER, ha="center", va="bottom", fontsize=6)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _voxel_mm3(patient: Any, affine: np.ndarray) -> float | None:
    if patient.spatial_unit not in {"mm", "meter", "micron"}:
        return None
    if patient.qform_code <= 0 and patient.sform_code <= 0:
        return None
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        return None
    spacing = np.asarray(patient.voxel_spacing, dtype=np.float64)
    affine_spacing = np.linalg.norm(affine[:3, :3], axis=0)
    if (
        spacing.shape != (3,)
        or np.any(spacing <= 0)
        or not np.allclose(spacing, affine_spacing, rtol=1e-4, atol=1e-6)
    ):
        return None
    determinant = abs(float(np.linalg.det(affine[:3, :3])))
    scale = {"mm": 1.0, "meter": 1e9, "micron": 1e-9}[patient.spatial_unit]
    value = determinant * scale
    return value if np.isfinite(value) and value > 0 else None


def _record_artifact(
    path: Path,
    records: list[dict[str, Any]],
    run_ids: list[str],
    protocol_digest: str,
    split_digest: str,
    scope: str,
    units: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    records.append(
        _source_record(path, run_ids, protocol_digest, split_digest, scope, units, parameters)
    )


def _write_templates(
    output: Path,
    protocol: ExperimentProtocol,
    digest: str,
    reasons: list[str],
    threshold_mode: str,
) -> dict[str, Any]:
    manifest = _not_run_manifest(protocol, digest, reasons)
    manifest["threshold_selection_mode"] = threshold_mode
    write_hashed_json(output / "report_manifest.json", manifest)
    return manifest


def generate_reports(
    runs_root: Path,
    split_path: Path,
    cache_path: Path,
    output: Path,
    protocol_path: Path = Path("ml/configs/experiment_protocol.yaml"),
    threshold_mode: str = "search",
) -> dict[str, Any]:
    if threshold_mode not in {"search", "fixed_050"}:
        raise ValueError("Report threshold mode must be search or fixed_050.")
    if output.exists():
        raise FileExistsError("Report output exists; previous artifacts will not be overwritten.")
    output.mkdir(parents=True)
    protocol = load_experiment_protocol(protocol_path)
    digest = protocol_sha256(protocol_path)
    if not split_path.is_file() or not cache_path.is_file():
        return _write_templates(
            output,
            protocol,
            digest,
            ["Verified research split and cache are unavailable."],
            threshold_mode,
        )
    try:
        split, cache = load_split(split_path), load_cache(cache_path)
    except (ValueError, OSError) as error:
        return _write_templates(
            output,
            protocol,
            digest,
            [f"Split/cache integrity validation failed: {type(error).__name__}."],
            threshold_mode,
        )
    if split.data_kind != "research" or cache.data_kind != "research":
        return _write_templates(
            output,
            protocol,
            digest,
            ["Synthetic data cannot generate research tables or figures."],
            threshold_mode,
        )
    split_digest, cache_digest = sha256_file(split_path), sha256_file(cache_path)
    paths = sorted(runs_root.rglob("test_metrics.json")) if runs_root.is_dir() else []
    runs: dict[tuple[str, int], ResearchRun] = {}
    rejected: list[dict[str, str]] = []
    for path in paths:
        try:
            record = _load_run(path, protocol, digest, split_digest, cache_digest, threshold_mode)
            key = (record.condition, record.seed)
            if key in runs:
                raise ValueError("Duplicate condition/seed run.")
            runs[key] = record
        except (ValueError, OSError, KeyError) as error:
            rejected.append({"path": path.as_posix(), "reason": str(error)})
    expected_keys = {
        (condition, seed) for condition in protocol.conditions for seed in protocol.seeds
    }
    missing_runs = sorted(expected_keys - runs.keys())
    expected_patients = set(split.test)
    patient_gaps = {
        f"{condition}/seed-{seed}": sorted(expected_patients ^ set(run.patient_dice))
        for (condition, seed), run in runs.items()
        if set(run.patient_dice) != expected_patients
    }
    seed_metrics = {
        condition: {
            seed: runs[(condition, seed)].patient_dice
            for seed in protocol.seeds
            if (condition, seed) in runs
        }
        for condition in protocol.conditions
    }
    paired = summarize_paired_seed_metrics(seed_metrics, protocol, expected_patients)
    write_hashed_json(output / "paired_statistics.json", paired)
    ready = (
        not missing_runs
        and not rejected
        and not patient_gaps
        and cache.split_sha256 == split_digest
    )
    if not ready:
        reasons = [
            *(
                f"Missing preregistered run: {condition}/seed-{seed}."
                for condition, seed in missing_runs
            ),
            *(
                f"Patient-pair coverage gap in {run_id}: {len(ids)} missing/extra IDs."
                for run_id, ids in patient_gaps.items()
            ),
            *(f"Rejected artifact {item['path']}: {item['reason']}" for item in rejected),
            "Full-cohort charts/tables require six runs and one complete frozen patient cohort.",
        ]
        manifest = _not_run_manifest(protocol, digest, reasons)
        manifest.update(
            {
                "threshold_selection_mode": threshold_mode,
                "paired_statistics_status": paired["status"],
                "missing_runs": [f"{name}/seed-{seed}" for name, seed in missing_runs],
                "patient_coverage_gaps": patient_gaps,
                "rejected_artifacts": rejected,
                "paired_statistics_file": "paired_statistics.json",
            }
        )
        write_hashed_json(output / "report_manifest.json", manifest)
        return manifest

    ordered_runs = [
        runs[(condition, seed)] for condition in protocol.conditions for seed in protocol.seeds
    ]
    run_ids = [run.run_id for run in ordered_runs]
    artifacts: list[dict[str, Any]] = []
    artifacts.append(
        _source_record(
            output / "paired_statistics.json",
            run_ids,
            digest,
            split_digest,
            "paired patient-level test statistics",
            "Dice; p value; 95% CI",
            {
                "wilcoxon": protocol.statistics["wilcoxon"],
                "bootstrap": protocol.statistics["patient_pair_bootstrap"],
            },
        )
    )
    subset_rows: list[dict[str, Any]] = []
    for subset in ("train", "validation", "test"):
        ids = getattr(split, subset)
        records = [item for item in cache.slices if item.subset == subset]
        lesion_ids = {item.patient_id for item in records if item.has_lesion}
        subset_rows.append(
            {
                "subset": subset,
                "patients": len(ids),
                "lesion_patients": len(lesion_ids),
                "empty_gt_patients": len(ids) - len(lesion_ids),
                "slices": len(records),
                "lesion_slices": sum(item.has_lesion for item in records),
            }
        )
    _write_csv(
        output / "dataset_split_statistics.csv",
        subset_rows,
        ["subset", "patients", "lesion_patients", "empty_gt_patients", "slices", "lesion_slices"],
    )
    _record_artifact(
        output / "dataset_split_statistics.csv",
        artifacts,
        run_ids,
        digest,
        split_digest,
        "patient/slice cohort counts",
        "patients; slices",
    )

    resource_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []
    single_slice_rows: list[dict[str, Any]] = []
    aggregation_rows: list[dict[str, Any]] = []
    for run in ordered_runs:
        status = read_hashed_json(run.run_directory / "run_status.json")
        if not isinstance(status, dict) or any(
            status.get(key) != expected
            for key, expected in {
                "run_id": run.run_id,
                "condition_name": run.condition,
                "seed": run.seed,
                "data_kind": "research",
            }.items()
        ):
            raise ValueError(f"Run status provenance does not match {run.run_id}.")
        resource_rows.append(
            {
                "condition": run.condition,
                "seed": run.seed,
                "run_id": run.run_id,
                "parameters": run.report["parameter_count"],
                "checkpoint_bytes_including_optimizer": (run.run_directory / "best.ckpt")
                .stat()
                .st_size,
                "serialized_weights_bytes": run.report["model_weights_bytes"],
            }
        )
        with (run.run_directory / "metrics.csv").open(encoding="utf-8", newline="") as stream:
            curve_rows.extend(
                {"condition": run.condition, "seed": run.seed, "run_id": run.run_id, **row}
                for row in csv.DictReader(stream)
            )
        for patient, elapsed in run.report["research_metrics"][
            "case_batched_inference_milliseconds"
        ].items():
            timing_rows.append(
                {
                    "condition": run.condition,
                    "seed": run.seed,
                    "run_id": run.run_id,
                    "patient_id": patient,
                    "milliseconds_per_case": elapsed,
                    "timing_scope": run.report["research_metrics"]["timing_scope"],
                }
            )
        single_slice_rows.append(
            {
                "condition": run.condition,
                "seed": run.seed,
                "run_id": run.run_id,
                "milliseconds_per_slice": run.report["research_metrics"][
                    "single_slice_inference_milliseconds"
                ],
                "timing_scope": "warmed cached CPU forward pass; preprocessing excluded",
            }
        )
        for aggregation, values in run.report["research_metrics"]["aggregation"].items():
            if isinstance(values, dict) and all(
                metric in values for metric in ("dice", "iou", "precision", "recall")
            ):
                aggregation_rows.append(
                    {
                        "condition": run.condition,
                        "seed": run.seed,
                        "run_id": run.run_id,
                        "aggregation": aggregation,
                        **values,
                    }
                )
    tables = [
        (
            "model_parameters_and_size.csv",
            resource_rows,
            [
                "condition",
                "seed",
                "run_id",
                "parameters",
                "checkpoint_bytes_including_optimizer",
                "serialized_weights_bytes",
            ],
            "model resource use",
            "parameters; bytes",
        ),
        (
            "training_validation_curves.csv",
            curve_rows,
            [
                "condition",
                "seed",
                "run_id",
                "epoch",
                "data_kind",
                "train_loss",
                "validation_loss",
                "validation_patient_dice",
                "validation_patient_iou",
                "learning_rate",
                "stale_epochs",
            ],
            "epoch training loss and validation patient-macro WT Dice at fixed 0.50",
            "loss; Dice; learning rate",
        ),
        (
            "inference_timing_distribution.csv",
            timing_rows,
            ["condition", "seed", "run_id", "patient_id", "milliseconds_per_case", "timing_scope"],
            "case-level inference timing",
            "milliseconds per case",
        ),
        (
            "single_slice_inference_timing.csv",
            single_slice_rows,
            ["condition", "seed", "run_id", "milliseconds_per_slice", "timing_scope"],
            "warmed single-slice forward-pass timing",
            "milliseconds per slice",
        ),
        (
            "aggregation_metrics.csv",
            aggregation_rows,
            ["condition", "seed", "run_id", "aggregation", "dice", "iou", "precision", "recall"],
            "slice macro, patient macro and pooled voxel metrics per run",
            "dimensionless metrics",
        ),
    ]
    for filename, rows, columns, scope, units in tables:
        _write_csv(output / filename, rows, columns)
        _record_artifact(output / filename, artifacts, run_ids, digest, split_digest, scope, units)

    comparison_rows = []
    for condition, summary in paired["cross_seed_mean_std"].items():
        ci = paired["patient_pair_bootstrap_ci"]
        test = paired["paired_wilcoxon"]
        row: dict[str, Any] = {
            "condition": condition,
            "patients": paired["n_complete_paired_patients"],
            "mean_of_three_seed_patient_macro": summary["mean"],
            "sample_std_across_seed_patient_macros": summary["std_sample_ddof_1"],
            "paired_mean_difference_attention_minus_unet": ci.get("mean_difference"),
            "paired_bootstrap_ci95_lower": ci.get("lower"),
            "paired_bootstrap_ci95_upper": ci.get("upper"),
            "wilcoxon_two_sided_p": test.get("p_value"),
            "zero_differences_excluded": test.get("zero_differences_excluded"),
        }
        for metric in ("iou", "precision", "recall"):
            per_seed = [
                float(np.mean([run.patient_metrics[patient][metric] for patient in split.test]))
                for run in ordered_runs
                if run.condition == condition
            ]
            row[f"{metric}_mean_across_seeds"] = float(np.mean(per_seed))
            row[f"{metric}_sample_std_across_seeds"] = float(np.std(per_seed, ddof=1))
        comparison_rows.append(row)
    comparison_path = output / "model_comparison_and_gate_ablation.csv"
    _write_csv(comparison_path, comparison_rows, list(comparison_rows[0]))
    _record_artifact(
        comparison_path,
        artifacts,
        run_ids,
        digest,
        split_digest,
        "patient-level three-seed paired comparison; no slice/seed pseudoreplication",
        "Dice; p value; 95% CI",
    )

    patient_rows = [
        {
            "patient_id": patient,
            "condition": condition,
            "mean_patient_dice_across_three_seeds": value,
        }
        for condition, summary in paired["patient_distribution"].items()
        for patient, value in summary["patient_scores"].items()
    ]
    patient_path = output / "patient_dice_distribution.csv"
    _write_csv(
        patient_path,
        patient_rows,
        ["patient_id", "condition", "mean_patient_dice_across_three_seeds"],
    )
    _record_artifact(
        patient_path,
        artifacts,
        run_ids,
        digest,
        split_digest,
        "each patient's score averaged over paired seeds",
        "Dice",
    )
    patient_metric_rows = []
    for condition in protocol.conditions:
        matching_runs = [run for run in ordered_runs if run.condition == condition]
        for patient in split.test:
            row: dict[str, Any] = {"patient_id": patient, "condition": condition}
            for metric in ("dice", "iou", "precision", "recall"):
                row[f"mean_{metric}_across_three_seeds"] = float(
                    np.mean([run.patient_metrics[patient][metric] for run in matching_runs])
                )
            patient_metric_rows.append(row)
    patient_metrics_path = output / "patient_metrics_across_seeds.csv"
    patient_metrics_columns = [
        "patient_id",
        "condition",
        "mean_dice_across_three_seeds",
        "mean_iou_across_three_seeds",
        "mean_precision_across_three_seeds",
        "mean_recall_across_three_seeds",
    ]
    _write_csv(patient_metrics_path, patient_metric_rows, patient_metrics_columns)
    _record_artifact(
        patient_metrics_path,
        artifacts,
        run_ids,
        digest,
        split_digest,
        "patient metrics averaged across paired seeds",
        "dimensionless metrics",
        {"patient_is_independent_unit": True},
    )

    lesion_rows, volumes, volume_unit = _lesion_rows(split, cache, cache_path, paired, protocol)
    lesion_path = output / "lesion_volume_relationship.csv"
    _write_csv(
        lesion_path,
        lesion_rows,
        [
            "patient_id",
            "lesion_volume",
            "unit",
            "condition",
            "mean_patient_dice_across_three_seeds",
        ],
    )
    _record_artifact(
        lesion_path,
        artifacts,
        run_ids,
        digest,
        split_digest,
        "test patient lesion volume and patient Dice",
        volume_unit,
        {
            "spatial_metadata_required": True,
            "physical_unit": "mm3",
            "fallback": "voxels when spatial metadata is untrusted",
        },
    )

    figure_paths = _generate_figures(
        output,
        protocol,
        digest,
        split_digest,
        split,
        cache,
        ordered_runs,
        paired,
        curve_rows,
        timing_rows,
        single_slice_rows,
        volumes,
        volume_unit,
    )
    for path, scope, units, parameters in figure_paths:
        _record_artifact(path, artifacts, run_ids, digest, split_digest, scope, units, parameters)
    _write_cases(
        output,
        protocol,
        split,
        cache,
        cache_path,
        ordered_runs,
        paired,
        digest,
        split_digest,
        run_ids,
        artifacts,
    )
    artifact_sources = output / "artifact_sources.json"
    run_sources = {
        run.run_id: {
            "test_report": run.report_path.relative_to(runs_root).as_posix(),
            "test_report_sha256": sha256_file(run.report_path),
            "git_commit": run.report["git_commit"],
            "condition": run.condition,
            "architecture": run.report["architecture"],
            "model_version": run.report["model_version"],
            "preprocessing_version": run.report["preprocessing_version"],
            "seed": run.seed,
            "config_hash": run.report["config_hash"],
            "checkpoint_sha256": run.report["checkpoint_sha256"],
            "metrics_csv_sha256": sha256_file(run.run_directory / "metrics.csv"),
            "run_status_sha256": sha256_file(run.run_directory / "run_status.json"),
            "frozen_protocol_sha256": run.report["frozen_protocol_sha256"],
            "model_weight_sha256": run.report["model_weight_sha256"],
            "threshold": run.report["threshold"],
            "threshold_selection_mode": run.report["threshold_selection_mode"],
        }
        for run in ordered_runs
    }
    write_hashed_json(
        artifact_sources,
        {"run_sources": run_sources, "artifacts": {item["file"]: item for item in artifacts}},
    )
    manifest = {
        "status": "GeneratedFromResearchArtifacts",
        "data_kind": "research",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": digest,
        "split_sha256": split_digest,
        "cache_sha256": cache_digest,
        "reporting_script_version": PROTOCOL_SCRIPT_VERSION,
        "threshold_selection_mode": threshold_mode,
        "run_ids": run_ids,
        "complete_test_patient_count": len(split.test),
        "paired_statistics": paired,
        "report_parameters": {
            "figure_dpi": 160,
            "timing_histogram_bins": 20,
            "training_curve_aggregation": "arithmetic mean across paired seeds by epoch",
            "validation_curve_aggregation": "mean and sample standard deviation by epoch",
            "case_ranking": protocol.representative_cases,
        },
        "artifacts": artifacts,
        "artifact_sources": artifact_sources.name,
        "disclaimer": DISCLAIMER,
    }
    write_hashed_json(output / "report_manifest.json", manifest)
    return manifest


def _lesion_rows(
    split: SplitManifest,
    cache: Any,
    cache_path: Path,
    paired: dict[str, Any],
    protocol: ExperimentProtocol,
) -> tuple[list[dict[str, Any]], dict[str, float], str]:
    voxel_count: dict[str, int] = {}
    physical_count: dict[str, float | None] = {}
    for patient in split.test:
        mask, affine = load_original_mask(cache_path, patient, cache)
        count = int(mask.sum())
        voxel_count[patient] = count
        metadata = split.patients[patient]
        voxel_mm3 = _voxel_mm3(metadata, affine)
        physical_count[patient] = count * voxel_mm3 if voxel_mm3 is not None else None
    use_physical = all(value is not None for value in physical_count.values())
    volume_unit = "mm3" if use_physical else "voxels"
    volumes = {
        patient: float(physical_count[patient] if use_physical else voxel_count[patient])
        for patient in split.test
    }
    patient_scores = {
        condition: summary["patient_scores"]
        for condition, summary in paired["patient_distribution"].items()
    }
    rows = [
        {
            "patient_id": patient,
            "lesion_volume": volumes[patient],
            "unit": volume_unit,
            "condition": condition,
            "mean_patient_dice_across_three_seeds": patient_scores[condition][patient],
        }
        for patient in split.test
        for condition in protocol.conditions
    ]
    return rows, volumes, volume_unit


def _generate_figures(
    output: Path,
    protocol: ExperimentProtocol,
    protocol_digest: str,
    split_digest: str,
    split: SplitManifest,
    cache: Any,
    runs: list[ResearchRun],
    paired: dict[str, Any],
    curve_rows: list[dict[str, Any]],
    timing_rows: list[dict[str, Any]],
    single_slice_rows: list[dict[str, Any]],
    volumes: dict[str, float],
    volume_unit: str,
) -> list[tuple[Path, str, str, dict[str, Any]]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    del protocol_digest, split_digest
    artifacts: list[tuple[Path, str, str, dict[str, Any]]] = []
    patient_scores = {
        condition: value["patient_scores"]
        for condition, value in paired["patient_distribution"].items()
    }

    figure, axis = plt.subplots()
    axis.boxplot(
        [
            [patient_scores[condition][patient] for patient in split.test]
            for condition in protocol.conditions
        ],
        tick_labels=list(protocol.conditions),
        showmeans=True,
    )
    axis.set_ylabel("Patient-level Whole Tumor Dice (mean over paired seeds)")
    axis.set_title("Patient-level Dice distribution")
    path = output / "patient_dice_distribution.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "each patient averaged across three paired seeds",
            "Dice",
            {"plot": "boxplot", "show_means": True, "patient_order": "split manifest order"},
        )
    )

    figure, axis = plt.subplots()
    for condition in protocol.conditions:
        rows = [row for row in curve_rows if row["condition"] == condition]
        epochs = sorted({int(row["epoch"]) for row in rows})
        means = [
            float(
                np.mean(
                    [float(row["validation_loss"]) for row in rows if int(row["epoch"]) == epoch]
                )
            )
            for epoch in epochs
        ]
        axis.plot(epochs, means, label=condition)
    axis.set_xlabel("Epoch")
    axis.set_ylabel("Validation BCE+Dice loss")
    axis.legend()
    path = output / "validation_loss_curves.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "validation loss averaged across paired seeds by epoch",
            "loss",
            {"aggregation": "arithmetic mean", "group_by": "epoch and condition"},
        )
    )

    figure, axis = plt.subplots()
    for condition in protocol.conditions:
        rows = [row for row in curve_rows if row["condition"] == condition]
        epochs = sorted({int(row["epoch"]) for row in rows})
        means = [
            float(np.mean([float(row["train_loss"]) for row in rows if int(row["epoch"]) == epoch]))
            for epoch in epochs
        ]
        axis.plot(epochs, means, label=condition)
    axis.set_xlabel("Epoch")
    axis.set_ylabel("Training BCE+Dice loss")
    axis.legend()
    path = output / "training_loss_curves.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "training loss averaged across paired seeds by epoch",
            "loss",
            {"aggregation": "arithmetic mean", "group_by": "epoch and condition"},
        )
    )

    figure, axis = plt.subplots()
    for condition in protocol.conditions:
        rows = [row for row in curve_rows if row["condition"] == condition]
        epochs = sorted({int(row["epoch"]) for row in rows})
        means = [
            float(
                np.mean(
                    [
                        float(row["validation_patient_dice"])
                        for row in rows
                        if int(row["epoch"]) == epoch
                    ]
                )
            )
            for epoch in epochs
        ]
        deviations = [
            float(
                np.std(
                    [
                        float(row["validation_patient_dice"])
                        for row in rows
                        if int(row["epoch"]) == epoch
                    ],
                    ddof=1,
                )
            )
            for epoch in epochs
        ]
        axis.plot(epochs, means, label=condition)
        axis.fill_between(
            epochs, np.asarray(means) - deviations, np.asarray(means) + deviations, alpha=0.15
        )
    axis.set_xlabel("Epoch")
    axis.set_ylabel("Validation patient-macro WT Dice at 0.50")
    axis.legend()
    path = output / "validation_patient_dice_curves.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "validation patient-macro Dice averaged across paired seeds",
            "Dice",
            {
                "aggregation": "mean and sample standard deviation",
                "threshold": 0.50,
                "group_by": "epoch and condition",
            },
        )
    )

    figure, axis = plt.subplots()
    for condition in protocol.conditions:
        axis.scatter(
            [volumes[patient] for patient in split.test],
            [patient_scores[condition][patient] for patient in split.test],
            label=condition,
            alpha=0.7,
        )
    axis.set_xlabel(f"Ground-truth Whole Tumor volume ({volume_unit})")
    axis.set_ylabel("Patient-level WT Dice (mean over paired seeds)")
    axis.legend()
    path = output / "lesion_volume_vs_patient_dice.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "test-patient lesion volume versus patient-macro Dice",
            volume_unit,
            {"volume_source": "ground-truth Whole Tumor", "require_trusted_spatial_metadata": True},
        )
    )

    figure, axis = plt.subplots()
    for condition in protocol.conditions:
        values = [
            float(row["milliseconds_per_case"])
            for row in timing_rows
            if row["condition"] == condition
        ]
        axis.hist(values, bins=20, alpha=0.45, label=condition)
    axis.set_xlabel("Cached CPU inference time per patient (ms; preprocessing excluded)")
    axis.set_ylabel("Run-patient observations")
    axis.legend()
    path = output / "case_inference_timing.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "case inference timing from test reports",
            "milliseconds per case",
            {"plot": "histogram", "bins": 20, "timing_scope": "cached CPU; preprocessing excluded"},
        )
    )

    figure, axis = plt.subplots()
    axis.boxplot(
        [
            [
                float(row["milliseconds_per_slice"])
                for row in single_slice_rows
                if row["condition"] == condition
            ]
            for condition in protocol.conditions
        ],
        tick_labels=list(protocol.conditions),
        showmeans=True,
    )
    axis.set_ylabel("Warmed single-slice CPU inference time (ms)")
    axis.set_title("Single-slice inference timing")
    path = output / "single_slice_inference_timing.png"
    _save_figure(figure, path)
    artifacts.append(
        (
            path,
            "one warmed single-slice forward-pass measurement per run",
            "milliseconds per slice",
            {"plot": "boxplot", "show_means": True, "observations_per_condition": 3},
        )
    )
    return artifacts


def _write_cases(
    output: Path,
    protocol: ExperimentProtocol,
    split: SplitManifest,
    cache: Any,
    cache_path: Path,
    runs: list[ResearchRun],
    paired: dict[str, Any],
    protocol_digest: str,
    split_digest: str,
    run_ids: list[str],
    artifacts: list[dict[str, Any]],
) -> None:
    patient_scores = {
        condition: summary["patient_scores"]
        for condition, summary in paired["patient_distribution"].items()
    }
    ranked = sorted(
        (
            float(
                np.mean([patient_scores[condition][patient] for condition in protocol.conditions])
            ),
            patient,
        )
        for patient in split.test
    )
    best_score = ranked[-1][0]
    best = min((item for item in ranked if item[0] == best_score), key=lambda item: item[1])
    selected = [("worst", ranked[0]), ("median", ranked[(len(ranked) - 1) // 2]), ("best", best)]
    seed = int(protocol.representative_cases["visualization_seed"])
    slices_by_patient: dict[str, list[Any]] = {}
    for record in cache.slices:
        if record.subset == "test":
            slices_by_patient.setdefault(record.patient_id, []).append(record)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(3, 6, figsize=(20, 10))
    rows: list[dict[str, Any]] = []
    for row_index, (rank, (score, patient)) in enumerate(selected):
        gt, _ = load_original_mask(cache_path, patient, cache)
        lesion_slices = [index for index in range(gt.shape[2]) if gt[:, :, index].any()]
        slice_index = (
            min(lesion_slices, key=lambda index: (-int(gt[:, :, index].sum()), index))
            if lesion_slices
            else gt.shape[2] // 2
        )
        record = next(
            item for item in slices_by_patient[patient] if item.slice_index == slice_index
        )
        with np.load(cache_path.parent / record.path, allow_pickle=False) as data:
            flair = data["image"]
        panels = [
            (0, flair, f"{rank}: {patient} FLAIR z={slice_index}"),
            (1, gt[:, :, slice_index], "Ground-truth WT"),
        ]
        for column, condition in ((2, "UNet"), (3, "AttentionUNet")):
            run = next(item for item in runs if item.condition == condition and item.seed == seed)
            prediction_path = (
                run.run_directory / "test" / "patient_masks" / f"{patient}_pred.nii.gz"
            )
            prediction = nib.load(prediction_path).get_fdata(dtype=np.float32)
            if prediction.shape != gt.shape:
                raise ValueError(
                    "Representative prediction geometry differs from the original patient volume."
                )
            prediction_slice = prediction[:, :, slice_index].astype(bool)
            truth_slice = gt[:, :, slice_index].astype(bool)
            panels.append((column, prediction_slice, f"{condition}; seed={seed}"))
            resized_prediction = resize_mask(prediction_slice.astype(np.uint8)).astype(bool)
            resized_truth = resize_mask(truth_slice.astype(np.uint8)).astype(bool)
            intensity = flair.astype(np.float32)
            low, high = float(np.min(intensity)), float(np.max(intensity))
            if high > low:
                intensity = (intensity - low) / (high - low)
            errors = np.repeat(intensity[:, :, None] * 0.25, 3, axis=2)
            errors[resized_truth & resized_prediction] = (0.0, 0.8, 0.0)
            errors[resized_prediction & ~resized_truth] = (1.0, 0.0, 0.0)
            errors[resized_truth & ~resized_prediction] = (0.0, 0.2, 1.0)
            panels.append((column + 2, errors, f"{condition} errors: FP red, FN blue"))
        for column, image, title in panels:
            axes[row_index, column].imshow(
                image,
                cmap="gray" if column < 4 else None,
                vmin=0 if column else None,
                vmax=1 if column else None,
            )
            axes[row_index, column].set_title(title)
            axes[row_index, column].set_axis_off()
        rows.append(
            {
                "rank": rank,
                "patient_id": patient,
                "mean_dice_across_models_and_seeds": score,
                "slice_index": slice_index,
                "selection_rule": protocol.representative_cases["score"],
            }
        )
    path = output / "typical_best_median_worst_cases.png"
    _save_figure(figure, path)
    artifacts.append(
        _source_record(
            path,
            run_ids,
            protocol_digest,
            split_digest,
            "predeclared best/lower-median/worst complete test patients",
            "axial slice; binary mask and FP/FN overlay",
            {
                "patient_ranking": protocol.representative_cases["score"],
                "tie_break": protocol.representative_cases["tie_break"],
                "visualization_seed": seed,
                "slice_rule": protocol.representative_cases["slice_rule"],
                "overlay_colors": {
                    "false_positive": "red",
                    "false_negative": "blue",
                    "true_positive": "green",
                },
            },
        )
    )
    table = output / "typical_cases.csv"
    _write_csv(
        table,
        rows,
        [
            "rank",
            "patient_id",
            "mean_dice_across_models_and_seeds",
            "slice_index",
            "selection_rule",
        ],
    )
    artifacts.append(
        _source_record(
            table,
            run_ids,
            protocol_digest,
            split_digest,
            "predeclared ranking over the complete frozen test cohort",
            "Dice; axial slice index",
            {
                "patient_ranking": protocol.representative_cases["score"],
                "tie_break": protocol.representative_cases["tie_break"],
            },
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--runs", type=Path, default=Path("artifacts/runs"))
    parser.add_argument("--split", type=Path, default=Path("artifacts/split_manifest.json"))
    parser.add_argument("--cache", type=Path, default=Path("artifacts/preprocessed/index.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--protocol", type=Path, default=Path("ml/configs/experiment_protocol.yaml")
    )
    parser.add_argument("--threshold-mode", choices=["search", "fixed_050"], default="search")
    arguments = parser.parse_args()
    result = generate_reports(
        arguments.runs,
        arguments.split,
        arguments.cache,
        arguments.output,
        arguments.protocol,
        arguments.threshold_mode,
    )
    print(yaml.safe_dump(result, sort_keys=True, allow_unicode=True))


if __name__ == "__main__":
    main()
