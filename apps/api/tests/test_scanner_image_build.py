import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import struct
import sys
import tarfile
import warnings
import zipfile

import pytest


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[3] / 'scripts/build_scanner_projectdiscovery.py'
    spec = importlib.util.spec_from_file_location('scanner_image_builder_fixture', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def elf(*, machine=62, segment=1):
    content = bytearray(120)
    content[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', content, 16, 2, machine, 1)
    struct.pack_into('<Q', content, 32, 64)
    struct.pack_into('<HH', content, 54, 56, 1)
    struct.pack_into('<I', content, 64, segment)
    return bytes(content)


def zipped(entries):
    data = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(data, 'w') as archive:
            for name, content, mode in entries:
                member = zipfile.ZipInfo(name)
                member.external_attr = mode << 16
                archive.writestr(member, content)
    return data.getvalue()


def release(builder, payload):
    return builder.Release('tlsx', '1.1.9', hashlib.sha256(payload).hexdigest())


def test_tampered_download_rejected_before_archive_read(builder):
    with pytest.raises(RuntimeError, match='checksum'):
        builder.verified_binary(b'changed upstream content', builder.RELEASES['tlsx'])


@pytest.mark.parametrize('entries', [
    [('tlsx', elf(), stat.S_IFREG | 0o755)] * 2,
    [('../tlsx', elf(), stat.S_IFREG | 0o755)],
    [('tlsx', elf(), stat.S_IFLNK | 0o777)],
    [('tlsx', b'truncated', stat.S_IFREG | 0o755)],
    [('tlsx', elf(machine=183), stat.S_IFREG | 0o755)],
    [('tlsx', elf(segment=3), stat.S_IFREG | 0o755)],
])
def test_unusable_or_ambiguous_binary_fails_closed(builder, entries):
    payload = zipped(entries)
    with pytest.raises(RuntimeError):
        builder.verified_binary(payload, release(builder, payload))


def test_unselected_archive_paths_are_never_extracted(builder, tmp_path, monkeypatch):
    working = tmp_path / 'work' / 'nested'
    working.mkdir(parents=True)
    monkeypatch.chdir(working)
    payload = zipped([('tlsx', elf(), stat.S_IFREG | 0o755),
                      ('../../outside', b'host write', stat.S_IFREG | 0o644)])
    assert builder.verified_binary(payload, release(builder, payload)) == elf()
    assert not (tmp_path / 'outside').exists()
    assert list(working.iterdir()) == []


def test_context_has_fixed_identity_and_only_selected_files(builder):
    selected = builder.RELEASES['tlsx']
    context = builder.build_context(selected, elf(), b'License fixture')
    assert context == builder.build_context(selected, elf(), b'License fixture')
    with tarfile.open(fileobj=io.BytesIO(context)) as archive:
        members = archive.getmembers()
        assert [m.name for m in members] == ['Dockerfile', 'filesystem.tar']
        assert all(m.uid == m.gid == m.mtime == 0 and m.isfile() for m in members)
        dockerfile = archive.extractfile('Dockerfile').read().decode()
        assert 'USER 10001:10001' in dockerfile and 'RUN ' not in dockerfile
        assert builder.BASE in dockerfile
        with tarfile.open(fileobj=io.BytesIO(archive.extractfile('filesystem.tar').read())) as fs:
            files = fs.getmembers()
            assert all(m.uid == m.gid == m.mtime == 0 and (m.isdir() or m.isfile()) for m in files)
            assert {m.name for m in files if m.isfile()} == {'usr/local/bin/tlsx', 'usr/share/licenses/tlsx/LICENSE'}
            assert fs.extractfile('usr/local/bin/tlsx').read() == elf()


def test_builder_rejects_different_uncached_results(builder, monkeypatch):
    class LocalBase:
        returncode = 0
        stdout = 'linux amd64 sha256:' + 'a' * 64 + '\n'
    monkeypatch.setattr(builder.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(builder.platform, 'machine', lambda: 'x86_64')
    class Storage:
        returncode = 0
        stdout = '/var/lib/docker\n'
    monkeypatch.setattr(builder.subprocess, 'run', lambda argv, **kw:
                        Storage() if argv[1] == 'info' else LocalBase())
    class Space:
        total = 20 * 1024 ** 3
        free = 1024 * 1024 * 1024
    monkeypatch.setattr(builder.shutil, 'disk_usage', lambda path: Space())
    payload = zipped([('tlsx', elf(), stat.S_IFREG | 0o755),
                      ('LICENSE', b'Approved license fixture text', stat.S_IFREG | 0o644)])
    monkeypatch.setattr(builder, 'download', lambda selected: payload)
    images = iter(['sha256:' + 'b' * 64, 'sha256:' + 'c' * 64])
    monkeypatch.setattr(builder, 'build_once', lambda context: next(images))
    with pytest.raises(RuntimeError, match='different image IDs'):
        builder.build(release(builder, payload))


@pytest.mark.parametrize('free', [117 * 1024 ** 2, 664 * 1024 ** 2, 1536 * 1024 ** 2])
def test_low_disk_fails_before_release_download(builder, monkeypatch, free):
    class Reply:
        returncode = 0
        stdout = ''
    def inspect(argv, **kwargs):
        reply = Reply()
        reply.stdout = '/var/lib/docker\n' if argv[1] == 'info' else 'linux amd64 sha256:' + 'a' * 64 + '\n'
        return reply
    class Space:
        total = 40 * 1024 ** 3
    space = Space()
    space.free = free
    monkeypatch.setattr(builder.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(builder.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(builder.subprocess, 'run', inspect)
    monkeypatch.setattr(builder.shutil, 'disk_usage', lambda path: space)
    monkeypatch.setattr(builder, 'download', lambda *args: pytest.fail('Must not download with low disk'))
    with pytest.raises(RuntimeError, match='storage is critical'):
        builder.build(builder.RELEASES['tlsx'])


def test_https_downgrade_is_rejected(builder):
    with pytest.raises(RuntimeError, match='HTTPS'):
        builder.HTTPSRedirects().redirect_request(None, None, 302, '', {}, 'http://example.invalid/release.zip')


@pytest.mark.parametrize('content,mode', [(b'', stat.S_IFREG),
    (b'License fixture with a NUL\x00', stat.S_IFREG),
    (b'License fixture symlink target', stat.S_IFLNK)])
def test_invalid_license_fails_closed(builder, content, mode):
    payload = zipped([('LICENSE', content, mode | 0o644)])
    with pytest.raises(RuntimeError):
        builder.verified_license(payload, release(builder, payload))
