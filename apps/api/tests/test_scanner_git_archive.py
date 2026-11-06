import importlib
import io
from pathlib import Path
import subprocess
import tarfile

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_git')


def test_export_ignore_cannot_remove_files_from_snapshot(adapter, tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    empty = tmp_path / 'export'
    empty.mkdir()
    def git(*args):
        return subprocess.run(['git', *map(str, args)], check=True, capture_output=True).stdout
    git('-C', work, 'init')
    (work / 'hidden.txt').write_text('synthetic fixture')
    (work / '.gitattributes').write_text('hidden.txt export-ignore\n')
    git('-C', work, 'add', '.')
    git('-C', work, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-m', 'synthetic fixture')
    bare = tmp_path / 'repository.git'
    git('clone', '--bare', work, bare)
    args = [arg.replace('/tmp/export', str(empty)) for arg in adapter.ARCHIVE_ARGS]
    raw = git('--git-dir=' + str(bare), *args)
    adapter.validate(raw)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        assert 'hidden.txt' in archive.getnames()
        assert archive.pax_headers['comment'].strip() == git('--git-dir=' + str(bare), 'rev-parse', 'HEAD').decode().strip()


def test_clone_failure_never_returns_archive(adapter, monkeypatch):
    monkeypatch.setattr(adapter, 'run_network', lambda *args, **kwargs: (1, b'', b'private diagnostic'))
    with pytest.raises(RuntimeError, match='acquisition failed'):
        adapter.clone_archive('guard', 'git', 'https://authorized.example/repo.git', '1.1.1.1')
