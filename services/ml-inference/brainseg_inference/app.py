import asyncio
import gzip
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

import nibabel as nib
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from training import DISCLAIMER
from training.metrics import BinaryMetrics, binary_metrics, macro_metrics
from training.preprocessing import normalize_volume, prepare_axial_context, whole_tumor_mask
from training.reconstruct_volume import reconstruct_volume
from training.uncertainty import brats_retention_metrics, calibration_metrics, uncertainty_to_uint8

from brainseg_inference.errors import ServiceError, error_response
from brainseg_inference.inputs import VolumeInput, ensure_same_geometry, parse_volume, read_volume
from brainseg_inference.logging import configure_logging, correlation_id
from brainseg_inference.runtime import ModelRuntime, Predictor
from brainseg_inference.settings import Settings
from brainseg_inference.storage import LocalObjectStorage

EVALUATION_PROTOCOL = "whole-tumor-v1"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Timings(APIModel):
    preprocessingMilliseconds: float
    inferenceMilliseconds: float
    postprocessingMilliseconds: float


class SegmentationResponse(APIModel):
    modelVersion: str
    architecture: str
    artifactKind: str
    preprocessingVersion: str
    inputSize: int
    threshold: float
    correlationId: str
    requestId: str
    inputSha256: str
    weightSha256: str | None
    modelManifestSha256: str | None
    predictionObjectKey: str
    predictionSha256: str
    maskShape: list[int]
    space: str = "original"
    tumorAreaPixels: int
    tumorAreaRatio: float
    inputMode: str = "2d"
    contextSlices: int = 1
    sliceFusion: str = "stack"
    boundaryHead: bool = False
    deepSupervision: bool = False
    memberWeightHashes: list[str] = Field(default_factory=list)
    probabilityArtifact: str | None = None
    probabilitySha256: str | None = None
    boundaryArtifact: str | None = None
    boundarySha256: str | None = None
    uncertaintyArtifact: str | None = None
    uncertaintySha256: str | None = None
    modelVarianceArtifact: str | None = None
    modelVarianceSha256: str | None = None
    ensembleSize: int = 1
    meanUncertainty: float | None = None
    p95Uncertainty: float | None = None
    timings: Timings
    disclaimer: str = DISCLAIMER


class ModelInfo(APIModel):
    modelVersion: str
    architecture: str
    artifactKind: str
    preprocessingVersion: str
    inputSize: int
    threshold: float
    inputMode: str = "2d"
    contextSlices: int = 1
    sliceFusion: str = "stack"
    boundaryHead: bool = False
    deepSupervision: bool = False
    ensembleSize: int = 1
    uncertaintyEnabled: bool = False
    memberWeightHashes: list[str] = Field(default_factory=list)


class ModelsResponse(APIModel):
    models: list[ModelInfo]
    ready: bool
    errorCode: str | None
    correlationId: str
    disclaimer: str = DISCLAIMER


class HealthResponse(APIModel):
    status: str
    modelReady: bool
    correlationId: str


class ReadyResponse(APIModel):
    status: str
    modelVersion: str
    correlationId: str


class EvaluationResponse(APIModel):
    modelVersion: str
    architecture: str
    artifactKind: str
    preprocessingVersion: str
    evaluationProtocol: str
    threshold: float
    weightSha256: str | None
    modelManifestSha256: str | None
    requestId: str
    correlationId: str
    inputSha256: str
    groundTruthSha256: str
    predictionObjectKey: str
    predictionSha256: str
    patientMetrics: BinaryMetrics
    sliceMacroMetrics: BinaryMetrics
    sliceCount: int
    calibrationMetrics: dict[str, Any] | None = None
    uncertaintyRetentionMetrics: list[dict[str, float | int | None]] | None = None
    disclaimer: str = DISCLAIMER


class ErrorDetail(APIModel):
    code: str
    message: str


class ErrorResponse(APIModel):
    error: ErrorDetail
    correlationId: str


ERROR_RESPONSES = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        400: "Invalid input or unsupported evaluation protocol.",
        404: "The referenced prediction artifact is unavailable.",
        409: "Artifact integrity or spatial alignment conflict.",
        413: "Input exceeds the configured resource limit.",
        422: "The request does not match the OpenAPI contract.",
        503: "The verified model is not ready.",
        504: "Model inference exceeded its deadline.",
        500: "Inference or prediction persistence failed.",
    }.items()
}


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise ServiceError("UPLOAD_TOO_LARGE", "The request exceeds the size limit.", 413)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except ServiceError as error:
            await error_response(error)(scope, receive, send)


def _same_geometry_metadata(first: dict[str, Any], second: dict[str, Any]) -> bool:
    keys = ("shape", "axisCodes", "spatialUnit", "qformCode", "sformCode")
    if any(first.get(key) != second.get(key) for key in keys):
        return False
    try:
        numeric_matches = all(
            np.allclose(
                np.asarray(first[key]),
                np.asarray(second[key]),
                rtol=0,
                atol=1e-5,
            )
            for key in ("affine", "voxelSpacing")
        )
        forms_match = all(
            (first[key] is None and second[key] is None)
            or (
                first[key] is not None
                and second[key] is not None
                and np.allclose(first[key], second[key], rtol=0, atol=1e-5)
            )
            for key in ("qform", "sform")
        )
        return numeric_matches and forms_match
    except (KeyError, TypeError, ValueError):
        return False


def _serialize_mask(mask: np.ndarray, volume: VolumeInput) -> bytes:
    return _serialize_volume(mask.astype(np.uint8), volume)


def _serialize_volume(array: np.ndarray, volume: VolumeInput) -> bytes:
    if array.shape != volume.volume.shape or not np.isfinite(array).all():
        raise ServiceError(
            "RECONSTRUCTION_FAILED", "An output could not be restored to input space.", 500
        )
    header = volume.header.copy()
    header.set_data_dtype(array.dtype)
    header.set_slope_inter(1.0, 0.0)
    header["descrip"] = b""
    header["aux_file"] = b""
    header["intent_name"] = b""
    header.extensions.clear()
    image = nib.Nifti1Image(array, volume.affine, header=header)
    qform = volume.geometry["qform"]
    sform = volume.geometry["sform"]
    image.set_qform(qform, code=volume.geometry["qformCode"])
    image.set_sform(sform, code=volume.geometry["sformCode"])
    return gzip.compress(image.to_bytes(), mtime=0)


def _reconstruct_scalar_volume(
    slices: np.ndarray, original_shape: tuple[int, int, int]
) -> np.ndarray:
    if slices.shape[0] != original_shape[2] or slices.ndim != 3:
        raise ValueError("A scalar output is required for every axial slice.")
    output = np.empty(original_shape, dtype=np.float32)
    for index, values in enumerate(slices):
        output[:, :, index] = np.asarray(
            Image.fromarray(values.astype(np.float32)).resize(
                (original_shape[1], original_shape[0]), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
    return output


def create_app(settings: Settings | None = None, predictor: Predictor | None = None) -> FastAPI:
    settings = settings or Settings()
    runtime = ModelRuntime(settings, predictor)
    storage = LocalObjectStorage(settings.object_storage_path, settings.max_upload_bytes)
    logger = configure_logging()
    request_lock = asyncio.Lock()

    async def require_service_auth(request: Request) -> None:
        expected = settings.service_api_key
        if not expected:
            raise ServiceError(
                "SERVICE_AUTH_NOT_CONFIGURED",
                "Service authentication is not configured.",
                503,
            )
        supplied = request.headers.get("Authorization", "")
        if not supplied.startswith("Bearer ") or not secrets.compare_digest(supplied[7:], expected):
            raise ServiceError("SERVICE_AUTH_REQUIRED", "Service authentication is required.", 401)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime.load()
        application.state.model_runtime = runtime
        yield
        runtime.close()

    application = FastAPI(
        title="BrainSeg Inference API",
        version="0.2.0",
        description=DISCLAIMER,
        lifespan=lifespan,
    )
    application.add_middleware(
        RequestSizeLimitMiddleware, max_bytes=settings.max_upload_bytes * 2 + 65536
    )

    @application.middleware("http")
    async def correlate(request: Request, call_next):
        candidate = request.headers.get("X-Correlation-Id", "")
        identifier = (
            candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid.uuid4().hex
        )
        token = correlation_id.set(identifier)
        request.state.correlation_id = identifier
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                logger.error(
                    "request_failed",
                    extra={
                        "errorCode": "INTERNAL_ERROR",
                        "diagnosticType": type(error).__name__,
                    },
                )
                response = error_response(
                    ServiceError("INTERNAL_ERROR", "The request could not be completed.", 500)
                )
            response.headers["X-Correlation-Id"] = identifier
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "statusCode": response.status_code,
                    "durationMilliseconds": round((time.perf_counter() - started) * 1000, 3),
                },
            )
            return response
        finally:
            correlation_id.reset(token)

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        response = error_response(error)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        logger.info(
            "request_validation_failed",
            extra={"errorCode": "VALIDATION_ERROR", "diagnosticType": type(error).__name__},
        )
        return await service_error(
            request, ServiceError("VALIDATION_ERROR", "The request fields are invalid.", 422)
        )

    @application.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok", modelReady=runtime.ready, correlationId=correlation_id.get()
        )

    @application.get(
        "/ready",
        response_model=ReadyResponse,
        responses={503: ERROR_RESPONSES[503]},
        tags=["Health"],
    )
    async def ready() -> ReadyResponse:
        if not runtime.ready or runtime.model_version is None:
            raise ServiceError(
                runtime.error_code or "MODEL_NOT_READY",
                "No verified model is available.",
                503,
            )
        return ReadyResponse(
            status="ready",
            modelVersion=runtime.model_version,
            correlationId=correlation_id.get(),
        )

    @application.get("/models", response_model=ModelsResponse, tags=["Models"])
    async def models() -> ModelsResponse:
        available = []
        if runtime.ready:
            model_version = runtime.model_version
            architecture = runtime.architecture
            artifact_kind = runtime.artifact_kind
            preprocessing_version = runtime.preprocessing_version
            threshold = runtime.threshold
            if (
                model_version is None
                or architecture is None
                or artifact_kind is None
                or preprocessing_version is None
                or threshold is None
            ):
                raise ServiceError("MODEL_NOT_READY", "No verified model is available.", 503)
            available.append(
                ModelInfo(
                    modelVersion=model_version,
                    architecture=architecture,
                    artifactKind=artifact_kind,
                    preprocessingVersion=preprocessing_version,
                    inputSize=256,
                    threshold=threshold,
                    inputMode=runtime.input_mode,
                    contextSlices=runtime.context_slices,
                    sliceFusion=runtime.slice_fusion,
                    boundaryHead=runtime.boundary_head,
                    deepSupervision=runtime.deep_supervision,
                    ensembleSize=runtime.ensemble_size,
                    uncertaintyEnabled=runtime.uncertainty_enabled,
                    memberWeightHashes=runtime.member_weight_hashes,
                )
            )
        return ModelsResponse(
            models=available,
            ready=runtime.ready,
            errorCode=runtime.error_code,
            correlationId=correlation_id.get(),
        )

    async def segment_volume(volume: VolumeInput, request_id: str) -> SegmentationResponse:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            raise ServiceError("INVALID_REQUEST_ID", "The request identifier is invalid.")
        async with request_lock:
            saved_response = storage.read_request_response(request_id, volume.sha256)
            if saved_response is not None:
                return SegmentationResponse.model_validate(saved_response)
            saved_response = storage.read_prediction_response(request_id, volume.sha256)
            if saved_response is not None:
                replay = SegmentationResponse.model_validate(saved_response)
                storage.save_request_response(
                    request_id,
                    volume.sha256,
                    replay.predictionObjectKey,
                    replay.predictionSha256,
                    replay.model_dump(mode="json"),
                )
                return replay
            return await _segment_volume(volume, request_id)

    async def _segment_volume(volume: VolumeInput, request_id: str) -> SegmentationResponse:
        model_version = runtime.model_version
        architecture = runtime.architecture
        artifact_kind = runtime.artifact_kind
        preprocessing_version = runtime.preprocessing_version
        threshold = runtime.threshold
        if (
            not runtime.ready
            or model_version is None
            or architecture is None
            or artifact_kind is None
            or preprocessing_version is None
            or threshold is None
        ):
            raise ServiceError("MODEL_NOT_READY", "No verified model is available.", 503)
        started = time.perf_counter()
        normalized = normalize_volume(volume.volume)
        slices = np.stack(
            [
                prepare_axial_context(
                    normalized,
                    index,
                    256,
                    runtime.context_slices,
                )
                for index in range(volume.volume.shape[2])
            ]
        ).astype(np.float32, copy=False)
        preprocessed = time.perf_counter()
        prediction = await runtime.predict_outputs(slices)
        inferred = time.perf_counter()
        probabilities = prediction.mean_probability
        if (
            probabilities.shape != (volume.volume.shape[2], 256, 256)
            or not np.isfinite(probabilities).all()
            or np.any((probabilities < 0) | (probabilities > 1))
        ):
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        masks = (probabilities >= threshold).astype(np.uint8)
        predictions = {index: mask for index, mask in enumerate(masks)}
        reconstructed = reconstruct_volume(predictions, tuple(volume.volume.shape))
        if reconstructed.shape != volume.volume.shape:
            raise ServiceError(
                "RECONSTRUCTION_FAILED", "The prediction could not be restored to input space.", 500
            )
        probability_volume: np.ndarray | None = None
        boundary_volume: np.ndarray | None = None
        uncertainty_volume: np.ndarray | None = None
        model_variance_volume: np.ndarray | None = None
        if runtime.optional_artifacts_enabled:
            probability_volume = _reconstruct_scalar_volume(
                probabilities, tuple(volume.volume.shape)
            )
        if prediction.boundary_probability is not None:
            if (
                prediction.boundary_probability.shape != probabilities.shape
                or not np.isfinite(prediction.boundary_probability).all()
                or np.any(
                    (prediction.boundary_probability < 0) | (prediction.boundary_probability > 1)
                )
            ):
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The boundary output contract is invalid.", 500
                )
            boundary_masks = (prediction.boundary_probability >= 0.5).astype(np.uint8)
            boundary_volume = reconstruct_volume(
                {index: mask for index, mask in enumerate(boundary_masks)},
                tuple(volume.volume.shape),
            )
        elif runtime.boundary_head:
            raise ServiceError(
                "MODEL_OUTPUT_INVALID", "The declared boundary output is missing.", 500
            )
        if prediction.model_variance is not None:
            if (
                prediction.model_variance.shape != probabilities.shape
                or not np.isfinite(prediction.model_variance).all()
                or np.any(prediction.model_variance < 0)
                or np.any(prediction.model_variance > 0.25)
            ):
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The ensemble variance output is invalid.", 500
                )
            model_variance_volume = _reconstruct_scalar_volume(
                prediction.model_variance, tuple(volume.volume.shape)
            )
        if runtime.uncertainty_enabled:
            scale = runtime.uncertainty_scale_max
            if scale is None:
                raise ServiceError(
                    "MODEL_MANIFEST_INVALID",
                    "The uncertainty scale is unavailable.",
                    503,
                )
            uncertainty_slices = uncertainty_to_uint8(prediction.predictive_entropy, scale)
            uncertainty_volume = _reconstruct_scalar_volume(
                uncertainty_slices.astype(np.float32) / 100,
                tuple(volume.volume.shape),
            )
            uncertainty_volume = np.rint(np.clip(uncertainty_volume, 0, 1) * 100).astype(np.uint8)
        manifest = runtime.manifest
        artifact_metadata = {
            "modelVersion": model_version,
            "architecture": architecture,
            "artifactKind": artifact_kind,
            "preprocessingVersion": preprocessing_version,
            "threshold": threshold,
            "evaluationProtocol": EVALUATION_PROTOCOL,
            "inputSha256": volume.sha256,
            "geometry": volume.geometry,
            "modelManifestSha256": runtime.manifest_sha256,
            "modelWeightSha256": manifest.weight_sha256 if manifest else None,
            "memberWeightHashes": runtime.member_weight_hashes,
            "inputMode": runtime.input_mode,
            "contextSlices": runtime.context_slices,
            "sliceFusion": runtime.slice_fusion,
            "boundaryHead": runtime.boundary_head,
            "deepSupervision": runtime.deep_supervision,
            "ensembleSize": runtime.ensemble_size,
            "uncertaintyMethod": (
                manifest.uncertainty_method if manifest and runtime.uncertainty_enabled else None
            ),
            "correlationId": correlation_id.get(),
            "requestId": request_id,
        }
        try:
            probability_artifact = (
                storage.put_auxiliary(
                    _serialize_volume(probability_volume.astype(np.float32), volume),
                    artifact_metadata,
                    "probability",
                )
                if probability_volume is not None
                else None
            )
            boundary_artifact = (
                storage.put_auxiliary(
                    _serialize_volume(boundary_volume.astype(np.uint8), volume),
                    artifact_metadata,
                    "boundary",
                )
                if boundary_volume is not None
                else None
            )
            uncertainty_artifact = (
                storage.put_auxiliary(
                    _serialize_volume(uncertainty_volume.astype(np.uint8), volume),
                    artifact_metadata,
                    "uncertainty",
                )
                if uncertainty_volume is not None
                else None
            )
            model_variance_artifact = (
                storage.put_auxiliary(
                    _serialize_volume(model_variance_volume.astype(np.float32), volume),
                    artifact_metadata,
                    "model_variance",
                )
                if model_variance_volume is not None
                else None
            )
            artifact_metadata["probabilityObjectKey"] = (
                probability_artifact.object_key if probability_artifact else None
            )
            artifact_metadata["probabilitySha256"] = (
                probability_artifact.sha256 if probability_artifact else None
            )
            artifact_metadata["boundaryObjectKey"] = (
                boundary_artifact.object_key if boundary_artifact else None
            )
            artifact_metadata["boundarySha256"] = (
                boundary_artifact.sha256 if boundary_artifact else None
            )
            artifact_metadata["uncertaintyObjectKey"] = (
                uncertainty_artifact.object_key if uncertainty_artifact else None
            )
            artifact_metadata["uncertaintySha256"] = (
                uncertainty_artifact.sha256 if uncertainty_artifact else None
            )
            artifact_metadata["modelVarianceObjectKey"] = (
                model_variance_artifact.object_key if model_variance_artifact else None
            )
            artifact_metadata["modelVarianceSha256"] = (
                model_variance_artifact.sha256 if model_variance_artifact else None
            )
            payload = _serialize_mask(reconstructed, volume)
            artifact = storage.put_prediction(payload, artifact_metadata)
        except OSError as error:
            raise ServiceError(
                "PREDICTION_STORAGE_FAILED",
                "The prediction artifact could not be stored.",
                500,
            ) from error
        completed = time.perf_counter()
        area = int(np.count_nonzero(reconstructed))
        response = SegmentationResponse(
            modelVersion=model_version,
            architecture=architecture,
            artifactKind=artifact_kind,
            preprocessingVersion=preprocessing_version,
            inputSize=256,
            threshold=threshold,
            correlationId=correlation_id.get(),
            requestId=request_id,
            inputSha256=volume.sha256,
            weightSha256=manifest.weight_sha256 if manifest else None,
            modelManifestSha256=runtime.manifest_sha256,
            predictionObjectKey=artifact.object_key,
            predictionSha256=artifact.sha256,
            maskShape=list(reconstructed.shape),
            tumorAreaPixels=area,
            tumorAreaRatio=area / reconstructed.size,
            inputMode=runtime.input_mode,
            contextSlices=runtime.context_slices,
            sliceFusion=runtime.slice_fusion,
            boundaryHead=runtime.boundary_head,
            deepSupervision=runtime.deep_supervision,
            memberWeightHashes=runtime.member_weight_hashes,
            probabilityArtifact=(probability_artifact.object_key if probability_artifact else None),
            probabilitySha256=probability_artifact.sha256 if probability_artifact else None,
            boundaryArtifact=boundary_artifact.object_key if boundary_artifact else None,
            boundarySha256=boundary_artifact.sha256 if boundary_artifact else None,
            uncertaintyArtifact=(uncertainty_artifact.object_key if uncertainty_artifact else None),
            uncertaintySha256=uncertainty_artifact.sha256 if uncertainty_artifact else None,
            modelVarianceArtifact=(
                model_variance_artifact.object_key if model_variance_artifact else None
            ),
            modelVarianceSha256=(
                model_variance_artifact.sha256 if model_variance_artifact else None
            ),
            ensembleSize=runtime.ensemble_size,
            meanUncertainty=(
                float(np.mean(uncertainty_volume)) if uncertainty_volume is not None else None
            ),
            p95Uncertainty=(
                float(np.percentile(uncertainty_volume, 95))
                if uncertainty_volume is not None
                else None
            ),
            timings=Timings(
                preprocessingMilliseconds=(preprocessed - started) * 1000,
                inferenceMilliseconds=prediction.forward_milliseconds,
                postprocessingMilliseconds=(completed - inferred) * 1000,
            ),
        )
        storage.save_prediction_response(artifact.object_key, response.model_dump(mode="json"))
        storage.save_request_response(
            request_id,
            volume.sha256,
            artifact.object_key,
            artifact.sha256,
            response.model_dump(mode="json"),
        )
        return response

    @application.post(
        "/v1/segment",
        response_model=SegmentationResponse,
        responses=ERROR_RESPONSES,
        tags=["Segmentation"],
    )
    async def segment(
        file: Annotated[UploadFile, File()],
        request_id: Annotated[str | None, Form(alias="requestId")] = None,
        _: None = Depends(require_service_auth),
    ) -> SegmentationResponse:
        volume = await read_volume(file, settings)
        return await segment_volume(volume, request_id or uuid.uuid4().hex)

    @application.get(
        "/v1/predictions/{prediction_object_key}",
        responses=ERROR_RESPONSES,
        tags=["Segmentation"],
        dependencies=[Depends(require_service_auth)],
    )
    async def download_prediction(prediction_object_key: str) -> Response:
        payload, _, digest = storage.read_prediction(prediction_object_key)
        return Response(
            content=payload,
            media_type="application/gzip",
            headers={"X-Prediction-Sha256": digest},
        )

    @application.get(
        "/v1/artifacts/{artifact_object_key}",
        responses=ERROR_RESPONSES,
        tags=["Segmentation"],
        dependencies=[Depends(require_service_auth)],
    )
    async def download_auxiliary_artifact(artifact_object_key: str) -> Response:
        payload, metadata, digest = storage.read_prediction(artifact_object_key)
        artifact_type = metadata.get("artifactType")
        if artifact_type not in {"probability", "boundary", "uncertainty", "model_variance"}:
            raise ServiceError(
                "INVALID_ARTIFACT_TYPE", "The requested auxiliary artifact is unavailable.", 404
            )
        return Response(
            content=payload,
            media_type="application/gzip",
            headers={
                "X-Artifact-Sha256": digest,
                "X-Artifact-Type": artifact_type,
            },
        )

    @application.post(
        "/v1/evaluate",
        response_model=EvaluationResponse,
        responses={
            status: definition for status, definition in ERROR_RESPONSES.items() if status != 504
        },
        tags=["Evaluation"],
    )
    async def evaluate(
        file: Annotated[UploadFile, File()],
        label: Annotated[UploadFile, File()],
        prediction_object_key: Annotated[str, Form(alias="predictionObjectKey")],
        evaluation_protocol: Annotated[str, Form(alias="evaluationProtocol")] = EVALUATION_PROTOCOL,
        _: None = Depends(require_service_auth),
    ) -> EvaluationResponse:
        if evaluation_protocol != EVALUATION_PROTOCOL:
            raise ServiceError(
                "EVALUATION_PROTOCOL_UNSUPPORTED",
                "The requested evaluation protocol is unsupported.",
            )
        source = await read_volume(file, settings)
        truth = await read_volume(label, settings)
        ensure_same_geometry(source, truth)
        try:
            expected = whole_tumor_mask(truth.volume)
        except ValueError as error:
            raise ServiceError(
                "INVALID_LABELS", "Only BraTS labels 0, 1, 2, and 4 are accepted."
            ) from error
        payload, artifact_metadata, digest = storage.read_prediction(prediction_object_key)
        if artifact_metadata.get("inputSha256") != source.sha256:
            raise ServiceError(
                "PREDICTION_SOURCE_MISMATCH",
                "The prediction artifact was not generated from this input volume.",
                409,
            )
        if not _same_geometry_metadata(source.geometry, artifact_metadata.get("geometry", {})):
            raise ServiceError(
                "PREDICTION_ALIGNMENT_INVALID",
                "Prediction and input volume geometry must match.",
                409,
            )
        prediction = parse_volume(payload, prediction_object_key, settings)
        if not _same_geometry_metadata(source.geometry, prediction.geometry):
            raise ServiceError(
                "PREDICTION_ALIGNMENT_INVALID",
                "Prediction and input volume geometry must match.",
                409,
            )
        if not np.isin(prediction.volume, [0, 1]).all():
            raise ServiceError(
                "PREDICTION_INVALID", "The stored prediction must be a binary mask.", 409
            )
        predicted = prediction.volume.astype(np.uint8)
        slices = [
            binary_metrics(predicted[:, :, index], expected[:, :, index])
            for index in range(predicted.shape[2])
        ]
        calibration = None
        retention = None
        probability_key = artifact_metadata.get("probabilityObjectKey")
        uncertainty_key = artifact_metadata.get("uncertaintyObjectKey")
        if isinstance(probability_key, str) and isinstance(uncertainty_key, str):
            probability_payload, probability_metadata, _ = storage.read_prediction(probability_key)
            uncertainty_payload, uncertainty_metadata, _ = storage.read_prediction(uncertainty_key)
            if (
                probability_metadata.get("artifactType") != "probability"
                or uncertainty_metadata.get("artifactType") != "uncertainty"
                or probability_metadata.get("requestId") != artifact_metadata.get("requestId")
                or uncertainty_metadata.get("requestId") != artifact_metadata.get("requestId")
                or probability_metadata.get("inputSha256") != source.sha256
                or uncertainty_metadata.get("inputSha256") != source.sha256
                or not _same_geometry_metadata(
                    source.geometry, probability_metadata.get("geometry", {})
                )
                or not _same_geometry_metadata(
                    source.geometry, uncertainty_metadata.get("geometry", {})
                )
            ):
                raise ServiceError(
                    "AUXILIARY_ARTIFACT_INVALID",
                    "An auxiliary prediction artifact failed its traceability checks.",
                    409,
                )
            probability_volume = parse_volume(probability_payload, probability_key, settings)
            uncertainty_volume = parse_volume(uncertainty_payload, uncertainty_key, settings)
            if (
                not _same_geometry_metadata(source.geometry, probability_volume.geometry)
                or not _same_geometry_metadata(source.geometry, uncertainty_volume.geometry)
                or probability_volume.volume.shape != source.volume.shape
                or uncertainty_volume.volume.shape != source.volume.shape
            ):
                raise ServiceError(
                    "AUXILIARY_ALIGNMENT_INVALID",
                    "Auxiliary artifacts must match the input volume geometry.",
                    409,
                )
            probabilities = probability_volume.volume.astype(np.float32)
            uncertainty = uncertainty_volume.volume.astype(np.float32)
            if (
                not np.isfinite(probabilities).all()
                or np.any((probabilities < 0) | (probabilities > 1))
                or not np.isin(uncertainty_volume.volume, np.arange(101)).all()
            ):
                raise ServiceError(
                    "AUXILIARY_ARTIFACT_INVALID",
                    "An auxiliary prediction artifact contains invalid values.",
                    409,
                )
            calibration = calibration_metrics(probabilities, expected, uncertainty)
            retention = brats_retention_metrics(
                predicted,
                expected,
                uncertainty_volume.volume.astype(np.float32),
            )
        return EvaluationResponse(
            modelVersion=str(artifact_metadata["modelVersion"]),
            architecture=str(artifact_metadata["architecture"]),
            artifactKind=str(artifact_metadata["artifactKind"]),
            preprocessingVersion=str(artifact_metadata["preprocessingVersion"]),
            evaluationProtocol=EVALUATION_PROTOCOL,
            threshold=float(artifact_metadata["threshold"]),
            weightSha256=artifact_metadata.get("modelWeightSha256"),
            modelManifestSha256=artifact_metadata.get("modelManifestSha256"),
            requestId=str(artifact_metadata["requestId"]),
            correlationId=correlation_id.get(),
            inputSha256=source.sha256,
            groundTruthSha256=truth.sha256,
            predictionObjectKey=prediction_object_key,
            predictionSha256=digest,
            patientMetrics=binary_metrics(predicted, expected),
            sliceMacroMetrics=macro_metrics(slices),
            sliceCount=len(slices),
            calibrationMetrics=calibration,
            uncertaintyRetentionMetrics=retention,
        )

    return application


app = create_app()
