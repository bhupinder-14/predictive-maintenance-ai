"""Reference-statistics validation and per-feature input drift tests."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import ks_2samp

from src.config import (
    CATEGORICAL_FEATURE_COLUMNS,
    DRIFT_CATEGORICAL_TVD_THRESHOLD,
    DRIFT_KS_ALPHA,
    DRIFT_MINIMUM_SAMPLE_SIZE,
    NUMERIC_FEATURE_COLUMNS,
)

logger = logging.getLogger(__name__)
REFERENCE_FEATURES = [*NUMERIC_FEATURE_COLUMNS, *CATEGORICAL_FEATURE_COLUMNS]
REFERENCE_VERSION = "drift_reference_v1"
CATEGORY_VALUES = ("H", "L", "M")


class DriftReferenceError(ValueError):
    """Raised when a reference artifact is missing or incompatible."""


@dataclass(frozen=True)
class DriftReference:
    version: str
    training_sample_size: int
    numeric_statistics: dict[str, dict[str, Any]]
    numeric_reference_values: dict[str, np.ndarray]
    type_counts: dict[str, int]
    type_proportions: dict[str, float]
    generated_at: str

    @classmethod
    def load(cls, path: Path) -> "DriftReference":
        """Load and validate the versioned reference JSON safely."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise DriftReferenceError("Drift reference is unavailable") from exc

        try:
            if payload["schema_version"] != 1:
                raise ValueError("unsupported schema")
            if payload["reference_version"] != REFERENCE_VERSION:
                raise ValueError("unsupported reference version")
            if payload["feature_names"] != REFERENCE_FEATURES:
                raise ValueError("feature schema mismatch")
            sample_size = int(payload["training_sample_size"])
            if sample_size < 2:
                raise ValueError("reference sample is too small")

            numeric_stats = payload["numeric_statistics"]
            numeric_values: dict[str, np.ndarray] = {}
            for name in NUMERIC_FEATURE_COLUMNS:
                stats = numeric_stats[name]
                values = np.asarray(stats["reference_values"], dtype=float)
                if len(values) != sample_size or not np.isfinite(values).all():
                    raise ValueError("invalid numeric reference values")
                numeric_values[name] = values

            categorical = payload["categorical_statistics"]["Type"]
            type_counts = {category: int(categorical["counts"].get(category, 0))
                           for category in CATEGORY_VALUES}
            if any(count < 0 for count in type_counts.values()) or sum(type_counts.values()) != sample_size:
                raise ValueError("invalid categorical reference counts")
            generated_at = str(payload["generated_at"])
            # Reject missing timestamp metadata while avoiding a dependency on a date parser.
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            type_proportions = {
                category: float(categorical["proportions"].get(category, 0.0))
                for category in CATEGORY_VALUES
            }
            if not np.isclose(sum(type_proportions.values()), 1.0):
                raise ValueError("invalid categorical proportions")
            return cls(
                version=REFERENCE_VERSION,
                training_sample_size=sample_size,
                numeric_statistics=numeric_stats,
                numeric_reference_values=numeric_values,
                type_counts=type_counts,
                type_proportions=type_proportions,
                generated_at=generated_at,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise DriftReferenceError("Drift reference is incompatible") from exc


class DriftDetector:
    """Use KS tests for numeric marginals and TV distance for Type proportions."""

    def __init__(
        self,
        reference: DriftReference,
        *,
        ks_alpha: float = 0.05,
        categorical_tvd_threshold: float = 0.10,
        minimum_sample_size: int = 20,
    ) -> None:
        if not 0 < ks_alpha < 1:
            raise ValueError("KS significance level must be between 0 and 1")
        if not 0 <= categorical_tvd_threshold <= 1:
            raise ValueError("Categorical threshold must be between 0 and 1")
        if minimum_sample_size < 2:
            raise ValueError("Minimum sample size must be at least 2")
        self.reference = reference
        self.ks_alpha = ks_alpha
        self.categorical_tvd_threshold = categorical_tvd_threshold
        self.minimum_sample_size = minimum_sample_size

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        ks_alpha: float = DRIFT_KS_ALPHA,
        categorical_tvd_threshold: float = DRIFT_CATEGORICAL_TVD_THRESHOLD,
        minimum_sample_size: int = DRIFT_MINIMUM_SAMPLE_SIZE,
    ) -> "DriftDetector":
        """Load a compatible reference and use documented default thresholds."""
        return cls(
            DriftReference.load(path),
            ks_alpha=ks_alpha,
            categorical_tvd_threshold=categorical_tvd_threshold,
            minimum_sample_size=minimum_sample_size,
        )

    def evaluate(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare a validated batch against reference feature distributions."""
        if not observations:
            raise ValueError("At least one observation is required")
        current_size = len(observations)
        current: dict[str, np.ndarray] = {}
        for name in NUMERIC_FEATURE_COLUMNS:
            values = np.asarray([row[name] for row in observations], dtype=float)
            if not np.isfinite(values).all():
                raise ValueError("Drift observations must be finite")
            current[name] = values
        type_counts = Counter(str(row["Type"]) for row in observations)

        enough_samples = current_size >= self.minimum_sample_size
        features: list[dict[str, Any]] = []
        for name in NUMERIC_FEATURE_COLUMNS:
            if enough_samples:
                result = ks_2samp(
                    self.reference.numeric_reference_values[name],
                    current[name],
                    alternative="two-sided",
                    method="auto",
                )
                statistic = float(result.statistic)
                p_value = float(result.pvalue)
                detected: bool | None = p_value < self.ks_alpha
            else:
                statistic = None
                p_value = None
                detected = None
            features.append({
                "feature_name": name,
                "method": "kolmogorov_smirnov_two_sample",
                "statistic": statistic,
                "p_value": p_value,
                "threshold": self.ks_alpha,
                "threshold_kind": "p_value_significance_level",
                "drift_detected": detected,
                "reference_sample_size": self.reference.training_sample_size,
                "current_sample_size": current_size,
            })

        if enough_samples:
            current_proportions = {
                category: type_counts.get(category, 0) / current_size
                for category in CATEGORY_VALUES
            }
            tvd = 0.5 * sum(
                abs(self.reference.type_proportions[category] - current_proportions[category])
                for category in CATEGORY_VALUES
            )
            type_detected: bool | None = tvd >= self.categorical_tvd_threshold
        else:
            tvd = None
            type_detected = None
        features.append({
            "feature_name": "Type",
            "method": "total_variation_distance",
            "statistic": tvd,
            "p_value": None,
            "threshold": self.categorical_tvd_threshold,
            "threshold_kind": "distance_threshold",
            "drift_detected": type_detected,
            "reference_sample_size": self.reference.training_sample_size,
            "current_sample_size": current_size,
        })

        if not enough_samples:
            overall_status = "insufficient_data"
        elif any(feature["drift_detected"] for feature in features):
            overall_status = "drift_detected"
        else:
            overall_status = "no_drift_detected"

        return {
            "reference_version": self.reference.version,
            "generated_at": datetime.now(timezone.utc),
            "reference_sample_size": self.reference.training_sample_size,
            "current_sample_size": current_size,
            "minimum_sample_size": self.minimum_sample_size,
            "overall_status": overall_status,
            "features": features,
            "interpretation": (
                "Drift indicates an input distribution change; it does not by itself "
                "establish reduced model accuracy."
            ),
        }
