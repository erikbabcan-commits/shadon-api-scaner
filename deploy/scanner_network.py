"""Trusted network scanner supervisor, never a tenant command interface.

Only operator-approved adapters select images, executables and arguments.
Destinations are resolved/authorized separately; this enforces exact IP/ports.
"""
import math
import re
import uuid

from scanner_guard import docker, policy_guard
from scanner_process import run_bounded


def run_network(guard_image, scanner_image, argv, endpoints, data=b'', *, timeout=30,
                max_output=4 * 1024 * 1024):
    if any(not re.fullmatch(r'sha256:[a-f0-9]{64}', value)
           for value in (guard_image, scanner_image)):
        raise ValueError('Require approved immutable local images')
    if (not isinstance(argv, (list, tuple)) or not argv
        or any(not isinstance(arg, str) or '\x00' in arg for arg in argv)
        or not argv[0].startswith('/')):
        raise ValueError('Require a trusted absolute scanner executable')
    if not isinstance(data, bytes) or len(data) > 1024 * 1024:
        raise ValueError('Scanner input exceeds limit')
    if (not math.isfinite(timeout) or not 0 < timeout <= 900
        or type(max_output) is not int or not 0 < max_output <= 4 * 1024 * 1024):
        raise ValueError('Invalid scanner limits')
    docker('image', 'inspect', scanner_image)
    with policy_guard(guard_image, endpoints) as guard:
        container = guard['container_id']
        if not re.fullmatch(r'[a-f0-9]{64}', container):
            raise RuntimeError('Invalid verified guard identity')
        job = uuid.uuid4().hex
        try:
            return run_bounded(['docker', 'run', '--interactive', '--pull', 'never',
                '--name', 'straz-network-' + job, '--label', 'straz.network=' + job,
                '--network', 'container:' + container, '--read-only',
                '--user', '10001:10001', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--memory', '128m',
                '--memory-swap', '128m', '--cpus', '0.5', '--pids-limit', '32',
                '--ipc', 'none', '--log-driver', 'none',
                '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m',
                '--entrypoint', argv[0], scanner_image, *argv[1:]], data,
                timeout=timeout, max_output=max_output)
        finally:
            owned = docker('ps', '--all', '--no-trunc', '--filter',
                           'label=straz.network=' + job, '--format', '{{.ID}}').splitlines()
            for identity in owned:
                if not re.fullmatch(r'[a-f0-9]{64}', identity):
                    raise RuntimeError('Unexpected cleanup identity')
                docker('rm', '--force', identity)
