import argparse
import io
from pathlib import Path

import torch

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.experiment_protocol import condition_for_architecture, load_experiment_protocol
from training.protocol import TrainingConfig, load_config, sha256_file, write_hashed_json
from training.run_io import checkpoint_model, config_hash, verify_freeze
from training.validate import EvaluationResult, evaluate_model, evaluation_report


def run_test(
    config: TrainingConfig, checkpoint_path: Path, freeze_path: Path, output: Path
) -> EvaluationResult:
    freeze = verify_freeze(freeze_path, checkpoint_path, config)
    model, checkpoint = checkpoint_model(checkpoint_path, config)
    protocol = load_experiment_protocol(Path(config.experiment_protocol_path))
    condition_name, condition = condition_for_architecture(protocol, checkpoint["architecture"])
    if (
        freeze.get("architecture") != checkpoint["architecture"]
        or freeze.get("seed") != checkpoint["seed"]
        or freeze.get("model_version") != condition.model_version
        or freeze.get("condition_name") != condition_name
        or freeze.get("run_id") != checkpoint.get("run_id")
        or freeze.get("evaluation_protocol") != protocol.protocol_id
        or freeze.get("preprocessing_version") != config.preprocessing_version
    ):
        raise ValueError(
            "Frozen model, seed, condition or run identity does not match the selected checkpoint."
        )
    if output.exists():
        raise FileExistsError(
            "Test outputs must use a new directory; prior evidence was not overwritten."
        )
    dataset = Brats2DDataset(Path(config.cache_index), "test")
    output.mkdir(parents=True)
    selected_config = TrainingConfig.model_validate(
        {**config.model_dump(), "threshold": freeze["threshold"]}
    )
    result = evaluate_model(model, dataset, selected_config, output / "patient_masks")
    report = evaluation_report(result, selected_config, "test")
    weights = io.BytesIO()
    torch.save(model.state_dict(), weights)
    report.update(
        architecture=checkpoint["architecture"],
        condition_name=condition_name,
        model_version=condition.model_version,
        run_id=checkpoint["run_id"],
        seed=checkpoint["seed"],
        git_commit=freeze["git_commit"],
        model_weight_sha256=checkpoint["model_weight_sha256"],
        evaluation_protocol=protocol.protocol_id,
        protocol_sha256=freeze["protocol_sha256"],
        config_hash=config_hash(config),
        split_sha256=freeze["split_sha256"],
        cache_sha256=freeze["cache_sha256"],
        preprocessing_version=config.preprocessing_version,
        threshold_source=freeze["threshold_source"],
        threshold_selection_mode=freeze["threshold_selection_mode"],
        checkpoint_sha256=sha256_file(checkpoint_path),
        frozen_protocol_sha256=sha256_file(freeze_path),
        parameter_count=sum(parameter.numel() for parameter in model.parameters()),
        model_weights_bytes=weights.tell(),
        complete_test_patient_count=len(result.patient_metrics),
    )
    write_hashed_json(output / "test_metrics.json", report)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    result = run_test(config, arguments.checkpoint, arguments.freeze, arguments.output)
    print(
        f"Test processed all {len(result.patient_metrics)} frozen patients; "
        f"mode={config.execution_mode}"
    )


if __name__ == "__main__":
    main()
