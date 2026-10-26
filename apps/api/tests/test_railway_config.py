import json
from pathlib import Path


def test_railway_api_config_properly_expands_port():
    api_dir = Path(__file__).resolve().parent.parent
    config_path = api_dir / "railway.api.json"
    assert config_path.exists(), "railway.api.json must exist in apps/api"

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    start_cmd = data.get("deploy", {}).get("startCommand", "")
    assert "sh -c" in start_cmd, "startCommand must use sh -c to expand shell variables"
    assert "${PORT:-8000}" in start_cmd, "startCommand must expand ${PORT:-8000} with fallback"
    assert start_cmd != "uvicorn app.main:app --host 0.0.0.0 --port $PORT", (
        "startCommand must not use raw unexpanded $PORT without a shell"
    )

    pre_deploy = data.get("deploy", {}).get("preDeployCommand", [])
    assert pre_deploy == ["python -m app.migrations upgrade"], (
        "preDeployCommand must run migrations upgrade before starting API"
    )

    healthcheck = data.get("deploy", {}).get("healthcheckPath")
    assert healthcheck == "/healthz/readiness", "healthcheckPath must point to /healthz/readiness"


def test_dockerfile_uses_dynamic_port_with_fallback():
    api_dir = Path(__file__).resolve().parent.parent
    dockerfile_path = api_dir / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist in apps/api"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert 'CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]' in content, (
        "Dockerfile CMD must use sh -c with ${PORT:-8000}"
    )
