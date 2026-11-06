"""Trusted supervisor entry point for offline scanner execution.

Only trusted profile adapters may choose image/argv. This is not an HTTP API;
never pass arbitrary tenant commands here. Images must already exist locally.
"""
import re
import uuid

from scanner_guard import docker
from scanner_process import run_bounded


def run_offline(image_id, argv, data=b'', *, timeout=30, max_output=4 * 1024 * 1024,
                max_input=1024 * 1024, memory_mib=128):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
        raise ValueError('Require an approved immutable local scanner image')
    if (not isinstance(argv, (list, tuple)) or not argv
        or any(not isinstance(arg, str) or '\x00' in arg for arg in argv)
        or not argv[0].startswith('/')):
        raise ValueError('Require a trusted absolute scanner executable')
    if type(max_input) is not int or max_input not in (1024 * 1024, 4 * 1024 * 1024):
        raise ValueError('Invalid approved scanner input limit')
    if not isinstance(data, bytes) or len(data) > max_input:
        raise ValueError('Scanner input exceeds limit')
    if type(memory_mib) is not int or memory_mib not in (128, 256):
        raise ValueError('Invalid approved scanner memory limit')
    docker('image', 'inspect', image_id)
    job = uuid.uuid4().hex
    try:
        return run_bounded(['docker', 'run', '--interactive', '--pull', 'never',
            '--name', 'straz-offline-' + job, '--label', 'straz.offline=' + job,
            '--network', 'none', '--read-only', '--user', '10001:10001',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', f'{memory_mib}m', '--memory-swap', f'{memory_mib}m', '--cpus', '0.5',
            '--pids-limit', '32', '--ipc', 'none', '--log-driver', 'none',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m',
            '--entrypoint', argv[0], image_id, *argv[1:]], data,
            timeout=timeout, max_output=max_output, max_input=max_input)
    finally:
        # Discover even if Docker created the container but its client failed.
        owned = docker('ps', '--all', '--no-trunc', '--filter',
                       'label=straz.offline=' + job, '--format', '{{.ID}}').splitlines()
        for container in owned:
            if not re.fullmatch(r'[a-f0-9]{64}', container):
                raise RuntimeError('Unexpected cleanup identity')
            docker('rm', '--force', container)
