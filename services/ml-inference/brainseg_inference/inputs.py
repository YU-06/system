import gzip
import hashlib
import io
from dataclasses import dataclass

import nibabel as nib
import numpy as np
from fastapi import UploadFile
from numpy.typing import NDArray

from brainseg_inference.errors import ServiceError
from brainseg_inference.settings import Settings


@dataclass(frozen=True)
class VolumeInput:
    volume: NDArray[np.float32]
    affine: NDArray[np.float64]
    sha256: str


async def read_volume(file: UploadFile, settings: Settings) -> VolumeInput:
    name = (file.filename or "").lower()
    if not name.endswith((".nii", ".nii.gz")) or file.content_type not in {
        "application/octet-stream",
        "application/gzip",
        "application/x-gzip",
        "application/x-nifti",
    }:
        raise ServiceError("INVALID_FILE_TYPE", "Only NIfTI-1 .nii and .nii.gz files are accepted.")
    try:
        payload = await file.read(settings.max_upload_bytes + 1)
    finally:
        await file.close()
    if len(payload) > settings.max_upload_bytes:
        raise ServiceError("UPLOAD_TOO_LARGE", "The uploaded file exceeds the size limit.", 413)
    digest = hashlib.sha256(payload).hexdigest()
    try:
        if name.endswith(".gz"):
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as archive:
                payload = archive.read(settings.max_decompressed_bytes + 1)
        if len(payload) > settings.max_decompressed_bytes:
            raise ServiceError(
                "VOLUME_TOO_LARGE", "The decompressed volume exceeds the size limit.", 413
            )
        header = nib.Nifti1Header.from_fileobj(io.BytesIO(payload))
        shape = header.get_data_shape()
        if len(shape) != 3 or any(dimension < 1 or dimension > 512 for dimension in shape):
            raise ServiceError(
                "INVALID_DIMENSIONS", "A bounded three-dimensional volume is required."
            )
        if np.prod(shape, dtype=np.int64) > settings.max_volume_voxels:
            raise ServiceError("VOLUME_TOO_LARGE", "The volume exceeds the voxel limit.", 413)
        if header.get_data_dtype().kind not in "iuf":
            raise ServiceError("INVALID_NUMERIC_RANGE", "A real numeric volume is required.")
        image = nib.Nifti1Image.from_bytes(payload)
        volume = image.get_fdata(dtype=np.float32)
        if not np.isfinite(volume).all() or np.max(np.abs(volume), initial=0) > 1e7:
            raise ServiceError("INVALID_NUMERIC_RANGE", "Volume values must be finite and bounded.")
        if not np.isfinite(image.affine).all() or abs(np.linalg.det(image.affine[:3, :3])) < 1e-8:
            raise ServiceError("INVALID_DIMENSIONS", "A valid volume transform is required.")
        return VolumeInput(volume=volume, affine=image.affine, sha256=digest)
    except ServiceError:
        raise
    except Exception as error:
        raise ServiceError("INVALID_NIFTI", "The file is not a valid NIfTI-1 volume.") from error
