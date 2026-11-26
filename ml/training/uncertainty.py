from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class EnsemblePrediction:
    mean_probability: NDArray[np.float32]
    binary_prediction: NDArray[np.uint8]
    predictive_entropy: NDArray[np.float32]
    model_variance: NDArray[np.float32] | None


def ensemble_probabilities(
    member_probabilities: list[NDArray[np.float32]], threshold: float
) -> EnsemblePrediction:
    if not member_probabilities or not 0 < threshold < 1:
        raise ValueError("At least one member and a valid decision threshold are required.")
    shape = member_probabilities[0].shape
    if not shape or any(
        values.shape != shape
        or not np.isfinite(values).all()
        or np.any((values < 0) | (values > 1))
        for values in member_probabilities
    ):
        raise ValueError("Ensemble members must provide aligned finite probabilities in [0, 1].")
    members = np.stack(member_probabilities).astype(np.float64, copy=False)
    mean = members.mean(axis=0)
    clipped = np.clip(mean, np.finfo(np.float64).eps, 1 - np.finfo(np.float64).eps)
    entropy = -(clipped * np.log2(clipped) + (1 - clipped) * np.log2(1 - clipped))
    variance = members.var(axis=0) if len(member_probabilities) > 1 else None
    return EnsemblePrediction(
        mean.astype(np.float32),
        (mean >= threshold).astype(np.uint8),
        entropy.astype(np.float32),
        variance.astype(np.float32) if variance is not None else None,
    )


def fit_uncertainty_scale(validation_entropy: NDArray[np.float32], percentile: float = 99) -> float:
    values = np.asarray(validation_entropy, dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all() or not 0 < percentile <= 100:
        raise ValueError("A finite nonempty validation uncertainty map is required.")
    scale = float(np.percentile(values, percentile))
    return max(scale, np.finfo(np.float32).eps)


def uncertainty_to_uint8(
    uncertainty: NDArray[np.float32], validation_scale: float
) -> NDArray[np.uint8]:
    values = np.asarray(uncertainty, dtype=np.float64)
    if not np.isfinite(values).all() or not np.isfinite(validation_scale) or validation_scale <= 0:
        raise ValueError("Uncertainty and its frozen validation scale must be finite and valid.")
    return np.rint(np.clip(values / validation_scale, 0, 1) * 100).astype(np.uint8)


def calibration_metrics(
    probability: NDArray[np.float32],
    expected: NDArray[np.uint8],
    uncertainty: NDArray[np.float32],
    bins: int = 15,
) -> dict:
    probability = np.asarray(probability, dtype=np.float64).reshape(-1)
    truth = np.asarray(expected, dtype=np.uint8).reshape(-1)
    uncertainty = np.asarray(uncertainty, dtype=np.float64).reshape(-1)
    if (
        probability.size == 0
        or probability.shape != truth.shape
        or uncertainty.shape != truth.shape
        or not np.isfinite(probability).all()
        or not np.isfinite(uncertainty).all()
        or np.any((probability < 0) | (probability > 1))
        or not np.isin(truth, [0, 1]).all()
        or bins < 1
    ):
        raise ValueError("Calibration inputs must be finite, aligned binary-volume arrays.")
    prediction = probability >= 0.5
    confidence = np.maximum(probability, 1 - probability)
    correct = prediction == truth
    ece = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for index in range(bins):
        selected = (confidence >= edges[index]) & (
            confidence <= edges[index + 1] if index == bins - 1 else confidence < edges[index + 1]
        )
        if selected.any():
            ece += float(selected.mean()) * abs(
                float(correct[selected].mean()) - float(confidence[selected].mean())
            )
    errors = (~correct).astype(np.uint8)
    return {
        "brier_score": float(np.mean((probability - truth) ** 2)),
        "ece": ece,
        "uncertainty_error_auroc": _binary_auroc(errors, uncertainty),
        "uncertainty_error_auprc": _binary_auprc(errors, uncertainty),
        "risk_coverage": risk_coverage(errors, uncertainty),
    }


def risk_coverage(
    errors: NDArray[np.uint8], uncertainty: NDArray[np.float32]
) -> list[dict[str, float]]:
    error_values = np.asarray(errors, dtype=np.uint8).reshape(-1)
    scores = np.asarray(uncertainty, dtype=np.float64).reshape(-1)
    if error_values.shape != scores.shape or not error_values.size or not np.isfinite(scores).all():
        raise ValueError("Risk-coverage inputs must be finite aligned nonempty arrays.")
    order = np.argsort(scores, kind="stable")
    cumulative = np.cumsum(error_values[order], dtype=np.float64)
    return [
        {
            "coverage": float(count / len(order)),
            "risk": float(cumulative[count - 1] / count),
        }
        for count in sorted(
            {max(1, int(np.ceil(len(order) * fraction / 10))) for fraction in range(1, 11)}
        )
    ]


def brats_retention_metrics(
    predicted: NDArray[np.uint8],
    expected: NDArray[np.uint8],
    uncertainty: NDArray[np.float32],
    thresholds: tuple[int, ...] = (10, 25, 50, 75, 90),
) -> list[dict[str, float | int | None]]:
    prediction = np.asarray(predicted)
    truth = np.asarray(expected)
    values = np.asarray(uncertainty)
    if (
        prediction.shape != truth.shape
        or prediction.shape != values.shape
        or not np.isin(prediction, [0, 1]).all()
        or not np.isin(truth, [0, 1]).all()
        or not np.isfinite(values).all()
    ):
        raise ValueError(
            "Selective evaluation requires aligned binary masks and finite uncertainty."
        )
    rows = []
    for threshold in thresholds:
        if not 0 <= threshold <= 100:
            raise ValueError("Uncertainty cutoffs must lie in [0, 100].")
        retained = values <= threshold
        retained_prediction = prediction[retained]
        retained_truth = truth[retained]
        intersection = int(np.count_nonzero(retained_prediction & retained_truth))
        predicted_count = int(np.count_nonzero(retained_prediction))
        truth_count = int(np.count_nonzero(retained_truth))
        denominator = predicted_count + truth_count
        rows.append(
            {
                "uncertainty_threshold": threshold,
                "coverage": float(retained.mean()),
                "retained_voxel_dice": (
                    None
                    if not retained.any()
                    else (2 * intersection / denominator if denominator else 1.0)
                ),
                "filtered_true_positive": int(
                    np.count_nonzero((prediction == 1) & (truth == 1) & ~retained)
                ),
                "filtered_true_negative": int(
                    np.count_nonzero((prediction == 0) & (truth == 0) & ~retained)
                ),
            }
        )
    return rows


def _binary_auroc(labels: NDArray[np.uint8], scores: NDArray[np.float64]) -> float | None:
    positives = labels.astype(bool)
    positive_count = int(positives.sum())
    negative_count = len(labels) - positive_count
    if not positive_count or not negative_count:
        return None
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2
        start = end
    return float(
        (ranks[positives].sum() - positive_count * (positive_count + 1) / 2)
        / (positive_count * negative_count)
    )


def _binary_auprc(labels: NDArray[np.uint8], scores: NDArray[np.float64]) -> float | None:
    order = np.argsort(-scores, kind="stable")
    sorted_labels = labels[order].astype(np.float64)
    positives = int(sorted_labels.sum())
    if not positives or positives == len(sorted_labels):
        return None
    true_positives = np.cumsum(sorted_labels)
    precision = true_positives / np.arange(1, len(sorted_labels) + 1)
    return float(np.sum(precision * sorted_labels) / positives)
