import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_tlsx')


def report(**fields):
    return json.dumps({'probe_status': True, 'ip': '1.1.1.1', 'port': '443',
                       'not_after': '2099-01-01T00:00:00Z', 'subject_an': ['authorized.example'], **fields}).encode()


@pytest.mark.parametrize('raw', [b'', b'{}', b'[]', b'not-json',
    report(probe_status=False), report(ip='127.0.0.1'), report(port='8443'),
    report(not_after=None), report(not_after='2099-01-01'), report(expired='false')])
def test_failed_or_malformed_probe_never_means_clean(adapter, raw):
    with pytest.raises(RuntimeError):
        adapter.parse_report(0, raw, '1.1.1.1', 443, 'authorized.example')


def test_valid_and_expired_certificate(adapter):
    assert adapter.parse_report(0, report(), '1.1.1.1', 443, 'authorized.example')['findings'] == []
    result = adapter.parse_report(0, report(not_after='2000-01-01T00:00:00Z'), '1.1.1.1', 443, 'authorized.example')
    assert result['findings'] == [{'rule_id': 'tls-expired', 'severity': 'high'}]


def test_exact_ip_port_and_sni_are_passed_to_guard(adapter, monkeypatch):
    def run(guard, image, args, endpoints, **kwargs):
        assert endpoints == [('1.1.1.1', 443)]
        assert args[args.index('-u') + 1] == '1.1.1.1'
        assert args[args.index('-sni') + 1] == 'authorized.example'
        assert '-duc' in args
        return 0, report(), b''
    monkeypatch.setattr(adapter, 'run_network', run)
    assert adapter.scan('guard', 'image', 'authorized.example', '1.1.1.1')['findings'] == []


@pytest.mark.parametrize('name,hostname,mismatch', [
    ('*.authorized.example', 'app.authorized.example', False),
    ('*.authorized.example', 'a.b.authorized.example', True),
    ('*.authorized.example', 'authorized.example', True),
    ('app*.authorized.example', 'app.authorized.example', True),
    ('AUTHORIZED.EXAMPLE', 'authorized.example', False),
    ('other.example', 'authorized.example', True),
])
def test_names_match_hostname_not_pinned_ip(adapter, name, hostname, mismatch):
    result = adapter.parse_report(0, report(subject_an=[name], mismatched=True),
                                  '1.1.1.1', 443, hostname)
    assert bool(result['findings']) is mismatch
