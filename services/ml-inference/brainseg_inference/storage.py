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
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@dataclass(frozen=True)
class StoredArtifact:
    object_key: str
    sha256: str


class LocalObjectStorage:
    def __init__(self, root: Path, max_object_bytes: int) -> None:
        self.root = root
        self.max_object_bytes = max_object_bytes

    @staticmethod
    def prediction_key(request_id: str) -> str:
        if not _REQUEST_ID.fullmatch(request_id):
            raise ServiceError("INVALID_REQUEST_ID", "The request identifier is invalid.")
        return f"{uuid.uuid5(uuid.NAMESPACE_URL, request_id).hex}.nii.gz"

    def put_prediction(self, payload: bytes, metadata: dict[str, Any]) -> StoredArtifact:
        request_id = metadata.get("requestId")
        if not isinstance(request_id, str):
            raise ServiceError("INVALID_REQUEST_ID", "The request identifier is invalid.")
        object_key = self.prediction_key(request_id)
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

    def read_prediction_response(self, request_id: str, input_sha256: str) -> dict[str, Any] | None:
        object_key = self.prediction_key(request_id)
        try:
            _, metadata, digest = self.read_prediction(object_key)
        except ServiceError as error:
            if error.code == "PREDICTION_NOT_FOUND":
                return None
            raise
        if metadata.get("requestId") != request_id or metadata.get("inputSha256") != input_sha256:
            raise ServiceError(
                "IDEMPOTENCY_CONFLICT",
                "The request identifier was used for a different input volume.",
                409,
            )
        response = metadata.get("response")
        if not isinstance(response, dict):
            return None
        if (
            response.get("predictionObjectKey") != object_key
            or response.get("predictionSha256") != digest
            or response.get("requestId") != request_id
            or response.get("inputSha256") != input_sha256
        ):
            raise ServiceError("REQUEST_RECEIPT_INVALID", "The request receipt is incomplete.", 409)
        return response

    def save_prediction_response(self, object_key: str, response: dict[str, Any]) -> None:
        if not _OBJECT_KEY.fullmatch(object_key):
            raise ServiceError(
                "INVALID_OBJECT_REFERENCE", "The prediction object reference is invalid."
            )
        _, metadata, digest = self.read_prediction(object_key)
        if response.get("predictionSha256") != digest:
            raise ServiceError(
                "PREDICTION_INTEGRITY_FAILED",
                "The prediction response does not match the stored artifact.",
                409,
            )
        path = self.root / f"{object_key}.json"
        metadata["response"] = response
        encoded = (json.dumps(metadata, sort_keys=True, allow_nan=False) + "\n").encode()
        self._atomic_write(path, encoded)

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

    def read_request_response(self, request_id: str, input_sha256: str) -> dict[str, Any] | None:
        if not _REQUEST_ID.fullmatch(request_id):
            raise ServiceError("INVALID_REQUEST_ID", "The request identifier is invalid.")
        receipt_path = self.root / f".request-{request_id}.json"
        try:
            if receipt_path.is_symlink() or receipt_path.stat().st_size > 65536:
                raise OSError("Invalid idempotency receipt.")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise ServiceError(
                "REQUEST_RECEIPT_INVALID", "The request receipt is unavailable.", 409
            ) from error
        if not isinstance(receipt, dict) or receipt.get("inputSha256") != input_sha256:
            raise ServiceError(
                "IDEMPOTENCY_CONFLICT",
                "The request identifier was used for a different input volume.",
                409,
            )
        key = receipt.get("predictionObjectKey")
        _, _, digest = self.read_prediction(key if isinstance(key, str) else "")
        if receipt.get("predictionSha256") != digest:
            raise ServiceError(
                "PREDICTION_INTEGRITY_FAILED",
                "The stored request result failed integrity validation.",
                409,
            )
        response = receipt.get("response")
        if not isinstance(response, dict):
            raise ServiceError("REQUEST_RECEIPT_INVALID", "The request receipt is incomplete.", 409)
        return response

    def save_request_response(
        self,
        request_id: str,
        input_sha256: str,
        prediction_object_key: str,
        prediction_sha256: str,
        response: dict[str, Any],
    ) -> None:
        if not _REQUEST_ID.fullmatch(request_id):
            raise ServiceError("INVALID_REQUEST_ID", "The request identifier is invalid.")
        receipt_path = self.root / f".request-{request_id}.json"
        receipt = {
            "inputSha256": input_sha256,
            "predictionObjectKey": prediction_object_key,
            "predictionSha256": prediction_sha256,
            "response": response,
        }
        encoded = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode()
        self._atomic_write(receipt_path, encoded)

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
