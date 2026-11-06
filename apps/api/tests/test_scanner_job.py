import base64
import importlib
from pathlib import Path
import socket
import uuid

import pytest


@pytest.fixture
def dispatcher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_job')


def job(profile='tls'):
    return {'version': 1, 'job_id': str(uuid.uuid4()), 'profile': profile,
            'target': {'hostname': 'authorized.example', 'port': 443}}


def test_mixed_dns_answers_rejected_before_scanner(dispatcher, monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))
        for address in ('1.1.1.1', '127.0.0.1')])
    with pytest.raises(ValueError):
        dispatcher.resolve_target('authorized.example', 443)


def test_all_addresses_complete_before_job_success(dispatcher, monkeypatch):
    monkeypatch.setattr(dispatcher, 'resolve_target', lambda *args: ['1.1.1.1', '8.8.8.8'])
    calls = []
    def scan(guard, image, host, address, port):
        calls.append(address)
        if address == '8.8.8.8':
            raise RuntimeError('Synthetic second endpoint failure')
        return {'findings': []}
    monkeypatch.setattr(dispatcher.scanner_tlsx, 'scan', scan)
    with pytest.raises(RuntimeError):
        dispatcher.execute(job(), {'guard': 'sha256:' + 'a' * 64, 'tls': 'sha256:' + 'b' * 64})
    assert calls == ['1.1.1.1', '8.8.8.8']


@pytest.mark.parametrize('extra', ['argv', 'image', 'command', 'environment'])
def test_job_cannot_choose_execution_configuration(dispatcher, extra):
    envelope = job()
    envelope[extra] = 'untrusted'
    with pytest.raises(ValueError, match='Unexpected'):
        dispatcher.execute(envelope, {})


def test_source_job_returns_only_adapter_metadata(dispatcher, monkeypatch):
    envelope = {'version': 1, 'job_id': str(uuid.uuid4()), 'profile': 'gitleaks',
                'source_base64': base64.b64encode(b'synthetic source').decode()}
    def scan(image, source):
        assert source == b'synthetic source'
        return []
    monkeypatch.setattr(dispatcher.scanner_gitleaks, 'scan', scan)
    result = dispatcher.execute(envelope, {'gitleaks': 'sha256:' + 'a' * 64})
    assert result['job_id'] == envelope['job_id'] and result['observations_complete'] is True
    assert 'source_base64' not in result and result['result'] == {'findings': []}


def test_repository_job_chains_pinned_acquisition_and_offline_scan(dispatcher, monkeypatch):
    envelope = {'version': 1, 'job_id': str(uuid.uuid4()), 'profile': 'gitleaks',
                'repository_url': 'https://authorized.example/owner/repo.git'}
    monkeypatch.setattr(dispatcher, 'resolve_target', lambda *args: ['1.1.1.1'])
    def clone(guard, git, url, address):
        assert address == '1.1.1.1' and url == envelope['repository_url']
        return {'commit': 'a' * 40, 'archive': b'synthetic validated archive'}
    monkeypatch.setattr(dispatcher.scanner_git, 'clone_archive', clone)
    def scan(image, archive):
        assert archive == b'synthetic validated archive'
        return []
    monkeypatch.setattr(dispatcher.scanner_gitleaks, 'scan_archive', scan)
    images = {key: 'sha256:' + 'a' * 64 for key in ('guard', 'git', 'gitleaks')}
    result = dispatcher.execute(envelope, images)
    assert result['observations_complete'] is True
    assert result['result'] == {'scope': 'repository_head', 'commit': 'a' * 40, 'findings': []}


def test_ports_job_passes_only_explicit_ports(dispatcher, monkeypatch):
    envelope = {'version': 1, 'job_id': str(uuid.uuid4()), 'profile': 'ports',
                'target': {'hostname': 'authorized.example', 'ports': [443]}}
    monkeypatch.setattr(dispatcher, 'resolve_target', lambda *args: ['1.1.1.1'])
    def scan(guard, image, address, ports):
        assert address == '1.1.1.1' and ports == [443]
        return {'scope': 'tcp_connect_observation', 'open_ports': [443]}
    monkeypatch.setattr(dispatcher.scanner_naabu, 'scan', scan)
    images = {key: 'sha256:' + 'a' * 64 for key in ('guard', 'ports')}
    result = dispatcher.execute(envelope, images)
    assert result['observations_complete'] is True


def test_dependency_job_retains_database_and_source_scope(dispatcher, monkeypatch):
    envelope = {'version': 1, 'job_id': str(uuid.uuid4()), 'profile': 'trivy_fs',
                'repository_url': 'https://authorized.example/repo.git'}
    monkeypatch.setattr(dispatcher, 'resolve_target', lambda *args: ['1.1.1.1'])
    monkeypatch.setattr(dispatcher.scanner_git, 'clone_archive', lambda *args:
                        {'commit': 'a' * 40, 'archive': b'synthetic validated archive'})
    monkeypatch.setattr(dispatcher.scanner_trivy, 'scan_archive', lambda *args:
                        {'scope': 'supported_dependency_files', 'database': {'updated_at': 'fixture'}, 'findings': []})
    images = {key: 'sha256:' + 'a' * 64 for key in ('guard', 'git', 'trivy_fs')}
    result = dispatcher.execute(envelope, images)
    assert result['result']['repository_commit'] == 'a' * 40
    assert result['result']['scope'] == 'supported_dependency_files'
    assert 'database' in result['result']
