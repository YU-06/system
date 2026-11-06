import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pytest
from training.metrics import binary_metrics
from training.preprocessing import (
    normalize_volume,
    prepare_axial_slice,
    resize_mask,
    whole_tumor_mask,
)
from training.protocol import create_patient_split, load_config, set_global_seed


def test_whole_tumor_mapping_and_nearest_mask_resize():
    labels = np.array([[0, 1], [2, 4]], dtype=np.float32)
    mask = whole_tumor_mask(labels)
    assert mask.tolist() == [[0, 1], [1, 1]]
    assert set(np.unique(resize_mask(mask)).tolist()) == {0, 1}
    with pytest.raises(ValueError):
        whole_tumor_mask(np.array([3], dtype=np.float32))


def test_normalization_uses_only_current_nonzero_volume():
    volume = np.array([[[0, 2], [4, 6]]], dtype=np.float32)
    normalized = normalize_volume(volume)
    assert normalized[0, 0, 0] == 0
    assert np.isclose(normalized[volume != 0].mean(), 0)
    assert np.isclose(normalized[volume != 0].std(), 1)
    assert prepare_axial_slice(volume, 0).shape == (256, 256)
    assert not normalize_volume(np.zeros((2, 2, 2), dtype=np.float32)).any()


def test_patient_split_is_disjoint_reproducible_and_hashed(tmp_path: Path):
    identifiers = [f"BraTS20_Training_{index:03}" for index in range(369)]
    output = tmp_path / "split_manifest.json"
    digest = create_patient_split(identifiers, output)
    manifest = json.loads(output.read_text())
    assert [len(manifest[name]) for name in ["train", "validation", "test"]] == [258, 74, 37]
    groups = [set(manifest[name]) for name in ["train", "validation", "test"]]
    assert not groups[0] & groups[1] and not groups[0] & groups[2] and not groups[1] & groups[2]
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    assert digest == create_patient_split(list(reversed(identifiers)), output)
    assert output.with_suffix(".json.sha256").read_text().strip() == digest
    with pytest.raises(ValueError):
        create_patient_split(identifiers[:-1], output)
    with pytest.raises(ValueError):
        create_patient_split(identifiers[:-1] + [identifiers[0]], output)


def test_metrics_include_empty_and_disjoint_cases():
    empty = np.zeros((2, 2), dtype=np.uint8)
    full = np.ones((2, 2), dtype=np.uint8)
    assert binary_metrics(empty, empty).dice == 1
    assert binary_metrics(full, full).iou == 1
    assert binary_metrics(full, empty).dice == 0
    assert binary_metrics(full, empty).precision == 0
    with pytest.raises(ValueError):
        binary_metrics(empty, np.array([0], dtype=np.uint8))


def test_baseline_protocol_has_no_test_leakage_or_fabricated_results():
    config = load_config(Path("ml/configs/baseline.yaml"))
    assert config.experiment_seeds == [42, 2024, 3407]
    assert config.threshold_source == "validation_only"
    assert config.test_execution == "locked_until_protocol_frozen"
    assert config.result_status == "NotRun"
    assert config.augmentation == {"train": True, "validation": False, "test": False}


def test_python_and_numpy_seeds_are_reproducible():
    set_global_seed(42, include_torch=False)
    first = (random.random(), np.random.rand())
    set_global_seed(42, include_torch=False)
    assert first == (random.random(), np.random.rand())


def test_missing_optional_torch_dependency_is_reported(monkeypatch: pytest.MonkeyPatch):
    def missing_torch(name: str) -> None:
        raise ImportError("Optional training dependency is absent.")

    monkeypatch.setattr("training.protocol.import_module", missing_torch)
    with pytest.raises(RuntimeError, match="training extra"):
        set_global_seed(42)
