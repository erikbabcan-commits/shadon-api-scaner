FROM python:3.12-slim

WORKDIR /app

ARG HTTPX_VERSION=1.6.10
ARG TLSX_VERSION=1.1.9
ARG NUCLEI_VERSION=3.3.7
ARG SUBFINDER_VERSION=2.16.0
ARG NAABU_VERSION=2.6.1
ARG TRIVY_VERSION=0.74.0
ARG GITLEAKS_VERSION=8.30.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# ProjectDiscovery + supply-chain binaries AFTER pip (avoid Python httpx CLI collision).
RUN set -eux; \
    mkdir -p /opt/pd/bin /opt/scanners/bin; \
    curl -fsSL "https://github.com/projectdiscovery/httpx/releases/download/v${HTTPX_VERSION}/httpx_${HTTPX_VERSION}_linux_amd64.zip" -o /tmp/httpx.zip; \
    curl -fsSL "https://github.com/projectdiscovery/tlsx/releases/download/v${TLSX_VERSION}/tlsx_${TLSX_VERSION}_linux_amd64.zip" -o /tmp/tlsx.zip; \
    curl -fsSL "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" -o /tmp/nuclei.zip; \
    curl -fsSL "https://github.com/projectdiscovery/subfinder/releases/download/v${SUBFINDER_VERSION}/subfinder_${SUBFINDER_VERSION}_linux_amd64.zip" -o /tmp/subfinder.zip; \
    curl -fsSL "https://github.com/projectdiscovery/naabu/releases/download/v${NAABU_VERSION}/naabu_${NAABU_VERSION}_linux_amd64.zip" -o /tmp/naabu.zip; \
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" -o /tmp/trivy.tgz; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" -o /tmp/gitleaks.tgz; \
    unzip -oj /tmp/httpx.zip httpx -d /opt/pd/bin; \
    unzip -oj /tmp/tlsx.zip tlsx -d /opt/pd/bin; \
    unzip -oj /tmp/nuclei.zip nuclei -d /opt/pd/bin; \
    unzip -oj /tmp/subfinder.zip subfinder -d /opt/pd/bin; \
    unzip -oj /tmp/naabu.zip naabu -d /opt/pd/bin; \
    tar -xzf /tmp/trivy.tgz -C /opt/scanners/bin trivy; \
    tar -xzf /tmp/gitleaks.tgz -C /opt/scanners/bin gitleaks; \
    chmod +x /opt/pd/bin/* /opt/scanners/bin/*; \
    rm -f /tmp/*.zip /tmp/*.tgz

ENV PATH="/opt/pd/bin:/opt/scanners/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN nuclei -update-templates || true

CMD ["arq", "app.worker.WorkerSettings"]
