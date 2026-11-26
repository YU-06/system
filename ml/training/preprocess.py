import argparse
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from training import DISCLAIMER, PREPROCESSING_VERSION
from training.create_split import SplitManifest, load_split
from training.preprocessing import normalize_volume, resize_image, resize_mask, whole_tumor_mask
from training.protocol import read_hashed_json, resolve_data_path, sha256_file, write_hashed_json
from training.scan_dataset import load_patient


class SliceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str
    subset: Literal["train", "validation", "test"]
    slice_index: int = Field(ge=0)
    has_lesion: bool
    path: str
    sha256: str


class CachedPatient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subset: Literal["train", "validation", "test"]
    original_shape: tuple[int, int, int]
    volume_path: str
    volume_sha256: str
    affine: list[list[float]] | None = None
    spacing: tuple[float, float, float] | None = None
    orientation: tuple[str, str, str] | None = None
    spatial_unit: str | None = None
    qform_code: int | None = None
    sform_code: int | None = None
    qform: list[list[float]] | None = None
    sform: list[list[float]] | None = None


class CacheManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    data_kind: Literal["research", "synthetic"]
    preprocessing_version: Literal["flair-v1"] = "flair-v1"
    input_size: Literal[256] = 256
    split_sha256: str
    patients: dict[str, CachedPatient]
    slices: list[SliceRecord]
    disclaimer: str = DISCLAIMER

    @model_validator(mode="after")
    def validate_all_slices(self) -> "CacheManifest":
        for identifier, patient in self.patients.items():
            records = [record for record in self.slices if record.patient_id == identifier]
            if sorted(record.slice_index for record in records) != list(
                range(patient.original_shape[2])
            ):
                raise ValueError("The cache must contain every axial slice exactly once.")
            if any(record.subset != patient.subset for record in records):
                raise ValueError("A patient's slices cannot cross dataset subsets.")
        if any(record.patient_id not in self.patients for record in self.slices):
            raise ValueError("Unknown patients cannot appear in the slice cache.")
        return self


def subset_for(manifest: SplitManifest, identifier: str) -> Literal["train", "validation", "test"]:
    if identifier in manifest.train:
        return "train"
    if identifier in manifest.validation:
        return "validation"
    if identifier in manifest.test:
        return "test"
    raise ValueError("Patient is absent from the split manifest.")


def preprocess_dataset(dataset_root: Path, split_path: Path, output: Path) -> CacheManifest:
    manifest = load_split(split_path)
    if output.exists():
        raise FileExistsError("The output cache already exists; it was not overwritten.")
    output.mkdir(parents=True)
    patients: dict[str, CachedPatient] = {}
    slices: list[SliceRecord] = []
    for identifier, files in sorted(manifest.patients.items()):
        image, labels = load_patient(dataset_root, files)
        volume = image.get_fdata(dtype=np.float32)
        mask = whole_tumor_mask(labels.get_fdata(dtype=np.float32))
        normalized = normalize_volume(volume)
        subset = subset_for(manifest, identifier)
        patient_directory = output / identifier
        patient_directory.mkdir()
        volume_path = patient_directory / "original_mask.npz"
        np.savez_compressed(volume_path, mask=mask, affine=image.affine)
        patients[identifier] = CachedPatient(
            subset=subset,
            original_shape=tuple(volume.shape),
            volume_path=volume_path.relative_to(output).as_posix(),
            volume_sha256=sha256_file(volume_path),
            affine=image.affine.tolist(),
            spacing=tuple(float(np.linalg.norm(image.affine[:3, axis])) for axis in range(3)),
            orientation=tuple(str(code) for code in nib.aff2axcodes(image.affine)),
            spatial_unit=image.header.get_xyzt_units()[0] or "unknown",
            qform_code=int(image.header["qform_code"]),
            sform_code=int(image.header["sform_code"]),
            qform=(
                np.asarray(image.header.get_qform(), dtype=np.float64).tolist()
                if int(image.header["qform_code"]) > 0
                else None
            ),
            sform=(
                np.asarray(image.header.get_sform(), dtype=np.float64).tolist()
                if int(image.header["sform_code"]) > 0
                else None
            ),
        )
        for slice_index in range(volume.shape[2]):
            path = patient_directory / f"slice_{slice_index:04}.npz"
            np.savez_compressed(
                path,
                image=resize_image(normalized[:, :, slice_index]),
                mask=resize_mask(mask[:, :, slice_index]),
            )
            slices.append(
                SliceRecord(
                    patient_id=identifier,
                    subset=subset,
                    slice_index=slice_index,
                    has_lesion=bool(mask[:, :, slice_index].any()),
                    path=path.relative_to(output).as_posix(),
                    sha256=sha256_file(path),
                )
            )
    cache = CacheManifest(
        data_kind=manifest.data_kind,
        split_sha256=sha256_file(split_path),
        preprocessing_version=PREPROCESSING_VERSION,
        patients=patients,
        slices=slices,
    )
    write_hashed_json(output / "index.json", cache.model_dump(mode="json"))
    return cache


def load_cache(path: Path) -> CacheManifest:
    return CacheManifest.model_validate(read_hashed_json(path))


def load_original_mask(
    index_path: Path, identifier: str, cache: CacheManifest | None = None
) -> tuple[np.ndarray, np.ndarray]:
    cache = cache or load_cache(index_path)
    patient = cache.patients[identifier]
    path = resolve_data_path(index_path.parent, patient.volume_path)
    if sha256_file(path) != patient.volume_sha256:
        raise ValueError("Cached patient volume integrity validation failed.")
    with np.load(path, allow_pickle=False) as data:
        return data["mask"].astype(np.uint8), data["affine"].astype(np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description=DISCLAIMER)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/preprocessed"))
    arguments = parser.parse_args()
    cache = preprocess_dataset(arguments.root, arguments.split, arguments.output)
    print(
        f"Cached {len(cache.patients)} patients and {len(cache.slices)} "
        f"complete axial slices; {cache.data_kind}"
    )


if __name__ == "__main__":
    main()
