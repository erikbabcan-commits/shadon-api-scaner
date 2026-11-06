import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_httpx')


def report(**fields):
    return json.dumps({'url': 'https://1.1.1.1:443/', 'status_code': 200, **fields}).encode()


@pytest.mark.parametrize('raw', [b'', b'{}', b'not-json', report(failed=True),
    report(status_code='200'), report(status_code=0), report(url='http://1.1.1.1/'),
    report(url='https://127.0.0.1/'), report(url='https://1.1.1.1:8443/')])
def test_failed_incomplete_or_changed_destination_rejected(adapter, raw):
    with pytest.raises(RuntimeError):
        adapter.parse_report(0, raw, '1.1.1.1', 443)


def test_server_error_is_finding_and_body_is_never_returned(adapter):
    result = adapter.parse_report(0, report(status_code=503, body='private fixture'), '1.1.1.1', 443)
    assert result == {'status_code': 503, 'findings': [{'rule_id': 'http-server-error', 'severity': 'high'}]}


def test_ip_sni_host_and_no_redirect_flags(adapter, monkeypatch):
    def run(guard, image, args, endpoints, **kwargs):
        assert endpoints == [('1.1.1.1', 443)]
        assert args[args.index('-u') + 1] == 'https://1.1.1.1:443/healthz'
        assert args[args.index('-sni') + 1] == 'authorized.example'
        assert args[args.index('-H') + 1] == 'Host: authorized.example'
        assert '-nfs' in args and '-fr' not in args and '-fhr' not in args
        return 0, report(), b''
    monkeypatch.setattr(adapter, 'run_network', run)
    assert adapter.scan('guard', 'image', 'authorized.example', '1.1.1.1', path='/healthz')['status_code'] == 200
