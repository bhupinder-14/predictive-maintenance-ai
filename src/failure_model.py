"""Supervised failure classification pipeline.

Uses the ``Machine failure`` binary label from the AI4I 2020 dataset.

This is **row-level failure classification**, not future-failure forecasting.
The dataset does not contain temporal sequences per machine that would
support predicting failure within a future time window.

Pipeline:
  1. Logistic Regression baseline
  2. Random Forest comparison
  3. Evaluation on held-out data (precision, recall, F1, PR-AUC, ROC-AUC,
     confusion matrix)
  4. Threshold selection on the validation set
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    auc,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.config import RANDOM_SEED
from src.model_utils import ModelArtifact, ModelMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_logistic_regression(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    random_seed: int = RANDOM_SEED,
) -> LogisticRegression:
    """Train a Logistic Regression baseline with class-weight balancing."""
    logger.info("Training Logistic Regression (seed=%d)", random_seed)
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=random_seed,
        solver="lbfgs",
    )
    model.fit(X_train, y_train)
    logger.info("Logistic Regression fitted on %d samples", X_train.shape[0])
    return model


def train_random_forest(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    n_estimators: int = 200,
    random_seed: int = RANDOM_SEED,
) -> RandomForestClassifier:
    """Train a Random Forest classifier with class-weight balancing."""
    logger.info(
        "Training Random Forest (n_estimators=%d, seed=%d)",
        n_estimators, random_seed,
    )
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        class_weight="balanced",
        random_state=random_seed,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    logger.info("Random Forest fitted on %d samples", X_train.shape[0])
    return model


# ---------------------------------------------------------------------------
# Threshold tuning
# ---------------------------------------------------------------------------

def find_best_threshold(
    model: Any,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    metric: str = "f1",
) -> float:
    """Find the probability threshold that maximises *metric* on the validation set.

    Only ``"f1"`` is currently supported.
    """
    if not hasattr(model, "predict_proba"):
        logger.warning("Model does not support predict_proba; using default 0.5")
        return 0.5

    probas = model.predict_proba(X_val)[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_val, probas)

    # F1 for each threshold
    f1_scores = np.where(
        (precisions[:-1] + recalls[:-1]) > 0,
        2 * precisions[:-1] * recalls[:-1] / (precisions[:-1] + recalls[:-1]),
        0.0,
    )
    best_idx = int(np.argmax(f1_scores))
    best_thresh = float(thresholds[best_idx])
    logger.info(
        "Best threshold=%.4f  (F1=%.4f on validation set)",
        best_thresh, f1_scores[best_idx],
    )
    return best_thresh


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_classifier(
    model: Any,
    X: np.ndarray,
    y_true: np.ndarray,
    *,
    threshold: float = 0.5,
    label: str = "test",
) -> dict[str, Any]:
    """Comprehensive evaluation of a binary classifier.

    Returns a dict containing precision, recall, F1, PR-AUC, ROC-AUC,
    confusion matrix, and the classification report.
    """
    has_proba = hasattr(model, "predict_proba")

    if has_proba:
        probas = model.predict_proba(X)[:, 1]
        y_pred = (probas >= threshold).astype(int)
    else:
        y_pred = model.predict(X)
        probas = None

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    metrics: dict[str, Any] = {
        "split": label,
        "n_samples": int(len(y_true)),
        "n_positive": int(y_true.sum()),
        "n_negative": int((y_true == 0).sum()),
        "threshold": threshold,
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "f1_score": round(float(f1), 4),
        "confusion_matrix": {
            "tn": int(tn), "fp": int(fp),
            "fn": int(fn), "tp": int(tp),
        },
        "classification_report": classification_report(
            y_true, y_pred, output_dict=True, zero_division=0,
        ),
    }

    if probas is not None:
        try:
            roc = roc_auc_score(y_true, probas)
            metrics["roc_auc"] = round(float(roc), 4)
        except ValueError:
            metrics["roc_auc"] = None

        precs, recs, _ = precision_recall_curve(y_true, probas)
        pr_auc = auc(recs, precs)
        metrics["pr_auc"] = round(float(pr_auc), 4)
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None

    logger.info(
        "[%s] precision=%.4f  recall=%.4f  F1=%.4f  ROC-AUC=%s  PR-AUC=%s",
        label, prec, rec, f1,
        metrics.get("roc_auc", "N/A"),
        metrics.get("pr_auc", "N/A"),
    )
    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@dataclass
class FailurePrediction:
    """Result of a single failure-classification inference."""

    predicted_class: int          # 0 = no failure, 1 = failure
    failure_probability: float | None   # None if model lacks predict_proba
    model_version: str


def predict_failure(
    artifact: ModelArtifact,
    features: pd.DataFrame | np.ndarray,
    *,
    threshold: float | None = None,
) -> list[FailurePrediction]:
    """Run failure-classification inference.

    Parameters
    ----------
    artifact : ModelArtifact
        Loaded failure model artifact.
    features : DataFrame or ndarray
        Raw feature values (pre-preprocessing).
    threshold : float, optional
        Override the threshold stored in the artifact metadata.

    Returns
    -------
    list[FailurePrediction]
    """
    if isinstance(features, pd.DataFrame):
        X = artifact.preprocessor.transform(features)
    else:
        X = np.asarray(features)
        if X.ndim == 1:
            X = X.reshape(1, -1)

    model = artifact.estimator
    thresh = threshold if threshold is not None else artifact.metadata.threshold
    if thresh is None:
        thresh = 0.5

    has_proba = hasattr(model, "predict_proba")
    results: list[FailurePrediction] = []

    if has_proba:
        probas = model.predict_proba(X)[:, 1]
        preds = (probas >= thresh).astype(int)
    else:
        preds = model.predict(X)
        probas = [None] * len(preds)  # type: ignore[assignment]

    for i in range(len(preds)):
        results.append(FailurePrediction(
            predicted_class=int(preds[i]),
            failure_probability=float(probas[i]) if probas[i] is not None else None,
            model_version=artifact.metadata.model_version,
        ))
    return results
