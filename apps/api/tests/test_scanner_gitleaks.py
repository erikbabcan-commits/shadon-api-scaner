import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'deploy'))
    return importlib.import_module('scanner_gitleaks')


def test_only_allowlisted_metadata_survives(adapter):
    row = {'RuleID': 'github-pat', 'StartLine': 1, 'EndLine': 1,
           'Secret': 'sensitive fixture', 'Match': 'source fixture',
           'Description': 'untrusted description', 'File': 'private-path',
           'Fingerprint': 'private identity', 'Email': 'private-contact'}
    assert adapter.parse_report(1, json.dumps([row]).encode()) == [
        {'rule_id': 'github-pat', 'start_line': 1, 'end_line': 1, 'severity': 'high'}]


@pytest.mark.parametrize('code,report', [(2, b'[]'), (1, b'[]'), (0, b'null'),
    (0, b'not-json'), (1, b'[{}]'), (0, b'[{"RuleID":"x"}]')])
def test_failure_or_inconsistent_report_never_means_clean(adapter, code, report):
    with pytest.raises(RuntimeError):
        adapter.parse_report(code, report)


def test_clean_report(adapter):
    assert adapter.parse_report(0, b'[]') == []
