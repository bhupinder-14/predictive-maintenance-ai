"""Thread-safe cumulative and rolling operational metrics for one API process."""

from __future__ import annotations

from collections import Counter, deque
from threading import Lock
from time import monotonic, perf_counter
from typing import Any, Callable


class OperationalMetrics:
    """Aggregate API activity and a bounded rolling window of observations."""

    def __init__(
        self,
        *,
        window_seconds: int = 300,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("Metrics window must be at least one second")
        self._lock = Lock()
        self._clock = clock
        self.window_seconds = window_seconds
        self._started_at = clock()
        self._request_total = 0
        self._request_successful = 0
        self._request_failed = 0
        self._request_statuses: Counter[str] = Counter()
        self._endpoint_metrics: dict[str, dict[str, Any]] = {}
        self._request_duration_total_ms = 0.0
        self._request_duration_max_ms = 0.0
        self._anomaly_predictions = 0
        self._anomaly_classes: Counter[str] = Counter()
        self._failure_predictions = 0
        self._failure_classes: Counter[str] = Counter()
        self._anomaly_by_version: dict[str, Counter[str]] = {}
        self._failure_by_version: dict[str, Counter[str]] = {}
        self._prediction_errors = 0
        self._prediction_errors_by_model: Counter[str] = Counter()
        self._window_requests: deque[tuple[float, str, int, float]] = deque()
        self._window_predictions: deque[tuple[float, str, str, str]] = deque()
        self._window_errors: deque[tuple[float, str]] = deque()

    def record_request(
        self,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        *,
        prediction_error_model: str | None = None,
    ) -> None:
        """Record one completed HTTP request and its elapsed time."""
        status_key = str(status_code)
        succeeded = status_code < 400
        with self._lock:
            now = self._clock()
            self._request_total += 1
            self._request_successful += int(succeeded)
            self._request_failed += int(not succeeded)
            self._request_statuses[status_key] += 1
            self._request_duration_total_ms += duration_ms
            self._request_duration_max_ms = max(self._request_duration_max_ms, duration_ms)

            endpoint_metrics = self._endpoint_metrics.setdefault(
                endpoint,
                {
                    "requests": 0,
                    "successful": 0,
                    "failed": 0,
                    "status_codes": Counter(),
                    "duration_total_ms": 0.0,
                    "duration_max_ms": 0.0,
                },
            )
            endpoint_metrics["requests"] += 1
            endpoint_metrics["successful"] += int(succeeded)
            endpoint_metrics["failed"] += int(not succeeded)
            endpoint_metrics["status_codes"][status_key] += 1
            endpoint_metrics["duration_total_ms"] += duration_ms
            endpoint_metrics["duration_max_ms"] = max(
                endpoint_metrics["duration_max_ms"], duration_ms
            )
            self._window_requests.append((now, endpoint, status_code, duration_ms))
            if prediction_error_model is not None and not succeeded:
                self._prediction_errors += 1
                self._prediction_errors_by_model[prediction_error_model] += 1
                self._window_errors.append((now, prediction_error_model))

    def record_anomaly_prediction(
        self, classification: str, model_version: str = "unknown"
    ) -> None:
        """Record a persisted anomaly outcome and actual loaded model version."""
        with self._lock:
            self._anomaly_predictions += 1
            self._anomaly_classes[classification] += 1
            self._anomaly_by_version.setdefault(model_version, Counter())[classification] += 1
            self._window_predictions.append(
                (self._clock(), "anomaly", model_version, classification)
            )

    def record_failure_prediction(
        self, predicted_class: int, model_version: str = "unknown"
    ) -> None:
        """Record a persisted supervised failure outcome and model version."""
        class_key = str(predicted_class)
        with self._lock:
            self._failure_predictions += 1
            self._failure_classes[class_key] += 1
            self._failure_by_version.setdefault(model_version, Counter())[class_key] += 1
            self._window_predictions.append(
                (self._clock(), "failure", model_version, class_key)
            )

    def record_prediction_error(self, model_name: str) -> None:
        """Count a failed prediction API request by model family."""
        with self._lock:
            self._prediction_errors += 1
            self._prediction_errors_by_model[model_name] += 1
            self._window_errors.append((self._clock(), model_name))

    @staticmethod
    def _request_summary(
        events: list[tuple[float, str, int, float]],
    ) -> dict[str, Any]:
        endpoint_metrics: dict[str, dict[str, Any]] = {}
        status_counts: Counter[str] = Counter()
        total_duration = 0.0
        max_duration = 0.0
        successful = 0
        for _, endpoint, status_code, duration in events:
            succeeded = status_code < 400
            status_key = str(status_code)
            status_counts[status_key] += 1
            successful += int(succeeded)
            total_duration += duration
            max_duration = max(max_duration, duration)
            values = endpoint_metrics.setdefault(
                endpoint,
                {"requests": 0, "successful": 0, "failed": 0,
                 "status_codes": Counter(), "durations": []},
            )
            values["requests"] += 1
            values["successful"] += int(succeeded)
            values["failed"] += int(not succeeded)
            values["status_codes"][status_key] += 1
            values["durations"].append(duration)

        by_endpoint = {}
        for endpoint, values in endpoint_metrics.items():
            durations = values.pop("durations")
            by_endpoint[endpoint] = {
                **values,
                "status_codes": dict(sorted(values["status_codes"].items())),
                "duration_ms": {
                    "total": round(sum(durations), 3),
                    "average": round(sum(durations) / len(durations), 3),
                    "max": round(max(durations), 3),
                },
            }
        return {
            "total": len(events),
            "successful": successful,
            "failed": len(events) - successful,
            "status_codes": dict(sorted(status_counts.items())),
            "by_endpoint": dict(sorted(by_endpoint.items())),
            "duration_ms": {
                "total": round(total_duration, 3),
                "average": round(total_duration / len(events), 3) if events else 0.0,
                "max": round(max_duration, 3),
            },
        }

    @staticmethod
    def _prediction_summary(
        events: list[tuple[float, str, str, str]],
        error_events: list[tuple[float, str]],
    ) -> dict[str, Any]:
        anomaly: dict[str, Any] = {
            "total": 0, "normal": 0, "anomaly": 0, "by_model_version": {}
        }
        failure: dict[str, Any] = {
            "total": 0, "predicted_class_0": 0, "predicted_class_1": 0,
            "by_model_version": {},
        }
        for _, family, version, outcome in events:
            target = anomaly if family == "anomaly" else failure
            target["total"] += 1
            if family == "anomaly":
                target[outcome] += 1
                version_counts = target["by_model_version"].setdefault(
                    version, {"total": 0, "normal": 0, "anomaly": 0}
                )
                version_counts[outcome] += 1
            else:
                target[f"predicted_class_{outcome}"] += 1
                version_counts = target["by_model_version"].setdefault(
                    version, {"total": 0, "predicted_class_0": 0,
                              "predicted_class_1": 0}
                )
                version_counts[f"predicted_class_{outcome}"] += 1
            version_counts["total"] += 1
        errors_by_model = Counter(model for _, model in error_events)
        return {
            "anomaly": anomaly,
            "failure": failure,
            "errors": {
                "total": len(error_events),
                "by_model": dict(sorted(errors_by_model.items())),
            },
        }

    def snapshot(
        self,
        *,
        model_availability: dict[str, dict[str, str | bool | None]] | None = None,
        database_available: bool | None = None,
    ) -> dict[str, Any]:
        """Return cumulative counters and rolling-window summaries atomically."""
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            while self._window_requests and self._window_requests[0][0] < cutoff:
                self._window_requests.popleft()
            while self._window_predictions and self._window_predictions[0][0] < cutoff:
                self._window_predictions.popleft()
            while self._window_errors and self._window_errors[0][0] < cutoff:
                self._window_errors.popleft()

            cumulative_endpoints: dict[str, dict[str, Any]] = {}
            for endpoint, values in self._endpoint_metrics.items():
                count = values["requests"]
                cumulative_endpoints[endpoint] = {
                    "requests": count,
                    "successful": values["successful"],
                    "failed": values["failed"],
                    "status_codes": dict(sorted(values["status_codes"].items())),
                    "duration_ms": {
                        "total": round(values["duration_total_ms"], 3),
                        "average": round(values["duration_total_ms"] / count, 3),
                        "max": round(values["duration_max_ms"], 3),
                    },
                }
            anomaly_versions = {
                version: {
                    "total": sum(counts.values()),
                    "normal": counts["normal"],
                    "anomaly": counts["anomaly"],
                }
                for version, counts in sorted(self._anomaly_by_version.items())
            }
            failure_versions = {
                version: {
                    "total": sum(counts.values()),
                    "predicted_class_0": self._failure_by_version[version]["0"],
                    "predicted_class_1": self._failure_by_version[version]["1"],
                }
                for version in sorted(self._failure_by_version)
                for counts in [self._failure_by_version[version]]
            }
            request_summary = {
                "total": self._request_total,
                "successful": self._request_successful,
                "failed": self._request_failed,
                "status_codes": dict(sorted(self._request_statuses.items())),
                "by_endpoint": dict(sorted(cumulative_endpoints.items())),
                "duration_ms": {
                    "total": round(self._request_duration_total_ms, 3),
                    "average": round(
                        self._request_duration_total_ms / self._request_total, 3
                    ) if self._request_total else 0.0,
                    "max": round(self._request_duration_max_ms, 3),
                },
            }
            prediction_summary = {
                "anomaly": {
                    "total": self._anomaly_predictions,
                    "normal": self._anomaly_classes["normal"],
                    "anomaly": self._anomaly_classes["anomaly"],
                    "by_model_version": anomaly_versions,
                },
                "failure": {
                    "total": self._failure_predictions,
                    "predicted_class_0": self._failure_classes["0"],
                    "predicted_class_1": self._failure_classes["1"],
                    "by_model_version": failure_versions,
                },
                "errors": {
                    "total": self._prediction_errors,
                    "by_model": dict(sorted(self._prediction_errors_by_model.items())),
                },
            }
            window_requests = list(self._window_requests)
            window_predictions = list(self._window_predictions)
            window_errors = list(self._window_errors)
            return {
                "requests": request_summary,
                "predictions": prediction_summary,
                "runtime": {
                    "uptime_seconds": round(now - self._started_at, 3),
                    "metrics_storage": "in_memory_process_local",
                },
                "availability": {
                    "models": model_availability or {},
                    "database_available": database_available,
                },
                "rolling_window": {
                    "window_seconds": self.window_seconds,
                    "requests": self._request_summary(window_requests),
                    "predictions": self._prediction_summary(
                        window_predictions, window_errors
                    ),
                },
            }


class RequestMetricsMiddleware:
    """ASGI middleware that measures requests once without buffering bodies."""

    def __init__(self, app, *, metrics: OperationalMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        response_status = 500

        async def send_and_capture(message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_and_capture)
        finally:
            duration_ms = (perf_counter() - started) * 1000
            route = scope.get("route")
            endpoint = getattr(route, "path", "unmatched")
            prediction_error_model = None
            if response_status >= 400:
                if endpoint == "/predict/anomaly":
                    prediction_error_model = "anomaly"
                elif endpoint == "/predict/failure":
                    prediction_error_model = "failure"
            self.metrics.record_request(
                endpoint,
                response_status,
                duration_ms,
                prediction_error_model=prediction_error_model,
            )
