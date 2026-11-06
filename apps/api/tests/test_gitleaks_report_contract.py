import json

import pytest

from app.services import scanners


@pytest.mark.parametrize('report,code', [(None, 0), (None, 1), (b'[]', 1),
    (b'null', 0), (b'not-json', 0), (b'\xff', 0), (b'[{}]', 1), (b'[]', 2)])
async def test_missing_malformed_or_inconsistent_report_fails(tmp_path, monkeypatch, report, code):
    monkeypatch.setattr(scanners, 'which', lambda _: '/fixture/gitleaks')
    async def run(*args, **kwargs):
        if report is not None:
            (tmp_path / 'gitleaks-report.json').write_bytes(report)
        return code, '', 'untrusted diagnostic'
    monkeypatch.setattr(scanners, '_run_cmd', run)
    with pytest.raises(RuntimeError) as error:
        await scanners.run_gitleaks(tmp_path / 'repo')
    assert 'untrusted diagnostic' not in str(error.value)
    assert not (tmp_path / 'gitleaks-report.json').exists()


async def test_oversized_report_is_bounded_and_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(scanners, 'which', lambda _: '/fixture/gitleaks')
    monkeypatch.setattr(scanners, 'SCANNER_OUTPUT_LIMIT_BYTES', 32)
    async def run(*args, **kwargs):
        (tmp_path / 'gitleaks-report.json').write_bytes(b' ' * 33)
        return 0, '', ''
    monkeypatch.setattr(scanners, '_run_cmd', run)
    with pytest.raises(RuntimeError, match='exceeds limit'):
        await scanners.run_gitleaks(tmp_path / 'repo')
    assert not (tmp_path / 'gitleaks-report.json').exists()


async def test_stale_clean_report_cannot_mask_missing_new_report(tmp_path, monkeypatch):
    monkeypatch.setattr(scanners, 'which', lambda _: '/fixture/gitleaks')
    (tmp_path / 'gitleaks-report.json').write_text('[]')
    async def run(*args, **kwargs):
        return 0, '', ''
    monkeypatch.setattr(scanners, '_run_cmd', run)
    with pytest.raises(RuntimeError, match='complete results'):
        await scanners.run_gitleaks(tmp_path / 'repo')


@pytest.mark.parametrize('found', [False, True])
async def test_complete_clean_and_redacted_finding_reports(tmp_path, monkeypatch, found):
    monkeypatch.setattr(scanners, 'which', lambda _: '/fixture/gitleaks')
    async def run(*args, **kwargs):
        rows = [{'RuleID': 'fixture-rule', 'File': 'fixture.txt', 'StartLine': 2,
                 'Secret': 'synthetic-sensitive-value', 'Match': 'synthetic-source'}] if found else []
        (tmp_path / 'gitleaks-report.json').write_text(json.dumps(rows))
        return int(found), '', ''
    monkeypatch.setattr(scanners, '_run_cmd', run)
    result = await scanners.run_gitleaks(tmp_path / 'repo')
    assert len(result) == int(found)
    assert 'synthetic-sensitive-value' not in repr(result)
    assert 'synthetic-source' not in repr(result)
