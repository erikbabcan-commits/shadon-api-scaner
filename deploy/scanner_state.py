"""Conservative local supervisor admission and durable job receipts.

One shared private state directory is mandatory for every supervisor process.
Running/failed receipts require operator reconciliation, never automatic replay.
This is not tenant authorization or application quota accounting.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

from scanner_guard import docker
from scanner_job import execute

MAX_STATE_ENTRIES = 10000


def check_capacity(root):
    usage = shutil.disk_usage(root)
    # Reserve enough space for bounded result + atomic replacement as well as
    # the host's critical floor. This is admission, never automatic retention.
    if usage.free < max(1024 ** 3, usage.total // 20) + 8 * 1024 ** 2:
        raise RuntimeError('Scanner state storage is critical')
    with os.scandir(root) as entries:
        for count, _ in enumerate(entries, 1):
            if count >= MAX_STATE_ENTRIES:
                raise RuntimeError('Scanner state requires operator retention')


def check_private(info):
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError('Require private operator-owned runner state')


def save(root, path, record):
    descriptor, temporary = tempfile.mkstemp(prefix='.receipt-', dir=root)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(record, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute_once(job, images, state_dir):
    try:
        identity = str(uuid.UUID(job['job_id']))
        if identity != job['job_id']:
            raise ValueError('Noncanonical ID')
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError('Invalid scanner job identity') from None
    digest = hashlib.sha256(json.dumps({'job': job, 'images': images},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    root = Path(state_dir)
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError('Runner state must be a private directory')
    check_private(info)
    descriptor = os.open(root / 'supervisor.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        check_private(os.fstat(descriptor))
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = root / (identity + '.json')
        try:
            cached_fd = os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            cached_fd = None
        if cached_fd is not None:
            with os.fdopen(cached_fd, 'rb') as stream:
                check_private(os.fstat(stream.fileno()))
                raw = stream.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise RuntimeError('Invalid scanner receipt')
            cached = json.loads(raw)
            if cached['request_sha256'] != digest:
                raise RuntimeError('Scanner job identity already used for different input')
            if cached['status'] != 'complete':
                raise RuntimeError('Scanner job requires operator reconciliation')
            return cached['response']
        check_capacity(root)
        # A previous crashed client may have left daemon-owned containers. Do
        # not release more work merely because its OS file lock disappeared.
        for label in ('straz.guard', 'straz.offline', 'straz.network'):
            if docker('ps', '--all', '--filter', 'label=' + label, '--format', '{{.ID}}'):
                raise RuntimeError('Scanner containers require operator reconciliation')
        record = {'request_sha256': digest, 'status': 'running'}
        save(root, receipt, record)  # Durable intent before any scanner starts.
        try:
            result = execute(job, images)
            if len(json.dumps(result).encode()) > 4 * 1024 * 1024:
                raise RuntimeError('Scanner response exceeds limit')
        except BaseException:
            save(root, receipt, {**record, 'status': 'failed'})
            raise
        save(root, receipt, {**record, 'status': 'complete', 'response': result})
        return result
    finally:
        os.close(descriptor)  # flock is released only after execution/cleanup.
