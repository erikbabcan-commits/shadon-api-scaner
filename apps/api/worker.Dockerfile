# ARQ worker image. Build context: apps/api (same as Dockerfile).
# External CLI scanners (nuclei, httpx, naabu, trivy, gitleaks, ...) are
# deliberately NOT installed: those profiles are blocked until enforced
# network isolation exists (see docs/SECURITY_REVIEW_2026-10-26.md, H13).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONPATH=/app

RUN useradd -u 10001 -m -d /home/straz -s /usr/sbin/nologin straz && \
    chown -R straz:straz /app
USER straz

CMD ["arq", "app.worker.WorkerSettings"]
