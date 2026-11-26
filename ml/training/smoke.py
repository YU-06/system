import argparse
from datetime import UTC, datetime
from pathlib import Path

import nibabel as nib
import numpy as np
import yaml

from training import DISCLAIMER
from training.create_split import create_split
from training.preprocess import preprocess_dataset
from training.protocol import TrainingConfig, load_config, write_hashed_json
from training.scan_dataset import scan_dataset
from training.test import run_test
from training.train import run_training
from training.validate import run_validation


def run_smoke(output: Path, template: Path = Path("ml/configs/smoke.yaml")) -> dict:
    if output.exists():
        raise FileExistsError("Smoke evidence must be generated into a new directory.")
    output.mkdir(parents=True)
    config = load_config(template)
    if config.execution_mode != "smoke":
        raise ValueError("Smoke generation requires the explicitly synthetic configuration.")
    root = output / "data"
    count = config.train_patients + config.validation_patients + config.test_patients
    generator = np.random.default_rng(config.split_seed)
    for index in range(count):
        identifier = f"Synthetic_{index:03}"
        directory = root / identifier
        directory.mkdir(parents=True)
        volume = generator.normal(100, 10, (16, 16, 3)).astype(np.float32)
        volume[:2] = 0
        labels = np.zeros(volume.shape, dtype=np.uint8)
        labels[6:10, 6:10, 1] = (1, 2, 4)[index % 3]
        nib.save(nib.Nifti1Image(volume, np.eye(4)), directory / f"{identifier}_flair.nii.gz")
        nib.save(nib.Nifti1Image(labels, np.eye(4)), directory / f"{identifier}_seg.nii.gz")
    scan = scan_dataset(root, synthetic=True)
    scan_path, split_path = output / "dataset_scan.json", output / "split_manifest.json"
    write_hashed_json(scan_path, scan.model_dump(mode="json"))
    create_split(
        scan_path,
        split_path,
        seed=config.split_seed,
        synthetic_counts=(config.train_patients, config.validation_patients, config.test_patients),
    )
    preprocess_dataset(root, split_path, output / "preprocessed")
    config = TrainingConfig.model_validate(
        {
            **config.model_dump(),
            "dataset_root": str(root),
            "split_manifest": str(split_path),
            "cache_index": str(output / "preprocessed" / "index.json"),
            "output_directory": str(output / "runs"),
        }
    )
    (output / "config.yaml").write_text(
        yaml.safe_dump(config.model_dump(), sort_keys=True), encoding="utf-8"
    )
    models: dict[str, dict] = {}
    for architecture in config.architectures:
        directory = run_training(
            config, architecture, config.experiment_seeds[0], stop_after_epoch=1
        )
        run_training(
            config, architecture, config.experiment_seeds[0], resume=directory / "last.ckpt"
        )
        freeze_path = directory / "protocol_frozen.json"
        validation = run_validation(
            config, directory / "best.ckpt", directory / "validation.json", freeze_path
        )
        testing = run_test(config, directory / "best.ckpt", freeze_path, directory / "test")
        models[architecture] = {
            "status": "SmokePassed",
            "resumed_to_epoch": config.max_epochs,
            "complete_validation_patients": len(validation.patient_metrics),
            "complete_test_patients": len(testing.patient_metrics),
            "artifacts": str(directory),
        }
    report = {
        "status": "SmokePassed",
        "data_kind": "synthetic",
        "models": models,
        "research_metrics": {
            "dice": "NotRun",
            "iou": "NotRun",
            "precision": "NotRun",
            "recall": "NotRun",
        },
        "full_brats_training": "NotRun",
        "disclaimer": DISCLAIMER,
    }
    write_hashed_json(output / "smoke_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / f"smoke_{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
    )
    parser.add_argument("--config", type=Path, default=Path("ml/configs/smoke.yaml"))
    arguments = parser.parse_args()
    report = run_smoke(arguments.output, arguments.config)
    print(
        f"{report['status']}: scan/split/preprocess, both models, checkpoint resume, "
        "validation freeze, full patient reconstruction."
    )
    evidence = arguments.output / "smoke_report.json"
    print(f"Evidence: {evidence}; all actual BraTS research metrics=NotRun.")


if __name__ == "__main__":
    main()
