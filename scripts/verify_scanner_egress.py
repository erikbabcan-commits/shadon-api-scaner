#!/usr/bin/env python3
"""Linux-only wire fixture. Run ONLY via unshare --net; policy comes on stdin.

All addresses below belong to private disposable namespaces, not the Internet.
No host interfaces, routes, firewall rules, services or files are modified.
"""
import json
import os
import select
import signal
import socket
import subprocess
import sys
import time


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=10, **kwargs)


def main():
    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('Refusing to run in the host network namespace')
    policy = sys.stdin.read()
    if not policy.strip():
        raise RuntimeError('Missing compiled policy')
    peer = subprocess.Popen(['unshare', '--net', 'sleep', '120'], start_new_session=True)
    server = None
    try:
        for _ in range(100):
            if peer.poll() is not None:
                raise RuntimeError('Fixture namespace creation failed')
            if os.readlink(f'/proc/{peer.pid}/ns/net') != os.readlink('/proc/self/ns/net'):
                break
            time.sleep(.01)
        else:
            raise RuntimeError('Fixture namespace did not become ready')
        def sink(*args):
            return command('nsenter', '-t', str(peer.pid), '-n', *args)
        command('ip', 'link', 'add', 'qa-client', 'type', 'veth', 'peer', 'name', 'qa-sink')
        command('ip', 'link', 'set', 'qa-sink', 'netns', str(peer.pid))
        command('ip', 'addr', 'add', '198.51.100.2/24', 'dev', 'qa-client')
        command('ip', 'link', 'set', 'qa-client', 'up')
        command('ip', 'link', 'set', 'lo', 'up')
        sink('ip', 'addr', 'add', '198.51.100.1/24', 'dev', 'qa-sink')
        sink('ip', 'link', 'set', 'qa-sink', 'up')
        sink('ip', 'link', 'set', 'lo', 'up')
        for address in ('1.1.1.1', '8.8.8.8', '10.0.0.1', '169.254.169.254'):
            sink('ip', 'addr', 'add', address + '/32', 'dev', 'lo')
            command('ip', 'route', 'add', address + '/32', 'via', '198.51.100.1')
        receiver = """
import selectors,socket
s=selectors.DefaultSelector()
for port in (443,8443):
 listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
 listener.bind(('0.0.0.0',port));listener.listen();s.register(listener,selectors.EVENT_READ)
print('READY',flush=True)
while True:
 for key,_ in s.select():
  c,_=key.fileobj.accept();c.sendall(b'fixture');c.close()
"""
        server = subprocess.Popen(['nsenter', '-t', str(peer.pid), '-n', 'python3', '-u', '-c', receiver],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        if not select.select([server.stdout], [], [], 5)[0] or server.stdout.readline().strip() != b'READY':
            raise RuntimeError('Fixture receiver did not start')
        def connects(address, port):
            try:
                with socket.create_connection((address, port), timeout=.5) as connection:
                    return connection.recv(16) == b'fixture'
            except OSError:
                return False
        cases = [('1.1.1.1',443),('1.1.1.1',8443),('8.8.8.8',443),('10.0.0.1',443),('169.254.169.254',443)]
        if not all(connects(*case) for case in cases):
            raise RuntimeError('Baseline receivers unreachable; negative checks would be meaningless')
        command('nft', '--check', '-f', '-', input=policy.encode())
        command('nft', '-f', '-', input=policy.encode())
        checks = {'baseline_all_reachable': True, 'allowed_endpoint_reachable': connects(*cases[0])}
        checks.update({label: not connects(*case) for label,case in zip(
            ('wrong_port_blocked','other_public_ip_blocked','private_ip_blocked','metadata_ip_blocked'),cases[1:])})
        print(json.dumps({'checks':checks,'all_passed':all(checks.values()),
                          'scope':'IPv4 TCP wire fixture only; no scanner integration or IPv6 wire proof'}))
        if not all(checks.values()):
            raise RuntimeError('Egress enforcement failed')
    finally:
        for process in (server,peer):
            if process is not None:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
