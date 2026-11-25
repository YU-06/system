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
from training.models import UNet, build_model
from training.preprocess import CacheManifest, load_cache
from training.protocol import TrainingConfig, read_hashed_json, resolve_data_path, sha256_file


def config_hash(config: TrainingConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


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
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise ValueError("Checkpoint config, split or cache provenance changed.")
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
    expected = {
        "config_hash": config_hash(config),
        "split_sha256": sha256_file(Path(config.split_manifest)),
        "cache_sha256": sha256_file(Path(config.cache_index)),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_threshold": config.threshold,
        "threshold_source": "validation_only",
        "data_kind": "synthetic" if config.execution_mode == "smoke" else "research",
    }
    if any(freeze.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Frozen model, threshold, configuration or dataset changed; test execution denied."
        )
    if freeze.get("threshold") not in config.validation_thresholds:
        raise ValueError("The frozen threshold was not a configured validation candidate.")
    report_name = freeze.get("validation_report")
    if not isinstance(report_name, str):
        raise ValueError("Freeze must reference the actual validation report.")
    report_path = resolve_data_path(path.parent, report_name)
    if sha256_file(report_path) != freeze.get("validation_report_sha256"):
        raise ValueError("The frozen validation evidence changed.")
    report = read_hashed_json(report_path)
    if not isinstance(report, dict) or report.get("subset") != "validation":
        raise ValueError("Only actual validation evidence can unlock testing.")
    return freeze
