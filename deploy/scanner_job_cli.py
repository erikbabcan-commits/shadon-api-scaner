"""One trusted scanner job per stdin/stdout invocation; never open a listener.

An authenticated private transport and application admission remain mandatory.
The operator image configuration contains image IDs, never job-chosen commands.
"""
import argparse
import json
from pathlib import Path
import signal
import sys

from scanner_job import execute

MAX_REQUEST = 2 * 1024 * 1024
FAILURE = {'version': 1, 'observations_complete': False, 'error': 'scanner_job_failed'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def serve(input_stream, output_stream, images):
    try:
        raw = input_stream.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError('Scanner request exceeds limit')
        job = json.loads(raw, object_pairs_hook=unique_object)
        result = execute(job, images)
        encoded = json.dumps(result, separators=(',', ':')).encode()
        if len(encoded) > 4 * 1024 * 1024:
            raise RuntimeError('Scanner response exceeds limit')
    except Exception:
        # Never echo request data, exception messages, paths, or tool stderr.
        output_stream.write(json.dumps(FAILURE).encode() + b'\n')
        output_stream.flush()
        return 1
    output_stream.write(encoded + b'\n')
    output_stream.flush()
    return 0


def interrupted(signum, frame):
    # Unwind scanner/guard finally blocks on ordinary transport termination.
    raise InterruptedError('Scanner job interrupted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images-file', type=Path, required=True)
    args = parser.parse_args()
    for name in ('SIGTERM', 'SIGINT', 'SIGHUP', 'SIGALRM'):
        signal.signal(getattr(signal, name), interrupted)
    signal.setitimer(signal.ITIMER_REAL, 300)
    try:
        with args.images_file.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError('Invalid operator image configuration')
        images = json.loads(raw, object_pairs_hook=unique_object)
        return serve(sys.stdin.buffer, sys.stdout.buffer, images)
    except Exception:
        sys.stdout.buffer.write(json.dumps(FAILURE).encode() + b'\n')
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    raise SystemExit(main())
