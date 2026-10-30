"""FastAPI application factory and ASGI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.config import LOG_LEVEL

from .config import get_model_directory
from .model_registry import ArtifactLoader, ModelRegistry
from .prediction_service import PredictionService
from .routes import router
from src.database.manager import Database
from src.database.prediction_workflow import PredictionWorkflow

logger = logging.getLogger(__name__)


def _configure_api_logging() -> None:
    """Ensure API prediction events are visible under the default Uvicorn run."""
    api_logger = logging.getLogger("src.api")
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    api_logger.setLevel(level)
    if not api_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        api_logger.addHandler(handler)
    api_logger.propagate = False


def create_app(
    model_directory: Path | None = None,
    *,
    artifact_loader: ArtifactLoader | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """Create the API with configurable artifact location for deployment/tests."""
    _configure_api_logging()
    registry_kwargs: dict[str, Any] = {}
    if artifact_loader is not None:
        registry_kwargs["artifact_loader"] = artifact_loader
    registry = ModelRegistry(model_directory or get_model_directory(), **registry_kwargs)
    database = Database(database_url)
    prediction_service = PredictionService(registry)
    prediction_workflow = PredictionWorkflow(database, prediction_service)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Load once when the process starts. Keep the server alive if an
        # artifact is missing so health/readiness can explain the state safely.
        registry.load_all()
        try:
            database.initialize()
        except Exception as exc:
            logger.error(
                "Database initialization failed error_type=%s",
                type(exc).__name__,
            )
        application.state.model_registry = registry
        application.state.database = database
        application.state.database_ready = database.initialized
        application.state.prediction_service = prediction_service
        application.state.prediction_workflow = prediction_workflow
        if registry.is_ready and database.initialized:
            logger.info("Prediction API ready with both model artifacts and database")
        else:
            logger.error(
                "Prediction API started with incomplete readiness models=%s database=%s",
                registry.readiness,
                database.initialized,
            )
        try:
            yield
        finally:
            database.dispose()

    application = FastAPI(
        title="Predictive Maintenance Prediction API",
        description=(
            "Inference service for the saved AI4I 2020 models. Failure output is "
            "row-level classification; anomaly scores are not failure probabilities."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Do not echo request values. Besides reducing data exposure, this
        # avoids JSON serialization failures for NaN/Infinity validation input.
        safe_errors = [
            {
                "loc": error.get("loc", ()),
                "msg": error.get("msg", "Invalid request value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": safe_errors},
        )

    application.state.model_registry = registry
    application.state.database = database
    application.state.database_ready = False
    application.state.prediction_service = prediction_service
    application.state.prediction_workflow = prediction_workflow
    application.include_router(router)
    return application


app = create_app()
