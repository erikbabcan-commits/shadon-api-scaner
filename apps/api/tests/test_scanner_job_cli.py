import importlib
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_job_cli')


@pytest.mark.parametrize('payload', [b'not-json', b'\xff', b'{"version":1,"version":2}',
    b'[]', b'{"source_base64":"private fixture"}'])
def test_malformed_request_returns_only_generic_failure(cli, payload):
    output = io.BytesIO()
    assert cli.serve(io.BytesIO(payload), output, {}) == 1
    assert json.loads(output.getvalue()) == cli.FAILURE
    assert b'private fixture' not in output.getvalue()


def test_request_limit_checked_before_dispatch(cli, monkeypatch):
    monkeypatch.setattr(cli, 'MAX_REQUEST', 32)
    monkeypatch.setattr(cli, 'execute', lambda *args: pytest.fail('Dispatched oversized request'))
    output = io.BytesIO()
    assert cli.serve(io.BytesIO(b'x' * 33), output, {}) == 1


def test_adapter_error_is_not_transmitted(cli, monkeypatch):
    def execute(*args):
        raise RuntimeError('private source fixture and diagnostic')
    monkeypatch.setattr(cli, 'execute', execute)
    output = io.BytesIO()
    assert cli.serve(io.BytesIO(b'{}'), output, {}) == 1
    assert json.loads(output.getvalue()) == cli.FAILURE


def test_success_is_exact_dispatcher_response(cli, monkeypatch):
    result = {'version': 1, 'job_id': 'fixture', 'observations_complete': True,
              'result': {'findings': []}}
    monkeypatch.setattr(cli, 'execute', lambda *args: result)
    output = io.BytesIO()
    assert cli.serve(io.BytesIO(b'{}'), output, {}) == 0
    assert json.loads(output.getvalue()) == result
