import gzip
import hashlib
import json
import logging
import threading
import time
from pathlib import Path

import nibabel as nib
import numpy as np
import onnx
import pytest
from brainseg_inference.app import create_app
from brainseg_inference.errors import ServiceError
from brainseg_inference.logging import JsonFormatter, correlation_id
from brainseg_inference.manifest import ModelManifest
from brainseg_inference.runtime import OnnxPredictor
from brainseg_inference.settings import Settings
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from onnx import TensorProto, helper


class PositivePredictor:
    batch_size = 8

    def predict_batch(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        return np.ones_like(images), 0.0


class SlowPredictor:
    batch_size = 8

    def predict_batch(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        started = time.perf_counter()
        threading.Event().wait(0.05)
        return np.ones_like(images), (time.perf_counter() - started) * 1000


class EmptyPredictor:
    batch_size = 8

    def predict_batch(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        return np.full_like(images, -100), 0.0


def volume_bytes(
    data: NDArray[np.float32] | None = None,
    affine: NDArray[np.float64] | None = None,
) -> bytes:
    values = data if data is not None else np.arange(240, dtype=np.float32).reshape(8, 10, 3)
    header = nib.Nifti1Header()
    header.set_xyzt_units("mm")
    image = nib.Nifti1Image(values, affine if affine is not None else np.diag([0.7, 0.8, 2.0, 1]))
    image.header.set_xyzt_units("mm")
    image.set_qform(image.affine, code=1)
    image.set_sform(image.affine, code=1)
    return image.to_bytes()


def test_unconfigured_model_is_alive_but_not_ready(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_MANIFEST_NOT_CONFIGURED"
        assert client.get("/models").json()["models"] == []


def test_correlation_id_is_shared_by_header_and_payload(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"X-Correlation-Id": "research_request-123"})
        assert response.headers["X-Correlation-Id"] == "research_request-123"
        assert response.json()["correlationId"] == "research_request-123"
        replacement = client.get("/health", headers={"X-Correlation-Id": "unsafe id"})
        assert replacement.headers["X-Correlation-Id"] != "unsafe id"


def test_full_volume_segmentation_round_trips_original_shape_and_space(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        object_storage_path=tmp_path,
        model_manifest_path=None,
    )
    with TestClient(create_app(settings, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment",
            headers={"X-Correlation-Id": "volume-request-1"},
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["modelVersion"] == "synthetic-test"
        assert result["artifactKind"] == "synthetic_test"
        assert result["preprocessingVersion"] == "flair-v1"
        assert result["threshold"] == 0.5
        assert result["correlationId"] == "volume-request-1"
        assert result["maskShape"] == [8, 10, 3]
        assert result["space"] == "original"
        assert "patientMetrics" not in result and "dice" not in result
        assert (
            result["predictionSha256"]
            == hashlib.sha256((tmp_path / result["predictionObjectKey"]).read_bytes()).hexdigest()
        )
        assert {path.name for path in tmp_path.iterdir()} == {
            result["predictionObjectKey"],
            f"{result['predictionObjectKey']}.json",
        }
        artifact_metadata = json.loads(
            (tmp_path / f"{result['predictionObjectKey']}.json").read_text(encoding="utf-8")
        )
        assert artifact_metadata["modelManifestSha256"] is None
        assert artifact_metadata["artifactKind"] == "synthetic_test"
        assert result["tumorAreaPixels"] == 8 * 10 * 3
        assert "Not for clinical diagnosis" in result["disclaimer"]
        assert result["timings"]["inferenceMilliseconds"] >= 0

        with gzip.open(tmp_path / result["predictionObjectKey"], "rb") as stream:
            mask_image = nib.Nifti1Image.from_bytes(stream.read())
        assert mask_image.shape == (8, 10, 3)
        assert np.allclose(mask_image.affine, np.diag([0.7, 0.8, 2.0, 1]))
        assert nib.aff2axcodes(mask_image.affine) == ("R", "A", "S")
        assert np.isin(mask_image.get_fdata(), [0, 1]).all()


def test_gzip_nifti_is_accepted_for_full_volume_inference(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment",
            files={
                "file": (
                    "fixture.nii.gz",
                    gzip.compress(volume_bytes()),
                    "application/gzip",
                )
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["maskShape"] == [8, 10, 3]


def test_evaluate_requires_traceable_prediction_and_reports_patient_and_slice_metrics(
    tmp_path: Path,
):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    source = volume_bytes()
    truth = volume_bytes(np.full((8, 10, 3), 4, dtype=np.float32))
    with TestClient(create_app(settings, PositivePredictor())) as client:
        segmentation = client.post(
            "/v1/segment",
            files={"file": ("source.nii", source, "application/octet-stream")},
        ).json()
        response = client.post(
            "/v1/evaluate",
            data={"predictionObjectKey": segmentation["predictionObjectKey"]},
            files={
                "file": ("source.nii", source, "application/octet-stream"),
                "label": ("labels.nii", truth, "application/octet-stream"),
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["evaluationProtocol"] == "whole-tumor-v1"
        assert result["artifactKind"] == "synthetic_test"
        assert result["patientMetrics"]["dice"] == 1
        assert result["sliceMacroMetrics"]["dice"] == 1
        assert result["sliceCount"] == 3
        assert result["groundTruthSha256"] == hashlib.sha256(truth).hexdigest()


def test_empty_masks_have_defined_metrics(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    zeros = volume_bytes(np.zeros((8, 10, 3), dtype=np.float32))
    with TestClient(create_app(settings, EmptyPredictor())) as client:
        segmentation = client.post(
            "/v1/segment",
            files={"file": ("source.nii", zeros, "application/octet-stream")},
        ).json()
        evaluation = client.post(
            "/v1/evaluate",
            data={"predictionObjectKey": segmentation["predictionObjectKey"]},
            files={
                "file": ("source.nii", zeros, "application/octet-stream"),
                "label": ("labels.nii", zeros, "application/octet-stream"),
            },
        )
        assert evaluation.status_code == 200
        assert evaluation.json()["patientMetrics"] == {
            "dice": 1,
            "iou": 1,
            "precision": 1,
            "recall": 1,
        }


def test_evaluate_rejects_spatial_mismatch_and_unrelated_source(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    source = volume_bytes()
    with TestClient(create_app(settings, PositivePredictor())) as client:
        segmentation = client.post(
            "/v1/segment",
            files={"file": ("source.nii", source, "application/octet-stream")},
        ).json()
        shifted_affine = np.diag([0.7, 0.8, 2.0, 1])
        shifted_affine[0, 3] = 4
        different_spacing = np.diag([0.9, 0.8, 2.0, 1])
        different_direction = np.diag([-0.7, 0.8, 2.0, 1])
        invalid_labels = (
            volume_bytes(np.full((8, 10, 3), 4, dtype=np.float32), shifted_affine),
            volume_bytes(np.full((8, 10, 3), 4, dtype=np.float32), different_spacing),
            volume_bytes(np.full((8, 10, 3), 4, dtype=np.float32), different_direction),
            volume_bytes(np.full((8, 10, 2), 4, dtype=np.float32)),
        )
        for invalid_label in invalid_labels:
            mismatch = client.post(
                "/v1/evaluate",
                data={"predictionObjectKey": segmentation["predictionObjectKey"]},
                files={
                    "file": ("source.nii", source, "application/octet-stream"),
                    "label": ("labels.nii", invalid_label, "application/octet-stream"),
                },
            )
            assert mismatch.status_code == 400
            assert mismatch.json()["error"]["code"] == "LABEL_ALIGNMENT_INVALID"
        unrelated = volume_bytes(np.ones((8, 10, 3), dtype=np.float32))
        bad_source = client.post(
            "/v1/evaluate",
            data={"predictionObjectKey": segmentation["predictionObjectKey"]},
            files={
                "file": ("different.nii", unrelated, "application/octet-stream"),
                "label": (
                    "labels.nii",
                    volume_bytes(np.ones((8, 10, 3), dtype=np.float32)),
                    "application/octet-stream",
                ),
            },
        )
        assert bad_source.status_code == 409
        assert bad_source.json()["error"]["code"] == "PREDICTION_SOURCE_MISMATCH"


def test_invalid_type_nifti_and_values_return_safe_errors(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings, PositivePredictor())) as client:
        invalid_type = client.post(
            "/v1/segment", files={"file": ("fixture.txt", b"invalid", "text/plain")}
        )
        assert invalid_type.json()["error"]["code"] == "INVALID_FILE_TYPE"
        invalid_file = client.post(
            "/v1/segment", files={"file": ("fixture.nii", b"invalid", "application/octet-stream")}
        )
        assert invalid_file.status_code == 400
        assert invalid_file.json()["error"]["code"] == "INVALID_NIFTI"
        values = np.zeros((8, 10, 3), dtype=np.float32)
        values[0, 0, 0] = np.nan
        invalid_values = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(values), "application/octet-stream")},
        )
        assert invalid_values.json()["error"]["code"] == "INVALID_NUMERIC_RANGE"
        assert "Traceback" not in invalid_values.text


def test_non_axial_axis_order_is_rejected_without_reorientation(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    affine = np.array(
        [
            [0, 0, 2.0, 0],
            [0, 0.8, 0, 0],
            [0.7, 0, 0, 0],
            [0, 0, 0, 1],
        ]
    )
    with TestClient(create_app(settings, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment",
            files={
                "file": (
                    "non-axial.nii",
                    volume_bytes(np.zeros((8, 10, 3), dtype=np.float32), affine),
                    "application/octet-stream",
                )
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_ORIENTATION"


def test_upload_decompression_and_dimension_limits(tmp_path: Path):
    upload_limited = Settings(
        _env_file=None, max_upload_bytes=2, object_storage_path=tmp_path / "upload"
    )
    with TestClient(create_app(upload_limited, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment", files={"file": ("fixture.nii", b"123", "application/octet-stream")}
        )
        assert response.status_code == 413
    expanded_limited = Settings(
        _env_file=None,
        max_decompressed_bytes=100,
        object_storage_path=tmp_path / "expanded",
    )
    with TestClient(create_app(expanded_limited, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment",
            files={
                "file": (
                    "fixture.nii.gz",
                    gzip.compress(volume_bytes()),
                    "application/gzip",
                )
            },
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "VOLUME_TOO_LARGE"
    dimension_limited = Settings(
        _env_file=None,
        max_volume_dimension=7,
        object_storage_path=tmp_path / "dimensions",
    )
    with TestClient(create_app(dimension_limited, PositivePredictor())) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.json()["error"]["code"] == "INVALID_DIMENSIONS"


def test_valid_input_cannot_run_without_a_model(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_NOT_READY"


def test_deadline_is_enforced_and_prediction_reference_is_not_a_path(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        object_storage_path=tmp_path,
        request_timeout_seconds=0.01,
    )
    with TestClient(create_app(settings, SlowPredictor())) as client:
        response = client.post(
            "/v1/segment",
            files={"file": ("fixture.nii", volume_bytes(), "application/octet-stream")},
        )
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "INFERENCE_TIMEOUT"
        invalid_ref = client.post(
            "/v1/evaluate",
            data={"predictionObjectKey": "C:\\unsafe\\mask.nii.gz"},
            files={
                "file": ("source.nii", volume_bytes(), "application/octet-stream"),
                "label": (
                    "labels.nii",
                    volume_bytes(np.zeros((8, 10, 3), dtype=np.float32)),
                    "application/octet-stream",
                ),
            },
        )
        assert invalid_ref.status_code == 400
        assert invalid_ref.json()["error"]["code"] == "INVALID_OBJECT_REFERENCE"


def _write_manifest(directory: Path, weight_bytes: bytes, **overrides: object) -> Path:
    path = directory / "model-manifest.yaml"
    values: dict[str, object] = {
        "manifestVersion": 1,
        "modelVersion": "synthetic-fixture",
        "architecture": "UNet",
        "preprocessingVersion": "flair-v1",
        "inputSize": 256,
        "threshold": 0.5,
        "weightFile": "model.onnx",
        "weightSha256": hashlib.sha256(weight_bytes).hexdigest(),
        "artifactKind": "synthetic_test",
    }
    values.update(overrides)
    (directory / "model.onnx").write_bytes(weight_bytes)
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_manifest_weight_hash_failure_and_test_artifact_are_never_ready(tmp_path: Path):
    model_path = _write_manifest(tmp_path, b"synthetic-only")
    manifest = json.loads(model_path.read_text(encoding="utf-8"))
    manifest["weightSha256"] = "0" * 64
    model_path.write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        _env_file=None,
        model_manifest_path=model_path,
        object_storage_path=tmp_path / "objects",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_HASH_MISMATCH"

    manifest["weightSha256"] = hashlib.sha256(b"synthetic-only").hexdigest()
    model_path.write_text(json.dumps(manifest), encoding="utf-8")
    with TestClient(create_app(settings)) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "TEST_ARTIFACT_NOT_ALLOWED"


def test_onnx_test_fixture_metadata_contract_is_explicitly_synthetic(tmp_path: Path):
    graph = helper.make_graph(
        [helper.make_node("Identity", ["image"], ["logits"])],
        "synthetic-contract-fixture",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 1, 256, 256])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 1, 256, 256])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 20)])
    model.ir_version = 9
    for key, value in {
        "brainseg.architecture": "UNet",
        "brainseg.preprocessing_version": "flair-v1",
        "brainseg.input_size": "256",
        "brainseg.threshold": "0.5",
    }.items():
        entry = model.metadata_props.add()
        entry.key, entry.value = key, value
    model_path = tmp_path / "synthetic-fixture.onnx"
    onnx.save(model, model_path)
    manifest = ModelManifest.model_validate(
        {
            "manifestVersion": 1,
            "modelVersion": "synthetic-fixture",
            "architecture": "UNet",
            "preprocessingVersion": "flair-v1",
            "inputSize": 256,
            "threshold": 0.5,
            "weightFile": model_path.name,
            "weightSha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "artifactKind": "synthetic_test",
        }
    )
    predictor = OnnxPredictor(
        str(model_path),
        manifest,
        Settings(_env_file=None, object_storage_path=tmp_path / "objects"),
    )
    output, _ = predictor.predict_batch(np.zeros((1, 256, 256), dtype=np.float32))
    assert output.shape == (1, 256, 256)
    assert manifest.artifact_kind == "synthetic_test"


@pytest.mark.parametrize(
    ("metadata", "error_code"),
    [
        (
            {
                "brainseg.architecture": "AttentionUNet",
                "brainseg.preprocessing_version": "flair-v1",
                "brainseg.input_size": "256",
                "brainseg.threshold": "0.5",
            },
            "MODEL_ARCHITECTURE_MISMATCH",
        ),
        (
            {
                "brainseg.architecture": "UNet",
                "brainseg.preprocessing_version": "flair-v2",
                "brainseg.input_size": "256",
                "brainseg.threshold": "0.5",
            },
            "PREPROCESSING_VERSION_MISMATCH",
        ),
        (
            {
                "brainseg.architecture": "UNet",
                "brainseg.preprocessing_version": "flair-v1",
                "brainseg.input_size": "128",
                "brainseg.threshold": "0.5",
            },
            "INPUT_SIZE_MISMATCH",
        ),
        (
            {
                "brainseg.architecture": "UNet",
                "brainseg.preprocessing_version": "flair-v1",
                "brainseg.input_size": "256",
                "brainseg.threshold": "0.6",
            },
            "MODEL_THRESHOLD_MISMATCH",
        ),
    ],
)
def test_model_metadata_mismatches_fail_closed(metadata: dict[str, str], error_code: str):
    manifest = ModelManifest.model_validate(
        {
            "manifestVersion": 1,
            "modelVersion": "synthetic-fixture",
            "architecture": "UNet",
            "preprocessingVersion": "flair-v1",
            "inputSize": 256,
            "threshold": 0.5,
            "weightFile": "synthetic.onnx",
            "weightSha256": "0" * 64,
            "artifactKind": "synthetic_test",
        }
    )
    with pytest.raises(ServiceError) as raised:
        OnnxPredictor._check_metadata(metadata, manifest)
    assert raised.value.code == error_code


def test_openapi_declares_contract_and_all_required_routes(tmp_path: Path):
    settings = Settings(_env_file=None, object_storage_path=tmp_path)
    with TestClient(create_app(settings)) as client:
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]
        assert {"/health", "/ready", "/models", "/v1/segment", "/v1/evaluate"} <= paths.keys()
        assert "SegmentationResponse" in schema["components"]["schemas"]
        assert "EvaluationResponse" in schema["components"]["schemas"]
        assert "ErrorResponse" in schema["components"]["schemas"]
        assert "503" in schema["paths"]["/ready"]["get"]["responses"]
        assert "504" in schema["paths"]["/v1/segment"]["post"]["responses"]
        assert "Not for clinical diagnosis" in schema["info"]["description"]


def test_json_logs_have_shared_correlation_and_exclude_raw_content():
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
