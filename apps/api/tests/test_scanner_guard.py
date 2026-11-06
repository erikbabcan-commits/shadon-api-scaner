import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def guard(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_guard')


def setup_guard(monkeypatch, guard, *, install_fails=False, changed=False):
    events = []
    image = 'sha256:' + 'a' * 64
    identity = 'b' * 64
    label = [None]
    inspections = [0]
    def docker(*args):
        events.append(args[0])
        if args[0] == 'run':
            label[0] = args[args.index('--label') + 1].split('=', 1)[1]
            return identity
        if args[0] == 'ps':
            return identity if label[0] else ''
        if args[0] == 'inspect':
            inspections[0] += 1
            return json.dumps([{'Id': identity, 'Image': image,
                'Config': {'Labels': {'straz.guard': label[0]}},
                'State': {'Running': True, 'Pid': 99 if changed and inspections[0] > 1 else 42},
                'HostConfig': {'NetworkMode': 'bridge'}}])
        return ''
    def install(pid, endpoints):
        events.append('policy')
        assert pid == 42
        if install_fails:
            raise RuntimeError('Fixture installation failure')
        return {'verified': True}
    monkeypatch.setattr(guard, 'docker', docker)
    monkeypatch.setattr(guard, 'install_policy', install)
    return image, identity, events


def test_handle_only_after_policy_and_cleanup_after_caller_error(guard, monkeypatch):
    image, identity, events = setup_guard(monkeypatch, guard)
    with pytest.raises(RuntimeError, match='Caller failed'):
        with guard.policy_guard(image, [('1.1.1.1', 443)]) as handle:
            assert handle['container_id'] == identity and 'policy' in events
            raise RuntimeError('Caller failed')
    assert events[-1] == 'rm'


@pytest.mark.parametrize('case', ['install', 'identity'])
def test_failure_never_returns_guard_and_cleans_resources(guard, monkeypatch, case):
    image, _, events = setup_guard(monkeypatch, guard, install_fails=case == 'install', changed=case == 'identity')
    with pytest.raises(RuntimeError):
        with guard.policy_guard(image, [('1.1.1.1', 443)]):
            pytest.fail('Unverified guard was exposed')
    assert events[-1] == 'rm'


def test_invalid_destination_creates_no_resource(guard, monkeypatch):
    image, _, events = setup_guard(monkeypatch, guard)
    with pytest.raises(ValueError):
        with guard.policy_guard(image, [('127.0.0.1', 443)]):
            pytest.fail('Private destination accepted')
    assert events == []


def test_uncertain_run_failure_still_discovers_owned_container(guard, monkeypatch):
    image, _, events = setup_guard(monkeypatch, guard)
    original = guard.docker
    def uncertain(*args):
        result = original(*args)
        if args[0] == 'run':
            raise TimeoutError('Daemon created container but response was lost')
        return result
    monkeypatch.setattr(guard, 'docker', uncertain)
    with pytest.raises(TimeoutError):
        with guard.policy_guard(image, [('1.1.1.1', 443)]):
            pytest.fail('Failed creation exposed a guard')
    assert events[-1] == 'rm' and 'policy' not in events
