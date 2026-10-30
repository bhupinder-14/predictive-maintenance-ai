from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from shutil import copy2

from fastapi.testclient import TestClient
import pytest

from src.api.main import create_app as _create_app
from src.api.schemas import SensorObservation
from src.anomaly_model import predict_anomaly
from src.failure_model import predict_failure
from src.model_utils import ModelArtifact
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models"
_ACTIVE_TEST_DATABASE: Path | None = None


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path: Path) -> None:
    """Keep every API test on a fresh SQLite file outside the project tree."""
    global _ACTIVE_TEST_DATABASE
    _ACTIVE_TEST_DATABASE = tmp_path / "api-test.sqlite3"


def create_app(model_directory=None, **kwargs):
    assert _ACTIVE_TEST_DATABASE is not None
    kwargs.setdefault("database_url", f"sqlite:///{_ACTIVE_TEST_DATABASE.as_posix()}")
    return _create_app(model_directory, **kwargs)

VALID_OBSERVATION = {
    "Type": "M",
    "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6,
    "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8,
    "Tool wear [min]": 0,
}


def test_health_and_readiness_with_saved_models() -> None:
    with TestClient(create_app(MODEL_DIR)) as client:
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "models": {"anomaly": True, "failure": True},
        "database": True,
    }


def test_swagger_ui_and_openapi_document_all_milestone_two_routes() -> None:
    with TestClient(create_app(MODEL_DIR)) as client:
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text.lower()
    assert schema.status_code == 200
    assert set(schema.json()["paths"]) == {
        "/health",
        "/ready",
        "/predict/anomaly",
        "/predict/failure",
        "/equipment",
        "/equipment/{equipment_id}/history",
        "/predictions/{prediction_id}",
    }


def test_valid_anomaly_request_returns_documented_response() -> None:
    with TestClient(create_app(MODEL_DIR)) as client:
        response = client.post("/predict/anomaly", json=VALID_OBSERVATION)

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_id"]
    assert body["equipment_id"] > 0
    assert body["reading_id"] > 0
    assert body["model_version"] == "anomaly_v1"
    assert body["classification"] in {"normal", "anomaly"}
    assert isinstance(body["anomaly_score"], float)
    assert body["prediction_timestamp"].endswith("Z") or "+00:00" in body["prediction_timestamp"]
    assert body["inference_latency_ms"] >= 0
    assert body["explanation"]["method"] == "absolute_deviation_in_standardised_space"
    assert body["explanation"]["top_suspicious_features"]
    assert "failure_probability" not in body


def test_valid_failure_request_returns_probability_and_class() -> None:
    with TestClient(create_app(MODEL_DIR)) as client:
        response = client.post("/predict/failure", json=VALID_OBSERVATION)

    assert response.status_code == 200
    body = response.json()
    assert body["prediction_id"]
    assert body["equipment_id"] > 0
    assert body["reading_id"] > 0
    assert body["model_version"] == "failure_v1"
    assert body["predicted_class"] in (0, 1)
    assert 0 <= body["failure_probability"] <= 1
    assert body["inference_latency_ms"] >= 0


def test_missing_required_sensor_fields_are_rejected() -> None:
    payload = {key: value for key, value in VALID_OBSERVATION.items() if key != "Torque [Nm]"}
    with TestClient(create_app(MODEL_DIR)) as client:
        response = client.post("/predict/failure", json=payload)
    assert response.status_code == 422
    assert any(error["loc"][-1] == "Torque [Nm]" for error in response.json()["detail"])


def test_invalid_sensor_type_and_machine_type_are_rejected() -> None:
    invalid_sensor = deepcopy(VALID_OBSERVATION)
    invalid_sensor["Torque [Nm]"] = "not-a-number"
    invalid_machine_type = deepcopy(VALID_OBSERVATION)
    invalid_machine_type["Type"] = "X"

    with TestClient(create_app(MODEL_DIR)) as client:
        sensor_response = client.post("/predict/anomaly", json=invalid_sensor)
        type_response = client.post("/predict/anomaly", json=invalid_machine_type)

    assert sensor_response.status_code == 422
    assert type_response.status_code == 422


def test_out_of_range_and_unexpected_target_fields_are_rejected() -> None:
    out_of_range = deepcopy(VALID_OBSERVATION)
    out_of_range["Air temperature [K]"] = 400
    with_target = {**VALID_OBSERVATION, "Machine failure": 0, "TWF": 0}

    with TestClient(create_app(MODEL_DIR)) as client:
        range_response = client.post("/predict/failure", json=out_of_range)
        target_response = client.post("/predict/failure", json=with_target)

    assert range_response.status_code == 422
    assert target_response.status_code == 422


def test_nan_infinity_empty_and_impossible_values_return_sanitized_422() -> None:
    nan_body = json.dumps(
        {**VALID_OBSERVATION, "Air temperature [K]": float("nan")},
        allow_nan=True,
    )
    positive_inf_body = json.dumps(
        {**VALID_OBSERVATION, "Torque [Nm]": float("inf")},
        allow_nan=True,
    )
    negative_inf_body = json.dumps(
        {**VALID_OBSERVATION, "Torque [Nm]": float("-inf")},
        allow_nan=True,
    )
    headers = {"content-type": "application/json"}

    with TestClient(create_app(MODEL_DIR)) as client:
        empty = client.post("/predict/anomaly", json={})
        missing_body = client.post("/predict/anomaly")
        nan = client.post("/predict/anomaly", content=nan_body, headers=headers)
        positive_inf = client.post("/predict/failure", content=positive_inf_body, headers=headers)
        negative_inf = client.post("/predict/failure", content=negative_inf_body, headers=headers)
        impossible = client.post(
            "/predict/failure",
            json={**VALID_OBSERVATION, "Rotational speed [rpm]": 999999},
        )

    for response in (empty, missing_body, nan, positive_inf, negative_inf, impossible):
        assert response.status_code == 422
        assert "Traceback" not in response.text
    assert "input" not in nan.json()["detail"][0]
    assert "nan" not in nan.text.lower()
    assert "infinity" not in positive_inf.text.lower()


def test_api_predictions_match_direct_saved_model_inference() -> None:
    observation = SensorObservation.model_validate(VALID_OBSERVATION)
    raw_features = pd.DataFrame([observation.as_model_features()])
    anomaly_artifact = ModelArtifact.load("anomaly_v1", MODEL_DIR)
    failure_artifact = ModelArtifact.load("failure_v1", MODEL_DIR)
    expected_anomaly = predict_anomaly(anomaly_artifact, raw_features)[0]
    expected_failure = predict_failure(failure_artifact, raw_features)[0]

    with TestClient(create_app(MODEL_DIR)) as client:
        anomaly = client.post("/predict/anomaly", json=VALID_OBSERVATION).json()
        failure = client.post("/predict/failure", json=VALID_OBSERVATION).json()

    assert anomaly["anomaly_score"] == expected_anomaly.anomaly_score
    assert anomaly["classification"] == (
        "anomaly" if expected_anomaly.is_anomaly else "normal"
    )
    assert failure["predicted_class"] == expected_failure.predicted_class
    assert failure["failure_probability"] == expected_failure.failure_probability


def test_missing_model_artifacts_keep_health_safe_and_readiness_unavailable(tmp_path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        prediction = client.post("/predict/anomaly", json=VALID_OBSERVATION)

    assert health.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "models": {"anomaly": False, "failure": False},
        "database": True,
    }
    assert prediction.status_code == 503
    assert prediction.json()["detail"] == "Anomaly model is unavailable"
    assert "Traceback" not in prediction.text


@pytest.mark.parametrize("available_model", ("anomaly", "failure"))
def test_partial_model_availability_serves_loaded_model_only(
    tmp_path,
    available_model: str,
) -> None:
    version = f"{available_model}_v1"
    for suffix in ("preprocessor.joblib", "estimator.joblib", "metadata.json"):
        filename = f"{version}_{suffix}"
        copy2(MODEL_DIR / filename, tmp_path / filename)

    with TestClient(create_app(tmp_path)) as client:
        anomaly = client.post("/predict/anomaly", json=VALID_OBSERVATION)
        failure = client.post("/predict/failure", json=VALID_OBSERVATION)
        ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["models"] == {
        "anomaly": available_model == "anomaly",
        "failure": available_model == "failure",
    }
    assert anomaly.status_code == (200 if available_model == "anomaly" else 503)
    assert failure.status_code == (200 if available_model == "failure" else 503)


def test_model_loading_exception_is_sanitized_and_reported_not_ready(tmp_path) -> None:
    def broken_loader(version: str, directory: Path) -> ModelArtifact:
        raise RuntimeError("private loader detail")

    with TestClient(create_app(tmp_path, artifact_loader=broken_loader)) as client:
        ready = client.get("/ready")
        prediction = client.post("/predict/failure", json=VALID_OBSERVATION)

    assert ready.status_code == 503
    assert prediction.status_code == 503
    assert "private loader detail" not in ready.text
    assert "private loader detail" not in prediction.text
    assert "Traceback" not in prediction.text


def test_incompatible_artifact_schema_is_not_marked_ready() -> None:
    def incompatible_loader(version: str, directory: Path) -> ModelArtifact:
        artifact = ModelArtifact.load(version, directory)
        if version == "failure_v1":
            artifact.metadata.feature_names = ["unexpected_feature"]
        return artifact

    with TestClient(create_app(MODEL_DIR, artifact_loader=incompatible_loader)) as client:
        ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["models"] == {"anomaly": True, "failure": False}


def test_inference_exception_returns_sanitized_error() -> None:
    with TestClient(create_app(MODEL_DIR)) as client:
        estimator = client.app.state.model_registry.artifacts["failure"].estimator

        def fail_inference(*args, **kwargs):
            raise RuntimeError("private path C:\\secret\\artifact.joblib")

        estimator.predict_proba = fail_inference
        response = client.post("/predict/failure", json=VALID_OBSERVATION)

    assert response.status_code == 500
    assert response.json() == {"detail": "Prediction could not be completed"}
    assert all(secret not in response.text for secret in ("Traceback", "C:\\secret", "artifact.joblib"))
