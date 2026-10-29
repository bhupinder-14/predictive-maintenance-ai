from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.anomaly_model import predict_anomaly, train_anomaly_model
from src.config import FAILURE_TYPE_COLUMNS, RAW_DATASET_PATH, TARGET_COLUMN
from src.data_ingestion import (
    clean_dataset,
    get_feature_target_split,
    load_raw_dataset,
    validate_dataset,
)
from src.failure_model import predict_failure, train_logistic_regression
from src.model_utils import ModelArtifact, ModelMetadata
from src.preprocessing import build_preprocessor, split_data


@pytest.fixture(scope="module")
def dataset() -> pd.DataFrame:
    return clean_dataset(load_raw_dataset())


def test_actual_dataset_loads_with_bom_and_validates(dataset: pd.DataFrame) -> None:
    raw_bytes = RAW_DATASET_PATH.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")
    report = validate_dataset(dataset)
    assert not report.has_issues
    assert len(dataset) == 10_000
    assert int(dataset[TARGET_COLUMN].sum()) == 339
    assert dataset.duplicated().sum() == 0


def test_failure_labels_are_excluded_from_model_features(dataset: pd.DataFrame) -> None:
    X, y = get_feature_target_split(dataset)
    assert TARGET_COLUMN not in X.columns
    assert not set(FAILURE_TYPE_COLUMNS).intersection(X.columns)
    assert len(X) == len(y)


def test_invalid_binary_labels_are_reported_and_rejected(dataset: pd.DataFrame) -> None:
    dirty = dataset.copy()
    dirty.loc[0, TARGET_COLUMN] = 2
    report = validate_dataset(dirty)
    assert report.invalid_binary_labels[TARGET_COLUMN] == 1
    with pytest.raises(ValueError, match="invalid non-binary labels"):
        clean_dataset(dirty)


def test_preprocessor_fit_uses_training_partition_only(dataset: pd.DataFrame) -> None:
    X, y = get_feature_target_split(dataset)
    splits = split_data(X, y)
    preprocessor = build_preprocessor()
    preprocessor.fit(splits["X_train"])
    # ColumnTransformer records the exact input columns used during fit.
    assert list(preprocessor.feature_names_in_) == list(splits["X_train"].columns)
    assert len(splits["X_train"]) + len(splits["X_val"]) + len(splits["X_test"]) == len(X)


def test_saved_artifacts_reload_and_predict(dataset: pd.DataFrame, tmp_path) -> None:
    X, y = get_feature_target_split(dataset)
    splits = split_data(X, y)
    prep = build_preprocessor()
    train_x = prep.fit_transform(splits["X_train"])
    sample = splits["X_test"].iloc[:5]
    transformed_sample = prep.transform(sample)

    failure = train_logistic_regression(train_x, splits["y_train"].to_numpy())
    failure_artifact = ModelArtifact(
        prep,
        failure,
        ModelMetadata(
            model_type="logistic_regression",
            model_version="failure_test",
            feature_names=list(prep.get_feature_names_out()),
            threshold=0.5,
        ),
    )
    failure_artifact.save(tmp_path)
    loaded_failure = ModelArtifact.load("failure_test", tmp_path)
    predictions = predict_failure(loaded_failure, sample)
    assert len(predictions) == len(sample)
    assert all(p.predicted_class in (0, 1) for p in predictions)

    anomaly = train_anomaly_model(train_x, n_estimators=20)
    anomaly_artifact = ModelArtifact(
        prep,
        anomaly,
        ModelMetadata(
            model_type="isolation_forest",
            model_version="anomaly_test",
            feature_names=list(prep.get_feature_names_out()),
            threshold=float(anomaly.offset_),
        ),
    )
    anomaly_artifact.save(tmp_path)
    loaded_anomaly = ModelArtifact.load("anomaly_test", tmp_path)
    results = predict_anomaly(loaded_anomaly, sample)
    assert len(results) == len(sample)
    assert np.allclose(
        [r.anomaly_score for r in results],
        loaded_anomaly.estimator.score_samples(transformed_sample),
    )
    assert all(isinstance(r.is_anomaly, bool) for r in results)
