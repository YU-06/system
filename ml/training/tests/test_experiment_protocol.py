from pathlib import Path

import pytest
from training.experiment_protocol import (
    assert_only_declared_condition_differences,
    build_condition_run_config,
    load_experiment_protocol,
    select_validation_threshold,
    validate_training_config,
)
from training.protocol import load_config

PROTOCOL = load_experiment_protocol()


def test_preregistered_config_pair_has_only_gate_architecture_and_run_id_differences():
    training = load_config(Path("ml/configs/baseline.yaml"))
    validate_training_config(PROTOCOL, training)
    base = training.model_dump(mode="json")
    unet = build_condition_run_config(PROTOCOL, base, "UNet", 17)
    attention = build_condition_run_config(PROTOCOL, base, "AttentionUNet", 17)
    differences = assert_only_declared_condition_differences(unet, attention, PROTOCOL)
    assert {item["path"] for item in differences} == {
        "model.architecture",
        "model.attention_gate",
        "run_id",
    }


def test_protocol_yaml_covers_requested_variable_control_and_statistical_contracts():
    config = load_config(Path("ml/configs/baseline.yaml"))
    validate_training_config(PROTOCOL, config)
    assert PROTOCOL.seeds == [17, 42, 2024]
    assert PROTOCOL.model_selection["candidate_thresholds"] == [
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
    ]
    assert PROTOCOL.ablation["changed_component"] == "skip_connection_attention_gate"
    assert PROTOCOL.evaluation["patient_is_independent_unit"] is True
    assert PROTOCOL.statistics["patient_pair_bootstrap"]["resampling_unit"] == "patient_pair"


def test_any_unregistered_control_change_is_rejected():
    base = load_config(Path("ml/configs/baseline.yaml")).model_dump(mode="json")
    unet = build_condition_run_config(PROTOCOL, base, "UNet", 42)
    attention = build_condition_run_config(PROTOCOL, base, "AttentionUNet", 42)
    attention["learning_rate"] = 0.0002
    with pytest.raises(ValueError, match="Unregistered experimental control differences"):
        assert_only_declared_condition_differences(unet, attention, PROTOCOL)


def test_all_three_seeds_pair_conditions_and_use_locked_threshold_grid():
    base = load_config(Path("ml/configs/baseline.yaml")).model_dump(mode="json")
    for seed in (17, 42, 2024):
        first = build_condition_run_config(PROTOCOL, base, "UNet", seed)
        second = build_condition_run_config(PROTOCOL, base, "AttentionUNet", seed)
        assert first["seed"] == second["seed"] == seed
        assert_only_declared_condition_differences(first, second, PROTOCOL)
    assert PROTOCOL.model_selection["candidate_thresholds"] == [
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
    ]


def test_validation_threshold_ties_follow_preregistered_rule():
    scores = {value: 0.75 for value in PROTOCOL.model_selection["candidate_thresholds"]}
    assert select_validation_threshold(scores, PROTOCOL, "search") == 0.50
    scores[0.45] = scores[0.55] = 0.9
    assert select_validation_threshold(scores, PROTOCOL, "search") == 0.45
    assert select_validation_threshold({0.50: 0.2}, PROTOCOL, "fixed_050") == 0.50
    with pytest.raises(ValueError, match="Every preregistered"):
        select_validation_threshold({0.50: 0.5}, PROTOCOL, "search")


def test_training_config_divergence_and_wrong_seed_protocol_are_rejected():
    config = load_config(Path("ml/configs/baseline.yaml"))
    changed = config.model_copy(update={"batch_size": config.batch_size + 1})
    with pytest.raises(ValueError, match="violates"):
        validate_training_config(PROTOCOL, changed)
    with pytest.raises(ValueError, match="fixed to"):
        type(PROTOCOL).model_validate({**PROTOCOL.model_dump(), "seeds": [42, 2024, 3407]})


def test_protocol_rejects_split_and_inference_changes():
    altered_split = PROTOCOL.model_dump()
    altered_split["split"]["counts"] = [257, 75, 37]
    with pytest.raises(ValueError, match="split is fixed"):
        type(PROTOCOL).model_validate(altered_split)

    altered_bootstrap = PROTOCOL.model_dump()
    altered_bootstrap["statistics"]["patient_pair_bootstrap"]["confidence_level"] = 0.90
    with pytest.raises(ValueError, match="Bootstrap"):
        type(PROTOCOL).model_validate(altered_bootstrap)

    altered_training = PROTOCOL.model_dump()
    altered_training["shared_training"]["learning_rate"] = 0.0002
    with pytest.raises(ValueError, match="Shared training controls"):
        type(PROTOCOL).model_validate(altered_training)
