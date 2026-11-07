# Architecture

This document describes the current repository implementation. The backend and frontend are independently started in local development. Docker Compose deploys only the FastAPI backend; GitHub Actions runs frontend checks and mocked Playwright tests.

## High-level architecture

```mermaid
flowchart LR
  CSV[UCI AI4I CSV] --> ING[Ingestion and validation]
  ING --> PRE[Leakage-safe split and preprocessing]
  PRE --> TRAIN[Anomaly and failure training scripts]
  TRAIN --> ART[Versioned preprocessors, estimators, metadata]
  REF[Versioned drift reference] --> API[FastAPI service]
  ART --> API
  API --> DB[(SQLite database)]
  API --> HEALTH[Health, readiness, metrics, drift APIs]
  API --> PRED[Prediction APIs]
  DB --> PRED
  DB --> HEALTH
  WEB[React and TypeScript frontend] -->|same-origin /api| VITE[Vite development proxy]
  VITE -->|strips /api| API
  CI[GitHub Actions frontend CI] --> UNIT[Typecheck, Vitest, production build]
  CI --> E2E[Playwright with intercepted API fixtures]
  COMPOSE[Docker Compose: backend API only] --> API
  VOL[(Named SQLite volume)] --> DB
```

The offline training pipeline produces the inference artifacts consumed at API startup. The frontend uses Axios and TanStack Query to request actual API data. The Vite proxy is a development arrangement; it is not a deployed reverse proxy. CI's browser tests intercept requests and are not live backend integration tests.

## ML training pipeline

```mermaid
flowchart TD
  LOAD[Load AI4I CSV] --> VALID[Validate schema, types, ranges, missingness, duplicates]
  VALID --> CLEAN[Apply explicit cleaning]
  CLEAN --> SELECT[Select six model inputs and target]
  SELECT --> SPLIT[Stratified 70/10/20 split, seed 42]
  SPLIT --> FIT[Fit scaler and encoder on training rows only]
  FIT --> TRANSFORM[Transform train, validation, and test]
  TRANSFORM --> IF[Train Isolation Forest, contamination 0.05]
  TRANSFORM --> LR[Train Logistic Regression baseline]
  TRANSFORM --> RF[Train Random Forest candidate]
  LR --> CHOOSE[Select classifier and threshold by validation F1]
  RF --> CHOOSE
  IF --> EVAL[Held-out test evaluation]
  CHOOSE --> EVAL
  EVAL --> SAVE[Save estimator, preprocessor, metadata, evaluation report]
```

`UDI`, `Product ID`, and the five failure-mode labels are not model features. Fitted preprocessing does not see validation or test data. The Random Forest selection and threshold use validation F1; the held-out test results are reported separately. Isolation Forest is evaluated as anomaly detection, including overlap with failure labels only as descriptive comparison—not as equivalence between anomaly and failure.

## Prediction request flows

The frontend presents two independent model actions. Both use the same six validated sensor inputs, but each request executes only its selected model.

```mermaid
sequenceDiagram
  actor User
  participant UI as Prediction Lab
  participant API as FastAPI
  participant Schema as Pydantic validation
  participant Model as Isolation Forest
  participant Store as SQLite transaction
  User->>UI: Submit observation for anomaly detection
  UI->>API: POST /predict/anomaly
  API->>Schema: Validate six features and association
  Schema-->>API: Valid SensorObservation
  API->>Model: score_samples and classify
  API->>Store: Persist equipment, reading, and prediction atomically
  Store-->>API: Commit
  API-->>UI: Classification, anomaly score, IDs, timestamp, version
```

```mermaid
sequenceDiagram
  actor User
  participant UI as Prediction Lab
  participant API as FastAPI
  participant Schema as Pydantic validation
  participant Model as Random Forest classifier
  participant Store as SQLite transaction
  User->>UI: Submit observation for failure classification
  UI->>API: POST /predict/failure
  API->>Schema: Validate six features and association
  Schema-->>API: Valid SensorObservation
  API->>Model: Predict class and class-1 estimator output
  API->>Store: Persist equipment, reading, and prediction atomically
  Store-->>API: Commit
  API-->>UI: Predicted class, uncalibrated estimator output, IDs, timestamp, version
```

Anomaly scores are Isolation Forest `score_samples` values, not failure probabilities. The supervised class-1 output is not separately calibrated and is not a future forecast. The frontend does not automatically retry prediction POST requests; after a timeout it warns that the outcome may be unknown and directs the user to equipment-scoped history.

## Monitoring and drift flow

```mermaid
flowchart LR
  OBS[Validated prediction observation] --> WRITE[Prediction workflow transaction]
  WRITE --> READINGS[(Sensor readings)]
  WRITE --> PREDS[(Prediction records)]
  BATCH[Client-submitted drift batch] --> DRIFT[Drift detector]
  REF[Training-split reference artifact] --> DRIFT
  DRIFT --> REPORT[(Persisted drift report)]
  GETDRIFT[GET /monitoring/drift] --> REPORT
  METRICS[GET /monitoring/metrics or /metrics/summary] --> PROC[Process-local metrics snapshot]
  HEALTH[GET /health and /ready] --> STATUS[Liveness and readiness response]
  UI[Overview, Drift Monitoring, System Health] --> GETDRIFT
  UI --> METRICS
  UI --> HEALTH
```

Drift is evaluated on a submitted batch, not on a continuous sensor stream. Numeric features use two-sample KS tests; categorical `Type` uses total variation distance. The minimum current batch size is configurable (default 20); defaults are KS alpha 0.05 and TVD threshold 0.10. A successful report is saved, and GET returns the latest report only (404 if none exists). Drift does not establish model degradation. Metrics are in-memory and process-local; they reset on restart and are not shared across worker processes. `/health` is liveness; `/ready` checks loaded model bundles and a database connectivity probe.

## Deployment and development topology

```mermaid
flowchart TB
  subgraph Compose[Docker Compose deployment]
    IMAGE[Python 3.12 backend image]
    API[Uvicorn and FastAPI on container port 8000]
    DB[(SQLite file on named volume)]
    IMAGE --> API
    API --> DB
    READY[GET /ready health check] --> API
  end
  BROWSER[Developer browser] --> VITE[Vite development server 127.0.0.1:5173]
  VITE -->|/api proxy strips prefix| API
  CI[GitHub Actions frontend workflow] --> CHECKS[Typecheck, Vitest, build, npm ls]
  CI --> BROWSERTEST[Playwright Chromium with mocked /api]
```

Compose publishes the backend API and persists its SQLite data in a named volume. The frontend is run separately with `npm run dev`; there is no frontend container, production static server, or full-stack Compose deployment in this repository. The `/ready` Compose health check requires both model bundles and a working database. The runtime image uses an unprivileged UID, a read-only root filesystem, a restricted temporary filesystem, dropped Linux capabilities, and `no-new-privileges`; these controls are not a security certification. No authentication or authorization is implemented.

The GitHub Actions workflow runs on pull requests and pushes to `master` plus manual dispatch. It installs frontend dependencies with `npm ci`, typechecks, runs Vitest, builds, checks `npm ls --depth=0`, installs Chromium, and runs Playwright tests. API calls in browser tests are intercepted with fixtures. CI does not verify backend connectivity, persistence, or deployment. See [Frontend setup and CI](../frontend/README.md).
