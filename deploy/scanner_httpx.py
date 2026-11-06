"""Trusted single-endpoint HTTP observation, no redirects or scheme fallback."""
import ipaddress
import json
import re
from urllib.parse import urlsplit

from scanner_network import run_network
from scanner_policy import compile_policy


def scan(guard_image, scanner_image, hostname, address, port=443, path='/'):
    if (not isinstance(hostname, str) or len(hostname) > 253
        or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', part)
                   for part in hostname.split('.'))):
        raise ValueError('Invalid authorized HTTP hostname')
    if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
        or len(path) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in path)
        or '?' in path or '#' in path or '\\' in path):
        raise ValueError('Require a public path without query or fragment')
    address = str(ipaddress.ip_address(address))
    compile_policy([(address, port)])
    authority = '[' + address + ']' if ':' in address else address
    url = f'https://{authority}:{port}{path}'
    host_header = hostname if port == 443 else f'{hostname}:{port}'
    code, raw, _ = run_network(guard_image, scanner_image, ['/usr/local/bin/httpx',
        '-u', url, '-sni', hostname, '-H', 'Host: ' + host_header,
        '-json', '-silent', '-duc', '-no-stdin', '-nfs', '-sc', '-ob',
        '-threads', '1', '-retries', '0', '-timeout', '10', '-rstr', '131072'],
        [(address, port)], timeout=30, memory_mib=256)
    return parse_report(code, raw, address, port)


def parse_report(code, raw, address, port):
    if code != 0 or len(raw) > 4 * 1024 * 1024:
        raise RuntimeError('HTTP scanner execution failed')
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid HTTP scanner report') from None
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError('Incomplete HTTP scanner report')
    row = rows[0]
    try:
        url = urlsplit(row['url'])
        matched = url.scheme == 'https' and url.hostname == address and (url.port or 443) == port
    except (KeyError, ValueError, TypeError, AttributeError):
        raise RuntimeError('Invalid HTTP scanner destination') from None
    status = row.get('status_code')
    if (not matched or row.get('failed') or type(status) is not int
        or not 100 <= status <= 599):
        raise RuntimeError('HTTP probe failed or destination changed')
    return {'status_code': status, 'findings': [
        {'rule_id': 'http-server-error', 'severity': 'high'}] if status >= 500 else []}
