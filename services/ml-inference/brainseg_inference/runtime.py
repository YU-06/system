import asyncio
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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


class OnnxPredictor:
    def __init__(self, weights_path: str, manifest: ModelManifest, settings: Settings) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(
            weights_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or inputs[0].type != "tensor(float)":
            raise ServiceError(
                "MODEL_CONTRACT_INVALID", "The model input or output contract is invalid.", 503
            )
        expected = [None, 1, manifest.input_size, manifest.input_size]
        shape = inputs[0].shape
        if len(shape) != 4 or shape[1:] != expected[1:]:
            raise ServiceError(
                "INPUT_SIZE_MISMATCH", "The model input dimensions do not match its manifest.", 503
            )
        if isinstance(shape[0], int) and shape[0] != 1:
            raise ServiceError(
                "MODEL_CONTRACT_INVALID",
                "The model must support a single or dynamic slice batch.",
                503,
            )
        output_shape = outputs[0].shape
        if (
            outputs[0].type != "tensor(float)"
            or len(output_shape) != 4
            or output_shape[1:] != expected[1:]
            or isinstance(output_shape[0], int)
            and output_shape[0] != 1
        ):
            raise ServiceError(
                "MODEL_CONTRACT_INVALID", "The model output contract is invalid.", 503
            )
        metadata = self.session.get_modelmeta().custom_metadata_map
        self._check_metadata(metadata, manifest)
        self.input_name = inputs[0].name
        self.batch_size = (
            settings.max_inference_batch_size
            if not isinstance(shape[0], int) and not isinstance(output_shape[0], int)
            else 1
        )
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

    def predict_batch(self, images: NDArray[np.float32]) -> NDArray[np.float32]:
        inputs = images[:, np.newaxis, :, :]
        started = time.perf_counter()
        output = self.session.run(None, {self.input_name: inputs})[0]
        forward_ms = (time.perf_counter() - started) * 1000
        expected_shape = (len(images), 1, images.shape[1], images.shape[2])
        if output.shape != expected_shape or not np.isfinite(output).all():
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        return np.asarray(output[:, 0], dtype=np.float32), forward_ms


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

    async def predict(self, images: NDArray[np.float32]) -> tuple[NDArray[np.float32], float]:
        predictor = self.predictor
        if predictor is None:
            raise ServiceError("MODEL_NOT_READY", "No verified model is available.", 503)
        if images.ndim != 3 or not np.isfinite(images).all():
            raise ServiceError("MODEL_INPUT_INVALID", "The model input is invalid.", 400)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.request_timeout_seconds
        acquired = False
        try:
            await asyncio.wait_for(self.semaphore.acquire(), max(0, deadline - loop.time()))
            acquired = True
            future = loop.run_in_executor(self.executor, self._predict_batched, predictor, images)
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

    def _release_inference_slot(
        self, completed: asyncio.Future[tuple[NDArray[np.float32], float]]
    ) -> None:
        if completed.done():
            self.semaphore.release()

    @staticmethod
    def _predict_batched(
        predictor: Predictor, images: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], float]:
        chunks = []
        forward_ms = 0.0
        for start in range(0, len(images), predictor.batch_size):
            try:
                batch_logits, batch_forward_ms = predictor.predict_batch(
                    images[start : start + predictor.batch_size]
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
            chunks.append(batch_logits)
            forward_ms += batch_forward_ms
        result = np.concatenate(chunks, axis=0)
        if result.shape != images.shape or not np.isfinite(result).all():
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        return result, forward_ms

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
