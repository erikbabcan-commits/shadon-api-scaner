"""Validate a bounded uncompressed source tar without extracting on the host."""
import io
from pathlib import PurePosixPath
import tarfile

LIMIT = 4 * 1024 * 1024


def validate(archive):
    if not isinstance(archive, bytes) or not archive or len(archive) > LIMIT:
        raise ValueError('Invalid source archive size')
    total = 0
    names = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as source:
            for member in source:
                path = PurePosixPath(member.name)
                if (not member.name or len(member.name) > 1024 or path.is_absolute()
                    or '..' in path.parts or '\\' in member.name or str(path) == '.'
                    or any(ord(c) < 32 for c in member.name)
                    or not (member.isfile() or member.isdir()) or member.mode & 0o7000
                    or str(path) in names or len(names) >= 8192):
                    raise ValueError('Unsafe source archive member')
                names.add(str(path))
                total += member.size
                if member.size < 0 or total > LIMIT:
                    raise ValueError('Source archive exceeds expanded size limit')
                if member.isfile():
                    stream = source.extractfile(member)
                    if stream is None:
                        raise ValueError('Missing source archive content')
                    with stream:
                        if len(stream.read(member.size + 1)) != member.size:
                            raise ValueError('Truncated source archive')
    except (tarfile.TarError, OSError, EOFError):
        raise ValueError('Invalid source archive') from None
    if not names:
        raise ValueError('Empty source archive')
