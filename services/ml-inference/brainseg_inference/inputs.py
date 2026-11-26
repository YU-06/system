import gzip
import hashlib
import io
from dataclasses import dataclass
from typing import Any

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
    header: nib.Nifti1Header
    geometry: dict[str, Any]


async def read_volume(file: UploadFile, settings: Settings) -> VolumeInput:
    filename = file.filename or ""
    try:
        payload = await file.read(settings.max_upload_bytes + 1)
    finally:
        await file.close()
    if len(payload) > settings.max_upload_bytes:
        raise ServiceError("UPLOAD_TOO_LARGE", "The uploaded file exceeds the size limit.", 413)
    return parse_volume(payload, filename, settings)


def parse_volume(payload: bytes, filename: str, settings: Settings) -> VolumeInput:
    name = filename.lower()
    if not name.endswith((".nii", ".nii.gz")):
        raise ServiceError("INVALID_FILE_TYPE", "Only NIfTI-1 .nii and .nii.gz files are accepted.")
    digest = hashlib.sha256(payload).hexdigest()
    try:
        if name.endswith(".nii.gz"):
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as archive:
                decompressed = archive.read(settings.max_decompressed_bytes + 1)
        else:
            decompressed = payload
        if len(decompressed) > settings.max_decompressed_bytes:
            raise ServiceError(
                "VOLUME_TOO_LARGE", "The decompressed volume exceeds the size limit.", 413
            )
        header = nib.Nifti1Header.from_fileobj(io.BytesIO(decompressed))
        shape = header.get_data_shape()
        if len(shape) != 3 or any(
            dimension < 1 or dimension > settings.max_volume_dimension for dimension in shape
        ):
            raise ServiceError(
                "INVALID_DIMENSIONS", "A bounded three-dimensional volume is required."
            )
        if int(np.prod(shape, dtype=np.int64)) > settings.max_volume_voxels:
            raise ServiceError("VOLUME_TOO_LARGE", "The volume exceeds the voxel limit.", 413)
        if header.get_data_dtype().kind not in "iuf":
            raise ServiceError("INVALID_NUMERIC_RANGE", "A real numeric volume is required.")
        image = nib.Nifti1Image.from_bytes(decompressed)
        volume = image.get_fdata(dtype=np.float32)
        affine = np.asarray(image.affine, dtype=np.float64)
        if not np.isfinite(volume).all() or np.max(np.abs(volume), initial=0) > 1e7:
            raise ServiceError("INVALID_NUMERIC_RANGE", "Volume values must be finite and bounded.")
        if not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3, :3])) < 1e-8:
            raise ServiceError("INVALID_DIMENSIONS", "A valid volume transform is required.")
        qform, qform_code = header.get_qform(coded=True)
        sform, sform_code = header.get_sform(coded=True)
        spatial_unit, _ = header.get_xyzt_units()
        for form, code in ((qform, qform_code), (sform, sform_code)):
            if code > 0 and (
                form is None
                or not np.isfinite(form).all()
                or abs(np.linalg.det(form[:3, :3])) < 1e-8
            ):
                raise ServiceError(
                    "INVALID_SPATIAL_METADATA", "NIfTI spatial forms must be finite and invertible."
                )
        axis_codes = list(nib.aff2axcodes(affine))
        voxel_spacing = np.linalg.norm(affine[:3, :3], axis=0)
        if axis_codes[2] not in {"S", "I"}:
            raise ServiceError(
                "INVALID_ORIENTATION", "Voxel axis 2 must represent the axial direction."
            )
        if not np.allclose(np.asarray(header.get_zooms()[:3]), voxel_spacing, rtol=0, atol=1e-4):
            raise ServiceError(
                "INVALID_SPATIAL_METADATA",
                "NIfTI voxel spacing does not match the affine transform.",
            )
        geometry = {
            "shape": [int(item) for item in shape],
            "affine": affine.tolist(),
            "axisCodes": axis_codes,
            "voxelSpacing": [float(item) for item in voxel_spacing],
            "spatialUnit": spatial_unit or "unknown",
            "qformCode": int(qform_code),
            "sformCode": int(sform_code),
            "qform": np.asarray(qform, dtype=np.float64).tolist() if qform is not None else None,
            "sform": np.asarray(sform, dtype=np.float64).tolist() if sform is not None else None,
        }
        return VolumeInput(
            volume=volume,
            affine=affine,
            sha256=digest,
            header=header.copy(),
            geometry=geometry,
        )
    except ServiceError:
        raise
    except Exception as error:
        raise ServiceError("INVALID_NIFTI", "The file is not a valid NIfTI-1 volume.") from error


def ensure_same_geometry(first: VolumeInput, second: VolumeInput) -> None:
    keys = ("shape", "axisCodes", "spatialUnit", "qformCode", "sformCode")
    if any(first.geometry[key] != second.geometry[key] for key in keys):
        raise ServiceError("LABEL_ALIGNMENT_INVALID", "Image and label volume geometry must match.")
    for key in ("affine", "voxelSpacing"):
        if not np.allclose(
            np.asarray(first.geometry[key]),
            np.asarray(second.geometry[key]),
            rtol=0,
            atol=1e-5,
        ):
            raise ServiceError(
                "LABEL_ALIGNMENT_INVALID", "Image and label volume geometry must match."
            )
    for key in ("qform", "sform"):
        first_form, second_form = first.geometry[key], second.geometry[key]
        if first_form is None or second_form is None:
            if first_form is not second_form:
                raise ServiceError(
                    "LABEL_ALIGNMENT_INVALID", "Image and label volume geometry must match."
                )
        elif not np.allclose(first_form, second_form, rtol=0, atol=1e-5):
            raise ServiceError(
                "LABEL_ALIGNMENT_INVALID", "Image and label volume geometry must match."
            )
