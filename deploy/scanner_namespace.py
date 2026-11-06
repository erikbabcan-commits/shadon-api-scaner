"""Privileged supervisor primitive; never callable by an untrusted scanner.

The caller must prove that pid belongs to its own newly created guard container.
The namespace FD pins that namespace across PID exit/reuse during configuration.
No host firewall fallback is permitted.
"""
import os
import subprocess

from scanner_policy import compile_policy


def install_policy(pid, endpoints):
    if type(pid) is not int or pid <= 1:
        raise ValueError('A verified guard PID greater than 1 is required')
    policy = compile_policy(endpoints)
    namespace = os.open(f'/proc/{pid}/ns/net', os.O_RDONLY | os.O_CLOEXEC)
    try:
        host = os.stat('/proc/1/ns/net')
        target = os.fstat(namespace)
        if (host.st_dev, host.st_ino) == (target.st_dev, target.st_ino):
            raise RuntimeError('Refusing the host network namespace')
        def nft(*args, **kwargs):
            return subprocess.run(['nsenter', f'--net=/proc/self/fd/{namespace}', 'nft', *args],
                pass_fds=(namespace,), check=True, capture_output=True, timeout=10, **kwargs)
        import json
        before = json.loads(nft('-j', 'list', 'ruleset').stdout)
        if any(set(item) - {'metainfo'} for item in before['nftables']):
            raise RuntimeError('Require a fresh namespace with no pre-existing firewall rules')
        nft('--check', '-f', '-', input=policy.encode())
        nft('-f', '-', input=policy.encode())
        after = json.loads(nft('-j', 'list', 'table', 'inet', 'straz_scanner').stdout)
        chains = [item['chain'] for item in after['nftables'] if 'chain' in item]
        if {c['name'] for c in chains} != {'input', 'output', 'forward'} or any(
            c.get('policy') != 'drop' or c.get('prio') != -10 for c in chains
        ):
            raise RuntimeError('Installed firewall verification failed; do not start scanner')
        return {'namespace_pinned': True, 'host_namespace_rejected': True,
                'fresh_ruleset_required': True, 'kernel_drop_chains_verified': True}
    finally:
        os.close(namespace)
