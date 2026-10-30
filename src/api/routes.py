"""HTTP routes for health, readiness, and model predictions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from .model_registry import ModelUnavailableError
from .prediction_service import PredictionExecutionError, PredictionService
from .schemas import (
    AnomalyPredictionResponse,
    EquipmentHistoryResponse,
    EquipmentResponse,
    FailurePredictionResponse,
    HealthResponse,
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
        return _prediction_workflow(request).predict_anomaly(observation)
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
        return _prediction_workflow(request).predict_failure(observation)
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
