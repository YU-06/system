from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from training.create_split import create_split, load_split
from training.preprocess import load_cache, preprocess_dataset
from training.protocol import read_hashed_json, write_hashed_json
from training.scan_dataset import scan_dataset


def make_patients(root: Path, count: int = 4) -> None:
    for index in range(count):
        identifier = f"Synthetic_{index:03}"
        directory = root / identifier
        directory.mkdir(parents=True)
        image = np.arange(16 * 16 * 3, dtype=np.float32).reshape(16, 16, 3)
        labels = np.zeros_like(image, dtype=np.uint8)
        labels[6:10, 6:10, 1] = (1, 2, 4)[index % 3]
        nib.save(nib.Nifti1Image(image, np.eye(4)), directory / f"{identifier}_flair.nii.gz")
        nib.save(nib.Nifti1Image(labels, np.eye(4)), directory / f"{identifier}_seg.nii.gz")


def test_scan_split_integrity_and_patient_membership(tmp_path: Path):
    root = tmp_path / "data"
    make_patients(root)
    scan = scan_dataset(root, synthetic=True)
    assert len(scan.patients) == 4
    scan_path = tmp_path / "scan.json"
    write_hashed_json(scan_path, scan.model_dump(mode="json"))
    split_path = tmp_path / "split_manifest.json"
    manifest = create_split(scan_path, split_path, synthetic_counts=(2, 1, 1))
    assert [len(manifest.train), len(manifest.validation), len(manifest.test)] == [2, 1, 1]
    assert not set(manifest.train) & set(manifest.validation)
    assert manifest == load_split(split_path)
    assert read_hashed_json(split_path)
    split_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        load_split(split_path)


@pytest.mark.parametrize("failure", ["missing", "labels", "geometry"])
def test_scan_never_silently_discards_invalid_patients(tmp_path: Path, failure: str):
    make_patients(tmp_path)
    path = tmp_path / "Synthetic_000" / "Synthetic_000_seg.nii.gz"
    if failure == "missing":
        path.unlink()
    elif failure == "labels":
        nib.save(nib.Nifti1Image(np.full((16, 16, 3), 3, dtype=np.uint8), np.eye(4)), path)
    else:
        affine = np.eye(4)
        affine[0, 3] = 1
        nib.save(nib.Nifti1Image(np.zeros((16, 16, 3), dtype=np.uint8), affine), path)
    with pytest.raises(ValueError, match="no cases were silently dropped"):
        scan_dataset(tmp_path, synthetic=True)


def test_research_counts_cannot_be_reduced_without_synthetic_marking(tmp_path: Path):
    make_patients(tmp_path / "data")
    scan = scan_dataset(tmp_path / "data")
    path = tmp_path / "scan.json"
    write_hashed_json(path, scan.model_dump(mode="json"))
    with pytest.raises(ValueError, match="synthetic"):
        create_split(path, tmp_path / "split.json", synthetic_counts=(2, 1, 1))


def prepare_cache(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    make_patients(root)
    scan = scan_dataset(root, synthetic=True)
    scan_path = tmp_path / "scan.json"
    write_hashed_json(scan_path, scan.model_dump(mode="json"))
    split_path = tmp_path / "split.json"
    create_split(scan_path, split_path, synthetic_counts=(2, 1, 1))
    preprocess_dataset(root, split_path, tmp_path / "cache")
    return tmp_path / "cache" / "index.json"


def test_preprocess_records_every_slice_and_matches_shared_inference(tmp_path: Path):
    from training.preprocessing import prepare_axial_slice

    index = prepare_cache(tmp_path)
    cache = load_cache(index)
    assert len(cache.patients) == 4 and len(cache.slices) == 12
    assert sum(record.has_lesion for record in cache.slices) == 4
    record = cache.slices[0]
    original = nib.load(tmp_path / "data" / record.patient_id / f"{record.patient_id}_flair.nii.gz")
    with np.load(index.parent / record.path, allow_pickle=False) as data:
        assert data["image"].shape == (256, 256)
        assert np.array_equal(
            data["image"],
            prepare_axial_slice(original.get_fdata(dtype=np.float32), record.slice_index),
        )
        assert set(np.unique(data["mask"])) <= {0, 1}


def test_dataset_sampling_does_not_delete_validation_or_test_slices(tmp_path: Path):
    from training.datasets.brats2d import Brats2DDataset
    from training.transforms import SynchronizedTransforms

    index = prepare_cache(tmp_path)
    training = Brats2DDataset(index, "train", empty_fraction=0.5)
    validation = Brats2DDataset(index, "validation")
    testing = Brats2DDataset(index, "test")
    assert len(training) == 4
    assert len(validation) == len(testing) == 3
    assert training[0]["image"].shape == (1, 256, 256)
    with pytest.raises(ValueError, match="every slice"):
        Brats2DDataset(index, "test", empty_fraction=0.5)
    with pytest.raises(ValueError, match="every slice"):
        Brats2DDataset(index, "validation", transform=SynchronizedTransforms())


def test_patient_reconstruction_restores_non_square_geometry_and_empty_metrics(tmp_path: Path):
    from training.reconstruct_volume import patient_metrics, reconstruct_volume, save_volume

    masks = {index: np.zeros((256, 256), dtype=np.uint8) for index in range(3)}
    original = np.zeros((12, 20, 3), dtype=np.uint8)
    volume, metrics = patient_metrics(masks, original)
    assert volume.shape == original.shape
    assert metrics.dice == metrics.iou == 1
    with pytest.raises(ValueError, match="every axial slice"):
        reconstruct_volume({0: masks[0]}, original.shape)
    affine = np.diag([1.5, 1.5, 2, 1])
    output = tmp_path / "reconstructed.nii.gz"
    save_volume(volume, affine, output)
    restored = nib.load(output)
    assert restored.shape == original.shape and np.allclose(restored.affine, affine)


def test_cache_manifest_rejects_missing_or_cross_split_slices(tmp_path: Path):
    from training.preprocess import CacheManifest

    index = prepare_cache(tmp_path)
    cache = load_cache(index)
    altered = cache.model_dump()
    altered["slices"] = altered["slices"][1:]
    with pytest.raises(ValueError, match="every axial slice"):
        CacheManifest.model_validate(altered)
    altered = cache.model_dump()
    altered["slices"][0]["subset"] = "test" if altered["slices"][0]["subset"] != "test" else "train"
    with pytest.raises(ValueError, match="cross dataset subsets"):
        CacheManifest.model_validate(altered)
