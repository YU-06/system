import argparse
import json
from pathlib import Path

from training import DISCLAIMER
from training.protocol import load_config, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-config")
    validate.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))

    scan = commands.add_parser("scan")
    scan.add_argument("--root", type=Path, required=True)
    scan.add_argument("--output", type=Path, default=Path("artifacts/dataset_scan.json"))
    scan.add_argument("--synthetic", action="store_true")

    split = commands.add_parser("split")
    split.add_argument("--scan", type=Path, required=True)
    split.add_argument("--output", type=Path, default=Path("artifacts/split_manifest.json"))
    split.add_argument("--seed", type=int, default=42)
    split.add_argument("--synthetic-counts", nargs=3, type=int)

    preprocess = commands.add_parser("preprocess")
    preprocess.add_argument("--root", type=Path, required=True)
    preprocess.add_argument("--split", type=Path, required=True)
    preprocess.add_argument("--output", type=Path, default=Path("artifacts/preprocessed"))

    train = commands.add_parser("train")
    train.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    train.add_argument("--architecture", choices=["UNet", "AttentionUNet"])
    train.add_argument("--seed", type=int)
    train.add_argument("--resume", type=Path)
    train.add_argument("--stop-after-epochs", type=int)

    evaluate = commands.add_parser("validate")
    evaluate.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    evaluate.add_argument("--checkpoint", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--freeze", type=Path)

    test = commands.add_parser("test")
    test.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    test.add_argument("--checkpoint", type=Path, required=True)
    test.add_argument("--freeze", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)

    smoke = commands.add_parser("smoke")
    smoke.add_argument("--config", type=Path, default=Path("ml/configs/smoke.yaml"))
    smoke.add_argument("--output", type=Path, default=Path("artifacts/smoke/current"))

    arguments = parser.parse_args()
    if arguments.command == "validate-config":
        config = load_config(arguments.config)
        print(
            json.dumps(
                {"status": "valid", "resultStatus": config.result_status, "disclaimer": DISCLAIMER}
            )
        )
    elif arguments.command == "scan":
        from training.protocol import write_hashed_json
        from training.scan_dataset import scan_dataset

        scan = scan_dataset(arguments.root, synthetic=arguments.synthetic)
        digest = write_hashed_json(arguments.output, scan.model_dump(mode="json"))
        print(
            json.dumps({"patients": len(scan.patients), "sha256": digest, "disclaimer": DISCLAIMER})
        )
    elif arguments.command == "split":
        from training.create_split import create_split

        counts = tuple(arguments.synthetic_counts) if arguments.synthetic_counts else None
        manifest = create_split(
            arguments.scan, arguments.output, seed=arguments.seed, synthetic_counts=counts
        )
        print(
            json.dumps(
                {
                    "splitSha256": sha256_file(arguments.output),
                    "counts": [len(manifest.train), len(manifest.validation), len(manifest.test)],
                    "disclaimer": DISCLAIMER,
                }
            )
        )
    elif arguments.command == "preprocess":
        from training.preprocess import preprocess_dataset

        cache = preprocess_dataset(arguments.root, arguments.split, arguments.output)
        print(
            json.dumps(
                {
                    "patients": len(cache.patients),
                    "slices": len(cache.slices),
                    "disclaimer": DISCLAIMER,
                }
            )
        )
    elif arguments.command == "train":
        from training.train import run_training

        config = load_config(arguments.config)
        architectures = [arguments.architecture] if arguments.architecture else config.architectures
        seeds = [arguments.seed] if arguments.seed is not None else config.experiment_seeds
        results = [
            run_training(config, architecture, seed, arguments.resume, arguments.stop_after_epochs)
            for architecture in architectures
            for seed in seeds
        ]
        print(
            json.dumps(
                {
                    "artifacts": [str(path) for path in results],
                    "test_metrics": "NotRun",
                    "disclaimer": DISCLAIMER,
                }
            )
        )
    elif arguments.command == "validate":
        from training.validate import run_validation

        config = load_config(arguments.config)
        run_validation(config, arguments.checkpoint, arguments.output, arguments.freeze)
        print(
            json.dumps(
                {
                    "status": "ValidationCompleted",
                    "test_metrics": "NotRun",
                    "disclaimer": DISCLAIMER,
                }
            )
        )
    elif arguments.command == "test":
        from training.test import run_test

        config = load_config(arguments.config)
        run_test(config, arguments.checkpoint, arguments.freeze, arguments.output)
        print(json.dumps({"status": "TestCompleted", "disclaimer": DISCLAIMER}))
    elif arguments.command == "smoke":
        from training.smoke import run_smoke

        report = run_smoke(arguments.output, arguments.config)
        print(json.dumps(report))


if __name__ == "__main__":
    main()
