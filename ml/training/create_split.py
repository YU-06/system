import argparse
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from training import DISCLAIMER, PREPROCESSING_VERSION
from training.protocol import read_hashed_json, sha256_file, write_hashed_json
from training.scan_dataset import DatasetScan, PatientFiles


class SplitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    dataset: Literal["BraTS 2020"] = "BraTS 2020"
    data_kind: Literal["research", "synthetic"]
    preprocessing_version: Literal["flair-v1"] = "flair-v1"
    split_unit: Literal["patient"] = "patient"
    seed: int
    scan_sha256: str
    train: list[str]
    validation: list[str]
    test: list[str]
    patients: dict[str, PatientFiles]
    disclaimer: str = DISCLAIMER

    @model_validator(mode="after")
    def validate_membership(self) -> "SplitManifest":
        identifiers = self.train + self.validation + self.test
        if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(self.patients):
            raise ValueError("Every patient must belong to exactly one subset.")
        if any(identifier != patient.patient_id for identifier, patient in self.patients.items()):
            raise ValueError("Patient metadata keys do not match their identifiers.")
        if not all((self.train, self.validation, self.test)):
            raise ValueError("All three patient subsets must be non-empty.")
        if self.data_kind == "research" and [
            len(self.train),
            len(self.validation),
            len(self.test),
        ] != [258, 74, 37]:
            raise ValueError("The research split must contain exactly 258/74/37 patients.")
        return self


def create_split(
    scan_path: Path,
    output: Path,
    *,
    seed: int = 42,
    synthetic_counts: tuple[int, int, int] | None = None,
) -> SplitManifest:
    scan = DatasetScan.model_validate(read_hashed_json(scan_path))
    counts = (258, 74, 37) if synthetic_counts is None else synthetic_counts
    if synthetic_counts is not None and scan.data_kind != "synthetic":
        raise ValueError("Reduced counts are permitted only for explicitly synthetic data.")
    if min(counts) < 1 or sum(counts) != len(scan.patients):
        raise ValueError("Patient counts do not match the requested split; research requires 369.")
    patients = {patient.patient_id: patient for patient in scan.patients}
    if len(patients) != len(scan.patients):
        raise ValueError("Duplicate patient identifiers are forbidden.")
    identifiers = sorted(patients)
    random.Random(seed).shuffle(identifiers)
    train_end, validation_end = counts[0], counts[0] + counts[1]
    manifest = SplitManifest(
        data_kind=scan.data_kind,
        seed=seed,
        scan_sha256=sha256_file(scan_path),
        train=identifiers[:train_end],
        validation=identifiers[train_end:validation_end],
        test=identifiers[validation_end:],
        patients=patients,
        preprocessing_version=PREPROCESSING_VERSION,
    )
    write_hashed_json(output, manifest.model_dump(mode="json"))
    return manifest


def load_split(path: Path) -> SplitManifest:
    return SplitManifest.model_validate(read_hashed_json(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/split_manifest.json"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--synthetic-counts", nargs=3, type=int)
    arguments = parser.parse_args()
    counts = tuple(arguments.synthetic_counts) if arguments.synthetic_counts else None
    manifest = create_split(
        arguments.scan, arguments.output, seed=arguments.seed, synthetic_counts=counts
    )
    counts = [len(manifest.train), len(manifest.validation), len(manifest.test)]
    print(f"Patient split {counts}; data_kind={manifest.data_kind}")


if __name__ == "__main__":
    main()
