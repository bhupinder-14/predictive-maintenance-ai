Milestone 1: Data Pipeline and Baseline Machine Learning Models
Goal: Build the complete data-processing pipeline, train your first ML models, evaluate them properly, and save the trained model artifacts.
1.1 Dataset selection and understanding
Use the AI4I 2020 Predictive Maintenance Dataset from the UCI Machine Learning Repository as the primary dataset.
- Download and inspect the dataset.
- Understand the meaning of each column, its data type, and its relevance to equipment monitoring.
- Identify the available sensor and operational features, such as air temperature, process temperature, rotational speed, torque, and tool wear.
- Identify the failure labels and their meanings.
- Inspect class imbalance, missing values, duplicate records, and unusual values.
- Document the limitations of the dataset, including that it is synthetic industrial data rather than live factory telemetry.
The application must use the actual dataset schema. Do not invent sensor columns or pretend the dataset contains continuous readings from a live machine.
1.2 Data preprocessing
Create reusable Python functions for:
- Loading the dataset.
- Validating the expected columns and data types.
- Identifying missing values and duplicates.
- Handling invalid or out-of-range values using documented rules.
- Separating input features from target labels.
- Encoding categorical features if required.
- Scaling numeric features when the selected model benefits from scaling.
- Splitting the data into training, validation, and test sets.
Fit imputation, scaling, and other learned preprocessing transformations only on the training data. Apply the same fitted transformations to validation, test, and production inputs.

Because the initial dataset is tabular rather than a continuous time series for each machine, don't create rolling-window features unless you have suitable chronological data.
1.3 Build the anomaly detection model
Implement an Isolation Forest model using scikit-learn.

The model should:
- Learn patterns in the selected reference data.
- Generate anomaly scores for observations.
- Classify observations as normal or anomalous using a documented threshold.
- Compare its results with a simple statistical baseline where practical.
- Save the trained model and preprocessing pipeline.
Evaluate the results using any available ground-truth information carefully. If you use failure labels to evaluate anomalies, explicitly distinguish a detected statistical anomaly from a confirmed equipment failure.
1.4 Build the supervised failure classification model
Use the available failure labels to train a model that classifies failure-related observations.

Start with Logistic Regression as a baseline, then compare it with Random Forest or Gradient Boosting if appropriate.

Evaluate using:
- Precision
- Recall
- F1-score
- PR-AUC
- ROC-AUC, where appropriate
- Confusion matrix
Since failures are rare in the dataset, do not rely on accuracy alone.

Also document the difference between classifying a row associated with a failure label and predicting a future failure within a specified time window. The latter requires a suitable target definition and supporting temporal data.
1.5 Save the model artifacts
Create a consistent artifact-generation process. Save the preprocessing pipeline, trained estimator, model version, feature list, selected threshold, training configuration, and evaluation metrics.

The model should be loadable from a separate inference script without rerunning the training process.
Deliverables
- Dataset ingestion and validation scripts.
- Reusable preprocessing pipeline.
- Isolation Forest anomaly detector.
- Supervised failure classifier.
- Evaluation reports and saved metrics.
- Versioned model artifacts.
- A README explaining the dataset, assumptions, training procedure, and results.
Milestone completion condition: You can run a documented training command from the repository, train both models, evaluate them on held-out data, save the artifacts, and load them again successfully.

### Milestone 1 execution status (verified 2026-10-30)

- [x] Actual UCI AI4I CSV loaded with UTF-8 BOM handling; 10,000 rows and all 14 expected columns.
- [x] Quality checks executed: no missing values, duplicate rows, duplicate UDIs, invalid Type values, or out-of-range sensor values; 339/10,000 rows have `Machine failure=1` (3.39%).
- [x] Cleaning, stratified train/validation/test split, and train-only learned preprocessing executed. Failure target and failure-mode sublabels are not model features.
- [x] Isolation Forest and statistical baseline trained and compared. Test: 103/2,000 flagged, anomaly rate 5.15%, score cutoff −0.585987; failure-label overlap precision 0.1262 and recall 0.1912. A statistical anomaly is not a confirmed failure.
- [x] Logistic Regression baseline and class-weighted Random Forest comparison executed. Random Forest selected by validation F1 at threshold 0.605. Held-out test: precision 0.7955, recall 0.5147, F1 0.6250, PR-AUC 0.7406, ROC-AUC 0.9648; TN=1923, FP=9, FN=33, TP=35.
- [x] Preprocessors, estimators, thresholds, features, metadata, and evaluation JSON saved under `models/`; the evaluation script reloaded both saved bundles and generated the held-out results without retraining.
- [x] Pytest suite executed: 5 passed.

Executed on Python 3.12.14 in the project `.venv`. Commands:

```powershell
python -m scripts.train_anomaly
python -m scripts.train_failure
python -m scripts.evaluate
python -m pytest -q
```

Full metric output is generated at `models/anomaly_v1_evaluation.json` and `models/failure_v1_evaluation.json`. Dataset caveats: AI4I is synthetic, and the available rows do not support chronological future-failure forecasting. The anomaly score is not a probability. Milestone 1 status does not imply completion of Milestones 2–5.

Milestone 2: Build the Prediction API Using FastAPI
Goal: Turn your trained models into a usable service that accepts sensor observations and returns predictions.

At the end of this milestone, another application should be able to send a request to your API and receive a structured prediction without needing access to your training code.
2.1 Set up FastAPI
Create a Python application with a clear separation between:
- API route handlers.
- Request and response schemas.
- Model inference logic.
- Data preprocessing.
- Configuration.
- Error handling.
Keep the model inference code separate from the HTTP layer so it can be tested independently.
2.2 Load the trained models
When the API starts:
- Load the saved anomaly detection model.
- Load the supervised failure model if it has been trained successfully.
- Load the corresponding preprocessing pipeline and model metadata.
- Validate that the artifacts are compatible with the expected feature schema.
- Fail clearly if required artifacts are missing or invalid.
Do not train the model every time a user makes a request.
2.3 Create the API endpoints
Implement the following endpoints:
- GET /health — basic application health.
- GET /ready — verify that required models and the database are available.
- POST /predict/anomaly — detect anomalous operating patterns.
- POST /predict/failure — classify failure risk when the supervised model is available.
Additional endpoints for equipment history and monitoring can be added in later milestones.
2.4 Validate incoming requests
Use Pydantic schemas to validate:
- Required fields.
- Numeric data types.
- Missing or unexpected features.
- Timestamps and identifiers.
- Reasonable value constraints based on the dataset and documented assumptions.
Invalid requests should return meaningful HTTP errors instead of causing the application to crash.

Ensure that the API accepts the same features and ordering expected by the trained model.
2.5 Define a consistent response format
An anomaly response might contain:
- Equipment ID.
- Anomaly score.
- Normal/anomaly classification.
- Model version.
- Prediction timestamp.
- A concise explanation of suspicious feature values.
A supervised failure response might additionally contain a predicted class and an estimated probability if the model supports a meaningful probability estimate.

An anomaly score must not be presented as a probability of equipment failure.
2.6 Add basic API logging
Record the request outcome, prediction ID where available, model version, inference latency, and errors.

Do not log credentials or unnecessarily sensitive information.
Deliverables
- Working FastAPI application.
- Pydantic request and response schemas.
- Model-loading and inference modules.
- Health and readiness endpoints.
- Anomaly and failure prediction endpoints.
- Example API requests and responses.
- Initial API tests and documented startup commands.
Milestone completion condition: You can start the API, open its interactive documentation, submit a valid sensor observation, receive a prediction, and verify that invalid requests are handled safely.

### Milestone 2 implementation status (verified 2026-10-30)

- [x] Modular FastAPI app, routes, Pydantic schemas, artifact registry, compatibility checks, and inference service added under `src/api/`.
- [x] Both existing `anomaly_v1` and `failure_v1` artifact bundles load once during application startup; no training occurs during startup or inference. Missing/incompatible bundles leave `/health` available and make `/ready` report HTTP 503.
- [x] `/health`, `/ready`, `/predict/anomaly`, and `/predict/failure` are implemented and documented in `README.md`.
- [x] Requests require the six trained raw features, reject missing/extra fields, reject invalid types and non-numeric sensor inputs, and enforce documented sensor value ranges.
- [x] Prediction responses include IDs, model versions, UTC timestamps, and inference latency. Anomaly output includes a non-probabilistic score and explanation; failure output includes the row-level class and the estimator probability estimate.
- [x] Tests cover valid requests, invalid/missing fields, invalid types and ranges, model loading and compatibility errors, health/readiness, and Swagger/OpenAPI.
- [x] Initial verification `python -m pytest -q`: 15 passed (five Milestone 1 tests plus ten API tests). The audit identified a NaN error-serialization bug and Starlette's deprecated legacy `httpx` TestClient path; both were corrected and reverified below.
- [x] Live Uvicorn verification: both models loaded; health, readiness, both predictions, `/docs`, and `/openapi.json` returned 200; an invalid request returned 422.

At Milestone 2 acceptance, SQL persistence and history were deferred to Milestone 3; they are now implemented and recorded in the Milestone 3 status below.

### Independent Milestone 2 audit follow-up (2026-10-30)

- [x] Independently exercised both-missing and partial-artifact availability. With only the anomaly bundle present, `/health` returned 200, `/ready` returned 503 with per-model status, the anomaly route returned 200, and the failure route returned 503.
- [x] Compared direct `predict_anomaly` and `predict_failure` outputs against API responses for the same request; anomaly score/class and failure class/probability matched.
- [x] Verified missing fields, extra fields, bad types, invalid Type, empty body, out-of-range readings, NaN, and positive/negative infinity return HTTP 422 without exposing input values or stack traces. A custom 422 handler was added after NaN exposed a serialization failure in the default validation handler.
- [x] Forced an inference exception; API returned sanitized HTTP 500 without internal path or traceback. Incompatible metadata remains unavailable and produces HTTP 503.
- [x] Updated the TestClient dependency from `httpx` to Starlette's recommended `httpx2`. Final verification: `python -m pytest -v` passed 20 tests with no warning; `python -m pip check` reported no broken requirements.
- [x] Verified empty body and JSON requests, NaN, positive/negative infinity, impossible ranges, and extra fields all return safe HTTP 422 responses.
- [x] Verified each partial availability direction: anomaly-only serves anomaly and returns 503 for failure; failure-only serves failure and returns 503 for anomaly. `/ready` reports the loaded-model map in both cases.
- [x] Verified inference exceptions return sanitized HTTP 500, and direct saved-model predictions match API score, class, and probability for identical input.

Milestone 3: SQL Database and Prediction History
Goal: Persist sensor readings, prediction results, equipment information, and monitoring reports so the application maintains a usable history across restarts.

For a simple local implementation, use SQLite. PostgreSQL is a good alternative if you want to demonstrate a more production-oriented database setup.
3.1 Design the database schema
Create four main tables.

A. Equipment

Stores information about monitored equipment.

Suggested fields:
- id
- name
- equipment_type
- location
- created_at
B. Sensor Readings

Stores validated sensor observations.

Suggested fields:
- id
- equipment_id
- timestamp
- Sensor feature columns supported by the dataset.
- source
C. Predictions

Stores the output of each model inference.

Suggested fields:
- id
- equipment_id
- reading_id
- model_version
- anomaly_score
- is_anomaly
- failure_probability, nullable when unavailable.
- latency_ms
- created_at
D. Monitoring Reports

Stores periodic checks on the application's operational health and input data.

Suggested fields:
- id
- model_version
- window_start
- window_end
- drift_metric
- drift_status
- created_at
Add primary keys, foreign keys, constraints, and indexes where appropriate.
3.2 Connect FastAPI to the database
Use SQLAlchemy or another appropriate database-access layer.

Implement reusable functions to:
- Create or retrieve equipment records.
- Store sensor readings.
- Save prediction results.
- Retrieve predictions by ID.
- Retrieve equipment history.
- Save monitoring reports.
Database operations should be handled separately from the API route logic.
3.3 Update the prediction workflow
When the API receives an observation, the workflow should be:
1. Validate the incoming request.
2. Verify or register the equipment record as appropriate.
3. Store the sensor observation.
4. Run the model inference.
5. Store the prediction and associated metadata.
6. Return the prediction response to the client.
Handle database failures deliberately. For example, don't return a success response claiming that a prediction was saved if the database transaction failed.

Consider the implications of storing a reading before inference succeeds, and document how failed inference attempts are handled.
3.4 Implement historical queries
Provide functionality to retrieve:
- The latest readings for a particular machine.
- Predictions within a date range.
- The most frequently flagged equipment.
- The average anomaly score by equipment.
- Prediction counts by model version.
- Average and 95th-percentile inference latency.
Use SQL queries or ORM operations to calculate these values from actual stored records.
3.5 Ensure data persists
Restart the API and verify that previously recorded readings and predictions remain available.

Use database migrations or documented schema initialization so a new developer can recreate the database structure.
Deliverables
- Database schema and initialization or migration scripts.
- Database models and connection configuration.
- Prediction persistence.
- Equipment history and prediction retrieval.
- SQL-based summaries.
- Database error handling.
- Tests verifying that records persist and relationships work correctly.
Milestone completion condition: You can submit a prediction, find its record in the database, retrieve it through the API, restart the application, and retrieve it again.

### Milestone 3 implementation status (verified 2026-10-30)

- [x] Added the four SQLite/SQLAlchemy tables with primary keys, foreign keys, relationships, result/range constraints, and query indexes.
- [x] Added a reusable SQLite engine/session manager with foreign-key enforcement, startup schema creation, and `python -m src.database.init_db` initialization.
- [x] Persisted equipment registration, sensor observations, model output, version and inference latency in a single transaction for both prediction endpoints. Inference or write errors roll back; a failed write returns HTTP 503.
- [x] Added equipment list/history and prediction retrieval endpoints. The history contains raw readings and associated anomaly/failure result fields.
- [x] Added reusable SQL-backed history queries for latest readings, date-range predictions, flagged equipment, average anomaly scores, model-version counts, and average/nearest-rank P95 latency.
- [x] Tests use a separate temporary SQLite database. Verified normal prediction writes, FK relationships, historical queries, simulated write failure rollback, startup and runtime database outage readiness, recovery after outage, and records surviving a fresh application start using the same database file.
- [x] Final suite: **26 passed**. See `verification-report.md` for the exact run and coverage summary.

No drift computation or monitoring endpoint is included; the monitoring table is only a schema for a later milestone. SQLAlchemy `create_all` initializes missing tables and is not a migration system for changing existing schemas.

`/ready` performs a read-only `SELECT 1` through a managed SQLAlchemy connection on each request. The connection is closed after the probe. A failed probe returns sanitized HTTP 503 with `database=false`; when the connection recovers, readiness returns HTTP 200 again. `/health` remains a basic liveness response during database outages.

Milestone 4: Automated Testing, Monitoring, and Data Drift
Goal: Demonstrate that your application is not only capable of generating predictions but also testable, observable, and able to detect signs of changing input data.

This milestone is particularly important because the Tech Mahindra JD explicitly mentions functional testing, debugging, model optimization, and monitoring.
4.1 Write automated tests
Use Pytest and FastAPI TestClient.

Organize tests into several categories.

Data pipeline tests
- Required columns are present.
- Invalid data is rejected or handled according to policy.
- Preprocessing produces the expected feature schema.
- Missing values are treated consistently.
- Test data does not influence fitted preprocessing transformations.
Model tests
- Model artifacts load successfully.
- Predictions have the expected format.
- Scores are finite and valid.
- The inference pipeline uses the correct feature order.
- Thresholds are applied consistently.
API tests
- Valid requests return the expected response schema.
- Missing or malformed fields return appropriate errors.
- Missing model artifacts are handled safely.
- The API does not expose internal stack traces.
- Health and readiness endpoints behave correctly.
Database tests
- Predictions are stored successfully.
- Historical records can be retrieved.
- Foreign-key relationships are valid.
- Database failures do not result in false success responses.
Integration tests

Test the complete flow: submit an observation, generate a prediction, persist the result, and retrieve the record through the API.
4.2 Implement operational monitoring
Measure:
- Total requests.
- Successful requests and failures.
- Input validation errors.
- Inference latency.
- Model-loading failures.
- Database availability.
- Prediction counts by model version.
Record latency in milliseconds and calculate summary statistics over an appropriate time window.

Use a repeatable benchmark procedure for performance testing. Avoid claiming that the system supports a particular number of users or requests per second without testing it.
4.3 Implement data drift detection
Create a monitoring process that compares recent input observations with a documented reference dataset.

For example:
- Use a Kolmogorov–Smirnov test for suitable continuous features.
- Alternatively, use Population Stability Index (PSI) with documented binning and thresholds.
- Report which features changed.
- Save the monitoring window, method, metric, and status in the database.
- Expose the latest report through GET /monitoring/drift.
Use controlled synthetic data to test whether the monitoring process can detect a distribution shift.

Explain the limitations of the selected method, including sensitivity to sample size and the fact that drift does not automatically mean model accuracy has deteriorated.
4.4 Monitor model quality when outcomes are available
If actual failure outcomes become available later, compare predictions with those outcomes and calculate the relevant classification metrics.

Do not report live model accuracy based only on incoming predictions when their ground-truth outcomes are unknown.
4.5 Test error and recovery scenarios
Test cases such as:
- Database temporarily unavailable.
- Invalid sensor observations.
- Missing model artifact.
- Incorrect feature schema.
- Drift detected in a recent data window.
- Restarting the API after predictions have been stored.
Document expected behavior and the observed result for each scenario.
Deliverables
- Automated unit tests.
- API and integration tests.
- A repeatable latency benchmark.
- Operational metrics and error logging.
- Data drift detection.
- Persisted monitoring reports.
- A documented test report and known limitations.
Milestone completion condition: The automated tests pass, the application handles documented failure cases safely, and a controlled change in input-data distribution produces an observable drift report.

### Milestone 4 implementation status (awaiting independent acceptance audit)

- [x] Expanded data-pipeline, saved-artifact, deterministic inference, API, database, and operational-monitoring tests without removing earlier coverage.
- [x] Added thread-safe process-local cumulative and rolling-window request/status/latency counters and separate anomaly/failure prediction outcome and error metrics.
- [x] Added `GET /metrics/summary` and retained `GET /monitoring/metrics` as an equivalent backward-compatible alias.
- [x] Exposed actual prediction counts by model family and loaded model version, sanitized model load/availability state, and live database availability.
- [x] Defined rolling summaries as the trailing configurable `METRICS_WINDOW_SECONDS` (default 300 seconds); cumulative-since-start counters remain separately identified.
- [x] Added `scripts/benchmark_api.py` with independent anomaly/failure samples, configurable warm-ups and sample count, and p50/p95/p99/mean/max output. The temporary local run and actual measurements are in `verification-report.md`.
- [x] Generated `data/reference/drift_reference_v1.json` from the actual AI4I training partition only (7,000 rows, seed 42); no validation/test rows, IDs, or targets are drift features.
- [x] Added sensor-only batch validation and `POST /monitoring/drift`: numeric KS tests (`p < 0.05`), Type total-variation distance (`>= 0.10`), and an insufficient-data response below 20 rows.
- [x] Persisted complete valid drift reports and added `GET /monitoring/drift` to retrieve the latest report without recalculation; empty history returns 404 and database failures return sanitized 503.
- [x] Added an idempotent additive SQLite upgrade for existing `monitoring_reports` tables; it preserves existing records and adds report metadata, methodology, batch description, and feature-result JSON columns.
- [x] Tests exercised similar, numerical-shifted, and categorical-shifted batches, small/invalid batches, missing/incompatible reference artifacts, metrics counters, and concurrent counter updates.
- [x] Added tests for report persistence/restart/latest ordering, legacy SQLite upgrade, write failure rollback behavior, no-report behavior, metrics aliases/version/availability/window summaries, and benchmark CLI/percentiles/warm-up/error handling.
- [x] Full test suite: **48 passed**. `pip check`: no broken requirements. `git diff --check`: no errors.
- [ ] Independent Milestone 4 acceptance audit (pending; do not begin Milestone 5).

Drift request batches are not persisted; completed reports are. No Docker, deployment, dashboard, or Milestone 5 work is included.

Milestone 5: Docker, Deployment, and Documentation
Goal: Make the project reproducible on another machine, without relying on undocumented local files, manual setup tricks, or your development environment.
5.1 Containerize the application
Create a Dockerfile that:
- Uses an appropriate Python base image.
- Installs the required dependencies.
- Copies the application code.
- Configures the working directory.
- Starts the FastAPI application using a documented command.
- Exposes the intended application port.
Avoid copying local credentials, virtual environments, raw private datasets, or unnecessary files into the image.
5.2 Create Docker Compose configuration
Use compose.yaml to simplify local startup.

For a SQLite setup, the application container can use a mounted volume for persistent database storage.

If you choose PostgreSQL, define a database service, environment variables, persistent storage, and appropriate readiness checks.

Ensure that the application handles startup ordering and database readiness correctly.
5.3 Manage configuration safely
Create a .env.example containing placeholders for configuration such as:
- Database connection URL.
- Application environment.
- Model artifact paths.
- Logging level.
- Monitoring thresholds.
Keep real secrets in local environment configuration and exclude them from Git.
5.4 Verify a clean setup
Follow your own README from a clean checkout.

Confirm that a new developer can:
1. Install dependencies or build the Docker image.
2. Obtain the required dataset.
3. Train the models.
4. Generate model artifacts.
5. Start the API.
6. Submit a test prediction.
7. Verify that the result is persisted.
8. Run the automated tests.
9. Access health and readiness endpoints.
Do not assume model artifacts will magically exist after cloning the repository. Document exactly how to generate them, or provide appropriately sized, reproducibly generated artifacts if practical.
5.5 Deploy the application if feasible
Local Docker execution is the minimum target. You can additionally deploy the service to a suitable cloud or hosting platform if you have the time and resources.

If you deploy it:
- Document the deployment environment.
- Configure environment variables safely.
- Verify the public health endpoint.
- Test the deployed prediction endpoint.
- Document any cost, availability, or resource limitations.
A deployed URL is useful for demonstrations, but don't sacrifice correctness or expose sensitive data just to have a public endpoint.
5.6 Write the README
The README should explain:
- Project objective and use cases.
- Architecture and data flow.
- Dataset source and limitations.
- Technology stack.
- Installation and configuration.
- Model training and evaluation.
- API endpoints and example requests.
- Database schema and persistence.
- Monitoring and drift detection.
- Testing commands and actual test results.
- Docker setup.
- Model metrics and limitations.
- Future improvements.
Deliverables
- Dockerfile.
- Docker Compose configuration.
- .env.example.
- .gitignore.
- Reproducible setup and training commands.
- Complete README.
- Successful clean-start verification.
- Optional deployment and documented access instructions.
Milestone completion condition: Another person can clone the repository, follow the documentation, train the models, start the application, make a prediction, and run the tests without needing undocumented assistance.

Milestone 6: Optional Dashboard and Final Portfolio Polish
Goal: Build a user-friendly demonstration layer on top of the working backend and prepare the repository for placement interviews.

This milestone should begin only after the model pipeline, API, database, tests, and Docker setup work reliably.
6.1 Create an equipment overview dashboard
Build a simple dashboard using Streamlit or a frontend framework you already know.

The overview should show:
- Number of registered machines.
- Latest recorded sensor readings.
- Total anomaly detections.
- Recent alerts.
- Last recorded reading for each machine.
- API or database health status, where available.
All values should come from the backend and database. Do not hardcode dashboard statistics.
6.2 Create an anomaly investigation view
Allow a user to:
- Select equipment.
- Filter by time range.
- View historical sensor readings.
- See detected anomalies and their scores.
- Read the explanation of suspicious features.
- Open the relevant prediction record.
Use charts to display sensor behavior over time if actual timestamped readings are available.

If the dataset doesn't support real chronological sensor histories, clearly label any simulated timeline as synthetic rather than presenting it as real equipment telemetry.
6.3 Display model evaluation
Include a model evaluation section that displays actual saved evaluation results:
- Precision, recall and F1-score.
- PR-AUC or ROC-AUC where appropriate.
- Confusion matrix.
- Model version.
- Evaluation dataset and date.
- Important limitations.
Do not display a single "AI accuracy" figure that combines anomaly detection and failure classification, since these are distinct tasks.
6.4 Add monitoring views
Display:
- Inference latency over time.
- Request and error counts.
- Recent data-drift reports.
- Features flagged by drift monitoring.
- Model versions associated with predictions.
The dashboard should distinguish an operational warning, a detected input-distribution shift, an anomalous observation, and a supervised failure prediction.
6.5 Polish the repository for interviews
Before declaring the project complete:
- Remove unused code and dead files.
- Verify that the GitHub repository contains the final working implementation.
- Add an architecture diagram and a clear README.
- Include sample API requests and responses.
- Document model evaluation honestly.
- Ensure setup instructions work from a clean checkout.
- Add a short demo video or screenshots if useful.
- Prepare to explain the main technical decisions and limitations.
6.6 Prepare an interview demonstration
A good demonstration should take the interviewer through a complete flow:
1. Show the selected dataset and preprocessing pipeline.
2. Explain the model selection and held-out evaluation.
3. Start the API and show its documentation.
4. Submit a valid observation.
5. Show the returned prediction.
6. Retrieve the persisted prediction from the database.
7. Demonstrate an invalid input and the error response.
8. Show a drift report generated from a controlled test.
9. Explain how the application is packaged and run with Docker.
Deliverables
- Working dashboard connected to the actual backend.
- Equipment and anomaly views.
- Model evaluation view.
- Monitoring and drift views.
- Updated README and architecture diagram.
- Final test and setup verification.
- A concise project demonstration suitable for a technical interview.
Milestone completion condition: You can demonstrate the complete workflow end to end and explain the data, ML, API, database, testing, deployment, and monitoring decisions behind it.

Final order of execution
Milestone	Main outcome
1	Reproducible ML models and evaluation
2	Working prediction API
3	Persistent SQL storage and history
4	Automated testing and monitoring
5	Dockerized, documented application
6	Optional dashboard and interview-ready demonstration

The most important rule: don't move to the next milestone merely because the AI has generated code. Move on when the current milestone's acceptance conditions have actually been verified. That is how you'll end up with a project you can confidently put on your resume and defend in a Tech Mahindra AI Engineer interview.
