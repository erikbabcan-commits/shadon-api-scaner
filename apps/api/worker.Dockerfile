FROM python:3.12-slim

WORKDIR /app

ARG HTTPX_VERSION=1.6.10
ARG TLSX_VERSION=1.1.9
ARG NUCLEI_VERSION=3.3.7

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# Install ProjectDiscovery binaries AFTER pip so Python's httpx CLI does not overwrite them.
# Prefer /opt/pd/bin on PATH ahead of /usr/local/bin.
RUN set -eux; \
    mkdir -p /opt/pd/bin; \
    curl -fsSL "https://github.com/projectdiscovery/httpx/releases/download/v${HTTPX_VERSION}/httpx_${HTTPX_VERSION}_linux_amd64.zip" -o /tmp/httpx.zip; \
    curl -fsSL "https://github.com/projectdiscovery/tlsx/releases/download/v${TLSX_VERSION}/tlsx_${TLSX_VERSION}_linux_amd64.zip" -o /tmp/tlsx.zip; \
    curl -fsSL "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" -o /tmp/nuclei.zip; \
    unzip -oj /tmp/httpx.zip httpx -d /opt/pd/bin; \
    unzip -oj /tmp/tlsx.zip tlsx -d /opt/pd/bin; \
    unzip -oj /tmp/nuclei.zip nuclei -d /opt/pd/bin; \
    chmod +x /opt/pd/bin/httpx /opt/pd/bin/tlsx /opt/pd/bin/nuclei; \
    rm -f /tmp/*.zip

ENV PATH="/opt/pd/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN nuclei -update-templates || true

CMD ["arq", "app.worker.WorkerSettings"]
