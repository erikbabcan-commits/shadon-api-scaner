import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_naabu')


@pytest.mark.parametrize('row', [None, {}, {'ip': '127.0.0.1', 'port': 443},
    {'ip': '1.1.1.1', 'port': 8443}, {'ip': '1.1.1.1', 'port': '443'},
    {'ip': '1.1.1.1', 'port': 443, 'protocol': 'udp'}])
def test_unexpected_destination_or_protocol_rejected(adapter, row):
    with pytest.raises(RuntimeError):
        adapter.parse_report(0, json.dumps(row).encode(), '1.1.1.1', [443])


def test_open_port_is_only_information(adapter):
    result = adapter.parse_report(0, b'{"ip":"1.1.1.1","port":443}', '1.1.1.1', [443])
    assert result['open_ports'] == [443] and result['findings'][0]['severity'] == 'info'
    empty = adapter.parse_report(0, b'', '1.1.1.1', [443])
    assert empty['scope'] == 'tcp_connect_observation' and 'closed_ports' not in empty


def test_connect_only_and_exact_port_pairs(adapter, monkeypatch):
    def run(guard, image, args, endpoints, **kwargs):
        assert endpoints == [('1.1.1.1', 80), ('1.1.1.1', 443)]
        assert args[args.index('-s') + 1] == 'c' and '-Pn' in args
        assert '-wn' not in args and '-nmap' not in args and '-passive' not in args
        return 0, b'', b''
    monkeypatch.setattr(adapter, 'run_network', run)
    assert adapter.scan('guard', 'image', '1.1.1.1', [443, 80, 443])['tested_ports'] == [80, 443]
