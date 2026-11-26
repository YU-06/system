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


def patient_spatial_metrics(
    predicted: np.ndarray,
    expected: np.ndarray,
    spacing: tuple[float, float, float] | None,
    spatial_unit: str | None,
    qform: np.ndarray | None,
    qform_code: int | None,
    sform: np.ndarray | None,
    sform_code: int | None,
    affine: np.ndarray | None,
) -> dict[str, float | str | None]:
    result: dict[str, float | str | None] = {
        "predicted_lesion_volume_mm3": None,
        "ground_truth_lesion_volume_mm3": None,
        "hd95_mm": None,
        "assd_mm": None,
        "spatial_status": "NotRun_untrusted_spatial_metadata",
    }
    if spacing is None or affine is None or spatial_unit not in {"meter", "mm", "micron"}:
        return result
    valid_form = any(
        code is not None
        and code > 0
        and form is not None
        and np.asarray(form).shape == (4, 4)
        and np.isfinite(form).all()
        and np.allclose(form, affine, rtol=0, atol=1e-5)
        for form, code in ((qform, qform_code), (sform, sform_code))
    )
    if (
        not valid_form
        or np.asarray(affine).shape != (4, 4)
        or not np.isfinite(affine).all()
        or len(spacing) != 3
        or any(not np.isfinite(value) or value <= 0 for value in spacing)
    ):
        return result
    conversion = {"meter": 1000.0, "mm": 1.0, "micron": 0.001}[spatial_unit]
    spacing_mm = tuple(float(value * conversion) for value in spacing)
    voxel_volume = float(np.prod(spacing_mm))
    predicted_mask = np.asarray(predicted, dtype=bool)
    expected_mask = np.asarray(expected, dtype=bool)
    if predicted_mask.shape != expected_mask.shape or predicted_mask.ndim != 3:
        raise ValueError("Spatial metrics require aligned three-dimensional masks.")
    result["predicted_lesion_volume_mm3"] = float(predicted_mask.sum() * voxel_volume)
    result["ground_truth_lesion_volume_mm3"] = float(expected_mask.sum() * voxel_volume)
    if not predicted_mask.any() or not expected_mask.any():
        result["spatial_status"] = "NotRun_undefined_empty_surface"
        return result
    from scipy import ndimage

    structure = ndimage.generate_binary_structure(3, 1)
    predicted_surface = predicted_mask & ~ndimage.binary_erosion(
        predicted_mask, structure=structure, border_value=0
    )
    expected_surface = expected_mask & ~ndimage.binary_erosion(
        expected_mask, structure=structure, border_value=0
    )
    distance_to_expected = ndimage.distance_transform_edt(~expected_surface, sampling=spacing_mm)
    distance_to_predicted = ndimage.distance_transform_edt(~predicted_surface, sampling=spacing_mm)
    distances = np.concatenate(
        (distance_to_expected[predicted_surface], distance_to_predicted[expected_surface])
    )
    result.update(
        hd95_mm=float(np.percentile(distances, 95)),
        assd_mm=float(np.mean(distances)),
        spatial_status="computed_from_trusted_nifti_geometry",
    )
    return result


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
