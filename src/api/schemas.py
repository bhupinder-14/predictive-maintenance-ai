"""Pydantic request and response schemas for prediction endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    anomaly_score: float = Field(description="Isolation Forest score; not a failure probability")
    classification: Literal["normal", "anomaly"]
    model_version: str
    prediction_timestamp: datetime
    inference_latency_ms: float = Field(ge=0)
    explanation: AnomalyExplanation


class FailurePredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: UUID
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
