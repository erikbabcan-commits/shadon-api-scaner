#!/usr/bin/env python3
"""Run the backend suite against disposable local PostgreSQL/Redis services.

Use a frozen dev environment as this script's Python interpreter. No production
connection strings are accepted. Every PostgreSQL bin directory starts a new
cluster, bound to loopback, and every run receives its own nonpersistent Redis.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def private_write(path, value):
    with open(path, "w", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        output.write(value)


def source_hashes():
    paths = [path for path in (ROOT / "apps/api").rglob("*.py")
             if ".venv" not in path.parts and "__pycache__" not in path.parts]
    paths.extend((ROOT / "apps/api/typings").rglob("*.pyi"))
    paths.extend((ROOT / "deploy").glob("scanner_*.py"))
    paths.extend((ROOT / "scripts").glob("*scanner*.py"))
    paths.extend([ROOT / "apps/api/uv.lock", ROOT / "apps/api/pyproject.toml", ROOT / "deploy/staging.py",
                  ROOT / "deploy/docker-compose.yml", ROOT / "deploy/docker-compose.staging.yml", Path(__file__)])
    return [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(set(paths))]


def verify(pg_bin, redis_server, redis_cli, output, timeout):
    # A short temporary path also keeps PostgreSQL Unix sockets within OS limits.
    scratch = Path(tempfile.mkdtemp(prefix="straz-qa-"))
    port, redis_port = free_port(), free_port()
    while redis_port == port:
        redis_port = free_port()
    pg_started = False
    redis = None
    version = run([str(pg_bin / "postgres"), "--version"]).stdout.strip()
    major = re.search(r"\b(\d+)(?:\.\d+)*\b", version).group(1)
    label = f"pg{major}"
    try:
        run([str(pg_bin / "initdb"), "-D", str(scratch / "db"), "-U", "straz", "-A", "trust", "--no-locale"])
        run([str(pg_bin / "pg_ctl"), "-D", str(scratch / "db"), "-l", str(scratch / "postgres.log"),
             "-o", f"-h 127.0.0.1 -p {port} -k {scratch} -c shared_buffers=16MB -c max_connections=20", "-w", "start"])
        pg_started = True
        with (scratch / "redis.log").open("w") as log:
            redis = subprocess.Popen([str(redis_server), "--bind", "127.0.0.1", "--port", str(redis_port),
                                      "--save", "", "--appendonly", "no"], stdout=log, stderr=subprocess.STDOUT)
        for _ in range(100):
            ping = subprocess.run([str(redis_cli), "-h", "127.0.0.1", "-p", str(redis_port), "ping"], capture_output=True, text=True)
            if ping.returncode == 0 and ping.stdout.strip() == "PONG":
                break
            if redis.poll() is not None:
                raise RuntimeError("Disposable Redis exited before readiness")
            time.sleep(0.05)
        else:
            raise RuntimeError("Disposable Redis did not become ready")
        run([str(pg_bin / "createdb"), "-h", "127.0.0.1", "-p", str(port), "-U", "straz", "straz_test"])
        env = {**os.environ,
               "STRAZ_TEST_PG_URL": f"postgresql+asyncpg://straz@127.0.0.1:{port}/straz_test",
               "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
               "REDIS_URL": f"redis://127.0.0.1:{redis_port}/15",
               "QUOTA_REDIS_URL": f"redis://127.0.0.1:{redis_port}/14",
               "STRAZ_ENV": "test", "PYTHONDONTWRITEBYTECODE": "1"}
        print(f"Testing {version} with isolated Redis", flush=True)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT / "apps/api", env=env,
                                capture_output=True, text=True, timeout=timeout)
        private_write(output / f"{label}-pytest.log", result.stdout + result.stderr)
        summaries = [line for line in result.stdout.splitlines()
                     if re.fullmatch(r"[0-9]+ passed(?:, [0-9]+ \w+)* in .+", line.strip())]
        summary = summaries[-1] if summaries else "No successful pytest summary; inspect private log"
        if result.returncode or not summaries or "skipped" in summary:
            raise RuntimeError(f"{label} did not pass without skips; inspect private log")
        print(f"{label}: {summary}", flush=True)
        return {"postgres": version, "pytest_exit": result.returncode, "summary": summary}
    finally:
        try:
            if redis is not None:
                if redis.poll() is None:
                    redis.terminate()
                try:
                    redis.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    redis.kill()
                    redis.wait(timeout=5)
        finally:
            if pg_started:
                # Keep the cluster if shutdown fails, rather than deleting live files.
                run([str(pg_bin / "pg_ctl"), "-D", str(scratch / "db"), "-m", "fast", "-w", "stop"])
            shutil.rmtree(scratch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", type=Path, action="append", required=True)
    parser.add_argument("--redis-server", type=Path, default=shutil.which("redis-server"))
    parser.add_argument("--redis-cli", type=Path, default=shutil.which("redis-cli"))
    parser.add_argument("--output", type=Path, required=True, help="New private directory outside the repository")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum seconds per pytest run")
    args = parser.parse_args()
    if not args.redis_server or not args.redis_cli:
        parser.error("redis-server and redis-cli are required")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("Keep private test logs outside the repository")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    tested_files = source_hashes()
    results = [verify(path.resolve(), args.redis_server, args.redis_cli, output, args.timeout)
               for path in args.postgres_bin]
    if source_hashes() != tested_files:
        raise RuntimeError("Sources changed during verification; repeat against a stable tree")
    evidence = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip(),
                "working_tree_had_changes": bool(run(["git", "status", "--porcelain"], cwd=ROOT).stdout.strip()),
                "python": sys.version.split()[0], "results": results, "production_data_used": False,
                "scope": "Native full suite: SQLite API units, real local PostgreSQL migrations/cutover, and Redis quota tests; not all API tests against PostgreSQL.",
                "tested_files": tested_files}
    private_write(output / "results.json", json.dumps(evidence, indent=2) + "\n")
    print("Disposable services stopped; evidence saved in the requested private directory")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # Child output may include environment-derived values: never echo it.
        print("Local verification failed; inspect private logs. No success claimed.", file=sys.stderr)
        raise SystemExit(1)
