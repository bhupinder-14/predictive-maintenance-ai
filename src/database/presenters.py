"""Convert persisted ORM records into stable API response schemas."""

from __future__ import annotations

from src.api.schemas import (
    EquipmentHistoryEntry,
    EquipmentHistoryResponse,
    EquipmentResponse,
    PredictionRecordResponse,
    PredictionSummaryResponse,
    SensorReadingResponse,
)

from .models import Equipment, Prediction, SensorReading
from .repository import utc_datetime


def present_equipment(equipment: Equipment) -> EquipmentResponse:
    return EquipmentResponse(
        id=equipment.id,
        name=equipment.name,
        equipment_type=equipment.equipment_type,
        location=equipment.location,
        created_at=utc_datetime(equipment.created_at),
    )


def present_reading(reading: SensorReading) -> SensorReadingResponse:
    return SensorReadingResponse.model_validate(
        {
            "id": reading.id,
            "equipment_id": reading.equipment_id,
            "timestamp": utc_datetime(reading.timestamp),
            "Type": reading.machine_type,
            "Air temperature [K]": reading.air_temperature_k,
            "Process temperature [K]": reading.process_temperature_k,
            "Rotational speed [rpm]": reading.rotational_speed_rpm,
            "Torque [Nm]": reading.torque_nm,
            "Tool wear [min]": reading.tool_wear_min,
            "source": reading.source,
        }
    )


def present_prediction_summary(prediction: Prediction) -> PredictionSummaryResponse:
    return PredictionSummaryResponse(
        id=prediction.id,
        model_version=prediction.model_version,
        anomaly_score=prediction.anomaly_score,
        is_anomaly=prediction.is_anomaly,
        failure_probability=prediction.failure_probability,
        latency_ms=prediction.latency_ms,
        created_at=utc_datetime(prediction.created_at),
    )


def present_prediction(prediction: Prediction) -> PredictionRecordResponse:
    return PredictionRecordResponse(
        id=prediction.id,
        equipment_id=prediction.equipment_id,
        reading_id=prediction.reading_id,
        model_version=prediction.model_version,
        anomaly_score=prediction.anomaly_score,
        is_anomaly=prediction.is_anomaly,
        failure_probability=prediction.failure_probability,
        latency_ms=prediction.latency_ms,
        created_at=utc_datetime(prediction.created_at),
    )


def present_history(
    equipment: Equipment,
    readings: list[SensorReading],
) -> EquipmentHistoryResponse:
    return EquipmentHistoryResponse(
        equipment=present_equipment(equipment),
        items=[
            EquipmentHistoryEntry(
                reading=present_reading(reading),
                predictions=[
                    present_prediction_summary(prediction)
                    for prediction in reading.predictions
                ],
            )
            for reading in readings
        ],
    )
