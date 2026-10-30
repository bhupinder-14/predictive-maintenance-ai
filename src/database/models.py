"""SQLAlchemy models for the Milestone 3 SQLite schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all persisted entities."""


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (Index("ix_equipment_name", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    readings: Mapped[list[SensorReading]] = relationship(back_populates="equipment")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="equipment")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        CheckConstraint('"Type" IN (\'L\', \'M\', \'H\')', name="ck_reading_type"),
        CheckConstraint('"Air temperature [K]" BETWEEN 290 AND 310', name="ck_reading_air_temp"),
        CheckConstraint('"Process temperature [K]" BETWEEN 300 AND 320', name="ck_reading_process_temp"),
        CheckConstraint('"Rotational speed [rpm]" BETWEEN 1000 AND 3000', name="ck_reading_speed"),
        CheckConstraint('"Torque [Nm]" BETWEEN 0 AND 100', name="ck_reading_torque"),
        CheckConstraint('"Tool wear [min]" BETWEEN 0 AND 300', name="ck_reading_tool_wear"),
        UniqueConstraint("id", "equipment_id", name="uq_reading_id_equipment"),
        Index("ix_sensor_readings_equipment_timestamp", "equipment_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    machine_type: Mapped[str] = mapped_column("Type", String(1), nullable=False)
    air_temperature_k: Mapped[float] = mapped_column("Air temperature [K]", Float, nullable=False)
    process_temperature_k: Mapped[float] = mapped_column("Process temperature [K]", Float, nullable=False)
    rotational_speed_rpm: Mapped[float] = mapped_column("Rotational speed [rpm]", Float, nullable=False)
    torque_nm: Mapped[float] = mapped_column("Torque [Nm]", Float, nullable=False)
    tool_wear_min: Mapped[float] = mapped_column("Tool wear [min]", Float, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="api", server_default="api")

    equipment: Mapped[Equipment] = relationship(back_populates="readings")
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="reading", foreign_keys="Prediction.reading_id"
    )


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="ck_prediction_latency_nonnegative"),
        CheckConstraint(
            "failure_probability IS NULL OR failure_probability BETWEEN 0 AND 1",
            name="ck_prediction_failure_probability",
        ),
        ForeignKeyConstraint(
            ["reading_id", "equipment_id"],
            ["sensor_readings.id", "sensor_readings.equipment_id"],
            ondelete="RESTRICT",
            name="fk_prediction_reading_equipment",
        ),
        CheckConstraint(
            "((anomaly_score IS NOT NULL AND is_anomaly IS NOT NULL AND failure_probability IS NULL) "
            "OR (anomaly_score IS NULL AND is_anomaly IS NULL AND failure_probability IS NOT NULL))",
            name="ck_prediction_result_kind",
        ),
        Index("ix_predictions_equipment_created", "equipment_id", "created_at"),
        Index("ix_predictions_version_created", "model_version", "created_at"),
        Index("ix_predictions_anomaly_equipment", "is_anomaly", "equipment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    reading_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    is_anomaly: Mapped[bool | None] = mapped_column(Boolean)
    failure_probability: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    equipment: Mapped[Equipment] = relationship(back_populates="predictions")
    reading: Mapped[SensorReading] = relationship(
        back_populates="predictions", foreign_keys=[reading_id]
    )


class MonitoringReport(Base):
    __tablename__ = "monitoring_reports"
    __table_args__ = (
        CheckConstraint("window_end >= window_start", name="ck_monitoring_window_order"),
        Index("ix_monitoring_reports_model_created", "model_version", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    drift_metric: Mapped[float | None] = mapped_column(Float)
    drift_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_version: Mapped[str | None] = mapped_column(String(80))
    batch_description: Mapped[str | None] = mapped_column(String(255))
    methodology: Mapped[dict | None] = mapped_column(JSON)
    report_metadata: Mapped[dict | None] = mapped_column(JSON)
    feature_results: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
