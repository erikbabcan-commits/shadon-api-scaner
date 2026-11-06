#!/usr/bin/env python3
"""Probe an offline Docker sandbox. This does not enable any scanner profile."""
import argparse
import json
import re
import subprocess
import uuid

PROBE = """
import errno,json,os,socket
from pathlib import Path
status=Path('/proc/self/status').read_text()
checks={'nonroot':os.getuid()==10001,
 'no_new_privileges':'NoNewPrivs:\\t1' in status,
 'capabilities_dropped':'CapEff:\\t0000000000000000' in status,
 'seccomp_enabled':'Seccomp:\\t2' in status,
 'docker_socket_absent':not Path('/var/run/docker.sock').exists(),
 'application_credentials_absent':not any(k in os.environ for k in ('DATABASE_URL','REDIS_URL','STRAZ_SESSION_SECRET','STRAZ_ADMIN_PASSWORD')),
 'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text().strip()=='134217728',
 'pid_limit':Path('/sys/fs/cgroup/pids.max').read_text().strip()=='32',
 'cpu_limit':Path('/sys/fs/cgroup/cpu.max').read_text().split()==['50000','100000'],
 'only_loopback_interface':sorted(p.name for p in Path('/sys/class/net').iterdir())==['lo']}
try:Path('/sandbox-write-probe').write_text('fixture')
except OSError as e:checks['readonly_root']=e.errno==errno.EROFS
else:checks['readonly_root']=False
with socket.socket() as s:
 s.settimeout(1)
 try:s.connect(('192.0.2.1',443))
 except OSError as e:checks['network_unreachable']=e.errno==errno.ENETUNREACH
 else:checks['network_unreachable']=False
print(json.dumps(checks))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--image', required=True, help='Existing trusted local sha256 image ID with Python')
    args = parser.parse_args()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', args.image):
        parser.error('An immutable local image ID is required')
    docker = ['docker', '--context', args.context]
    name = 'straz-sandbox-probe-' + uuid.uuid4().hex
    subprocess.run([*docker, 'image', 'inspect', args.image], check=True, capture_output=True)
    try:
        result = subprocess.run([*docker, 'run', '--name', name, '--pull', 'never',
            '--network', 'none', '--read-only', '--user', '10001:10001',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', '128m', '--memory-swap', '128m', '--cpus', '0.5',
            '--pids-limit', '32', '--ipc', 'none', '--log-driver', 'none',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
            '--entrypoint', 'python', args.image, '-c', PROBE],
            capture_output=True, text=True, timeout=60, check=True)
        checks = json.loads(result.stdout)
        inspected = subprocess.run([*docker, 'inspect', name], check=True,
                                   capture_output=True, text=True)
        host = json.loads(inspected.stdout)[0]['HostConfig']
        checks['network_mode_none'] = host['NetworkMode'] == 'none'
        checks['private_pid_namespace'] = host['PidMode'] == ''
        checks['no_host_mounts'] = not host.get('Binds') and not host.get('Mounts')
        print(json.dumps({'checks': checks, 'all_passed': all(checks.values()),
            'scope': 'Offline sandbox prerequisite only; no online egress policy or scanner functionality proven'}))
        if not all(checks.values()):
            raise SystemExit(1)
    finally:
        cleanup = subprocess.run([*docker, 'rm', '--force', name], capture_output=True)
        if cleanup.returncode:
            raise RuntimeError('Owned probe cleanup not confirmed')


if __name__ == '__main__':
    main()
