#!/usr/bin/env python3
"""Compile an endpoint allowlist for a NEW scanner network namespace only.

This module never executes nft or changes host networking. A supervisor must
apply and verify it before starting an unprivileged scanner in that namespace.
"""
import argparse
import ipaddress


def compile_policy(endpoints):
    endpoints = list(endpoints)
    if not 1 <= len(endpoints) <= 64:
        raise ValueError('Require 1..64 authorized endpoint pairs')
    approved = set()
    for value, port in endpoints:
        address = ipaddress.ip_address(value)
        if getattr(address, 'scope_id', None):
            raise ValueError('Scoped addresses are not accepted')
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Only public unicast addresses and valid TCP ports are accepted')
        approved.add((address.version, str(address), port))
    rules = ['table inet straz_scanner {',
             ' chain output { type filter hook output priority -10; policy drop;']
    for version, address, port in sorted(approved):
        family = 'ip' if version == 4 else 'ip6'
        rules.append(f'  {family} daddr {address} tcp dport {port} ct state new,established accept')
    if any(version == 6 for version, _, _ in approved):
        rules.append('  ip6 hoplimit 255 icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert } accept')
    rules.extend([' }', ' chain input { type filter hook input priority -10; policy drop;',
                  '  ct state established,related accept'])
    if any(version == 6 for version, _, _ in approved):
        rules.append('  ip6 hoplimit 255 icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert } accept')
    rules.extend([' }', ' chain forward { type filter hook forward priority -10; policy drop; }', '}'])
    return '\n'.join(rules) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', action='append', nargs=2, required=True, metavar=('PUBLIC_IP', 'TCP_PORT'))
    args = parser.parse_args()
    print(compile_policy([(ip, int(port)) for ip, port in args.endpoint]), end='')
