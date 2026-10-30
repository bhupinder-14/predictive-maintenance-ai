"""Atomic workflow connecting database persistence with existing model inference."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from src.api.prediction_service import PredictionService
from src.api.schemas import (
    AnomalyPredictionResponse,
    EquipmentHistoryResponse,
    EquipmentResponse,
    FailurePredictionResponse,
    PersistedDriftReportResponse,
    PredictionRecordResponse,
    SensorObservation,
)

from .manager import Database
from .presenters import (
    present_equipment,
    present_history,
    present_monitoring_report,
    present_prediction,
)
from .repository import (
    EquipmentNotFoundError,
    PredictionNotFoundError,
    PredictionRepository,
    utc_datetime,
)

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """Raised when application database initialization is not ready."""


class PersistenceError(RuntimeError):
    """Raised when a database transaction could not commit safely."""


class PredictionWorkflow:
    """Persist equipment/readings and model output in one database transaction."""

    def __init__(
        self,
        database: Database,
        inference: PredictionService,
        repository: type[PredictionRepository] = PredictionRepository,
    ) -> None:
        self.database = database
        self.inference = inference
        self.repository = repository

    def predict_anomaly(self, observation: SensorObservation) -> AnomalyPredictionResponse:
        return self._persist_prediction(observation, model_name="anomaly")

    def predict_failure(self, observation: SensorObservation) -> FailurePredictionResponse:
        return self._persist_prediction(observation, model_name="failure")

    def _persist_prediction(
        self,
        observation: SensorObservation,
        *,
        model_name: str,
    ) -> AnomalyPredictionResponse | FailurePredictionResponse:
        if not self.database.initialized:
            raise DatabaseUnavailableError("Database is unavailable")

        reading_timestamp = observation.observed_at or datetime.now(timezone.utc)
        response: AnomalyPredictionResponse | FailurePredictionResponse
        try:
            with self.database.session() as session:
                with session.begin():
                    equipment = self.repository.resolve_equipment(
                        session,
                        equipment_id=observation.equipment_id,
                        equipment_name=observation.equipment_name,
                        equipment_type=observation.Type,
                        location=observation.equipment_location,
                    )
                    reading = self.repository.create_sensor_reading(
                        session,
                        equipment_id=equipment.id,
                        observation=observation,
                        timestamp=reading_timestamp,
                        source="api",
                    )
                    if model_name == "anomaly":
                        response = self.inference.predict_anomaly(
                            observation,
                            equipment_id=equipment.id,
                            reading_id=reading.id,
                        )
                        anomaly_score = response.anomaly_score
                        is_anomaly = response.classification == "anomaly"
                        failure_probability = None
                    else:
                        response = self.inference.predict_failure(
                            observation,
                            equipment_id=equipment.id,
                            reading_id=reading.id,
                        )
                        anomaly_score = None
                        is_anomaly = None
                        failure_probability = response.failure_probability

                    self.repository.create_prediction(
                        session,
                        prediction_id=str(response.prediction_id),
                        equipment_id=equipment.id,
                        reading_id=reading.id,
                        model_version=response.model_version,
                        anomaly_score=anomaly_score,
                        is_anomaly=is_anomaly,
                        failure_probability=failure_probability,
                        latency_ms=response.inference_latency_ms,
                        created_at=response.prediction_timestamp,
                    )
        except (EquipmentNotFoundError, PredictionNotFoundError):
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Prediction persistence failed model=%s error_type=%s",
                model_name,
                type(exc).__name__,
            )
            raise PersistenceError("Prediction could not be persisted") from exc

        logger.info(
            "Prediction outcome=persisted prediction_id=%s equipment_id=%s reading_id=%s model=%s "
            "model_version=%s timestamp=%s latency_ms=%.3f",
            response.prediction_id,
            response.equipment_id,
            response.reading_id,
            model_name,
            response.model_version,
            utc_datetime(response.prediction_timestamp).isoformat(),
            response.inference_latency_ms,
        )
        return response

    def list_equipment(self, *, limit: int, offset: int) -> list[EquipmentResponse]:
        return self._read(lambda session: [
            present_equipment(equipment)
            for equipment in self.repository.list_equipment(
                session, limit=limit, offset=offset
            )
        ])

    def equipment_history(
        self,
        *,
        equipment_id: int,
        limit: int,
        offset: int,
    ) -> EquipmentHistoryResponse:
        return self._read(lambda session: present_history(*self.repository.equipment_history(
            session,
            equipment_id=equipment_id,
            limit=limit,
            offset=offset,
        )))

    def get_prediction(self, prediction_id: str) -> PredictionRecordResponse:
        return self._read(lambda session: present_prediction(
            self.repository.get_prediction(session, prediction_id)
        ))

    def persist_drift_report(self, **fields: Any) -> int:
        """Save one complete drift report atomically and return its database ID."""
        if not self.database.initialized:
            raise DatabaseUnavailableError("Database is unavailable")
        try:
            with self.database.session() as session, session.begin():
                report = self.repository.create_monitoring_report(session, **fields)
                report_id = report.id
            return report_id
        except SQLAlchemyError as exc:
            logger.error("Drift report persistence failed error_type=%s", type(exc).__name__)
            raise PersistenceError("Drift report could not be persisted") from exc

    def latest_drift_report(self) -> PersistedDriftReportResponse | None:
        """Return the newest persisted report, or ``None`` when history is empty."""
        def load(session):
            report = self.repository.latest_monitoring_report(session)
            return present_monitoring_report(report) if report is not None else None

        return self._read(load)

    def _read(self, operation):
        if not self.database.initialized:
            raise DatabaseUnavailableError("Database is unavailable")
        try:
            with self.database.session() as session:
                return operation(session)
        except (EquipmentNotFoundError, PredictionNotFoundError):
            raise
        except SQLAlchemyError as exc:
            logger.error("Database read failed error_type=%s", type(exc).__name__)
            raise PersistenceError("Database request could not be completed") from exc
