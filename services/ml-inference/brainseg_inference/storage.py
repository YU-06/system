import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brainseg_inference.errors import ServiceError

_OBJECT_KEY = re.compile(r"^[0-9a-f]{32}\.nii\.gz$")


@dataclass(frozen=True)
class StoredArtifact:
    object_key: str
    sha256: str


class LocalObjectStorage:
    def __init__(self, root: Path, max_object_bytes: int) -> None:
        self.root = root
        self.max_object_bytes = max_object_bytes

    def put_prediction(self, payload: bytes, metadata: dict[str, Any]) -> StoredArtifact:
        object_key = f"{uuid.uuid4().hex}.nii.gz"
        digest = hashlib.sha256(payload).hexdigest()
        self._atomic_write(self.root / object_key, payload)
        try:
            manifest = {
                **metadata,
                "objectKey": object_key,
                "predictionSha256": digest,
            }
            encoded = (json.dumps(manifest, sort_keys=True, allow_nan=False) + "\n").encode()
            self._atomic_write(self.root / f"{object_key}.json", encoded)
        except Exception:
            (self.root / object_key).unlink(missing_ok=True)
            raise
        return StoredArtifact(object_key=object_key, sha256=digest)

    def read_prediction(self, object_key: str) -> tuple[bytes, dict[str, Any], str]:
        if not _OBJECT_KEY.fullmatch(object_key):
            raise ServiceError(
                "INVALID_OBJECT_REFERENCE", "The prediction object reference is invalid."
            )
        payload_path = self.root / object_key
        metadata_path = self.root / f"{object_key}.json"
        try:
            if payload_path.is_symlink() or metadata_path.is_symlink():
                raise OSError("Symbolic links are not valid object references.")
            if (
                payload_path.stat().st_size > self.max_object_bytes
                or metadata_path.stat().st_size > 1048576
            ):
                raise ServiceError(
                    "PREDICTION_TOO_LARGE",
                    "The stored prediction artifact exceeds the configured size limit.",
                    413,
                )
            payload = payload_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except ServiceError:
            raise
        except (OSError, json.JSONDecodeError) as error:
            raise ServiceError(
                "PREDICTION_NOT_FOUND", "The prediction artifact is unavailable.", 404
            ) from error
        digest = hashlib.sha256(payload).hexdigest()
        if (
            not isinstance(metadata, dict)
            or metadata.get("objectKey") != object_key
            or metadata.get("predictionSha256") != digest
        ):
            raise ServiceError(
                "PREDICTION_INTEGRITY_FAILED",
                "The prediction artifact failed integrity validation.",
                409,
            )
        return payload, metadata, digest

    def _atomic_write(self, destination: Path, payload: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
