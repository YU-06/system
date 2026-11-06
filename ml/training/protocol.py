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
    train_patients: Literal[258]
    validation_patients: Literal[74]
    test_patients: Literal[37]
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
    augmentation: dict[str, bool]
    device: Literal["cpu"]
    test_execution: Literal["locked_until_protocol_frozen"]
    result_status: Literal["NotRun"]

    @model_validator(mode="after")
    def validate_comparison(self) -> "TrainingConfig":
        if len(set(self.experiment_seeds)) < 3:
            raise ValueError("At least three distinct experiment seeds are required.")
        if self.architectures != ["UNet", "AttentionUNet"] or self.foreground_labels != [1, 2, 4]:
            raise ValueError(
                "The fixed architecture comparison and label mapping must be preserved."
            )
        if self.augmentation != {"train": True, "validation": False, "test": False}:
            raise ValueError("Augmentation is allowed only for the training split.")
        if not self.channels or any(channel <= 0 for channel in self.channels):
            raise ValueError("Positive shared channel sizes are required.")
        return self


def load_config(path: Path) -> TrainingConfig:
    return TrainingConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


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
