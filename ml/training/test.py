import argparse
import io
from pathlib import Path

import torch

from training import DISCLAIMER
from training.datasets.brats2d import Brats2DDataset
from training.protocol import TrainingConfig, load_config, sha256_file, write_hashed_json
from training.run_io import checkpoint_model, verify_freeze
from training.validate import EvaluationResult, evaluate_model, evaluation_report


def run_test(
    config: TrainingConfig, checkpoint_path: Path, freeze_path: Path, output: Path
) -> EvaluationResult:
    freeze = verify_freeze(freeze_path, checkpoint_path, config)
    model, checkpoint = checkpoint_model(checkpoint_path, config)
    if (
        freeze.get("architecture") != checkpoint["architecture"]
        or freeze.get("seed") != checkpoint["seed"]
    ):
        raise ValueError("Frozen architecture and seed do not match the selected model.")
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
        seed=checkpoint["seed"],
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
