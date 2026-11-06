"""Run on the approved Linux Docker host with an approved local image ID.

Uses only generated synthetic input; creates no production scan or DB record.
Does not pull/build images. Output contains proof metadata, never the token.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))

from scanner_gitleaks import scan  # noqa: E402
from scanner_guard import docker  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-id', required=True)
    args = parser.parse_args()
    before = set(docker('ps', '--no-trunc', '--format', '{{.ID}}').splitlines())
    token = 'ghp_' + secrets.token_hex(18)
    if scan(args.image_id, b'clean synthetic fixture') != []:
        raise RuntimeError('Clean fixture failed')
    findings = scan(args.image_id, ('token="' + token + '"\n').encode())
    if len(findings) != 1 or findings[0]['rule_id'] != 'github-pat':
        raise RuntimeError('Synthetic detection failed')
    if token in json.dumps(findings):
        raise RuntimeError('Output redaction failed')
    after = set(docker('ps', '--no-trunc', '--format', '{{.ID}}').splitlines())
    if not before.issubset(after):
        raise RuntimeError('Existing container availability changed')
    print(json.dumps({'image': args.image_id, 'clean_case': True,
        'synthetic_detection': True, 'returned_secret_absent': True,
        'existing_containers_still_running': True,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'deploy').glob('scanner_*.py')}}))


if __name__ == '__main__':
    main()
