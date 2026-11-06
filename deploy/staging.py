#!/usr/bin/env python3
"""Validate resolved local staging targets before starting any containers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent


def compose_command() -> list[str]:
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return ["docker", "compose"]


def compose_environment(root: Path, inherited: dict[str, str]) -> dict[str, str]:
    """Make the private staging file authoritative over unrelated shell exports."""
    names = {
        line.split("=", 1)[0].strip()
        for line in (root / "deploy/.env.example").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    return {k: v for k, v in inherited.items() if k not in names and not k.startswith("COMPOSE_")}


def validate_targets(config: dict) -> None:
    """Reject remote databases, credential mismatches and remote Redis without exposing URLs."""
    services = config["services"]
    postgres = services["postgres"]["environment"]
    for service in ("api", "worker"):
        environment = services[service]["environment"]
        database = urlsplit(environment["DATABASE_URL"])
        if not (
            database.scheme == "postgresql+asyncpg"
            and database.hostname == "postgres"
            and database.port in (None, 5432)
            and not database.query and not database.fragment
            and unquote(database.path.removeprefix("/")) == postgres["POSTGRES_DB"]
            and unquote(database.username or "") == postgres["POSTGRES_USER"]
            and unquote(database.password or "") == postgres["POSTGRES_PASSWORD"]
            and postgres["POSTGRES_PASSWORD"]
        ):
            raise ValueError("Staging must use its own postgres service and matching credentials")
        redis = urlsplit(environment["REDIS_URL"])
        if not (
            redis.scheme == "redis" and redis.hostname == "redis"
            and redis.port in (None, 6379) and not redis.username and not redis.password
            and not redis.query and not redis.fragment
        ):
            raise ValueError("Staging must use its own redis service")
        if environment["STRAZ_ENV"] != "staging":
            raise ValueError("Staging environment required")


def run(action: str, *, root: Path = ROOT, command: list[str] | None = None) -> int:
    if action not in {"check", "up"}:
        raise ValueError("Unsupported staging action")
    command = command or compose_command()
    arguments = [
        *command, "--project-name", "straz-staging", "--env-file", str(root / ".env.staging"),
        "-f", str(root / "deploy/docker-compose.yml"),
        "-f", str(root / "deploy/docker-compose.staging.yml"),
    ]
    environment = compose_environment(root, dict(os.environ))
    # Capture config: it contains credentials and must never reach logs or terminal output.
    rendered = subprocess.run(
        [*arguments, "config", "--format", "json"], env=environment,
        capture_output=True, text=True, check=True,
    )
    validate_targets(json.loads(rendered.stdout))
    if action == "check":
        print("Local staging configuration validated; no containers started.")
        return 0
    # Build first, then quiesce existing application processes before changing schema.
    # A new database also needs migrations before either application may start.
    phases = [
        ["build"],
        ["stop", "api", "worker"],
        ["up", "--detach", "--wait", "postgres", "redis"],
        ["run", "--rm", "--no-deps", "api", "python", "-m", "app.migrations", "upgrade"],
        ["up", "--detach", "--wait"],
    ]
    for phase in phases:
        # A failed migration can contain a DSN in its traceback. Never echo captured output.
        subprocess.run([*arguments, *phase], env=environment, capture_output=True, check=True)
        print(f"Staging phase completed: {phase[0]}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "up"), nargs="?", default="check")
    args = parser.parse_args()
    try:
        return run(args.action)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        # Neither exception strings nor Compose stderr are safe to print: both may contain a DSN.
        print("Staging validation failed. Check the private staging file, local targets and Compose >=2.30.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
