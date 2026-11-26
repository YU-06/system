import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel


class BinaryMetrics(BaseModel):
    dice: float
    iou: float
    precision: float
    recall: float


class ConfusionCounts(BaseModel):
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0

    def __add__(self, other: "ConfusionCounts") -> "ConfusionCounts":
        return ConfusionCounts(
            **{
                name: getattr(self, name) + getattr(other, name)
                for name in ("true_positive", "false_positive", "false_negative", "true_negative")
            }
        )


def binary_confusion(predicted: NDArray[np.uint8], expected: NDArray[np.uint8]) -> ConfusionCounts:
    if predicted.shape != expected.shape:
        raise ValueError("Masks must have the same shape.")
    if not np.isin(predicted, [0, 1]).all() or not np.isin(expected, [0, 1]).all():
        raise ValueError("Metrics require binary masks.")
    predicted_positive = predicted.astype(bool)
    expected_positive = expected.astype(bool)
    return ConfusionCounts(
        true_positive=int(np.count_nonzero(predicted_positive & expected_positive)),
        false_positive=int(np.count_nonzero(predicted_positive & ~expected_positive)),
        false_negative=int(np.count_nonzero(~predicted_positive & expected_positive)),
        true_negative=int(np.count_nonzero(~predicted_positive & ~expected_positive)),
    )


def metrics_from_confusion(counts: ConfusionCounts) -> BinaryMetrics:
    intersection = counts.true_positive
    predicted_count = counts.true_positive + counts.false_positive
    expected_count = counts.true_positive + counts.false_negative
    union = predicted_count + expected_count - intersection
    total = predicted_count + expected_count
    return BinaryMetrics(
        dice=2 * intersection / total if total else 1.0,
        iou=intersection / union if union else 1.0,
        precision=(
            intersection / predicted_count
            if predicted_count
            else (1.0 if expected_count == 0 else 0.0)
        ),
        recall=(
            intersection / expected_count
            if expected_count
            else (1.0 if predicted_count == 0 else 0.0)
        ),
    )


def binary_metrics(predicted: NDArray[np.uint8], expected: NDArray[np.uint8]) -> BinaryMetrics:
    return metrics_from_confusion(binary_confusion(predicted, expected))


def macro_metrics(scores: list[BinaryMetrics]) -> BinaryMetrics:
    if not scores:
        raise ValueError("Macro metrics require at least one independent unit.")
    return BinaryMetrics(
        **{
            name: float(np.mean([getattr(score, name) for score in scores]))
            for name in ("dice", "iou", "precision", "recall")
        }
    )
