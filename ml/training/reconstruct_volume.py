import argparse
from collections.abc import Mapping
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image

from training import DISCLAIMER
from training.metrics import BinaryMetrics, binary_metrics
from training.preprocessing import whole_tumor_mask


def reconstruct_volume(
    predictions: Mapping[int, np.ndarray], original_shape: tuple[int, int, int]
) -> np.ndarray:
    if set(predictions) != set(range(original_shape[2])):
        raise ValueError(
            "Patient reconstruction requires every axial slice, without omissions or duplicates."
        )
    volume = np.zeros(original_shape, dtype=np.uint8)
    for index in range(original_shape[2]):
        mask = np.asarray(predictions[index])
        if mask.shape != (256, 256) or not np.isin(mask, [0, 1]).all():
            raise ValueError("Predicted slices must be binary 256x256 masks.")
        resized = Image.fromarray(mask.astype(np.uint8)).resize(
            (original_shape[1], original_shape[0]), Image.Resampling.NEAREST
        )
        volume[:, :, index] = np.asarray(resized, dtype=np.uint8)
    return volume


def patient_metrics(
    predictions: Mapping[int, np.ndarray], expected: np.ndarray
) -> tuple[np.ndarray, BinaryMetrics]:
    if expected.ndim != 3:
        raise ValueError("Patient ground truth must be three-dimensional.")
    reconstructed = reconstruct_volume(predictions, tuple(expected.shape))
    return reconstructed, binary_metrics(reconstructed, expected)


def save_volume(mask: np.ndarray, affine: np.ndarray, output: Path) -> None:
    if mask.ndim != 3 or affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError("A three-dimensional mask and finite reference affine are required.")
    if not np.isin(mask, [0, 1]).all():
        raise ValueError("Only a binary WT volume can be saved.")
    output.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(mask.astype(np.uint8), affine), output)


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    arguments = parser.parse_args()
    reference = nib.load(arguments.reference)
    with np.load(arguments.predictions, allow_pickle=False) as data:
        masks, indices = data["masks"], data["slice_indices"]
        if len(indices) != len(set(indices.tolist())) or len(indices) != len(masks):
            raise ValueError("Each prediction must have a distinct slice index.")
        predictions = dict(zip(indices.tolist(), masks, strict=True))
    volume = reconstruct_volume(predictions, tuple(reference.shape))
    save_volume(volume, reference.affine, arguments.output)
    if arguments.labels:
        labels = nib.load(arguments.labels)
        if not np.allclose(labels.affine, reference.affine):
            raise ValueError("Ground truth and reference geometry must match.")
        result = binary_metrics(volume, whole_tumor_mask(labels.get_fdata(dtype=np.float32)))
        print(result.model_dump_json())
    else:
        print('{"metrics":"NotRun","reason":"No ground truth supplied"}')


if __name__ == "__main__":
    main()
