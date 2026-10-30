# Predictive Maintenance & Anomaly Detection AI

Milestones 1 and 2 are implemented: the repository validates the actual AI4I 2020 CSV, trains separate anomaly-detection and row-level failure-classification pipelines, evaluates held-out data, saves versioned artifacts, and serves those existing artifacts through a FastAPI prediction service.

Milestones 3–5 (persistence, monitoring, deployment) remain future work.

## Dataset

Use the [AI4I 2020 Predictive Maintenance Dataset from UCI](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset). Place the original CSV at `data/raw/ai4i2020.csv`. The supplied local copy is the 10,000-row dataset and includes a UTF-8 BOM; ingestion uses `utf-8-sig`. The raw CSV is excluded from Git by `.gitignore`, so obtain it from UCI when setting up a fresh checkout.

The source has 14 columns: UDI and Product ID identifiers; Type (`L`, `M`, `H`); air and process temperature, rotational speed, torque, and tool wear; the `Machine failure` binary target; and five failure-mode labels (`TWF`, `HDF`, `PWF`, `OSF`, `RNF`). IDs and all failure-mode labels are excluded from model inputs. Failure-mode counts overlap and should not be summed as unique failed rows.

Observed data-quality findings from the local CSV: 10,000 rows; 339 machine-failure rows (3.39%); no missing values, duplicate rows, duplicate UDIs, invalid Types, or values outside the configured sensor ranges. Cleaning retains all 10,000 rows. Configured numeric ranges are 290–310 K (air), 300–320 K (process), 1,000–3,000 rpm, 0–100 Nm, and 0–300 minutes of tool wear. These are validation bounds, not claims about all industrial equipment.

AI4I is synthetic industrial data, not live factory telemetry. It does not provide a usable per-machine chronological history for forecasting a future failure window. The supervised model therefore classifies whether an individual row is associated with the provided failure label; it does not forecast future failures.

## Environment and commands

Python 3.12 is recommended. The Milestone 1 commands below were run using Python 3.12.14 on Windows PowerShell. From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `py -3.12` is unavailable, install Python 3.12 from python.org and rerun the commands. The current environment used the desktop runtime's Python 3.12.14 executable to create `.venv`; no system security settings were changed.

Train and evaluate both models:

```powershell
python -m scripts.train_anomaly
python -m scripts.train_failure
python -m scripts.evaluate
python -m pytest -q
```

The training scripts print a data-quality report and save artifacts and JSON evaluation reports under `models/`. Raw data, model artifacts, `.venv`, and the project-local generated files are git-ignored as configured.

## Pipeline and artifacts

`src/data_ingestion.py` loads with BOM-aware encoding, validates the schema, ranges, missing values, duplicates, Types, numeric features, and binary labels, then applies explicit cleaning rules. Invalid/missing required columns or non-binary labels fail clearly. `src/preprocessing.py` makes stratified 70% train / 10% validation / 20% test partitions before fitting a scaler and one-hot encoder on training rows only. The same fitted transformer is applied to validation, test, and inference inputs.

The failure pipeline trains class-weighted Logistic Regression and Random Forest candidates. It chooses the decision threshold and winning estimator by validation F1, then reports held-out metrics. Inputs include only the five sensor readings and Type; `Machine failure`, `TWF`, `HDF`, `PWF`, `OSF`, and `RNF` are excluded.

The anomaly pipeline fits Isolation Forest on the training partition, with contamination 0.05. Its `score_samples` values are higher for more normal observations; a score below the persisted estimator offset is classified anomalous. This score is not a failure probability. It also compares against a 3-standard-deviation statistical baseline. The overlap with failure labels is informational only because an anomaly is not equivalent to a failure.

Each model bundle is saved as a preprocessor, estimator, and metadata JSON file. Metadata records features, version, timestamp, seed, parameters, threshold, and evaluation details. `scripts.evaluate` reloads both bundles and evaluates them on the reproducible held-out split without retraining.

## Results from the executed run

Split seed: 42. Each split is stratified. Metrics below are from the held-out 2,000-row test partition.

| Pipeline | Result |
| --- | --- |
| Isolation Forest | 103/2,000 observations flagged (5.15%); score cutoff −0.585987. Relative to failure labels: precision 0.1262, recall 0.1912. The 3σ baseline flagged 237/2,000 (11.85%) and agreed with Isolation Forest on 90.9% of rows. |
| Failure classifier | Random Forest selected over Logistic Regression by validation F1; validation-selected threshold 0.605. Test precision 0.7955, recall 0.5147, F1 0.6250, PR-AUC 0.7406, ROC-AUC 0.9648; confusion matrix TN=1923, FP=9, FN=33, TP=35. |

The classifier threshold was selected on validation data; the test results are held-out. Metrics describe this dataset and split and do not establish performance on real equipment or future data. Full reports are in `models/anomaly_v1_evaluation.json` and `models/failure_v1_evaluation.json` after training.

## FastAPI prediction service

The API loads `anomaly_v1` and `failure_v1` artifacts once during application startup. It validates each artifact's model version, raw input schema, transformed feature names, estimator feature count, and model-specific prediction interface. It does not train or update models on startup or per request. If an artifact is missing or incompatible, the process still serves `/health`; `/ready` reports HTTP 503 and prediction requests for an unavailable model return HTTP 503 without exposing internal loader details.

Run from the repository root after creating `.venv`, installing requirements, and generating both model artifacts as described above:

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open interactive Swagger documentation at `http://127.0.0.1:8000/docs`; the OpenAPI schema is at `http://127.0.0.1:8000/openapi.json`.

| Method and path | Behavior |
| --- | --- |
| `GET /health` | Basic process health. |
| `GET /ready` | Confirms both model bundles loaded and passed compatibility checks; otherwise returns 503. |
| `POST /predict/anomaly` | Returns Isolation Forest score, normal/anomaly classification, and transparent standardized-feature deviations. The score is not a failure probability. |
| `POST /predict/failure` | Returns the row-level predicted failure class and Random Forest `predict_proba` estimate. The estimate is not separately calibrated and is not a future-failure forecast. |

Both prediction endpoints accept exactly the six model inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, and `Tool wear [min]`. IDs, `Machine failure`, and failure-mode labels are not accepted. Type must be `L`, `M`, or `H`; numeric values must be JSON numbers within the documented dataset bounds (290–310 K, 300–320 K, 1,000–3,000 rpm, 0–100 Nm, and 0–300 minutes). Missing or extra fields and invalid values receive HTTP 422.

Example request (the same observation can be posted to either prediction route):

```json
{
  "Type": "M",
  "Air temperature [K]": 298.1,
  "Process temperature [K]": 308.6,
  "Rotational speed [rpm]": 1551,
  "Torque [Nm]": 42.8,
  "Tool wear [min]": 0
}
```

Example anomaly response from a live request:

```json
{
  "prediction_id": "cc4de0b7-9d67-4de4-8b5a-6f018bdc4d72",
  "anomaly_score": -0.5078505082382462,
  "classification": "normal",
  "model_version": "anomaly_v1",
  "prediction_timestamp": "2026-10-30T00:01:51.495268Z",
  "inference_latency_ms": 123.2057,
  "explanation": {
    "method": "absolute_deviation_in_standardised_space",
    "anomaly_score": -0.507851,
    "top_suspicious_features": [
      {"feature": "num__Tool wear [min]", "standardised_value": -1.6843, "abs_deviation": 1.6843},
      {"feature": "cat__Type_M", "standardised_value": 1.0, "abs_deviation": 1.0},
      {"feature": "num__Process temperature [K]", "standardised_value": -0.9596, "abs_deviation": 0.9596}
    ]
  }
}
```

Example failure response from a live request:

```json
{
  "prediction_id": "e7404f4b-5373-424f-81af-2ef80d831e9f",
  "predicted_class": 0,
  "failure_probability": 0.005,
  "model_version": "failure_v1",
  "prediction_timestamp": "2026-10-30T00:01:51.550841Z",
  "inference_latency_ms": 49.3232
}
```

Prediction logs record outcome, prediction ID, model name/version, timestamp, and inference latency. Sensor payloads are not logged. This milestone does not persist prediction history; SQL storage is planned for Milestone 3. The API test suite uses FastAPI `TestClient`; run it with:

```powershell
python -m pytest -q
```

Milestone 2 verification: **20 passed** (15 API tests and five Milestone 1 tests), with no TestClient deprecation warning after declaring Starlette's recommended `httpx2` dependency. `pip check` reports no broken requirements. The independent audit also verified partial model availability, direct-vs-API prediction equivalence, inference-error sanitization, and clean 422 responses for NaN and infinity inputs. A live Uvicorn run returned 200 for health, readiness, both predictions, Swagger UI, and OpenAPI; invalid inputs returned 422.

## Current scope and limitations

- Implemented: local CSV ingestion and validation, leakage-aware preprocessing/splitting, Isolation Forest with score cutoff and statistical comparison, Logistic Regression baseline, Random Forest comparison, class-imbalance weighting, held-out evaluation, metadata/artifact persistence, artifact reload, FastAPI health/readiness and inference endpoints, request validation, model compatibility checks, prediction logging, and Milestone 1/2 tests.
- Not implemented yet: SQL persistence, operational/data-drift monitoring, Docker deployment, or dashboard. These belong to later milestones.
- No time-series forecasting or calibrated failure probability is claimed. Random Forest `predict_proba` is an estimator score and has not been separately calibrated.
- Dataset values are synthetic and may not represent actual sensor distributions, failure prevalence, or operational costs.
