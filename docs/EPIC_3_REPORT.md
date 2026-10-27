> Historický implementačný report; nie dôkaz aktuálneho nasadenia alebo dostupnosti profilov. Aktuálny rozsah a stav: [NOTION_NOTES.md](../NOTION_NOTES.md).

# EPIC 3 — Executive Reporting, Compliance Indicators and White Label Report

## Overview
EPIC 3 delivers executive-ready reporting, automated compliance scoring (A+ to F), Article 21 NIS2 indicator mapping, OWASP Top 10 breakdown, and white-label branding for Pro and Agency organizations.

## Scoring & Compliance Engine
- **Algorithm (`app/services/compliance.py`)**:
  - Score baseline: 100 points.
  - Critical finding: -35 points.
  - High finding: -15 points.
  - Medium finding: -5 points.
  - Expiration (SSL / Domain) within 21 days: -10 points.
  - Expired SSL or domain / App downtime: Forced F (<40 points).
  - Scale: 95–100 (A+), 85–94 (A), 75–84 (B), 60–74 (C), 40–59 (D), <40 (F).
- **NIS2 Article 21 Technical Areas**:
  1. Network & Cryptographic Security (TLS, RDAP, DNS).
  2. Vulnerability & Exposure Management (Nuclei, Naabu, InternetDB).
  3. Supply Chain Security (Trivy FS/Image, Gitleaks).
  4. Availability & Incident Monitoring (Heartbeat, HTTPX status).
- **OWASP Top 10 (2021/2025 crosswalk)**: Automatic heuristic classification of active findings.

## Print-Ready Report & Integrity
- **Generator (`app/services/reporting.py`)**:
  - Pure CSS print styling: `@page { size: A4 portrait; margin: 12mm; }`, page breaks (`page-break-inside: avoid;`).
  - No heavy serverless Chromium or headless browser runtime required.
  - Automatic `window.print()` trigger on load.
  - Cryptographic snapshot verification: Non-executable JSON manifest and SHA-256 integrity hash embedded in document metadata and footer.
  - Automatic redaction of sensitive credentials, tokens, and secrets.

## White-Label Branding
- Custom agency logo URL, custom primary color (`#hex`), custom audit footer text.
- Restricted to Pro and Agency tiers (HTTP 402 with `X-Upgrade-Required` on Free/Starter).

## Frontend Components
- `CompliancePanel.tsx`: Visual grade badge, score progress bar, NIS2 checklist, one-click PDF export button.
- `BrandingSettings.tsx`: In-app customization form with live color picker.
