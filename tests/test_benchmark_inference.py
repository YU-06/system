import importlib.util
import json
import os
from pathlib import Path


def benchmark_module():
    path = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "benchmark_inference.py"
    spec = importlib.util.spec_from_file_location("benchmark_inference", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentile_summary_uses_nearest_rank_for_small_samples():
    module = benchmark_module()
    assert module.percentile95([5.0, 1.0, 4.0, 3.0, 2.0]) == 5.0
    assert module.summarize([]) == {
        "count": 0,
        "mean": None,
        "median": None,
        "p95": None,
        "min": None,
        "max": None,
    }


def test_benchmark_without_real_input_writes_only_a_not_run_record(tmp_path):
    module = benchmark_module()
    output = tmp_path / "performance.json"

    assert module.main(["--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "NotRun"
    assert report["results"] is None
    assert report["input"] is None
    assert report["model"] is None
    assert report["disclaimer"]


def test_process_rss_is_measured_for_current_process_on_supported_platforms():
    module = benchmark_module()

    if module.platform.system() in {"Linux", "Windows"}:
        assert module.process_rss_bytes(os.getpid()) > 0
    else:
        assert module.process_rss_bytes(os.getpid()) is None
