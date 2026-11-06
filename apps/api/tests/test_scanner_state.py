import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import uuid

import pytest


@pytest.fixture
def state(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    module = importlib.import_module('scanner_state')
    monkeypatch.setattr(module, 'docker', lambda *args: '')
    return module


def job():
    return {'job_id': str(uuid.uuid4()), 'profile': 'fixture'}


def test_completed_job_replayed_without_second_execution(state, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(state, 'execute', lambda *args: calls.append(True) or {'complete': True})
    envelope = job()
    for _ in range(2):
        assert state.execute_once(envelope, {}, tmp_path) == {'complete': True}
    assert calls == [True]
    assert 'profile' not in (tmp_path / (envelope['job_id'] + '.json')).read_text()


def test_identity_reuse_with_different_source_rejected(state, monkeypatch, tmp_path):
    monkeypatch.setattr(state, 'execute', lambda *args: {})
    envelope = job()
    state.execute_once(envelope, {}, tmp_path)
    with pytest.raises(RuntimeError, match='different input'):
        state.execute_once({**envelope, 'source': 'different synthetic source'}, {}, tmp_path)


def test_failed_job_cannot_be_automatically_reexecuted(state, monkeypatch, tmp_path):
    def execute(*args):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(state, 'execute', execute)
    envelope = job()
    with pytest.raises(RuntimeError, match='synthetic failure'):
        state.execute_once(envelope, {}, tmp_path)
    with pytest.raises(RuntimeError, match='reconciliation'):
        state.execute_once(envelope, {}, tmp_path)
    assert json.loads((tmp_path / (envelope['job_id'] + '.json')).read_text())['status'] == 'failed'


def test_second_supervisor_cannot_enter_while_lock_held(state, monkeypatch, tmp_path):
    monkeypatch.setattr(state, 'execute', lambda *args: pytest.fail('Concurrent execution'))
    with (tmp_path / 'supervisor.lock').open('w') as stream:
        (tmp_path / 'supervisor.lock').chmod(0o600)
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            state.execute_once(job(), {}, tmp_path)


def test_orphan_containers_prevent_new_admission(state, monkeypatch, tmp_path):
    monkeypatch.setattr(state, 'docker', lambda *args: 'fixture-owned-container')
    monkeypatch.setattr(state, 'execute', lambda *args: pytest.fail('Orphan bypass'))
    with pytest.raises(RuntimeError, match='containers require'):
        state.execute_once(job(), {}, tmp_path)


def test_state_symlink_rejected(state, tmp_path):
    link = tmp_path / 'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match='private directory'):
        state.execute_once(job(), {}, link)


def test_crash_left_running_receipt_requires_reconciliation(state, monkeypatch, tmp_path):
    envelope = job()
    digest = hashlib.sha256(json.dumps({'job': envelope, 'images': {}},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    state.save(tmp_path, tmp_path / (envelope['job_id'] + '.json'),
               {'request_sha256': digest, 'status': 'running'})
    monkeypatch.setattr(state, 'execute', lambda *args: pytest.fail('Crashed job replayed'))
    with pytest.raises(RuntimeError, match='reconciliation'):
        state.execute_once(envelope, {}, tmp_path)


def test_image_change_does_not_silently_reexecute_same_job(state, monkeypatch, tmp_path):
    monkeypatch.setattr(state, 'execute', lambda *args: {})
    envelope = job()
    state.execute_once(envelope, {'image': 'old'}, tmp_path)
    with pytest.raises(RuntimeError, match='different input'):
        state.execute_once(envelope, {'image': 'new'}, tmp_path)
