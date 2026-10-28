#!/usr/bin/env python3
"""Exercise real scans against disposable repositories, never against production."""
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

GATE = Path(__file__).with_name("check_secrets.py")


def check(root: Path, mode: str, expected: int, forbidden: str = "", extra: list[str] | None = None) -> None:
    result = subprocess.run([sys.executable, str(GATE), mode, "--root", str(root), *(extra or [])], capture_output=True, text=True)
    assert result.returncode == expected, f"Unexpected scanner result: {result.returncode}"
    assert not forbidden or forbidden not in result.stdout + result.stderr, "Scanner exposed fixture value"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix="straz-secret-gate-test-") as temp:
    root = Path(temp)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "README.md").write_text("Synthetic scanner fixture\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "clean fixture")
    clean_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    check(root, "tree", 0)
    check(root, "staged", 0)
    value = secrets.token_hex(32)
    (root / "fixture.txt").write_text("STRAZ_" + "SESSION_SECRET=" + value + "\n")
    check(root, "tree", 1, value)
    git(root, "add", "fixture.txt")
    check(root, "staged", 1, value)
    git(root, "commit", "-qm", "synthetic scanner positive fixture")
    secret_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    check(root, "history", 1, value)
    check(root, "range", 1, value, ["--base", clean_sha, "--head", secret_sha])
    (root / "fixture.txt").unlink()
    git(root, "add", "-u")
    check(root, "tree", 0)
    check(root, "history", 1, value)
    git(root, "commit", "-qm", "remove synthetic fixture")
    fixed_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    check(root, "range", 0, value, ["--base", secret_sha, "--head", fixed_sha])
    for name in (".env", "private.key", "local.sqlite", "backup.dump", "backups/db.sql.gz"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic non-secret placeholder\n")
        git(root, "add", name)
        check(root, "staged", 1)
        git(root, "rm", "--cached", name)
print("Secret gate: clean tree/staged pass; synthetic tree/staged/history/range reject; output redacted; credential/backup paths rejected")
