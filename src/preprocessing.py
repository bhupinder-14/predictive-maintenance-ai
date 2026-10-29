"""Leakage-safe preprocessing pipeline for the AI4I 2020 dataset.

Key design decisions:
  - All fitted transformations (scaling, encoding) are learned **only** on
    the training split, then applied identically to validation / test / prod.
  - The pipeline is serialised alongside the model for reproducible inference.
  - Failure-type sub-labels are excluded from features to prevent target
    leakage (they are a *decomposition* of the target, not predictors).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import (
    CATEGORICAL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    RANDOM_SEED,
    TEST_SIZE,
    VALIDATION_SIZE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Train / Validation / Test split
# ---------------------------------------------------------------------------

def split_data(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    test_size: float = TEST_SIZE,
    validation_size: float = VALIDATION_SIZE,
    random_seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Stratified split into train / validation / test sets.

    Returns a dict with keys ``X_train``, ``y_train``, ``X_val``, ``y_val``,
    ``X_test``, ``y_test``.

    The split is performed **before** any fitted preprocessing so that
    validation and test distributions are never seen during fitting.
    """
    # First: separate test set
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_seed,
        stratify=y,
    )
    # Second: separate validation from training
    # validation_size is a fraction of the original dataset, so we rescale
    val_frac_of_trainval = validation_size / (1.0 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval,
        test_size=val_frac_of_trainval,
        random_state=random_seed,
        stratify=y_trainval,
    )
    logger.info(
        "Split sizes  train=%d  val=%d  test=%d",
        len(X_train), len(X_val), len(X_test),
    )
    return {
        "X_train": X_train, "y_train": y_train,
        "X_val": X_val, "y_val": y_val,
        "X_test": X_test, "y_test": y_test,
    }


# ---------------------------------------------------------------------------
# Preprocessing pipeline builder
# ---------------------------------------------------------------------------

def build_preprocessor(
    numeric_features: list[str] | None = None,
    categorical_features: list[str] | None = None,
) -> ColumnTransformer:
    """Build a scikit-learn ``ColumnTransformer`` for the AI4I feature set.

    - Numeric features → ``StandardScaler``
    - Categorical features → ``OneHotEncoder`` (drop='if_binary')

    The returned transformer must be **fit only on training data**.
    """
    if numeric_features is None:
        numeric_features = list(NUMERIC_FEATURE_COLUMNS)
    if categorical_features is None:
        categorical_features = list(CATEGORICAL_FEATURE_COLUMNS)

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(drop="if_binary", sparse_output=False,
                                  handle_unknown="infrequent_if_exist"),
             categorical_features),
        ],
        remainder="drop",  # drop UDI, Product ID, etc.
        verbose_feature_names_out=True,
    )
    return preprocessor


def get_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    """Extract human-readable feature names from a *fitted* preprocessor."""
    return list(preprocessor.get_feature_names_out())


def preprocess_split(
    splits: dict[str, Any],
    preprocessor: ColumnTransformer | None = None,
) -> tuple[dict[str, np.ndarray], ColumnTransformer]:
    """Fit the preprocessor on ``X_train`` and transform all splits.

    Parameters
    ----------
    splits : dict
        Output of :func:`split_data`.
    preprocessor : ColumnTransformer, optional
        If *None* a fresh one is built via :func:`build_preprocessor`.

    Returns
    -------
    transformed : dict
        Same keys as *splits* but with numpy arrays instead of DataFrames.
    preprocessor : ColumnTransformer
        The **fitted** preprocessor (save alongside the model).
    """
    if preprocessor is None:
        preprocessor = build_preprocessor()

    # Fit ONLY on training data
    X_train_t = preprocessor.fit_transform(splits["X_train"])
    logger.info(
        "Preprocessor fitted on training data (%d rows, %d features → %d transformed)",
        splits["X_train"].shape[0], splits["X_train"].shape[1], X_train_t.shape[1],
    )

    transformed: dict[str, Any] = {
        "X_train": X_train_t,
        "y_train": np.asarray(splits["y_train"]),
        "X_val": preprocessor.transform(splits["X_val"]),
        "y_val": np.asarray(splits["y_val"]),
        "X_test": preprocessor.transform(splits["X_test"]),
        "y_test": np.asarray(splits["y_test"]),
    }
    return transformed, preprocessor
