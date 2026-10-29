# Predictive Maintenance & Anomaly Detection AI

> End-to-end AI application that monitors industrial equipment sensor data,
> detects anomalous operating patterns, and predicts equipment failure.

## Status

🚧 **Under construction** – repository skeleton created; application code is
not yet implemented.

## Dataset

[AI4I 2020 Predictive Maintenance Dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
from the UCI Machine Learning Repository.

Place the downloaded CSV in `data/raw/` before running the training pipeline.

## Technology Stack

| Layer            | Technology                     |
| ---------------- | ------------------------------ |
| Language         | Python                         |
| ML               | scikit-learn, Pandas, NumPy    |
| API              | FastAPI, Pydantic, Uvicorn     |
| Database         | SQLite via SQLAlchemy          |
| Testing          | Pytest, HTTPX / TestClient     |
| Containerisation | Docker, Docker Compose         |

## Project Structure

```
predictive-maintenance-ai/
├── data/
│   ├── raw/              # Original, unmodified dataset
│   └── processed/        # Cleaned / transformed data
├── models/               # Trained model artifacts
├── scripts/              # Training, evaluation & utility scripts
├── src/                  # Application source code
├── tests/                # Automated tests
├── .env.example          # Environment variable placeholders
├── .gitignore
├── requirements.txt
└── README.md
```

## Quick Start

> Detailed instructions will be added as each milestone is completed.

```bash
# 1. Clone the repository
git clone <repo-url> && cd predictive-maintenance-ai

# 2. Create a virtual environment
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment config
cp .env.example .env

# 5. (TODO) Download dataset, train models, start API …
```

## Milestones

- [ ] **Milestone 1** – Data pipeline & baseline ML models
- [ ] **Milestone 2** – FastAPI prediction service
- [ ] **Milestone 3** – SQL database & prediction history
- [ ] **Milestone 4** – Automated testing, monitoring & data drift
- [ ] **Milestone 5** – Docker, deployment & documentation
- [ ] ~~Milestone 6 – Dashboard~~ *(skipped)*

## License

This project is for educational and portfolio purposes.
