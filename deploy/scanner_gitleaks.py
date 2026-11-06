"""Offline stdin adapter; expose only fixed finding metadata, never source text."""
import json
import re

from scanner_offline import run_offline


def scan(image_id, data):
    code, stdout, _stderr = run_offline(image_id, ['/usr/local/bin/gitleaks',
        'stdin', '--report-format', 'json', '--report-path', '-', '--redact=100',
        '--no-banner', '--log-level', 'error', '--ignore-gitleaks-allow'], data)
    return parse_report(code, stdout)


def parse_report(code, raw):
    if code not in (0, 1) or len(raw) > 4 * 1024 * 1024:
        raise RuntimeError('Gitleaks execution failed')
    try:
        rows = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError('Invalid Gitleaks report') from None
    if not isinstance(rows, list) or len(rows) > 10000 or (code == 0) != (len(rows) == 0):
        raise RuntimeError('Inconsistent Gitleaks report')
    findings = []
    for row in rows:
        if (not isinstance(row, dict)
            or not isinstance(row.get('RuleID'), str)
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,127}', row['RuleID'])
            or type(row.get('StartLine')) is not int or row['StartLine'] < 1
            or type(row.get('EndLine')) is not int or row['EndLine'] < row['StartLine']):
            raise RuntimeError('Invalid Gitleaks finding')
        findings.append({'rule_id': row['RuleID'], 'start_line': row['StartLine'],
                         'end_line': row['EndLine'], 'severity': 'high'})
    return findings
