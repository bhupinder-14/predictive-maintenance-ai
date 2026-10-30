"""Create versioned drift reference statistics from the training split only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import (
    CATEGORICAL_FEATURE_COLUMNS,
    DRIFT_REFERENCE_PATH,
    NUMERIC_FEATURE_COLUMNS,
    RANDOM_SEED,
    RAW_DATASET_PATH,
    TEST_SIZE,
    VALIDATION_SIZE,
)
from src.data_ingestion import clean_dataset, get_feature_target_split, load_raw_dataset
from src.preprocessing import split_data

REFERENCE_VERSION = "drift_reference_v1"
QUANTILES = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
CATEGORIES = ("H", "L", "M")
EXPECTED_FEATURES = [*NUMERIC_FEATURE_COLUMNS, *CATEGORICAL_FEATURE_COLUMNS]


def build_reference_payload(
    training_features: pd.DataFrame,
    *,
    dataset_sha256: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Summarize only the model's raw training feature frame."""
    if list(training_features.columns) != [*CATEGORICAL_FEATURE_COLUMNS, *NUMERIC_FEATURE_COLUMNS]:
        raise ValueError("Reference frame does not match the six allowed sensor features")
    if training_features.empty:
        raise ValueError("Cannot create a drift reference from an empty training split")
    if not set(training_features["Type"].dropna().unique()).issubset(CATEGORIES):
        raise ValueError("Reference frame contains an unsupported Type category")

    numeric_statistics: dict[str, dict[str, Any]] = {}
    for name in NUMERIC_FEATURE_COLUMNS:
        values = pd.to_numeric(training_features[name], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Reference feature {name!r} contains non-finite values")
        numeric_statistics[name] = {
            "mean": float(np.mean(values)),
            "standard_deviation": float(np.std(values, ddof=1)),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
            "median": float(np.median(values)),
            "quantiles": {
                str(q): float(np.quantile(values, q)) for q in QUANTILES
            },
            # Retain the empirical reference sample for two-sample KS inference.
            "reference_values": sorted(float(value) for value in values),
        }

    counts = training_features["Type"].value_counts().to_dict()
    type_counts = {category: int(counts.get(category, 0)) for category in CATEGORIES}
    sample_size = len(training_features)
    type_proportions = {
        category: type_counts[category] / sample_size for category in CATEGORIES
    }
    timestamp = generated_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "reference_version": REFERENCE_VERSION,
        "generated_at": timestamp.astimezone(timezone.utc).isoformat(),
        "source_dataset": "UCI AI4I 2020 Predictive Maintenance Dataset",
        "source_dataset_sha256": dataset_sha256,
        "reference_selection": {
            "split": "train",
            "random_seed": RANDOM_SEED,
            "test_fraction": TEST_SIZE,
            "validation_fraction": VALIDATION_SIZE,
            "partition_method": "stratified row split from src.preprocessing.split_data",
            "target_usage": "Machine failure used only for stratification; target values are not reference features",
            "test_and_validation_excluded": True,
        },
        "feature_names": EXPECTED_FEATURES,
        "training_sample_size": sample_size,
        "numeric_statistics": numeric_statistics,
        "categorical_statistics": {
            "Type": {
                "categories": list(CATEGORIES),
                "counts": type_counts,
                "proportions": type_proportions,
            }
        },
    }


def generate_reference(
    dataset_path: Path = RAW_DATASET_PATH,
    output_path: Path = DRIFT_REFERENCE_PATH,
) -> dict[str, Any]:
    """Load the actual CSV, reuse its training split, and write reference JSON."""
    raw = load_raw_dataset(dataset_path)
    cleaned = clean_dataset(raw)
    features, target = get_feature_target_split(cleaned)
    splits = split_data(features, target)
    training_features = splits["X_train"]
    payload = build_reference_payload(
        training_features,
        dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=RAW_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DRIFT_REFERENCE_PATH)
    args = parser.parse_args()
    payload = generate_reference(args.dataset, args.output)
    print(
        f"Generated {payload['reference_version']} from "
        f"{payload['training_sample_size']} training rows at {args.output}"
    )


if __name__ == "__main__":
    main()
