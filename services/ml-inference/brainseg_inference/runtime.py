import asyncio
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

from brainseg_inference.errors import ServiceError
from brainseg_inference.logging import configure_logging
from brainseg_inference.settings import Settings


class Predictor(Protocol):
    def predict(self, image: NDArray[np.float32]) -> NDArray[np.float32]: ...


class OnnxPredictor:
    def __init__(self, settings: Settings) -> None:
        if settings.model_path is None or not settings.model_path.is_file():
            raise ServiceError("MODEL_NOT_CONFIGURED", "No model file is configured.", 503)
        if len(settings.model_sha256) != 64:
            raise ServiceError("MODEL_HASH_REQUIRED", "A model SHA-256 is required.", 503)
        with settings.model_path.open("rb") as model_file:
            digest = hashlib.file_digest(model_file, "sha256").hexdigest()
        if not hmac.compare_digest(digest, settings.model_sha256.lower()):
            raise ServiceError("MODEL_HASH_MISMATCH", "Model integrity validation failed.", 503)
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(settings.model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        inputs = self.session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != "tensor(float)":
            raise ServiceError(
                "MODEL_CONTRACT_INVALID", "The model input contract is invalid.", 503
            )
        expected = [1, 1, settings.input_size, settings.input_size]
        if len(inputs[0].shape) != 4 or any(
            isinstance(actual, int) and actual != required
            for actual, required in zip(inputs[0].shape, expected, strict=True)
        ):
            raise ServiceError(
                "MODEL_CONTRACT_INVALID", "The model input dimensions are invalid.", 503
            )
        self.input_name = inputs[0].name

    def predict(self, image: NDArray[np.float32]) -> NDArray[np.float32]:
        output = self.session.run(None, {self.input_name: image[np.newaxis, np.newaxis]})[0]
        if output.shape != (1, 1, *image.shape) or not np.isfinite(output).all():
            raise ServiceError("MODEL_OUTPUT_INVALID", "The model output contract is invalid.", 500)
        return np.asarray(output[0, 0], dtype=np.float32)


class ModelRuntime:
    def __init__(self, settings: Settings, predictor: Predictor | None = None) -> None:
        self.settings = settings
        self.predictor = predictor
        self.error_code: str | None = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.semaphore = asyncio.Semaphore(1)

    @property
    def ready(self) -> bool:
        return self.predictor is not None

    def load(self) -> None:
        if self.predictor is not None:
            return
        try:
            self.predictor = OnnxPredictor(self.settings)
        except Exception as error:
            self.error_code = error.code if isinstance(error, ServiceError) else "MODEL_LOAD_FAILED"
            configure_logging().warning("model_not_ready", extra={"errorCode": self.error_code})

    async def predict(self, image: NDArray[np.float32]) -> NDArray[np.float32]:
        if self.predictor is None:
            raise ServiceError("MODEL_NOT_READY", "No verified model is available.", 503)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.request_timeout_seconds
        try:
            await asyncio.wait_for(self.semaphore.acquire(), self.settings.request_timeout_seconds)
            future = loop.run_in_executor(self.executor, self.predictor.predict, image)
            future.add_done_callback(lambda completed: self.semaphore.release())
            return await asyncio.wait_for(asyncio.shield(future), max(0, deadline - loop.time()))
        except TimeoutError as error:
            raise ServiceError(
                "INFERENCE_TIMEOUT", "The inference deadline was exceeded.", 504
            ) from error

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
