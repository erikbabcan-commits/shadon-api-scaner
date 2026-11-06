"""Build pinned TLSX/HTTPX images twice on the approved Linux AMD64 host.

Only the initial official release download uses the network. Both image builds
use an existing digest-pinned base, no RUN instructions, no cache and no network.
This operator tool accepts a fixed tool name, never a tenant URL or Dockerfile.
"""
import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import tarfile
from urllib.parse import urlsplit
import urllib.request
import zipfile

BASE = 'busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_BINARY = 128 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    name: str
    version: str
    checksum: str

    @property
    def url(self):
        return (f'https://github.com/projectdiscovery/{self.name}/releases/download/'
                f'v{self.version}/{self.name}_{self.version}_linux_amd64.zip')

    @property
    def license_name(self):
        return {'tlsx': 'LICENSE', 'httpx': 'LICENSE.md'}[self.name]


RELEASES = {
    'tlsx': Release('tlsx', '1.1.9', '4b2480ca7be1dadf45ca9e861f3ea1147b56b976fe39f62fe1efa8c40ff8dec7'),
    'httpx': Release('httpx', '1.6.10', 'e7eb8473530c2d0eb4eb132c7253c0138745d622970f36413c1f349ddd60edb7'),
}


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise RuntimeError('Release redirect must use HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(release):
    opener = urllib.request.build_opener(HTTPSRedirects())
    with opener.open(release.url, timeout=30) as response:
        if urlsplit(response.url).scheme != 'https':
            raise RuntimeError('Release response must use HTTPS')
        return response.read(MAX_ARCHIVE + 1)


def validate_elf(binary):
    """Require a static little-endian Linux-compatible ELF64 x86-64 executable."""
    if len(binary) < 64 or len(binary) > MAX_BINARY or binary[:7] != b'\x7fELF\x02\x01\x01':
        raise RuntimeError('Invalid scanner ELF header')
    kind, machine, version = struct.unpack_from('<HHI', binary, 16)
    offset = struct.unpack_from('<Q', binary, 32)[0]
    size, count = struct.unpack_from('<HH', binary, 54)
    if (kind not in (2, 3) or machine != 62 or version != 1 or size != 56
        or not 1 <= count <= 256 or offset < 64 or offset + size * count > len(binary)):
        raise RuntimeError('Invalid scanner architecture or program headers')
    kinds = [struct.unpack_from('<I', binary, offset + size * i)[0] for i in range(count)]
    if 3 in kinds or 1 not in kinds:
        raise RuntimeError('Scanner must be static and contain a loadable segment')


def verified_member(payload, release, name, limit, minimum):
    if (not isinstance(payload, bytes) or len(payload) > MAX_ARCHIVE
        or hashlib.sha256(payload).hexdigest() != release.checksum):
        raise RuntimeError('Release checksum or size mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            matches = [m for m in members if m.filename == name]
            if len(members) > 256 or len(matches) != 1:
                raise RuntimeError('Missing or duplicated release member')
            member = matches[0]
            mode = member.external_attr >> 16
            if (member.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                or member.flag_bits & 1 or not minimum <= member.file_size <= limit):
                raise RuntimeError('Invalid release member')
            with archive.open(member) as source:
                content = source.read(limit + 1)
            if len(content) != member.file_size:
                raise RuntimeError('Truncated release member')
    except (zipfile.BadZipFile, NotImplementedError, ValueError, OSError):
        raise RuntimeError('Invalid scanner release archive') from None
    return content


def verified_binary(payload, release):
    binary = verified_member(payload, release, release.name, MAX_BINARY, 64)
    validate_elf(binary)
    return binary


def verified_license(payload, release):
    notice = verified_member(payload, release, release.license_name, 64 * 1024, 20)
    try:
        if '\x00' in notice.decode('utf-8'):
            raise ValueError('Invalid license text')
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid release license') from None
    return notice


def build_context(release, binary, notice):
    # An in-memory normalized tar avoids caller paths, uid/gid and file mtimes.
    validate_elf(binary)
    # COPY creates destination directories with current timestamps. SOURCE_DATE_EPOCH
    # alone only normalizes config/history; image rewrite conflicts with some
    # Docker exporters. ADD our own tar with explicit directory timestamps instead.
    filesystem = io.BytesIO()
    with tarfile.open(fileobj=filesystem, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in ['.', 'usr', 'usr/local', 'usr/local/bin', 'usr/share',
                     'usr/share/licenses', 'usr/share/licenses/' + release.name]:
            member = tarfile.TarInfo(name)
            member.type, member.mode = tarfile.DIRTYPE, 0o755
            member.uid = member.gid = member.mtime = 0
            archive.addfile(member)
        for name, content, mode in [(f'usr/local/bin/{release.name}', binary, 0o755),
                                    (f'usr/share/licenses/{release.name}/LICENSE', notice, 0o644)]:
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), mode
            member.uid = member.gid = member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    dockerfile = (f'FROM {BASE}\nADD filesystem.tar /\n'
                  'USER 10001:10001\nENV HOME=/tmp\n').encode()
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, content in [('Dockerfile', dockerfile), ('filesystem.tar', filesystem.getvalue())]:
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), 0o644
            member.uid = member.gid = member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    return data.getvalue()


def build_once(context):
    env = {**os.environ, 'DOCKER_BUILDKIT': '1'}
    result = subprocess.run(['docker', 'build', '--platform=linux/amd64', '--network=none',
        '--pull=false', '--no-cache', '--build-arg', 'SOURCE_DATE_EPOCH=0',
        '--provenance=false', '--sbom=false', '--quiet', '-'],
        input=context, capture_output=True, timeout=180, env=env)
    if result.returncode:
        raise RuntimeError('Scanner image build failed')
    rows = result.stdout.decode('ascii', errors='replace').strip().splitlines()
    if not rows or not re.fullmatch(r'sha256:[a-f0-9]{64}', rows[-1]):
        raise RuntimeError('Invalid built image identity')
    return rows[-1]


def build(release):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('Require the approved Linux AMD64 runner host')
    base = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Os}} {{.Architecture}} {{.Id}}', BASE],
                          capture_output=True, text=True, timeout=15)
    if base.returncode or not re.fullmatch(r'linux amd64 sha256:[a-f0-9]{64}\n?', base.stdout):
        raise RuntimeError('Approved local AMD64 base image is unavailable')
    # Keep a safety margin on the selected small shared VPS. Never prune here.
    storage = subprocess.run(['docker', 'info', '--format', '{{.DockerRootDir}}'],
                             capture_output=True, text=True, timeout=15)
    directory = storage.stdout.strip()
    if storage.returncode or not directory.startswith('/'):
        raise RuntimeError('Docker storage is unavailable')
    usage = shutil.disk_usage(directory)
    if usage.free < max(1024 ** 3, usage.total // 20):
        raise RuntimeError('Docker storage is critical; require at least 1 GiB and 5 percent free')
    payload = download(release)
    binary = verified_binary(payload, release)
    notice = verified_license(payload, release)
    context = build_context(release, binary, notice)
    first, second = build_once(context), build_once(context)
    if first != second:
        raise RuntimeError('Independent uncached builds have different image IDs')
    return {'tool': release.name, 'version': release.version, 'release_url': release.url,
            'release_sha256': release.checksum, 'binary_sha256': hashlib.sha256(binary).hexdigest(),
            'license_sha256': hashlib.sha256(notice).hexdigest(),
            'base': BASE, 'base_image_id': base.stdout.strip().split()[-1],
            'context_sha256': hashlib.sha256(context).hexdigest(),
            'image': first, 'uncached_builds': 2, 'matching_image_ids': True,
            'scope': 'Same selected host/BuildKit reproduction; no cross-builder or runtime acceptance claim'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool', choices=sorted(RELEASES))
    args = parser.parse_args()
    try:
        print(json.dumps(build(RELEASES[args.tool])))
    except (RuntimeError, OSError, subprocess.SubprocessError, EOFError):
        # Never forward Docker output, environment values or redirect URLs.
        parser.exit(1, 'Pinned scanner build failed; no image approved.\n')


if __name__ == '__main__':
    main()
