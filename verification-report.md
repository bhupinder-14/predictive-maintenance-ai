# Milestone 1 Verification Report

Verification date: 2026-10-30 (Asia/Calcutta)  
Project root: `predictive-maintenance-ai`

## Audit findings

- Reviewed `spec.md` (the lowercase filename corresponding to SPEC.md), `CHECKLIST.md`, `requirements.txt`, `.env.example`, `README.md`, every Python file under `src/` and `scripts/`, and the local `data/raw/ai4i2020.csv`.
- `verification-report.md` did not exist at the start of this audit; this report records the executed work.
- The source was already separated into ingestion, preprocessing, artifact, anomaly, failure, and command-line training/evaluation modules. Training excludes `UDI`, `Product ID`, `Machine failure`, and the five failure-mode labels from features.
- Fixed a Windows `cp1252` console crash by replacing the Unicode checkmark in the data-quality report with ASCII text.
- Added strict required-column and binary-label checks. Invalid labels now fail clearly instead of being silently cast.
- Recorded the Isolation Forest score cutoff in artifact metadata and used that cutoff consistently during inference. Clarified that low scores are anomalous and scores are not failure probabilities.
- Added tests for BOM/data validation, leakage exclusion, invalid labels, split/preprocessing behavior, artifact round-trip, and inference.
- Tightened the NumPy and scikit-learn minimum versions for the recommended Python 3.12 environment. The resolver selected compatible packages; `pip check` reported no broken requirements.

## Dataset inspection

Source: UCI AI4I 2020 Predictive Maintenance Dataset, local file `data/raw/ai4i2020.csv`. The file starts with a UTF-8 BOM and loads correctly using `utf-8-sig`.

- 10,000 rows, 14 expected columns, 339 rows with `Machine failure=1` (3.39%).
- 0 missing values, 0 duplicate rows, 0 duplicate UDIs, 0 invalid Type labels, and 0 values outside configured sensor bounds.
- Observed numeric minima/maxima: air temperature 295.3–304.5 K; process temperature 305.7–313.8 K; rotational speed 1,168–2,886 rpm; torque 3.8–76.6 Nm; tool wear 0–253 min.
- Failure-mode label counts: TWF=46, HDF=115, PWF=95, OSF=98, RNF=19. These labels can co-occur.
- This is synthetic tabular data, not continuous telemetry. It supports row-level classification only, not a time-window forecast.

## Environment

Project virtual environment: `.venv`, based on Python 3.12.14. Resolved versions: pandas 3.1.0, NumPy 2.5.4, scikit-learn 1.9.1, SciPy 1.18.1, joblib 1.6.0, pytest 9.2.0. `python -m pip check`: no broken requirements.

## Executed commands and results

Commands run from the repository root:

```powershell
python -m scripts.train_anomaly
python -m scripts.train_failure
python -m scripts.evaluate
python -m pytest -q
```

All four commands completed successfully. `scripts.evaluate` independently loaded `anomaly_v1` and `failure_v1` artifacts and recomputed held-out evaluations. Pytest: **5 passed**.

### Anomaly detection

Isolation Forest parameters: 200 estimators, contamination 0.05, random seed 42. The persisted `score_samples` cutoff is **−0.585987**; scores below it are flagged. On the 2,000-row test split, 103 rows were flagged (5.15%). Comparing flags to `Machine failure` labels only for context: precision 0.1262, recall 0.1912. The 3σ statistical baseline flagged 237 rows (11.85%); prediction agreement with Isolation Forest was 90.9%.

### Failure classification

Failure prevalence is imbalanced; both candidate classifiers used class weighting. Logistic Regression and Random Forest were compared by validation F1. Random Forest won with validation F1 0.7636 and threshold 0.605. Held-out test metrics:

- Precision: 0.7955
- Recall: 0.5147
- F1: 0.6250
- PR-AUC: 0.7406
- ROC-AUC: 0.9648
- Confusion matrix: TN=1923, FP=9, FN=33, TP=35

This is row-level failure classification, not future-failure forecasting. The Random Forest's probability output has not been separately calibrated.

## Saved artifacts

- `models/anomaly_v1_preprocessor.joblib`
- `models/anomaly_v1_estimator.joblib`
- `models/anomaly_v1_metadata.json`
- `models/anomaly_v1_evaluation.json`
- `models/failure_v1_preprocessor.joblib`
- `models/failure_v1_estimator.joblib`
- `models/failure_v1_metadata.json`
- `models/failure_v1_evaluation.json`

Artifact files are git-ignored as model outputs; rerun the training commands to regenerate them. Dataset and model limitations are documented in `README.md` and `CHECKLIST.md`.

## Milestone 2 verification (2026-10-30)

Implemented a modular service under `src/api/`: configuration, Pydantic schemas, artifact registry/compatibility validation, prediction orchestration, route handlers, and an ASGI application factory. The existing Milestone 1 training and artifact files were preserved.

The existing `anomaly_v1` and `failure_v1` artifact bundles loaded during the FastAPI startup lifespan. Compatibility checks validated each artifact version, six-column raw input schema, transformed metadata feature list, estimator input width, and required model interface. The service does not retrain. Missing artifacts, loader exceptions, and incompatible schemas leave health available while readiness reports HTTP 503; model-specific inference returns a sanitized HTTP 503.

Live verification command:

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Observed results: `/health`, `/ready`, `/predict/anomaly`, `/predict/failure`, `/docs`, and `/openapi.json` returned HTTP 200 with the real artifacts loaded. A malformed Type request returned HTTP 422. A second live request confirmed the prediction event logger recorded prediction ID, model version, UTC timestamp, outcome, and latency without logging sensor values. The first valid observation produced anomaly score −0.5078505082 (normal) and failure class 0 with Random Forest probability estimate 0.005. These are examples for that input, not general performance metrics.

Initial full test command `python -m pytest -v`: **15 passed** (10 API tests and 5 Milestone 1 tests). The suite initially emitted a Starlette deprecation warning because `httpx` was installed without Starlette's recommended `httpx2` TestClient dependency. The dependency was updated to `httpx2>=2.0`, and the final audit rerun is recorded below.

At the time of the Milestone 2 audit, the API accepted only `Type` and the five trained sensor features and had no persistence. Milestone 3 adds optional equipment metadata and SQLite persistence as documented below. The model still receives only the six trained features; failure labels and dataset identifiers remain excluded. Anomaly scores remain distinct from failure probability, and the Random Forest probability estimate is not calibrated.

### Independent acceptance audit follow-up

- The audit found that the default FastAPI validation error handler attempted to serialize a NaN input value, causing an exception instead of returning a 422 response. A narrow custom handler now omits raw input values from validation errors. Regression coverage confirms empty body/object, NaN, positive and negative infinity, extra fields, invalid field types/Type, and impossible sensor ranges return HTTP 422.
- Both partial model states were exercised using isolated temporary directories: anomaly-only and failure-only. Each available endpoint returned 200, the unavailable endpoint returned 503, `/health` remained 200, and `/ready` returned 503 with correct per-model status. Both-missing artifacts, incompatible metadata, and loader exceptions were also covered.
- Direct predictions from saved Milestone 1 artifacts matched API anomaly score/class and failure class/probability for identical input. A forced inference exception returned sanitized HTTP 500 without path or traceback in the response.
- Current Starlette TestClient code deprecates the legacy `httpx` client and recommends `httpx2`; `requirements.txt` now declares `httpx2>=2.0`. With installed `httpx2` 2.16.0, the warning no longer appears.
- Final `python -m pytest -v`: **20 passed** (15 API cases and 5 Milestone 1 tests). Final `python -m pip check`: no broken requirements.
- After the validation-handler and TestClient dependency changes, Uvicorn was started again with both artifacts. `/health`, `/ready`, both prediction routes, `/docs`, and `/openapi.json` returned 200; a live NaN request returned 422. Prediction-event logs included IDs, versions, timestamps, outcomes, and latency. No Milestone 3 work was started.

## Milestone 3 implementation verification (2026-10-30)

Implemented database support in `src/database/` and connected it to the existing FastAPI prediction workflow. No Milestone 1 model artifacts, estimators, preprocessors, or training code were changed. Database initialization uses SQLAlchemy `Base.metadata.create_all`; this creates missing tables but is not a migration mechanism for changing existing schemas.

### Schema and workflow

- `equipment`: integer primary key, name, AI4I product `Type` stored as `equipment_type`, optional location, and creation timestamp.
- `sensor_readings`: equipment FK, timestamp, all six original model input values, and source. Database CHECK constraints enforce supported Type and configured numeric bounds.
- `predictions`: UUID primary key, equipment and reading FKs, model version, mutually exclusive anomaly fields or failure probability, latency, and creation timestamp. CHECK constraints enforce result shape, valid probability, and nonnegative latency.
- `monitoring_reports`: report fields and window-order constraint only. No drift calculations or monitoring endpoints were added.

Foreign keys are enabled for SQLite connections. The database manager creates parent directories for file-backed SQLite databases, uses `check_same_thread=False`, supports in-memory test databases, and exposes short-lived sessions. The application initializes the database during startup. `/ready` now reports model and database readiness; `/health` remains a process-health response when database initialization fails.

Both inference endpoints create/reuse equipment, persist the sensor observation, run the existing inference service on the unchanged six raw model fields, persist the model-specific result, and commit as one transaction. A model or database exception rolls back pending writes. A persistence error returns sanitized HTTP 503; no response claims success when the prediction was not committed. The response prediction ID is also the persisted record ID.

Database setup commands from the repository root:

```powershell
python -m src.database.init_db
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
python -m pytest -v
```

Set `DATABASE_URL` to select another SQLite file; a relative `sqlite:///./name.db` path is resolved from the project root. Test apps override this with a distinct SQLite file under pytest's temporary directory. Historical query helpers are implemented in `src/database/repository.py` and execute against persisted rows: latest readings, date-range prediction selection, most flagged equipment, mean anomaly score, model-version counts, and mean/nearest-rank P95 latency.

### Executed verification

Command: `.venv\Scripts\python.exe -m pytest -q`

Result: **25 passed in 8.94s** (no warnings in the captured output).

Dependency check: `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.**

The documented initializer was also invoked with `DATABASE_URL` pointed at an isolated temporary SQLite file; output: `Database schema initialized.`

Coverage by test:

- `tests/test_milestone1.py` (5): actual dataset/BOM validation, failure-label leakage exclusion, invalid labels, train-only preprocessing fit, and saved-model reload/inference.
- `tests/test_api.py` (15 cases including parametrized partial availability): health/readiness and OpenAPI, valid anomaly/failure predictions, required/invalid/range/extra field validation, NaN/infinity sanitization, direct-vs-API inference equivalence, missing/partial/incompatible model artifacts, loader errors, and sanitized inference errors. All these tests now use a fresh temporary database.
- `test_database_initialization_equipment_and_foreign_key_relationships`: four table names, equipment/readings/prediction relationship navigation, and active SQLite foreign-key pragma.
- `test_historical_sql_queries_use_persisted_records`: latest reading, bounded date query, flagged-equipment count, mean anomaly score, model-version counts, average latency, and nearest-rank P95 from seeded records.
- `test_api_persists_prediction_history_and_survives_restart`: both prediction types, equipment registration/reuse, record lookup, history, and a second FastAPI app instance reopening the same SQLite file.
- `test_database_write_failure_rolls_back_and_never_returns_success`: injected prediction INSERT failure gives HTTP 503 and leaves no equipment, reading, or prediction records.
- `test_database_initialization_failure_keeps_health_and_marks_unready`: unsupported driver leaves `/health` at 200, `/ready` at 503 with `database=false`, and prediction request at sanitized 503.

The restart test demonstrates durable file-backed SQLite records across application startup/shutdown. README examples document the optional equipment fields and history endpoints. Sample response identifiers and timestamps are placeholders, not additional measured model results. No Milestone 4 work was started.

## Independent Milestone 3 acceptance audit (2026-10-30)

Audit run independently against fresh temporary SQLite files; no application code or model artifacts were changed during the audit.

- Full suite: `.venv\Scripts\python.exe -m pytest -v` → **25 passed in 8.24s**, including all five Milestone 1 tests and all 15 Milestone 2 API cases. The tests use pytest temporary databases.
- Dependency check: `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.**
- Direct schema/API checks passed: required tables, primary/foreign keys and indexes were present; `failure_probability` is nullable; empty historical query outputs were correct; valid anomaly and failure records were linked to readings/equipment; all six raw input values round-tripped in history; listing, pagination and prediction retrieval worked; unknown equipment and prediction IDs returned 404; sensor-reading INSERT failure rolled back its equipment write and returned 503; persisted records remained retrievable after a new application startup.
- A simulated startup database initialization failure produced `/health` 200, `/ready` 503 with `database=false`, and a prediction 503. A separately simulated database outage after successful startup showed `/equipment` returning 503, but `/ready` still returned 200 with `database=true`.

**Needs attention:** readiness reflects only the startup `database.initialized` flag; it does not check an active connection when `/ready` is requested. The README and checklist now state this limitation. Core persistence, retrieval, rollback, and restart acceptance flows were independently verified. This audit did not begin Milestone 4.

## Runtime readiness fix and verification (2026-10-30)

Updated `Database.check_connection()` to execute read-only `SELECT 1` using `engine.connect()` as a context manager. The readiness route now checks that probe on every request and reports `database=false` with HTTP 503 when unavailable. A failed probe does not expose exception details; `/health` remains independent from database status. No prediction route, transaction flow, model implementation, or trained artifact was changed.

The prior runtime-outage finding was reproduced by an automated test that makes only the readiness probe fail, then removes the failure and checks recovery. It asserts normal readiness is HTTP 200, simulated outage readiness is sanitized HTTP 503, `/health` remains HTTP 200 during the outage, and readiness returns to HTTP 200 after recovery. The existing startup-unavailable test also remains in the suite.

Final command: `.venv\Scripts\python.exe -m pytest -v` → **26 passed in 8.50s**, including all Milestone 1 and 2 tests. `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.** The test apps use isolated pytest temporary SQLite databases. No Milestone 4 work was started.

## Milestone 4 acceptance-gap corrections (2026-10-30; independent audit pending)

The original Milestone 4 implementation introduced in-memory counters and sensor drift checks. This correction adds the missing durable report workflow, metrics compatibility/status summaries, rolling metrics, and a repeatable benchmark. No production model artifacts were retrained or modified. The drift reference was read and regenerated only to a temporary output path for comparison; the checked-in reference was not changed.

### Persisted reports and SQLite upgrade

`MonitoringReport` now stores reference version, batch description, methodology JSON, overall metadata JSON, and complete per-feature results JSON in addition to its existing fields. `POST /monitoring/drift` persists only after a valid batch has been evaluated. It returns the existing response schema; database write failure returns sanitized HTTP 503. Raw sensor batches are not saved. For this non-chronological dataset, window start/end describe the evaluation instant, not a time-series window. The scalar legacy `drift_metric` is left NULL because KS p-values and TVD distances are not comparable as one score.

`GET /monitoring/drift` returns the latest stored report with its report ID and saved metadata, ordered by creation timestamp and then primary key descending. It returns HTTP 404 when no report exists and sanitized HTTP 503 when the database is unavailable. Retrieval does not invoke the drift detector.

`Database.initialize()` applies an idempotent additive SQLite upgrade after `create_all`: it adds nullable report columns and the expected report index when missing. `BEGIN IMMEDIATE` serializes upgrades. Existing rows and the existing database file are preserved. The migration test initialized a legacy-shaped table with a row, verified new columns were added, and verified the row's old values remained intact.

### Operational metrics and benchmark

`GET /metrics/summary` is the SPEC path; `/monitoring/metrics` remains a documented alias. Both return the same schema. Prediction counters are grouped by anomaly/failure family and actual loaded model version. Availability includes sanitized per-model states (`available`, `missing_artifacts`, `incompatible_artifacts`, `load_failed`) and a live database `SELECT 1` result.

Cumulative counters are since process start. `rolling_window` summarizes request counts/statuses/durations, prediction classes/model versions, and prediction errors from the trailing `METRICS_WINDOW_SECONDS` interval (default 300 seconds). A scrape is recorded after its response snapshot and is visible to the next scrape. Both storage modes are process-local and reset after restart.

The repeatable script is `scripts/benchmark_api.py`; command used for the observed run:

```powershell
python -m scripts.benchmark_api --base-url http://127.0.0.1:62759 --warmup-requests 2 --requests 5 --timeout-seconds 15
```

It ran against a temporary loopback API process with a temporary SQLite database. It returned exit code 0 and five measured samples per endpoint after two warm-ups. Observed client-side HTTP latency (ms):

| Endpoint | n | p50 | p95 | p99 | Mean | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `/predict/anomaly` | 5 | 54.6910 | 56.2352 | 56.4928 | 53.9460 | 56.5572 |
| `/predict/failure` | 5 | 64.9724 | 74.8343 | 75.9489 | 67.1092 | 76.2275 |

These are one local run, not a service-level guarantee. Results depend on hardware, network, server settings, and database state. The benchmark has no universal pass/fail latency threshold; its prediction requests perform normal persistence into the temporary database.

### Executed verification

Final complete command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v` → **48 passed in 19.86s**. This run covered 8 acceptance-gap cases, 4 benchmark cases, 15 API cases, 6 database cases, 8 Milestone 1/pipeline cases, and 7 existing monitoring/drift cases. Tests use `tmp_path` databases and output artifacts; the benchmark test uses mocks, while the measured run used a temporary local server/database.

`.venv\Scripts\python.exe -m pip check` → **No broken requirements found.** `git diff --check` → **No errors** (Git reports line-ending conversion warnings for existing CRLF/LF worktree files).

Production model artifacts and the checked-in drift reference were not modified. Existing direct saved-model/API prediction comparisons and Milestones 1–3 regression tests passed. No Milestone 5 work was started. Independent acceptance audit remains pending; no Milestone 4 acceptance is claimed.
