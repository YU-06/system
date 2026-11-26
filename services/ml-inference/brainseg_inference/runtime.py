import asyncio
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

from brainseg_inference.errors import ServiceError
from brainseg_inference.logging import configure_logging
from brainseg_inference.manifest import ModelManifest
from brainseg_inference.settings import Settings


class Predictor(Protocol):
    batch_size: int

    def predict_batch(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]: ...


@dataclass(frozen=True)
class PredictorOutput:
    mean_probability: NDArray[np.float32]
    boundary_probability: NDArray[np.float32] | None
    predictive_entropy: NDArray[np.float32]
    model_variance: NDArray[np.float32] | None
    forward_milliseconds: float


class OnnxPredictor:
    def __init__(self, weights_path: str, manifest: ModelManifest, settings: Settings) -> None:
        self.manifest = manifest
        self.sessions: list[ort.InferenceSession] = []
        self.input_names: list[str] = []
        self.output_names: list[list[str]] = []
        max_batch = settings.max_inference_batch_size
        base = Path(weights_path).parent
        for member in manifest.ensemble_members:
            path = base / member.weight_file
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.log_severity_level = 3
            session = ort.InferenceSession(
                str(path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            input_values, outputs = session.get_inputs(), session.get_outputs()
            if len(input_values) != 1 or not outputs or input_values[0].type != "tensor(float)":
                raise ServiceError(
                    "MODEL_CONTRACT_INVALID", "The model input or output contract is invalid.", 503
                )
            expected_channels = 1 if manifest.input_mode == "2d" else manifest.context_slices
            input_shape = input_values[0].shape
            expected_input = [expected_channels, manifest.input_size, manifest.input_size]
            if len(input_shape) != 4 or input_shape[1:] != expected_input:
                raise ServiceError(
                    "INPUT_SIZE_MISMATCH",
                    "The model input dimensions do not match its manifest.",
                    503,
                )
            if isinstance(input_shape[0], int) and input_shape[0] != 1:
                raise ServiceError(
                    "MODEL_CONTRACT_INVALID",
                    "The model must support a single or dynamic slice batch.",
                    503,
                )
            output_shape = outputs[0].shape
            if (
                outputs[0].type != "tensor(float)"
                or len(output_shape) != 4
                or output_shape[1:] != [1, manifest.input_size, manifest.input_size]
                or isinstance(output_shape[0], int)
                and output_shape[0] != 1
            ):
                raise ServiceError(
                    "MODEL_CONTRACT_INVALID", "The model output contract is invalid.", 503
                )
            names = [output.name for output in outputs]
            if manifest.boundary_head and "boundary_logits" not in names:
                raise ServiceError(
                    "MODEL_CONTRACT_INVALID",
                    "The model manifest declares a missing boundary output.",
                    503,
                )
            if manifest.deep_supervision and "aux_logits" not in names:
                raise ServiceError(
                    "MODEL_CONTRACT_INVALID",
                    "The model manifest declares a missing auxiliary output.",
                    503,
                )
            self._check_metadata(session.get_modelmeta().custom_metadata_map, manifest)
            self.sessions.append(session)
            self.input_names.append(input_values[0].name)
            self.output_names.append(names)
            if isinstance(input_shape[0], int) or isinstance(output_shape[0], int):
                max_batch = 1
        self.batch_size = max_batch
        if self.batch_size < 1:
            raise ServiceError(
                "MODEL_CONTRACT_INVALID", "The model batch dimension is invalid.", 503
            )

    @staticmethod
    def _check_metadata(metadata: dict[str, str], manifest: ModelManifest) -> None:
        expected = (
            ("brainseg.architecture", manifest.architecture, "MODEL_ARCHITECTURE_MISMATCH"),
            (
                "brainseg.preprocessing_version",
                manifest.preprocessing_version,
                "PREPROCESSING_VERSION_MISMATCH",
            ),
            ("brainseg.input_size", str(manifest.input_size), "INPUT_SIZE_MISMATCH"),
        )
        for key, value, error_code in expected:
            if key not in metadata:
                raise ServiceError(
                    "MODEL_METADATA_MISSING", "Required model metadata is missing.", 503
                )
            if metadata[key] != value:
                raise ServiceError(error_code, "Model metadata does not match its manifest.", 503)
        if manifest.input_mode == "2p5d":
            context_contract = {
                "brainseg.input_mode": manifest.input_mode,
                "brainseg.context_slices": str(manifest.context_slices),
                "brainseg.slice_fusion": manifest.slice_fusion,
            }
            if manifest.boundary_head:
                context_contract["brainseg.boundary_head"] = "true"
            if manifest.deep_supervision:
                context_contract["brainseg.deep_supervision"] = "true"
            if any(metadata.get(key) != value for key, value in context_contract.items()):
                raise ServiceError(
                    "MODEL_METADATA_MISSING",
                    "Required model architecture metadata is missing or inconsistent.",
                    503,
                )
        try:
            embedded_threshold = float(metadata["brainseg.threshold"])
        except (KeyError, ValueError) as error:
            raise ServiceError(
                "MODEL_METADATA_MISSING",
                "Required model metadata is missing.",
                503,
            ) from error
        if not math.isclose(embedded_threshold, manifest.threshold, rel_tol=0, abs_tol=1e-9):
            raise ServiceError(
                "MODEL_THRESHOLD_MISMATCH",
                "The model threshold does not match its manifest.",
                503,
            )

    def predict_outputs_batch(self, images: NDArray[np.float32]) -> PredictorOutput:
        inputs = images[:, np.newaxis, :, :] if images.ndim == 3 else images
        expected_channels = 1 if self.manifest.input_mode == "2d" else self.manifest.context_slices
        if inputs.ndim != 4 or inputs.shape[1:] != (
            expected_channels,
            self.manifest.input_size,
            self.manifest.input_size,
        ):
            raise ServiceError("MODEL_INPUT_INVALID", "The model input is invalid.", 400)
        member_probabilities: list[NDArray[np.float32]] = []
        member_boundaries: list[NDArray[np.float32]] = []
        forward_ms = 0.0
        for session, input_name, output_names in zip(
            self.sessions, self.input_names, self.output_names, strict=True
        ):
            started = time.perf_counter()
            outputs = session.run(None, {input_name: inputs})
            forward_ms += (time.perf_counter() - started) * 1000
            output_map = dict(zip(output_names, outputs, strict=True))
            segmentation = output_map.get("segmentation_logits", outputs[0])
            expected_shape = (len(inputs), 1, self.manifest.input_size, self.manifest.input_size)
            if segmentation.shape != expected_shape or not np.isfinite(segmentation).all():
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500
                )
            clipped = np.clip(segmentation[:, 0], -80, 80)
            member_probabilities.append((1 / (1 + np.exp(-clipped))).astype(np.float32))
            if self.manifest.boundary_head:
                boundary = output_map["boundary_logits"]
                if boundary.shape != expected_shape or not np.isfinite(boundary).all():
                    raise ServiceError(
                        "MODEL_OUTPUT_INVALID", "The boundary output contract is invalid.", 500
                    )
                member_boundaries.append(
                    (1 / (1 + np.exp(-np.clip(boundary[:, 0], -80, 80)))).astype(np.float32)
                )
        members = np.stack(member_probabilities).astype(np.float64, copy=False)
        mean = members.mean(axis=0)
        clipped_mean = np.clip(mean, np.finfo(np.float64).eps, 1 - np.finfo(np.float64).eps)
        entropy = -(
            clipped_mean * np.log2(clipped_mean) + (1 - clipped_mean) * np.log2(1 - clipped_mean)
        )
        boundary_probability = (
            np.mean(np.stack(member_boundaries), axis=0).astype(np.float32)
            if member_boundaries
            else None
        )
        return PredictorOutput(
            mean.astype(np.float32),
            boundary_probability,
            entropy.astype(np.float32),
            members.var(axis=0).astype(np.float32) if len(member_probabilities) > 1 else None,
            forward_ms,
        )

    def predict_batch(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        output = self.predict_outputs_batch(images)
        probability = np.clip(output.mean_probability, 1e-7, 1 - 1e-7)
        logits = np.log(probability / (1 - probability)).astype(np.float32)
        return logits, output.forward_milliseconds


class ModelRuntime:
    def __init__(self, settings: Settings, predictor: Predictor | None = None) -> None:
        self.settings = settings
        self.predictor = predictor
        self.manifest: ModelManifest | None = None
        self.manifest_sha256: str | None = None
        self.error_code: str | None = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.semaphore = asyncio.Semaphore(1)
        self._load_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.predictor is not None

    @property
    def model_version(self) -> str | None:
        return (
            self.manifest.model_version
            if self.manifest
            else ("synthetic-test" if self.predictor is not None else None)
        )

    @property
    def architecture(self) -> str | None:
        return (
            self.manifest.architecture
            if self.manifest
            else ("test-double" if self.predictor is not None else None)
        )

    @property
    def preprocessing_version(self) -> str | None:
        return (
            self.manifest.preprocessing_version
            if self.manifest
            else ("flair-v1" if self.predictor is not None else None)
        )

    @property
    def threshold(self) -> float | None:
        return (
            self.manifest.threshold
            if self.manifest
            else (0.5 if self.predictor is not None else None)
        )

    @property
    def artifact_kind(self) -> str | None:
        return (
            self.manifest.artifact_kind
            if self.manifest
            else ("synthetic_test" if self.predictor is not None else None)
        )

    @property
    def input_mode(self) -> str:
        return self.manifest.input_mode if self.manifest else "2d"

    @property
    def context_slices(self) -> int:
        if self.manifest is None or self.manifest.input_mode == "2d":
            return 1
        return self.manifest.context_slices

    @property
    def slice_fusion(self) -> str:
        return self.manifest.slice_fusion if self.manifest else "stack"

    @property
    def boundary_head(self) -> bool:
        return self.manifest.boundary_head if self.manifest else False

    @property
    def deep_supervision(self) -> bool:
        return self.manifest.deep_supervision if self.manifest else False

    @property
    def uncertainty_enabled(self) -> bool:
        return self.manifest.uncertainty_enabled if self.manifest else False

    @property
    def uncertainty_scale_max(self) -> float | None:
        return self.manifest.uncertainty_scale_max if self.manifest else None

    @property
    def ensemble_size(self) -> int:
        return len(self.manifest.ensemble_members) if self.manifest else 1

    @property
    def member_weight_hashes(self) -> list[str]:
        return (
            [member.weight_sha256 for member in self.manifest.ensemble_members]
            if self.manifest
            else []
        )

    @property
    def optional_artifacts_enabled(self) -> bool:
        return bool(
            self.manifest
            and (
                self.manifest.input_mode == "2p5d"
                or self.manifest.boundary_head
                or self.manifest.uncertainty_enabled
                or len(self.manifest.ensemble_members) > 1
            )
        )

    def load(self) -> None:
        if self.predictor is not None:
            return
        try:
            with self._load_lock:
                manifest, weights_path, manifest_sha256 = ModelManifest.load(self.settings)
                self.predictor = OnnxPredictor(str(weights_path), manifest, self.settings)
                self.manifest = manifest
                self.manifest_sha256 = manifest_sha256
                self.error_code = None
        except Exception as error:
            self.error_code = error.code if isinstance(error, ServiceError) else "MODEL_LOAD_FAILED"
            configure_logging().warning(
                "model_not_ready",
                extra={
                    "errorCode": self.error_code,
                    "diagnosticType": type(error).__name__,
                },
            )

    async def predict_outputs(self, images: NDArray[np.float32]) -> PredictorOutput:
        predictor = self.predictor
        if predictor is None:
            raise ServiceError("MODEL_NOT_READY", "No verified model is available.", 503)
        if images.ndim not in {3, 4} or not np.isfinite(images).all():
            raise ServiceError("MODEL_INPUT_INVALID", "The model input is invalid.", 400)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.request_timeout_seconds
        acquired = False
        try:
            await asyncio.wait_for(self.semaphore.acquire(), max(0, deadline - loop.time()))
            acquired = True
            future = loop.run_in_executor(
                self.executor, self._predict_batched_outputs, predictor, images
            )
            future.add_done_callback(self._release_inference_slot)
            acquired = False
            return await asyncio.wait_for(asyncio.shield(future), max(0, deadline - loop.time()))
        except TimeoutError as error:
            raise ServiceError(
                "INFERENCE_TIMEOUT", "The inference deadline was exceeded.", 504
            ) from error
        finally:
            if acquired:
                self.semaphore.release()

    async def predict(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        output = await self.predict_outputs(images)
        probability = np.clip(output.mean_probability, 1e-7, 1 - 1e-7)
        logits = np.log(probability / (1 - probability)).astype(np.float32)
        return logits, output.forward_milliseconds

    def _release_inference_slot(self, completed: asyncio.Future[PredictorOutput]) -> None:
        if completed.done():
            self.semaphore.release()

    @staticmethod
    def _predict_batched_outputs(
        predictor: Predictor, images: NDArray[np.float32]
    ) -> PredictorOutput:
        probability_chunks: list[NDArray[np.float32]] = []
        boundary_chunks: list[NDArray[np.float32]] = []
        entropy_chunks: list[NDArray[np.float32]] = []
        variance_chunks: list[NDArray[np.float32]] = []
        forward_ms = 0.0
        for start in range(0, len(images), predictor.batch_size):
            batch = images[start : start + predictor.batch_size]
            try:
                rich_predict = getattr(predictor, "predict_outputs_batch", None)
                if callable(rich_predict):
                    output = rich_predict(batch)
                else:
                    batch_logits, batch_forward_ms = predictor.predict_batch(batch)
                    logits = np.asarray(batch_logits, dtype=np.float32)
                    if logits.ndim == 4 and logits.shape[1] == 1:
                        logits = logits[:, 0]
                    if logits.shape != (len(batch), batch.shape[-2], batch.shape[-1]):
                        raise ServiceError(
                            "MODEL_OUTPUT_INVALID",
                            "The model output contract is invalid.",
                            500,
                        )
                    probability = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
                    clipped = np.clip(
                        probability, np.finfo(np.float32).eps, 1 - np.finfo(np.float32).eps
                    )
                    entropy = -(clipped * np.log2(clipped) + (1 - clipped) * np.log2(1 - clipped))
                    output = PredictorOutput(
                        probability.astype(np.float32),
                        None,
                        entropy.astype(np.float32),
                        None,
                        float(batch_forward_ms),
                    )
            except ServiceError:
                raise
            except Exception as error:
                configure_logging().error(
                    "model_forward_failed",
                    extra={
                        "errorCode": "MODEL_FORWARD_FAILED",
                        "diagnosticType": type(error).__name__,
                    },
                )
                raise ServiceError(
                    "MODEL_FORWARD_FAILED", "Model inference could not be completed.", 500
                ) from error
            expected_shape = (len(batch), batch.shape[-2], batch.shape[-1])
            if (
                output.mean_probability.shape != expected_shape
                or output.predictive_entropy.shape != expected_shape
                or not np.isfinite(output.mean_probability).all()
                or not np.isfinite(output.predictive_entropy).all()
                or np.any((output.mean_probability < 0) | (output.mean_probability > 1))
                or np.any((output.predictive_entropy < 0) | (output.predictive_entropy > 1))
            ):
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500
                )
            if output.boundary_probability is not None and (
                output.boundary_probability.shape != expected_shape
                or not np.isfinite(output.boundary_probability).all()
                or np.any((output.boundary_probability < 0) | (output.boundary_probability > 1))
            ):
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The boundary output contract is invalid.", 500
                )
            if output.model_variance is not None and (
                output.model_variance.shape != expected_shape
                or not np.isfinite(output.model_variance).all()
                or np.any((output.model_variance < 0) | (output.model_variance > 0.25))
            ):
                raise ServiceError(
                    "MODEL_OUTPUT_INVALID", "The ensemble variance output is invalid.", 500
                )
            probability_chunks.append(output.mean_probability)
            entropy_chunks.append(output.predictive_entropy)
            if output.boundary_probability is not None:
                boundary_chunks.append(output.boundary_probability)
            if output.model_variance is not None:
                variance_chunks.append(output.model_variance)
            forward_ms += output.forward_milliseconds
        mean_probability = np.concatenate(probability_chunks, axis=0)
        predictive_entropy = np.concatenate(entropy_chunks, axis=0)
        boundary_probability = np.concatenate(boundary_chunks, axis=0) if boundary_chunks else None
        model_variance = np.concatenate(variance_chunks, axis=0) if variance_chunks else None
        if not np.isfinite(mean_probability).all():
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        return PredictorOutput(
            mean_probability,
            boundary_probability,
            predictive_entropy,
            model_variance,
            forward_ms,
        )

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
