"""Trusted supervisor job dispatch, not a public or authenticated service.

Application admission must authorize tenant/target/quota before calling this.
Images belong to operator configuration; jobs cannot choose commands or images.
"""
import base64
import binascii
import ipaddress
import re
import socket
import uuid

import scanner_gitleaks
import scanner_git
import scanner_httpx
import scanner_naabu
import scanner_tlsx
import scanner_trivy
from scanner_policy import compile_policy


def resolve_target(hostname, port):
    if (not isinstance(hostname, str) or len(hostname) > 253
        or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', part)
                   for part in hostname.split('.'))):
        raise ValueError('Invalid authorized hostname')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid authorized port')
    answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    addresses = {str(ipaddress.ip_address(answer[4][0])) for answer in answers}
    # Reject mixed public/private answers, not merely the first selected answer.
    compile_policy([(address, port) for address in addresses])
    return sorted(addresses, key=lambda address: (ipaddress.ip_address(address).version, address))


def execute(job, images):
    if not isinstance(job, dict) or job.get('version') != 1 or type(job.get('version')) is not int:
        raise ValueError('Invalid scanner job version')
    try:
        identity = str(uuid.UUID(job['job_id']))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError('Invalid scanner job identity') from None
    if identity != job['job_id']:
        raise ValueError('Require canonical scanner job identity')
    profile = job.get('profile')
    if profile not in ('tls', 'http', 'gitleaks', 'ports', 'trivy_fs'):
        raise ValueError('Unsupported isolated profile')
    repository = profile in ('gitleaks', 'trivy_fs') and 'repository_url' in job
    if profile == 'trivy_fs' and not repository:
        raise ValueError('Dependency job requires an authorized repository')
    payload_field = ('repository_url' if repository else 'source_base64') if profile in ('gitleaks', 'trivy_fs') else 'target'
    expected = {'version', 'job_id', 'profile', payload_field}
    if set(job) != expected:
        raise ValueError('Unexpected scanner job fields')
    keys = ('guard', 'git', profile) if repository else ((profile,) if profile == 'gitleaks' else ('guard', profile))
    if (not isinstance(images, dict) or any(not isinstance(images.get(key), str)
        or not re.fullmatch(r'sha256:[a-f0-9]{64}', images[key]) for key in keys)):
        raise ValueError('Missing approved immutable scanner image')
    if repository:
        host, port = scanner_git.repository_endpoint(job['repository_url'])
        addresses = resolve_target(host, port)
        snapshot = scanner_git.clone_archive(images['guard'], images['git'],
                                             job['repository_url'], addresses[0])
        if profile == 'gitleaks':
            result = {'scope': 'repository_head', 'commit': snapshot['commit'],
                      'findings': scanner_gitleaks.scan_archive(images[profile], snapshot['archive'])}
        else:
            result = scanner_trivy.scan_archive(images[profile], snapshot['archive'])
            result['repository_commit'] = snapshot['commit']
    elif profile == 'gitleaks':
        encoded = job['source_base64']
        if not isinstance(encoded, str) or len(encoded) > 1398104:
            raise ValueError('Invalid scanner source input')
        try:
            source = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Invalid scanner source encoding') from None
        if len(source) > 1024 * 1024:
            raise ValueError('Scanner source exceeds limit')
        result = {'findings': scanner_gitleaks.scan(images[profile], source)}
    else:
        target = job['target']
        required = {'hostname', 'ports'} if profile == 'ports' else {'hostname', 'port'}
        allowed = required | {'path'} if profile == 'http' else required
        if not isinstance(target, dict) or not required <= set(target) or set(target) - allowed:
            raise ValueError('Invalid authorized scanner target')
        if profile == 'ports':
            ports = scanner_naabu.validated_ports(target['ports'])
            addresses = resolve_target(target['hostname'], ports[0])
            result = {'endpoints': [scanner_naabu.scan(images['guard'], images[profile],
                address, ports) for address in addresses]}
        else:
            addresses = resolve_target(target['hostname'], target['port'])
            adapter = scanner_tlsx if profile == 'tls' else scanner_httpx
            extra = {'path': target.get('path', '/')} if profile == 'http' else {}
            # All resolved endpoints must complete. Never return partial success.
            result = {'endpoints': [adapter.scan(images['guard'], images[profile],
                target['hostname'], address, target['port'], **extra) for address in addresses]}
    return {'version': 1, 'job_id': identity, 'profile': profile,
            'observations_complete': True, 'result': result}
