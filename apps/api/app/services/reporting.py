from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import App, Finding, FindingSeverity, Organization
from app.services.compliance import (
    calculate_security_score,
    evaluate_nis2_areas,
    map_owasp_top_10,
)
from app.services.quota import get_plan_tier


def redact_sensitive_text(text: str | None) -> str | None:
    if not text:
        return text
    # Redact common tokens, passwords, bearer secrets
    redacted = re.sub(r"(bearer\s+)[a-zA-Z0-9_\-\.]{15,}", r"\1[REDACTED]", text, flags=re.I)
    redacted = re.sub(r"(password['\":\s=]+)[^\s,}\"']+", r"\1[REDACTED]", redacted, flags=re.I)
    redacted = re.sub(r"(api[_-]?key['\":\s=]+)[^\s,}\"']+", r"\1[REDACTED]", redacted, flags=re.I)
    redacted = re.sub(r"(secret['\":\s=]+)[^\s,}\"']+", r"\1[REDACTED]", redacted, flags=re.I)
    return redacted


def generate_html_report(
    app: App,
    org: Organization,
    findings: list[Finding],
) -> str:
    report_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc)
    tier = get_plan_tier(org)

    is_white_label = tier in ("pro", "agency")
    brand_color = org.brand_color if (is_white_label and org.brand_color) else "#0284c7"
    logo_url = org.custom_logo_url if (is_white_label and org.custom_logo_url) else None
    footer_text = (
        org.report_footer_text
        if (is_white_label and org.report_footer_text)
        else "Vygenerované bezpečnostnou platformou Stráž Security Intelligence • Certifikovaný export pre audit a compliance."
    )

    scoring = calculate_security_score(findings, app)
    nis2_areas = evaluate_nis2_areas(findings, app)
    owasp_counts = map_owasp_top_10(findings)

    # Prepare snapshot data and SHA-256 integrity hash
    manifest_data = {
        "report_id": report_id,
        "app_id": str(app.id),
        "app_name": app.name,
        "base_url": app.base_url,
        "organization_id": str(org.id),
        "organization_name": org.name,
        "generated_at": generated_at.isoformat(),
        "score": scoring["score"],
        "grade": scoring["grade"],
        "total_open_findings": scoring["open_counts"]["total"],
    }
    manifest_json = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"))
    sha256_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

    # Build findings HTML rows
    findings_rows = []
    for f in sorted(
        findings,
        key=lambda x: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x.severity.value, 5)
        ),
    ):
        sev_badge_color = {
            "critical": "background:#ef4444;color:#fff;",
            "high": "background:#f97316;color:#fff;",
            "medium": "background:#eab308;color:#000;",
            "low": "background:#3b82f6;color:#fff;",
            "info": "background:#64748b;color:#fff;",
        }.get(f.severity.value, "background:#64748b;color:#fff;")

        safe_title = html.escape(f.title or "Nález")
        safe_detail = html.escape(redact_sensitive_text(f.detail) or "Bez podrobností")
        safe_source = html.escape(f.source.value if hasattr(f.source, "value") else str(f.source))

        findings_rows.append(
            f"""
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:10px;page-break-inside:avoid;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-weight:700;font-size:14px;color:#0f172a;">{safe_title}</span>
                    <span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;text-transform:uppercase;{sev_badge_color}">
                        {f.severity.value}
                    </span>
                </div>
                <div style="font-size:12px;color:#475569;margin-bottom:6px;">
                    <strong>Zdroj:</strong> {safe_source} | <strong>Stav:</strong> {f.status.value}
                </div>
                <div style="font-size:12px;color:#334155;background:#f8fafc;padding:8px;border-radius:6px;font-family:monospace;white-space:pre-wrap;">
                    {safe_detail}
                </div>
            </div>
            """
        )

    # Build NIS2 rows
    nis2_rows = []
    for area in nis2_areas:
        status_color = "#10b981" if area["status"] == "COMPLIANT" else ("#f59e0b" if area["status"] == "WARNING" else "#ef4444")
        nis2_rows.append(
            f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px;font-weight:600;font-size:13px;color:#1e293b;">{html.escape(area['name'])}</td>
                <td style="padding:10px;font-size:12px;color:#64748b;">{html.escape(area['iso_ref'])}</td>
                <td style="padding:10px;text-align:right;">
                    <span style="background:{status_color};color:#fff;font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;">
                        {area['status']}
                    </span>
                </td>
            </tr>
            """
        )

    # Build OWASP rows
    owasp_rows = []
    for cat, count in owasp_counts.items():
        if count > 0:
            owasp_rows.append(
                f"""
                <tr style="border-bottom:1px solid #e2e8f0;">
                    <td style="padding:8px 10px;font-size:13px;color:#1e293b;">{html.escape(cat)}</td>
                    <td style="padding:8px 10px;text-align:right;font-weight:700;font-size:13px;color:#ef4444;">{count}</td>
                </tr>
                """
            )

    html_content = f"""<!DOCTYPE html>
<html lang="sk">
<head>
    <meta charset="utf-8">
    <title>Executive Security Audit — {html.escape(app.name)}</title>
    <meta name="report-sha256" content="{sha256_hash}">
    <style>
        @page {{
            size: A4 portrait;
            margin: 12mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
            background: #fff;
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }}
        .header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid {brand_color};
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        .score-box {{
            display: flex;
            align-items: center;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .grade-badge {{
            font-size: 42px;
            font-weight: 900;
            width: 80px;
            height: 80px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: {scoring['color']};
            color: #fff;
            border-radius: 12px;
            margin-right: 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }}
        h2 {{
            font-size: 16px;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 6px;
            margin-top: 24px;
            color: #0f172a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            margin-bottom: 20px;
        }}
        .footer {{
            border-top: 1px solid #e2e8f0;
            margin-top: 40px;
            padding-top: 12px;
            font-size: 11px;
            color: #64748b;
            display: flex;
            justify-content: space-between;
        }}
        @media print {{
            body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .no-print {{ display: none !important; }}
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div>
            {f'<img src="{html.escape(logo_url)}" style="max-height:40px;margin-bottom:6px;" alt="Logo"/>' if logo_url else f'<h1 style="margin:0;font-size:24px;color:{brand_color};font-weight:800;">STRÁŽ INTELLIGENCE</h1>'}
            <div style="font-size:12px;color:#64748b;">Bezpečnostný audit a posúdenie zhody NIS2 / ISO 27001</div>
        </div>
        <div style="text-align:right;font-size:11px;color:#64748b;">
            <div><strong>Audit ID:</strong> {report_id[:8]}</div>
            <div><strong>Dátum:</strong> {generated_at.strftime('%d.%m.%Y %H:%M UTC')}</div>
            <div><strong>SHA-256:</strong> {sha256_hash[:16]}…</div>
        </div>
    </div>

    <div style="margin-bottom:20px;">
        <h1 style="margin:0 0 4px 0;font-size:22px;">{html.escape(app.name)}</h1>
        <div style="font-size:13px;color:#475569;">
            <strong>Cieľová URL:</strong> {html.escape(app.base_url)} | <strong>Prostredie:</strong> {html.escape(app.environment)} | <strong>Organizácia:</strong> {html.escape(org.name)}
        </div>
    </div>

    <div class="score-box">
        <div class="grade-badge">{scoring['grade']}</div>
        <div style="flex:1;">
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                <span style="font-size:18px;font-weight:700;">Celkový bezpečnostný index: {scoring['score']} %</span>
                <span style="font-size:13px;color:#64748b;">{scoring['open_counts']['total']} otvorených nálezov</span>
            </div>
            <div style="background:#e2e8f0;height:10px;border-radius:5px;overflow:hidden;">
                <div style="background:{scoring['color']};height:100%;width:{scoring['score']}%;"></div>
            </div>
            <div style="font-size:12px;color:#64748b;margin-top:8px;">
                Kritické: <strong style="color:#ef4444;">{scoring['open_counts']['critical']}</strong> • 
                Vysoké: <strong style="color:#f97316;">{scoring['open_counts']['high']}</strong> • 
                Stredné: <strong style="color:#eab308;">{scoring['open_counts']['medium']}</strong> • 
                Nízke / Info: <strong>{scoring['open_counts']['low'] + scoring['open_counts']['info']}</strong>
            </div>
        </div>
    </div>

    <h2>1. Vyhodnotenie súladu s európskou smernicou NIS2 (Článok 21)</h2>
    <table>
        <tbody>
            {''.join(nis2_rows)}
        </tbody>
    </table>

    {f'''<h2>2. Mapovanie bezpečnostných zlyhaní na OWASP Top 10</h2>
    <table>
        <tbody>
            {''.join(owasp_rows)}
        </tbody>
    </table>''' if owasp_rows else ''}

    <h2>3. Detail technických zraniteľností a odporúčané nápravy</h2>
    {''.join(findings_rows) if findings_rows else '<p style="color:#10b981;font-weight:600;font-size:14px;">Neboli zistené žiadne aktívne zraniteľnosti. Systém spĺňa štandardy bezpečnostnej hygieny.</p>'}

    <div class="footer">
        <div>{html.escape(footer_text)}</div>
        <div>Overovací hash záznamu: {sha256_hash}</div>
    </div>

    <script class="no-print">
        window.addEventListener('load', function() {{
            setTimeout(function() {{
                window.print();
            }}, 400);
        }});
    </script>
</body>
</html>
"""
    return html_content
