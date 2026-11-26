import math
import random
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
import torch
from torch.utils.data import Dataset

from training.preprocess import load_cache
from training.protocol import resolve_data_path, sha256_file
from training.transforms import SynchronizedTransforms


class SliceSample(TypedDict):
    image: torch.Tensor
    mask: torch.Tensor
    patient_id: str
    slice_index: int
    has_lesion: bool


class Brats2DDataset(Dataset[SliceSample]):
    def __init__(
        self,
        index_path: Path,
        subset: Literal["train", "validation", "test"],
        transform: SynchronizedTransforms | None = None,
        empty_fraction: float | None = None,
        seed: int = 42,
    ) -> None:
        if subset != "train" and (transform is not None or empty_fraction is not None):
            raise ValueError(
                "Validation and test must retain every slice without random augmentation."
            )
        self.index_path = index_path
        self.cache = load_cache(index_path)
        self.transform = transform
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

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> SliceSample:
        record = self.records[index]
        path = resolve_data_path(self.index_path.parent, record.path)
        if sha256_file(path) != record.sha256:
            raise ValueError("Cached slice integrity validation failed.")
        with np.load(path, allow_pickle=False) as data:
            image = data["image"].astype(np.float32)
            mask = data["mask"].astype(np.float32)
        if image.shape != (256, 256) or mask.shape != image.shape or not np.isfinite(image).all():
            raise ValueError("Cached slices must match the fixed finite 256x256 contract.")
        if not np.isin(mask, [0, 1]).all():
            raise ValueError("Cached masks must be binary.")
        image_tensor = torch.from_numpy(image).unsqueeze(0)
        mask_tensor = torch.from_numpy(mask).unsqueeze(0)
        if self.transform is not None:
            image_tensor, mask_tensor = self.transform(image_tensor, mask_tensor)
        return SliceSample(
            image=image_tensor,
            mask=mask_tensor,
            patient_id=record.patient_id,
            slice_index=record.slice_index,
            has_lesion=record.has_lesion,
        )
