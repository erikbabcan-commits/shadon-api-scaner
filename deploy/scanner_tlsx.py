"""Trusted TLS adapter: one authorized public IP/port and explicit SNI.

Caller authorizes the hostname and resolves its IP before invoking this code.
No DNS or redirect egress is opened in the scanner namespace.
"""
from datetime import datetime, timezone
import ipaddress
import json
import re

from scanner_network import run_network
from scanner_policy import compile_policy


def scan(guard_image, scanner_image, hostname, address, port=443):
    if (not isinstance(hostname, str) or len(hostname) > 253
        or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
                   for label in hostname.split('.'))):
        raise ValueError('Invalid authorized TLS hostname')
    address = str(ipaddress.ip_address(address))
    compile_policy([(address, port)])
    code, raw, _ = run_network(guard_image, scanner_image, ['/usr/local/bin/tlsx',
        '-u', address, '-p', str(port), '-sni', hostname, '-json', '-silent',
        '-duc', '-sm', 'ctls', '-c', '1', '-retry', '1', '-timeout', '5',
        '-tps', '-ex', '-ss'], [(address, port)], timeout=30)
    return parse_report(code, raw, address, port, hostname)


def parse_report(code, raw, address, port, hostname):
    if code != 0 or len(raw) > 4 * 1024 * 1024:
        raise RuntimeError('TLS scanner execution failed')
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid TLS scanner report') from None
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError('Incomplete TLS scanner report')
    row = rows[0]
    if (row.get('probe_status') is not True or row.get('error')
        or row.get('ip', row.get('host')) != address or row.get('port') != str(port)):
        raise RuntimeError('TLS probe failed or destination changed')
    try:
        expires = datetime.fromisoformat(row['not_after'].replace('Z', '+00:00'))
        if expires.tzinfo is None:
            raise ValueError('Missing timezone')
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RuntimeError('Invalid TLS certificate expiry') from None
    flags = {}
    for name in ('expired', 'self_signed'):
        value = row.get(name, False)
        if type(value) is not bool:
            raise RuntimeError('Invalid TLS certificate flag')
        flags[name] = value
    # tlsx compares against its IP input; SNI alone does not change that check.
    # Match DNS SANs against the authorized hostname instead of that IP flag.
    # Only a complete leftmost wildcard label is accepted, never partial/glob.
    names = row.get('subject_an', [])
    common_name = row.get('subject_cn', '')
    if (not isinstance(names, list) or any(not isinstance(n, str) for n in names)
        or not isinstance(common_name, str) or not (names or common_name)):
        raise RuntimeError('Missing TLS certificate names')
    if not names:
        raise RuntimeError('Missing TLS DNS subject alternative names')
    host_labels = hostname.lower().split('.')
    def matches(name):
        labels = name.lower().split('.')
        if '*' not in name:
            return labels == host_labels
        return (len(labels) >= 3 and labels[0] == '*' and len(labels) == len(host_labels)
                and '*' not in '.'.join(labels[1:]) and labels[1:] == host_labels[1:])
    flags['mismatched'] = not any(matches(name) for name in names)
    days_left = (expires - datetime.now(timezone.utc)).days
    findings = []
    if flags['expired'] or days_left < 0:
        findings.append({'rule_id': 'tls-expired', 'severity': 'high'})
    elif days_left < 21:
        findings.append({'rule_id': 'tls-expiring', 'severity': 'medium'})
    for field in ('mismatched', 'self_signed'):
        if flags[field]:
            findings.append({'rule_id': 'tls-' + field.replace('_', '-'), 'severity': 'high'})
    return {'not_after': expires.isoformat(), 'findings': findings}
