"""Model inference orchestration independent of FastAPI route handling."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import pandas as pd

from src.anomaly_model import predict_anomaly
from src.failure_model import predict_failure

from .model_registry import ModelRegistry, ModelUnavailableError
from .schemas import (
    AnomalyExplanation,
    AnomalyPredictionResponse,
    FailurePredictionResponse,
    SensorObservation,
)

logger = logging.getLogger(__name__)


class PredictionExecutionError(RuntimeError):
    """Raised when validated model inference cannot be completed."""


class PredictionService:
    """Create API response records from validated observations and loaded models."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def predict_anomaly(self, observation: SensorObservation) -> AnomalyPredictionResponse:
        return self._predict("anomaly", observation)

    def predict_failure(self, observation: SensorObservation) -> FailurePredictionResponse:
        return self._predict("failure", observation)

    def _predict(
        self,
        model_name: str,
        observation: SensorObservation,
    ) -> AnomalyPredictionResponse | FailurePredictionResponse:
        prediction_id = uuid4()
        started = perf_counter()
        timestamp = datetime.now(timezone.utc)
        model_version: str | None = None

        try:
            artifact = self.registry.require(model_name)
            model_version = artifact.metadata.model_version
            features = pd.DataFrame([observation.as_model_features()])

            if model_name == "anomaly":
                result = predict_anomaly(artifact, features)[0]
                latency_ms = (perf_counter() - started) * 1000
                timestamp = datetime.now(timezone.utc)
                response = AnomalyPredictionResponse(
                    prediction_id=prediction_id,
                    anomaly_score=result.anomaly_score,
                    classification="anomaly" if result.is_anomaly else "normal",
                    model_version=model_version,
                    prediction_timestamp=timestamp,
                    inference_latency_ms=latency_ms,
                    explanation=AnomalyExplanation.model_validate(result.explanation),
                )
            else:
                result = predict_failure(artifact, features)[0]
                if result.failure_probability is None:
                    raise RuntimeError("Failure estimator did not return predict_proba output")
                latency_ms = (perf_counter() - started) * 1000
                timestamp = datetime.now(timezone.utc)
                response = FailurePredictionResponse(
                    prediction_id=prediction_id,
                    predicted_class=result.predicted_class,
                    failure_probability=result.failure_probability,
                    model_version=model_version,
                    prediction_timestamp=timestamp,
                    inference_latency_ms=latency_ms,
                )
        except ModelUnavailableError:
            latency_ms = (perf_counter() - started) * 1000
            logger.warning(
                "Prediction outcome=unavailable prediction_id=%s model=%s model_version=%s "
                "timestamp=%s latency_ms=%.3f",
                prediction_id,
                model_name,
                model_version,
                timestamp.isoformat(),
                latency_ms,
            )
            raise
        except Exception as exc:
            latency_ms = (perf_counter() - started) * 1000
            logger.exception(
                "Prediction outcome=error prediction_id=%s model=%s model_version=%s "
                "timestamp=%s latency_ms=%.3f error_type=%s",
                prediction_id,
                model_name,
                model_version,
                timestamp.isoformat(),
                latency_ms,
                type(exc).__name__,
            )
            raise PredictionExecutionError("Model inference failed") from exc

        logger.info(
            "Prediction outcome=success prediction_id=%s model=%s model_version=%s "
            "timestamp=%s latency_ms=%.3f",
            response.prediction_id,
            model_name,
            response.model_version,
            response.prediction_timestamp.isoformat(),
            response.inference_latency_ms,
        )
        return response
