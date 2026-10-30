"""Repeatable, informational latency benchmark for the prediction API."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

SAMPLE_PAYLOAD = {
    "Type": "M",
    "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6,
    "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8,
    "Tool wear [min]": 0,
    "equipment_name": "API latency benchmark",
}


class BenchmarkError(RuntimeError):
    """Raised when a benchmark request cannot produce a valid prediction."""


def _validate_prediction_response(path: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise BenchmarkError(f"{path} returned an unexpected response shape")
    if not result.get("prediction_id") or not result.get("model_version"):
        raise BenchmarkError(f"{path} response is missing prediction metadata")
    if path.endswith("/anomaly"):
        if result.get("classification") not in {"normal", "anomaly"}:
            raise BenchmarkError(f"{path} response has an invalid classification")
        score = result.get("anomaly_score")
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            raise BenchmarkError(f"{path} response has an invalid anomaly score")
    else:
        probability = result.get("failure_probability")
        if result.get("predicted_class") not in (0, 1):
            raise BenchmarkError(f"{path} response has an invalid predicted class")
        if (not isinstance(probability, (int, float)) or
                not math.isfinite(probability) or not 0 <= probability <= 1):
            raise BenchmarkError(f"{path} response has an invalid failure probability")
    return result


def post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout: float,
    *,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """POST one JSON request and require an expected prediction response."""
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        raise BenchmarkError(f"{path} returned unexpected HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise BenchmarkError(f"Could not reach {path}: {type(exc).__name__}") from None
    if status != 200:
        raise BenchmarkError(f"{path} returned unexpected HTTP {status}")
    try:
        result = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BenchmarkError(f"{path} returned invalid JSON") from None
    return _validate_prediction_response(path, result)


def summarize_latencies_ms(samples: list[float]) -> dict[str, float | int]:
    """Summarize measured milliseconds using NumPy's linear percentiles."""
    if not samples or any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError("At least one finite, nonnegative latency sample is required")
    return {
        "sample_size": len(samples),
        "p50": float(np.percentile(samples, 50, method="linear")),
        "p95": float(np.percentile(samples, 95, method="linear")),
        "p99": float(np.percentile(samples, 99, method="linear")),
        "mean": float(np.mean(samples)),
        "maximum": float(max(samples)),
    }


def benchmark_endpoint(
    base_url: str,
    path: str,
    *,
    warmup_requests: int,
    measured_requests: int,
    timeout_seconds: float,
    sender: Callable[[str, str, dict[str, Any], float], dict[str, Any]] | None = None,
    timer_ns: Callable[[], int] | None = None,
) -> dict[str, float | int]:
    """Warm up the endpoint, then time only validated measured requests."""
    sender = sender or post_json
    timer_ns = timer_ns or time.perf_counter_ns
    payload = dict(SAMPLE_PAYLOAD)
    try:
        for _ in range(warmup_requests):
            _validate_prediction_response(
                path, sender(base_url, path, payload, timeout_seconds)
            )
        samples: list[float] = []
        for _ in range(measured_requests):
            started = timer_ns()
            _validate_prediction_response(
                path, sender(base_url, path, payload, timeout_seconds)
            )
            elapsed_ns = timer_ns() - started
            samples.append(elapsed_ns / 1_000_000)
    except BenchmarkError:
        raise
    except Exception as exc:
        raise BenchmarkError(f"Benchmark failed for {path}: {type(exc).__name__}") from None
    return summarize_latencies_ms(samples)


def run_benchmark(
    base_url: str,
    *,
    warmup_requests: int = 5,
    measured_requests: int = 100,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Measure the anomaly and failure endpoints independently."""
    if warmup_requests < 0 or measured_requests < 1 or timeout_seconds <= 0:
        raise ValueError("Warm-ups must be nonnegative; requests and timeout must be positive")
    return {
        "base_url": base_url.rstrip("/"),
        "warmup_requests_per_endpoint": warmup_requests,
        "measured_requests_per_endpoint": measured_requests,
        "latency_unit": "milliseconds",
        "percentile_method": "linear interpolation (NumPy percentile)",
        "endpoints": {
            path: benchmark_endpoint(
                base_url,
                path,
                warmup_requests=warmup_requests,
                measured_requests=measured_requests,
                timeout_seconds=timeout_seconds,
            )
            for path in ("/predict/anomaly", "/predict/failure")
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument("--requests", dest="measured_requests", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(
            args.base_url,
            warmup_requests=args.warmup_requests,
            measured_requests=args.measured_requests,
            timeout_seconds=args.timeout_seconds,
        )
    except (BenchmarkError, ValueError) as exc:
        print(f"Benchmark error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
