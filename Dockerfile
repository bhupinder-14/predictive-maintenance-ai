FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_PORT=8000 \
    DATABASE_URL=sqlite:////var/lib/predictive-maintenance/predictive_maintenance.db \
    MODEL_DIR=/app/models \
    DRIFT_REFERENCE_PATH=/app/data/reference/drift_reference_v1.json

WORKDIR /app

# Install only the runtime dependency set before copying frequently changed code.
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

# The API reads existing artifacts; it does not train or regenerate them.
COPY src/ ./src/
RUN mkdir -p ./models
COPY models/anomaly_v1_preprocessor.joblib \
     models/anomaly_v1_estimator.joblib \
     models/anomaly_v1_metadata.json \
     models/failure_v1_preprocessor.joblib \
     models/failure_v1_estimator.joblib \
     models/failure_v1_metadata.json \
     ./models/
COPY data/reference/drift_reference_v1.json ./data/reference/drift_reference_v1.json
COPY scripts/benchmark_api.py scripts/verify_deployment.py ./scripts/

# A dedicated unprivileged UID owns only the persistent data directory.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /var/lib/predictive-maintenance \
    && chown 10001:10001 /var/lib/predictive-maintenance

USER 10001:10001

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port \"${APP_PORT:-8000}\""]
