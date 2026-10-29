"""Data ingestion and validation for the AI4I 2020 dataset.

Responsibilities:
  - Load the CSV from a documented path.
  - Validate expected columns and data types.
  - Identify missing values, duplicates, and out-of-range values.
  - Report data-quality issues clearly.
  - Apply documented cleaning rules.
  - Separate raw data from processed data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    ALL_EXPECTED_COLUMNS,
    CATEGORICAL_FEATURE_COLUMNS,
    COLUMN_PRODUCT_ID,
    COLUMN_TYPE,
    COLUMN_UDI,
    FAILURE_TYPE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    RAW_DATASET_PATH,
    TARGET_COLUMN,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reasonable value ranges (based on dataset documentation & inspection)
# ---------------------------------------------------------------------------
EXPECTED_RANGES: dict[str, tuple[float, float]] = {
    "Air temperature [K]":      (290.0, 310.0),
    "Process temperature [K]":  (300.0, 320.0),
    "Rotational speed [rpm]":   (1_000.0, 3_000.0),
    "Torque [Nm]":              (0.0, 100.0),
    "Tool wear [min]":          (0.0, 300.0),
}

EXPECTED_TYPES: set[str] = {"L", "M", "H"}


@dataclass
class DataQualityReport:
    """Container for data-quality findings."""

    n_rows: int = 0
    n_columns: int = 0
    missing_counts: dict[str, int] = field(default_factory=dict)
    duplicate_rows: int = 0
    duplicate_udis: int = 0
    unexpected_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    out_of_range: dict[str, int] = field(default_factory=dict)
    invalid_types: int = 0
    non_numeric_errors: dict[str, int] = field(default_factory=dict)

    @property
    def has_issues(self) -> bool:
        return bool(
            any(v > 0 for v in self.missing_counts.values())
            or self.duplicate_rows
            or self.duplicate_udis
            or self.unexpected_columns
            or self.missing_columns
            or any(v > 0 for v in self.out_of_range.values())
            or self.invalid_types
            or any(v > 0 for v in self.non_numeric_errors.values())
        )

    def summary(self) -> str:
        lines = [
            f"Data Quality Report ({self.n_rows} rows, {self.n_columns} columns)",
            "=" * 60,
        ]
        if self.missing_columns:
            lines.append(f"  MISSING COLUMNS: {self.missing_columns}")
        if self.unexpected_columns:
            lines.append(f"  UNEXPECTED COLUMNS: {self.unexpected_columns}")
        if any(v > 0 for v in self.missing_counts.values()):
            lines.append("  MISSING VALUES:")
            for col, cnt in self.missing_counts.items():
                if cnt > 0:
                    lines.append(f"    {col}: {cnt}")
        else:
            lines.append("  Missing values: None")
        lines.append(f"  Duplicate rows: {self.duplicate_rows}")
        lines.append(f"  Duplicate UDIs: {self.duplicate_udis}")
        if any(v > 0 for v in self.out_of_range.values()):
            lines.append("  OUT-OF-RANGE values:")
            for col, cnt in self.out_of_range.items():
                if cnt > 0:
                    lines.append(f"    {col}: {cnt}")
        if self.invalid_types > 0:
            lines.append(f"  Invalid Type values: {self.invalid_types}")
        if any(v > 0 for v in self.non_numeric_errors.values()):
            lines.append("  NON-NUMERIC errors:")
            for col, cnt in self.non_numeric_errors.items():
                if cnt > 0:
                    lines.append(f"    {col}: {cnt}")
        if not self.has_issues:
            lines.append("  ✅ No data-quality issues found.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_raw_dataset(path: Path | str | None = None) -> pd.DataFrame:
    """Load the AI4I 2020 CSV from *path* (defaults to ``RAW_DATASET_PATH``).

    Uses ``encoding='utf-8-sig'`` to handle the UTF-8 BOM present in the
    original file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at the expected location.
    """
    path = Path(path) if path else RAW_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. "
            "Download the AI4I 2020 Predictive Maintenance Dataset from "
            "https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset "
            "and place the CSV in data/raw/."
        )
    logger.info("Loading dataset from %s", path)
    df = pd.read_csv(path, encoding="utf-8-sig")
    logger.info("Loaded %d rows, %d columns", *df.shape)
    return df


def validate_dataset(df: pd.DataFrame) -> DataQualityReport:
    """Run comprehensive validation checks and return a quality report.

    This function does **not** modify *df*.
    """
    report = DataQualityReport(n_rows=len(df), n_columns=len(df.columns))

    # Column presence
    actual_cols = set(df.columns)
    expected_cols = set(ALL_EXPECTED_COLUMNS)
    report.missing_columns = sorted(expected_cols - actual_cols)
    report.unexpected_columns = sorted(actual_cols - expected_cols)

    # Missing values
    for col in df.columns:
        n_missing = int(df[col].isnull().sum())
        if n_missing > 0:
            report.missing_counts[col] = n_missing

    # Duplicate rows
    report.duplicate_rows = int(df.duplicated().sum())

    # Duplicate UDIs
    if COLUMN_UDI in df.columns:
        report.duplicate_udis = int(df[COLUMN_UDI].duplicated().sum())

    # Numeric type & range checks
    for col in NUMERIC_FEATURE_COLUMNS:
        if col not in df.columns:
            continue
        numeric_col = pd.to_numeric(df[col], errors="coerce")
        n_non_numeric = int(numeric_col.isnull().sum() - df[col].isnull().sum())
        if n_non_numeric > 0:
            report.non_numeric_errors[col] = n_non_numeric
        lo, hi = EXPECTED_RANGES.get(col, (-np.inf, np.inf))
        n_oor = int(((numeric_col < lo) | (numeric_col > hi)).sum())
        if n_oor > 0:
            report.out_of_range[col] = n_oor

    # Categorical type check
    if COLUMN_TYPE in df.columns:
        report.invalid_types = int(
            (~df[COLUMN_TYPE].isin(EXPECTED_TYPES)).sum()
        )

    return report


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Apply documented cleaning rules and return a copy.

    Cleaning rules:
      1. Drop exact duplicate rows (keep first).
      2. Coerce numeric feature columns to float; rows with non-coercible
         values are dropped.
      3. Drop rows where any numeric feature is outside the expected range.
      4. Drop rows with an invalid ``Type`` value.
      5. Ensure target and failure-type columns are integer 0/1.

    The function never silently changes the *meaning* of data.
    """
    logger.info("Cleaning dataset (%d rows)", len(df))
    df = df.copy()

    # 1. Drop exact duplicates
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.info("Dropped %d duplicate rows", n_dropped)

    # 2. Coerce numeric columns
    for col in NUMERIC_FEATURE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    n_before = len(df)
    df = df.dropna(subset=NUMERIC_FEATURE_COLUMNS)
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.info("Dropped %d rows with non-numeric feature values", n_dropped)

    # 3. Range filtering
    for col in NUMERIC_FEATURE_COLUMNS:
        if col not in EXPECTED_RANGES:
            continue
        lo, hi = EXPECTED_RANGES[col]
        mask = (df[col] >= lo) & (df[col] <= hi)
        n_oor = int((~mask).sum())
        if n_oor:
            logger.info("Dropping %d out-of-range rows for %s", n_oor, col)
        df = df.loc[mask]

    # 4. Valid Type
    if COLUMN_TYPE in df.columns:
        valid_mask = df[COLUMN_TYPE].isin(EXPECTED_TYPES)
        n_invalid = int((~valid_mask).sum())
        if n_invalid:
            logger.info("Dropping %d rows with invalid Type values", n_invalid)
        df = df.loc[valid_mask]

    # 5. Ensure target columns are int
    for col in [TARGET_COLUMN] + FAILURE_TYPE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(int)

    df = df.reset_index(drop=True)
    logger.info("Cleaning complete: %d rows remaining", len(df))
    return df


def get_feature_target_split(
    df: pd.DataFrame,
    *,
    include_failure_types: bool = False,
) -> tuple[pd.DataFrame, pd.Series]:
    """Split *df* into features ``X`` and target ``y``.

    Parameters
    ----------
    include_failure_types : bool
        If *False* (default), the failure-type sub-labels (TWF, HDF, …)
        are **excluded** from *X* to prevent target leakage.

    Returns
    -------
    X, y
    """
    drop_cols = [COLUMN_UDI, COLUMN_PRODUCT_ID, TARGET_COLUMN]
    if not include_failure_types:
        drop_cols += FAILURE_TYPE_COLUMNS

    X = df.drop(columns=[c for c in drop_cols if c in df.columns])
    y = df[TARGET_COLUMN]
    return X, y
