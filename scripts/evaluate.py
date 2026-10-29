#!/usr/bin/env python
"""Load saved model artifacts and re-evaluate on the test set.

Usage:
    python -m scripts.evaluate

This script verifies that saved artifacts can be loaded and produce
consistent evaluation results without retraining.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.anomaly_model import evaluate_anomaly_model
from src.config import MODEL_DIR, RANDOM_SEED
from src.data_ingestion import (
    clean_dataset,
    get_feature_target_split,
    load_raw_dataset,
)
from src.failure_model import evaluate_classifier
from src.model_utils import ModelArtifact
from src.preprocessing import split_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=" * 60)
    logger.info("MODEL EVALUATION (from saved artifacts)")
    logger.info("=" * 60)

    # 1. Reproduce the same data splits
    df = load_raw_dataset()
    df = clean_dataset(df)
    X, y = get_feature_target_split(df, include_failure_types=False)
    splits = split_data(X, y)

    # ── Anomaly model ────────────────────────────────────────────
    try:
        anomaly_artifact = ModelArtifact.load("anomaly_v1")
        logger.info("Loaded anomaly artifact (version=%s)", anomaly_artifact.metadata.model_version)
    except FileNotFoundError as e:
        logger.error("Anomaly artifact not found: %s", e)
        anomaly_artifact = None

    if anomaly_artifact is not None:
        X_test_a = anomaly_artifact.preprocessor.transform(splits["X_test"])
        y_test = splits["y_test"].values
        anomaly_metrics = evaluate_anomaly_model(
            anomaly_artifact.estimator, X_test_a, y_test,
        )
        anomaly_metrics["split"] = "test"
        print("\n--- Anomaly Model (test set) ---")
        print(f"  Anomalies detected: {anomaly_metrics['n_anomalies_detected']}/{anomaly_metrics['n_samples']}")
        print(f"  Anomaly rate: {anomaly_metrics['anomaly_rate']:.4f}")
        if "failure_overlap" in anomaly_metrics:
            fo = anomaly_metrics["failure_overlap"]
            print(f"  Failure overlap: precision={fo['precision']:.4f}  recall={fo['recall']:.4f}")

    # ── Failure model ────────────────────────────────────────────
    try:
        failure_artifact = ModelArtifact.load("failure_v1")
        logger.info("Loaded failure artifact (version=%s)", failure_artifact.metadata.model_version)
    except FileNotFoundError as e:
        logger.error("Failure artifact not found: %s", e)
        failure_artifact = None

    if failure_artifact is not None:
        X_test_f = failure_artifact.preprocessor.transform(splits["X_test"])
        y_test = splits["y_test"].values
        threshold = failure_artifact.metadata.threshold or 0.5
        failure_metrics = evaluate_classifier(
            failure_artifact.estimator, X_test_f, y_test,
            threshold=threshold, label="test",
        )
        print("\n--- Failure Model (test set) ---")
        print(f"  Model type: {failure_artifact.metadata.model_type}")
        print(f"  Threshold:  {threshold:.4f}")
        print(f"  Precision:  {failure_metrics['precision']:.4f}")
        print(f"  Recall:     {failure_metrics['recall']:.4f}")
        print(f"  F1:         {failure_metrics['f1_score']:.4f}")
        print(f"  ROC-AUC:    {failure_metrics.get('roc_auc', 'N/A')}")
        print(f"  PR-AUC:     {failure_metrics.get('pr_auc', 'N/A')}")
        cm = failure_metrics["confusion_matrix"]
        print(f"  Confusion:  TN={cm['tn']} FP={cm['fp']} FN={cm['fn']} TP={cm['tp']}")

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
