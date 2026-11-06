"""Trusted Linux-host supervisor for a policy-ready guard, not scanner activation.

Use only an operator-approved immutable image. The app worker never receives
Docker access. A scanner may join the returned container network namespace only
after entry succeeds; the caller must separately enforce its execution sandbox.
"""
from contextlib import contextmanager
import json
import re
import subprocess
import uuid

from scanner_namespace import install_policy
from scanner_policy import compile_policy


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()


@contextmanager
def policy_guard(image_id, endpoints):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
        raise ValueError('Require an approved immutable local guard image')
    endpoints = tuple(endpoints)
    compile_policy(endpoints)  # Reject invalid inputs before creating resources.
    docker('image', 'inspect', image_id)  # Never pull a missing image.
    job = uuid.uuid4().hex
    name = 'straz-guard-' + job
    try:
        # The default bridge has no embedded DNS proxy rules in its namespace.
        # Only trusted sleep runs before policy; no job input is mounted here.
        container = docker('run', '--detach', '--pull', 'never', '--name', name,
            '--label', 'straz.guard=' + job, '--network', 'bridge',
            '--read-only', '--user', '10001:10001', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '64m',
            '--memory-swap', '64m', '--cpus', '0.1', '--pids-limit', '8',
            '--ipc', 'none', '--log-driver', 'none', '--entrypoint', '/bin/sleep',
            image_id, '1200')
        info = json.loads(docker('inspect', name))[0]
        if (info['Id'] != container or info['Image'] != image_id
            or info['Config'].get('Labels', {}).get('straz.guard') != job
            or not info['State']['Running'] or info['HostConfig']['NetworkMode'] != 'bridge'):
            raise RuntimeError('Guard identity verification failed')
        pid = info['State']['Pid']
        proof = install_policy(pid, endpoints)
        # Do not return a handle if the container exited or changed identity.
        current = json.loads(docker('inspect', name))[0]
        if current['Id'] != container or not current['State']['Running'] or current['State']['Pid'] != pid:
            raise RuntimeError('Guard changed during policy installation')
        yield {'container_id': container, 'policy': proof}
    finally:
        # A timed-out create/run may have succeeded in the daemon. Discover by
        # our unguessable ownership label even when no container ID returned.
        owned = docker('ps', '--all', '--no-trunc', '--filter', 'label=straz.guard=' + job,
                       '--format', '{{.ID}}').splitlines()
        for container in owned:
            if not re.fullmatch(r'[a-f0-9]{64}', container):
                raise RuntimeError('Unexpected cleanup identity')
            docker('rm', '--force', container)
