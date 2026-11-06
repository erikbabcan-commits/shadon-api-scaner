"""Build the approved offline Gitleaks image on the Linux AMD64 runner host.

Downloads only the pinned official release, verifies before extracting a single
binary, and never pulls the already-approved base image. No application deploy.
"""
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import urllib.request

VERSION = '8.30.1'
CHECKSUM = '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
BASE = 'busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662'


def main():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('Require the approved Linux AMD64 runner host')
    subprocess.run(['docker', 'image', 'inspect', BASE], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    with tempfile.TemporaryDirectory(prefix='straz-gitleaks-build-') as directory:
        root = Path(directory)
        archive = root / 'release.tar.gz'
        url = f'https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_linux_x64.tar.gz'
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read(32 * 1024 * 1024 + 1)
        if len(payload) > 32 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != CHECKSUM:
            raise RuntimeError('Release checksum or size mismatch')
        archive.write_bytes(payload)
        with tarfile.open(archive) as release:
            member = release.getmember('gitleaks')
            if not member.isfile() or member.size > 64 * 1024 * 1024:
                raise RuntimeError('Invalid release binary')
            stream = release.extractfile(member)
            if stream is None:
                raise RuntimeError('Missing release binary')
            with stream:
                (root / 'gitleaks').write_bytes(stream.read())
        archive.unlink()
        (root / 'gitleaks').chmod(0o755)
        (root / 'Dockerfile').write_text(f'FROM {BASE}\n'
            'COPY gitleaks /usr/local/bin/gitleaks\nUSER 10001:10001\n'
            'ENTRYPOINT ["/usr/local/bin/gitleaks"]\n')
        result = subprocess.run(['docker', 'build', '--network=none', '--pull=false',
            '--quiet', str(root)], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError('Scanner image build failed')
        image = result.stdout.strip().splitlines()[-1]
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise RuntimeError('Invalid built image identity')
        print(json.dumps({'image': image, 'version': VERSION, 'release_sha256': CHECKSUM}))


if __name__ == '__main__':
    main()
