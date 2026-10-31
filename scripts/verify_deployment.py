"""Smoke-check a running deployment through its public HTTP API.

The script creates two prediction records and one drift report. It also
retrieves equipment and reading history. Use a disposable database/volume when
running it as a deployment acceptance check; it never connects to SQLite
directly.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DeploymentVerificationError(RuntimeError):
    """Raised when the deployed API does not meet the smoke-check contract."""


SENSOR_ROW: dict[str, Any] = {
    "Type": "M",
    "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6,
    "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8,
    "Tool wear [min]": 0,
}
METRICS_SECTIONS = {"requests", "predictions", "runtime", "availability", "rolling_window"}
DRIFT_FEATURE_FIELDS = {
    "feature_name", "method", "statistic", "threshold", "drift_detected",
    "reference_sample_size", "current_sample_size",
}


def _request(
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    timeout: float,
) -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        body = exc.read()
        exc.close()
        return exc.code, body
    except (URLError, TimeoutError, OSError) as exc:
        raise DeploymentVerificationError(
            f"Could not reach {path}: {type(exc).__name__}"
        ) from None


def _json_value(
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    timeout: float,
    expected_status: int = 200,
) -> Any:
    status_code, body = _request(base_url, path, payload=payload, timeout=timeout)
    if status_code != expected_status:
        raise DeploymentVerificationError(
            f"{path} returned HTTP {status_code}; expected HTTP {expected_status}"
        )
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DeploymentVerificationError(f"{path} did not return valid JSON") from None


def _json_response(
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    timeout: float,
) -> dict[str, Any]:
    value = _json_value(base_url, path, payload=payload, timeout=timeout)
    if not isinstance(value, dict):
        raise DeploymentVerificationError(f"{path} returned an unexpected response shape")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DeploymentVerificationError(message)


def _validate_prediction_record(
    family: str,
    prediction: dict[str, Any],
    persisted: dict[str, Any],
) -> None:
    """Compare inference response to the corresponding persisted record schema."""
    prediction_id = prediction.get("prediction_id")
    _require(
        isinstance(prediction_id, str) and bool(prediction_id),
        f"/predict/{family} omitted prediction_id",
    )
    _require(
        persisted.get("id") == prediction_id,
        f"/predictions/{prediction_id} returned a different prediction ID",
    )
    version = prediction.get("model_version")
    _require(
        isinstance(version, str) and version.startswith(f"{family}_"),
        f"/predict/{family} returned an unexpected model family",
    )
    _require(
        persisted.get("model_version") == version,
        f"/predictions/{prediction_id} model version did not match",
    )
    for field in ("equipment_id", "reading_id"):
        _require(
            persisted.get(field) == prediction.get(field),
            f"/predictions/{prediction_id} {field} did not match",
        )

    if family == "anomaly":
        score = prediction.get("anomaly_score")
        classification = prediction.get("classification")
        _require(
            classification in ("normal", "anomaly")
            and isinstance(score, (int, float))
            and math.isfinite(score),
            "Anomaly prediction response has invalid result fields",
        )
        _require(
            persisted.get("failure_probability") is None
            and persisted.get("is_anomaly") is (classification == "anomaly")
            and isinstance(persisted.get("anomaly_score"), (int, float))
            and math.isclose(persisted["anomaly_score"], score, rel_tol=0, abs_tol=1e-12),
            f"/predictions/{prediction_id} anomaly result did not match",
        )
    elif family == "failure":
        probability = prediction.get("failure_probability")
        _require(
            prediction.get("predicted_class") in (0, 1)
            and isinstance(probability, (int, float))
            and math.isfinite(probability)
            and 0 <= probability <= 1,
            "Failure prediction response has invalid result fields",
        )
        _require(
            persisted.get("anomaly_score") is None
            and persisted.get("is_anomaly") is None
            and isinstance(persisted.get("failure_probability"), (int, float))
            and math.isclose(
                persisted["failure_probability"], probability, rel_tol=0, abs_tol=1e-12
            ),
            f"/predictions/{prediction_id} failure result did not match",
        )
    else:
        raise DeploymentVerificationError(f"Unsupported prediction family: {family}")


def _validate_equipment_history(
    equipment: dict[str, Any],
    history: dict[str, Any],
    predictions: list[tuple[str, dict[str, Any]]],
) -> None:
    equipment_id = equipment["id"]
    _require(
        isinstance(history.get("equipment"), dict)
        and history["equipment"].get("id") == equipment_id,
        "Equipment history returned a different equipment record",
    )
    items = history.get("items")
    _require(isinstance(items, list), "Equipment history omitted its items list")

    # Empty items are a valid history response for equipment without readings.
    persisted_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for entry in items:
        _require(isinstance(entry, dict), "Equipment history contains an invalid entry")
        reading = entry.get("reading")
        summaries = entry.get("predictions")
        _require(
            isinstance(reading, dict) and isinstance(summaries, list),
            "Equipment history entry omitted its reading or prediction list",
        )
        _require(
            reading.get("equipment_id") == equipment_id,
            "Equipment history contains a reading for another equipment record",
        )
        for summary in summaries:
            _require(isinstance(summary, dict), "Equipment history has an invalid prediction")
            persisted_by_id[str(summary.get("id"))] = (reading, summary)

    for family, prediction in predictions:
        prediction_id = str(prediction["prediction_id"])
        _require(
            prediction_id in persisted_by_id,
            f"Equipment history omitted persisted {family} prediction {prediction_id}",
        )
        reading, summary = persisted_by_id[prediction_id]
        _require(
            reading.get("id") == prediction.get("reading_id")
            and summary.get("model_version") == prediction.get("model_version"),
            f"Equipment history result for {prediction_id} did not match",
        )
        if family == "anomaly":
            _require(
                summary.get("is_anomaly") is (prediction["classification"] == "anomaly")
                and summary.get("failure_probability") is None
                and isinstance(summary.get("anomaly_score"), (int, float))
                and math.isfinite(summary["anomaly_score"])
                and math.isclose(
                    summary["anomaly_score"],
                    prediction["anomaly_score"],
                    rel_tol=0,
                    abs_tol=1e-12,
                ),
                f"Equipment history anomaly result for {prediction_id} did not match",
            )
        else:
            _require(
                summary.get("anomaly_score") is None
                and summary.get("is_anomaly") is None
                and isinstance(summary.get("failure_probability"), (int, float))
                and math.isfinite(summary["failure_probability"])
                and math.isclose(
                    summary["failure_probability"],
                    prediction["failure_probability"],
                    rel_tol=0,
                    abs_tol=1e-12,
                ),
                f"Equipment history failure result for {prediction_id} did not match",
            )


def _validate_metrics_equivalence(
    summary: dict[str, Any],
    alias: dict[str, Any],
) -> None:
    """Compare stable metric fields; request snapshots legitimately differ."""
    _require(
        METRICS_SECTIONS.issubset(summary) and METRICS_SECTIONS.issubset(alias),
        "A metrics endpoint omitted required sections",
    )
    for response in (summary, alias):
        _require(
            all(isinstance(response.get(section), dict) for section in METRICS_SECTIONS)
            and isinstance(response["rolling_window"].get("predictions"), dict)
            and isinstance(response["requests"], dict)
            and isinstance(response["requests"].get("by_endpoint"), dict)
            and isinstance(response["rolling_window"].get("requests"), dict),
            "Metrics response has an invalid request-summary shape",
        )
    stable_sections = (
        "predictions",
        "availability",
    )
    _require(
        all(summary[key] == alias[key] for key in stable_sections),
        "Metrics aliases returned different prediction or availability data",
    )
    _require(
        summary["runtime"].get("metrics_storage")
        == alias["runtime"].get("metrics_storage")
        and summary["rolling_window"].get("window_seconds")
        == alias["rolling_window"].get("window_seconds")
        and summary["rolling_window"].get("predictions")
        == alias["rolling_window"].get("predictions"),
        "Metrics aliases returned different stable runtime or rolling data",
    )


def _parse_timestamp(value: Any) -> datetime:
    _require(isinstance(value, str), "Drift report omitted a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise DeploymentVerificationError("Drift report contains an invalid timestamp") from None
    _require(parsed.tzinfo is not None, "Drift report timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_saved_drift(
    evaluated: dict[str, Any],
    latest: dict[str, Any],
    previous_report_id: int | None,
) -> int:
    features = evaluated.get("features")
    _require(
        isinstance(features, list)
        and len(features) == 6
        and all(isinstance(feature, dict) and DRIFT_FEATURE_FIELDS.issubset(feature)
                for feature in features),
        "Drift POST response omitted complete feature results",
    )
    report_id = latest.get("report_id")
    _require(
        isinstance(report_id, int) and report_id > 0,
        "Latest persisted drift report omitted a valid report ID",
    )
    if previous_report_id is not None:
        _require(
            report_id > previous_report_id,
            "GET /monitoring/drift did not return a newer persisted report",
        )
    _require(
        latest.get("features") == features,
        "GET /monitoring/drift feature results differ from the saved POST report",
    )
    _require(
        latest.get("overall_status") == evaluated.get("overall_status")
        and latest.get("reference_version") == evaluated.get("reference_version"),
        "GET /monitoring/drift metadata differs from the evaluated report",
    )
    metadata = latest.get("report_metadata")
    _require(isinstance(metadata, dict), "Saved drift report omitted report metadata")
    _require(
        _parse_timestamp(metadata.get("generated_at"))
        == _parse_timestamp(evaluated.get("generated_at")),
        "GET /monitoring/drift did not return the saved evaluation timestamp",
    )
    _require(
        latest.get("created_at") is not None
        and latest.get("methodology")
        and latest.get("batch_description"),
        "Saved drift report omitted database-only persistence metadata",
    )
    return report_id


def verify_deployment(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Exercise the API and confirm prediction/history/drift persistence."""
    health = _json_response(base_url, "/health", timeout=timeout)
    _require(health.get("status") == "ok", "/health returned an invalid status")
    readiness = _json_response(base_url, "/ready", timeout=timeout)
    _require(
        readiness.get("status") == "ready"
        and readiness.get("database") is True
        and isinstance(readiness.get("models"), dict)
        and readiness["models"].get("anomaly") is True
        and readiness["models"].get("failure") is True,
        "/ready did not report both models and the database available",
    )
    openapi = _json_response(base_url, "/openapi.json", timeout=timeout)
    paths = openapi.get("paths")
    _require(
        isinstance(paths, dict)
        and {
            "/predict/anomaly", "/predict/failure", "/equipment",
            "/equipment/{equipment_id}/history", "/predictions/{prediction_id}",
            "/metrics/summary", "/monitoring/metrics", "/monitoring/drift",
        }.issubset(paths),
        "/openapi.json omitted a documented API endpoint",
    )
    docs_status, _ = _request(base_url, "/docs", timeout=timeout)
    _require(docs_status == 200, f"/docs returned HTTP {docs_status}; expected HTTP 200")

    common = dict(SENSOR_ROW, equipment_name="Docker deployment verification")
    prediction_results: list[tuple[str, dict[str, Any]]] = []
    prediction_ids: dict[str, str] = {}
    equipment_id: int | None = None
    for family in ("anomaly", "failure"):
        result = _json_response(
            base_url, f"/predict/{family}", payload=common, timeout=timeout
        )
        prediction_id = result.get("prediction_id")
        _require(
            isinstance(prediction_id, str) and bool(prediction_id),
            f"/predict/{family} omitted prediction_id",
        )
        if equipment_id is None:
            equipment_id = result.get("equipment_id")
        _require(
            isinstance(equipment_id, int)
            and result.get("equipment_id") == equipment_id,
            f"/predict/{family} returned inconsistent equipment_id",
        )
        persisted = _json_response(
            base_url, f"/predictions/{prediction_id}", timeout=timeout
        )
        _validate_prediction_record(family, result, persisted)
        prediction_ids[family] = prediction_id
        prediction_results.append((family, result))

    equipment_name = "Docker deployment verification"
    equipment: dict[str, Any] | None = None
    # The endpoint is paginated and ordered by ID ascending, so walk pages to
    # find recently created equipment even when the database has >100 rows.
    for offset in range(0, 100_000, 100):
        page = _json_value(
            base_url,
            f"/equipment?limit=100&offset={offset}",
            timeout=timeout,
        )
        _require(isinstance(page, list), "GET /equipment did not return a list")
        for item in page:
            _require(
                isinstance(item, dict)
                and {"id", "name", "equipment_type", "created_at"}.issubset(item),
                "GET /equipment returned an invalid equipment record",
            )
            if item["id"] == equipment_id:
                equipment = item
                break
        if equipment is not None or len(page) < 100:
            break
    _require(
        equipment is not None and equipment["name"] == equipment_name,
        "GET /equipment omitted the equipment created by the prediction workflow",
    )

    history = _json_response(
        base_url, f"/equipment/{equipment_id}/history", timeout=timeout
    )
    _validate_equipment_history(equipment, history, prediction_results)

    previous_status, previous_body = _request(
        base_url, "/monitoring/drift", timeout=timeout
    )
    if previous_status == 404:
        previous_report_id = None
    elif previous_status == 200:
        try:
            previous = json.loads(previous_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DeploymentVerificationError(
                "Existing drift report response was not valid JSON"
            ) from None
        _require(isinstance(previous, dict), "Existing drift report had an invalid shape")
        previous_report_id = previous.get("report_id")
        _require(
            isinstance(previous_report_id, int),
            "Existing drift report omitted a valid report ID",
        )
    else:
        raise DeploymentVerificationError(
            f"GET /monitoring/drift returned HTTP {previous_status}"
        )

    evaluated = _json_response(
        base_url,
        "/monitoring/drift",
        payload={"observations": [dict(SENSOR_ROW) for _ in range(20)]},
        timeout=timeout,
    )
    latest = _json_response(base_url, "/monitoring/drift", timeout=timeout)
    drift_report_id = _validate_saved_drift(evaluated, latest, previous_report_id)

    metrics_summary = _json_response(base_url, "/metrics/summary", timeout=timeout)
    metrics_alias = _json_response(base_url, "/monitoring/metrics", timeout=timeout)
    _validate_metrics_equivalence(metrics_summary, metrics_alias)
    return {
        "status": "passed",
        "base_url": base_url.rstrip("/"),
        "checked_endpoints": [
            "/health", "/ready", "/docs", "/openapi.json",
            "/predict/anomaly", "/predict/failure", "/predictions/{id}",
            "/equipment", "/equipment/{id}/history",
            "/monitoring/metrics", "/metrics/summary",
            "POST /monitoring/drift", "GET /monitoring/drift",
        ],
        "equipment_id": equipment_id,
        "prediction_ids": prediction_ids,
        "drift_report_id": drift_report_id,
        "note": "This smoke check writes two predictions and a drift report to the target application database.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    try:
        result = verify_deployment(args.base_url, timeout=args.timeout_seconds)
    except DeploymentVerificationError as exc:
        print(f"Deployment verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
