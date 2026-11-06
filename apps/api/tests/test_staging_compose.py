"""Staging must not inherit a production target from the operator's shell."""
import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("staging_compose", ROOT / "deploy/staging.py")
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


def local_config():
    password = uuid.uuid4().hex
    environment = {
        "DATABASE_URL": f"postgresql+asyncpg://local:{quote(password, safe='')}@postgres:5432/local",
        "REDIS_URL": "redis://redis:6379/0", "STRAZ_ENV": "staging",
    }
    return {"services": {
        "postgres": {"environment": {"POSTGRES_USER": "local", "POSTGRES_DB": "local", "POSTGRES_PASSWORD": password}},
        "api": {"environment": environment}, "worker": {"environment": dict(environment)},
    }}


@pytest.mark.parametrize("target", [
    "postgresql+asyncpg://user:fixture@production.example.invalid:5432/live",
    "postgresql+asyncpg://user:fixture@postgres:5432/wrong",
    "postgresql+asyncpg://user:fixture@postgres:5432/local?host=production.example.invalid",
])
def test_remote_or_mismatched_database_rejected_before_up(monkeypatch, tmp_path, target):
    config = local_config()
    config["services"]["worker"]["environment"]["DATABASE_URL"] = target
    calls = []
    import json
    (tmp_path / "deploy").mkdir()
    shutil.copyfile(ROOT / "deploy/.env.example", tmp_path / "deploy/.env.example")

    def render(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, json.dumps(config))

    monkeypatch.setattr(staging.subprocess, "run", render)
    with pytest.raises(ValueError, match="own postgres service"):
        staging.run("up", root=tmp_path, command=["fixture-compose"])
    assert len(calls) == 1 and "config" in calls[0] and "up" not in calls[0]


def test_remote_redis_and_wrong_mode_are_rejected():
    config = local_config()
    staging.validate_targets(config)
    wrong = copy.deepcopy(config)
    wrong["services"]["api"]["environment"]["REDIS_URL"] = "redis://production.example.invalid:6379/0"
    with pytest.raises(ValueError, match="own redis service"):
        staging.validate_targets(wrong)
    wrong = copy.deepcopy(config)
    wrong["services"]["worker"]["environment"]["STRAZ_ENV"] = "production"
    with pytest.raises(ValueError, match="Staging environment"):
        staging.validate_targets(wrong)


@pytest.mark.parametrize("migration_fails", [False, True])
def test_apps_start_only_after_quiesced_successful_migration(monkeypatch, tmp_path, migration_fails):
    import json
    (tmp_path / "deploy").mkdir()
    shutil.copyfile(ROOT / "deploy/.env.example", tmp_path / "deploy/.env.example")
    state = {"apps_running": True, "database_ready": False, "migrated": False}

    def compose(arguments, **kwargs):
        if "config" in arguments:
            return subprocess.CompletedProcess(arguments, 0, json.dumps(local_config()))
        if "stop" in arguments:
            state["apps_running"] = False
        elif "run" in arguments:
            assert state["database_ready"] and not state["apps_running"]
            if migration_fails:
                raise subprocess.CalledProcessError(1, arguments, stderr="private failure")
            state["migrated"] = True
        elif "up" in arguments:
            if arguments[-2:] == ["postgres", "redis"]:
                state["database_ready"] = True
            else:
                assert state["migrated"], "API and worker must never start against an unmigrated database"
                state["apps_running"] = True
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(staging.subprocess, "run", compose)
    if migration_fails:
        with pytest.raises(subprocess.CalledProcessError):
            staging.run("up", root=tmp_path, command=["fixture-compose"])
        assert not state["apps_running"] and not state["migrated"]
    else:
        assert staging.run("up", root=tmp_path, command=["fixture-compose"]) == 0
        assert state["apps_running"] and state["migrated"]


def test_real_compose_ignores_exported_production_urls(monkeypatch, tmp_path):
    executable = shutil.which("docker-compose")
    if not executable:
        docker = shutil.which("docker")
        if not docker or subprocess.run([docker, "compose", "version"], capture_output=True).returncode:
            pytest.skip("Compose CLI unavailable; no engine required")
        command = [docker, "compose"]
    else:
        command = [executable]
    (tmp_path / "deploy").mkdir()
    for name in ("docker-compose.yml", "docker-compose.staging.yml", ".env.example"):
        shutil.copyfile(ROOT / "deploy" / name, tmp_path / "deploy" / name)
    password = uuid.uuid4().hex
    values = {
        "POSTGRES_USER": "local", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "local",
        "DATABASE_URL": f"postgresql+asyncpg://local:{password}@postgres:5432/local",
        "REDIS_URL": "redis://redis:6379/0", "STRAZ_ENV": "staging",
        "STRAZ_ADMIN_EMAIL": "fixture@example.invalid", "STRAZ_ADMIN_PASSWORD": uuid.uuid4().hex,
        "STRAZ_SESSION_SECRET": uuid.uuid4().hex,
    }
    (tmp_path / ".env.staging").write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fixture@production.example.invalid/live")
    monkeypatch.setenv("REDIS_URL", "redis://production.example.invalid/0")
    # Validate the overlay itself, even outside the launcher and with a polluted shell.
    import json, os
    rendered = subprocess.run([
        *command, "--env-file", str(tmp_path / ".env.staging"),
        "-f", str(tmp_path / "deploy/docker-compose.yml"),
        "-f", str(tmp_path / "deploy/docker-compose.staging.yml"), "config", "--format", "json",
    ], env=dict(os.environ), capture_output=True, text=True, check=True)
    staging.validate_targets(json.loads(rendered.stdout))
    assert staging.run("check", root=tmp_path, command=command) == 0
