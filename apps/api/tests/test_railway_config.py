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
    command = json.loads(next(line[4:] for line in content.splitlines() if line.startswith("CMD ")))
    assert command[:2] == ["sh", "-c"]
    assert "${PORT:-8000}" in command[2]
    assert '--forwarded-allow-ips "${STRAZ_TRUSTED_PROXY_IPS:-}"' in command[2]
    assert "--proxy-headers" in command[2]
    assert "--no-server-header" in command[2]


def test_start_commands_preserve_proxy_allowlist_argument(tmp_path):
    import os
    import shlex
    import subprocess

    api_dir = Path(__file__).resolve().parent.parent
    binary = tmp_path / "uvicorn"
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    binary.chmod(0o700)
    config = json.loads((api_dir / "railway.api.json").read_text())
    docker = json.loads(next(line[4:] for line in (api_dir / "Dockerfile").read_text().splitlines() if line.startswith("CMD ")))
    for trust in ("", "192.0.2.10,192.0.2.11"):
        env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
               "PORT": "8123", "STRAZ_TRUSTED_PROXY_IPS": trust}
        for command in (docker, shlex.split(config["deploy"]["startCommand"])):
            result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
            args = result.stdout.splitlines()
            assert args[args.index("--port") + 1] == "8123"
            assert args[args.index("--forwarded-allow-ips") + 1] == trust
            assert "--proxy-headers" in args
