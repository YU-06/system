import csv
import hashlib
import json
import os
import platform
import random
import subprocess
from pathlib import Path

import nibabel
import numpy as np
import torch
import yaml

from training import DISCLAIMER
from training.create_split import load_split
from training.experiment_protocol import load_experiment_protocol, protocol_sha256
from training.models import UNet, build_model
from training.preprocess import CacheManifest, load_cache
from training.protocol import (
    TrainingConfig,
    config_hash,
    read_hashed_json,
    resolve_data_path,
    sha256_file,
)


def state_dict_sha256(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        value = state[name].detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(json.dumps(list(value.shape), separators=(",", ":")).encode("ascii"))
        digest.update(value.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def checked_cache(config: TrainingConfig) -> CacheManifest:
    split_path = Path(config.split_manifest)
    split = load_split(split_path)
    cache = load_cache(Path(config.cache_index))
    expected_kind = "synthetic" if config.execution_mode == "smoke" else "research"
    if split.data_kind != expected_kind or cache.data_kind != expected_kind:
        raise ValueError("Research and synthetic execution modes cannot be mixed.")
    if cache.split_sha256 != sha256_file(split_path) or set(cache.patients) != set(split.patients):
        raise ValueError("Cache and patient split provenance do not match.")
    if [len(split.train), len(split.validation), len(split.test)] != [
        config.train_patients,
        config.validation_patients,
        config.test_patients,
    ]:
        raise ValueError("Configured patient counts do not match the split manifest.")
    for identifier in split.train:
        if cache.patients[identifier].subset != "train":
            raise ValueError("Patient split leakage detected.")
    for identifier in split.validation:
        if cache.patients[identifier].subset != "validation":
            raise ValueError("Patient split leakage detected.")
    for identifier in split.test:
        if cache.patients[identifier].subset != "test":
            raise ValueError("Patient split leakage detected.")
    return cache


def capture_rng() -> dict:
    state = np.random.get_state()
    return {
        "python": random.getstate(),
        "numpy": (state[0], torch.tensor(state[1].astype(np.int64)), state[2], state[3], state[4]),
        "torch": torch.get_rng_state(),
    }


def restore_rng(state: dict) -> None:
    random.setstate(state["python"])
    name, keys, position, gaussian, cached = state["numpy"]
    np.random.set_state((name, keys.cpu().numpy().astype(np.uint32), position, gaussian, cached))
    torch.set_rng_state(state["torch"])


def save_checkpoint(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temporary)
    os.replace(temporary, path)


def load_checkpoint(path: Path, config: TrainingConfig) -> dict:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1:
        raise ValueError("Unsupported checkpoint schema.")
    expected = {
        "config_hash": config_hash(config),
        "split_sha256": sha256_file(Path(config.split_manifest)),
        "cache_sha256": sha256_file(Path(config.cache_index)),
        "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise ValueError("Checkpoint config, split or cache provenance changed.")
    state = checkpoint.get("model_state")
    if not isinstance(state, dict) or state_dict_sha256(state) != checkpoint.get(
        "model_weight_sha256"
    ):
        raise ValueError("Checkpoint model-weight digest does not match the saved tensor state.")
    if (
        checkpoint.get("architecture") not in config.architectures
        or checkpoint.get("seed") not in config.experiment_seeds
    ):
        raise ValueError("Checkpoint architecture or seed is outside the configured protocol.")
    return checkpoint


def checkpoint_model(path: Path, config: TrainingConfig) -> tuple[UNet, dict]:
    checked_cache(config)
    checkpoint = load_checkpoint(path, config)
    model = build_model(checkpoint["architecture"], config.channels)
    model.load_state_dict(checkpoint["model_state"], strict=True)
    return model, checkpoint


def initialize_run(directory: Path, config: TrainingConfig) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.yaml").write_text(
        yaml.safe_dump(config.model_dump(), sort_keys=True), encoding="utf-8"
    )
    split_path = Path(config.split_manifest)
    protocol_path = Path(config.experiment_protocol_path)
    (directory / "experiment_protocol.yaml").write_bytes(protocol_path.read_bytes())
    (directory / "experiment_protocol.yaml.sha256").write_text(
        protocol_sha256(protocol_path) + "\n", encoding="ascii"
    )
    (directory / "split_manifest.json").write_bytes(split_path.read_bytes())
    (directory / "split_manifest.json.sha256").write_text(
        sha256_file(split_path) + "\n", encoding="ascii"
    )
    environment = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "nibabel": nibabel.__version__,
        "device": "cpu",
        "cuda_runtime": "NotRun (CPU-only)",
        "disclaimer": DISCLAIMER,
    }
    (directory / "environment.txt").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        commit = "NotRun"
    (directory / "git_commit.txt").write_text(commit + "\n", encoding="ascii")


def reconcile_history(path: Path, checkpoint: dict, fields: list[str]) -> None:
    if not path.is_file():
        raise ValueError("Resume requires the original epoch history.")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    completed = int(checkpoint["epoch"])
    committed = {int(row["epoch"]): row for row in rows if int(row["epoch"]) <= completed}
    committed[completed] = checkpoint["epoch_metrics"]
    if set(committed) != set(range(1, completed + 1)):
        raise ValueError("Checkpoint history is incomplete; missing epochs cannot be fabricated.")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(committed[index] for index in range(1, completed + 1))


def verify_freeze(path: Path, checkpoint_path: Path, config: TrainingConfig) -> dict:
    if not path.is_file():
        raise ValueError("Test execution is locked until a validation protocol freeze exists.")
    freeze = read_hashed_json(path)
    if not isinstance(freeze, dict) or freeze.get("kind") != "validation_protocol_freeze":
        raise ValueError("Invalid validation protocol freeze.")
    required = {
        "git_commit",
        "split_sha256",
        "config_hash",
        "protocol_sha256",
        "cache_sha256",
        "checkpoint_sha256",
        "model_weight_sha256",
        "architecture",
        "condition_name",
        "model_version",
        "preprocessing_version",
        "seed",
        "run_id",
        "threshold",
        "threshold_selection_mode",
        "evaluation_protocol",
        "validation_report_sha256",
        "validation_report",
        "threshold_source",
        "training_threshold",
        "data_kind",
    }
    missing = required - freeze.keys()
    if missing:
        raise ValueError(f"Protocol freeze is incomplete: {sorted(missing)}")
    checkpoint = load_checkpoint(checkpoint_path, config)
    protocol = load_experiment_protocol(Path(config.experiment_protocol_path))
    expected = {
        "config_hash": config_hash(config),
        "split_sha256": sha256_file(Path(config.split_manifest)),
        "cache_sha256": sha256_file(Path(config.cache_index)),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
        "evaluation_protocol": protocol.protocol_id,
        "preprocessing_version": config.preprocessing_version,
        "training_threshold": config.threshold,
        "threshold_source": "validation_only",
        "data_kind": "synthetic" if config.execution_mode == "smoke" else "research",
    }
    if any(freeze.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Frozen model, threshold, configuration or dataset changed; test execution denied."
        )
    if (
        not isinstance(freeze["threshold"], (int, float))
        or not np.isfinite(freeze["threshold"])
        or freeze["threshold"] not in config.validation_thresholds
    ):
        raise ValueError("The frozen threshold was not a configured validation candidate.")
    report_name = freeze["validation_report"]
    if not isinstance(report_name, str):
        raise ValueError("Freeze must reference the actual validation report.")
    report_path = resolve_data_path(path.parent, report_name)
    if sha256_file(report_path) != freeze.get("validation_report_sha256"):
        raise ValueError("The frozen validation evidence changed.")
    report = read_hashed_json(report_path)
    if (
        not isinstance(report, dict)
        or report.get("subset") != "validation"
        or report.get("data_kind") != freeze["data_kind"]
    ):
        raise ValueError("Only actual validation evidence can unlock testing.")
    if not freeze["git_commit"] or freeze["git_commit"] == "NotRun":
        raise ValueError("A source commit is required to freeze the testing protocol.")
    if freeze["threshold_selection_mode"] not in {"search", "fixed_050"}:
        raise ValueError("Unknown frozen validation threshold selection mode.")
    from training.experiment_protocol import select_validation_threshold

    threshold_rows = report.get("validation_threshold_search")
    expected_thresholds = (
        protocol.model_selection["candidate_thresholds"]
        if freeze["threshold_selection_mode"] == "search"
        else [protocol.model_selection["sensitivity_threshold"]]
    )
    if not isinstance(threshold_rows, list) or any(
        not isinstance(row, dict) or set(row) != {"threshold", "validation_patient_dice"}
        for row in threshold_rows
    ):
        raise ValueError("Validation report is missing its threshold-selection evidence.")
    threshold_scores = {row["threshold"]: row["validation_patient_dice"] for row in threshold_rows}
    if list(threshold_scores) != expected_thresholds:
        raise ValueError(
            "Validation report does not contain the preregistered threshold candidates."
        )
    selected_threshold = select_validation_threshold(
        threshold_scores, protocol, freeze["threshold_selection_mode"]
    )
    if selected_threshold != freeze["threshold"]:
        raise ValueError("Frozen threshold is not the selected validation-only threshold.")
    selected_report_score = threshold_scores[freeze["threshold"]]
    if not isinstance(selected_report_score, (int, float)) or not np.isfinite(
        selected_report_score
    ):
        raise ValueError("Selected validation report score is invalid.")
    metrics_key = (
        "research_metrics" if freeze["data_kind"] == "research" else "synthetic_smoke_measurements"
    )
    selected_metrics = report.get(metrics_key, {})
    patient_metrics = (
        selected_metrics.get("patients") if isinstance(selected_metrics, dict) else None
    )
    if not isinstance(patient_metrics, dict) or not patient_metrics:
        raise ValueError("Validation report is missing reconstructed patient-level metrics.")
    if freeze["data_kind"] == "research":
        split = load_split(Path(config.split_manifest))
        if set(patient_metrics) != set(split.validation):
            raise ValueError(
                "Validation evidence does not cover the complete frozen patient cohort."
            )
    observed_dice = [
        value.get("dice") for value in patient_metrics.values() if isinstance(value, dict)
    ]
    if len(observed_dice) != len(patient_metrics) or any(
        not isinstance(value, (int, float)) or not np.isfinite(value) or not 0 <= value <= 1
        for value in observed_dice
    ):
        raise ValueError("Validation report contains invalid patient-level Dice values.")
    selected_score = float(np.mean(observed_dice))
    if not np.isclose(selected_score, selected_report_score, rtol=0, atol=1e-12):
        raise ValueError(
            "Selected validation score does not match reconstructed patient-level Dice."
        )
    for key in ("run_id", "architecture", "condition_name", "model_version", "seed", "git_commit"):
        if freeze[key] != checkpoint.get(key):
            raise ValueError(f"Protocol freeze {key} does not match the checkpoint.")
    if freeze["model_weight_sha256"] != checkpoint["model_weight_sha256"]:
        raise ValueError("Frozen model-weight digest does not match the checkpoint tensor state.")
    if (
        report.get("threshold") != freeze["threshold"]
        or report.get("threshold_selection_mode") != freeze["threshold_selection_mode"]
        or report.get("run_id") != freeze["run_id"]
        or report.get("git_commit") != freeze["git_commit"]
        or report.get("checkpoint_sha256") != freeze["checkpoint_sha256"]
        or report.get("model_weight_sha256") != freeze["model_weight_sha256"]
        or report.get("protocol_sha256") != freeze["protocol_sha256"]
        or report.get("evaluation_protocol") != freeze["evaluation_protocol"]
        or report.get("data_kind") != freeze["data_kind"]
    ):
        raise ValueError("Validation evidence does not match the frozen threshold selection.")
    return freeze
