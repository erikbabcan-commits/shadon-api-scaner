"""Bounded binary pipes for the trusted scanner supervisor (POSIX only).

The caller owns container cleanup; killing a Docker client alone does not stop
its container. Output-limit and timeout failures never return partial success.
"""
import math
import os
import selectors
import signal
import subprocess
import time


def run_bounded(argv, data=b'', *, timeout=30, max_output=4 * 1024 * 1024,
                max_input=1024 * 1024):
    if type(max_input) is not int or max_input not in (1024 * 1024, 4 * 1024 * 1024):
        raise ValueError('Invalid approved scanner input limit')
    if not isinstance(data, bytes) or len(data) > max_input:
        raise ValueError('Scanner input exceeds limit')
    if not math.isfinite(timeout) or timeout <= 0 or type(max_output) is not int or max_output <= 0:
        raise ValueError('Invalid scanner limits')
    output = [bytearray(), bytearray()]
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            for index, stream in enumerate((process.stdout, process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, None)
            else:
                process.stdin.close()
            offset = 0
            total = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Scanner execution timed out')
                for key, _ in selector.select(min(remaining, 0.1)):
                    if key.data is None:
                        try:
                            offset += os.write(key.fd, data[offset:offset + 65536])
                        except BrokenPipeError:
                            offset = len(data)
                        if offset == len(data):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, min(65536, max_output - total + 1))
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > max_output:
                            raise RuntimeError('Scanner output exceeds limit')
                        output[key.data].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Scanner execution timed out')
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise TimeoutError('Scanner execution timed out') from None
            return code, bytes(output[0]), bytes(output[1])
    finally:
        # Descendants may retain pipes or survive the immediate parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
