"""Central configuration for the Predictive Maintenance application.

Loads settings from environment variables (or .env file) with sensible
defaults for local development.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / os.getenv("MODEL_DIR", "models")

RAW_DATASET_FILENAME = "ai4i2020.csv"
RAW_DATASET_PATH = DATA_RAW_DIR / RAW_DATASET_FILENAME

# ---------------------------------------------------------------------------
# Dataset schema – authoritative column names from the AI4I 2020 dataset
# ---------------------------------------------------------------------------
COLUMN_UDI = "UDI"
COLUMN_PRODUCT_ID = "Product ID"
COLUMN_TYPE = "Type"

NUMERIC_FEATURE_COLUMNS: list[str] = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

CATEGORICAL_FEATURE_COLUMNS: list[str] = [
    "Type",
]

TARGET_COLUMN = "Machine failure"

FAILURE_TYPE_COLUMNS: list[str] = [
    "TWF",   # Tool Wear Failure
    "HDF",   # Heat Dissipation Failure
    "PWF",   # Power Failure
    "OSF",   # Overstrain Failure
    "RNF",   # Random Failures
]

# Columns that leak the target (failure-type sub-labels imply the target)
LEAKAGE_COLUMNS: list[str] = FAILURE_TYPE_COLUMNS

# All expected columns in the raw CSV (order matters for validation)
ALL_EXPECTED_COLUMNS: list[str] = [
    COLUMN_UDI,
    COLUMN_PRODUCT_ID,
    COLUMN_TYPE,
    *NUMERIC_FEATURE_COLUMNS,
    TARGET_COLUMN,
    *FAILURE_TYPE_COLUMNS,
]

# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42
TEST_SIZE: float = 0.20
VALIDATION_SIZE: float = 0.10  # fraction of the *training* portion

# Isolation Forest
ISOLATION_FOREST_CONTAMINATION: float = 0.05
ISOLATION_FOREST_N_ESTIMATORS: int = 200

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'predictive_maintenance.db'}")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_ENV: str = os.getenv("APP_ENV", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Milestone 4 drift monitoring
# ---------------------------------------------------------------------------
_drift_reference_path = Path(
    os.getenv("DRIFT_REFERENCE_PATH", "data/reference/drift_reference_v1.json")
)
DRIFT_REFERENCE_PATH = (
    _drift_reference_path.resolve()
    if _drift_reference_path.is_absolute()
    else (PROJECT_ROOT / _drift_reference_path).resolve()
)
DRIFT_KS_ALPHA = float(os.getenv("DRIFT_KS_ALPHA", "0.05"))
DRIFT_CATEGORICAL_TVD_THRESHOLD = float(
    os.getenv("DRIFT_CATEGORICAL_TVD_THRESHOLD", "0.10")
)
DRIFT_MINIMUM_SAMPLE_SIZE = int(os.getenv("DRIFT_MINIMUM_SAMPLE_SIZE", "20"))
METRICS_WINDOW_SECONDS = int(os.getenv("METRICS_WINDOW_SECONDS", "300"))
if METRICS_WINDOW_SECONDS < 1:
    raise ValueError("METRICS_WINDOW_SECONDS must be at least 1")
