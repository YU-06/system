import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from training import DISCLAIMER
from training.protocol import TrainingConfig

PROTOCOL_PATH = Path("ml/configs/experiment_protocol.yaml")
PROTOCOL_SCRIPT_VERSION = "experiment-report-v1"
ALLOWED_DIFFERENCES = frozenset({"model.architecture", "model.attention_gate", "run_id"})
ABLATION_MATRIX_PATH = Path("ml/configs/ablation_matrix.yaml")


class ModelCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    architecture: Literal["UNet", "AttentionUNet"]
    attention_gate: bool
    model_version: str
    run_id_prefix: str = Field(pattern=r"^[a-z][a-z0-9-]{0,40}$")


class ExperimentProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_id: str
    protocol_version: Literal[1]
    dataset: Literal["BraTS 2020"]
    modality: Literal["T2-FLAIR"]
    task: Literal["2D axial Whole Tumor binary segmentation"]
    preprocessing_version: Literal["flair-v1"]
    split: dict[str, Any]
    seeds: list[int]
    shared_training: dict[str, Any]
    conditions: dict[str, ModelCondition]
    ablation: dict[str, Any]
    allowed_condition_difference_paths: list[str]
    model_selection: dict[str, Any]
    evaluation: dict[str, Any]
    statistics: dict[str, Any]
    lesion_volume: dict[str, Any]
    representative_cases: dict[str, Any]
    reporting: dict[str, Any]
    disclaimer: str

    @model_validator(mode="after")
    def enforce_frozen_protocol(self) -> "ExperimentProtocol":
        if self.seeds != [17, 42, 2024]:
            raise ValueError("Paired seeds are fixed to [17, 42, 2024].")
        if self.split != {"unit": "patient", "counts": [258, 74, 37], "seed": 42}:
            raise ValueError("Research split is fixed to 258/74/37 patients with seed 42.")
        expected_training = {
            "input_size": 256,
            "channels": [32, 64, 128, 256, 512],
            "foreground_labels": [1, 2, 4],
            "loss": "BCEWithLogitsLoss+DiceLoss",
            "bce_weight": 0.5,
            "dice_smoothing": 0.000001,
            "optimizer": "Adam",
            "learning_rate": 0.0001,
            "batch_size": 16,
            "max_epochs": 100,
            "early_stopping_patience": 15,
            "early_stopping_min_delta": 0.0,
            "train_empty_fraction": 0.5,
            "augmentation": {
                "train": "synchronized_horizontal_vertical_flip_and_90_degree_rotation",
                "validation": "none",
                "test": "none",
            },
            "horizontal_flip_probability": 0.5,
            "vertical_flip_probability": 0.5,
            "rotate_90": True,
            "device": "cpu",
            "num_workers": 0,
            "cpu_threads": 2,
            "test_patient_subset": "locked_until_validation_protocol_freeze",
        }
        if any(self.shared_training.get(key) != value for key, value in expected_training.items()):
            raise ValueError("Shared training controls must match the preregistered protocol.")
        if set(self.conditions) != {"UNet", "AttentionUNet"}:
            raise ValueError("The only primary comparison is U-Net versus Attention U-Net.")
        if (
            self.conditions["UNet"].attention_gate
            or not self.conditions["AttentionUNet"].attention_gate
        ):
            raise ValueError("Attention Gate must be the sole declared architectural ablation.")
        if (
            self.conditions["UNet"].architecture != "UNet"
            or self.conditions["AttentionUNet"].architecture != "AttentionUNet"
        ):
            raise ValueError("Each preregistered condition must use its named architecture.")
        if (
            self.conditions["UNet"].model_version != "unet-v1"
            or self.conditions["AttentionUNet"].model_version != "attention-gate-v1"
        ):
            raise ValueError("Model definition versions must remain preregistered.")
        if self.ablation != {
            "name": "attention_gate_only",
            "changed_component": "skip_connection_attention_gate",
            "baseline_gate": False,
            "treatment_gate": True,
        }:
            raise ValueError("The only allowed ablation changes the Attention Gate.")
        if set(self.allowed_condition_difference_paths) != ALLOWED_DIFFERENCES:
            raise ValueError("Condition differences may only be architecture, gate, and run_id.")
        if (
            self.model_selection.get("selection_subset") != "validation"
            or self.model_selection.get("threshold_search_subset") != "validation"
            or self.model_selection.get("threshold_metric")
            != "patient_macro_wt_dice_after_3d_reconstruction"
            or self.model_selection.get("checkpoint_metric")
            != "validation_patient_macro_wt_dice_at_0.50"
            or self.model_selection.get("sensitivity_threshold") != 0.50
        ):
            raise ValueError(
                "Model and threshold selection must use the preregistered validation protocol."
            )
        expected = [round(0.30 + index * 0.05, 2) for index in range(9)]
        if self.model_selection.get("candidate_thresholds") != expected:
            raise ValueError("Validation threshold search is fixed to 0.30–0.70 in 0.05 steps.")
        if self.model_selection.get("checkpoint_threshold") != 0.50:
            raise ValueError(
                "Per-epoch checkpoint selection uses the preregistered 0.50 threshold."
            )
        if self.model_selection.get("tie_break") != [
            "highest_patient_macro_dice",
            "closest_threshold_to_0.50",
            "lowest_threshold",
        ]:
            raise ValueError("Validation threshold tie-break order is preregistered.")
        wilcoxon_protocol = self.statistics.get("wilcoxon", {})
        if (
            wilcoxon_protocol.get("alternative") != "two-sided"
            or wilcoxon_protocol.get("zero_difference_method") != "wilcox"
            or not wilcoxon_protocol.get("zero_differences_excluded_and_reported")
        ):
            raise ValueError(
                "The preregistered Wilcoxon test and zero-difference rule cannot change."
            )
        bootstrap = self.statistics.get("patient_pair_bootstrap", {})
        if (
            bootstrap.get("resamples") != 10000
            or bootstrap.get("seed") != 20261126
            or bootstrap.get("confidence_level") != 0.95
            or bootstrap.get("statistic") != "mean_paired_patient_dice_difference"
            or bootstrap.get("resampling_unit") != "patient_pair"
            or bootstrap.get("interval") != "percentile"
        ):
            raise ValueError("Bootstrap repetitions and seed are preregistered.")
        if (
            self.representative_cases.get("tie_break") != "patient_id_ascending"
            or self.representative_cases.get("visualization_seed") != 17
            or self.representative_cases.get("include_empty_ground_truth_patients") is not True
            or self.representative_cases.get("select_from")
            != "complete_research_test_patient_cohort"
        ):
            raise ValueError(
                "Representative cases must follow the preregistered cohort and tie rule."
            )
        return self


class AblationCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    architecture: Literal["UNet", "AttentionUNet"]
    attention_gate: bool
    input_mode: Literal["2d", "2p5d"]
    context_slices: int = Field(ge=1, le=9)
    slice_fusion: Literal["stack", "center_attention"]
    boundary_head: bool
    deep_supervision: bool
    model_version: str
    run_id_prefix: str = Field(pattern=r"^[a-z][a-z0-9-]{0,40}$")

    @model_validator(mode="after")
    def validate_condition(self) -> "AblationCondition":
        if self.context_slices % 2 != 1:
            raise ValueError("Ablation context size must be odd.")
        if self.attention_gate != (self.architecture == "AttentionUNet"):
            raise ValueError("The gate flag must match the declared architecture.")
        if self.input_mode == "2d" and self.slice_fusion != "stack":
            raise ValueError("The 2D conditions use stack fusion.")
        if self.deep_supervision and not self.boundary_head:
            raise ValueError("Deep supervision is paired with the boundary head in A3.")
        return self


class AblationMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matrix_id: str
    matrix_version: Literal[1]
    base_protocol_id: str
    conditions: dict[str, AblationCondition]
    allowed_condition_difference_paths: list[str]
    pairwise_difference_paths: dict[str, list[str]]
    disclaimer: str

    @model_validator(mode="after")
    def validate_frozen_matrix(self) -> "AblationMatrix":
        if set(self.conditions) != {"A0", "A1", "A2", "A3"}:
            raise ValueError("The ablation matrix must declare exactly A0 through A3.")
        if self.disclaimer != DISCLAIMER:
            raise ValueError("The research disclaimer must remain attached to the ablation matrix.")
        expected = {
            "A0": ("UNet", False, "2d", "stack", False, False),
            "A1": ("AttentionUNet", True, "2d", "stack", False, False),
            "A2": ("AttentionUNet", True, "2p5d", "center_attention", False, False),
            "A3": ("AttentionUNet", True, "2p5d", "center_attention", True, True),
        }
        for name, condition in self.conditions.items():
            observed = (
                condition.architecture,
                condition.attention_gate,
                condition.input_mode,
                condition.slice_fusion,
                condition.boundary_head,
                condition.deep_supervision,
            )
            if observed != expected[name] or condition.context_slices != 3:
                raise ValueError(f"{name} differs from its preregistered ablation definition.")
        required_pairs = {
            "A0_A1": {
                "condition_id",
                "model.architecture",
                "model.attention_gate",
                "model.model_version",
                "run_id",
            },
            "A1_A2": {
                "condition_id",
                "input_mode",
                "slice_fusion",
                "model.model_version",
                "run_id",
            },
            "A2_A3": {
                "condition_id",
                "boundary_head",
                "deep_supervision",
                "model.model_version",
                "run_id",
            },
        }
        observed_pairs = {key: set(paths) for key, paths in self.pairwise_difference_paths.items()}
        if observed_pairs != required_pairs:
            raise ValueError("Pairwise ablation differences must match the fixed A0-A3 matrix.")
        allowed = set().union(*required_pairs.values())
        if set(self.allowed_condition_difference_paths) != allowed:
            raise ValueError("Only declared architecture and ablation fields may differ.")
        return self


def load_ablation_matrix(path: Path = ABLATION_MATRIX_PATH) -> AblationMatrix:
    return AblationMatrix.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def ablation_matrix_sha256(path: Path = ABLATION_MATRIX_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_ablation_condition(
    config: TrainingConfig, matrix: AblationMatrix, condition_id: str
) -> TrainingConfig:
    if condition_id not in matrix.conditions:
        raise ValueError("Ablation condition is not preregistered.")
    condition = matrix.conditions[condition_id]
    values = config.model_dump(mode="json")
    values.update(
        condition_id=condition_id,
        input_mode=condition.input_mode,
        context_slices=condition.context_slices,
        slice_fusion=condition.slice_fusion,
        boundary_head=condition.boundary_head,
        deep_supervision=condition.deep_supervision,
    )
    return TrainingConfig.model_validate(values)


def condition_metadata(
    protocol: ExperimentProtocol, config: TrainingConfig, architecture: str
) -> tuple[str, str, str | None]:
    if config.condition_id == "baseline":
        name, condition = condition_for_architecture(protocol, architecture)
        return name, condition.model_version, None
    matrix = load_ablation_matrix()
    condition = matrix.conditions.get(config.condition_id)
    if condition is None or condition.architecture != architecture:
        raise ValueError("Checkpoint model does not match the selected ablation condition.")
    if (
        apply_ablation_condition(config, matrix, config.condition_id).model_dump()
        != config.model_dump()
    ):
        raise ValueError("Training config differs from the frozen ablation condition.")
    return config.condition_id, condition.model_version, ablation_matrix_sha256()


def build_ablation_run_config(
    config: TrainingConfig, matrix: AblationMatrix, condition_id: str, seed: int
) -> dict[str, Any]:
    if condition_id not in matrix.conditions or seed not in config.experiment_seeds:
        raise ValueError("Ablation condition and seed must belong to the registered protocol.")
    condition = matrix.conditions[condition_id]
    result = config.model_dump(mode="json")
    result["experiment_seeds"] = [seed]
    result["condition_id"] = condition_id
    result["input_mode"] = condition.input_mode
    result["context_slices"] = condition.context_slices
    result["slice_fusion"] = condition.slice_fusion
    result["boundary_head"] = condition.boundary_head
    result["deep_supervision"] = condition.deep_supervision
    result["model"] = {
        "architecture": condition.architecture,
        "attention_gate": condition.attention_gate,
        "model_version": condition.model_version,
    }
    result["seed"] = seed
    result["run_id"] = f"{condition.run_id_prefix}-seed-{seed}"
    result["ablation_matrix_id"] = matrix.matrix_id
    return result


def assert_ablation_matrix_differences(
    config: TrainingConfig, matrix: AblationMatrix, seed: int
) -> list[dict[str, Any]]:
    names = ("A0", "A1", "A2", "A3")
    rows = []
    for left_name, right_name in zip(names, names[1:], strict=False):
        left = build_ablation_run_config(config, matrix, left_name, seed)
        right = build_ablation_run_config(config, matrix, right_name, seed)
        differences = [
            {"path": path, "left": left_value, "right": right_value}
            for path, left_value, right_value in _flattened_differences(left, right)
        ]
        pair_name = f"{left_name}_{right_name}"
        observed = {difference["path"] for difference in differences}
        if observed != set(matrix.pairwise_difference_paths[pair_name]):
            raise ValueError(
                f"Unexpected configuration differences for {pair_name}: {sorted(observed)}"
            )
        if not observed <= set(matrix.allowed_condition_difference_paths):
            raise ValueError(f"Undeclared configuration difference for {pair_name}.")
        rows.extend(differences)
    return rows


def _flattened_differences(
    left: dict[str, Any], right: dict[str, Any], prefix: str = ""
) -> list[tuple[str, Any, Any]]:
    paths = []
    for key in sorted(left.keys() | right.keys()):
        path = f"{prefix}.{key}" if prefix else key
        left_value, right_value = left.get(key), right.get(key)
        if isinstance(left_value, dict) and isinstance(right_value, dict):
            paths.extend(_flattened_differences(left_value, right_value, path))
        elif left_value != right_value:
            paths.append((path, left_value, right_value))
    return paths


def load_experiment_protocol(path: Path = PROTOCOL_PATH) -> ExperimentProtocol:
    return ExperimentProtocol.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def protocol_sha256(path: Path = PROTOCOL_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def condition_for_architecture(
    protocol: ExperimentProtocol, architecture: str
) -> tuple[str, ModelCondition]:
    matches = [
        (name, condition)
        for name, condition in protocol.conditions.items()
        if condition.architecture == architecture
    ]
    if len(matches) != 1:
        raise ValueError(
            "Every configured architecture must resolve to one preregistered condition."
        )
    return matches[0]


def validate_training_config(protocol: ExperimentProtocol, config: TrainingConfig) -> None:
    expected = {
        "dataset": protocol.dataset,
        "modality": protocol.modality,
        "task": protocol.task,
        "preprocessing_version": protocol.preprocessing_version,
        "split_seed": protocol.split["seed"],
        "input_size": protocol.shared_training["input_size"],
        "channels": protocol.shared_training["channels"],
        "foreground_labels": protocol.shared_training["foreground_labels"],
        "loss": protocol.shared_training["loss"],
        "bce_weight": protocol.shared_training["bce_weight"],
        "dice_smoothing": protocol.shared_training["dice_smoothing"],
        "optimizer": protocol.shared_training["optimizer"],
        "learning_rate": protocol.shared_training["learning_rate"],
        "batch_size": protocol.shared_training["batch_size"],
        "max_epochs": protocol.shared_training["max_epochs"],
        "early_stopping_patience": protocol.shared_training["early_stopping_patience"],
        "early_stopping_min_delta": protocol.shared_training["early_stopping_min_delta"],
        "checkpoint_metric": "validation_dice",
        "threshold": protocol.model_selection["checkpoint_threshold"],
        "train_empty_fraction": protocol.shared_training["train_empty_fraction"],
        "augmentation": {"train": True, "validation": False, "test": False},
        "horizontal_flip_probability": protocol.shared_training["horizontal_flip_probability"],
        "vertical_flip_probability": protocol.shared_training["vertical_flip_probability"],
        "rotate_90": protocol.shared_training["rotate_90"],
        "num_workers": protocol.shared_training["num_workers"],
        "cpu_threads": protocol.shared_training["cpu_threads"],
        "experiment_seeds": protocol.seeds,
        "validation_thresholds": protocol.model_selection["candidate_thresholds"],
        "threshold_source": "validation_only",
        "execution_mode": "research",
        "device": protocol.shared_training["device"],
    }
    actual = config.model_dump()
    differences = {
        key: (actual.get(key), value) for key, value in expected.items() if actual.get(key) != value
    }
    if differences:
        raise ValueError(
            f"Training config violates the preregistered experiment protocol: {differences}"
        )
    if (config.train_patients, config.validation_patients, config.test_patients) != tuple(
        protocol.split["counts"]
    ):
        raise ValueError("Training config patient split sizes differ from the preregistration.")


def select_validation_threshold(
    scores: dict[float, float], protocol: ExperimentProtocol, mode: Literal["search", "fixed_050"]
) -> float:
    if mode == "fixed_050":
        threshold = float(protocol.model_selection["sensitivity_threshold"])
        if threshold not in scores:
            raise ValueError(
                "Fixed 0.50 sensitivity score was not evaluated on validation patients."
            )
        return threshold
    candidates = protocol.model_selection["candidate_thresholds"]
    if set(scores) != set(candidates):
        raise ValueError(
            "Every preregistered validation threshold must have one finite patient-macro score."
        )
    if any(
        not isinstance(value, (int, float)) or not math.isfinite(value) for value in scores.values()
    ):
        raise ValueError("Validation threshold scores must be finite.")
    center = float(protocol.model_selection["sensitivity_threshold"])
    return max(
        scores, key=lambda threshold: (scores[threshold], -abs(threshold - center), -threshold)
    )


def build_condition_run_config(
    protocol: ExperimentProtocol, base: dict[str, Any], condition_name: str, seed: int
) -> dict[str, Any]:
    if condition_name not in protocol.conditions or seed not in protocol.seeds:
        raise ValueError("Condition and seed must be registered in the protocol.")
    condition = protocol.conditions[condition_name]
    result = json.loads(json.dumps(base))
    result["experiment_seeds"] = [seed]
    result["model"] = {
        "architecture": condition.architecture,
        "attention_gate": condition.attention_gate,
    }
    result["seed"] = seed
    result["run_id"] = f"{condition.run_id_prefix}-seed-{seed}"
    result["protocol_id"] = protocol.protocol_id
    return result


def flatten_config(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            flattened.update(flatten_config(child, path))
        else:
            flattened[path] = child
    return flattened


def assert_only_declared_condition_differences(
    left: dict[str, Any], right: dict[str, Any], protocol: ExperimentProtocol
) -> list[dict[str, Any]]:
    left_flat, right_flat = flatten_config(left), flatten_config(right)
    if left_flat.keys() != right_flat.keys():
        missing = sorted(left_flat.keys() ^ right_flat.keys())
        raise ValueError(f"Condition configurations have different fields: {missing}")
    differences = [
        {"path": path, "left": left_flat[path], "right": right_flat[path]}
        for path in sorted(left_flat)
        if left_flat[path] != right_flat[path]
    ]
    unexpected = [
        difference
        for difference in differences
        if difference["path"] not in protocol.allowed_condition_difference_paths
    ]
    if unexpected:
        raise ValueError(f"Unregistered experimental control differences: {unexpected}")
    if {difference["path"] for difference in differences} != ALLOWED_DIFFERENCES:
        raise ValueError(
            "Each paired comparison must differ only in its declared model and run identity."
        )
    return differences
