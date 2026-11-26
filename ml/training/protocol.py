import hashlib
import json
import os
import random
import re
from importlib import import_module
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from training import DISCLAIMER, PREPROCESSING_VERSION


class TrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: Literal["BraTS 2020"]
    modality: Literal["T2-FLAIR"]
    task: Literal["2D axial Whole Tumor binary segmentation"]
    dataset_root: str
    preprocessing_version: Literal["flair-v1"]
    input_size: Literal[256]
    train_patients: int = Field(gt=0)
    validation_patients: int = Field(gt=0)
    test_patients: int = Field(gt=0)
    execution_mode: Literal["research", "smoke"] = "research"
    split_manifest: str = "artifacts/split_manifest.json"
    cache_index: str = "artifacts/preprocessed/index.json"
    experiment_protocol_path: str = "ml/configs/experiment_protocol.yaml"
    output_directory: str = "artifacts/runs"
    split_seed: int = 42
    experiment_seeds: list[int]
    architectures: list[Literal["UNet", "AttentionUNet"]]
    channels: list[int]
    foreground_labels: list[int]
    loss: Literal["BCEWithLogitsLoss+DiceLoss"]
    optimizer: Literal["Adam"]
    learning_rate: float = Field(gt=0)
    batch_size: int = Field(gt=0)
    max_epochs: int = Field(gt=0, le=100)
    early_stopping_patience: Literal[15]
    checkpoint_metric: Literal["validation_dice"]
    threshold: float = Field(gt=0, lt=1)
    threshold_source: Literal["validation_only"]
    validation_thresholds: list[float] = Field(default_factory=lambda: [0.5])
    augmentation: dict[str, bool]
    device: Literal["cpu"]
    test_execution: Literal["locked_until_protocol_frozen"]
    result_status: Literal["NotRun"]
    bce_weight: float = Field(default=0.5, ge=0, le=1)
    dice_smoothing: float = Field(default=1e-6, gt=0)
    train_empty_fraction: float = Field(default=0.5, ge=0, lt=1)
    horizontal_flip_probability: float = Field(default=0.5, ge=0, le=1)
    vertical_flip_probability: float = Field(default=0.5, ge=0, le=1)
    rotate_90: bool = True
    num_workers: int = Field(default=0, ge=0)
    cpu_threads: int = Field(default=2, ge=1)
    early_stopping_min_delta: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def validate_comparison(self) -> "TrainingConfig":
        if self.experiment_seeds != [17, 42, 2024]:
            raise ValueError("The paired research seeds are fixed to [17, 42, 2024].")
        if self.architectures != ["UNet", "AttentionUNet"] or self.foreground_labels != [1, 2, 4]:
            raise ValueError(
                "The fixed architecture comparison and label mapping must be preserved."
            )
        if self.augmentation != {"train": True, "validation": False, "test": False}:
            raise ValueError("Augmentation is allowed only for the training split.")
        if len(self.channels) != 5 or any(channel <= 0 for channel in self.channels):
            raise ValueError("Five positive shared channel sizes are required.")
        if self.execution_mode == "research" and (
            self.train_patients,
            self.validation_patients,
            self.test_patients,
        ) != (258, 74, 37):
            raise ValueError("Research training requires the fixed patient split 258/74/37.")
        if (
            not self.validation_thresholds
            or len(set(self.validation_thresholds)) != len(self.validation_thresholds)
            or any(
                not np.isfinite(value) or not 0 < value < 1 for value in self.validation_thresholds
            )
        ):
            raise ValueError(
                "Validation threshold candidates must be distinct finite values in (0, 1)."
            )
        if self.execution_mode == "research" and self.validation_thresholds != [
            0.3,
            0.35,
            0.4,
            0.45,
            0.5,
            0.55,
            0.6,
            0.65,
            0.7,
        ]:
            raise ValueError("The research threshold search is fixed to 0.30-0.70 in 0.05 steps.")
        return self


def load_config(path: Path) -> TrainingConfig:
    return TrainingConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def config_hash(config: TrainingConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_hashed_json(path: Path, value: object) -> str:
    payload = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    return digest


def read_hashed_json(path: Path) -> object:
    payload = path.read_bytes()
    expected = path.with_suffix(path.suffix + ".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("Manifest integrity validation failed.")
    return json.loads(payload)


def resolve_data_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Dataset paths must reference existing files inside the dataset root.")
    return path


def set_global_seed(seed: int, *, include_torch: bool = True) -> None:
    random.seed(seed)
    np.random.seed(seed)
    if include_torch:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        try:
            torch = import_module("torch")
        except ImportError as error:
            raise RuntimeError("Install the training extra before seeding PyTorch.") from error
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True)


def create_patient_split(patient_ids: list[str], output: Path, seed: int = 42) -> str:
    if len(patient_ids) != 369 or len(set(patient_ids)) != 369:
        raise ValueError("Exactly 369 distinct BraTS 2020 patient identifiers are required.")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier) for identifier in patient_ids):
        raise ValueError("Only pseudonymous patient identifiers are accepted, not paths.")
    shuffled = sorted(patient_ids)
    random.Random(seed).shuffle(shuffled)
    manifest = {
        "dataset": "BraTS 2020",
        "modality": "T2-FLAIR",
        "preprocessingVersion": PREPROCESSING_VERSION,
        "splitUnit": "patient",
        "seed": seed,
        "train": shuffled[:258],
        "validation": shuffled[258:332],
        "test": shuffled[332:],
        "disclaimer": DISCLAIMER,
    }
    payload = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    return digest
