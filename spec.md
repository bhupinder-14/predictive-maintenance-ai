# Project Specification: Predictive Maintenance & Anomaly Detection AI

## 1. Project Objective

Build a complete, reproducible, end-to-end AI engineering application that monitors industrial equipment sensor data, detects anomalous operating patterns, and predicts equipment failure when appropriate labeled data is available.

The project is intended to demonstrate practical competence in Python, Pandas, NumPy, scikit-learn, machine learning, data preprocessing, feature engineering, REST APIs, SQL, Docker, automated testing, model evaluation, monitoring, and production-oriented software engineering.

This must be a working application, not just a Jupyter Notebook, a static dashboard, or a collection of disconnected scripts.

Prioritize correctness, reliability, reproducibility, clear architecture, and demonstrable functionality over unnecessary complexity.

## 2. Required Technology Stack

- Python
- Pandas and NumPy
- scikit-learn
- FastAPI and Pydantic
- SQL database: SQLite for a simple local setup or PostgreSQL for a more production-like implementation
- SQLAlchemy or an equivalent database access layer
- Pytest and FastAPI TestClient
- Docker and Docker Compose
- Git and GitHub

Optional technologies such as Streamlit, React, SHAP, MLflow, or a cloud hosting provider may be added only if they improve the project without unnecessarily complicating it.

Do not add technologies simply to increase the number of keywords in the README.

## 3. Dataset and Data Ingestion

Use the public AI4I 2020 Predictive Maintenance Dataset from the UCI Machine Learning Repository as the initial dataset for supervised failure prediction.

Document the dataset source, its schema, feature meanings, target labels, limitations, and any preprocessing assumptions.

The ingestion pipeline must:

- Load the source dataset from a documented local path.
- Validate required columns and data types.
- Identify missing values, duplicate records, invalid numeric values, and unexpected feature ranges.
- Report data-quality issues clearly.
- Apply documented cleaning rules without silently changing the meaning of the data.
- Separate raw data from processed data.
- Ensure the training process can be reproduced.

If the dataset cannot be downloaded automatically, explain where the user must obtain it and how to place it locally. Do not silently substitute fabricated data.

Synthetic data may be generated separately for API testing, edge cases, or controlled anomaly demonstrations. Label it clearly as synthetic.

## 4. Machine Learning Component A: Anomaly Detection

Implement an anomaly-detection pipeline using scikit-learn Isolation Forest.

Requirements:

- Select relevant numeric features based on the actual dataset.
- Implement appropriate preprocessing.
- Fit the model on a documented reference dataset.
- Explain the meaning and limitations of the model's anomaly score.
- Define and document the decision threshold.
- Compare results against a simple statistical baseline where useful.
- Save the trained model and its preprocessing pipeline.
- Record the model version, training configuration, and evaluation details.
- Provide an inference function that accepts validated feature data and returns an anomaly score and normal/anomaly classification.
- Provide a clear explanation of suspicious feature values using a transparent method.

Do not interpret the Isolation Forest score as a calibrated failure probability.

If the dataset does not contain genuine time-series sequences for each machine, do not claim to have implemented rolling-window or temporal anomaly detection using nonexistent history.

## 5. Machine Learning Component B: Failure Prediction

Implement a supervised failure-classification pipeline using the actual available failure labels.

Begin with Logistic Regression as a baseline and compare it with a suitable tree-based model, such as Random Forest or Gradient Boosting, if appropriate.

Requirements:

- Define the prediction target precisely.
- Inspect the label distribution and potential class imbalance.
- Split the dataset before fitting preprocessing transformations.
- Use stratified splits for suitable independent tabular data.
- Use chronological or group-aware splits if the data structure and prediction objective require them.
- Prevent data leakage, including leakage through derived features and target-related columns.
- Evaluate the model on held-out data.
- Report precision, recall, F1-score, PR-AUC, ROC-AUC where appropriate, and a confusion matrix.
- Record the baseline results and compare candidate models fairly.
- Select a decision threshold based on documented validation criteria.
- Save the selected model and preprocessing pipeline.
- Implement a prediction function that returns the predicted class and a probability only when the model supports a meaningful probability estimate.

Do not claim that the model predicts failures within a future time window unless the dataset supports that target definition.

If the available data only supports row-level failure classification, describe the model accurately as failure classification rather than future failure forecasting.

## 6. Reproducible Model Training and Evaluation

Create independent scripts or modules for:

- Data ingestion and validation
- Feature engineering
- Anomaly model training
- Failure model training
- Model evaluation
- Model artifact loading and validation

Each training run should record:

- Dataset source or version
- Selected features
- Preprocessing configuration
- Model parameters
- Random seed where applicable
- Training timestamp
- Validation and test metrics
- Selected threshold
- Model version

Bundle preprocessing and model inference into a consistent pipeline where appropriate.

The deployed API must load saved model artifacts during startup. It must not retrain models for every prediction request.

Provide clear commands for training and evaluating models from a clean checkout.

## 7. FastAPI Application

Implement a well-structured FastAPI service.

Required endpoints:

- GET /health — basic application health
- GET /ready — verify that required models and database connections are ready
- POST /predict/anomaly — detect abnormal operating behavior
- POST /predict/failure — classify failure risk when the supervised model is available
- GET /equipment — list known equipment
- GET /equipment/{equipment_id}/history — retrieve historical readings and predictions
- GET /predictions/{prediction_id} — retrieve a prediction record
- GET /metrics/summary — retrieve operational metrics and prediction summaries
- GET /monitoring/drift — retrieve the latest available data-drift report

Use Pydantic request and response schemas.

Requirements:

- Validate required fields, numeric types, feature names, timestamps, and reasonable value constraints.
- Return appropriate HTTP status codes and informative validation errors.
- Handle missing model artifacts and database failures safely.
- Load model artifacts once during startup.
- Keep model inference logic separate from HTTP route handlers.
- Record request latency, model version, prediction timestamp, and prediction ID.
- Avoid exposing stack traces, secrets, or sensitive information in API responses.
- Generate interactive API documentation through FastAPI's OpenAPI support.

The input schema must match the actual trained model features. Do not invent sensor fields that are absent from the chosen dataset.

## 8. SQL Database

Implement a relational database with appropriate primary keys, foreign keys, constraints, and indexes.

Include tables for:

1. Equipment metadata
2. Sensor readings
3. Prediction records
4. Monitoring reports

Prediction records should include the relevant equipment ID, input record reference where applicable, model version, anomaly score, anomaly decision, optional failure probability, inference latency, and creation timestamp.

Allow failure probability to be NULL when the supervised failure model is unavailable.

Persist prediction records and monitoring results across application restarts.

Provide migrations or documented schema initialization, safe database access, and useful SQL queries for historical analysis.

## 9. Monitoring and Data Drift

Implement monitoring for:

- Request count and error count
- Inference latency
- Model and database readiness
- Input validation failures
- Input feature distribution changes
- Model performance when ground-truth labels become available

For data drift, compare recent input data with a documented reference dataset using an appropriate statistical method.

Document the chosen drift metric, feature selection, sample-size limitations, and alert threshold.

Store drift reports in the database and expose them through the monitoring endpoint.

Do not claim that data drift proves model degradation. Do not claim to measure current model accuracy without appropriate ground-truth outcomes.

Do not automatically retrain and replace the deployed model without validation and a documented promotion procedure.

## 10. Automated Testing

Use Pytest and FastAPI TestClient.

Include tests for:

- Dataset schema validation
- Missing and invalid feature values
- Preprocessing consistency
- Model artifact loading
- Valid anomaly predictions
- Valid failure predictions
- API response schemas and status codes
- Database persistence and relationships
- Missing model artifacts
- Database failure handling
- Monitoring calculations
- Drift detection under controlled distribution changes

Include integration tests for the complete flow: submit sensor data, generate a prediction, store the result, and retrieve it through the API.

Use synthetic fixtures for edge cases without misrepresenting them as real industrial observations.

Provide a documented command to run the entire test suite.

## 11. Docker and Deployment

Create a Dockerfile and Docker Compose configuration.

The application should:

- Start from a documented setup procedure.
- Load configuration through environment variables.
- Keep credentials out of source control.
- Persist database data when required.
- Load previously trained model artifacts.
- Expose the FastAPI service on a documented port.
- Provide health checks where practical.
- Shut down cleanly.
- Return useful errors when required resources are unavailable.

Include a .env.example file containing placeholders only.

Do not require a cloud account merely to run the local version.

## 12. Optional Dashboard

If time permits, implement a lightweight dashboard showing:

- Equipment overview
- Latest sensor readings
- Anomaly alerts
- Anomaly scores and explanations
- Historical prediction records
- Held-out model evaluation metrics
- API latency and error summaries
- Data-drift reports

The dashboard must retrieve actual information from the backend. Do not use hardcoded values to simulate a working application.

Keep the dashboard secondary to the ML pipeline, API, database, testing, and monitoring.

## 13. Code Quality and Repository Structure

Use modular, readable Python code with appropriate type hints, docstrings, configuration management, logging, and error handling.

Separate data processing, training, inference, API routes, database access, and monitoring.

Include:

- requirements.txt or an equivalent dependency specification
- Dockerfile
- compose.yaml
- .env.example
- .gitignore
- README.md
- Automated tests
- Training and evaluation scripts

The README must explain the architecture, dataset, installation, training procedure, API usage, model evaluation, database setup, monitoring, testing, Docker execution, limitations, and known issues.

Document any optional features that have not been implemented.

## 14. Acceptance Criteria

The project is complete only when:

1. A new user can follow the README to configure the environment.
2. The dataset can be loaded and validated using documented commands.
3. Both model pipelines can be trained reproducibly from the available data.
4. Held-out evaluation results are generated and saved.
5. The FastAPI application loads trained artifacts and serves predictions.
6. API requests generate persistent database records.
7. Invalid requests are rejected safely.
8. Automated unit and integration tests run successfully.
9. Docker can start the application using documented commands.
10. Health and readiness endpoints behave correctly.
11. Drift monitoring can be demonstrated using controlled test data.
12. The repository does not depend on undocumented local files or credentials.
13. The README accurately distinguishes implemented features from future enhancements.

At completion, provide a summary of the implemented architecture, files created, commands to install and run the project, training commands, test results, evaluation metrics, known limitations, and any remaining manual setup.

Never invent model metrics, test results, deployment status, or implemented functionality. If a requirement cannot be completed, explain the reason and provide the next actionable step.