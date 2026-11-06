import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from training import DISCLAIMER, PREPROCESSING_VERSION
from training.metrics import BinaryMetrics, binary_metrics
from training.preprocessing import prepare_axial_slice, resize_mask, whole_tumor_mask

from brainseg_inference.errors import ServiceError, error_response
from brainseg_inference.inputs import VolumeInput, read_volume
from brainseg_inference.logging import configure_logging, correlation_id
from brainseg_inference.runtime import ModelRuntime, Predictor
from brainseg_inference.settings import Settings


class Timings(BaseModel):
    preprocessingMilliseconds: float
    inferenceMilliseconds: float
    postprocessingMilliseconds: float


class SegmentationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelVersion: str
    preprocessingVersion: str
    threshold: float
    correlationId: str
    inputSha256: str
    sliceIndex: int
    mask: list[list[int]]
    tumorAreaPixels: int
    tumorAreaRatio: float
    timings: Timings
    disclaimer: str = DISCLAIMER


class EvaluationResponse(BaseModel):
    segmentation: SegmentationResponse
    sliceMetrics: BinaryMetrics
    metricLevel: str = "slice"
    disclaimer: str = DISCLAIMER


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


def create_app(settings: Settings | None = None, predictor: Predictor | None = None) -> FastAPI:
    settings = settings or Settings()
    runtime = ModelRuntime(settings, predictor)
    logger = configure_logging()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime.load()
        yield
        runtime.close()

    application = FastAPI(
        title="BrainSeg Inference API", version="0.1.0", description=DISCLAIMER, lifespan=lifespan
    )
    application.add_middleware(
        RequestSizeLimitMiddleware, max_bytes=settings.max_upload_bytes + 65536
    )

    @application.middleware("http")
    async def correlate(request: Request, call_next):
        candidate = request.headers.get("X-Correlation-Id", "")
        identifier = (
            candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid.uuid4().hex
        )
        token = correlation_id.set(identifier)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.error("request_failed", extra={"errorCode": "INTERNAL_ERROR"})
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
        return error_response(error)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return error_response(
            ServiceError("VALIDATION_ERROR", "The request fields are invalid.", 422)
        )

    @application.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "modelReady": runtime.ready, "correlationId": correlation_id.get()}

    @application.get("/ready", tags=["Health"])
    async def ready():
        if not runtime.ready:
            return error_response(
                ServiceError(
                    runtime.error_code or "MODEL_NOT_READY", "No verified model is available.", 503
                )
            )
        return {
            "status": "ready",
            "modelVersion": settings.model_version,
            "correlationId": correlation_id.get(),
        }

    @application.get("/models", tags=["Models"])
    async def models():
        return {
            "models": [
                {
                    "modelVersion": settings.model_version,
                    "preprocessingVersion": PREPROCESSING_VERSION,
                    "threshold": settings.threshold,
                    "inputSize": settings.input_size,
                    "device": "cpu",
                }
            ]
            if runtime.ready
            else [],
            "ready": runtime.ready,
            "errorCode": runtime.error_code,
            "correlationId": correlation_id.get(),
            "disclaimer": DISCLAIMER,
        }

    async def segment_volume(volume: VolumeInput, slice_index: int) -> SegmentationResponse:
        if slice_index >= volume.volume.shape[2]:
            raise ServiceError("SLICE_OUT_OF_RANGE", "Slice index is outside the volume.")
        started = time.perf_counter()
        image = prepare_axial_slice(volume.volume, slice_index, settings.input_size)
        preprocessed = time.perf_counter()
        logits = await runtime.predict(image)
        inferred = time.perf_counter()
        if logits.shape != image.shape or not np.isfinite(logits).all():
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        probabilities = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
        mask = (probabilities >= settings.threshold).astype(np.uint8)
        completed = time.perf_counter()
        area = int(np.count_nonzero(mask))
        return SegmentationResponse(
            modelVersion=settings.model_version,
            preprocessingVersion=PREPROCESSING_VERSION,
            threshold=settings.threshold,
            correlationId=correlation_id.get(),
            inputSha256=volume.sha256,
            sliceIndex=slice_index,
            mask=mask.tolist(),
            tumorAreaPixels=area,
            tumorAreaRatio=area / mask.size,
            timings=Timings(
                preprocessingMilliseconds=(preprocessed - started) * 1000,
                inferenceMilliseconds=(inferred - preprocessed) * 1000,
                postprocessingMilliseconds=(completed - inferred) * 1000,
            ),
        )

    @application.post("/v1/segment", response_model=SegmentationResponse, tags=["Segmentation"])
    async def segment(
        file: Annotated[UploadFile, File()], slice_index: Annotated[int, Form(ge=0)] = 0
    ):
        volume = await read_volume(file, settings)
        return await segment_volume(volume, slice_index)

    @application.post("/v1/evaluate", response_model=EvaluationResponse, tags=["Evaluation"])
    async def evaluate(
        file: Annotated[UploadFile, File()],
        label: Annotated[UploadFile, File()],
        slice_index: Annotated[int, Form(ge=0)] = 0,
    ):
        volume = await read_volume(file, settings)
        labels = await read_volume(label, settings)
        if labels.volume.shape != volume.volume.shape or not np.allclose(
            labels.affine, volume.affine
        ):
            raise ServiceError(
                "LABEL_ALIGNMENT_INVALID", "Image and label volume geometry must match."
            )
        try:
            expected_volume = whole_tumor_mask(labels.volume)
        except ValueError as error:
            raise ServiceError(
                "INVALID_LABELS", "Only BraTS labels 0, 1, 2, and 4 are accepted."
            ) from error
        segmentation = await segment_volume(volume, slice_index)
        expected = resize_mask(expected_volume[:, :, slice_index], settings.input_size)
        predicted = np.asarray(segmentation.mask, dtype=np.uint8)
        return EvaluationResponse(
            segmentation=segmentation, sliceMetrics=binary_metrics(predicted, expected)
        )

    return application


app = create_app()
