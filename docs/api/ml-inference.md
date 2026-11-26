# ML inference API

**Research and teaching only. Not a medical device; not for clinical diagnosis; no diagnostic, treatment, or prognosis advice.**

OpenAPI is served at `/openapi.json` and Swagger UI at `/docs`. The API accepts complete NIfTI-1 `.nii` and `.nii.gz` volumes via multipart upload; it does not accept paths, URLs, archive files, or caller-selected model files. The [API index](README.md) records the ABP and FastAPI schema URLs and safe inspection commands.

All `/v1/*` data endpoints require `Authorization: Bearer <ML_SERVICE_API_KEY>`. If the service key is missing or empty, inference, evaluation, and prediction download fail closed with `503 SERVICE_AUTH_NOT_CONFIGURED`; `/health`, `/ready`, `/models`, and OpenAPI remain available for diagnosis. Compose supplies the same generated secret to the ABP client and FastAPI service without logging it.

## Endpoints

| Method and path | Contract |
| --- | --- |
| `GET /health` | Process liveness. `200` means the process can respond; it does not mean a model is available. |
| `GET /ready` | Model readiness. Returns `503` and a stable error code until the manifest, checksummed weights, ONNX contract, and model metadata pass validation. |
| `GET /models` | The single loaded model descriptor or an empty list when not ready. |
| `POST /v1/segment` | Multipart fields `file` and stable `requestId`: full T2-FLAIR volume. Returns a system-generated `predictionObjectKey`, prediction SHA-256, original-space dimensions and provenance. |
| `GET /v1/predictions/{predictionObjectKey}` | Authenticated download of the generated binary NIfTI prediction and its SHA-256 response header. |
| `POST /v1/evaluate` | Multipart fields `file`, `label`, `predictionObjectKey`, and optional `evaluationProtocol` (only `whole-tumor-v1`). Requires the original source volume and a previously generated prediction object reference. |

`/v1/segment` normalizes the non-zero brain region using shared `flair-v1` preprocessing, resizes each axis-2 slice using the training interpolation rules, runs batched model inference, thresholds with the value frozen in the model manifest, and restores binary slices to the source array shape with nearest-neighbour interpolation. Axis 2 must be axial (`S`/`I`) as in the training data pipeline; the service rejects other orientations rather than silently reorienting them. Affine-derived spacing must agree with the NIfTI header. The resulting NIfTI retains the original affine, qform/sform codes and spatial units. No accuracy metric is returned by segmentation.

Prediction keys are deterministic UUIDs derived from `requestId`. A receipt and prediction sidecar make retries return the same response and object, including recovery when a process stopped after object persistence but before receipt persistence. Reuse with a different input hash returns `409 IDEMPOTENCY_CONFLICT`; no duplicate prediction object is created for the same request identifier.

`/v1/evaluate` maps BraTS labels 1, 2 and 4 to foreground and label 0 to background. It verifies source, label, and stored prediction shapes, axis directions, voxel spacing, affine, qform/sform and units before calculating patient-volume metrics and the arithmetic mean of per-slice metrics. It rejects mismatches; it never silently resamples. Empty GT and empty prediction produce Dice/IoU/Precision/Recall of 1; exactly one empty mask produces 0, following the shared training metric implementation. The response echoes request id, model weight hash, manifest hash, source/GT/prediction hashes, model/processing versions and correlation ID for ABP to validate before recording metrics.

## Manifest and model verification

`ML_MODEL_MANIFEST_PATH` points to a deployment-controlled YAML manifest. `weightFile` must be a basename in the manifest directory; it cannot be a path or URL. The service checks the manifest schema/version, weight SHA-256, architecture (`UNet` or `AttentionUNet`), preprocessing version, 256 input size, threshold, and matching ONNX custom metadata:

| ONNX custom metadata key | Required value |
| --- | --- |
| `brainseg.architecture` | Manifest architecture |
| `brainseg.preprocessing_version` | Manifest preprocessing version |
| `brainseg.input_size` | Manifest input size |
| `brainseg.threshold` | Manifest threshold |

Only manifests with `artifactKind: research` may become ready. Synthetic test artifacts are rejected at startup and can never be advertised as research weights. The tracked [`model-manifest.example.yaml`](../../services/ml-inference/model-manifest.example.yaml) is explicitly synthetic and non-operational. No real model weights or research inference outputs are included in this repository.

The ONNX Runtime CPU path is the existing inference backend. Model input is float32 `[N,1,256,256]`; output is finite float32 logits `[N,1,256,256]`. A fixed batch dimension of one is supported; otherwise batch dimensions must be dynamic. The maximum runtime batch size is configurable and bounded.

## Resource, privacy, and timing boundaries

- Defaults: 64 MiB uploaded file, 128 MiB decompressed NIfTI, 16,777,216 voxels, maximum dimension 512, and 16 slices per dynamic ONNX batch. Configurable values also have hard caps (256 MiB upload, 512 MiB decompressed, 67,108,864 voxels, dimension 2,048, 128 slices per batch, and 300 seconds). HTTP body size is bounded for multipart overhead.
- Only one model-forward job runs at a time. The inference deadline covers waiting for the inference slot and all forward batches; timed-out work is not reported as successful.
- `preprocessingMilliseconds`: shared volume normalization and 2D slice resizing.
- `inferenceMilliseconds`: summed wall time inside ONNX `session.run` calls only; excludes queue wait.
- `postprocessingMilliseconds`: sigmoid/threshold, inverse resize, NIfTI encoding, SHA-256 and prediction payload/base-provenance persistence. Final idempotency receipt writes are excluded.
- The service stores prediction NIfTI files and provenance sidecars under a configured local object-storage root. Returned keys are deterministic UUIDs derived from an opaque requestId; evaluation only accepts that restricted key format. User MRI uploads are not persisted.
- Correlation IDs are validated or regenerated and are returned in response headers/bodies and stored with prediction provenance. Logs exclude request bodies, MRI data, and tokens.
- The API does not store user or authorization data. Base Compose does not publish port 8000 and attaches the service only to its internal backend network. The optional `compose.dev.yaml` publishes it on `127.0.0.1` for host-based development only. Do not expose this service directly to an untrusted network.

Stable error responses use `{ "error": { "code": "...", "message": "..." }, "correlationId": "..." }`. Important codes include `SERVICE_AUTH_NOT_CONFIGURED`, `SERVICE_AUTH_REQUIRED`, `MODEL_MANIFEST_NOT_CONFIGURED`, `MODEL_MANIFEST_INVALID`, `MODEL_NOT_READY`, `MODEL_HASH_MISMATCH`, `MODEL_ARCHITECTURE_MISMATCH`, `PREPROCESSING_VERSION_MISMATCH`, `INPUT_SIZE_MISMATCH`, `MODEL_THRESHOLD_MISMATCH`, `TEST_ARTIFACT_NOT_ALLOWED`, `MODEL_FORWARD_FAILED`, `INVALID_REQUEST_ID`, `IDEMPOTENCY_CONFLICT`, `REQUEST_RECEIPT_INVALID`, `INVALID_FILE_TYPE`, `INVALID_NIFTI`, `INVALID_DIMENSIONS`, `INVALID_ORIENTATION`, `INVALID_SPATIAL_METADATA`, `INVALID_NUMERIC_RANGE`, `UPLOAD_TOO_LARGE`, `VOLUME_TOO_LARGE`, `INVALID_LABELS`, `LABEL_ALIGNMENT_INVALID`, `PREDICTION_SOURCE_MISMATCH`, `INVALID_OBJECT_REFERENCE`, `PREDICTION_STORAGE_FAILED`, and `INFERENCE_TIMEOUT`.
