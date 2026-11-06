import importlib
import io
from pathlib import Path
import tarfile

import pytest


@pytest.fixture
def archive(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_archive')


def bundle(name='src/fixture.txt', kind=tarfile.REGTYPE):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as tar:
        item = tarfile.TarInfo(name)
        item.type = kind
        if kind == tarfile.REGTYPE:
            item.size = 7
            tar.addfile(item, io.BytesIO(b'fixture'))
        else:
            item.linkname = '/etc/passwd'
            tar.addfile(item)
    return output.getvalue()


@pytest.mark.parametrize('name', ['/tmp/escape', '../escape', 'src/../../escape', 'src\\escape', '.'])
def test_unsafe_paths_rejected(archive, name):
    with pytest.raises(ValueError):
        archive.validate(bundle(name))


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_links_and_special_files_rejected(archive, kind):
    with pytest.raises(ValueError):
        archive.validate(bundle(kind=kind))


def test_regular_source_validates_without_extracting(archive, tmp_path):
    assert archive.validate(bundle()) is None
    assert list(tmp_path.iterdir()) == []


def test_oversize_and_corrupt_archives_rejected(archive):
    for data in (b'not tar', b'x' * (archive.LIMIT + 1)):
        with pytest.raises(ValueError):
            archive.validate(data)
