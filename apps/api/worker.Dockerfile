# ARQ worker image. Build context: apps/api (same as Dockerfile).
# External CLI scanners (nuclei, httpx, naabu, trivy, gitleaks, ...) are
# deliberately NOT installed: those profiles are blocked until enforced
# network isolation exists (see docs/SECURITY_REVIEW_2026-10-26.md, H13).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

RUN useradd -u 10001 -m -d /home/straz -s /usr/sbin/nologin straz && \
    chown -R straz:straz /app
USER straz

CMD ["arq", "app.worker.WorkerSettings"]
