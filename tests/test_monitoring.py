from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from scripts.generate_drift_reference import generate_reference
from src.api.main import create_app
from src.config import DRIFT_REFERENCE_PATH, RAW_DATASET_PATH
from src.data_ingestion import clean_dataset, get_feature_target_split, load_raw_dataset
from src.monitoring.metrics import OperationalMetrics
from src.preprocessing import split_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models"
BASE_OBSERVATION = {
    "Type": "M",
    "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6,
    "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8,
    "Tool wear [min]": 0,
}


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture(scope="module")
def training_features() -> pd.DataFrame:
    dataset = clean_dataset(load_raw_dataset())
    features, target = get_feature_target_split(dataset)
    return split_data(features, target)["X_train"]


def observations_from_frame(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.to_dict(orient="records")


def test_drift_reference_is_reproducibly_generated_from_training_rows_only(
    tmp_path: Path,
    training_features: pd.DataFrame,
) -> None:
    generated = generate_reference(RAW_DATASET_PATH, tmp_path / "drift_reference.json")
    committed = json.loads(DRIFT_REFERENCE_PATH.read_text(encoding="utf-8"))
    assert generated["training_sample_size"] == 7000
    assert generated["reference_selection"]["split"] == "train"
    assert generated["reference_selection"]["test_and_validation_excluded"] is True
    assert generated["feature_names"] == [
        "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]",
        "Torque [Nm]", "Tool wear [min]", "Type",
    ]
    prohibited = {
        "Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF", "UDI", "Product ID"
    }
    assert not prohibited.intersection(generated["feature_names"])
    assert generated["numeric_statistics"]["Torque [Nm]"]["mean"] == pytest.approx(
        training_features["Torque [Nm]"].mean()
    )
    assert generated["numeric_statistics"] == committed["numeric_statistics"]
    assert generated["categorical_statistics"] == committed["categorical_statistics"]


def test_drift_endpoint_detects_similar_numeric_and_changed_type_distributions(
    tmp_path: Path,
    training_features: pd.DataFrame,
) -> None:
    url = sqlite_url(tmp_path / "drift.sqlite3")
    similar = training_features.sample(n=500, random_state=42)
    shifted_numeric = similar.copy()
    shifted_numeric["Torque [Nm]"] += 15.0
    shifted_type = similar.copy()
    shifted_type["Type"] = "H"

    with TestClient(create_app(MODEL_DIR, database_url=url)) as client:
        similar_response = client.post(
            "/monitoring/drift", json={"observations": observations_from_frame(similar)}
        )
        numeric_response = client.post(
            "/monitoring/drift", json={"observations": observations_from_frame(shifted_numeric)}
        )
        type_response = client.post(
            "/monitoring/drift", json={"observations": observations_from_frame(shifted_type)}
        )

    assert similar_response.status_code == 200
    assert similar_response.json()["overall_status"] == "no_drift_detected"
    assert numeric_response.status_code == 200
    numeric_report = {row["feature_name"]: row for row in numeric_response.json()["features"]}
    assert numeric_report["Torque [Nm]"]["drift_detected"] is True
    assert numeric_report["Torque [Nm]"]["method"] == "kolmogorov_smirnov_two_sample"
    assert type_response.status_code == 200
    type_report = {row["feature_name"]: row for row in type_response.json()["features"]}
    assert type_report["Type"]["drift_detected"] is True
    assert type_report["Type"]["method"] == "total_variation_distance"


def test_drift_endpoint_handles_insufficient_and_invalid_batches(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "validation.sqlite3")
    small_batch = [BASE_OBSERVATION] * 5
    with TestClient(create_app(MODEL_DIR, database_url=url)) as client:
        small = client.post("/monitoring/drift", json={"observations": small_batch})
        empty = client.post("/monitoring/drift", json={"observations": []})
        missing = client.post("/monitoring/drift", json={"observations": [{"Type": "M"}]})
        extra_target = client.post(
            "/monitoring/drift",
            json={"observations": [{**BASE_OBSERVATION, "Machine failure": 0}]},
        )
        extra_identifier = client.post(
            "/monitoring/drift",
            json={"observations": [{**BASE_OBSERVATION, "UDI": 1}]},
        )
        invalid_type = client.post(
            "/monitoring/drift",
            json={"observations": [{**BASE_OBSERVATION, "Type": "X"}]},
        )
        out_of_range = client.post(
            "/monitoring/drift",
            json={"observations": [{**BASE_OBSERVATION, "Torque [Nm]": 200}]},
        )
        nan_body = json.dumps(
            {"observations": [{**BASE_OBSERVATION, "Torque [Nm]": float("nan")}]},
            allow_nan=True,
        )
        nan = client.post(
            "/monitoring/drift", content=nan_body,
            headers={"content-type": "application/json"},
        )

    assert small.status_code == 200
    assert small.json()["overall_status"] == "insufficient_data"
    assert all(item["drift_detected"] is None for item in small.json()["features"])
    for response in (empty, missing, extra_target, extra_identifier, invalid_type, out_of_range, nan):
        assert response.status_code == 422
        assert "Traceback" not in response.text
    assert "input" not in nan.text


@pytest.mark.parametrize("bad_reference", ["missing", "incompatible"])
def test_missing_or_incompatible_reference_is_safely_unavailable(
    tmp_path: Path,
    bad_reference: str,
) -> None:
    reference_path = tmp_path / "drift_reference.json"
    if bad_reference == "incompatible":
        reference_path.write_text('{"schema_version":999}', encoding="utf-8")
    with TestClient(create_app(
        MODEL_DIR,
        database_url=sqlite_url(tmp_path / "unavailable.sqlite3"),
        drift_reference_path=reference_path,
    )) as client:
        health = client.get("/health")
        drift = client.post(
            "/monitoring/drift", json={"observations": [BASE_OBSERVATION] * 20}
        )
    assert health.status_code == 200
    assert drift.status_code == 503
    assert drift.json() == {"detail": "Drift reference is unavailable"}
    assert str(tmp_path) not in drift.text


def test_operational_metrics_count_requests_predictions_and_errors(tmp_path: Path) -> None:
    with TestClient(create_app(
        MODEL_DIR, database_url=sqlite_url(tmp_path / "metrics.sqlite3")
    )) as client:
        initial = client.get("/monitoring/metrics")
        assert initial.status_code == 200
        assert initial.json()["requests"]["total"] == 0
        client.get("/health")
        invalid = client.post("/predict/anomaly", json={})
        anomaly = client.post("/predict/anomaly", json=BASE_OBSERVATION)
        failure = client.post("/predict/failure", json=BASE_OBSERVATION)
        estimator = client.app.state.model_registry.artifacts["failure"].estimator

        def fail_prediction(*args, **kwargs):
            raise RuntimeError("internal model error")

        estimator.predict_proba = fail_prediction
        failed_failure = client.post("/predict/failure", json=BASE_OBSERVATION)
        metrics = client.get("/monitoring/metrics")

    assert invalid.status_code == 422
    assert anomaly.status_code == failure.status_code == 200
    assert failed_failure.status_code == 500
    assert failed_failure.json() == {"detail": "Prediction could not be completed"}
    body = metrics.json()
    requests = body["requests"]
    assert requests["total"] == 6
    assert requests["successful"] == 4
    assert requests["failed"] == 2
    assert requests["status_codes"] == {"200": 4, "422": 1, "500": 1}
    assert requests["by_endpoint"]["/predict/anomaly"]["requests"] == 2
    assert requests["by_endpoint"]["/predict/anomaly"]["status_codes"] == {
        "200": 1, "422": 1
    }
    assert requests["duration_ms"]["average"] >= 0
    assert body["predictions"]["anomaly"]["total"] == 1
    assert body["predictions"]["anomaly"]["normal"] + body["predictions"]["anomaly"]["anomaly"] == 1
    assert body["predictions"]["failure"]["total"] == 1
    assert body["predictions"]["failure"][f"predicted_class_{failure.json()['predicted_class']}"] == 1
    assert body["predictions"]["errors"] == {
        "total": 2, "by_model": {"anomaly": 1, "failure": 1}
    }
    assert body["runtime"]["metrics_storage"] == "in_memory_process_local"


def test_metrics_counter_updates_are_thread_safe() -> None:
    metrics = OperationalMetrics()

    def add_requests(_: int) -> None:
        for _ in range(100):
            metrics.record_request("/health", 200, 1.25)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add_requests, range(8)))

    snapshot = metrics.snapshot()
    assert snapshot["requests"]["total"] == 800
    assert snapshot["requests"]["successful"] == 800
    assert snapshot["requests"]["by_endpoint"]["/health"]["requests"] == 800
