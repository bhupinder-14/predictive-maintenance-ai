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

Historical Milestone 1 status: at that point, model artifacts were git-ignored outputs and could be regenerated with the training commands. As of commit `a2a09737b42b34fcabb650654d323f1e0fd09c14`, the six v1 production inference artifacts are tracked for deployment; generated evaluation reports and other model outputs remain ignored.

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

At the time of this Milestone 4 report, production model artifacts and the checked-in drift reference were not modified; direct saved-model/API prediction comparisons and Milestones 1–3 regression tests passed. Milestone 5 work had not started, and Milestone 4 acceptance was pending. Milestone 4 was accepted before the Milestone 5 work recorded below.

## Historical Milestone 5 implementation verification (2026-10-30; before owner-run Docker verification)

Added a Python 3.12 slim Docker image definition, one-service Compose configuration, build-context exclusions, persistent SQLite volume configuration, and a host-side deployment smoke-check script. The image installs `requirements.txt`; Pytest and TestClient dependencies were separated into `requirements-dev.txt` so they are not installed in the runtime image. No application entry point, model-loading behavior, migration logic, prediction semantics, or drift method was replaced. Configuration now rejects invalid log levels and out-of-range numeric drift settings clearly at import/startup.

The Dockerfile runs Uvicorn as UID/GID 10001, includes the six runtime model bundle files and versioned drift reference, and excludes evaluation-only outputs, tests, raw data, local database files, environment files, caches, and Git history from the image inputs. Compose publishes configurable host/container ports, mounts the named `predictive-maintenance-data` volume at `/var/lib/predictive-maintenance`, uses the existing additive SQLite initialization, applies `unless-stopped`, drops Linux capabilities, enables `no-new-privileges`, and uses a read-only root filesystem with a temporary `/tmp`. Its health probe calls `/ready` using Python's standard-library HTTP client.

### Executed host verification

- Full suite: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v` → **52 passed in 15.25s**. This includes all previous Milestone 1–4 tests and four deployment/configuration cases for invalid drift/log-level configuration, verifier CLI arguments, and runtime build-context/dependency declarations.
- `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.**
- `git diff --check` → **No errors**; Git emitted line-ending conversion warnings for the mixed-ending worktree.
- Parsed `compose.yaml` with the available PyYAML parser and checked its single API service, named volume, restart policy, read-only root, and `/ready` check → **passed**.
- Ran `scripts/verify_deployment.py` against a temporary local Uvicorn server and a temporary SQLite database → exit code **0**. The script verified `/health`, `/ready`, `/docs`, `/openapi.json`, both prediction routes and saved prediction retrieval, both metrics paths, and persisted drift POST/GET. It wrote only to its temporary database.
- At the time of this implementation verification, `docker --version` and `docker compose version` could not run because Docker was unavailable in that environment. No image build or container test was claimed in that audit; subsequent owner-run Docker evidence is recorded in the current status section below.

Production model artifact and drift-reference SHA-256 values match those recorded before this milestone work. No models were retrained, the reference was not regenerated, and no project database was initialized or modified; tests and the local API smoke check used temporary databases. Milestone 6 was not started. At the time of this historical implementation report, Milestone 5 acceptance had not been claimed.

## Historical Milestone 5 pre-deployment audit corrections (2026-10-30; Docker verification pending at that time)

The image now has a default `DATABASE_URL` under `/var/lib/predictive-maintenance`, and the Dockerfile creates/chowns that directory to UID/GID 10001. Compose continues to supply its `DATABASE_URL` override. The README documents that standalone `docker run` needs a named volume mounted at this location for records to survive container removal; no broad writable application directory or root execution was introduced.

The deployment verifier now checks `/health` and `/ready` fields, required OpenAPI paths, equipment listing (following API pagination), both prediction record IDs and persisted results, their related equipment history entries, stable metrics data across the aliases while excluding request counters/uptime that can change between snapshots, and saved drift-report ID, creation metadata, timestamp, and feature results. It uses only HTTP APIs. Its docstring and README state that it writes two predictions and a drift report to the target application database; verification should use a disposable database/volume.

### Executed correction verification

- Targeted deployment tests: `.venv\Scripts\python.exe -m pytest tests/test_deployment.py -p no:cacheprovider -v` → **9 passed**.
- Ran the deployment verifier against a temporary local Uvicorn process and temporary SQLite file → exit code **0**. It checked health/readiness/docs/OpenAPI, both predictions and exact saved-record retrieval, equipment listing and history, metrics aliases, and drift POST/GET; the temporary database was 77,824 bytes afterward.
- Ran against closed loopback port `127.0.0.1:1` with one-second timeout → exit code **1**, concise `Could not reach /health: URLError` message, no traceback.
- At the time of this correction audit, Docker Engine/Compose was unavailable. No Docker build, standalone/container run, container volume permission test, or container-recreation persistence test was performed; later owner-run results are recorded below.

Final verification for this correction pass:

- `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v` → **57 passed in 14.97s**.
- `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.**
- `git diff --check` → **No errors**; Git emitted line-ending conversion warnings only.

At the time of this correction report, model and drift-reference artifacts were not modified and the real project database was not accessed or changed. Docker build and container volume/runtime checks were still pending then; later owner-run verification is recorded below.

## Historical Milestone 5 final Docker verification gap audit (2026-10-30; before clean-checkout run)

No application or Docker files were changed in this audit. The project owner reports having manually verified image startup, UID/GID 10001, healthy status, API endpoints, and persistence across Compose and standalone recreation with named volumes in a separate environment. Those are recorded here as owner-reported results; they were not independently repeated in this execution environment.

### Commands and results from this audit

- `docker --version` → unavailable: PowerShell reported that `docker` is not recognized (exit status 1).
- `docker compose version` → unavailable for the same reason.
- `docker info --format '{{.ServerVersion}}'` → unavailable for the same reason.
- `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v` → **57 passed in 17.75s**. The existing temporary-database migration tests passed, including additive legacy schema upgrade and idempotency coverage; these do not constitute a mounted-volume/container test.
- `.venv\Scripts\python.exe -m pip check` → **No broken requirements found.**
- `git diff --check` → **No errors**; only Git LF-to-CRLF warnings.
- Parsed `compose.yaml` with PyYAML and statically checked that its default `DATABASE_URL` matches the Dockerfile default, the named volume mounts at `/var/lib/predictive-maintenance`, and the health command targets `/ready` → **passed**. The first check incorrectly expected PyYAML to expand Compose's literal `${DOCKER_DATABASE_URL:-...}` expression and failed; inspection confirmed the interpolation is intentionally left for Compose, and the corrected check passed.
- `Test-Path predictive_maintenance.db` → `False`; no project-root SQLite database was present. No application DB initialization or migration was run against the project directory.

### Static findings and limits

The Dockerfile sets the same default SQLite file that Compose uses, creates its parent directory, and assigns directory ownership to UID/GID 10001 before switching users. Compose overrides `DATABASE_URL` with the same volume-backed default and mounts its named volume at that parent directory. The API startup calls `Database.initialize()`, which runs SQLAlchemy table creation and the existing additive SQLite migration. Its health probe invokes Python's standard-library `urlopen` against `/ready`; a non-2xx readiness response raises an HTTP error and produces an unhealthy probe exit. These are source/configuration findings, not container execution results.

At that audit date, a fresh/no-cache build, actual mounted-volume writes, migration of a pre-existing mounted DB, Docker persistence/recreation, health transitions, and standalone named-volume persistence had not been independently verified in that environment. The later owner-run clean-checkout deployment evidence and final read-only audit are recorded below. No existing volume was modified by that audit.

## Historical Milestone 5 manual Docker evidence and readiness-test update (2026-10-30; before final acceptance)

At the time of this October 30 report, this was the latest Milestone 5 status and it superseded earlier pending Docker-verification statements, which describe the state of those earlier audits.

The project owner reports completing the following manual Docker checks after the final Docker gap audit. These results are recorded as owner-provided evidence; they were not executed again in this documentation update:

- `docker compose build --pull --no-cache api` built a fresh image successfully, and the Compose deployment started and reached healthy status.
- `/health`, `/ready`, and `/docs` were verified. The deployment smoke verifier passed **13/13 checks**, and both model bundles loaded.
- The container ran as UID/GID `10001:10001`; the application user could write to the mounted SQLite volume.
- Prediction and drift-report records survived Compose container recreation with the same named volume. Standalone-container prediction records survived container removal and recreation when the same named volume was reused.
- A disposable legacy SQLite database containing `monitoring_reports` record ID 17 was migrated by normal application startup. The five nullable columns and `ix_monitoring_reports_model_created` index were added; the legacy values remained unchanged and the five new fields were NULL. The volume was writable by UID 10001. The migration checks passed again after restarting the application container.

### Readiness test execution

Executed:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v tests/test_database.py::test_readiness_detects_database_outage_and_recovers tests/test_database.py::test_database_initialization_failure_keeps_health_and_marks_unready tests/test_api.py::test_health_and_readiness_with_saved_models
```

Result: **3 passed in 5.58s**. The tests cover normal ready/health responses, startup database initialization failure, an injected SQLAlchemy exception during the readiness connection probe, `/health` remaining available during that injected failure, sanitized readiness output, and readiness recovery after removing the injection. The injected probe exception is a test of readiness behavior; it does **not** simulate an actual SQLite storage outage. No real SQLite outage is claimed or attempted.

At the time of this October 30 update, runtime dependency inspection, container missing-artifact/invalid-configuration checks, and clean-checkout Docker verification remained outstanding. Subsequent owner-run evidence supersedes that status; the current scope split is recorded below.

## Historical Milestone 5 additional manual acceptance evidence (2026-10-30; before final acceptance)

This update supersedes the preceding section's status for runtime dependency inspection and missing-model/invalid-configuration container checks. The following results were manually verified by the project owner and recorded here as supplied evidence; they were not rerun during this documentation update:

- Runtime packages inside the Docker image: `pip check` reported no broken requirements, and `pytest` plus `httpx2` were absent from the production image.
- Missing-model behavior with the anomaly model unavailable: `GET /health` returned HTTP 200; `GET /ready` returned HTTP 503 with anomaly=false, failure=true, database=true; `POST /predict/anomaly` returned HTTP 503 with `{"detail":"Anomaly model is unavailable"}`; and `POST /predict/failure` returned HTTP 200. The resulting failure prediction was retrieved at `/predictions/{prediction_id}` with HTTP 200 and matching persisted fields.
- Invalid configuration: a disposable container configured with `DRIFT_KS_ALPHA=1.0` exited with code 1. Its logs contained `ValueError: DRIFT_KS_ALPHA must be greater than 0 and less than 1`. Since configuration validation fails before the API starts, this is a startup-failure result and has no `/ready` HTTP status.

At the time of that October 30 entry, clean-checkout Docker verification remained outstanding. It was subsequently completed by the owner-run verification documented below. No actual SQLite storage outage was tested; it remains explicitly unverified.

## Historical Milestone 5 clean-checkout status (2026-10-31; before training reproducibility run)

This section supersedes earlier dated statements that Docker execution or clean-checkout deployment verification remained outstanding. It distinguishes the owner-run Docker execution from checks independently performed by the final audit agent. The audit agent did not run Docker or modify any resource.

### Owner-run clean-checkout deployment evidence

The project owner reports that a fresh image was built from a detached clean worktree in a temporary directory at commit `a2a09737b42b34fcabb650654d323f1e0fd09c14`. Compose resolved one port mapping, `18082:8000`, and used a disposable database volume for the deployment check.

- All six committed production artifacts were SHA-256 checked. The container ran as UID/GID `10001:10001`, reached healthy status, and `/health`, `/ready`, and `/docs` returned HTTP 200. Readiness showed both models and the database available.
- OpenAPI was version 3.1.0 with the eight required API paths. `scripts/verify_deployment.py` reported `passed` and checked 13 endpoints.
- Anomaly prediction `4f84013f-8b47-4f63-a1dd-5fd1fbcf2453`, failure prediction `23a67abc-a771-4362-a562-03d4eabb994a`, and drift report `1` were retrieved. After forced recreation, old container `4ecebc46a96c1f17085d4ac41688cce8c7ac95a015ca6a2ffa3230d724d52299` was replaced by `4a6b9d1578e59a2319efa431af719b3a6f8ed4fc5b2c9ec6056b3f837315926d`; the new container became healthy, and both predictions plus the drift report remained retrievable with unchanged model versions.
- Runtime image `pip check` reported no broken requirements; `pytest` and `httpx2` were absent. Missing-anomaly-artifact behavior passed while failure inference remained available. Invalid `DRIFT_KS_ALPHA=1.0` caused startup exit code 1 with the expected validation message.
- On a disposable legacy SQLite volume, startup migration preserved report ID 17 and its original values, added all five nullable columns and the required index, left the new fields NULL for that row, and passed again after restart. UID 10001 could write to the mounted volume.

### Independent read-only audit evidence and limits

The audit agent confirmed the main repository `HEAD` equals the requested commit and its `git status --short` was empty. A command-scoped `safe.directory` override was needed to inspect the owner-created worktree because it is owned by a different Windows account; its `HEAD` matched the commit and its status was empty. The audit independently hashed the six Git blobs and confirmed all matched their expected SHA-256 values. Docker was not installed in the audit agent's environment, so Docker build, API, health, persistence, and migration behavior were not independently rerun; those execution results above remain explicitly owner-run evidence.

The three readiness tests previously executed in the project environment passed in 5.58 seconds. The runtime failure is injected at the SQLAlchemy connection probe and recovery is tested by removing that injection. It does **not** establish behavior during a real SQLite storage outage. No actual SQLite storage outage has been tested.

### Clean-checkout scope and acceptance status

At the time of this entry, clean-checkout deployment using committed production artifacts was complete, but full training reproducibility from a clean checkout was **not verified**. The earlier 57-passed full-suite result was a local run, not a clean-worktree full-suite run. The subsequent owner-run training reproduction is recorded in the following section.

Checklist section 5.4 and its Milestone 5 completion condition explicitly require a new developer to obtain data, train models, generate artifacts, start the API, make and persist a prediction, and run tests. At the time of this entry that scope remained a mandatory blocker. No actual SQLite storage outage was tested; that limitation remains current.

## Clean-checkout training reproducibility completion (2026-10-31; project-owner-run evidence)

The project owner completed the full training reproducibility workflow in a separate disposable Git worktree at base commit `a2a09737b42b34fcabb650654d323f1e0fd09c14`. This is distinct from the Docker clean-checkout deployment verification above, which used the six committed production artifacts. This documentation update records the owner-provided execution evidence; it did not rerun training or tests.

- Downloaded and extracted the official UCI AI4I 2020 dataset. Its SHA-256 was `dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e`, matching the committed drift-reference provenance.
- Created a Python 3.12.10 environment, installed `requirements-dev.txt`, and ran `pip check` successfully with no broken requirements.
- Ran `python -m scripts.train_anomaly`, `python -m scripts.train_failure`, and `python -m scripts.evaluate`; all completed successfully.
- Reproduced the reported held-out failure-classification results: precision 0.7955, recall 0.5147, F1 0.6250, ROC-AUC 0.9648, PR-AUC 0.7406, and confusion matrix TN=1923, FP=9, FN=33, TP=35. Isolation Forest flagged 103 of 2,000 test rows (5.15%).
- Ran `python -m scripts.generate_drift_reference`. The regenerated JSON matched the committed reference after normalizing timestamp fields; all other keys and statistics matched.
- Ran the complete test suite: **57 passed in 13.06 seconds** using a dedicated `--basetemp` directory. An initial Windows pytest temporary-directory permission issue was resolved by using that dedicated base directory; it was an environment issue, not reported as an application test failure.
- Started the API with the newly generated model artifacts and an isolated disposable SQLite database. `/ready` returned HTTP 200 with anomaly=true, failure=true, and database=true. `scripts/verify_deployment.py` passed all 13 checks covering health, readiness, docs/OpenAPI, both predictions and persisted retrieval, equipment listing/history, both metrics paths, and drift POST/GET.
- Verified all eight generated model/evaluation artifacts and the generated drift reference were present. The disposable worktree remained clean; `git diff --exit-code -- models data/reference` passed. The API process was stopped after verification.

The generated artifacts and reference were isolated from the committed baseline. This establishes workflow and reported-metric reproducibility, not bit-for-bit identical model artifact hashes across dependency versions. Clean-checkout training reproducibility criterion 5.4B is complete. The final independent audit and acceptance decision are recorded below.

The actual SQLite storage-outage scenario remains **not verified**. Existing readiness tests inject a SQLAlchemy connection-probe failure, verify HTTP 503/unready behavior and recovery, and keep `/health` available; they do not simulate a physical database-file or disk outage. This limitation is distinct from the successful disposable-database API persistence verification.

## Final Milestone 5 acceptance (2026-10-31)

The final independent audit returned **PASS WITH LIMITATIONS** and recommended **ACCEPT MILESTONE 5**. Milestone 5 is **ACCEPTED**. The audit independently checked Git state, the documentation changes, and deployment/training implementation by source inspection. Docker execution, clean-checkout training, evaluation, tests, and live API results are project-owner-run evidence recorded above; the audit did not rerun Docker, training, or the test suite.

Limitations remain explicit: an actual SQLite storage/disk outage and recovery is **NOT VERIFIED**; injected SQLAlchemy readiness-probe failure/recovery tests are not a physical storage outage test. Bit-for-bit model artifact reproducibility across dependency versions is **NOT GUARANTEED**. These limitations were not marked as passed.
