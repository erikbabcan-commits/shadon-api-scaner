import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('scanner_policy', Path(__file__).resolve().parents[3] / 'deploy/scanner_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '100.64.0.1', '224.0.0.1', '::1', 'fc00::1', '::ffff:127.0.0.1', '2001:4860::1%eth0', '1.1.1.1; accept'])
def test_non_public_or_unsafe_address_rejected(address):
    with pytest.raises(ValueError):
        policy.compile_policy([(address, 443)])


@pytest.mark.parametrize('port', [True, 0, 65536, '443'])
def test_invalid_ports_rejected(port):
    with pytest.raises(ValueError):
        policy.compile_policy([('1.1.1.1', port)])


def test_exact_pairs_no_dns_no_cartesian_expansion():
    script = policy.compile_policy([('1.1.1.1', 443), ('8.8.8.8', 80), ('1.1.1.1', 443)])
    assert script.count('policy drop') == 3
    assert script.count('ip daddr 1.1.1.1 tcp dport 443') == 1
    assert 'ip daddr 1.1.1.1 tcp dport 80 ' not in script
    assert 'udp' not in script and 'flush ruleset' not in script


def test_ipv6_and_mapped_public_address_normalized():
    script = policy.compile_policy([('::ffff:1.1.1.1', 443), ('2001:4860:4860::8888', 443)])
    assert 'ip daddr 1.1.1.1 tcp dport 443' in script
    assert 'ip6 daddr 2001:4860:4860::8888 tcp dport 443' in script
    assert 'ip6 hoplimit 255' in script


@pytest.mark.parametrize('endpoints', [[], [('1.1.1.1', 443)] * 65])
def test_empty_and_excessive_lists_rejected(endpoints):
    with pytest.raises(ValueError):
        policy.compile_policy(endpoints)
