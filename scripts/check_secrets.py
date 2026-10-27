#!/usr/bin/env python3
"""Fail-closed secret gate. Print locations only, never matched values."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def forbidden_paths(root: Path, staged: bool) -> list[str]:
    args = (["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
            if staged else ["ls-files", "-z"])
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    bad = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="replace")
        p = Path(name)
        if ((p.name == ".env" or p.name.startswith(".env.")) and p.name != ".env.example"
            or p.suffix.lower() in {".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".dump", ".backup"}
            or name.startswith("backups/") or p.name.endswith(".sql.gz")
            or p.name in {"id_rsa", "id_ed25519", "credentials.json", "service-account.json"}):
            bad.append(name)
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["tree", "staged", "history", "range"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode in {"tree", "staged"}:
        bad = forbidden_paths(root, args.mode == "staged")
        if bad:
            for name in bad:
                print(f"Forbidden tracked credential/data file: {name}", file=sys.stderr)
            return 1
    if args.mode == "range":
        if not all(re.fullmatch(r"[0-9a-fA-F]{40}", value or "") for value in (args.base, args.head)):
            print("Commit range requires two full Git SHAs", file=sys.stderr)
            return 2
        if set(args.base) == {"0"}:
            print("No trustworthy previous commit; scan full history instead", file=sys.stderr)
            args.mode = "history"
    config = Path(__file__).with_name("gitleaks.toml").resolve()
    env = {k: v for k, v in os.environ.items()
           if k not in {"GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML"}}
    with tempfile.TemporaryDirectory(prefix="straz-secret-scan-") as temp:
        report = Path(temp) / "report.json"
        command = [os.environ.get("GITLEAKS_BIN", "gitleaks"),
                   "dir" if args.mode == "tree" else "git", str(root),
                   "--config", str(config), "--redact=100", "--no-banner",
                   "--log-level", "error", "--ignore-gitleaks-allow",
                   "--gitleaks-ignore-path", temp,
                   "--report-format", "json", "--report-path", str(report)]
        if args.mode == "staged":
            command += ["--pre-commit", "--staged"]
        elif args.mode == "range":
            command += ["--log-opts", f"{args.base}..{args.head}"]
        try:
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            print("Gitleaks unavailable or timed out; refusing to pass", file=sys.stderr)
            return 2
        try:
            findings = json.loads(report.read_text()) if report.exists() else []
        except (ValueError, OSError):
            print("Invalid scanner report; refusing to pass", file=sys.stderr)
            return 2
        if not isinstance(findings, list):
            return 2
        for item in findings:
            # Do not forward scanner stdout/stderr, Match, Secret, author or URLs.
            print(json.dumps({k: item.get(k) for k in ("RuleID", "File", "StartLine", "Commit")}))
        if findings or result.returncode == 1:
            print(f"Secret scan rejected: {len(findings)} finding(s)", file=sys.stderr)
            return 1
        if result.returncode != 0:
            print("Scanner failed; refusing to pass", file=sys.stderr)
            return 2
        print(f"Secret scan passed ({args.mode})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
