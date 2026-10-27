import json
from pathlib import Path


def test_frontend_csp_remains_report_only_until_browser_acceptance():
    root = Path(__file__).resolve().parents[3]
    policies = []
    for path in (root / "vercel.json", root / "apps/web/vercel.json"):
        config = json.loads(path.read_text())
        headers = {h["key"].lower(): h["value"]
                   for rule in config["headers"] if rule["source"] == "/(.*)"
                   for h in rule["headers"]}
        assert "content-security-policy" not in headers
        policy = headers["content-security-policy-report-only"]
        directives = {part.strip().split()[0]: part.strip().split()[1:]
                      for part in policy.split(";") if part.strip()}
        assert directives["default-src"] == ["'self'"]
        assert directives["object-src"] == ["'none'"]
        assert "'unsafe-eval'" not in directives["script-src"]
        assert "'self'" in directives["connect-src"]
        assert "https://straz-api-production.up.railway.app" in directives["connect-src"]
        policies.append(policy)
    assert policies[0] == policies[1]
