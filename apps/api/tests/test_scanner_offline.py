import importlib
from pathlib import Path

import pytest


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_offline')


@pytest.mark.parametrize('failure', [False, True])
def test_execution_is_offline_and_cleanup_runs_after_failure(offline, monkeypatch, failure):
    events = []
    identity = 'b' * 64
    def docker(*args):
        events.append(args)
        return identity if args[0] == 'ps' else ''
    def run(args, data, **limits):
        assert args[args.index('--network') + 1] == 'none'
        assert args[args.index('--pull') + 1] == 'never'
        assert '--read-only' in args and '--env' not in args and '--volume' not in args
        assert args[-3:] == ['/bin/cat', 'sha256:' + 'a' * 64, '-']
        assert data == b'fixture' and limits['timeout'] == 2
        if failure:
            raise TimeoutError('Fixture timeout')
        return (0, data, b'')
    monkeypatch.setattr(offline, 'docker', docker)
    monkeypatch.setattr(offline, 'run_bounded', run)
    if failure:
        with pytest.raises(TimeoutError):
            offline.run_offline('sha256:' + 'a' * 64, ['/bin/cat', '-'], b'fixture', timeout=2)
    else:
        assert offline.run_offline('sha256:' + 'a' * 64, ['/bin/cat', '-'], b'fixture', timeout=2)[0] == 0
    assert events[-1] == ('rm', '--force', identity)


def test_mutable_image_rejected_before_docker(offline, monkeypatch):
    monkeypatch.setattr(offline, 'docker', lambda *args: pytest.fail('Docker called'))
    with pytest.raises(ValueError):
        offline.run_offline('busybox:latest', ['/bin/cat'])
