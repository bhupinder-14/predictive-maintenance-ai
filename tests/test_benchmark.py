from __future__ import annotations

import json

import pytest

from scripts import benchmark_api


def test_percentile_calculation_uses_linear_numpy_percentiles() -> None:
    values = benchmark_api.summarize_latencies_ms([1, 2, 3, 4, 5])
    assert values == {
        "sample_size": 5, "p50": 3.0, "p95": 4.8, "p99": 4.96,
        "mean": 3.0, "maximum": 5,
    }


def test_benchmark_cli_arguments_and_warmups_excluded(monkeypatch, capsys) -> None:
    calls: list[str] = []
    response = {
        "prediction_id": "test-id", "model_version": "test-v1",
        "classification": "normal", "anomaly_score": -0.2,
        "predicted_class": 0, "failure_probability": 0.1,
    }
    monkeypatch.setattr(
        benchmark_api, "post_json",
        lambda base, path, payload, timeout: (calls.append(path) or response),
    )
    clock_values = iter([0, 1_000_000, 1_000_000, 3_000_000, 3_000_000, 6_000_000] * 2)
    monkeypatch.setattr(benchmark_api.time, "perf_counter_ns", lambda: next(clock_values))

    result_code = benchmark_api.main([
        "--base-url", "http://127.0.0.1:9999/", "--warmup-requests", "2",
        "--requests", "3", "--timeout-seconds", "2",
    ])
    assert result_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["base_url"] == "http://127.0.0.1:9999"
    assert result["warmup_requests_per_endpoint"] == 2
    for path in ("/predict/anomaly", "/predict/failure"):
        assert calls.count(path) == 5
        assert result["endpoints"][path]["sample_size"] == 3
        assert result["endpoints"][path]["mean"] == 2.0
        assert result["endpoints"][path]["maximum"] == 3.0


def test_benchmark_rejects_unexpected_server_response() -> None:
    with pytest.raises(benchmark_api.BenchmarkError, match="invalid predicted class"):
        benchmark_api.benchmark_endpoint(
            "http://local", "/predict/failure", warmup_requests=0,
            measured_requests=1, timeout_seconds=1,
            sender=lambda *_: {
                "prediction_id": "x", "model_version": "v1",
                "predicted_class": 3, "failure_probability": 0.1,
            },
        )


def test_benchmark_reports_http_failure_without_echoing_body() -> None:
    from urllib.error import HTTPError

    def unavailable(*args, **kwargs):
        raise HTTPError("http://local", 503, "unavailable", {}, None)

    with pytest.raises(benchmark_api.BenchmarkError, match="HTTP 503"):
        benchmark_api.post_json(
            "http://local", "/predict/anomaly", {}, 1, opener=unavailable
        )
