import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel


class BinaryMetrics(BaseModel):
    dice: float
    iou: float
    precision: float
    recall: float


def binary_metrics(predicted: NDArray[np.uint8], expected: NDArray[np.uint8]) -> BinaryMetrics:
    if predicted.shape != expected.shape:
        raise ValueError("Masks must have the same shape.")
    if not np.isin(predicted, [0, 1]).all() or not np.isin(expected, [0, 1]).all():
        raise ValueError("Metrics require binary masks.")
    predicted_positive = predicted.astype(bool)
    expected_positive = expected.astype(bool)
    intersection = int(np.count_nonzero(predicted_positive & expected_positive))
    predicted_count = int(np.count_nonzero(predicted_positive))
    expected_count = int(np.count_nonzero(expected_positive))
    union = predicted_count + expected_count - intersection
    total = predicted_count + expected_count
    return BinaryMetrics(
        dice=2 * intersection / total if total else 1.0,
        iou=intersection / union if union else 1.0,
        precision=intersection / predicted_count if predicted_count else 1.0,
        recall=intersection / expected_count if expected_count else 1.0,
    )
