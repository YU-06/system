import pytest
from training.experiment_protocol import load_experiment_protocol
from training.paired_statistics import summarize_paired_seed_metrics

PROTOCOL = load_experiment_protocol()
SEEDS = PROTOCOL.seeds


def observations(unet, attention):
    return {
        "UNet": {
            seed: {
                patient: value for patient, value in zip(["p1", "p2", "p3"], values, strict=True)
            }
            for seed, values in zip(SEEDS, unet, strict=True)
        },
        "AttentionUNet": {
            seed: {
                patient: value for patient, value in zip(["p1", "p2", "p3"], values, strict=True)
            }
            for seed, values in zip(SEEDS, attention, strict=True)
        },
    }


def test_paired_statistics_average_seeds_by_patient_then_compare_patients():
    result = summarize_paired_seed_metrics(
        observations(
            [[0.4, 0.6, 0.8], [0.5, 0.7, 0.7], [0.6, 0.5, 0.9]],
            [[0.5, 0.7, 0.8], [0.6, 0.8, 0.7], [0.7, 0.6, 0.9]],
        ),
        PROTOCOL,
        {"p1", "p2", "p3"},
    )
    assert result["n_complete_paired_patients"] == 3
    assert result["independent_unit"] == "patient"
    assert result["cross_seed_mean_std"]["UNet"]["n_seeds"] == 3
    assert result["paired_wilcoxon"]["alternative"] == "two-sided"
    assert result["paired_wilcoxon"]["zero_method"] == "wilcox"
    assert result["paired_wilcoxon"]["n_effective_nonzero_differences"] == 2
    assert result["paired_wilcoxon"]["assumptions"]
    assert result["patient_pair_bootstrap_ci"]["resampling_unit"] == "complete paired patient"
    assert result["patient_pair_bootstrap_ci"]["resamples"] == 10000
    assert (
        result["patient_pair_bootstrap_ci"]["lower"] <= result["patient_pair_bootstrap_ci"]["upper"]
    )


def test_missing_seed_patient_pairs_are_reported_and_never_imputed():
    values = observations([[0.5, 0.6, 0.7]] * 3, [[0.6, 0.7, 0.8]] * 3)
    del values["AttentionUNet"][2024]["p2"]
    result = summarize_paired_seed_metrics(values, PROTOCOL, {"p1", "p2", "p3", "p4"})
    assert result["n_complete_paired_patients"] == 2
    assert result["status"] == "partial"
    assert result["n_patients_missing_at_least_one_condition_seed"] == 2
    assert {item["patient_id"] for item in result["missing_pairs"]} == {"p2", "p4"}
    assert result["imputation"] == "none"


def test_unexpected_patient_pairs_are_reported_separately():
    values = observations([[0.5, 0.6, 0.7]] * 3, [[0.6, 0.7, 0.8]] * 3)
    values["UNet"][17]["outside_split"] = 0.9
    result = summarize_paired_seed_metrics(values, PROTOCOL, {"p1", "p2", "p3"})
    assert result["status"] == "partial"
    assert result["unexpected_patient_pairs"] == [
        {"condition": "UNet", "seed": 17, "patient_id": "outside_split"}
    ]


def test_missing_required_seed_run_reports_not_run_with_gap():
    values = observations([[0.5, 0.6, 0.7]] * 3, [[0.6, 0.7, 0.8]] * 3)
    del values["UNet"][17]
    result = summarize_paired_seed_metrics(values, PROTOCOL, {"p1", "p2", "p3"})
    assert result["status"] == "NotRun"
    assert result["n_complete_paired_patients"] == 0
    assert result["paired_wilcoxon"] == "NotRun"
    assert any(
        item["seed"] == 17 and item["patient_id"] is None for item in result["missing_pairs"]
    )


def test_zero_differences_follow_preregistered_wilcox_exclusion():
    result = summarize_paired_seed_metrics(
        observations([[0.5, 0.6, 0.7]] * 3, [[0.5, 0.6, 0.7]] * 3),
        PROTOCOL,
        {"p1", "p2", "p3"},
    )
    test = result["paired_wilcoxon"]
    assert test["status"] == "not_informative_all_zero_differences"
    assert test["zero_differences_excluded"] == 3
    assert test["n_effective_nonzero_differences"] == 0
    assert test["p_value"] == 1.0
    assert result["patient_pair_bootstrap_ci"]["lower"] == 0.0
    assert result["patient_pair_bootstrap_ci"]["upper"] == 0.0


def test_unregistered_conditions_seeds_and_invalid_patient_scores_are_rejected():
    values = observations([[0.5, 0.6, 0.7]] * 3, [[0.6, 0.7, 0.8]] * 3)
    values["UNet"][99] = {"p1": 0.5}
    with pytest.raises(ValueError, match="Unregistered seed"):
        summarize_paired_seed_metrics(values, PROTOCOL)

    values["UNet"].pop(99)
    values["UNet"][17]["p1"] = 1.1
    with pytest.raises(ValueError, match="within \\[0, 1\\]"):
        summarize_paired_seed_metrics(values, PROTOCOL)
