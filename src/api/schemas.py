"""Pydantic request and response schemas for prediction endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
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


class SensorFeatures(BaseModel):
    """The six supported raw AI4I sensor features, with no targets or IDs."""

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
        """Return only the exact raw feature names used by trained models."""
        return {
            "Type": self.Type,
            "Air temperature [K]": self.air_temperature_k,
            "Process temperature [K]": self.process_temperature_k,
            "Rotational speed [rpm]": self.rotational_speed_rpm,
            "Torque [Nm]": self.torque_nm,
            "Tool wear [min]": self.tool_wear_min,
        }


class SensorObservation(SensorFeatures):
    """One inference observation plus optional persistence metadata."""

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



class DriftRequest(BaseModel):
    """A bounded batch containing only supported sensor features."""

    model_config = ConfigDict(extra="forbid")

    observations: Annotated[list[SensorFeatures], Field(min_length=1, max_length=10_000)]


class FeatureDriftResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str
    method: Literal["kolmogorov_smirnov_two_sample", "total_variation_distance"]
    statistic: float | None
    p_value: float | None
    threshold: float
    threshold_kind: Literal["p_value_significance_level", "distance_threshold"]
    drift_detected: bool | None
    reference_sample_size: int
    current_sample_size: int


class DriftReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_version: str
    generated_at: datetime
    reference_sample_size: int
    current_sample_size: int
    minimum_sample_size: int
    overall_status: Literal["drift_detected", "no_drift_detected", "insufficient_data"]
    features: list[FeatureDriftResult]
    interpretation: str


class PersistedDriftReportResponse(DriftReportResponse):
    """Latest saved drift result, including database and batch metadata."""

    report_id: int
    created_at: datetime
    window_start: datetime
    window_end: datetime
    batch_description: str
    reference_version: str
    methodology: dict[str, Any]
    report_metadata: dict[str, Any]
    model_version: str


class EndpointRequestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: int
    successful: int
    failed: int
    status_codes: dict[str, int]
    duration_ms: dict[str, float]


class RequestMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    successful: int
    failed: int
    status_codes: dict[str, int]
    by_endpoint: dict[str, EndpointRequestMetrics]
    duration_ms: dict[str, float]


class PredictionMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly: dict[str, Any]
    failure: dict[str, Any]
    errors: dict[str, Any]


class RuntimeMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uptime_seconds: float
    metrics_storage: Literal["in_memory_process_local"]


class AvailabilityMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: dict[str, dict[str, str | bool | None]]
    database_available: bool | None


class RollingMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_seconds: int
    requests: RequestMetricsResponse
    predictions: PredictionMetricsResponse


class OperationalMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: RequestMetricsResponse
    predictions: PredictionMetricsResponse
    runtime: RuntimeMetricsResponse
    availability: AvailabilityMetricsResponse
    rolling_window: RollingMetricsResponse


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
