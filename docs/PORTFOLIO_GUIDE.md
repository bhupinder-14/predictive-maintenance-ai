# Predictive Maintenance & Anomaly Detection AI

> A reproducible machine-learning and API project with a React operations dashboard. It demonstrates row-level anomaly detection and failure classification on the UCI AI4I 2020 dataset; it is not a live industrial monitoring or future-failure forecasting system.

This guide supplements the protected root [README](../README.md), which documents the accepted M1–M5 backend and deployment evidence. The [frontend guide](../frontend/README.md) contains frontend-specific commands. See [Architecture](ARCHITECTURE.md) for data-flow diagrams and [Screenshot Guide](screenshots/README.md) for a truthful demonstration plan.

## Project overview

Predictive maintenance uses observed machine data to help identify unusual operating patterns or conditions associated with failures. This project addresses those as two separate modeling tasks:

- **Anomaly detection** asks whether a sensor observation looks unusual relative to the model's training distribution. It uses an unsupervised Isolation Forest.
- **Failure classification** asks whether a labeled AI4I observation is associated with the dataset's `Machine failure` target. It uses a supervised classifier.

The distinction matters: unusual operation is not synonymous with failure, and a row-level failure label is not a forecast of a future event. The application demonstrates data validation, leakage-aware model training, inference, persistence, equipment-scoped history, operational monitoring, drift reporting, a typed frontend, and automated tests.

## Key capabilities

| Area | Implemented capability |
| --- | --- |
| Data and ML | AI4I CSV validation/cleaning; stratified data splits; preprocessing fitted on training data; Isolation Forest anomaly scoring; Logistic Regression baseline and Random Forest failure-classification comparison; saved model bundles and evaluation metadata. |
| API | FastAPI health/readiness, independent prediction endpoints, equipment listing/history, saved prediction retrieval, metrics, and drift evaluation/latest-report endpoints. |
| Persistence | SQLite storage for equipment, sensor readings, predictions, and persisted drift reports. Prediction workflow writes the observation and result in one transaction. |
| Monitoring | Process-local request/prediction counters, a separate rolling window, model/database readiness, and a persisted latest drift report. |
| Deployment | Docker image and Compose service for the **backend API only**, with a named database volume and runtime hardening. |
| Frontend | React/TypeScript command center with seven routes, same-origin `/api` requests through Vite during development, TanStack Query server state, and data-backed charts. |
| Quality checks | Python tests, frontend Vitest tests, frontend Playwright tests with intercepted/mock API responses, and a GitHub Actions workflow for frontend checks. |

The frontend CI suite is not a live-backend or deployment test. The Playwright suite uses controlled fixtures and does not write to the application database.

## Technology stack

Frontend versions below are pinned in the manifest. Python versions are the versions observed in the current local `.venv`; the Python requirements files specify lower bounds rather than an exact lockfile, so these observed versions are not guaranteed for another installation.

| Component | Technology |
| --- | --- |
| Data and ML | Python 3.12.14; Pandas 3.1.0, NumPy 2.5.4, scikit-learn 1.9.1 |
| API and validation | FastAPI 0.162.0, Pydantic 2.14.2 |
| Persistence | SQLAlchemy 2.1.6, SQLite |
| Backend tests | Pytest 9.2.0 and FastAPI TestClient |
| Containerization | Docker and Docker Compose |
| Frontend | React 18.3.1, TypeScript 5.7.2, Vite 6.4.5, Tailwind CSS 3.4.17 |
| Frontend data/UI | TanStack Query 5.66.9, Axios 1.21.0, Recharts 3.10.1, Lucide React 0.468.0 |
| Browser tests | Playwright 1.64.1 |
| CI | GitHub Actions (`checkout@v4`, `setup-node@v4`, `upload-artifact@v4`) |

Python libraries are declared in `requirements.txt` and `requirements-dev.txt` using version ranges. The frontend pins exact direct dependency versions in `frontend/package.json` and uses `frontend/package-lock.json` for installation.

## Dataset and model methodology

### Dataset

The project uses the [UCI AI4I 2020 Predictive Maintenance Dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset). The inspected dataset has 10,000 rows and 14 columns, including identifiers, six model inputs, the `Machine failure` label, and five failure-mode labels. The inspected local copy had 339 failure-labeled rows, no missing values, and no duplicate records.

The six model inputs are `Type` plus air temperature, process temperature, rotational speed, torque, and tool wear. `UDI` and `Product ID` are identifiers. `TWF`, `HDF`, `PWF`, `OSF`, and `RNF` are excluded from model inputs because they describe failure modes and can leak the target. Failure-mode labels can overlap; their counts must not be summed as unique failed rows.

AI4I is synthetic tabular data. It does not supply reliable chronological sequences for individual real machines. Its distributions and failure prevalence do not establish performance on operating equipment.

### Split and leakage control

The accepted split is stratified with `random_state=42`: 7,000 training rows, 1,000 validation rows, and 2,000 held-out test rows. Splitting precedes fitted preprocessing. Scaling and categorical encoding are fitted only on the training rows, then reused for validation, test, and inference. Validation data supports model/threshold selection; test data is reserved for final reported evaluation.

### Anomaly detection

The anomaly pipeline fits an Isolation Forest with contamination 0.05. It returns `score_samples` and applies the estimator's persisted decision threshold to classify an observation as normal or anomalous. For this score, lower values are more anomalous. The test split flagged 103 of 2,000 observations (5.15%). A separate 3-standard-deviation baseline is also evaluated.

An anomaly flag is not a failure label, failure probability, proof of damage, or estimate of future risk.

### Failure classification

The supervised pipeline compares Logistic Regression and Random Forest. The winning model and decision threshold are selected using validation F1, then evaluated once on the held-out test split. Random Forest was selected in the accepted run.

| Held-out test metric | Result |
| --- | ---: |
| Precision | 0.7955 |
| Recall | 0.5147 |
| F1 | 0.6250 |
| PR-AUC | 0.7406 |
| ROC-AUC | 0.9648 |
| Accuracy | 0.9790 |
| Confusion matrix | TN 1923, FP 9, FN 33, TP 35 |

These are results from the stated split and dataset, not live production performance. The dataset is imbalanced: accuracy alone can conceal missed positive cases, so precision/recall and PR-AUC provide important context. The Random Forest class-1 `predict_proba` output is an **uncalibrated estimator output**. It is not a calibrated probability, future failure forecast, or remaining-useful-life estimate.

### Artifact loading

Training scripts save a preprocessor, estimator, and metadata for each model. The API loads the versioned inference artifacts during startup and checks their compatibility; it does not train per request. Docker copies the existing model and drift-reference artifacts into the backend image. Re-training is separate and requires the raw CSV.

## Frontend feature tour

All routes are client-side React Router routes and are lazy loaded. The API client uses same-origin `/api`; Vite's development proxy strips `/api` and forwards to the backend (default `http://127.0.0.1:8000`).

| Route | What it shows and consumes | Actions and limitations |
| --- | --- | --- |
| **Overview** `/` | Shared health/readiness, operational metrics, prediction-family counts, and latest drift report from the monitoring APIs. | Refreshes health every 15 s, metrics every 30 s, and drift every 60 s while the page is active; background polling is disabled. Cumulative metrics are process-local; rolling values have a bounded window. |
| **Equipment Explorer** `/equipment` | Equipment metadata from `GET /equipment`. | Loads paginated records and searches records currently loaded in the browser. The API provides no total count or server-side search. |
| **Equipment Profile** `/equipment/:equipmentId` | Metadata and paginated readings with associated predictions from equipment-scoped history. | Shows the latest **persisted observation** and sensor charts over loaded readings. It is not live telemetry; charts cover loaded pages, not complete lifetime history. |
| **Prediction Lab** `/prediction-lab` | Equipment choices plus validated six-feature input. | Runs anomaly detection or failure classification independently and displays each returned model result. Predictions persist the reading and result; timeout messaging treats the outcome as potentially unknown and directs the user to history before retrying. |
| **Prediction History** `/prediction-history` | Paginated readings and saved predictions for the selected equipment; saved details use `GET /predictions/{prediction_id}`. | History is equipment-scoped, not global. Anomaly scores and failure estimator outputs remain distinct; historical failure classes are not reconstructed. |
| **Drift Monitoring** `/drift` | The latest persisted report from `GET /monitoring/drift`. | Handles the no-report response as an empty state. It does not provide report history or upload a drift batch from this page. |
| **System Health** `/system` | `/health`, `/ready`, and operational metrics. | Separates liveness from readiness, model/database availability, and metrics failures. Metrics are process-local and reset on restart. |

Equipment history pagination is scoped by equipment ID. The API does not support a global prediction-history endpoint. Prediction records can share a reading; profile analytics distinguish unique readings from unique prediction IDs.

### API surface

| Method and path | Purpose and response behavior |
| --- | --- |
| `GET /health` | Process liveness. |
| `GET /ready` | Model and database readiness; can return HTTP 503 when a required dependency is unavailable. |
| `POST /predict/anomaly` | Validate a sensor observation, run anomaly detection, and persist the reading/result. |
| `POST /predict/failure` | Validate an observation, run supervised classification, and persist the reading/result. |
| `GET /equipment?limit=&offset=` | Paginated equipment listing. |
| `GET /equipment/{equipment_id}/history?limit=&offset=` | Paginated readings and associated prediction summaries for one equipment record. |
| `GET /predictions/{prediction_id}` | Retrieve one saved prediction. |
| `GET /metrics/summary` and `GET /monitoring/metrics` | Equivalent metrics endpoints; counters are process-local. |
| `GET /monitoring/drift` | Retrieve the latest persisted report, or HTTP 404 when no report exists. |
| `POST /monitoring/drift` | Evaluate and persist a validated sensor batch; this is a write operation. |

The root [README API section](../README.md#fastapi-prediction-service) contains the actual request and response examples, feature constraints, and persistence semantics. The examples there are illustrative API examples; they do not represent live service records.

## System architecture

The application combines an offline training workflow with a separately started API and frontend. Compose packages only the backend. For diagrams and process detail, see [Architecture](ARCHITECTURE.md).

## Local setup and commands

Commands below reflect the current repository files. Run the backend and frontend in separate terminals when using the Python development setup.

### Python backend and training

Use Python 3.12. From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

For training reproduction, obtain the official AI4I CSV and place it at `data/raw/ai4i2020.csv`. The local file is ignored by Git and is not required to run the container when the versioned inference artifacts are present.

```powershell
python -m scripts.train_anomaly
python -m scripts.train_failure
python -m scripts.evaluate
python -m pytest -q
```

Training writes model artifacts and evaluation reports under `models/`, and the drift-reference generator writes to its configured path. Training commands overwrite the versioned output names by default; use a disposable checkout and separate output paths when protecting existing artifacts.

Start the API from the repository root:

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

The API's interactive OpenAPI UI is at `http://127.0.0.1:8000/docs` while the server is running.

### Backend with Docker Compose

The Compose configuration starts the backend API only and persists SQLite under a named volume:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

The API is published as `127.0.0.1:8000:8000` by default: it is reachable only from the Docker host, while container port 8000 remains unchanged. `HOST_IP` can be deliberately overridden to publish on another host interface; do this only behind a trusted network and appropriate security boundary. The API has no authentication or authorization, and binding to an interface does not add either. `HOST_PORT` changes the host port and `APP_PORT` changes the container port. `docker compose down` retains the named volume; deleting a volume permanently removes saved history and drift reports. Do not use destructive volume commands on data you need.

### Render Free deployment settings

The repository can be deployed as two Render services after the required deployment variables are configured:

- **Backend Web Service:** repository root, Docker runtime, `Dockerfile`, Free plan, HTTP health check `/ready`. The Docker command binds `0.0.0.0` and chooses port in this order: `PORT`, `APP_PORT`, then `8000`. Render supplies `PORT` (default `10000`); Compose and standalone Docker continue to use `APP_PORT`/`8000` when `PORT` is absent.
- **Frontend Static Site:** root directory `frontend`, build command `npm ci && npm run build`, publish directory `dist`, and rewrite `/*` to `/index.html` using Rewrite so React Router handles direct navigation and refreshes.
- Set backend `FRONTEND_ORIGIN` to exactly the deployed frontend origin (scheme and host only, no path). CORS allows only that one origin, `GET`/`POST`, and `Accept`/`Content-Type`; credentials are disabled. If unset, no cross-origin browser origin is allowed. Local Vite proxy requests are same-origin and need no CORS configuration.
- Set frontend build-time `VITE_API_BASE_URL` to the backend origin, without `/api`. It is public configuration embedded into the generated JavaScript, not a secret. Do not put a future service URL in source code.

For this Dockerfile, set Render's `PORT=8000` so the listener matches its existing `EXPOSE 8000` declaration. Render's default is `10000`, but its web-service port can be configured; leaving `PORT` at its default is also expected to work when Render detects the bound port. If bypassing the Vite proxy locally, set backend `FRONTEND_ORIGIN=http://127.0.0.1:5173`; the normal same-origin proxy does not need it.

The API does not implement authentication, authorization, rate limiting, or a request-body byte cap. Prediction inputs have bounded sensor values and name lengths, but drift requests permit up to 10,000 observations. CORS does not restrict direct clients. For an anonymous public demo, add modest request/batch limits and rate controls at the API or trusted edge before inviting unrestricted use; no new dependency or such enforcement is included here.

On Render Free the backend's SQLite filesystem is ephemeral, so saved history and drift reports can be lost on restart, redeploy, or idle spin-down. The free instance has 512 MB RAM and 0.1 CPU; expect cold starts and validate memory/latency on the hosted instance. The API is a portfolio demo, not a durable production service.

### Frontend development and tests

In a separate terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Node.js 22.12.0 or newer is required by `frontend/package.json`. Vite serves on `127.0.0.1:5173` and proxies `/api` to the backend on port 8000 by default. The development proxy target can be changed with `API_PROXY_TARGET`; that variable is Vite server configuration, not a browser secret.

```powershell
npm run typecheck
npm test -- --configLoader runner --reporter=dot
npm run build -- --configLoader runner
npm ls --depth=0
npx playwright install chromium
npm run test:e2e -- --workers=1
```

Playwright starts its own Vite server on `127.0.0.1:4175`; that port must be free. E2E tests intercept `/api/*` with controlled fixtures. They do not require or verify the live backend and do not write to a database. The production build creates `frontend/dist`; the repository does not configure a production frontend container or hosting service.

### Accepted verification snapshots

The following are milestone-specific verification snapshots, not a sum of independent test cases. Later snapshots include the then-current broader frontend test suite; counts should not be added across milestones.

| Milestone | Recorded evidence |
| --- | --- |
| M1–M4 backend | 5, 20, 26, and 36 tests at their respective milestones. |
| M5 | Deployment verifier: 13/13 checks; separate clean-checkout training reproduction: 57 tests passed. |
| M6.1–M6.4 frontend | 36, 79, 118, and 128 tests at their respective milestones. |
| M6.5.1–M6.5.3 frontend | 146, 147, and 156 tests across 18 files at their respective verification snapshots. |
| M6.5.4 frontend | 156 Vitest tests and 16 Playwright E2E tests passed; typecheck, build, and clean install were verified. |

M6.5.4 CI uses mocked API responses. It does not establish FastAPI integration, persisted database behavior, real deployment correctness, or complete accessibility conformance. The Python dependency ranges are not fully locked, and model artifact hashes are not guaranteed identical across dependency versions.

## Security and operational limitations

- The application has no authentication or authorization. Treat it as a local demonstration or controlled internal tool, not an unrestricted public service.
- Docker's unprivileged user, read-only root filesystem, dropped capabilities, and `no-new-privileges` setting are baseline hardening, not a security certification. TLS, access control, rate limiting, and deployment-level protections require a separate security architecture.
- Two moderate React Router advisories remain in the pinned 6.x dependency chain. The installed versions are not patched. Source review found fixed internal navigation destinations and validated numeric equipment IDs, with no clear attacker-controlled redirect path in the current UI. The SSR hydration advisory's affected server-rendering path is absent from this client-rendered application. These are exposure assessments, not dependency fixes.
- Operational counters are in memory and process-local; they reset on restart and are not shared between worker processes.
- Drift analysis compares submitted batches with a fixed reference. Drift is not proof of model degradation, and the endpoint returns only the latest saved report.
- The dataset is synthetic. There is no continuous sensor ingestion, temporal forecast, future failure window, or RUL calculation.
- Frontend CI tests mocked API contracts. Live backend and production-hosting verification are separate activities.

## Future work

The following are not implemented capabilities; they are possible future directions requiring appropriate data, validation, and security design:

- Calibrated failure probabilities and calibration evaluation.
- Ingestion of real, permissioned industrial telemetry.
- Temporal failure prediction supported by chronological, machine-linked outcomes.
- Remaining useful life estimation with suitable run-to-failure data.
- Authentication, authorization, rate limiting, and secure public deployment architecture.
- A full-stack production deployment for the frontend and API.
- More extensive alerting, historical drift-report exploration, and ground-truth performance monitoring.

## Interview discussion points

- **Why two models?** Isolation Forest detects distributional unusualness without using the failure target; Random Forest learns a supervised row-level label. Their outputs answer different questions.
- **Why PR-AUC?** Positive failure labels are a small minority. Precision-recall behavior exposes positive-class trade-offs that accuracy can hide.
- **How is leakage controlled?** Failure-mode labels and identifiers are excluded, the split occurs before fitting transformations, and preprocessing is learned on training data only.
- **Why not rely on accuracy?** A model can appear accurate on an imbalanced dataset while missing many positive cases; the reported recall and confusion matrix show that trade-off.
- **Why are scores not interchangeable?** Isolation Forest `score_samples` measures relative anomaly behavior; Random Forest's class-1 estimator output is uncalibrated and tied to a supervised class.
- **How is persistence protected?** The prediction workflow places equipment/readings and prediction output in a database transaction, so a failed write rolls back the associated operation.
- **How do liveness and readiness differ?** `/health` reports process health; `/ready` checks model availability and database connectivity and can return 503 while the process remains alive.
- **How is drift monitored?** A submitted batch is compared with the versioned reference using per-feature KS tests and a categorical TVD rule, then the report is persisted. Retrieval returns the latest report without recalculation.
- **Why equipment-scoped history?** Persisted readings and predictions belong to equipment, and the API exposes history under an equipment ID rather than as a global event feed.
- **What does CI prove?** It verifies frontend behavior against controlled API fixtures. It does not prove the live API, database persistence, or deployment integration.
