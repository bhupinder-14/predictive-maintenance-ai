from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_deployment import (
    DeploymentVerificationError,
    _validate_equipment_history,
    _validate_metrics_equivalence,
    _validate_prediction_record,
    _validate_saved_drift,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("DRIFT_KS_ALPHA", "1.0", "DRIFT_KS_ALPHA must be greater than 0 and less than 1"),
        ("LOG_LEVEL", "TRACE", "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"),
    ],
)
def test_invalid_runtime_configuration_fails_clearly_at_import(
    setting: str, value: str, message: str
) -> None:
    environment = os.environ.copy()
    environment[setting] = value
    result = subprocess.run(
        [sys.executable, "-c", "import src.config"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert message in result.stderr


def test_deployment_verification_command_exposes_cli_options() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_deployment.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--base-url" in result.stdout
    assert "--timeout-seconds" in result.stdout


def test_container_build_context_contains_runtime_artifacts_and_excludes_dev_files() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    runtime_requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "COPY requirements.txt" in dockerfile
    assert "COPY src/" in dockerfile
    assert "DATABASE_URL=sqlite:////var/lib/predictive-maintenance/predictive_maintenance.db" in dockerfile
    assert "chown 10001:10001 /var/lib/predictive-maintenance" in dockerfile
    for model_artifact in (
        "anomaly_v1_preprocessor.joblib",
        "anomaly_v1_estimator.joblib",
        "anomaly_v1_metadata.json",
        "failure_v1_preprocessor.joblib",
        "failure_v1_estimator.joblib",
        "failure_v1_metadata.json",
    ):
        assert model_artifact in dockerfile
    assert "COPY data/reference/drift_reference_v1.json" in dockerfile
    for required_path in (
        "requirements.txt",
        "src/api/main.py",
        "data/reference/drift_reference_v1.json",
        "scripts/benchmark_api.py",
        "scripts/verify_deployment.py",
        "models/anomaly_v1_preprocessor.joblib",
        "models/anomaly_v1_estimator.joblib",
        "models/anomaly_v1_metadata.json",
        "models/failure_v1_preprocessor.joblib",
        "models/failure_v1_estimator.joblib",
        "models/failure_v1_metadata.json",
    ):
        assert (PROJECT_ROOT / required_path).is_file(), required_path
    assert "models/" not in dockerignore.splitlines()
    assert "models/*_evaluation.json" in dockerignore
    assert "data/reference/" not in dockerignore
    assert "data/raw/" in dockerignore
    assert ".env" in dockerignore
    assert "pytest" not in runtime_requirements
    assert "httpx2" not in runtime_requirements
    assert "read_only: true" in compose
    assert "predictive_maintenance_data:/var/lib/predictive-maintenance" in compose
    assert "/ready" in compose


def test_docker_startup_port_precedence_is_render_port_then_app_port_then_8000() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert '--host 0.0.0.0 --port \\"${PORT:-${APP_PORT:-8000}}\\"' in dockerfile
    assert 'APP_PORT=8000' in dockerfile


@pytest.mark.parametrize("family", ["anomaly", "failure"])
def test_prediction_record_verifier_checks_id_family_and_saved_result(family: str) -> None:
    if family == "anomaly":
        prediction = {
            "prediction_id": "prediction-1", "equipment_id": 7, "reading_id": 11,
            "model_version": "anomaly_v1", "anomaly_score": -0.42,
            "classification": "anomaly",
        }
        persisted = {
            "id": "prediction-1", "equipment_id": 7, "reading_id": 11,
            "model_version": "anomaly_v1", "anomaly_score": -0.42,
            "is_anomaly": True, "failure_probability": None,
        }
    else:
        prediction = {
            "prediction_id": "prediction-2", "equipment_id": 7, "reading_id": 12,
            "model_version": "failure_v1", "predicted_class": 1,
            "failure_probability": 0.73,
        }
        persisted = {
            "id": "prediction-2", "equipment_id": 7, "reading_id": 12,
            "model_version": "failure_v1", "anomaly_score": None,
            "is_anomaly": None, "failure_probability": 0.73,
        }

    _validate_prediction_record(family, prediction, persisted)
    persisted["id"] = "wrong-id"
    with pytest.raises(DeploymentVerificationError, match="different prediction ID"):
        _validate_prediction_record(family, prediction, persisted)
    persisted["id"] = prediction["prediction_id"]
    if family == "anomaly":
        persisted["anomaly_score"] = -0.5
    else:
        persisted["failure_probability"] = 0.5
    with pytest.raises(DeploymentVerificationError, match="result did not match"):
        _validate_prediction_record(family, prediction, persisted)


def test_equipment_history_verifier_accepts_empty_history_and_checks_expected_records() -> None:
    equipment = {"id": 7, "name": "smoke fixture"}
    _validate_equipment_history(
        equipment, {"equipment": equipment, "items": []}, []
    )

    prediction = {
        "prediction_id": "prediction-1", "equipment_id": 7, "reading_id": 11,
        "model_version": "anomaly_v1", "anomaly_score": -0.42,
        "classification": "anomaly",
    }
    history = {
        "equipment": equipment,
        "items": [{
            "reading": {"id": 11, "equipment_id": 7},
            "predictions": [{
                "id": "prediction-1", "model_version": "anomaly_v1",
                "anomaly_score": -0.42, "is_anomaly": True,
                "failure_probability": None,
            }],
        }],
    }
    _validate_equipment_history(equipment, history, [("anomaly", prediction)])
    history["items"] = []
    with pytest.raises(DeploymentVerificationError, match="omitted persisted anomaly"):
        _validate_equipment_history(equipment, history, [("anomaly", prediction)])


def test_metrics_alias_comparison_ignores_expected_self_request_counter_delta() -> None:
    base = {
        "requests": {"total": 4, "by_endpoint": {}},
        "predictions": {"anomaly": {"total": 1}, "failure": {"total": 1}},
        "runtime": {"metrics_storage": "in_memory_process_local", "uptime_seconds": 2.1},
        "availability": {"database_available": True},
        "rolling_window": {
            "window_seconds": 300, "requests": {"total": 4},
            "predictions": {"anomaly": {"total": 1}, "failure": {"total": 1}},
        },
    }
    alias = {
        **base,
        "requests": {"total": 5, "by_endpoint": {"/metrics/summary": {"requests": 1}}},
        "runtime": {"metrics_storage": "in_memory_process_local", "uptime_seconds": 2.2},
        "rolling_window": {**base["rolling_window"], "requests": {"total": 5}},
    }
    _validate_metrics_equivalence(base, alias)
    alias["predictions"] = {"anomaly": {"total": 2}}
    with pytest.raises(DeploymentVerificationError, match="different prediction"):
        _validate_metrics_equivalence(base, alias)


def test_saved_drift_verifier_requires_database_report_identity_and_details() -> None:
    timestamp = "2026-01-01T00:00:00Z"
    feature = {
        "feature_name": "Type", "method": "total_variation_distance",
        "statistic": 0.2, "threshold": 0.1, "drift_detected": True,
        "reference_sample_size": 7000, "current_sample_size": 20,
    }
    evaluated = {
        "generated_at": timestamp, "features": [dict(feature) for _ in range(6)],
        "overall_status": "drift_detected", "reference_version": "drift_reference_v1",
    }
    saved = {
        "report_id": 9, "features": [dict(feature) for _ in range(6)],
        "overall_status": "drift_detected", "reference_version": "drift_reference_v1",
        "created_at": timestamp, "batch_description": "batch",
        "methodology": {"methods": ["total_variation_distance"]},
        "report_metadata": {"generated_at": "2026-01-01T00:00:00+00:00"},
    }
    assert _validate_saved_drift(evaluated, saved, previous_report_id=8) == 9
    saved["report_id"] = 8
    with pytest.raises(DeploymentVerificationError, match="newer persisted report"):
        _validate_saved_drift(evaluated, saved, previous_report_id=8)
