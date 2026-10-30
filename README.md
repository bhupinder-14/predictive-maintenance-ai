# Predictive Maintenance & Anomaly Detection AI

Milestones 1–3 are accepted. Milestone 4 monitoring and drift implementation is in place and awaits its independent acceptance audit. Deployment remains future work.

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
| `GET /ready` | Confirms both model bundles are loaded and runs a read-only database connectivity probe (`SELECT 1`); returns 503 if either is unavailable. |
| `POST /predict/anomaly` | Returns Isolation Forest score, normal/anomaly classification, and transparent standardized-feature deviations. The score is not a failure probability. |
| `POST /predict/failure` | Returns the row-level predicted failure class and Random Forest `predict_proba` estimate. The estimate is not separately calibrated and is not a future-failure forecast. |

Both prediction endpoints accept the six model inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, and `Tool wear [min]`. Optional database fields are `equipment_id` (reuse a registered record), `equipment_name`, `equipment_location`, and timezone-aware `observed_at`. Provide an existing `equipment_id` or optionally a name/location; when identity is omitted, the request is registered as a distinct equipment record and the returned `equipment_id` can be reused. The model receives only the six original model inputs. Dataset identifiers (`UDI`, `Product ID`), `Machine failure`, and failure-mode labels are not accepted. Type must be `L`, `M`, or `H`; numeric values must be JSON numbers within the documented dataset bounds (290–310 K, 300–320 K, 1,000–3,000 rpm, 0–100 Nm, and 0–300 minutes). Missing or extra fields and invalid values receive HTTP 422.

Example request (the same observation can be posted to either prediction route):

```json
{
  "Type": "M",
  "Air temperature [K]": 298.1,
  "Process temperature [K]": 308.6,
  "Rotational speed [rpm]": 1551,
  "Torque [Nm]": 42.8,
  "Tool wear [min]": 0,
  "equipment_name": "CNC 12",
  "equipment_location": "Line A"
}
```

Illustrative anomaly response shape (IDs and times are generated per request):

```json
{
  "prediction_id": "<generated UUID>",
  "equipment_id": 1,
  "reading_id": 1,
  "anomaly_score": -0.5078505082382462,
  "classification": "normal",
  "model_version": "anomaly_v1",
  "prediction_timestamp": "<UTC timestamp>",
  "inference_latency_ms": 0.0,
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

Illustrative failure response shape:

```json
{
  "prediction_id": "<generated UUID>",
  "equipment_id": 1,
  "reading_id": 2,
  "predicted_class": 0,
  "failure_probability": 0.005,
  "model_version": "failure_v1",
  "prediction_timestamp": "<UTC timestamp>",
  "inference_latency_ms": 0.0
}
```

Prediction logs record outcome, prediction ID, equipment and reading IDs, model name/version, timestamp, and inference latency. Sensor payloads are not logged. Both prediction endpoints save the observation and result in one database transaction; database failures return HTTP 503 and roll back the complete write. Failed model inference also rolls back the reading and equipment registration created for that request.

## SQLite database and history

The default database is `predictive_maintenance.db` in the project root. Set `DATABASE_URL` to change it, for example `sqlite:///./local.db` (relative paths resolve from the project root). SQLite foreign-key enforcement is enabled. Application startup and `python -m src.database.init_db` create missing tables and apply the additive SQLite schema upgrade. For an existing `monitoring_reports` table, the upgrade adds any missing report columns and the model/created-time index without resetting the database or deleting existing records. Repeated initialization is idempotent.

| Table | Contents and relationships |
| --- | --- |
| `equipment` | Registered name, AI4I product `Type` (L/M/H), optional location, creation time. |
| `sensor_readings` | Equipment FK, timestamp, all six raw model fields, and source. |
| `predictions` | Equipment and reading FKs, model version, model-specific output, latency, timestamp. Anomaly columns are null for failure rows and failure probability is null for anomaly rows. |
| `monitoring_reports` | Persisted drift-report metadata and per-feature results. Successful `POST /monitoring/drift` evaluations are saved; `GET /monitoring/drift` retrieves the latest saved report. Raw sensor batches are not stored, and GET returns saved results without recalculating drift. Database failures return sanitized HTTP 503 errors. |

Relationships are Equipment 1-to-many SensorReadings and Predictions, and SensorReading 1-to-many Predictions. Foreign keys, range/result consistency constraints, and query indexes are defined in `src/database/models.py`.

| Method and path | Behavior |
| --- | --- |
| `GET /equipment` | List registered equipment (`limit`, `offset`). |
| `GET /equipment/{equipment_id}/history` | Readings with saved predictions (`limit`, `offset`). |
| `GET /predictions/{prediction_id}` | Retrieve one persisted prediction. |

Historical SQL helpers are in `src/database/repository.py`: latest readings per equipment, predictions in a date range, most frequently anomaly-flagged equipment, average anomaly score by equipment, counts by model version, and average/nearest-rank P95 inference latency. They query stored records; these SQL aggregates do not have a dedicated endpoint.

## Operational monitoring and drift detection

### Request and prediction metrics

`GET /metrics/summary` returns operational counters; `/monitoring/metrics` remains an alias with the same response schema. ASGI middleware records the matched route template, status and end-to-end request duration. Statuses below 400 count as successful; 400 and above count as failed. Metrics include cumulative-since-process-start totals and a separate rolling window (default 300 seconds), each with request counts and latency summaries. `METRICS_WINDOW_SECONDS` configures the rolling-window length.

Successfully persisted anomaly outcomes (`normal`/`anomaly`) and failure classifications (class 0/1) are separate and grouped by the model version returned by the loaded artifact. Failed prediction requests are counted by family. The response's `availability.models` reports sanitized `available`, `missing_artifacts`, `incompatible_artifacts`, or `load_failed` status and the actual loaded version when available. `availability.database_available` uses a live read-only `SELECT 1` connectivity probe.

Counters are thread-safe, in-memory, and process-local. Both cumulative and rolling counters reset when the process restarts and are not shared across workers. A metrics response is counted after its snapshot is taken, so a scrape appears in the following snapshot. No credentials, request bodies, local paths, or stack traces are returned.

The response includes these principal sections (per-endpoint request details, model-version subcounts, and rolling-window counterparts are also included):

```json
{
  "requests": {"total": 0, "successful": 0, "failed": 0, "status_codes": {}, "by_endpoint": {}, "duration_ms": {"total": 0, "average": 0, "max": 0}},
  "predictions": {
    "anomaly": {"total": 0, "normal": 0, "anomaly": 0, "by_model_version": {}},
    "failure": {"total": 0, "predicted_class_0": 0, "predicted_class_1": 0, "by_model_version": {}},
    "errors": {"total": 0, "by_model": {}}
  },
  "runtime": {"uptime_seconds": 0, "metrics_storage": "in_memory_process_local"},
  "availability": {"models": {}, "database_available": true},
  "rolling_window": {"window_seconds": 300, "requests": {}, "predictions": {}}
}
```

The zeros above show the response shape, not measured service metrics.

### Repeatable prediction latency benchmark

With the API running, execute:

```powershell
python -m scripts.benchmark_api --base-url http://127.0.0.1:8000 --warmup-requests 5 --requests 100
```

The command warms each prediction endpoint independently, then measures the requested number of successful HTTP prediction calls using `perf_counter_ns`. It reports measured sample count, p50, p95, p99, mean, and maximum milliseconds for anomaly and failure separately. Percentiles use NumPy's linear interpolation. Each call creates the normal sensor-reading and prediction records; use a suitable database when running a larger benchmark. No universal latency pass/fail threshold is implied. Results depend on hardware, network, server configuration, and database state.

Observed local benchmark (Python 3.12.14, Windows, loopback API, temporary SQLite database, two warm-ups and five measured requests per endpoint):

| Endpoint | n | p50 ms | p95 ms | p99 ms | Mean ms | Max ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `/predict/anomaly` | 5 | 54.6910 | 56.2352 | 56.4928 | 53.9460 | 56.5572 |
| `/predict/failure` | 5 | 64.9724 | 74.8343 | 75.9489 | 67.1092 | 76.2275 |

### Drift reference and methods

The checked-in reference is [`data/reference/drift_reference_v1.json`](data/reference/drift_reference_v1.json). It was generated from the existing AI4I cleaned data and the same `split_data` function and seed used by model training: the stratified 7,000-row training partition only. Validation and held-out test rows are excluded. The target is used only by the existing split function for stratification; the saved feature list and statistics contain only five numeric sensor features and `Type`. The artifact records numerical mean, sample standard deviation, minimum, maximum, median, quantiles, empirical reference values, and `Type` category counts/proportions.

Regenerate deliberately after placing the original CSV at `data/raw/ai4i2020.csv`:

```powershell
python -m scripts.generate_drift_reference
```

The command overwrites the configured reference path. `DRIFT_REFERENCE_PATH` can select a different location; relative paths resolve from the project root. The API loads and validates this versioned JSON at startup. A missing or incompatible reference leaves inference available and makes `POST /monitoring/drift` return a sanitized HTTP 503.

`POST /monitoring/drift` accepts a non-empty batch of 1–10,000 observations, each containing exactly the six supported raw input features. It rejects IDs, targets, failure-mode columns, extra fields, invalid Type values, invalid sensor values, NaN, and infinity. A batch under 20 observations returns `overall_status: insufficient_data`; no per-feature drift decision is made. Raw batches are not stored. Each successful evaluation is persisted as a report.

- Each numeric feature is tested independently with a two-sided two-sample Kolmogorov–Smirnov test. Drift is flagged when `p_value < 0.05`.
- Categorical `Type` is evaluated separately with total variation distance (half the L1 distance between reference/current category proportions). Drift is flagged at distance `>= 0.10`; absent categories receive proportion zero.
- Overall status is `drift_detected` when any feature meets its rule, `no_drift_detected` when none do, or `insufficient_data` below 20 current rows. These metrics are not collapsed into a combined score.

The POST response lists each feature's method, statistic, threshold, sample sizes, and decision; numeric features also include the KS p-value. `GET /monitoring/drift` returns the latest saved response plus `report_id`, `created_at`, evaluation `window_start`/`window_end`, batch description, reference version, model-version context, methodology, and overall report metadata. Latest ordering is `created_at DESC, id DESC`. If no report exists, GET returns HTTP 404 with `{"detail":"No drift report is available"}`. Database failures return sanitized HTTP 503. GET reads the saved report without recalculating drift.

The persisted `monitoring_reports` table retains its original columns and adds nullable `reference_version`, `batch_description`, `methodology`, `report_metadata`, and `feature_results` fields. The existing `model_version` column records the actual loaded model versions associated with the report (or `not_model_specific` if none were loaded). Since numeric KS p-values and categorical TVD scores are not comparable, the legacy scalar `drift_metric` remains NULL; full per-feature values are stored in `feature_results`. For this dataset, batch window timestamps mark the evaluation instant; they do not imply chronological telemetry.

On application startup, `Database.initialize()` applies an idempotent additive SQLite schema upgrade under a write lock. It adds nullable columns and the model/created-time index if absent, preserving existing rows. No database reset is performed. The normal API startup and `python -m src.database.init_db` initialization command apply this upgrade.

Example of the POST response for one valid row (below the minimum sample size):

```json
{
  "reference_version": "drift_reference_v1",
  "generated_at": "2026-10-30T00:43:47.592749Z",
  "reference_sample_size": 7000,
  "current_sample_size": 1,
  "minimum_sample_size": 20,
  "overall_status": "insufficient_data",
  "features": [
    {
      "feature_name": "Air temperature [K]",
      "method": "kolmogorov_smirnov_two_sample",
      "statistic": null,
      "p_value": null,
      "threshold": 0.05,
      "threshold_kind": "p_value_significance_level",
      "drift_detected": null,
      "reference_sample_size": 7000,
      "current_sample_size": 1
    }
  ],
  "interpretation": "Drift indicates an input distribution change; it does not by itself establish reduced model accuracy."
}
```

The response excerpt shows one of six feature entries; the actual response includes all monitored features. KS uses univariate marginal distributions and a per-feature 0.05 significance level without a multiple-testing correction; p-values are sample-size sensitive. Total variation's 0.10 cutoff is a practical distance threshold, not a significance test. These checks do not test feature correlations, establish model degradation, or measure current accuracy. No raw request batch is persisted, and no automatic retraining occurs.

The drift thresholds, reference path and metrics window can be set with `DRIFT_KS_ALPHA`, `DRIFT_CATEGORICAL_TVD_THRESHOLD`, `DRIFT_MINIMUM_SAMPLE_SIZE`, `DRIFT_REFERENCE_PATH`, and `METRICS_WINDOW_SECONDS`; defaults are 0.05, 0.10, 20, `data/reference/drift_reference_v1.json`, and 300 seconds respectively. SciPy was already a declared dependency; no new package or infrastructure was added.

The API test suite uses FastAPI `TestClient` and a fresh temporary SQLite database per test. Run it with:

```powershell
python -m pytest -q
```

Milestone 2 verification: **20 passed** (15 API tests and five Milestone 1 tests), with no TestClient deprecation warning after declaring Starlette's recommended `httpx2` dependency. Milestone 3 verification: **26 passed** (including schema, query, transaction, API persistence, restart, and readiness outage/recovery tests). These are test-suite results from the current implementation; the exact final command output is recorded in `verification-report.md`.

## Current scope and limitations

- Implemented: local CSV ingestion and validation, leakage-aware preprocessing/splitting, Isolation Forest with score cutoff and statistical comparison, Logistic Regression baseline, Random Forest comparison, class-imbalance weighting, held-out evaluation, metadata/artifact persistence, artifact reload, FastAPI health/readiness and inference endpoints, request validation, model compatibility checks, SQLite persistence and history endpoints, historical SQL helpers, process-local request/prediction metrics, a training-split-only versioned drift reference, validated drift evaluation, and Milestone 1–4 tests.
- Not implemented yet: persistent operational metric counters, Docker deployment, or dashboard. Drift reports are persisted; raw drift request batches are not.
- No time-series forecasting or calibrated failure probability is claimed. Random Forest `predict_proba` is an estimator score and has not been separately calibrated.
- Dataset values are synthetic and may not represent actual sensor distributions, failure prevalence, or operational costs.
