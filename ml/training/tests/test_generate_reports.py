from pathlib import Path

import nibabel as nib
import numpy as np
from training.create_split import create_split
from training.generate_reports import generate_reports
from training.preprocess import preprocess_dataset
from training.protocol import write_hashed_json
from training.scan_dataset import scan_dataset


def make_synthetic_cache(root: Path, output: Path) -> tuple[Path, Path]:
    dataset_root = root / "synthetic_data"
    for index in range(4):
        identifier = f"Synthetic_{index:03}"
        patient_dir = dataset_root / identifier
        patient_dir.mkdir(parents=True)
        image = np.arange(16 * 16 * 3, dtype=np.float32).reshape(16, 16, 3)
        labels = np.zeros_like(image, dtype=np.uint8)
        labels[6:10, 6:10, 1] = 1
        nib.save(nib.Nifti1Image(image, np.eye(4)), patient_dir / f"{identifier}_flair.nii.gz")
        nib.save(nib.Nifti1Image(labels, np.eye(4)), patient_dir / f"{identifier}_seg.nii.gz")

    scan_path = root / "scan.json"
    write_hashed_json(scan_path, scan_dataset(dataset_root, synthetic=True).model_dump(mode="json"))
    split_path = root / "split.json"
    create_split(scan_path, split_path, synthetic_counts=(2, 1, 1))
    cache_path = root / "cache" / "index.json"
    preprocess_dataset(dataset_root, split_path, cache_path.parent)
    return split_path, cache_path


def test_synthetic_fixture_only_writes_not_run_templates_and_no_figures(tmp_path: Path):
    output = tmp_path / "reports"
    split, cache = make_synthetic_cache(tmp_path, output)

    manifest = generate_reports(tmp_path / "runs", split, cache, output)

    assert manifest["status"] == "NotRun"
    assert manifest["generated_figures"] == []
    assert any("Synthetic data" in reason for reason in manifest["not_run_checklist"])
    assert not list(output.glob("*.png"))
    assert (output / "report_manifest.json").is_file()
    assert (output / "report_manifest.json.sha256").is_file()


def test_missing_research_inputs_produce_only_not_run_checklist(tmp_path: Path):
    output = tmp_path / "reports"

    manifest = generate_reports(
        tmp_path / "runs", tmp_path / "missing-split.json", tmp_path / "missing-cache.json", output
    )

    assert manifest["status"] == "NotRun"
    assert manifest["not_run_checklist"]
    assert manifest["generated_figures"] == []
    assert not list(output.glob("*.csv"))
    assert not list(output.glob("*.png"))
