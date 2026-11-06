from contextlib import contextmanager
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def network(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_network')


@pytest.mark.parametrize('failed', [False, True])
def test_scanner_only_runs_inside_verified_guard_and_cleans_before_guard(network, monkeypatch, failed):
    events = []
    image = 'sha256:' + 'a' * 64
    identity = 'b' * 64
    @contextmanager
    def guard(image_arg, endpoints):
        assert image_arg == image and endpoints == [('1.1.1.1', 443)]
        events.append('policy-ready')
        try:
            yield {'container_id': identity}
        finally:
            events.append('guard-removed')
    def docker(*args):
        events.append(args[0])
        return 'c' * 64 if args[0] == 'ps' else ''
    def run(args, data, **kwargs):
        assert 'policy-ready' in events
        assert args[args.index('--network') + 1] == 'container:' + identity
        assert '--volume' not in args and '--env' not in args and '--read-only' in args
        events.append('scanner')
        if failed:
            raise TimeoutError('Synthetic timeout')
        return 0, b'fixture', b''
    monkeypatch.setattr(network, 'policy_guard', guard)
    monkeypatch.setattr(network, 'docker', docker)
    monkeypatch.setattr(network, 'run_bounded', run)
    if failed:
        with pytest.raises(TimeoutError):
            network.run_network(image, image, ['/bin/cat'], [('1.1.1.1', 443)])
    else:
        assert network.run_network(image, image, ['/bin/cat'], [('1.1.1.1', 443)])[0] == 0
    assert events[-2:] == ['rm', 'guard-removed']


def test_policy_failure_never_launches_scanner(network, monkeypatch):
    @contextmanager
    def guard(*args):
        raise RuntimeError('Policy failed')
        yield
    monkeypatch.setattr(network, 'policy_guard', guard)
    monkeypatch.setattr(network, 'docker', lambda *args: '')
    monkeypatch.setattr(network, 'run_bounded', lambda *args, **kwargs: pytest.fail('Scanner launched'))
    with pytest.raises(RuntimeError, match='Policy failed'):
        network.run_network('sha256:' + 'a' * 64, 'sha256:' + 'b' * 64,
                            ['/bin/cat'], [('1.1.1.1', 443)])


@pytest.mark.parametrize('memory', [0, 129, 512, True, '256'])
def test_unapproved_memory_budget_rejected_before_docker(network, monkeypatch, memory):
    monkeypatch.setattr(network, 'docker', lambda *args: pytest.fail('Docker called'))
    with pytest.raises(ValueError):
        network.run_network('sha256:' + 'a' * 64, 'sha256:' + 'b' * 64,
                            ['/bin/cat'], [('1.1.1.1', 443)], memory_mib=memory)
