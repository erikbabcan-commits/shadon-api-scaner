import importlib
from pathlib import Path
import sys
import time

import pytest


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_process').run_bounded


def test_binary_input_and_separate_outputs(runner):
    code, stdout, stderr = runner([sys.executable, '-c',
        'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); '
        'sys.stderr.buffer.write(bytes([255])); sys.exit(1)'], b'fixture\x00')
    assert (code, stdout, stderr) == (1, b'fixture\x00', b'\xff')


def test_combined_limit_fails_without_partial_success(runner):
    with pytest.raises(RuntimeError, match='output exceeds limit'):
        runner([sys.executable, '-c',
            'import os; os.write(1,b"a"*600); os.write(2,b"b"*600)'], max_output=1000)


def test_full_output_before_consuming_large_input_does_not_deadlock(runner):
    code, stdout, stderr = runner([sys.executable, '-c',
        'import sys; sys.stdout.buffer.write(b"y"*262144); sys.stdout.buffer.flush(); '
        'data=sys.stdin.buffer.read(); sys.stderr.write(str(len(data)))'],
        b'x' * 262144, timeout=5)
    assert code == 0 and stdout == b'y' * 262144 and stderr == b'262144'


def test_child_inheriting_pipes_cannot_hold_supervisor(runner):
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        runner([sys.executable, '-c',
            'import os,time; pid=os.fork(); time.sleep(30) if pid==0 else None'], timeout=0.3)
    assert time.monotonic() - started < 3


def test_closed_pipes_do_not_bypass_deadline(runner):
    with pytest.raises(TimeoutError):
        runner([sys.executable, '-c',
            'import os,time; os.close(0); os.close(1); os.close(2); time.sleep(30)'], timeout=0.3)


def test_large_input_rejected_before_spawn(runner):
    with pytest.raises(ValueError):
        runner(['/does/not/exist'], b'x' * (1024 * 1024 + 1))


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), 0, -1])
def test_invalid_deadline_rejected_before_spawn(runner, timeout):
    with pytest.raises(ValueError):
        runner(['/does/not/exist'], timeout=timeout)
