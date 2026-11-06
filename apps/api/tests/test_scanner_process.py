"""Real disposable child processes only; no external scanners or network I/O."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from app.services import scanners


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


@pytest.mark.parametrize("stream", ["stdout", "stderr", "combined"])
async def test_output_limit_is_shared_and_never_returns_truncated_success(monkeypatch, stream):
    monkeypatch.setattr(scanners, "SCANNER_OUTPUT_LIMIT_BYTES", 4096, raising=False)
    script = {
        "stdout": "import os; os.write(1, b'x' * 4097)",
        "stderr": "import os; os.write(2, b'x' * 4097)",
        "combined": "import os; os.write(1, b'x' * 3000); os.write(2, b'y' * 3000)",
    }[stream]
    with pytest.raises(RuntimeError, match="Scanner output exceeded limit"):
        await scanners._run_cmd(python(script), timeout=3)


async def test_exact_limit_preserves_both_streams_and_unicode(monkeypatch):
    stdout, stderr = "ž" * 1000, "e" * 2096
    monkeypatch.setattr(scanners, "SCANNER_OUTPUT_LIMIT_BYTES", 4096, raising=False)
    code, out, err = await scanners._run_cmd(python(
        f"import os; os.write(1, {stdout.encode()!r}); os.write(2, {stderr.encode()!r})"
    ))
    assert (code, out, err) == (0, stdout, stderr)


async def test_child_has_no_application_credentials_or_inherited_input(monkeypatch):
    monkeypatch.setenv("SCANNER_PRIVATE_SENTINEL", "synthetic-value")
    monkeypatch.setenv("SCANNER_NONWHITELIST_SETTING", "synthetic-setting")
    _, out, _ = await scanners._run_cmd(python(
        "import os,sys,json; print(json.dumps({'keys':sorted(os.environ), 'stdin':sys.stdin.read()}))"
    ))
    result = json.loads(out)
    assert result["stdin"] == ""
    assert not set(result["keys"]) & {
        "SCANNER_PRIVATE_SENTINEL", "SCANNER_NONWHITELIST_SETTING", "DATABASE_URL",
        "REDIS_URL", "STRAZ_SESSION_SECRET", "STRAZ_ADMIN_PASSWORD", "STRIPE_WEBHOOK_SECRET",
    }


@pytest.mark.parametrize("name,exit_code,accepted", [
    ("gitleaks", 0, True), ("gitleaks", 1, True), ("gitleaks", 2, False),
    ("other-scanner", 0, True), ("other-scanner", 1, False), ("other-scanner", 2, False),
])
async def test_exit_policy_and_errors_do_not_expose_process_diagnostics(tmp_path, name, exit_code, accepted):
    if os.name != "posix":
        pytest.skip("Fixture executable uses a POSIX shebang")
    executable = tmp_path / name
    executable.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "print('synthetic diagnostic detail',file=sys.stderr)\n"
        f"sys.exit({exit_code})\n"
    )
    executable.chmod(0o700)
    if accepted:
        assert (await scanners._run_cmd([str(executable)]))[0] == exit_code
    else:
        with pytest.raises(RuntimeError, match=f"Scanner process failed \\(exit {exit_code}\\)") as error:
            await scanners._run_cmd([str(executable)])
        assert "synthetic diagnostic detail" not in str(error.value)
        assert str(executable) not in str(error.value)


def fork_program(path: Path, *, overflow=False, root_exits=False) -> list[str]:
    child = (
        "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "time.sleep(30)"
    )
    return python(
        "import json,os,signal,subprocess,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}],"
        + ("stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); " if root_exits else "); ")
        + f"Path({str(path)!r}).write_text(json.dumps({{'parent':os.getpid(),'child':p.pid,'group':os.getpgrp()}})); "
        + ("os.write(1,b'x'*100_000); time.sleep(30)" if overflow else ("" if root_exits else "time.sleep(30)"))
    )


async def pid_record(path: Path) -> dict:
    async with asyncio.timeout(5):
        while not path.exists():
            await asyncio.sleep(0.01)
    result = json.loads(path.read_text())
    assert result["group"] == result["parent"]
    assert result["group"] != os.getpgrp(), "Fixture must never share pytest's process group"
    return result


def running(pid: int) -> bool:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    # A killed orphan may briefly await the host init reaper. It is not running.
    return result.returncode == 0 and bool(result.stdout.strip()) and not result.stdout.lstrip().startswith("Z")


async def assert_stopped(record: dict):
    async with asyncio.timeout(3):
        while running(record["parent"]) or running(record["child"]):
            await asyncio.sleep(0.01)
    with pytest.raises(ChildProcessError):
        os.waitpid(record["parent"], os.WNOHANG)


def final_cleanup(path: Path):
    if path.exists():
        record = json.loads(path.read_text())
        assert record["group"] != os.getpgrp()
        try:
            os.killpg(record["group"], signal.SIGKILL)
        except ProcessLookupError:
            pass


posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX process group contract")


@posix_only
async def test_timeout_kills_root_and_forked_child_and_reaps_root(tmp_path):
    path = tmp_path / "pids.json"
    task = asyncio.create_task(scanners._run_cmd(fork_program(path), timeout=1))
    try:
        record = await pid_record(path)
        with pytest.raises(RuntimeError, match="Scanner timed out"):
            await asyncio.wait_for(task, 4)
        await assert_stopped(record)
    finally:
        final_cleanup(path)


@posix_only
async def test_output_limit_kills_entire_group(tmp_path, monkeypatch):
    path = tmp_path / "pids.json"
    monkeypatch.setattr(scanners, "SCANNER_OUTPUT_LIMIT_BYTES", 4096, raising=False)
    task = asyncio.create_task(scanners._run_cmd(fork_program(path, overflow=True), timeout=10))
    try:
        record = await pid_record(path)
        with pytest.raises(RuntimeError, match="Scanner output exceeded limit"):
            await asyncio.wait_for(task, 4)
        await assert_stopped(record)
    finally:
        final_cleanup(path)


@posix_only
async def test_cancel_kills_entire_group_and_propagates_cancellation(tmp_path):
    path = tmp_path / "pids.json"
    task = asyncio.create_task(scanners._run_cmd(fork_program(path), timeout=30))
    try:
        record = await pid_record(path)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 4)
        await assert_stopped(record)
    finally:
        final_cleanup(path)


@posix_only
async def test_normal_root_exit_does_not_leave_background_group_member(tmp_path):
    path = tmp_path / "pids.json"
    try:
        result = await scanners._run_cmd(fork_program(path, root_exits=True), timeout=5)
        record = await pid_record(path)
        assert result[0] == 0
        await assert_stopped(record)
    finally:
        final_cleanup(path)


@posix_only
async def test_repeated_cancellation_cannot_abandon_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "pids.json"
    original_cleanup = scanners._close_scanner_process
    cleanup_started = asyncio.Event()

    async def delayed_cleanup(started, output):
        cleanup_started.set()
        await asyncio.sleep(0.05)
        await original_cleanup(started, output)

    monkeypatch.setattr(scanners, "_close_scanner_process", delayed_cleanup)
    task = asyncio.create_task(scanners._run_cmd(fork_program(path), timeout=30))
    try:
        record = await pid_record(path)
        task.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 4)
        await assert_stopped(record)
    finally:
        final_cleanup(path)


@posix_only
async def test_cancellation_during_spawn_still_collects_and_closes_transport(tmp_path, monkeypatch):
    path = tmp_path / "pids.json"
    loop = asyncio.get_running_loop()
    original_spawn = loop.subprocess_exec
    allow_spawn_to_return = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        transport, protocol = await original_spawn(*args, **kwargs)
        await allow_spawn_to_return.wait()
        return transport, protocol

    monkeypatch.setattr(loop, "subprocess_exec", delayed_spawn)
    task = asyncio.create_task(scanners._run_cmd(fork_program(path), timeout=30))
    try:
        record = await pid_record(path)
        task.cancel()
        allow_spawn_to_return.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 4)
        await assert_stopped(record)
    finally:
        allow_spawn_to_return.set()
        final_cleanup(path)
