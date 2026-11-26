import hashlib
import hmac
import math
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from brainseg_inference.errors import ServiceError
from brainseg_inference.settings import Settings


class ManifestMember(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    weight_file: str = Field(alias="weightFile", min_length=1, max_length=128)
    weight_sha256: str = Field(alias="weightSha256", pattern=r"^[a-f0-9]{64}$")


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    manifest_version: Literal[1] = Field(alias="manifestVersion")
    model_version: str = Field(alias="modelVersion", min_length=1, max_length=80)
    architecture: Literal["UNet", "AttentionUNet"]
    preprocessing_version: Literal["flair-v1"] = Field(alias="preprocessingVersion")
    input_size: Literal[256] = Field(alias="inputSize")
    threshold: float = Field(gt=0, lt=1)
    weight_file: str = Field(alias="weightFile", min_length=1, max_length=128)
    weight_sha256: str = Field(alias="weightSha256", pattern=r"^[a-f0-9]{64}$")
    artifact_kind: Literal["research", "synthetic_test"] = Field(alias="artifactKind")
    input_mode: Literal["2d", "2p5d"] = Field(default="2d", alias="inputMode")
    context_slices: int = Field(default=3, ge=1, le=9, alias="contextSlices")
    slice_fusion: Literal["stack", "center_attention"] = Field(default="stack", alias="sliceFusion")
    boundary_head: bool = Field(default=False, alias="boundaryHead")
    deep_supervision: bool = Field(default=False, alias="deepSupervision")
    member_weights: list[ManifestMember] = Field(
        default_factory=list, max_length=10, alias="memberWeights"
    )
    member_weight_hashes: list[str] = Field(
        default_factory=list, max_length=10, alias="memberWeightHashes"
    )
    uncertainty_enabled: bool = Field(default=False, alias="uncertaintyEnabled")
    uncertainty_method: Literal["predictive_entropy-v1"] | None = Field(
        default=None, alias="uncertaintyMethod"
    )
    uncertainty_scale_max: float | None = Field(default=None, gt=0, alias="uncertaintyScaleMax")
    uncertainty_output_dtype: Literal["uint8"] = Field(
        default="uint8", alias="uncertaintyOutputDtype"
    )

    @model_validator(mode="after")
    def validate_architecture_contract(self) -> "ModelManifest":
        if self.context_slices % 2 != 1:
            raise ValueError("Context slices must be odd.")
        if self.input_mode == "2d" and self.slice_fusion != "stack":
            raise ValueError("2D model manifests must use stack fusion.")
        if self.input_mode == "2p5d" and self.slice_fusion != "center_attention":
            raise ValueError("2.5D manifests must declare center_attention fusion.")
        if self.member_weight_hashes and self.member_weight_hashes != [
            member.weight_sha256 for member in self.member_weights
        ]:
            raise ValueError("Member weight hashes must match the declared member weights.")
        if self.member_weights and (
            self.member_weights[0].weight_file != self.weight_file
            or self.member_weights[0].weight_sha256 != self.weight_sha256
        ):
            raise ValueError("The primary weight must be the first registered ensemble member.")
        if self.uncertainty_enabled and (
            self.uncertainty_method != "predictive_entropy-v1" or self.uncertainty_scale_max is None
        ):
            raise ValueError("Uncertainty output requires a frozen method and validation scale.")
        return self

    @property
    def ensemble_members(self) -> list[ManifestMember]:
        return self.member_weights or [
            ManifestMember(weightFile=self.weight_file, weightSha256=self.weight_sha256)
        ]

    @classmethod
    def load(cls, settings: Settings) -> tuple["ModelManifest", Path, str]:
        manifest_path = settings.model_manifest_path
        if manifest_path is None or manifest_path.is_symlink() or not manifest_path.is_file():
            raise ServiceError(
                "MODEL_MANIFEST_NOT_CONFIGURED",
                "No readable model manifest is configured.",
                503,
            )
        try:
            manifest_bytes = manifest_path.read_bytes()
            data = yaml.safe_load(manifest_bytes.decode("utf-8"))
            manifest = cls.model_validate(data)
        except (OSError, yaml.YAMLError, ValidationError, TypeError) as error:
            raise ServiceError(
                "MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503
            ) from error
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}", manifest.model_version):
            raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
        base = manifest_path.resolve().parent
        weights_path: Path | None = None
        for index, member in enumerate(manifest.ensemble_members):
            if (
                Path(member.weight_file).name != member.weight_file
                or "/" in member.weight_file
                or "\\" in member.weight_file
                or ":" in member.weight_file
                or member.weight_file in {".", ".."}
                or not member.weight_file.lower().endswith(".onnx")
            ):
                raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
            configured_weights = base / member.weight_file
            if configured_weights.is_symlink():
                raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
            member_path = configured_weights.resolve()
            if member_path.parent != base or not member_path.is_file():
                raise ServiceError("MODEL_WEIGHTS_NOT_FOUND", "Model weights are unavailable.", 503)
            with member_path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if not hmac.compare_digest(digest, member.weight_sha256.lower()):
                raise ServiceError("MODEL_HASH_MISMATCH", "Model integrity validation failed.", 503)
            if index == 0:
                weights_path = member_path
        if weights_path is None:
            raise ServiceError("MODEL_WEIGHTS_NOT_FOUND", "Model weights are unavailable.", 503)
        if not math.isfinite(manifest.threshold):
            raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
        if manifest.artifact_kind != "research":
            raise ServiceError(
                "TEST_ARTIFACT_NOT_ALLOWED",
                "Synthetic or test weights cannot be served as research models.",
                503,
            )
        return manifest, weights_path, hashlib.sha256(manifest_bytes).hexdigest()
