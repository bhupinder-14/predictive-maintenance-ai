# Predictive Maintenance & Anomaly Detection AI

Milestone 1 is implemented: the repository validates the actual AI4I 2020 CSV, trains separate anomaly-detection and row-level failure-classification pipelines, evaluates held-out data, saves versioned artifacts, and reloads those artifacts for evaluation.

Milestones 2–5 (API, persistence, monitoring, deployment) remain future work. This README documents the implemented Milestone 1 workflow only.

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

## Current scope and limitations

- Implemented: local CSV ingestion and validation, leakage-aware preprocessing/splitting, Isolation Forest with score cutoff and statistical comparison, Logistic Regression baseline, Random Forest comparison, class-imbalance weighting, held-out evaluation, metadata/artifact persistence, artifact reload, and Milestone 1 tests.
- Not implemented yet: FastAPI endpoints, SQL persistence, operational/data-drift monitoring, Docker deployment, or dashboard. These belong to later milestones.
- No time-series forecasting or calibrated failure probability is claimed. Random Forest `predict_proba` is an estimator score and has not been separately calibrated.
- Dataset values are synthetic and may not represent actual sensor distributions, failure prevalence, or operational costs.
