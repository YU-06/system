"""Reproducible, research-artifact-only inference benchmark.

The script deliberately refuses to benchmark synthetic models and writes no input path,
file name, image data, token, or per-case identifier to its report.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
import nibabel as nib
import numpy as np
import onnxruntime
from brainseg_inference.manifest import ModelManifest
from brainseg_inference.runtime import OnnxPredictor
from brainseg_inference.settings import Settings
from training import DISCLAIMER
from training.preprocessing import normalize_volume, resize_image

SCRIPT_VERSION = "1.0.0"
CONCURRENCY_LEVELS = (1, 5, 10)


def percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def summarize(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": percentile95(values),
        "min": min(values),
        "max": max(values),
    }


def process_rss_bytes(pid: int) -> int | None:
    if pid < 1:
        return None
    current_platform = platform.system()
    if current_platform == "Linux":
        try:
            resident_pages = int(Path(f"/proc/{pid}/statm").read_text(encoding="ascii").split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            return None
    if current_platform == "Windows":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            return None
        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            return int(counters.WorkingSetSize)
        finally:
            kernel.CloseHandle(handle)
    return None


def gpu_hardware() -> dict[str, Any]:
    executable = "nvidia-smi.exe" if sys.platform == "win32" else "nvidia-smi"
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        return {"status": "Detected", "devices": result.stdout.strip().splitlines()}
    except (OSError, subprocess.SubprocessError):
        return {"status": "NotDetected"}


def write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)


def source_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "NotAvailable"


def base_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "scriptVersion": SCRIPT_VERSION,
        "runId": f"phase8-{uuid.uuid4().hex}",
        "status": "NotRun",
        "disclaimer": DISCLAIMER,
        "blockers": [],
        "protocol": {
            "warmupRequests": args.warmups,
            "singleForwardWarmups": args.forward_warmups,
            "singleForwardRepeats": args.forward_repeats,
            "sequentialRepeats": args.repeats,
            "requestTimeoutSeconds": 180,
            "concurrencyLevels": list(CONCURRENCY_LEVELS),
            "requestsPerWorkerAtEachConcurrency": args.concurrent_repeats,
            "sustainedSequentialRequests": 50,
            "timingBoundaries": {
                "singleForwardMilliseconds": "ONNX session.run only, one 256x256 slice",
                "caseInferenceMilliseconds": "API-reported sum of model forward batches",
                "completeRequestMilliseconds": (
                    "Client wall clock from multipart POST to response body"
                ),
            },
            "synchronization": (
                "ONNX Runtime CPUExecutionProvider; GPU synchronization is not applicable"
            ),
            "resourceMonitoring": (
                "Inference service RSS sampled only when --service-pid is supplied"
            ),
        },
        "environment": {
            "sourceCommit": source_commit(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "NotReported",
            "logicalCpuCount": os.cpu_count(),
            "onnxruntime": onnxruntime.__version__,
            "gpuHardware": gpu_hardware(),
        },
        "model": None,
        "input": None,
        "results": None,
    }


def not_run(report: dict[str, Any], reason: str) -> dict[str, Any]:
    report["status"] = "NotRun"
    report["blockers"].append(reason)
    return report


def safe_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
        code = payload.get("error", {}).get("code")
        if isinstance(code, str) and code and len(code) <= 80:
            return code
    except (ValueError, AttributeError):
        pass
    return f"HTTP_{response.status_code}"


def percentile_summary(samples: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [float(sample[field]) for sample in samples if sample.get(field) is not None]
    return summarize(values)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, help="Controlled local NIfTI input; its path is never recorded"
    )
    parser.add_argument("--manifest", type=Path, help="Local verified research model manifest")
    parser.add_argument(
        "--base-url", default=os.environ.get("BRAINSEG_BENCHMARK_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/quality/phase8-performance.json")
    )
    parser.add_argument(
        "--service-pid", type=int, help="Local inference service PID for RSS sampling"
    )
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--forward-warmups", type=int, default=5)
    parser.add_argument("--forward-repeats", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--concurrent-repeats", type=int, default=10)
    parser.add_argument(
        "--allow-persistent-results",
        action="store_true",
        help=(
            "Acknowledge that complete API requests persist prediction objects; "
            "use disposable storage"
        ),
    )
    args = parser.parse_args(argv)
    for name in ("warmups", "forward_warmups"):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    for name in ("forward_repeats", "repeats", "concurrent_repeats"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = base_report(args)
    output = args.output
    api_key = os.environ.get("BRAINSEG_BENCHMARK_API_KEY")
    if args.input is None or not args.input.is_file():
        not_run(report, "A controlled, real NIfTI input was not supplied.")
        write_report(output, report)
        print(f"NotRun: controlled input unavailable; report written to {output}")
        return 0
    if args.manifest is None or not args.manifest.is_file():
        not_run(report, "A local model manifest and verified research weights were not supplied.")
        write_report(output, report)
        print(f"NotRun: local research model unavailable; report written to {output}")
        return 0
    if not args.allow_persistent_results:
        not_run(
            report, "Use --allow-persistent-results only with disposable inference object storage."
        )
        write_report(output, report)
        print(
            "NotRun: persistent result storage was not explicitly acknowledged; "
            f"report written to {output}"
        )
        return 0
    if not api_key:
        not_run(report, "BRAINSEG_BENCHMARK_API_KEY is not configured.")
        write_report(output, report)
        print(f"NotRun: service authentication is unavailable; report written to {output}")
        return 0

    try:
        manifest, weights_path, manifest_hash = ModelManifest.load(
            Settings(_env_file=None, model_manifest_path=args.manifest)
        )
    except Exception as error:
        not_run(
            report,
            "The local model manifest did not validate as a research artifact: "
            + getattr(error, "code", type(error).__name__),
        )
        write_report(output, report)
        print(f"NotRun: verified research model unavailable; report written to {output}")
        return 0

    if args.input.suffix.lower() not in {".nii", ".gz"} or (
        args.input.suffix.lower() == ".gz" and not args.input.name.lower().endswith(".nii.gz")
    ):
        not_run(report, "Input must be a .nii or .nii.gz NIfTI file.")
        write_report(output, report)
        print(f"NotRun: input is not an accepted NIfTI file; report written to {output}")
        return 0
    try:
        image = nib.load(str(args.input))
        if len(image.shape) != 3 or any(int(axis) < 1 for axis in image.shape):
            not_run(report, "Input must be a non-empty three-dimensional volume.")
            write_report(output, report)
            print(
                "NotRun: input dimensions are outside the benchmark protocol; "
                f"report written to {output}"
            )
            return 0
        volume = np.asarray(image.dataobj, dtype=np.float32)
        if not np.isfinite(volume).all():
            not_run(report, "Input contains non-finite values.")
            write_report(output, report)
            print(f"NotRun: input values are invalid; report written to {output}")
            return 0
    except Exception as error:
        not_run(report, f"Input could not be read as NIfTI: {type(error).__name__}")
        write_report(output, report)
        print(f"NotRun: input could not be read; report written to {output}")
        return 0

    data = args.input.read_bytes()
    report["input"] = {
        "sizeBytes": len(data),
        "dimensions": [int(axis) for axis in volume.shape],
        "voxelCount": int(volume.size),
        "fileType": ".nii.gz" if args.input.name.lower().endswith(".nii.gz") else ".nii",
    }
    report["model"] = {
        "modelVersion": manifest.model_version,
        "architecture": manifest.architecture,
        "preprocessingVersion": manifest.preprocessing_version,
        "inputSize": manifest.input_size,
        "threshold": manifest.threshold,
        "artifactKind": manifest.artifact_kind,
        "weightSha256": manifest.weight_sha256,
        "manifestSha256": manifest_hash,
        "weightFileSizeBytes": weights_path.stat().st_size,
        "provider": "CPUExecutionProvider",
    }
    predictor = OnnxPredictor(str(weights_path), manifest, Settings(_env_file=None))
    normalized = normalize_volume(volume)
    sample = resize_image(normalized[:, :, volume.shape[2] // 2], manifest.input_size)
    single_slice = np.asarray([sample], dtype=np.float32)
    for _ in range(args.forward_warmups):
        predictor.predict_batch(single_slice)
    forward_samples = [
        predictor.predict_batch(single_slice)[1] for _ in range(args.forward_repeats)
    ]

    token = f"Bearer {api_key}"
    headers = {"Authorization": token}
    errors: dict[str, int] = {}
    errors_lock = threading.Lock()

    def record_error(code: str) -> None:
        with errors_lock:
            errors[code] = errors.get(code, 0) + 1

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=180.0) as client:
        try:
            models_response = client.get("/models")
            models_response.raise_for_status()
            models_payload = models_response.json()
            matched = any(
                model.get("modelVersion") == manifest.model_version
                and model.get("artifactKind") == "research"
                and model.get("preprocessingVersion") == manifest.preprocessing_version
                and model.get("threshold") == manifest.threshold
                for model in models_payload.get("models", [])
            )
        except (httpx.HTTPError, ValueError):
            matched = False
        if not matched:
            not_run(
                report,
                "Inference service is unavailable or does not expose the same research model.",
            )
            write_report(output, report)
            print(f"NotRun: matching research service unavailable; report written to {output}")
            return 0

        def segment_once() -> dict[str, Any]:
            request_id = f"phase8bench-{uuid.uuid4().hex}"
            correlation = f"phase8-{uuid.uuid4().hex}"
            started = time.perf_counter()
            try:
                response = client.post(
                    "/v1/segment",
                    headers={"X-Correlation-Id": correlation},
                    data={"requestId": request_id},
                    files={
                        "file": (
                            "benchmark.nii.gz"
                            if args.input.name.lower().endswith(".nii.gz")
                            else "benchmark.nii",
                            data,
                            "application/gzip"
                            if args.input.name.lower().endswith(".nii.gz")
                            else "application/octet-stream",
                        )
                    },
                )
                elapsed = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    code = safe_error_code(response)
                    record_error(code)
                    return {"ok": False, "errorCode": code, "completeRequestMilliseconds": elapsed}
                payload = response.json()
                if (
                    payload.get("modelVersion") != manifest.model_version
                    or payload.get("artifactKind") != "research"
                    or payload.get("weightSha256") != manifest.weight_sha256
                    or payload.get("requestId") != request_id
                ):
                    record_error("MODEL_PROVENANCE_MISMATCH")
                    return {
                        "ok": False,
                        "errorCode": "MODEL_PROVENANCE_MISMATCH",
                        "completeRequestMilliseconds": elapsed,
                    }
                timings = payload["timings"]
                return {
                    "ok": True,
                    "completeRequestMilliseconds": elapsed,
                    "caseInferenceMilliseconds": float(timings["inferenceMilliseconds"]),
                    "preprocessingMilliseconds": float(timings["preprocessingMilliseconds"]),
                    "postprocessingMilliseconds": float(timings["postprocessingMilliseconds"]),
                }
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                record_error("BENCHMARK_REQUEST_FAILED")
                return {"ok": False, "errorCode": "BENCHMARK_REQUEST_FAILED"}

        warmups = [segment_once() for _ in range(args.warmups)]
        resource_samples: list[int] = []
        sampler_stop = threading.Event()

        def sample_service_memory() -> None:
            if args.service_pid is None:
                return
            while not sampler_stop.is_set():
                memory = process_rss_bytes(args.service_pid)
                if memory is not None:
                    resource_samples.append(memory)
                sampler_stop.wait(0.1)

        sampler = threading.Thread(target=sample_service_memory, daemon=True)
        sampler.start()
        sequential = [segment_once() for _ in range(args.repeats)]
        concurrency: dict[str, Any] = {}
        for level in CONCURRENCY_LEVELS:
            count = level * args.concurrent_repeats
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=level) as executor:
                futures = [executor.submit(segment_once) for _ in range(count)]
                samples = [future.result() for future in as_completed(futures)]
            elapsed = time.perf_counter() - started
            latency = [
                float(sample["completeRequestMilliseconds"])
                for sample in samples
                if sample.get("completeRequestMilliseconds") is not None
            ]
            concurrency[str(level)] = {
                "requests": count,
                "successes": sum(bool(sample.get("ok")) for sample in samples),
                "failures": count - sum(bool(sample.get("ok")) for sample in samples),
                "elapsedSeconds": elapsed,
                "throughputRequestsPerSecond": count / elapsed if elapsed else None,
                "completeRequestP95Milliseconds": percentile95(latency),
            }
        memory_before = process_rss_bytes(args.service_pid) if args.service_pid else None
        sustained = [segment_once() for _ in range(50)]
        memory_after = process_rss_bytes(args.service_pid) if args.service_pid else None
        sampler_stop.set()
        sampler.join(timeout=1)

    report["results"] = {
        "warmupSuccesses": sum(bool(sample.get("ok")) for sample in warmups),
        "singleForwardMilliseconds": summarize(forward_samples),
        "sequential": {
            "requests": len(sequential),
            "successes": sum(bool(sample.get("ok")) for sample in sequential),
            "failures": len(sequential) - sum(bool(sample.get("ok")) for sample in sequential),
            "completeRequestMilliseconds": percentile_summary(
                sequential, "completeRequestMilliseconds"
            ),
            "caseInferenceMilliseconds": percentile_summary(
                sequential, "caseInferenceMilliseconds"
            ),
            "preprocessingMilliseconds": percentile_summary(
                sequential, "preprocessingMilliseconds"
            ),
            "postprocessingMilliseconds": percentile_summary(
                sequential, "postprocessingMilliseconds"
            ),
        },
        "concurrency": concurrency,
        "sustained50": {
            "requests": 50,
            "successes": sum(bool(sample.get("ok")) for sample in sustained),
            "failures": 50 - sum(bool(sample.get("ok")) for sample in sustained),
            "successRate": sum(bool(sample.get("ok")) for sample in sustained) / 50,
            "serviceRssBeforeBytes": memory_before,
            "serviceRssAfterBytes": memory_after,
            "serviceRssPeakSampledBytes": max(resource_samples, default=None),
            "serviceRssDeltaBytes": (
                memory_after - memory_before
                if memory_before is not None and memory_after is not None
                else None
            ),
            "resourceMonitoringStatus": (
                "Measured"
                if memory_before is not None and memory_after is not None
                else "NotRun: local --service-pid not supplied or not readable"
            ),
        },
        "errorCodeCounts": errors,
        "gpuInference": {
            "status": "NotRun",
            "reason": "The current inference runtime is configured for CPUExecutionProvider.",
        },
    }
    report["status"] = (
        "Pass"
        if all(bool(sample.get("ok")) for sample in warmups)
        and all(
            section["failures"] == 0
            for section in [
                report["results"]["sequential"],
                *report["results"]["concurrency"].values(),
                report["results"]["sustained50"],
            ]
        )
        else "Fail"
    )
    write_report(output, report)
    print(f"{report['status']}: benchmark report written to {output}")
    return 0 if report["status"] == "Pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
