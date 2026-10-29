#!/usr/bin/env python
"""Train the supervised failure classification model.

Usage:
    python -m scripts.train_failure

Trains Logistic Regression (baseline) and Random Forest, selects the
best model by validation F1, tunes the decision threshold, and saves
the winning model artifact.

Outputs:
    models/failure_v1_preprocessor.joblib
    models/failure_v1_estimator.joblib
    models/failure_v1_metadata.json
    models/failure_v1_evaluation.json
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import MODEL_DIR, RANDOM_SEED
from src.data_ingestion import (
    clean_dataset,
    get_feature_target_split,
    load_raw_dataset,
    validate_dataset,
)
from src.failure_model import (
    evaluate_classifier,
    find_best_threshold,
    train_logistic_regression,
    train_random_forest,
)
from src.model_utils import ModelArtifact, ModelMetadata
from src.preprocessing import build_preprocessor, get_feature_names, split_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=" * 60)
    logger.info("FAILURE CLASSIFICATION TRAINING PIPELINE")
    logger.info("=" * 60)

    # 1. Load, validate, clean
    df = load_raw_dataset()
    report = validate_dataset(df)
    print(report.summary())

    df = clean_dataset(df)

    # 2. Feature / target split
    #    Failure-type sub-labels (TWF, HDF, PWF, OSF, RNF) are EXCLUDED
    #    because they are a decomposition of the target, not independent features.
    X, y = get_feature_target_split(df, include_failure_types=False)
    logger.info("Features shape: %s, Target distribution:\n%s", X.shape, y.value_counts())

    # 3. Stratified split (before preprocessing)
    splits = split_data(X, y)

    # 4. Fit preprocessor on training data only
    preprocessor = build_preprocessor()
    X_train_t = preprocessor.fit_transform(splits["X_train"])
    X_val_t = preprocessor.transform(splits["X_val"])
    X_test_t = preprocessor.transform(splits["X_test"])
    y_train = splits["y_train"].values
    y_val = splits["y_val"].values
    y_test = splits["y_test"].values

    feature_names = get_feature_names(preprocessor)

    # 5. Train both candidates
    lr_model = train_logistic_regression(X_train_t, y_train, random_seed=RANDOM_SEED)
    rf_model = train_random_forest(X_train_t, y_train, random_seed=RANDOM_SEED)

    # 6. Find best thresholds on validation set
    lr_thresh = find_best_threshold(lr_model, X_val_t, y_val)
    rf_thresh = find_best_threshold(rf_model, X_val_t, y_val)

    # 7. Evaluate both on validation set
    lr_val_metrics = evaluate_classifier(
        lr_model, X_val_t, y_val, threshold=lr_thresh, label="val_logistic_regression",
    )
    rf_val_metrics = evaluate_classifier(
        rf_model, X_val_t, y_val, threshold=rf_thresh, label="val_random_forest",
    )

    # 8. Select winner by validation F1
    lr_f1 = lr_val_metrics["f1_score"]
    rf_f1 = rf_val_metrics["f1_score"]
    if rf_f1 >= lr_f1:
        winner_name = "random_forest"
        winner_model = rf_model
        winner_thresh = rf_thresh
        winner_val = rf_val_metrics
        loser_name = "logistic_regression"
        loser_val = lr_val_metrics
    else:
        winner_name = "logistic_regression"
        winner_model = lr_model
        winner_thresh = lr_thresh
        winner_val = lr_val_metrics
        loser_name = "random_forest"
        loser_val = rf_val_metrics

    logger.info(
        "Model selection: %s (val F1=%.4f) over %s (val F1=%.4f)",
        winner_name, winner_val["f1_score"], loser_name, loser_val["f1_score"],
    )

    # 9. Evaluate winner on held-out TEST set
    test_metrics = evaluate_classifier(
        winner_model, X_test_t, y_test, threshold=winner_thresh, label="test",
    )

    # 10. Build full evaluation report
    evaluation = {
        "selected_model": winner_name,
        "selection_criterion": "validation_f1",
        "logistic_regression_validation": lr_val_metrics,
        "random_forest_validation": rf_val_metrics,
        "test_evaluation": test_metrics,
        "note": (
            "This is row-level failure classification, not future-failure "
            "forecasting. The dataset does not contain temporal sequences "
            "per machine that would support predicting failure within a "
            "future time window."
        ),
    }

    # 11. Save artifact
    model_params = winner_model.get_params()
    # Filter out non-serialisable params
    serialisable_params = {
        k: v for k, v in model_params.items()
        if isinstance(v, (int, float, str, bool, type(None)))
    }

    metadata = ModelMetadata(
        model_type=winner_name,
        model_version="failure_v1",
        feature_names=feature_names,
        random_seed=RANDOM_SEED,
        dataset_rows=len(df),
        training_rows=X_train_t.shape[0],
        model_params=serialisable_params,
        threshold=winner_thresh,
        metrics={
            "validation": winner_val,
            "test": test_metrics,
        },
    )

    artifact = ModelArtifact(
        preprocessor=preprocessor,
        estimator=winner_model,
        metadata=metadata,
    )
    save_dir = artifact.save()

    # 12. Save evaluation report
    eval_path = MODEL_DIR / "failure_v1_evaluation.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2)
    logger.info("Evaluation report saved to %s", eval_path)

    # 13. Summary
    print("\n" + "=" * 60)
    print("FAILURE CLASSIFICATION TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Selected model: {winner_name}")
    print(f"  Decision threshold: {winner_thresh:.4f}")
    print(f"  Artifacts dir: {save_dir}")
    print()
    print("  Validation comparison:")
    print(f"    Logistic Regression  F1={lr_f1:.4f}  (threshold={lr_thresh:.4f})")
    print(f"    Random Forest        F1={rf_f1:.4f}  (threshold={rf_thresh:.4f})")
    print()
    print(f"  Test results ({winner_name}):")
    print(f"    Precision: {test_metrics['precision']:.4f}")
    print(f"    Recall:    {test_metrics['recall']:.4f}")
    print(f"    F1:        {test_metrics['f1_score']:.4f}")
    print(f"    ROC-AUC:   {test_metrics.get('roc_auc', 'N/A')}")
    print(f"    PR-AUC:    {test_metrics.get('pr_auc', 'N/A')}")
    cm = test_metrics["confusion_matrix"]
    print(f"    Confusion matrix:  TN={cm['tn']}  FP={cm['fp']}  FN={cm['fn']}  TP={cm['tp']}")
    print()


if __name__ == "__main__":
    main()
