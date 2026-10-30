"""Settings for the prediction API."""

from __future__ import annotations

from pathlib import Path

from src.config import MODEL_DIR

ANOMALY_MODEL_VERSION = "anomaly_v1"
FAILURE_MODEL_VERSION = "failure_v1"
EXPECTED_MODEL_VERSIONS = {
    "anomaly": ANOMALY_MODEL_VERSION,
    "failure": FAILURE_MODEL_VERSION,
}


def get_model_directory() -> Path:
    """Return the configured model artifact directory."""
    return MODEL_DIR
