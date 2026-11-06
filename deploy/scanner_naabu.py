"""Bounded TCP connect observations on explicit authorized public ports.

Absence from open_ports is not proof of a closed port or a secure service.
"""
import ipaddress
import json

from scanner_network import run_network
from scanner_policy import compile_policy


def validated_ports(ports):
    if (not isinstance(ports, (list, tuple)) or not 1 <= len(ports) <= 64
        or any(type(port) is not int or not 1 <= port <= 65535 for port in ports)):
        raise ValueError('Require 1..64 explicit authorized TCP ports')
    return sorted(set(ports))


def scan(guard_image, scanner_image, address, ports):
    ports = validated_ports(ports)
    address = str(ipaddress.ip_address(address))
    endpoints = [(address, port) for port in ports]
    compile_policy(endpoints)
    code, raw, _ = run_network(guard_image, scanner_image, ['/usr/local/bin/naabu',
        '-host', address, '-p', ','.join(map(str, ports)), '-s', 'c', '-Pn',
        '-c', '1', '-rate', '10', '-retries', '1', '-timeout', '1000',
        '-warm-up-time', '0', '-json', '-silent', '-duc', '-no-stdin'],
        endpoints, timeout=90, memory_mib=256)
    return parse_report(code, raw, address, ports)


def parse_report(code, raw, address, ports):
    if code != 0 or len(raw) > 4 * 1024 * 1024:
        raise RuntimeError('TCP connect scanner execution failed')
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid TCP connect scanner report') from None
    open_ports = set()
    for row in rows:
        if (not isinstance(row, dict) or row.get('ip') != address
            or type(row.get('port')) is not int or row['port'] not in ports
            or row.get('protocol', 'tcp') != 'tcp'):
            raise RuntimeError('Unexpected TCP connect scanner result')
        open_ports.add(row['port'])
    return {'scope': 'tcp_connect_observation', 'tested_ports': ports,
            'open_ports': sorted(open_ports), 'findings': [
                {'rule_id': 'tcp-port-open', 'port': port, 'severity': 'info'}
                for port in sorted(open_ports)]}
