"""HTTP routes for health, readiness, and model predictions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from .model_registry import ModelUnavailableError
from .prediction_service import PredictionExecutionError, PredictionService
from .schemas import (
    AnomalyPredictionResponse,
    DriftReportResponse,
    DriftRequest,
    EquipmentHistoryResponse,
    EquipmentResponse,
    FailurePredictionResponse,
    HealthResponse,
    OperationalMetricsResponse,
    PersistedDriftReportResponse,
    PredictionRecordResponse,
    ReadinessResponse,
    SensorObservation,
)
from src.database.prediction_workflow import (
    DatabaseUnavailableError,
    PredictionWorkflow,
    PersistenceError,
)
from src.database.repository import EquipmentNotFoundError, PredictionNotFoundError
from src.monitoring.drift import DriftDetector

router = APIRouter()


def _prediction_service(request: Request) -> PredictionService:
    return request.app.state.prediction_service


def _prediction_workflow(request: Request) -> PredictionWorkflow:
    return request.app.state.prediction_workflow


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Return basic process health; model readiness is reported separately."""
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    tags=["health"],
)
def ready(request: Request) -> ReadinessResponse | JSONResponse:
    """Report whether both required model bundles are loaded and compatible."""
    registry = request.app.state.model_registry
    database_ready = request.app.state.database.check_connection()
    request.app.state.database_ready = database_ready
    if registry.is_ready and database_ready:
        return ReadinessResponse(
            status="ready", models=registry.readiness, database=True
        )
    body = ReadinessResponse(
        status="not_ready", models=registry.readiness, database=database_ready
    )
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump())


@router.get(
    "/monitoring/metrics",
    response_model=OperationalMetricsResponse,
    tags=["monitoring"],
)
@router.get(
    "/metrics/summary",
    response_model=OperationalMetricsResponse,
    tags=["monitoring"],
)
def monitoring_metrics(request: Request) -> OperationalMetricsResponse:
    """Return operational counters and a live readiness snapshot."""
    database_available = request.app.state.database.check_connection()
    request.app.state.database_ready = database_available
    return OperationalMetricsResponse.model_validate(
        request.app.state.operational_metrics.snapshot(
            model_availability=request.app.state.model_registry.operational_status,
            database_available=database_available,
        )
    )


@router.post(
    "/monitoring/drift",
    response_model=DriftReportResponse,
    tags=["monitoring"],
    responses={503: {"description": "Drift reference is unavailable"}},
)
def evaluate_drift(payload: DriftRequest, request: Request) -> DriftReportResponse:
    """Compare a validated batch against the saved training-split reference."""
    detector: DriftDetector | None = request.app.state.drift_detector
    if detector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift reference is unavailable",
        )
    try:
        report = detector.evaluate(
            [observation.as_model_features() for observation in payload.observations]
        )
        created_at = report["generated_at"]
        versions = {
            family: artifact.metadata.model_version
            for family, artifact in request.app.state.model_registry.artifacts.items()
        }
        methodologies = sorted({item["method"] for item in report["features"]})
        method_thresholds = [
            {
                "feature_name": item["feature_name"],
                "method": item["method"],
                "threshold": item["threshold"],
                "threshold_kind": item["threshold_kind"],
            }
            for item in report["features"]
        ]
        current_size = report["current_sample_size"]
        request.app.state.prediction_workflow.persist_drift_report(
            model_version=(
                ";".join(f"{family}={version}" for family, version in sorted(versions.items()))
                or "not_model_specific"
            ),
            reference_version=report["reference_version"],
            batch_description=(
                f"Batch of {current_size} validated observations evaluated at "
                f"{created_at.isoformat()}; the dataset has no chronological sequence."
            ),
            methodology={
                "methods": methodologies,
                "feature_thresholds": method_thresholds,
            },
            report_metadata={
                "generated_at": created_at.isoformat(),
                "reference_sample_size": report["reference_sample_size"],
                "current_sample_size": current_size,
                "minimum_sample_size": report["minimum_sample_size"],
                "overall_status": report["overall_status"],
                "interpretation": report["interpretation"],
                "model_versions": versions,
            },
            feature_results=report["features"],
            window_start=created_at,
            window_end=created_at,
            drift_metric=None,
            drift_status=report["overall_status"],
            created_at=created_at,
        )
        return DriftReportResponse.model_validate(report)
    except (DatabaseUnavailableError, PersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drift report could not be persisted",
        ) from None
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Drift batch could not be evaluated",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Drift evaluation could not be completed",
        ) from None


@router.get(
    "/monitoring/drift",
    response_model=PersistedDriftReportResponse,
    tags=["monitoring"],
    responses={404: {"description": "No drift report has been saved"}},
)
def latest_drift_report(request: Request) -> PersistedDriftReportResponse:
    """Return the latest saved report without reevaluating any observations."""
    try:
        report = request.app.state.prediction_workflow.latest_drift_report()
    except (DatabaseUnavailableError, PersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from None
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No drift report is available",
        )
    return report


@router.post(
    "/predict/anomaly",
    response_model=AnomalyPredictionResponse,
    tags=["predictions"],
)
def anomaly_prediction(
    observation: SensorObservation,
    request: Request,
) -> AnomalyPredictionResponse:
    """Score one observation for anomalous sensor patterns."""
    try:
        result = _prediction_workflow(request).predict_anomaly(observation)
        request.app.state.operational_metrics.record_anomaly_prediction(
            result.classification, result.model_version
        )
        return result
    except EquipmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Equipment was not found") from exc
    except (DatabaseUnavailableError, PersistenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction could not be persisted",
        ) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anomaly model is unavailable",
        ) from exc
    except PredictionExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction could not be completed",
        ) from exc


@router.post(
    "/predict/failure",
    response_model=FailurePredictionResponse,
    tags=["predictions"],
)
def failure_prediction(
    observation: SensorObservation,
    request: Request,
) -> FailurePredictionResponse:
    """Classify the failure label associated with one observation row."""
    try:
        result = _prediction_workflow(request).predict_failure(observation)
        request.app.state.operational_metrics.record_failure_prediction(
            result.predicted_class, result.model_version
        )
        return result
    except EquipmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Equipment was not found") from exc
    except (DatabaseUnavailableError, PersistenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction could not be persisted",
        ) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failure model is unavailable",
        ) from exc
    except PredictionExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction could not be completed",
        ) from exc


@router.get("/equipment", response_model=list[EquipmentResponse], tags=["equipment"])
def list_equipment(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[EquipmentResponse]:
    """List registered equipment, newest numeric ids last."""
    try:
        return _prediction_workflow(request).list_equipment(limit=limit, offset=offset)
    except (DatabaseUnavailableError, PersistenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@router.get(
    "/equipment/{equipment_id}/history",
    response_model=EquipmentHistoryResponse,
    tags=["equipment"],
)
def equipment_history(
    equipment_id: int,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EquipmentHistoryResponse:
    """Return persisted sensor readings and their prediction records."""
    try:
        return _prediction_workflow(request).equipment_history(
            equipment_id=equipment_id,
            limit=limit,
            offset=offset,
        )
    except EquipmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Equipment was not found") from exc
    except (DatabaseUnavailableError, PersistenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc


@router.get(
    "/predictions/{prediction_id}",
    response_model=PredictionRecordResponse,
    tags=["predictions"],
)
def get_prediction(
    prediction_id: UUID,
    request: Request,
) -> PredictionRecordResponse:
    """Retrieve one saved prediction by its response ID."""
    try:
        return _prediction_workflow(request).get_prediction(str(prediction_id))
    except PredictionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Prediction was not found") from exc
    except (DatabaseUnavailableError, PersistenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
    except PredictionExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction could not be completed",
        ) from exc
