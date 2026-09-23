from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


@dataclass
class HeartbeatResult:
    ok: bool
    status_code: int | None
    latency_ms: float | None
    title: str | None
    error: str | None = None


@dataclass
class ToolFinding:
    title: str
    detail: str
    severity: str
    fingerprint_key: str


def which(bin_name: str) -> str | None:
    # Prefer ProjectDiscovery binaries installed under /opt/pd/bin (PATH-ordered in worker image).
    for candidate in (f"/opt/pd/bin/{bin_name}", bin_name):
        found = shutil.which(candidate) if "/" not in candidate else (candidate if Path(candidate).exists() else None)
        if found:
            # Avoid Python's httpx CLI wrapper if PD binary is present alongside it.
            if bin_name == "httpx":
                try:
                    text = Path(found).read_text(encoding="utf-8", errors="ignore")[:80]
                    if "from httpx import main" in text:
                        continue
                except OSError:
                    pass
            return found
    return None


async def run_heartbeat(url: str, timeout: float = 10.0) -> HeartbeatResult:
    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            latency = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            parser = _TitleParser()
            try:
                parser.feed(resp.text[:200_000])
            except Exception:
                pass
            title = parser.title.strip()[:500] or None
            return HeartbeatResult(
                ok=resp.status_code < 500,
                status_code=resp.status_code,
                latency_ms=round(latency, 2),
                title=title,
            )
    except httpx.HTTPError as exc:
        return HeartbeatResult(ok=False, status_code=None, latency_ms=None, title=None, error=str(exc))


async def _run_cmd(args: list[str], timeout: float = 120.0) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, "", "timeout"
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode(
        "utf-8", errors="replace"
    )


async def run_tlsx(host: str) -> list[ToolFinding]:
    binary = which("tlsx")
    findings: list[ToolFinding] = []
    if not binary:
        findings.append(
            ToolFinding(
                title="tlsx not installed",
                detail="Worker image is missing tlsx binary",
                severity="medium",
                fingerprint_key=f"tlsx-missing|{host}",
            )
        )
        return findings

    code, out, err = await _run_cmd(
        [binary, "-host", host, "-json", "-silent", "-expired", "-mismatch", "-nc"],
        timeout=60,
    )
    if code not in (0, 1) and not out.strip():
        findings.append(
            ToolFinding(
                title="tlsx failed",
                detail=err or f"exit {code}",
                severity="low",
                fingerprint_key=f"tlsx-fail|{host}",
            )
        )
        return findings

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        expired = bool(data.get("expired"))
        mismatch = bool(data.get("mismatch"))
        not_after = data.get("not_after") or data.get("notAfter")
        days_left = None
        if not_after:
            try:
                # tlsx may return epoch or iso
                if isinstance(not_after, (int, float)):
                    expiry = datetime.fromtimestamp(not_after, tz=timezone.utc)
                else:
                    expiry = datetime.fromisoformat(str(not_after).replace("Z", "+00:00"))
                days_left = (expiry - datetime.now(timezone.utc)).days
            except Exception:
                days_left = None
        if expired:
            findings.append(
                ToolFinding(
                    title=f"TLS certificate expired on {host}",
                    detail=str(data),
                    severity="high",
                    fingerprint_key=f"tls-expired|{host}",
                )
            )
        elif days_left is not None and days_left < 21:
            findings.append(
                ToolFinding(
                    title=f"TLS certificate expires in {days_left} days on {host}",
                    detail=str(data),
                    severity="medium",
                    fingerprint_key=f"tls-expiring|{host}",
                )
            )
        if mismatch:
            findings.append(
                ToolFinding(
                    title=f"TLS hostname mismatch on {host}",
                    detail=str(data),
                    severity="high",
                    fingerprint_key=f"tls-mismatch|{host}",
                )
            )
    return findings


async def run_httpx_probe(url: str) -> list[ToolFinding]:
    binary = which("httpx")
    findings: list[ToolFinding] = []
    if not binary:
        findings.append(
            ToolFinding(
                title="httpx not installed",
                detail="Worker image is missing httpx binary",
                severity="medium",
                fingerprint_key=f"httpx-missing|{url}",
            )
        )
        return findings

    code, out, err = await _run_cmd(
        [
            binary,
            "-u",
            url,
            "-json",
            "-silent",
            "-status-code",
            "-title",
            "-tech-detect",
            "-follow-redirects",
        ],
        timeout=90,
    )
    if not out.strip():
        findings.append(
            ToolFinding(
                title=f"Host not reachable via httpx: {url}",
                detail=err or f"exit {code}",
                severity="high",
                fingerprint_key=f"httpx-down|{url}",
            )
        )
        return findings

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = data.get("status_code") or data.get("status-code")
        techs = data.get("tech") or data.get("technologies") or []
        if isinstance(techs, str):
            techs = [techs]
        title = data.get("title") or ""
        if status and int(status) >= 500:
            findings.append(
                ToolFinding(
                    title=f"HTTP {status} on {url}",
                    detail=f"title={title}; tech={','.join(map(str, techs))}",
                    severity="high",
                    fingerprint_key=f"httpx-5xx|{url}|{status}",
                )
            )
        # store tech snapshot as info finding for change detection baseline
        if techs:
            tech_key = ",".join(sorted(map(str, techs)))
            findings.append(
                ToolFinding(
                    title=f"Detected technologies on {url}",
                    detail=tech_key,
                    severity="info",
                    fingerprint_key=f"httpx-tech|{url}|{tech_key}",
                )
            )
    return findings


async def run_nuclei_safe(url: str, work_dir: Path | None = None) -> list[ToolFinding]:
    binary = which("nuclei")
    findings: list[ToolFinding] = []
    if not binary:
        findings.append(
            ToolFinding(
                title="nuclei not installed",
                detail="Worker image is missing nuclei binary",
                severity="medium",
                fingerprint_key=f"nuclei-missing|{url}",
            )
        )
        return findings

    out_file = (work_dir or Path("/tmp")) / "nuclei-out.jsonl"
    args = [
        binary,
        "-u",
        url,
        "-jsonl",
        "-silent",
        "-c",
        "10",
        "-rl",
        "50",
        "-tags",
        "misconfig,exposure,ssl,tech",
        "-exclude-tags",
        "dos,fuzz,intrusive",
        "-o",
        str(out_file),
    ]
    code, _out, err = await _run_cmd(args, timeout=600)
    if not out_file.exists():
        if code not in (0, 1):
            findings.append(
                ToolFinding(
                    title="nuclei failed",
                    detail=err or f"exit {code}",
                    severity="low",
                    fingerprint_key=f"nuclei-fail|{url}",
                )
            )
        return findings

    for line in out_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        info = data.get("info") or {}
        name = info.get("name") or data.get("template-id") or "nuclei finding"
        severity = (info.get("severity") or "info").lower()
        if severity not in {"info", "low", "medium", "high", "critical"}:
            severity = "info"
        template_id = data.get("template-id") or data.get("templateID") or name
        matched = data.get("matched-at") or data.get("host") or url
        findings.append(
            ToolFinding(
                title=str(name)[:500],
                detail=json.dumps(data)[:4000],
                severity=severity,
                fingerprint_key=f"nuclei|{template_id}|{matched}",
            )
        )
    try:
        out_file.unlink(missing_ok=True)
    except OSError:
        pass
    return findings
