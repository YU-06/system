from pathlib import Path

import pytest
import torch
from training.protocol import TrainingConfig, load_config
from training.run_io import load_checkpoint
from training.test import run_test
from training.tests.test_data_pipeline import prepare_cache
from training.train import EarlyStopping, run_training
from training.validate import run_validation


def smoke_config(tmp_path: Path) -> TrainingConfig:
    index = prepare_cache(tmp_path)
    original = load_config(Path("ml/configs/smoke.yaml"))
    return TrainingConfig.model_validate(
        {
            **original.model_dump(),
            "dataset_root": str(tmp_path / "data"),
            "split_manifest": str(tmp_path / "split.json"),
            "cache_index": str(index),
            "output_directory": str(tmp_path / "runs"),
        }
    )


def test_early_stopping_tracks_improvement_and_exact_patience():
    stopping = EarlyStopping(15)
    assert stopping.update(0.5) == (True, False)
    for _ in range(14):
        assert stopping.update(0.5) == (False, False)
    assert stopping.update(0.4) == (False, True)
    assert stopping.update(0.6) == (True, False)


def test_training_saves_real_state_and_resumes_without_protocol_drift(tmp_path: Path):
    config = smoke_config(tmp_path)
    directory = run_training(config, "UNet", 42, stop_after_epoch=1)
    first = load_checkpoint(directory / "last.ckpt", config)
    assert first["epoch"] == 1 and first["data_kind"] == "synthetic"
    assert first["optimizer_state"]["state"]
    run_training(config, "UNet", 42, resume=directory / "last.ckpt")
    final = load_checkpoint(directory / "last.ckpt", config)
    assert final["epoch"] == 2
    assert any(
        not torch.equal(value, final["model_state"][name])
        for name, value in first["model_state"].items()
    )
    assert (directory / "best.ckpt").is_file()
    for name in [
        "config.yaml",
        "environment.txt",
        "git_commit.txt",
        "split_manifest.json",
        "metrics.csv",
    ]:
        assert (directory / name).is_file()
    assert "NotRun" in (directory / "run_status.json").read_text()
    altered = TrainingConfig.model_validate({**config.model_dump(), "learning_rate": 0.001})
    with pytest.raises(ValueError, match="provenance"):
        load_checkpoint(directory / "last.ckpt", altered)


def test_epoch_boundary_resume_matches_uninterrupted_weights(tmp_path: Path):
    config = smoke_config(tmp_path)
    directory = run_training(config, "UNet", 42, stop_after_epoch=1)
    run_training(config, "UNet", 42, resume=directory / "last.ckpt")
    resumed = load_checkpoint(directory / "last.ckpt", config)
    uninterrupted_config = TrainingConfig.model_validate(
        {**config.model_dump(), "output_directory": str(tmp_path / "uninterrupted")}
    )
    uninterrupted_directory = run_training(uninterrupted_config, "UNet", 42)
    uninterrupted = load_checkpoint(uninterrupted_directory / "last.ckpt", uninterrupted_config)
    assert resumed["epoch"] == uninterrupted["epoch"] == 2
    assert all(
        torch.equal(value, uninterrupted["model_state"][name])
        for name, value in resumed["model_state"].items()
    )
    assert torch.equal(resumed["loader_generator_state"], uninterrupted["loader_generator_state"])


def test_testing_requires_actual_validation_freeze_and_rejects_threshold_drift(tmp_path: Path):
    config = smoke_config(tmp_path)
    directory = run_training(config, "UNet", 42)
    freeze = directory / "protocol_frozen.json"
    with pytest.raises(ValueError, match="locked"):
        run_test(config, directory / "best.ckpt", freeze, directory / "denied-test")
    run_validation(config, directory / "best.ckpt", directory / "validation.json", freeze)
    result = run_test(config, directory / "best.ckpt", freeze, directory / "test")
    assert len(result.patient_metrics) == 1
    assert len(result.slice_metrics) == 3
    assert (directory / "test" / "test_metrics.json").is_file()
    assert list((directory / "test" / "patient_masks").glob("*.nii.gz"))
    from training.protocol import read_hashed_json

    frozen = read_hashed_json(freeze)
    assert frozen["threshold"] in config.validation_thresholds
    assert frozen["threshold_source"] == "validation_only"
    altered = TrainingConfig.model_validate({**config.model_dump(), "threshold": 0.6})
    with pytest.raises(ValueError, match="changed"):
        run_test(altered, directory / "best.ckpt", freeze, directory / "changed-test")


def test_both_models_complete_explicitly_synthetic_smoke_without_fake_research_metrics(
    tmp_path: Path,
):
    from training.smoke import run_smoke

    report = run_smoke(tmp_path / "smoke")
    assert report["status"] == "SmokePassed"
    assert set(report["models"]) == {"UNet", "AttentionUNet"}
    assert report["research_metrics"]["dice"] == "NotRun"
    assert report["full_brats_training"] == "NotRun"
