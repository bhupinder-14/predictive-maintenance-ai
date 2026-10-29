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

Artifact files are git-ignored as model outputs; rerun the training commands to regenerate them. Dataset and model limitations are documented in `README.md` and `CHECKLIST.md`. This report verifies Milestone 1 only; it makes no completion claim for later milestones.
