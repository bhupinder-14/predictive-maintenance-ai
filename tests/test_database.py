from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError

from src.api.main import create_app
from src.database.manager import Database
from src.database.models import Equipment, Prediction, SensorReading
from src.database.repository import PredictionRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models"
OBSERVATION = {
    "Type": "M",
    "Air temperature [K]": 298.1,
    "Process temperature [K]": 308.6,
    "Rotational speed [rpm]": 1551,
    "Torque [Nm]": 42.8,
    "Tool wear [min]": 0,
}


def db_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_database_initialization_equipment_and_foreign_key_relationships(tmp_path: Path) -> None:
    database = Database(db_url(tmp_path / "records.sqlite3"))
    database.initialize()
    assert set(inspect(database.engine).get_table_names()) == {
        "equipment", "sensor_readings", "predictions", "monitoring_reports"
    }
    with database.session() as session:
        with session.begin():
            equipment = PredictionRepository.resolve_equipment(
                session, equipment_id=None, equipment_name="Press 4",
                equipment_type="M", location="Line A",
            )
            reading = SensorReading(
                equipment_id=equipment.id, timestamp=datetime.now(timezone.utc),
                machine_type="M", air_temperature_k=298.1,
                process_temperature_k=308.6, rotational_speed_rpm=1551,
                torque_nm=42.8, tool_wear_min=0, source="test",
            )
            session.add(reading)
            session.flush()
            prediction = Prediction(
                id="prediction-test", equipment_id=equipment.id,
                reading_id=reading.id, model_version="failure_v1",
                failure_probability=0.2, latency_ms=1.5,
            )
            session.add(prediction)
        assert session.get(Equipment, equipment.id).readings[0].predictions[0].id == "prediction-test"
        assert session.get(Prediction, "prediction-test").reading.equipment_id == equipment.id
        another_equipment = Equipment(name="Press 5", equipment_type="M")
        session.add(another_equipment)
        session.commit()
        session.add(Prediction(
            id="mismatched", equipment_id=another_equipment.id,
            reading_id=reading.id, model_version="failure_v1",
            failure_probability=0.2, latency_ms=1.0,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    assert database.engine.connect().exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    database.dispose()


def test_historical_sql_queries_use_persisted_records(tmp_path: Path) -> None:
    database = Database(db_url(tmp_path / "history.sqlite3"))
    database.initialize()
    now = datetime.now(timezone.utc)
    with database.session() as session, session.begin():
        equipment = PredictionRepository.resolve_equipment(
            session, equipment_id=None, equipment_name="Lathe", equipment_type="L", location=None
        )
        reading = SensorReading(
            equipment_id=equipment.id, timestamp=now, machine_type="L",
            air_temperature_k=298, process_temperature_k=308,
            rotational_speed_rpm=1500, torque_nm=40, tool_wear_min=4, source="test",
        )
        session.add(reading)
        session.flush()
        session.add_all([
            Prediction(id="a1", equipment_id=equipment.id, reading_id=reading.id,
                       model_version="anomaly_v1", anomaly_score=-0.7,
                       is_anomaly=True, latency_ms=10, created_at=now),
            Prediction(id="a2", equipment_id=equipment.id, reading_id=reading.id,
                       model_version="anomaly_v1", anomaly_score=-0.3,
                       is_anomaly=False, latency_ms=20, created_at=now + timedelta(seconds=1)),
            Prediction(id="f1", equipment_id=equipment.id, reading_id=reading.id,
                       model_version="failure_v1", failure_probability=0.25,
                       latency_ms=30, created_at=now + timedelta(seconds=2)),
        ])
    with database.session() as session:
        assert len(PredictionRepository.latest_readings_by_equipment(session, equipment_id=equipment.id)) == 1
        assert len(PredictionRepository.predictions_in_range(
            session, start=now - timedelta(seconds=1), end=now + timedelta(seconds=3)
        )) == 3
        flagged = PredictionRepository.most_frequently_flagged_equipment(session)
        assert [(item.id, count) for item, count in flagged] == [(equipment.id, 1)]
        average = PredictionRepository.average_anomaly_score_by_equipment(session)
        assert average[0][1] == pytest.approx(-0.5)
        assert PredictionRepository.prediction_counts_by_model_version(session) == {
            "anomaly_v1": 2, "failure_v1": 1
        }
        assert PredictionRepository.latency_summary(session) == {
            "count": 3, "average_ms": 20.0, "p95_ms": 30.0
        }
    database.dispose()


def test_api_persists_prediction_history_and_survives_restart(tmp_path: Path) -> None:
    url = db_url(tmp_path / "durable.sqlite3")
    with TestClient(create_app(MODEL_DIR, database_url=url)) as client:
        anomaly = client.post("/predict/anomaly", json={**OBSERVATION, "equipment_name": "CNC 9"})
        failure = client.post("/predict/failure", json={
            **OBSERVATION, "equipment_id": anomaly.json()["equipment_id"]
        })
        assert anomaly.status_code == failure.status_code == 200
        prediction_id = failure.json()["prediction_id"]
        equipment_id = anomaly.json()["equipment_id"]
        reading_id = failure.json()["reading_id"]
        persisted = client.get(f"/predictions/{prediction_id}")
        history = client.get(f"/equipment/{equipment_id}/history")
        equipment = client.get("/equipment")
        assert persisted.status_code == 200
        assert persisted.json()["failure_probability"] == failure.json()["failure_probability"]
        assert history.status_code == 200
        assert len(history.json()["items"]) == 2
        assert len(equipment.json()) == 1
        assert any(item["reading"]["id"] == reading_id for item in history.json()["items"])

    with TestClient(create_app(MODEL_DIR, database_url=url)) as restarted:
        assert restarted.get(f"/predictions/{prediction_id}").status_code == 200
        assert len(restarted.get(f"/equipment/{equipment_id}/history").json()["items"]) == 2


def test_database_write_failure_rolls_back_and_never_returns_success(tmp_path: Path) -> None:
    url = db_url(tmp_path / "failure.sqlite3")
    with TestClient(create_app(MODEL_DIR, database_url=url)) as client:
        engine = client.app.state.database.engine

        def fail_prediction_insert(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO PREDICTIONS"):
                raise OperationalError(statement, parameters, RuntimeError("write failed"))

        event.listen(engine, "before_cursor_execute", fail_prediction_insert)
        response = client.post("/predict/anomaly", json=OBSERVATION)
        event.remove(engine, "before_cursor_execute", fail_prediction_insert)
        assert response.status_code == 503
        assert response.json() == {"detail": "Prediction could not be persisted"}
        with client.app.state.database.session() as session:
            assert session.scalar(select(Equipment)) is None
            assert session.scalar(select(SensorReading)) is None
            assert session.scalar(select(Prediction)) is None


def test_database_initialization_failure_keeps_health_and_marks_unready() -> None:
    with TestClient(create_app(MODEL_DIR, database_url="unsupported://database")) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        prediction = client.post("/predict/anomaly", json=OBSERVATION)
    assert ready.status_code == 503
    assert ready.json()["database"] is False
    assert prediction.status_code == 503
    assert prediction.json() == {"detail": "Prediction could not be persisted"}


def test_readiness_detects_database_outage_and_recovers(tmp_path: Path) -> None:
    url = db_url(tmp_path / "readiness.sqlite3")
    with TestClient(create_app(MODEL_DIR, database_url=url)) as client:
        assert client.get("/ready").status_code == 200
        engine = client.app.state.database.engine

        def fail_connection_check(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper() == "SELECT 1":
                raise OperationalError(statement, parameters, RuntimeError("database unavailable"))

        event.listen(engine, "before_cursor_execute", fail_connection_check)
        unavailable = client.get("/ready")
        health = client.get("/health")
        assert unavailable.status_code == 503
        assert unavailable.json() == {
            "status": "not_ready",
            "models": {"anomaly": True, "failure": True},
            "database": False,
        }
        assert health.status_code == 200
        event.remove(engine, "before_cursor_execute", fail_connection_check)

        recovered = client.get("/ready")
        assert recovered.status_code == 200
        assert recovered.json()["database"] is True
