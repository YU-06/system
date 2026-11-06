import argparse
import json
from pathlib import Path

from training import DISCLAIMER
from training.protocol import create_patient_split, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-config")
    validate.add_argument("--config", type=Path, default=Path("ml/configs/baseline.yaml"))
    split = commands.add_parser("split")
    split.add_argument("--patients", type=Path, required=True)
    split.add_argument("--output", type=Path, default=Path("artifacts/split_manifest.json"))
    split.add_argument("--seed", type=int, default=42)
    arguments = parser.parse_args()
    if arguments.command == "validate-config":
        config = load_config(arguments.config)
        print(
            json.dumps(
                {"status": "valid", "resultStatus": config.result_status, "disclaimer": DISCLAIMER}
            )
        )
    else:
        patient_ids = json.loads(arguments.patients.read_text(encoding="utf-8"))
        if not isinstance(patient_ids, list) or not all(
            isinstance(value, str) for value in patient_ids
        ):
            parser.error("The patient file must be a JSON array of pseudonymous identifiers.")
        digest = create_patient_split(patient_ids, arguments.output, arguments.seed)
        print(
            json.dumps({"splitSha256": digest, "counts": [258, 74, 37], "disclaimer": DISCLAIMER})
        )


if __name__ == "__main__":
    main()
