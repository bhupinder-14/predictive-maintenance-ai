"""Startup loading and compatibility checks for persisted model artifacts."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from pathlib import Path

from src.config import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from src.model_utils import ModelArtifact

from .config import EXPECTED_MODEL_VERSIONS

logger = logging.getLogger(__name__)

RAW_FEATURE_NAMES = [*CATEGORICAL_FEATURE_COLUMNS, *NUMERIC_FEATURE_COLUMNS]
ArtifactLoader = Callable[[str, Path], ModelArtifact]


class ModelUnavailableError(RuntimeError):
    """Raised when an endpoint's required artifact is unavailable."""


class ModelCompatibilityError(ValueError):
    """Raised when a loaded artifact does not match the API feature contract."""


def _load_artifact(version: str, directory: Path) -> ModelArtifact:
    return ModelArtifact.load(version, directory=directory)


class ModelRegistry:
    """Load, validate, and expose the two saved Milestone 1 model bundles."""

    def __init__(
        self,
        model_directory: Path,
        artifact_loader: ArtifactLoader = _load_artifact,
    ) -> None:
        self.model_directory = Path(model_directory)
        self.artifact_loader = artifact_loader
        self.artifacts: dict[str, ModelArtifact] = {}
        self.load_errors: dict[str, str] = {}

    def load_all(self) -> None:
        """Try to load both models, retaining per-model failures for readiness."""
        self.artifacts.clear()
        self.load_errors.clear()
        for name, version in EXPECTED_MODEL_VERSIONS.items():
            try:
                artifact = self.artifact_loader(version, self.model_directory)
                self._validate(name, version, artifact)
            except Exception as exc:
                self.load_errors[name] = type(exc).__name__
                logger.exception(
                    "Model load failed model=%s version=%s error_type=%s",
                    name,
                    version,
                    type(exc).__name__,
                )
                continue
            self.artifacts[name] = artifact
            logger.info(
                "Model loaded model=%s version=%s directory=%s",
                name,
                artifact.metadata.model_version,
                self.model_directory,
            )

    @property
    def readiness(self) -> dict[str, bool]:
        return {name: name in self.artifacts for name in EXPECTED_MODEL_VERSIONS}

    @property
    def operational_status(self) -> dict[str, dict[str, str | bool | None]]:
        """Return sanitized availability and actual loaded versions by model family."""
        status: dict[str, dict[str, str | bool | None]] = {}
        for name in EXPECTED_MODEL_VERSIONS:
            artifact = self.artifacts.get(name)
            if artifact is not None:
                status[name] = {
                    "available": True,
                    "status": "available",
                    "model_version": artifact.metadata.model_version,
                }
                continue
            error_type = self.load_errors.get(name, "NotLoaded")
            if error_type == "FileNotFoundError":
                label = "missing_artifacts"
            elif error_type in {
                "ModelCompatibilityError", "ValueError", "TypeError", "KeyError",
                "JSONDecodeError",
            }:
                label = "incompatible_artifacts"
            else:
                label = "load_failed"
            status[name] = {
                "available": False,
                "status": label,
                "model_version": None,
            }
        return status

    @property
    def is_ready(self) -> bool:
        return all(self.readiness.values())

    def require(self, name: str) -> ModelArtifact:
        """Return a loaded model or raise a safe, endpoint-level unavailable error."""
        artifact = self.artifacts.get(name)
        if artifact is None:
            raise ModelUnavailableError(f"Model '{name}' is unavailable")
        return artifact

    @staticmethod
    def _validate(name: str, expected_version: str, artifact: ModelArtifact) -> None:
        metadata = artifact.metadata
        preprocessor = artifact.preprocessor
        estimator = artifact.estimator

        if metadata.model_version != expected_version:
            raise ModelCompatibilityError("Artifact version does not match API configuration")
        if not hasattr(preprocessor, "feature_names_in_"):
            raise ModelCompatibilityError("Preprocessor has no fitted input feature schema")
        raw_names = list(preprocessor.feature_names_in_)
        if raw_names != RAW_FEATURE_NAMES:
            raise ModelCompatibilityError("Preprocessor raw feature schema is incompatible")
        transformed_names = list(preprocessor.get_feature_names_out())
        if metadata.feature_names != transformed_names:
            raise ModelCompatibilityError("Metadata feature names do not match preprocessor output")
        estimator_feature_count = getattr(estimator, "n_features_in_", None)
        if estimator_feature_count != len(transformed_names):
            raise ModelCompatibilityError("Estimator feature count does not match preprocessor output")

        if name == "anomaly":
            if not callable(getattr(estimator, "score_samples", None)):
                raise ModelCompatibilityError("Anomaly estimator does not expose score_samples")
            threshold = metadata.threshold
            offset = getattr(estimator, "offset_", None)
            if threshold is None or offset is None or not math.isclose(
                float(threshold), float(offset), rel_tol=0, abs_tol=1e-12
            ):
                raise ModelCompatibilityError("Anomaly threshold does not match estimator offset")
        elif name == "failure":
            if not callable(getattr(estimator, "predict_proba", None)):
                raise ModelCompatibilityError("Failure estimator does not expose predict_proba")
            classes = list(getattr(estimator, "classes_", []))
            if classes != [0, 1]:
                raise ModelCompatibilityError("Failure estimator classes must be [0, 1]")
            if metadata.threshold is None or not 0 <= float(metadata.threshold) <= 1:
                raise ModelCompatibilityError("Failure decision threshold must be in [0, 1]")
        else:
            raise ModelCompatibilityError(f"Unknown model role: {name}")
