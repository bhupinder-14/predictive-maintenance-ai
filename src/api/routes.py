"""HTTP routes for health, readiness, and model predictions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .model_registry import ModelUnavailableError
from .prediction_service import PredictionExecutionError, PredictionService
from .schemas import (
    AnomalyPredictionResponse,
    FailurePredictionResponse,
    HealthResponse,
    ReadinessResponse,
    SensorObservation,
)

router = APIRouter()


def _prediction_service(request: Request) -> PredictionService:
    return request.app.state.prediction_service


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
    if registry.is_ready:
        return ReadinessResponse(status="ready", models=registry.readiness)
    body = ReadinessResponse(status="not_ready", models=registry.readiness)
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
        return _prediction_service(request).predict_anomaly(observation)
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
        return _prediction_service(request).predict_failure(observation)
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
