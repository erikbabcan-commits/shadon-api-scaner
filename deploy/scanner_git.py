"""Build trusted, pinned HTTPS Git acquisition commands.

The caller must authorize this repository, resolve its hostname, and run the
command only inside the matching network guard. No credentials are accepted.
"""
import ipaddress
import re
from urllib.parse import urlsplit

from scanner_policy import compile_policy


def pinned_args(url, address, *, destination='/tmp/repository.git'):
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
    address = str(ipaddress.ip_address(address))
    port = parsed.port or 443
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
