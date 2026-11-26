import hashlib
import hmac
import math
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from brainseg_inference.errors import ServiceError
from brainseg_inference.settings import Settings


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
        if (
            Path(manifest.weight_file).name != manifest.weight_file
            or "/" in manifest.weight_file
            or "\\" in manifest.weight_file
            or ":" in manifest.weight_file
            or manifest.weight_file in {".", ".."}
            or not manifest.weight_file.lower().endswith(".onnx")
        ):
            raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
        base = manifest_path.resolve().parent
        configured_weights = base / manifest.weight_file
        if configured_weights.is_symlink():
            raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
        weights_path = configured_weights.resolve()
        if weights_path.parent != base or not weights_path.is_file():
            raise ServiceError("MODEL_WEIGHTS_NOT_FOUND", "Model weights are unavailable.", 503)
        with weights_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not hmac.compare_digest(digest, manifest.weight_sha256.lower()):
            raise ServiceError("MODEL_HASH_MISMATCH", "Model integrity validation failed.", 503)
        if not math.isfinite(manifest.threshold):
            raise ServiceError("MODEL_MANIFEST_INVALID", "The model manifest is invalid.", 503)
        if manifest.artifact_kind != "research":
            raise ServiceError(
                "TEST_ARTIFACT_NOT_ALLOWED",
                "Synthetic or test weights cannot be served as research models.",
                503,
            )
        return manifest, weights_path, hashlib.sha256(manifest_bytes).hexdigest()
