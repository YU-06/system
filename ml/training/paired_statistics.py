from typing import Any

import numpy as np
from scipy.stats import wilcoxon

from training import DISCLAIMER
from training.experiment_protocol import ExperimentProtocol


def summarize_paired_seed_metrics(
    per_condition_seed_patient_dice: dict[str, dict[int, dict[str, float]]],
    protocol: ExperimentProtocol,
    expected_patients: set[str] | None = None,
) -> dict[str, Any]:
    conditions = list(protocol.conditions)
    seeds = protocol.seeds
    if len(conditions) != 2:
        raise ValueError(
            "Paired model statistics require exactly the preregistered two conditions."
        )
    if set(per_condition_seed_patient_dice) != set(conditions):
        raise ValueError("Paired statistics accept only the two preregistered model conditions.")
    for condition, seed_results in per_condition_seed_patient_dice.items():
        if set(seed_results) - set(seeds):
            raise ValueError(f"Unregistered seed observations found for {condition}.")
        for patient_scores in seed_results.values():
            if any(
                not isinstance(value, (int, float, np.number))
                or not np.isfinite(value)
                or not 0 <= value <= 1
                for value in patient_scores.values()
            ):
                raise ValueError("Patient-level WT Dice must be finite values within [0, 1].")
    observed_patients = {
        patient
        for seed_results in per_condition_seed_patient_dice.values()
        for patient_scores in seed_results.values()
        for patient in patient_scores
    }
    candidate_patients = expected_patients if expected_patients is not None else observed_patients
    missing: list[dict[str, Any]] = []
    unexpected = (
        [
            {"condition": condition, "seed": seed, "patient_id": patient}
            for condition, seed_results in per_condition_seed_patient_dice.items()
            for seed, patient_scores in seed_results.items()
            for patient in sorted(set(patient_scores) - candidate_patients)
        ]
        if expected_patients is not None
        else []
    )
    complete: list[str] = []
    for patient in sorted(candidate_patients):
        missing_for_patient = [
            {"condition": condition, "seed": seed, "patient_id": patient}
            for condition in conditions
            for seed in seeds
            if patient not in per_condition_seed_patient_dice.get(condition, {}).get(seed, {})
        ]
        if missing_for_patient:
            missing.extend(missing_for_patient)
        else:
            complete.append(patient)
    for condition in conditions:
        if set(per_condition_seed_patient_dice.get(condition, {})) != set(seeds):
            for seed in sorted(
                set(seeds) ^ set(per_condition_seed_patient_dice.get(condition, {}))
            ):
                missing.append({"condition": condition, "seed": seed, "patient_id": None})
    values = [
        per_condition_seed_patient_dice[condition][seed][patient]
        for condition in conditions
        for seed in seeds
        for patient in complete
    ]
    if any(not np.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("Patient-level WT Dice must be finite values within [0, 1].")
    result: dict[str, Any] = {
        "disclaimer": DISCLAIMER,
        "status": (
            "NotRun" if not complete else "partial" if missing or unexpected else "complete"
        ),
        "scope": "patient-level Whole Tumor Dice",
        "conditions": conditions,
        "seeds": seeds,
        "n_expected_patients": len(candidate_patients),
        "n_complete_paired_patients": len(complete),
        "n_patients_missing_at_least_one_condition_seed": len(candidate_patients) - len(complete),
        "missing_pairs": missing,
        "unexpected_patient_pairs": unexpected,
        "imputation": "none",
        "independent_unit": "patient",
        "seed_handling": (
            "average three paired runs within each patient before between-model inference"
        ),
    }
    if not complete:
        result["reason"] = (
            "No patient has complete observations for both conditions and all three seeds."
        )
        result["cross_seed_mean_std"] = "NotRun"
        result["patient_distribution"] = "NotRun"
        result["paired_wilcoxon"] = "NotRun"
        result["patient_pair_bootstrap_ci"] = "NotRun"
        return result

    patient_means: dict[str, dict[str, float]] = {}
    seed_summary: dict[str, dict[str, float | list[float]]] = {}
    patient_distributions: dict[str, dict[str, Any]] = {}
    for condition in conditions:
        means_by_seed = {
            str(seed): float(
                np.mean(
                    [
                        per_condition_seed_patient_dice[condition][seed][patient]
                        for patient in complete
                    ]
                )
            )
            for seed in seeds
        }
        seed_values = np.asarray(list(means_by_seed.values()), dtype=np.float64)
        seed_summary[condition] = {
            "seed_patient_macro_dice": means_by_seed,
            "mean": float(seed_values.mean()),
            "std_sample_ddof_1": float(seed_values.std(ddof=1)),
            "n_seeds": len(seed_values),
        }
        patient_means[condition] = {
            patient: float(
                np.mean(
                    [per_condition_seed_patient_dice[condition][seed][patient] for seed in seeds]
                )
            )
            for patient in complete
        }
        distribution = np.asarray(list(patient_means[condition].values()), dtype=np.float64)
        patient_distributions[condition] = {
            "n_patients": int(distribution.size),
            "mean": float(distribution.mean()),
            "std_sample_ddof_1": float(distribution.std(ddof=1)) if distribution.size > 1 else 0.0,
            "min": float(distribution.min()),
            "q1": float(np.quantile(distribution, 0.25)),
            "median": float(np.median(distribution)),
            "q3": float(np.quantile(distribution, 0.75)),
            "max": float(distribution.max()),
            "patient_scores": patient_means[condition],
        }

    baseline, attention = conditions
    differences = np.asarray(
        [
            patient_means[attention][patient] - patient_means[baseline][patient]
            for patient in complete
        ],
        dtype=np.float64,
    )
    nonzero = differences[differences != 0]
    wilcoxon_record: dict[str, Any] = {
        "alternative": "two-sided",
        "zero_method": "wilcox",
        "zero_differences_excluded": int(differences.size - nonzero.size),
        "n_paired_patients": int(differences.size),
        "n_effective_nonzero_differences": int(nonzero.size),
        "median_paired_difference_attention_minus_unet": float(np.median(differences)),
        "assumptions": protocol.statistics["wilcoxon"]["assumptions"],
    }
    if nonzero.size == 0:
        wilcoxon_record.update(
            status="not_informative_all_zero_differences", statistic=0.0, p_value=1.0
        )
    else:
        test = wilcoxon(differences, zero_method="wilcox", alternative="two-sided", method="auto")
        wilcoxon_record.update(
            status="computed", statistic=float(test.statistic), p_value=float(test.pvalue)
        )

    bootstrap_protocol = protocol.statistics["patient_pair_bootstrap"]
    repetitions = int(bootstrap_protocol["resamples"])
    bootstrap_seed = int(bootstrap_protocol["seed"])
    rng = np.random.default_rng(bootstrap_seed)
    bootstrap_means = np.empty(repetitions, dtype=np.float64)
    chunk_size = 512
    for start in range(0, repetitions, chunk_size):
        stop = min(start + chunk_size, repetitions)
        sample_indices = rng.integers(0, differences.size, size=(stop - start, differences.size))
        bootstrap_means[start:stop] = differences[sample_indices].mean(axis=1)
    alpha = 1 - float(bootstrap_protocol["confidence_level"])
    interval = np.quantile(bootstrap_means, [alpha / 2, 1 - alpha / 2])
    bootstrap_record = {
        "status": "computed",
        "statistic": "mean paired patient-level Dice difference (Attention U-Net - U-Net)",
        "mean_difference": float(differences.mean()),
        "confidence_level": float(bootstrap_protocol["confidence_level"]),
        "lower": float(interval[0]),
        "upper": float(interval[1]),
        "resamples": repetitions,
        "random_seed": bootstrap_seed,
        "resampling_unit": "complete paired patient",
        "interval": "percentile",
        "n_paired_patients": int(differences.size),
    }
    result.update(
        cross_seed_mean_std=seed_summary,
        patient_distribution=patient_distributions,
        paired_patient_differences={
            patient: float(value) for patient, value in zip(complete, differences, strict=True)
        },
        paired_wilcoxon=wilcoxon_record,
        patient_pair_bootstrap_ci=bootstrap_record,
    )
    return result
