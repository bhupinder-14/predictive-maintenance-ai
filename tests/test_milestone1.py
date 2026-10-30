from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.anomaly_model import predict_anomaly, train_anomaly_model
from src.config import FAILURE_TYPE_COLUMNS, MODEL_DIR, RAW_DATASET_PATH, TARGET_COLUMN
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
    assert not {"UDI", "Product ID"}.intersection(X.columns)
    assert len(X) == len(y)


def test_data_quality_report_covers_missing_duplicates_invalid_values_and_extra_columns(
    dataset: pd.DataFrame,
) -> None:
    dirty = dataset.iloc[:10].copy()
    dirty["Air temperature [K]"] = dirty["Air temperature [K]"].astype(object)
    dirty.loc[dirty.index[1], "Torque [Nm]"] = np.nan
    dirty.loc[dirty.index[2], "Air temperature [K]"] = "not numeric"
    dirty.loc[dirty.index[3], "Type"] = "X"
    dirty["unexpected sensor"] = 1
    dirty = pd.concat([dirty, dirty.iloc[[0]]], ignore_index=True)

    report = validate_dataset(dirty)
    assert report.missing_counts["Torque [Nm]"] == 1
    assert report.duplicate_rows == 1
    assert report.duplicate_udis == 1
    assert report.non_numeric_errors["Air temperature [K]"] == 1
    assert report.invalid_types == 1
    assert report.unexpected_columns == ["unexpected sensor"]


def test_preprocessor_transforms_valid_inference_rows_to_expected_schema(
    dataset: pd.DataFrame,
) -> None:
    X, y = get_feature_target_split(dataset)
    splits = split_data(X, y)
    preprocessor = build_preprocessor().fit(splits["X_train"])
    transformed = preprocessor.transform(splits["X_test"].iloc[:8])
    assert transformed.shape == (8, len(preprocessor.get_feature_names_out()))
    assert np.isfinite(transformed).all()


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


def test_existing_production_artifact_predictions_are_deterministic() -> None:
    raw_features = pd.DataFrame([{
        "Type": "M",
        "Air temperature [K]": 298.1,
        "Process temperature [K]": 308.6,
        "Rotational speed [rpm]": 1551,
        "Torque [Nm]": 42.8,
        "Tool wear [min]": 0,
    }])
    anomaly_artifact = ModelArtifact.load("anomaly_v1", MODEL_DIR)
    failure_artifact = ModelArtifact.load("failure_v1", MODEL_DIR)

    anomaly_first = predict_anomaly(anomaly_artifact, raw_features)[0]
    anomaly_second = predict_anomaly(anomaly_artifact, raw_features)[0]
    failure_first = predict_failure(failure_artifact, raw_features)[0]
    failure_second = predict_failure(failure_artifact, raw_features)[0]

    assert anomaly_first == anomaly_second
    assert failure_first == failure_second
