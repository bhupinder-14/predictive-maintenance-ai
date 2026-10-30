from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import OperationalError

from src.api.main import create_app
from src.api.model_registry import ModelCompatibilityError
from src.config import MODEL_DIR
from src.database.manager import Database
from src.database.models import MonitoringReport
from src.database.repository import PredictionRepository
from src.monitoring.metrics import OperationalMetrics

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / MODEL_DIR
OBSERVATION = {
    "Type": "M", "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6, "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8, "Tool wear [min]": 0,
}


def db_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def report_batch() -> dict[str, list[dict[str, object]]]:
    return {"observations": [dict(OBSERVATION) for _ in range(20)]}


def test_drift_report_is_complete_latest_and_survives_restart(tmp_path: Path) -> None:
    database_url = db_url(tmp_path / "drift-history.sqlite3")
    with TestClient(create_app(MODEL_PATH, database_url=database_url)) as client:
        assert client.get("/monitoring/drift").status_code == 404
        posted = client.post("/monitoring/drift", json=report_batch())
        assert posted.status_code == 200
        post_body = posted.json()
        with client.app.state.database.session() as session:
            persisted = session.scalar(select(MonitoringReport))
            assert persisted is not None
            first_id = persisted.id
            saved_features = persisted.feature_results
            assert len(saved_features) == 6
            assert persisted.reference_version == post_body["reference_version"]
            assert persisted.report_metadata["current_sample_size"] == 20
            assert persisted.methodology["methods"] == [
                "kolmogorov_smirnov_two_sample", "total_variation_distance"
            ]

    with TestClient(create_app(MODEL_PATH, database_url=database_url)) as restarted:
        # Retrieval must use the stored report rather than reevaluate a batch.
        restarted.app.state.drift_detector.evaluate = lambda *_: (_ for _ in ()).throw(
            AssertionError("GET recalculated drift")
        )
        fetched = restarted.get("/monitoring/drift")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["report_id"] == first_id
        assert body["features"] == post_body["features"] == saved_features
        assert body["report_metadata"]["overall_status"] == body["overall_status"]
        assert body["reference_version"] == post_body["reference_version"]
        assert body["batch_description"].startswith("Batch of 20")

        # Equal timestamps are ordered by the monotonic database primary key.
        same_created_at = datetime.now(timezone.utc) + timedelta(days=1)
        with restarted.app.state.database.session() as session, session.begin():
            first_tied = PredictionRepository.create_monitoring_report(
                session,
                model_version="anomaly=anomaly_v1;failure=failure_v1",
                window_start=same_created_at, window_end=same_created_at,
                drift_metric=None, drift_status="no_drift_detected",
                created_at=same_created_at, reference_version="drift_reference_v1",
                batch_description="tie check 1", methodology={"methods": []},
                report_metadata={"generated_at": same_created_at.isoformat(),
                                 "reference_sample_size": 7000,
                                 "current_sample_size": 20,
                                 "minimum_sample_size": 20,
                                 "interpretation": "saved"},
                feature_results=[],
            )
            first_tied_id = first_tied.id
            second_tied = PredictionRepository.create_monitoring_report(
                session,
                model_version="anomaly=anomaly_v1;failure=failure_v1",
                window_start=same_created_at, window_end=same_created_at,
                drift_metric=None, drift_status="drift_detected",
                created_at=same_created_at, reference_version="drift_reference_v1",
                batch_description="tie check 2", methodology={"methods": []},
                report_metadata={"generated_at": same_created_at.isoformat(),
                                 "reference_sample_size": 7000,
                                 "current_sample_size": 20,
                                 "minimum_sample_size": 20,
                                 "interpretation": "saved"},
                feature_results=[],
            )
            second_tied_id = second_tied.id
        latest = restarted.get("/monitoring/drift").json()
        assert second_tied_id > first_tied_id
        assert latest["report_id"] == second_tied_id
        assert latest["batch_description"] == "tie check 2"


def test_invalid_drift_input_is_not_persisted(tmp_path: Path) -> None:
    with TestClient(create_app(
        MODEL_PATH, database_url=db_url(tmp_path / "invalid-drift.sqlite3")
    )) as client:
        invalid = client.post("/monitoring/drift", json={"observations": []})
        assert invalid.status_code == 422
        with client.app.state.database.session() as session:
            assert session.scalar(select(MonitoringReport)) is None


def test_drift_persistence_failure_returns_sanitized_503(tmp_path: Path) -> None:
    with TestClient(create_app(
        MODEL_PATH, database_url=db_url(tmp_path / "write-failure.sqlite3")
    )) as client:
        engine = client.app.state.database.engine

        def fail_report_write(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO MONITORING_REPORTS"):
                raise OperationalError(statement, parameters, RuntimeError("secret-path"))

        event.listen(engine, "before_cursor_execute", fail_report_write)
        failed = client.post("/monitoring/drift", json=report_batch())
        event.remove(engine, "before_cursor_execute", fail_report_write)
        assert failed.status_code == 503
        assert failed.json() == {"detail": "Drift report could not be persisted"}
        assert "secret-path" not in failed.text
        assert client.get("/monitoring/drift").status_code == 404


def test_drift_routes_report_unavailable_database_safely() -> None:
    with TestClient(create_app(MODEL_PATH, database_url="unsupported://database")) as client:
        posted = client.post("/monitoring/drift", json=report_batch())
        fetched = client.get("/monitoring/drift")
    assert posted.status_code == fetched.status_code == 503
    assert posted.json() == {"detail": "Drift report could not be persisted"}
    assert fetched.json() == {"detail": "Database is unavailable"}


def test_existing_sqlite_report_rows_migrate_additively(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE monitoring_reports ("
            "id INTEGER PRIMARY KEY, model_version VARCHAR(80) NOT NULL, "
            "window_start DATETIME NOT NULL, window_end DATETIME NOT NULL, "
            "drift_metric FLOAT, drift_status VARCHAR(40) NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )
        connection.execute(
            "INSERT INTO monitoring_reports VALUES (1, 'legacy-v0', "
            "'2025-01-01 00:00:00', '2025-01-01 00:00:00', 0.1, "
            "'legacy', '2025-01-01 00:00:00')"
        )

    database = Database(db_url(path))
    database.initialize()
    columns = {item["name"] for item in inspect(database.engine).get_columns("monitoring_reports")}
    assert {"reference_version", "batch_description", "methodology",
            "report_metadata", "feature_results"}.issubset(columns)
    with database.session() as session:
        legacy = session.get(MonitoringReport, 1)
        assert legacy is not None
        assert legacy.model_version == "legacy-v0"
        assert legacy.drift_metric == pytest.approx(0.1)
        assert legacy.reference_version is None
        assert legacy.feature_results is None
    database.dispose()


def test_metrics_aliases_versions_availability_and_live_database_state(tmp_path: Path) -> None:
    with TestClient(create_app(
        MODEL_PATH, database_url=db_url(tmp_path / "metrics.sqlite3")
    )) as client:
        assert client.post("/predict/anomaly", json=OBSERVATION).status_code == 200
        assert client.post("/predict/failure", json=OBSERVATION).status_code == 200
        summary = client.get("/metrics/summary")
        alias = client.get("/monitoring/metrics")
        assert summary.status_code == alias.status_code == 200
        for response in (summary, alias):
            body = response.json()
            assert body["availability"]["database_available"] is True
            assert body["availability"]["models"] == {
                "anomaly": {"available": True, "status": "available",
                            "model_version": "anomaly_v1"},
                "failure": {"available": True, "status": "available",
                            "model_version": "failure_v1"},
            }
            assert body["predictions"]["anomaly"]["by_model_version"]["anomaly_v1"]["total"] == 1
            assert body["predictions"]["failure"]["by_model_version"]["failure_v1"]["total"] == 1
        assert summary.json()["predictions"] == alias.json()["predictions"]

        engine = client.app.state.database.engine

        def unavailable_select_one(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper() == "SELECT 1":
                raise OperationalError(statement, parameters, RuntimeError("offline"))

        event.listen(engine, "before_cursor_execute", unavailable_select_one)
        down = client.get("/metrics/summary")
        event.remove(engine, "before_cursor_execute", unavailable_select_one)
        up = client.get("/monitoring/metrics")
        assert down.json()["availability"]["database_available"] is False
        assert up.json()["availability"]["database_available"] is True


def test_metrics_expose_missing_and_incompatible_model_states(tmp_path: Path) -> None:
    missing_dir = tmp_path / "empty-models"
    missing_dir.mkdir()
    with TestClient(create_app(
        missing_dir, database_url=db_url(tmp_path / "missing-models.sqlite3")
    )) as missing_client:
        missing = missing_client.get("/metrics/summary").json()
    assert all(
        item["status"] == "missing_artifacts" and item["available"] is False
        for item in missing["availability"]["models"].values()
    )

    def incompatible_loader(version: str, directory: Path):
        raise ModelCompatibilityError("private artifact detail")

    with TestClient(create_app(
        MODEL_PATH,
        artifact_loader=incompatible_loader,
        database_url=db_url(tmp_path / "incompatible.sqlite3"),
    )) as incompatible_client:
        incompatible = incompatible_client.get("/metrics/summary").json()
    assert all(
        item["status"] == "incompatible_artifacts" and item["available"] is False
        for item in incompatible["availability"]["models"].values()
    )
    assert "private artifact detail" not in json.dumps(incompatible)

    def failed_loader(version: str, directory: Path):
        raise RuntimeError("private loader detail")

    with TestClient(create_app(
        MODEL_PATH,
        artifact_loader=failed_loader,
        database_url=db_url(tmp_path / "load-failed.sqlite3"),
    )) as failed_client:
        failed = failed_client.get("/metrics/summary").json()
    assert all(
        item["status"] == "load_failed" and item["available"] is False
        for item in failed["availability"]["models"].values()
    )
    assert "private loader detail" not in json.dumps(failed)


def test_metrics_rolling_window_excludes_expired_observations() -> None:
    now = [100.0]
    metrics = OperationalMetrics(window_seconds=10, clock=lambda: now[0])
    metrics.record_request("/health", 200, 2.0)
    metrics.record_anomaly_prediction("normal", "anomaly_v1")
    metrics.record_prediction_error("failure")
    now[0] = 105.0
    metrics.record_request("/predict/failure", 503, 4.0)
    snapshot = metrics.snapshot(model_availability={}, database_available=True)
    assert snapshot["rolling_window"]["window_seconds"] == 10
    assert snapshot["rolling_window"]["requests"]["total"] == 2
    assert snapshot["rolling_window"]["requests"]["duration_ms"]["average"] == 3.0
    assert snapshot["rolling_window"]["predictions"]["anomaly"]["total"] == 1
    assert snapshot["rolling_window"]["predictions"]["errors"]["total"] == 1
    now[0] = 111.0
    expired = metrics.snapshot(model_availability={}, database_available=True)
    assert expired["requests"]["total"] == 2  # cumulative counters remain
    assert expired["rolling_window"]["requests"]["total"] == 1
    assert expired["rolling_window"]["requests"]["by_endpoint"].keys() == {"/predict/failure"}
    assert expired["rolling_window"]["predictions"]["anomaly"]["total"] == 0
    assert expired["rolling_window"]["predictions"]["errors"]["total"] == 0
