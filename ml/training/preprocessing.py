import numpy as np
from numpy.typing import NDArray
from PIL import Image


def normalize_volume(volume: NDArray[np.float32]) -> NDArray[np.float32]:
    if volume.ndim != 3 or not np.isfinite(volume).all():
        raise ValueError("A finite three-dimensional volume is required.")
    brain = volume != 0
    result = np.zeros_like(volume, dtype=np.float32)
    if not brain.any():
        return result
    values = volume[brain].astype(np.float64)
    standard_deviation = values.std()
    if standard_deviation > 1e-8:
        result[brain] = np.clip((values - values.mean()) / standard_deviation, -5, 5)
    return result


def resize_image(image: NDArray[np.float32], size: int = 256) -> NDArray[np.float32]:
    return np.asarray(
        Image.fromarray(image.astype(np.float32)).resize((size, size), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )


def whole_tumor_mask(labels: NDArray[np.float32]) -> NDArray[np.uint8]:
    if not np.isfinite(labels).all() or not np.isin(labels, [0, 1, 2, 4]).all():
        raise ValueError("Only BraTS labels 0, 1, 2, and 4 are accepted.")
    return np.isin(labels, [1, 2, 4]).astype(np.uint8)


def resize_mask(mask: NDArray[np.uint8], size: int = 256) -> NDArray[np.uint8]:
    return np.asarray(
        Image.fromarray(mask.astype(np.uint8)).resize((size, size), Image.Resampling.NEAREST),
        dtype=np.uint8,
    )


def prepare_axial_slice(
    volume: NDArray[np.float32], slice_index: int, size: int = 256
) -> NDArray[np.float32]:
    if slice_index < 0 or slice_index >= volume.shape[2]:
        raise ValueError("Slice index is outside the volume.")
    return resize_image(normalize_volume(volume)[:, :, slice_index], size)
