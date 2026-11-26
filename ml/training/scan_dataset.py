import argparse
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from training import DISCLAIMER
from training.preprocessing import whole_tumor_mask
from training.protocol import resolve_data_path, sha256_file, write_hashed_json


class PatientFiles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    flair: str
    segmentation: str
    flair_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    segmentation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shape: tuple[int, int, int]
    affine: list[list[float]]
    spatial_unit: Literal["meter", "mm", "micron", "unknown"]
    qform_code: int
    sform_code: int
    qform: list[list[float]] | None = None
    sform: list[list[float]] | None = None
    voxel_spacing: tuple[float, float, float]


class DatasetScan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    dataset: Literal["BraTS 2020"] = "BraTS 2020"
    data_kind: Literal["research", "synthetic"] = "research"
    modality: Literal["T2-FLAIR"] = "T2-FLAIR"
    patients: list[PatientFiles]
    disclaimer: str = DISCLAIMER


def load_patient(root: Path, patient: PatientFiles) -> tuple[nib.Nifti1Image, nib.Nifti1Image]:
    flair_path = resolve_data_path(root, patient.flair)
    label_path = resolve_data_path(root, patient.segmentation)
    if (
        sha256_file(flair_path) != patient.flair_sha256
        or sha256_file(label_path) != patient.segmentation_sha256
    ):
        raise ValueError(f"Patient {patient.patient_id}: source data changed after scanning.")
    image = nib.load(flair_path)
    labels = nib.load(label_path)
    if not isinstance(image, nib.Nifti1Image) or not isinstance(labels, nib.Nifti1Image):
        raise ValueError("Only NIfTI-1 input is supported by the shared inference contract.")
    return image, labels


def scan_dataset(root: Path, *, synthetic: bool = False) -> DatasetScan:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("The dataset root does not exist.")
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.lower().endswith((".nii", ".nii.gz"))
    ]
    directories = {path.parent for path in files}
    directories.update(path for path in root.rglob("BraTS20_Training_*") if path.is_dir())
    if not directories:
        raise ValueError("No patient NIfTI directories were found.")
    patients: list[PatientFiles] = []
    errors: list[str] = []
    identifiers: set[str] = set()
    for directory in sorted(directories):
        identifier = directory.name
        if identifier in identifiers:
            errors.append(f"{identifier}: duplicate patient identifier")
            continue
        identifiers.add(identifier)
        candidates = [path for path in files if path.parent == directory]
        flair = [
            path
            for path in candidates
            if path.name.lower()
            in {f"{identifier.lower()}_flair.nii", f"{identifier.lower()}_flair.nii.gz"}
        ]
        labels = [
            path
            for path in candidates
            if path.name.lower()
            in {f"{identifier.lower()}_seg.nii", f"{identifier.lower()}_seg.nii.gz"}
        ]
        if len(flair) != 1 or len(labels) != 1:
            errors.append(f"{identifier}: exactly one FLAIR and one seg file are required")
            continue
        try:
            image = nib.load(resolve_data_path(root, flair[0].relative_to(root).as_posix()))
            segmentation = nib.load(resolve_data_path(root, labels[0].relative_to(root).as_posix()))
            if not isinstance(image, nib.Nifti1Image) or not isinstance(
                segmentation, nib.Nifti1Image
            ):
                raise ValueError("NIfTI-1 is required")
            if len(image.shape) != 3 or any(
                dimension < 1 or dimension > 512 for dimension in image.shape
            ):
                raise ValueError("bounded three-dimensional FLAIR is required")
            if np.prod(image.shape) > 16777216 or segmentation.shape != image.shape:
                raise ValueError("FLAIR and segmentation dimensions do not match")
            if (
                not np.isfinite(image.affine).all()
                or abs(np.linalg.det(image.affine[:3, :3])) < 1e-8
            ):
                raise ValueError("invalid affine transform")
            if not np.allclose(image.affine, segmentation.affine, atol=1e-5):
                raise ValueError("FLAIR and segmentation geometry does not match")
            if nib.aff2axcodes(image.affine)[2] not in {"S", "I"}:
                raise ValueError("axis 2 must represent the axial direction")
            qform, qform_code = image.header.get_qform(coded=True)
            sform, sform_code = image.header.get_sform(coded=True)
            for form, code in ((qform, qform_code), (sform, sform_code)):
                if code > 0 and (
                    form is None
                    or not np.isfinite(form).all()
                    or abs(np.linalg.det(form[:3, :3])) < 1e-8
                ):
                    raise ValueError("NIfTI spatial forms must be finite and invertible")
            volume = image.get_fdata(dtype=np.float32)
            if not np.isfinite(volume).all() or np.max(np.abs(volume), initial=0) > 1e7:
                raise ValueError("non-finite or out-of-range FLAIR values")
            whole_tumor_mask(segmentation.get_fdata(dtype=np.float32))
            spatial_unit, _ = image.header.get_xyzt_units()
            if spatial_unit not in {"meter", "mm", "micron"}:
                spatial_unit = "unknown"
            voxel_spacing = tuple(
                float(np.linalg.norm(image.affine[:3, axis])) for axis in range(3)
            )
            if not np.allclose(
                np.asarray(image.header.get_zooms()[:3]), voxel_spacing, rtol=0, atol=1e-4
            ):
                raise ValueError("NIfTI voxel spacing does not match the affine transform")
            patients.append(
                PatientFiles(
                    patient_id=identifier,
                    flair=flair[0].relative_to(root).as_posix(),
                    segmentation=labels[0].relative_to(root).as_posix(),
                    flair_sha256=sha256_file(flair[0]),
                    segmentation_sha256=sha256_file(labels[0]),
                    shape=tuple(int(value) for value in image.shape),
                    affine=image.affine.tolist(),
                    spatial_unit=spatial_unit,
                    qform_code=int(qform_code),
                    sform_code=int(sform_code),
                    qform=np.asarray(qform).tolist() if qform is not None else None,
                    sform=np.asarray(sform).tolist() if sform is not None else None,
                    voxel_spacing=voxel_spacing,
                )
            )
        except Exception as error:
            errors.append(f"{identifier}: {type(error).__name__}: invalid or inconsistent volume")
    if errors:
        raise ValueError(
            "Dataset integrity checks failed; no cases were silently dropped:\n" + "\n".join(errors)
        )
    return DatasetScan(data_kind="synthetic" if synthetic else "research", patients=patients)


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/dataset_scan.json"))
    parser.add_argument("--synthetic", action="store_true")
    arguments = parser.parse_args()
    scan = scan_dataset(arguments.root, synthetic=arguments.synthetic)
    digest = write_hashed_json(arguments.output, scan.model_dump(mode="json"))
    print(f"Scanned {len(scan.patients)} patients; data_kind={scan.data_kind}; sha256={digest}")


if __name__ == "__main__":
    main()
