import gzip
import hashlib
import json
import logging
import threading
from pathlib import Path

import nibabel as nib
import numpy as np
import onnx
from brainseg_inference.app import create_app
from brainseg_inference.logging import JsonFormatter, correlation_id
from brainseg_inference.settings import Settings
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from onnx import TensorProto, helper


class PositivePredictor:
    def predict(self, image: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.ones_like(image)


class SlowPredictor:
    def predict(self, image: NDArray[np.float32]) -> NDArray[np.float32]:
        threading.Event().wait(0.05)
        return np.ones_like(image)


def volume_bytes(data: NDArray[np.float32] | None = None) -> bytes:
    values = data if data is not None else np.arange(128, dtype=np.float32).reshape(8, 8, 2)
    return nib.Nifti1Image(values, np.eye(4)).to_bytes()


def test_unconfigured_model_is_alive_but_not_ready():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"
        assert client.get("/models").json()["models"] == []


def test_correlation_id_is_shared_by_header_and_payload():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/health", headers={"X-Correlation-Id": "research_request-123"})
        assert response.headers["X-Correlation-Id"] == "research_request-123"
        assert response.json()["correlationId"] == "research_request-123"
        replacement = client.get("/health", headers={"X-Correlation-Id": "unsafe id"})
        assert replacement.headers["X-Correlation-Id"] != "unsafe id"


def test_normal_segmentation_and_evaluation_are_typed_and_versioned():
    with TestClient(
        create_app(Settings(_env_file=None, model_version="synthetic-test"), PositivePredictor())
    ) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["modelVersion"] == "synthetic-test"
        assert result["preprocessingVersion"] == "flair-v1"
        assert result["threshold"] == 0.5
        assert len(result["mask"]) == 256 and len(result["mask"][0]) == 256
        assert result["tumorAreaPixels"] == 256 * 256
        assert result["inputSha256"] == hashlib.sha256(volume_bytes()).hexdigest()
        assert "Not for clinical diagnosis" in result["disclaimer"]
        assert result["timings"]["inferenceMilliseconds"] >= 0
        evaluation = client.post(
            "/v1/evaluate",
            files={
                "file": ("fixture.nii", volume_bytes(), "application/octet-stream"),
                "label": (
                    "labels.nii",
                    volume_bytes(np.full((8, 8, 2), 4, dtype=np.float32)),
                    "application/octet-stream",
                ),
            },
        )
        assert evaluation.status_code == 200
        assert evaluation.json()["sliceMetrics"]["dice"] == 1
        assert evaluation.json()["metricLevel"] == "slice"


def test_invalid_file_and_numeric_values_return_safe_errors():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        invalid_type = client.post(
            "/v1/segment", files={"file": ("fixture.txt", b"invalid", "text/plain")}
        )
        assert invalid_type.json()["error"]["code"] == "INVALID_FILE_TYPE"
        invalid_file = client.post(
            "/v1/segment", files={"file": ("fixture.nii", b"invalid", "application/octet-stream")}
        )
        assert invalid_file.status_code == 400
        assert invalid_file.json()["error"]["code"] == "INVALID_NIFTI"
        values = np.zeros((8, 8, 2), dtype=np.float32)
        values[0, 0, 0] = np.nan
        invalid_values = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(values), "application/octet-stream")},
        )
        assert invalid_values.json()["error"]["code"] == "INVALID_NUMERIC_RANGE"
        assert "Traceback" not in invalid_values.text


def test_upload_and_decompression_limits():
    with TestClient(create_app(Settings(_env_file=None, max_upload_bytes=2))) as client:
        response = client.post(
            "/v1/segment", files={"file": ("fixture.nii", b"123", "application/octet-stream")}
        )
        assert response.status_code == 413
    with TestClient(create_app(Settings(_env_file=None, max_decompressed_bytes=100))) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii.gz", gzip.compress(volume_bytes()), "application/gzip")},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "VOLUME_TOO_LARGE"


def test_valid_input_cannot_run_without_a_model():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_NOT_READY"


def test_deadline_and_invalid_slice_index():
    with TestClient(
        create_app(Settings(_env_file=None, request_timeout_seconds=0.01), SlowPredictor())
    ) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "INFERENCE_TIMEOUT"
        invalid_slice = client.post(
            "/v1/segment",
            data={"slice_index": "5"},
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert invalid_slice.json()["error"]["code"] == "SLICE_OUT_OF_RANGE"


def test_model_hash_failure_keeps_diagnostics_available(tmp_path: Path):
    model = tmp_path / "synthetic.onnx"
    model.write_bytes(b"invalid model")
    settings = Settings(_env_file=None, model_path=model, model_sha256="0" * 64)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_HASH_MISMATCH"
        assert str(tmp_path) not in response.text


def test_verified_onnx_model_loads_and_runs_on_cpu(tmp_path: Path):
    shape = [1, 1, 256, 256]
    graph = helper.make_graph(
        [helper.make_node("Identity", ["image"], ["logits"])],
        "synthetic-contract-fixture",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, shape)],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, shape)],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 20)])
    model.ir_version = 9
    path = tmp_path / "synthetic.onnx"
    onnx.save(model, path)
    settings = Settings(
        _env_file=None, model_path=path, model_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 200
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 200
        assert len(response.json()["mask"]) == 256


def test_openapi_contains_all_required_endpoints():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        schema = client.get("/openapi.json").json()
        assert {"/health", "/ready", "/models", "/v1/segment", "/v1/evaluate"} <= schema[
            "paths"
        ].keys()
        assert "Not for clinical diagnosis" in schema["info"]["description"]


def test_json_logs_have_shared_correlation_field_and_exclude_raw_content():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "request_completed", (), None)
    record.__dict__["body"] = "synthetic-private-content"
    record.__dict__["access_token"] = "synthetic-token"
    token = correlation_id.set("research-log-123")
    try:
        encoded = JsonFormatter().format(record)
    finally:
        correlation_id.reset(token)
    payload = json.loads(encoded)
    assert payload["CorrelationId"] == "research-log-123"
    assert payload["service"] == "ml-inference"
    assert "synthetic-private-content" not in encoded
    assert "synthetic-token" not in encoded
