"""Pydantic request and response schemas for prediction endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    model_validator,
)


class SensorObservation(BaseModel):
    """One observation using only the raw features accepted by the models."""

    model_config = ConfigDict(extra="forbid")

    Type: Literal["L", "M", "H"] = Field(description="AI4I product quality type")
    air_temperature_k: Annotated[
        float, Field(alias="Air temperature [K]", strict=True, ge=290, le=310)
    ]
    process_temperature_k: Annotated[
        float, Field(alias="Process temperature [K]", strict=True, ge=300, le=320)
    ]
    rotational_speed_rpm: Annotated[
        float, Field(alias="Rotational speed [rpm]", strict=True, ge=1000, le=3000)
    ]
    torque_nm: Annotated[
        float, Field(alias="Torque [Nm]", strict=True, ge=0, le=100)
    ]
    tool_wear_min: Annotated[
        float, Field(alias="Tool wear [min]", strict=True, ge=0, le=300)
    ]
    equipment_id: PositiveInt | None = None
    equipment_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ] | None = None
    equipment_location: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
    ] | None = None
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def equipment_identifier_is_unambiguous(self) -> SensorObservation:
        if self.equipment_id is not None and (
            self.equipment_name is not None or self.equipment_location is not None
        ):
            raise ValueError(
                "Provide equipment_id or new equipment name/location, not both"
            )
        return self

    def as_model_features(self) -> dict[str, str | float]:
        """Return values under the exact raw column names expected by preprocessing."""
        return {
            "Type": self.Type,
            "Air temperature [K]": self.air_temperature_k,
            "Process temperature [K]": self.process_temperature_k,
            "Rotational speed [rpm]": self.rotational_speed_rpm,
            "Torque [Nm]": self.torque_nm,
            "Tool wear [min]": self.tool_wear_min,
        }


class SuspiciousFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    standardised_value: float
    abs_deviation: float = Field(ge=0)


class AnomalyExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    anomaly_score: float
    top_suspicious_features: list[SuspiciousFeature]


class AnomalyPredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: UUID
    equipment_id: int
    reading_id: int
    anomaly_score: float = Field(description="Isolation Forest score; not a failure probability")
    classification: Literal["normal", "anomaly"]
    model_version: str
    prediction_timestamp: datetime
    inference_latency_ms: float = Field(ge=0)
    explanation: AnomalyExplanation


class FailurePredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: UUID
    equipment_id: int
    reading_id: int
    predicted_class: Literal[0, 1]
    failure_probability: float = Field(ge=0, le=1)
    model_version: str
    prediction_timestamp: datetime
    inference_latency_ms: float = Field(ge=0)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    models: dict[str, bool]
    database: bool


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    equipment_type: str
    location: str | None
    created_at: datetime


class SensorReadingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    equipment_id: int
    timestamp: datetime
    machine_type: Literal["L", "M", "H"] = Field(alias="Type")
    air_temperature_k: float = Field(alias="Air temperature [K]")
    process_temperature_k: float = Field(alias="Process temperature [K]")
    rotational_speed_rpm: float = Field(alias="Rotational speed [rpm]")
    torque_nm: float = Field(alias="Torque [Nm]")
    tool_wear_min: float = Field(alias="Tool wear [min]")
    source: str


class PredictionSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    model_version: str
    anomaly_score: float | None
    is_anomaly: bool | None
    failure_probability: float | None
    latency_ms: float
    created_at: datetime


class EquipmentHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reading: SensorReadingResponse
    predictions: list[PredictionSummaryResponse]


class EquipmentHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment: EquipmentResponse
    items: list[EquipmentHistoryEntry]


class PredictionRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    equipment_id: int
    reading_id: int
    model_version: str
    anomaly_score: float | None
    is_anomaly: bool | None
    failure_probability: float | None
    latency_ms: float
    created_at: datetime
