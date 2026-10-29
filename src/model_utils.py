"""Model artifact save / load utilities.

Every saved artifact bundle includes:
  - The fitted preprocessing pipeline
  - The trained estimator
  - Metadata (model version, feature names, training config, metrics, etc.)

Artifacts are stored under the configured ``MODEL_DIR`` using joblib.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from src.config import MODEL_DIR

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Metadata recorded alongside a trained model artifact."""

    model_type: str                       # e.g. "isolation_forest", "random_forest"
    model_version: str                    # e.g. "anomaly_v1", "failure_v1"
    feature_names: list[str]              # post-preprocessing feature names
    training_timestamp: str = ""
    random_seed: int | None = None
    dataset_rows: int = 0
    training_rows: int = 0
    model_params: dict[str, Any] = field(default_factory=dict)
    threshold: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.training_timestamp:
            self.training_timestamp = datetime.now(timezone.utc).isoformat()


class ModelArtifact:
    """Bundle of preprocessor + estimator + metadata."""

    def __init__(
        self,
        preprocessor: Any,
        estimator: Any,
        metadata: ModelMetadata,
    ) -> None:
        self.preprocessor = preprocessor
        self.estimator = estimator
        self.metadata = metadata

    # -- persistence --------------------------------------------------------

    def save(self, directory: Path | str | None = None) -> Path:
        """Persist the artifact to disk.

        Creates three files under *directory*:
          - ``{version}_preprocessor.joblib``
          - ``{version}_estimator.joblib``
          - ``{version}_metadata.json``
        """
        directory = Path(directory or MODEL_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        version = self.metadata.model_version

        prep_path = directory / f"{version}_preprocessor.joblib"
        est_path = directory / f"{version}_estimator.joblib"
        meta_path = directory / f"{version}_metadata.json"

        joblib.dump(self.preprocessor, prep_path)
        joblib.dump(self.estimator, est_path)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.metadata), f, indent=2, default=_json_default)

        logger.info("Saved artifact '%s' to %s", version, directory)
        return directory

    @classmethod
    def load(cls, version: str, directory: Path | str | None = None) -> "ModelArtifact":
        """Load a previously saved artifact by *version* name."""
        directory = Path(directory or MODEL_DIR)

        prep_path = directory / f"{version}_preprocessor.joblib"
        est_path = directory / f"{version}_estimator.joblib"
        meta_path = directory / f"{version}_metadata.json"

        for p in (prep_path, est_path, meta_path):
            if not p.exists():
                raise FileNotFoundError(f"Model artifact file not found: {p}")

        preprocessor = joblib.load(prep_path)
        estimator = joblib.load(est_path)
        with open(meta_path, encoding="utf-8") as f:
            meta_dict = json.load(f)
        metadata = ModelMetadata(**meta_dict)

        logger.info("Loaded artifact '%s' from %s", version, directory)
        return cls(preprocessor=preprocessor, estimator=estimator, metadata=metadata)


def _json_default(obj: Any) -> Any:
    """JSON serialiser fallback for numpy types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
