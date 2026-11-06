"""Offline vulnerability observations for supported dependency files only."""
from datetime import datetime, timedelta, timezone
import json

from scanner_archive import validate
from scanner_offline import run_offline


def database_metadata(raw):
    try:
        if len(raw) > 8192:
            raise ValueError('Metadata exceeds limit')
        data = json.loads(raw)
        if type(data['Version']) is not int or data['Version'] != 2:
            raise ValueError('Unsupported database schema')
        updated = datetime.fromisoformat(data['UpdatedAt'].replace('Z', '+00:00'))
        next_update = datetime.fromisoformat(data['NextUpdate'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        if (updated.tzinfo is None or next_update.tzinfo is None
            or updated > now + timedelta(minutes=5) or updated < now - timedelta(hours=72)
            or next_update < updated or next_update < now - timedelta(hours=24)):
            raise ValueError('Vulnerability database is stale or invalid')
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        raise RuntimeError('Trivy database metadata is missing stale or invalid') from None
    return {'updated_at': updated.isoformat(), 'next_update': next_update.isoformat()}


def scan_archive(image_id, archive):
    validate(archive)
    code, raw, _ = run_offline(image_id, ['/bin/cat', '/opt/trivy-cache/db/metadata.json'])
    if code:
        raise RuntimeError('Trivy database metadata unavailable')
    metadata = database_metadata(raw)
    command = ('mkdir /tmp/source && tar -xf - -C /tmp/source && '
        "printf '{}\\n' > /tmp/approved.yaml && "
        'exec /usr/local/bin/trivy fs --config /tmp/approved.yaml --ignorefile /dev/null '
        '--scanners vuln --offline-scan --skip-db-update --skip-java-db-update '
        '--skip-check-update --cache-dir /opt/trivy-cache --cache-backend memory '
        '--parallel 1 --quiet --format json /tmp/source')
    code, raw, _ = run_offline(image_id, ['/bin/sh', '-c', command], archive,
                              timeout=120, max_input=4 * 1024 * 1024, memory_mib=256)
    result = parse_report(code, raw)
    result['database'] = metadata
    return result


def parse_report(code, raw):
    if code != 0 or len(raw) > 4 * 1024 * 1024:
        raise RuntimeError('Offline Trivy execution failed')
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid offline Trivy report') from None
    if (not isinstance(report, dict) or report.get('SchemaVersion') != 2
        or not isinstance(report.get('Results'), list) or not report['Results']):
        raise RuntimeError('No complete dependency coverage report')
    findings = []
    severities = {'UNKNOWN': 'info', 'LOW': 'low', 'MEDIUM': 'medium', 'HIGH': 'high', 'CRITICAL': 'critical'}
    for result in report['Results']:
        if (not isinstance(result, dict) or not isinstance(result.get('Target'), str)
            or not result['Target'] or not isinstance(result.get('Vulnerabilities', []), list)):
            raise RuntimeError('Invalid dependency result')
        for vuln in result.get('Vulnerabilities', []):
            if (not isinstance(vuln, dict)
                or not isinstance(vuln.get('Severity'), str) or vuln['Severity'] not in severities
                or any(not isinstance(vuln.get(key), str) or not 1 <= len(vuln[key]) <= 256
                       for key in ('VulnerabilityID', 'PkgName'))):
                raise RuntimeError('Invalid dependency vulnerability')
            finding = {'vulnerability_id': vuln['VulnerabilityID'], 'package': vuln['PkgName'],
                       'severity': severities[vuln['Severity']]}
            for field, output in (('InstalledVersion', 'installed_version'), ('FixedVersion', 'fixed_version')):
                if field in vuln:
                    if not isinstance(vuln[field], str) or len(vuln[field]) > 1024:
                        raise RuntimeError('Invalid dependency version metadata')
                    finding[output] = vuln[field]
            findings.append(finding)
    return {'scope': 'supported_dependency_files', 'analyzed_targets': len(report['Results']),
            'findings': findings}
