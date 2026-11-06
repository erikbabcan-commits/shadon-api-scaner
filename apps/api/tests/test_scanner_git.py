import importlib
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_git')


def test_https_host_is_pinned_and_side_protocols_hooks_redirects_disabled(adapter):
    args = adapter.pinned_args('https://authorized.example/owner/repo.git', '1.1.1.1')
    for option in ['protocol.allow=never', 'protocol.https.allow=always',
        'core.hooksPath=/dev/null', 'http.followRedirects=false', 'http.sslVerify=true',
        'http.curloptResolve=authorized.example:443:1.1.1.1', 'credential.helper=']:
        assert option in args
    assert args[-2:] == ['https://authorized.example/owner/repo.git', '/tmp/repository.git']
    assert '--bare' in args and '--depth' in args


@pytest.mark.parametrize('url', ['http://authorized.example/repo',
    'https://user:password@authorized.example/repo', 'file:///tmp/repo',
    'ext::command', 'https://authorized.example/repo?token=fixture',
    'https://authorized.example/repo#fragment', 'https://authorized.example/',
    'https://authorized.example/repo\noption'])
def test_credentials_unsafe_schemes_or_ambiguous_urls_rejected(adapter, url):
    with pytest.raises(ValueError):
        adapter.pinned_args(url, '1.1.1.1')


@pytest.mark.parametrize('address', ['127.0.0.1', '169.254.169.254', '10.0.0.1', '::1'])
def test_private_repository_destinations_rejected(adapter, address):
    with pytest.raises(ValueError):
        adapter.pinned_args('https://authorized.example/repo.git', address)
