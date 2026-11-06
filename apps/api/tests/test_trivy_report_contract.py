import json

import pytest

from app.services.scanners import _parse_trivy_json


@pytest.mark.parametrize('results', [None, {}, '', False, [None], [{}],
    [{'Target': 'fixture', 'Vulnerabilities': {}}],
    [{'Target': 'fixture', 'Vulnerabilities': [None]}],
    [{'Target': 'fixture', 'Vulnerabilities': [{}]}],
    [{'Target': 'fixture', 'Vulnerabilities': [{'VulnerabilityID': 'CVE-fixture',
        'PkgName': 'fixture', 'Severity': 'unexpected'}]}]])
def test_invalid_results_never_mean_clean(results):
    with pytest.raises(RuntimeError):
        _parse_trivy_json(json.dumps({'Results': results}), 'private diagnostic', 0, 'fixture')


@pytest.mark.parametrize('results', [[], [{'Target': 'fixture'}],
    [{'Target': 'fixture', 'Vulnerabilities': []}]])
def test_valid_empty_collections(results):
    assert _parse_trivy_json(json.dumps({'Results': results}), '', 0, 'fixture') == []


def test_critical_finding_remains_critical():
    payload = {'Results': [{'Target': 'fixture', 'Vulnerabilities': [{
        'VulnerabilityID': 'CVE-fixture', 'PkgName': 'fixture', 'Severity': 'CRITICAL'}]}]}
    findings = _parse_trivy_json(json.dumps(payload), '', 0, 'fixture')
    assert len(findings) == 1 and findings[0].severity == 'critical'
