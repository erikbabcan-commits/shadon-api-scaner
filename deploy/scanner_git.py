"""Build trusted, pinned HTTPS Git acquisition commands.

The caller must authorize this repository, resolve its hostname, and run the
command only inside the matching network guard. No credentials are accepted.
"""
import ipaddress
import io
import re
import tarfile
from urllib.parse import urlsplit

from scanner_policy import compile_policy
from scanner_archive import validate
from scanner_network import run_network

ARCHIVE_ARGS = ['--work-tree=/tmp/export', '-c', 'core.attributesFile=/dev/null',
                'archive', '--worktree-attributes', '--format=tar', 'HEAD']


def repository_endpoint(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise ValueError('Invalid public repository URL')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
        or not parsed.path.startswith('/') or parsed.path == '/'
        or '\\' in url or '%' in parsed.netloc):
        raise ValueError('Require a credential-free HTTPS repository URL')
    host = parsed.hostname
    if (len(host) > 253 or not all(re.fullmatch(
        r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', part) for part in host.split('.'))):
        raise ValueError('Invalid repository hostname')
    return host, parsed.port or 443


def pinned_args(url, address, *, destination='/tmp/repository.git'):
    host, port = repository_endpoint(url)
    address = str(ipaddress.ip_address(address))
    compile_policy([(address, port)])
    if destination != '/tmp/repository.git':
        raise ValueError('Repository destination is fixed by supervisor')
    resolved = '[' + address + ']' if ':' in address else address
    return ['/usr/bin/git', '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always',
        '-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=',
        '-c', 'http.proxy=', '-c', 'http.followRedirects=false',
        '-c', 'http.sslVerify=true', '-c', 'http.sslCAInfo=/etc/ssl/certs/ca-certificates.crt',
        '-c', f'http.curloptResolve={host}:{port}:{resolved}',
        '-c', 'fetch.recurseSubmodules=false', '-c', 'core.fsmonitor=false',
        'clone', '--bare', '--depth', '1', '--no-local', '--', url, destination]


def clone_archive(guard_image, git_image, url, address):
    args = pinned_args(url, address)
    # An empty worktree on a bare clone bypasses repository export-ignore and
    # export-subst attributes. The script is fixed; URL is a positional arg.
    script = ('mkdir /tmp/export && "$@" && '
        '/usr/bin/git --git-dir=/tmp/repository.git ' + ' '.join(ARCHIVE_ARGS))
    code, archive, _ = run_network(guard_image, git_image,
        ['/bin/sh', '-c', script, 'straz-git-export', *args],
        [(str(ipaddress.ip_address(address)), urlsplit(url).port or 443)],
        timeout=90, memory_mib=256)
    if code != 0:
        raise RuntimeError('Isolated repository acquisition failed')
    validate(archive)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as source:
        commit = source.pax_headers.get('comment', '')
    if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', commit):
        raise RuntimeError('Missing immutable repository snapshot identity')
    return {'archive': archive, 'commit': commit}
