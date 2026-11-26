from pathlib import Path

import pytest
from training.experiment_protocol import load_experiment_protocol
from training.protocol import (
    TrainingConfig,
    load_config,
    read_hashed_json,
    sha256_file,
    write_hashed_json,
)
from training.run_io import config_hash, protocol_sha256, verify_freeze


def make_freeze_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    template = load_config(Path("ml/configs/smoke.yaml"))
    split_path = tmp_path / "split.json"
    cache_path = tmp_path / "cache.json"
    split_path.write_text("synthetic split fixture", encoding="utf-8")
    cache_path.write_text("synthetic cache fixture", encoding="utf-8")
    config = TrainingConfig.model_validate(
        {
            **template.model_dump(),
            "split_manifest": str(split_path),
            "cache_index": str(cache_path),
            "experiment_protocol_path": str(Path("ml/configs/experiment_protocol.yaml").resolve()),
        }
    )
    protocol = load_experiment_protocol(Path(config.experiment_protocol_path))
    condition = protocol.conditions["UNet"]
    run_id = f"{condition.run_id_prefix}-seed-17"
    checkpoint_path = tmp_path / "best.ckpt"
    checkpoint_path.write_bytes(b"synthetic checkpoint bytes")
    checkpoint = {
        "run_id": run_id,
        "architecture": condition.architecture,
        "condition_name": "UNet",
        "model_version": condition.model_version,
        "seed": 17,
        "git_commit": "297d656925737247db922e293e67f4f1733a3d9f",
        "model_weight_sha256": "a" * 64,
    }
    monkeypatch.setattr("training.run_io.load_checkpoint", lambda *_: checkpoint)
    report_path = tmp_path / "validation.json"
    report = {
        "subset": "validation",
        "data_kind": "synthetic",
        "synthetic_smoke_measurements": {
            "patients": {
                "p1": {"dice": 0.6},
                "p2": {"dice": 0.6},
                "p3": {"dice": 0.6},
            }
        },
        "validation_threshold_search": [
            {"threshold": threshold, "validation_patient_dice": 0.6}
            for threshold in protocol.model_selection["candidate_thresholds"]
        ],
        "threshold": 0.5,
        "threshold_selection_mode": "search",
        "run_id": run_id,
        "git_commit": checkpoint["git_commit"],
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "model_weight_sha256": checkpoint["model_weight_sha256"],
        "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
        "evaluation_protocol": protocol.protocol_id,
    }
    write_hashed_json(report_path, report)
    freeze_path = tmp_path / "freeze.json"
    freeze = {
        "kind": "validation_protocol_freeze",
        **checkpoint,
        "split_sha256": sha256_file(split_path),
        "config_hash": config_hash(config),
        "protocol_sha256": protocol_sha256(Path(config.experiment_protocol_path)),
        "cache_sha256": sha256_file(cache_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "preprocessing_version": config.preprocessing_version,
        "evaluation_protocol": protocol.protocol_id,
        "threshold": 0.5,
        "training_threshold": config.threshold,
        "threshold_selection_mode": "search",
        "threshold_source": "validation_only",
        "data_kind": "synthetic",
        "validation_report": report_path.name,
        "validation_report_sha256": sha256_file(report_path),
    }
    write_hashed_json(freeze_path, freeze)
    return config, checkpoint_path, freeze_path


def test_complete_freeze_accepts_matching_checkpoint_and_validation_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config, checkpoint, freeze = make_freeze_fixture(tmp_path, monkeypatch)
    actual = verify_freeze(freeze, checkpoint, config)
    assert actual["threshold_source"] == "validation_only"
    assert actual["threshold_selection_mode"] == "search"
    assert actual["run_id"] == "unet-seed-17"


@pytest.mark.parametrize(
    "field,value",
    [
        ("threshold_source", "test_set"),
        ("git_commit", "NotRun"),
        ("model_weight_sha256", "b" * 64),
        ("evaluation_protocol", "unregistered-protocol"),
    ],
)
def test_freeze_rejects_external_threshold_or_mismatched_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
):
    from training.protocol import read_hashed_json

    config, checkpoint, freeze_path = make_freeze_fixture(tmp_path, monkeypatch)
    freeze = read_hashed_json(freeze_path)
    freeze[field] = value
    freeze_path.unlink()
    freeze_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(freeze_path, freeze)
    with pytest.raises(ValueError):
        verify_freeze(freeze_path, checkpoint, config)


def test_freeze_rejects_incomplete_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config, checkpoint, freeze_path = make_freeze_fixture(tmp_path, monkeypatch)
    freeze = read_hashed_json(freeze_path)
    del freeze["model_weight_sha256"]
    freeze_path.unlink()
    freeze_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(freeze_path, freeze)
    with pytest.raises(ValueError, match="incomplete"):
        verify_freeze(freeze_path, checkpoint, config)


def test_freeze_rejects_validation_report_relabelled_as_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config, checkpoint, freeze_path = make_freeze_fixture(tmp_path, monkeypatch)
    report_path = tmp_path / "validation.json"
    report = read_hashed_json(report_path)
    report["subset"] = "test"
    report_path.unlink()
    report_path.with_suffix(".json.sha256").unlink()
    digest = write_hashed_json(report_path, report)
    freeze = read_hashed_json(freeze_path)
    freeze["validation_report_sha256"] = digest
    freeze_path.unlink()
    freeze_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(freeze_path, freeze)
    with pytest.raises(ValueError, match="Only actual validation"):
        verify_freeze(freeze_path, checkpoint, config)


def test_freeze_rejects_threshold_not_selected_by_validation_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config, checkpoint, freeze_path = make_freeze_fixture(tmp_path, monkeypatch)
    report_path = tmp_path / "validation.json"
    report = read_hashed_json(report_path)
    report["validation_threshold_search"] = [
        {"threshold": row["threshold"], "validation_patient_dice": float(row["threshold"])}
        for row in report["validation_threshold_search"]
    ]
    report_path.unlink()
    report_path.with_suffix(".json.sha256").unlink()
    digest = write_hashed_json(report_path, report)
    freeze = read_hashed_json(freeze_path)
    freeze["validation_report_sha256"] = digest
    freeze_path.unlink()
    freeze_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(freeze_path, freeze)
    with pytest.raises(ValueError, match="not the selected validation-only threshold"):
        verify_freeze(freeze_path, checkpoint, config)


def test_fixed_050_sensitivity_freeze_accepts_only_the_validation_050_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config, checkpoint, freeze_path = make_freeze_fixture(tmp_path, monkeypatch)
    report_path = tmp_path / "validation.json"
    report = read_hashed_json(report_path)
    report["validation_threshold_search"] = [{"threshold": 0.5, "validation_patient_dice": 0.6}]
    report["threshold_selection_mode"] = "fixed_050"
    report_path.unlink()
    report_path.with_suffix(".json.sha256").unlink()
    digest = write_hashed_json(report_path, report)
    freeze = read_hashed_json(freeze_path)
    freeze["validation_report_sha256"] = digest
    freeze["threshold_selection_mode"] = "fixed_050"
    freeze_path.unlink()
    freeze_path.with_suffix(".json.sha256").unlink()
    write_hashed_json(freeze_path, freeze)

    assert verify_freeze(freeze_path, checkpoint, config)["threshold_selection_mode"] == "fixed_050"
