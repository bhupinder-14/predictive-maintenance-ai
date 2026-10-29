#!/usr/bin/env python
"""Train the Isolation Forest anomaly detection model.

Usage:
    python -m scripts.train_anomaly

Outputs:
    models/anomaly_v1_preprocessor.joblib
    models/anomaly_v1_estimator.joblib
    models/anomaly_v1_metadata.json
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.anomaly_model import (
    StatisticalBaseline,
    evaluate_anomaly_model,
    train_anomaly_model,
)
from src.config import (
    ISOLATION_FOREST_CONTAMINATION,
    ISOLATION_FOREST_N_ESTIMATORS,
    MODEL_DIR,
    RANDOM_SEED,
)
from src.data_ingestion import (
    clean_dataset,
    get_feature_target_split,
    load_raw_dataset,
    validate_dataset,
)
from src.model_utils import ModelArtifact, ModelMetadata
from src.preprocessing import build_preprocessor, get_feature_names, split_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # 1. Load and validate
    logger.info("=" * 60)
    logger.info("ANOMALY MODEL TRAINING PIPELINE")
    logger.info("=" * 60)

    df = load_raw_dataset()
    report = validate_dataset(df)
    print(report.summary())

    # 2. Clean
    df = clean_dataset(df)

    # 3. Feature / target split (exclude failure sub-types to avoid leakage)
    X, y = get_feature_target_split(df, include_failure_types=False)
    logger.info("Features shape: %s, Target shape: %s", X.shape, y.shape)

    # 4. Train / val / test split
    splits = split_data(X, y)

    # 5. Build and fit preprocessor on training data only
    preprocessor = build_preprocessor()
    X_train_t = preprocessor.fit_transform(splits["X_train"])
    X_val_t = preprocessor.transform(splits["X_val"])
    X_test_t = preprocessor.transform(splits["X_test"])
    y_train = splits["y_train"].values
    y_val = splits["y_val"].values
    y_test = splits["y_test"].values

    feature_names = get_feature_names(preprocessor)
    logger.info("Transformed feature names: %s", feature_names)

    # 6. Train statistical baseline
    baseline = StatisticalBaseline(threshold=3.0)
    baseline.fit(X_train_t)

    # 7. Train Isolation Forest
    model = train_anomaly_model(
        X_train_t,
        contamination=ISOLATION_FOREST_CONTAMINATION,
        n_estimators=ISOLATION_FOREST_N_ESTIMATORS,
        random_seed=RANDOM_SEED,
    )

    # 8. Evaluate on each split
    results = {}
    for name, Xs, ys in [
        ("train", X_train_t, y_train),
        ("validation", X_val_t, y_val),
        ("test", X_test_t, y_test),
    ]:
        metrics = evaluate_anomaly_model(model, Xs, ys, baseline=baseline)
        metrics["split"] = name
        results[name] = metrics
        logger.info("[%s] anomalies=%d/%d  rate=%.4f",
                    name, metrics["n_anomalies_detected"],
                    metrics["n_samples"], metrics["anomaly_rate"])

    # 9. Save artifact
    metadata = ModelMetadata(
        model_type="isolation_forest",
        model_version="anomaly_v1",
        feature_names=feature_names,
        random_seed=RANDOM_SEED,
        dataset_rows=len(df),
        training_rows=X_train_t.shape[0],
        model_params={
            "n_estimators": ISOLATION_FOREST_N_ESTIMATORS,
            "contamination": ISOLATION_FOREST_CONTAMINATION,
        },
        metrics=results,
    )

    artifact = ModelArtifact(
        preprocessor=preprocessor,
        estimator=model,
        metadata=metadata,
    )
    save_dir = artifact.save()

    # 10. Save evaluation report
    eval_path = MODEL_DIR / "anomaly_v1_evaluation.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Evaluation report saved to %s", eval_path)

    # 11. Summary
    print("\n" + "=" * 60)
    print("ANOMALY MODEL TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Model version:  anomaly_v1")
    print(f"  Artifacts dir:  {save_dir}")
    print(f"  Training rows:  {X_train_t.shape[0]}")
    print(f"  Test anomalies: {results['test']['n_anomalies_detected']}/{results['test']['n_samples']}")
    test_overlap = results["test"].get("failure_overlap", {})
    if test_overlap:
        print(f"  Test overlap with failures:  precision={test_overlap['precision']:.4f}  recall={test_overlap['recall']:.4f}")
    print(f"  Baseline comparison (test): {results['test'].get('baseline_comparison', 'N/A')}")
    print()


if __name__ == "__main__":
    main()
