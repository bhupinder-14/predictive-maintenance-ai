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

The API accepts only `Type` and the five trained sensor features. It rejects failure labels, identifiers, unknown fields, missing fields, nonnumeric sensor values, invalid Type values, and values outside the documented bounds. Anomaly scores remain distinct from failure probability; the failure response's Random Forest probability estimate is not calibrated. No database, persistence, monitoring, deployment, or dashboard functionality was added; those remain later milestones.

### Independent acceptance audit follow-up

- The audit found that the default FastAPI validation error handler attempted to serialize a NaN input value, causing an exception instead of returning a 422 response. A narrow custom handler now omits raw input values from validation errors. Regression coverage confirms empty body/object, NaN, positive and negative infinity, extra fields, invalid field types/Type, and impossible sensor ranges return HTTP 422.
- Both partial model states were exercised using isolated temporary directories: anomaly-only and failure-only. Each available endpoint returned 200, the unavailable endpoint returned 503, `/health` remained 200, and `/ready` returned 503 with correct per-model status. Both-missing artifacts, incompatible metadata, and loader exceptions were also covered.
- Direct predictions from saved Milestone 1 artifacts matched API anomaly score/class and failure class/probability for identical input. A forced inference exception returned sanitized HTTP 500 without path or traceback in the response.
- Current Starlette TestClient code deprecates the legacy `httpx` client and recommends `httpx2`; `requirements.txt` now declares `httpx2>=2.0`. With installed `httpx2` 2.16.0, the warning no longer appears.
- Final `python -m pytest -v`: **20 passed** (15 API cases and 5 Milestone 1 tests). Final `python -m pip check`: no broken requirements.
- After the validation-handler and TestClient dependency changes, Uvicorn was started again with both artifacts. `/health`, `/ready`, both prediction routes, `/docs`, and `/openapi.json` returned 200; a live NaN request returned 422. Prediction-event logs included IDs, versions, timestamps, outcomes, and latency. No Milestone 3 work was started.
