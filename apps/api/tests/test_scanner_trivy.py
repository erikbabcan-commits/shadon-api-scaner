from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_trivy')


@pytest.mark.parametrize('hours', [-1, 80])
def test_future_or_stale_database_rejected(adapter, hours):
    updated = datetime.now(timezone.utc) - timedelta(hours=hours)
    raw = json.dumps({'Version': 2, 'UpdatedAt': updated.isoformat(),
                      'NextUpdate': (updated + timedelta(hours=6)).isoformat()}).encode()
    with pytest.raises(RuntimeError):
        adapter.database_metadata(raw)


def test_fresh_database_metadata(adapter):
    now = datetime.now(timezone.utc)
    raw = json.dumps({'Version': 2, 'UpdatedAt': now.isoformat(),
                      'NextUpdate': (now + timedelta(hours=6)).isoformat()}).encode()
    assert adapter.database_metadata(raw)['updated_at'] == now.isoformat()


@pytest.mark.parametrize('report', [{}, {'SchemaVersion': 2, 'Results': []},
    {'SchemaVersion': 2, 'Results': [{}]}, {'SchemaVersion': 2, 'Results': None}])
def test_absent_coverage_never_means_clean(adapter, report):
    with pytest.raises(RuntimeError):
        adapter.parse_report(0, json.dumps(report).encode())


def test_real_critical_severity_preserved(adapter):
    report = {'SchemaVersion': 2, 'Results': [{'Target': 'package-lock.json',
        'Vulnerabilities': [{'VulnerabilityID': 'CVE-fixture', 'PkgName': 'fixture',
                             'Severity': 'CRITICAL', 'Description': 'untrusted description'}]}]}
    result = adapter.parse_report(0, json.dumps(report).encode())
    assert result['findings'] == [{'vulnerability_id': 'CVE-fixture', 'package': 'fixture', 'severity': 'critical'}]
