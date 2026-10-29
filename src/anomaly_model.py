"""Isolation Forest anomaly detection pipeline.

This module trains an Isolation Forest on the numeric sensor features from
the AI4I 2020 dataset and provides inference functions that return an anomaly
score and a normal/anomaly classification.

Limitations (documented per SPEC §4):
  - The Isolation Forest score is **not** a calibrated failure probability.
  - The dataset is tabular, not a true time series per machine, so rolling-
    window or temporal anomaly detection is not implemented.
  - The decision threshold is based on the contamination parameter and can
    be overridden at inference time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.config import (
    ISOLATION_FOREST_CONTAMINATION,
    ISOLATION_FOREST_N_ESTIMATORS,
    NUMERIC_FEATURE_COLUMNS,
    RANDOM_SEED,
)
from src.model_utils import ModelArtifact, ModelMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Statistical baseline
# ---------------------------------------------------------------------------

@dataclass
class StatisticalBaseline:
    """Simple z-score baseline for comparison with Isolation Forest.

    A point is flagged anomalous if *any* feature's absolute z-score exceeds
    ``threshold`` (default 3.0).
    """

    means: np.ndarray | None = None
    stds: np.ndarray | None = None
    threshold: float = 3.0

    def fit(self, X: np.ndarray) -> "StatisticalBaseline":
        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0)
        # Avoid division by zero
        self.stds[self.stds == 0] = 1.0
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return 1 for normal, -1 for anomaly (same convention as sklearn)."""
        z = np.abs((X - self.means) / self.stds)
        is_anomaly = np.any(z > self.threshold, axis=1)
        return np.where(is_anomaly, -1, 1)

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Return negative max-z as a pseudo anomaly score (lower = more anomalous)."""
        z = np.abs((X - self.means) / self.stds)
        return -z.max(axis=1)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_anomaly_model(
    X_train: np.ndarray,
    *,
    contamination: float = ISOLATION_FOREST_CONTAMINATION,
    n_estimators: int = ISOLATION_FOREST_N_ESTIMATORS,
    random_seed: int = RANDOM_SEED,
) -> IsolationForest:
    """Train an Isolation Forest on *X_train* and return the fitted model."""
    logger.info(
        "Training Isolation Forest (n_estimators=%d, contamination=%.3f, seed=%d)",
        n_estimators, contamination, random_seed,
    )
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_seed,
        n_jobs=-1,
    )
    model.fit(X_train)
    logger.info("Isolation Forest fitted on %d samples", X_train.shape[0])
    return model


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_anomaly_model(
    model: IsolationForest,
    X: np.ndarray,
    y_true: np.ndarray | None = None,
    *,
    baseline: StatisticalBaseline | None = None,
) -> dict[str, Any]:
    """Evaluate the anomaly model and return a metrics dict.

    If *y_true* is provided (binary failure labels), the evaluation computes
    overlap statistics between detected anomalies and actual failures.
    **Important**: a statistical anomaly is not the same as a confirmed
    equipment failure — this comparison is informational only.
    """
    predictions = model.predict(X)          # 1 = normal, -1 = anomaly
    scores = model.score_samples(X)         # higher = more normal

    n_anomalies = int((predictions == -1).sum())
    metrics: dict[str, Any] = {
        "n_samples": int(X.shape[0]),
        "n_anomalies_detected": n_anomalies,
        "anomaly_rate": round(n_anomalies / len(predictions), 4),
        "score_min": float(scores.min()),
        "score_max": float(scores.max()),
        "score_mean": float(scores.mean()),
        "score_std": float(scores.std()),
        # IsolationForest.predict labels score_samples values below its
        # learned offset as anomalous. Persisting this cutoff makes the
        # decision rule explicit and keeps scoring semantics auditable.
        "score_samples_threshold": float(model.offset_),
    }

    # Comparison with ground-truth failure labels (informational)
    if y_true is not None:
        is_anomaly = predictions == -1
        is_failure = y_true == 1
        tp = int((is_anomaly & is_failure).sum())
        fp = int((is_anomaly & ~is_failure).sum())
        fn = int((~is_anomaly & is_failure).sum())
        tn = int((~is_anomaly & ~is_failure).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        metrics["failure_overlap"] = {
            "note": (
                "Comparison of detected anomalies vs failure labels. "
                "A detected anomaly is not necessarily a failure."
            ),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }

    # Statistical baseline comparison
    if baseline is not None:
        bl_preds = baseline.predict(X)
        bl_anomalies = int((bl_preds == -1).sum())
        agreement = int((predictions == bl_preds).sum())
        metrics["baseline_comparison"] = {
            "baseline_anomalies_detected": bl_anomalies,
            "baseline_anomaly_rate": round(bl_anomalies / len(bl_preds), 4),
            "agreement_with_iforest": round(agreement / len(predictions), 4),
        }

    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@dataclass
class AnomalyResult:
    """Result of a single anomaly-detection inference."""

    anomaly_score: float
    is_anomaly: bool
    explanation: dict[str, Any]


def predict_anomaly(
    artifact: ModelArtifact,
    features: pd.DataFrame | np.ndarray,
) -> list[AnomalyResult]:
    """Run anomaly inference on one or more observations.

    Parameters
    ----------
    artifact : ModelArtifact
        Loaded anomaly model artifact (preprocessor + Isolation Forest).
    features : DataFrame or ndarray
        Raw feature values (pre-preprocessing).  If a DataFrame it is
        transformed by the artifact's preprocessor; if already an ndarray
        it is used directly.

    Returns
    -------
    list[AnomalyResult]
    """
    if isinstance(features, pd.DataFrame):
        X = artifact.preprocessor.transform(features)
    else:
        X = np.asarray(features)
        if X.ndim == 1:
            X = X.reshape(1, -1)

    model: IsolationForest = artifact.estimator
    scores = model.score_samples(X)
    # ``score_samples`` is higher for more normal observations. The learned
    # offset is the documented contamination-based cutoff used by predict().
    threshold = artifact.metadata.threshold
    if threshold is None:
        threshold = float(model.offset_)
    predictions = np.where(scores < threshold, -1, 1)

    results: list[AnomalyResult] = []
    feature_names = artifact.metadata.feature_names

    for i in range(X.shape[0]):
        # Build explanation: which features contributed most to the anomaly
        # Using absolute deviation from training mean as a simple transparent method
        explanation = _build_explanation(X[i], feature_names, scores[i])
        results.append(AnomalyResult(
            anomaly_score=float(scores[i]),
            is_anomaly=bool(predictions[i] == -1),
            explanation=explanation,
        ))
    return results


def _build_explanation(
    x: np.ndarray,
    feature_names: list[str],
    score: float,
) -> dict[str, Any]:
    """Build a human-readable explanation of which features look suspicious.

    Uses absolute feature values as a simple proxy.  For a more rigorous
    approach, SHAP could be used (listed as optional in SPEC §2).
    """
    # Rank features by absolute value (in standardised space, larger
    # absolute values are further from the training centre)
    abs_vals = np.abs(x)
    ranked_indices = np.argsort(abs_vals)[::-1]
    top_k = min(3, len(feature_names))

    suspicious = []
    for idx in ranked_indices[:top_k]:
        suspicious.append({
            "feature": feature_names[idx],
            "standardised_value": round(float(x[idx]), 4),
            "abs_deviation": round(float(abs_vals[idx]), 4),
        })

    return {
        "method": "absolute_deviation_in_standardised_space",
        "anomaly_score": round(score, 6),
        "top_suspicious_features": suspicious,
    }
