"""Database operations and historical queries, separate from HTTP routes."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import Equipment, MonitoringReport, Prediction, SensorReading


class EquipmentNotFoundError(LookupError):
    """Raised when a supplied equipment id does not exist."""


class PredictionNotFoundError(LookupError):
    """Raised when a requested prediction id does not exist."""


def utc_datetime(value: datetime) -> datetime:
    """Normalize a database timestamp to an aware UTC datetime for API output."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PredictionRepository:
    """Reusable writes and SQL-based history queries."""

    @staticmethod
    def resolve_equipment(
        session: Session,
        *,
        equipment_id: int | None,
        equipment_name: str | None,
        equipment_type: str,
        location: str | None,
    ) -> Equipment:
        if equipment_id is not None:
            equipment = session.get(Equipment, equipment_id)
            if equipment is None:
                raise EquipmentNotFoundError(equipment_id)
            return equipment

        name = equipment_name or f"Unidentified equipment {uuid4().hex[:10]}"
        query = select(Equipment).where(Equipment.name == name)
        if location is None:
            query = query.where(Equipment.location.is_(None))
        else:
            query = query.where(Equipment.location == location)
        equipment = session.scalar(query.order_by(Equipment.id).limit(1))
        if equipment is not None:
            return equipment

        equipment = Equipment(name=name, equipment_type=equipment_type, location=location)
        session.add(equipment)
        session.flush()
        return equipment

    @staticmethod
    def create_sensor_reading(
        session: Session,
        *,
        equipment_id: int,
        observation: Any,
        timestamp: datetime,
        source: str = "api",
    ) -> SensorReading:
        reading = SensorReading(
            equipment_id=equipment_id,
            timestamp=timestamp,
            machine_type=observation.Type,
            air_temperature_k=observation.air_temperature_k,
            process_temperature_k=observation.process_temperature_k,
            rotational_speed_rpm=observation.rotational_speed_rpm,
            torque_nm=observation.torque_nm,
            tool_wear_min=observation.tool_wear_min,
            source=source,
        )
        session.add(reading)
        session.flush()
        return reading

    @staticmethod
    def create_prediction(
        session: Session,
        *,
        prediction_id: str,
        equipment_id: int,
        reading_id: int,
        model_version: str,
        anomaly_score: float | None,
        is_anomaly: bool | None,
        failure_probability: float | None,
        latency_ms: float,
        created_at: datetime,
    ) -> Prediction:
        prediction = Prediction(
            id=prediction_id,
            equipment_id=equipment_id,
            reading_id=reading_id,
            model_version=model_version,
            anomaly_score=anomaly_score,
            is_anomaly=is_anomaly,
            failure_probability=failure_probability,
            latency_ms=latency_ms,
            created_at=created_at,
        )
        session.add(prediction)
        session.flush()
        return prediction

    @staticmethod
    def list_equipment(session: Session, *, limit: int, offset: int) -> list[Equipment]:
        return list(
            session.scalars(
                select(Equipment).order_by(Equipment.id).limit(limit).offset(offset)
            ).all()
        )

    @staticmethod
    def equipment_history(
        session: Session,
        *,
        equipment_id: int,
        limit: int,
        offset: int,
    ) -> tuple[Equipment, list[SensorReading]]:
        equipment = session.get(Equipment, equipment_id)
        if equipment is None:
            raise EquipmentNotFoundError(equipment_id)
        readings = list(
            session.scalars(
                select(SensorReading)
                .where(SensorReading.equipment_id == equipment_id)
                .options(selectinload(SensorReading.predictions))
                .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return equipment, readings

    @staticmethod
    def get_prediction(session: Session, prediction_id: str) -> Prediction:
        prediction = session.get(Prediction, prediction_id)
        if prediction is None:
            raise PredictionNotFoundError(prediction_id)
        return prediction

    @staticmethod
    def latest_readings_by_equipment(
        session: Session,
        *,
        equipment_id: int,
        limit: int = 1,
    ) -> list[SensorReading]:
        return list(
            session.scalars(
                select(SensorReading)
                .where(SensorReading.equipment_id == equipment_id)
                .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc())
                .limit(limit)
            ).all()
        )

    @staticmethod
    def predictions_in_range(
        session: Session,
        *,
        start: datetime,
        end: datetime,
        equipment_id: int | None = None,
    ) -> list[Prediction]:
        start_utc = utc_datetime(start).replace(tzinfo=None)
        end_utc = utc_datetime(end).replace(tzinfo=None)
        statement = select(Prediction).where(
            Prediction.created_at >= start_utc,
            Prediction.created_at <= end_utc,
        )
        if equipment_id is not None:
            statement = statement.where(Prediction.equipment_id == equipment_id)
        return list(session.scalars(statement.order_by(Prediction.created_at)).all())

    @staticmethod
    def most_frequently_flagged_equipment(
        session: Session,
        *,
        limit: int = 10,
    ) -> list[tuple[Equipment, int]]:
        rows = session.execute(
            select(Equipment, func.count(Prediction.id).label("flag_count"))
            .join(Prediction, Prediction.equipment_id == Equipment.id)
            .where(Prediction.is_anomaly.is_(True))
            .group_by(Equipment.id)
            .order_by(func.count(Prediction.id).desc(), Equipment.id)
            .limit(limit)
        ).all()
        return [(equipment, int(count)) for equipment, count in rows]

    @staticmethod
    def average_anomaly_score_by_equipment(
        session: Session,
    ) -> list[tuple[Equipment, float]]:
        rows = session.execute(
            select(Equipment, func.avg(Prediction.anomaly_score).label("avg_score"))
            .join(Prediction, Prediction.equipment_id == Equipment.id)
            .where(Prediction.anomaly_score.is_not(None))
            .group_by(Equipment.id)
            .order_by(Equipment.id)
        ).all()
        return [(equipment, float(score)) for equipment, score in rows]

    @staticmethod
    def prediction_counts_by_model_version(session: Session) -> dict[str, int]:
        rows = session.execute(
            select(Prediction.model_version, func.count(Prediction.id))
            .group_by(Prediction.model_version)
            .order_by(Prediction.model_version)
        ).all()
        return {str(version): int(count) for version, count in rows}

    @staticmethod
    def latency_summary(session: Session) -> dict[str, float | int | None]:
        values = list(
            session.scalars(
                select(Prediction.latency_ms).order_by(Prediction.latency_ms)
            ).all()
        )
        if not values:
            return {"count": 0, "average_ms": None, "p95_ms": None}
        rank = max(1, math.ceil(0.95 * len(values)))
        return {
            "count": len(values),
            "average_ms": float(sum(values) / len(values)),
            "p95_ms": float(values[rank - 1]),
        }

    @staticmethod
    def create_monitoring_report(session: Session, **fields: Any) -> MonitoringReport:
        report = MonitoringReport(**fields)
        session.add(report)
        session.flush()
        return report

    @staticmethod
    def latest_monitoring_report(session: Session) -> MonitoringReport | None:
        """Return the newest report, using its primary key to break timestamp ties."""
        return session.scalar(
            select(MonitoringReport)
            .order_by(MonitoringReport.created_at.desc(), MonitoringReport.id.desc())
            .limit(1)
        )
