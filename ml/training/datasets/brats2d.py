import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import nibabel as nib
import numpy as np
import torch
from torch.utils.data import Dataset

from training.preprocess import load_cache, load_original_mask
from training.preprocessing import context_slice_indices
from training.protocol import resolve_data_path, sha256_file
from training.transforms import SynchronizedTransforms


@dataclass(frozen=True)
class PatientGeometry:
    affine: torch.Tensor
    spacing: torch.Tensor
    orientation: tuple[str, str, str]
    spatial_unit: str | None
    qform: np.ndarray | None
    qform_code: int | None
    sform: np.ndarray | None
    sform_code: int | None


class SliceSample(TypedDict):
    image: torch.Tensor
    mask: torch.Tensor
    patient_id: str
    slice_index: int
    center_slice_index: int
    has_lesion: bool
    original_shape: tuple[int, int, int]
    affine: torch.Tensor
    spacing: torch.Tensor
    orientation: tuple[str, str, str]
    preprocessing_version: str


class Brats2DDataset(Dataset[SliceSample]):
    def __init__(
        self,
        index_path: Path,
        subset: Literal["train", "validation", "test"],
        transform: SynchronizedTransforms | None = None,
        empty_fraction: float | None = None,
        seed: int = 42,
        input_mode: Literal["2d", "2p5d"] = "2d",
        context_slices: int = 3,
    ) -> None:
        if subset != "train" and (transform is not None or empty_fraction is not None):
            raise ValueError(
                "Validation and test must retain every slice without random augmentation."
            )
        if context_slices < 1 or context_slices % 2 != 1:
            raise ValueError("Context slices must be an odd positive number.")
        self.index_path = index_path
        self.cache = load_cache(index_path)
        self.input_mode = input_mode
        self.context_slices = context_slices
        self.transform = transform
        self.slice_records = {
            (record.patient_id, record.slice_index): record for record in self.cache.slices
        }
        records = [record for record in self.cache.slices if record.subset == subset]
        if empty_fraction is not None:
            if not 0 <= empty_fraction < 1:
                raise ValueError("Training empty-slice fraction must be in [0, 1).")
            positive = [record for record in records if record.has_lesion]
            negative = [record for record in records if not record.has_lesion]
            if not positive:
                raise ValueError(
                    "At least one lesion slice is required for controlled training sampling."
                )
            allowed = min(
                len(negative), math.floor(len(positive) * empty_fraction / (1 - empty_fraction))
            )
            records = positive + random.Random(seed).sample(negative, allowed)
        self.records = sorted(records, key=lambda record: (record.patient_id, record.slice_index))
        if not self.records:
            raise ValueError("The selected dataset subset is empty.")
        self.patient_geometry: dict[str, PatientGeometry] = {}
        for identifier in {record.patient_id for record in self.records}:
            patient = self.cache.patients[identifier]
            affine = patient.affine
            if affine is None:
                _, legacy_affine = load_original_mask(index_path, identifier, self.cache)
                affine = legacy_affine.tolist()
            affine_array = np.asarray(affine, dtype=np.float64)
            spacing = patient.spacing or tuple(
                float(np.linalg.norm(affine_array[:3, axis])) for axis in range(3)
            )
            orientation = patient.orientation or tuple(
                str(code) for code in nib.aff2axcodes(affine_array)
            )
            if affine_array.shape != (4, 4) or len(spacing) != 3 or len(orientation) != 3:
                raise ValueError("Cached patient spatial metadata is invalid.")
            self.patient_geometry[identifier] = PatientGeometry(
                affine=torch.from_numpy(affine_array.copy()),
                spacing=torch.tensor(spacing, dtype=torch.float64),
                orientation=orientation,
                spatial_unit=patient.spatial_unit,
                qform=np.asarray(patient.qform, dtype=np.float64) if patient.qform else None,
                qform_code=patient.qform_code,
                sform=np.asarray(patient.sform, dtype=np.float64) if patient.sform else None,
                sform_code=patient.sform_code,
            )

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> SliceSample:
        record = self.records[index]
        patient = self.cache.patients[record.patient_id]
        indices = (
            context_slice_indices(
                record.slice_index, patient.original_shape[2], self.context_slices
            )
            if self.input_mode == "2p5d"
            else (record.slice_index,)
        )
        images: list[np.ndarray] = []
        mask: np.ndarray | None = None
        for slice_index in indices:
            context_record = self.slice_records[(record.patient_id, slice_index)]
            path = resolve_data_path(self.index_path.parent, context_record.path)
            if sha256_file(path) != context_record.sha256:
                raise ValueError("Cached slice integrity validation failed.")
            with np.load(path, allow_pickle=False) as data:
                image = data["image"].astype(np.float32)
                current_mask = data["mask"].astype(np.float32)
            if (
                image.shape != (256, 256)
                or current_mask.shape != image.shape
                or not np.isfinite(image).all()
            ):
                raise ValueError("Cached slices must match the fixed finite 256x256 contract.")
            if not np.isin(current_mask, [0, 1]).all():
                raise ValueError("Cached masks must be binary.")
            images.append(image)
            if slice_index == record.slice_index:
                mask = current_mask
        if mask is None:
            raise ValueError("The center slice is missing from its context window.")
        image_tensor = (
            torch.from_numpy(np.stack(images))
            if self.input_mode == "2p5d"
            else torch.from_numpy(images[0]).unsqueeze(0)
        )
        mask_tensor = torch.from_numpy(mask).unsqueeze(0)
        if self.transform is not None:
            image_tensor, mask_tensor = self.transform(image_tensor, mask_tensor)
        geometry = self.patient_geometry[record.patient_id]
        return SliceSample(
            image=image_tensor,
            mask=mask_tensor,
            patient_id=record.patient_id,
            slice_index=record.slice_index,
            center_slice_index=record.slice_index,
            has_lesion=record.has_lesion,
            original_shape=patient.original_shape,
            affine=geometry.affine,
            spacing=geometry.spacing,
            orientation=geometry.orientation,
            preprocessing_version=self.cache.preprocessing_version,
        )
