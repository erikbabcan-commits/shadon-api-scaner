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
    # Prefer ProjectDiscovery / scanner binaries under /opt/*/bin ahead of Python wrappers.
    for candidate in (f"/opt/pd/bin/{bin_name}", f"/opt/scanners/bin/{bin_name}", bin_name):
        found = shutil.which(candidate) if "/" not in candidate else (candidate if Path(candidate).exists() else None)
        if found:
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


async def run_subfinder(domain: str) -> list[str]:
    binary = which("subfinder")
    if not binary:
        return []
    code, out, _err = await _run_cmd(
        [binary, "-d", domain, "-silent", "-nW"],
        timeout=180,
    )
    if code not in (0, 1):
        return []
    hosts: list[str] = []
    for line in out.splitlines():
        h = line.strip().lower()
        if h and h != domain.lower():
            hosts.append(h)
    return list(dict.fromkeys(hosts))


async def run_naabu(host: str, ports: str) -> list[ToolFinding]:
    binary = which("naabu")
    findings: list[ToolFinding] = []
    if not binary:
        findings.append(
            ToolFinding(
                title="naabu not installed",
                detail="Worker image is missing naabu binary",
                severity="medium",
                fingerprint_key=f"naabu-missing|{host}",
            )
        )
        return findings

    code, out, err = await _run_cmd(
        [
            binary,
            "-host",
            host,
            "-p",
            ports,
            "-silent",
            "-json",
            "-c",
            "25",
            "-rate",
            "100",
            "-timeout",
            "2000",
            "-scan-type",
            "c",
        ],
        timeout=180,
    )
    if code not in (0, 1) and not out.strip():
        findings.append(
            ToolFinding(
                title=f"naabu failed on {host}",
                detail=err or f"exit {code}",
                severity="low",
                fingerprint_key=f"naabu-fail|{host}",
            )
        )
        return findings

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        port = None
        try:
            data = json.loads(line)
            port = data.get("port")
            host_val = data.get("host") or host
        except json.JSONDecodeError:
            # host:port
            if ":" in line:
                host_val, _, port_s = line.rpartition(":")
                try:
                    port = int(port_s)
                except ValueError:
                    continue
            else:
                continue
        if port is None:
            continue
        findings.append(
            ToolFinding(
                title=f"Open port {port} on {host_val}",
                detail=json.dumps({"host": host_val, "port": port}),
                severity="info",
                fingerprint_key=f"naabu|{host_val}|{port}",
            )
        )
    return findings


async def git_clone(url: str, dest: Path, timeout: float = 300.0) -> tuple[bool, str]:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    code, _out, err = await _run_cmd(
        ["git", "clone", "--depth", "1", url, str(dest)],
        timeout=timeout,
    )
    if code != 0:
        return False, err or f"git clone exit {code}"
    return True, ""


async def run_trivy_fs(path: Path) -> list[ToolFinding]:
    binary = which("trivy")
    findings: list[ToolFinding] = []
    if not binary:
        return [
            ToolFinding(
                title="trivy not installed",
                detail="Worker image is missing trivy binary",
                severity="medium",
                fingerprint_key="trivy-missing|fs",
            )
        ]
    code, out, err = await _run_cmd(
        [
            binary,
            "fs",
            "--quiet",
            "--format",
            "json",
            "--severity",
            "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
            str(path),
        ],
        timeout=600,
    )
    return _parse_trivy_json(out, err, code, source_key=f"fs|{path.name}")


async def run_trivy_image(image: str) -> list[ToolFinding]:
    binary = which("trivy")
    if not binary:
        return [
            ToolFinding(
                title="trivy not installed",
                detail="Worker image is missing trivy binary",
                severity="medium",
                fingerprint_key="trivy-missing|image",
            )
        ]
    code, out, err = await _run_cmd(
        [
            binary,
            "image",
            "--quiet",
            "--format",
            "json",
            "--severity",
            "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
            image,
        ],
        timeout=900,
    )
    return _parse_trivy_json(out, err, code, source_key=f"image|{image}")


def _parse_trivy_json(out: str, err: str, code: int, source_key: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    if not out.strip():
        if code not in (0, 1):
            findings.append(
                ToolFinding(
                    title="trivy failed",
                    detail=err or f"exit {code}",
                    severity="low",
                    fingerprint_key=f"trivy-fail|{source_key}",
                )
            )
        return findings
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return findings

    results = data.get("Results") if isinstance(data, dict) else None
    if results is None and isinstance(data, list):
        results = data
    if not results:
        return findings

    sev_map = {
        "UNKNOWN": "info",
        "LOW": "low",
        "MEDIUM": "medium",
        "HIGH": "high",
        "CRITICAL": "critical",
    }
    for result in results:
        target = result.get("Target") or source_key
        for vuln in result.get("Vulnerabilities") or []:
            vid = vuln.get("VulnerabilityID") or vuln.get("PkgID") or "unknown"
            sev = sev_map.get(str(vuln.get("Severity", "UNKNOWN")).upper(), "info")
            pkg = vuln.get("PkgName") or ""
            title = f"{vid} in {pkg or target}"[:500]
            detail = json.dumps(
                {
                    "target": target,
                    "pkg": pkg,
                    "installed": vuln.get("InstalledVersion"),
                    "fixed": vuln.get("FixedVersion"),
                    "title": vuln.get("Title"),
                },
                ensure_ascii=False,
            )[:4000]
            findings.append(
                ToolFinding(
                    title=title,
                    detail=detail,
                    severity=sev,
                    fingerprint_key=f"trivy|{source_key}|{vid}|{pkg}",
                )
            )
    return findings


async def run_gitleaks(path: Path) -> list[ToolFinding]:
    binary = which("gitleaks")
    if not binary:
        return [
            ToolFinding(
                title="gitleaks not installed",
                detail="Worker image is missing gitleaks binary",
                severity="medium",
                fingerprint_key="gitleaks-missing",
            )
        ]
    report = path.parent / "gitleaks-report.json"
    code, _out, err = await _run_cmd(
        [
            binary,
            "detect",
            "--source",
            str(path),
            "--report-format",
            "json",
            "--report-path",
            str(report),
            "--no-git",
            "-v",
        ],
        timeout=600,
    )
    findings: list[ToolFinding] = []
    if not report.exists():
        if code not in (0, 1):
            findings.append(
                ToolFinding(
                    title="gitleaks failed",
                    detail=err[:500] if err else f"exit {code}",
                    severity="low",
                    fingerprint_key="gitleaks-fail",
                )
            )
        return findings

    try:
        data = json.loads(report.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        data = []
    finally:
        try:
            report.unlink(missing_ok=True)
        except OSError:
            pass

    if not isinstance(data, list):
        data = []

    for item in data:
        rule = item.get("RuleID") or item.get("Description") or "secret"
        file_path = item.get("File") or item.get("Path") or ""
        start = item.get("StartLine") or item.get("Line") or 0
        # Never store raw secret — redact
        findings.append(
            ToolFinding(
                title=f"Possible secret: {rule}",
                detail=json.dumps(
                    {
                        "rule": rule,
                        "file": file_path,
                        "line": start,
                        "commit": item.get("Commit"),
                        "secret": "[REDACTED]",
                    },
                    ensure_ascii=False,
                )[:2000],
                severity="high",
                fingerprint_key=f"gitleaks|{rule}|{file_path}|{start}",
            )
        )
    return findings


async def run_whois_rdap(host: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    domain = host.split(":")[0].strip().lower()

    if not domain or domain.replace(".", "").isdigit() or "." not in domain or domain in {"localhost", "local"}:
        return findings

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(f"https://rdap.org/domain/{domain}")
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                expiration_date: datetime | None = None
                for evt in events:
                    if evt.get("eventAction") in ("expiration", "registration expiration"):
                        date_str = evt.get("eventDate")
                        if date_str:
                            try:
                                expiration_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            except ValueError:
                                pass

                if expiration_date:
                    days_left = (expiration_date - datetime.now(timezone.utc)).days
                    if days_left <= 0:
                        findings.append(
                            ToolFinding(
                                title=f"Domain {domain} has expired",
                                detail=f"RDAP expiration date was {expiration_date.isoformat()}",
                                severity="critical",
                                fingerprint_key=f"rdap-expired|{domain}",
                            )
                        )
                    elif days_left < 30:
                        findings.append(
                            ToolFinding(
                                title=f"Domain {domain} expires in {days_left} days",
                                detail=f"RDAP expiration date is {expiration_date.isoformat()}",
                                severity="high" if days_left < 14 else "medium",
                                fingerprint_key=f"rdap-expiring|{domain}",
                            )
                        )
    except Exception:
        pass

    return findings


SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----", "Private RSA/EC/SSH Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"xox[b-aprs]-[0-9a-zA-Z]{10,48}", "Slack API Token"),
    (r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+", "Hardcoded JWT Token"),
    (r"(postgres|mysql|mongodb)://[^:]+:[^@]+@[^/]+", "Database credentials in connection string"),
]


async def run_secrets_sast(path: Path) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    if not path.exists():
        return findings

    target_files = [
        p
        for p in path.rglob("*")
        if p.is_file()
        and not any(
            part.startswith(".") or part in {"node_modules", "venv", ".venv", "dist", "build"}
            for part in p.parts
        )
    ]

    for fpath in target_files[:200]:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            for pattern, name in SECRET_PATTERNS:
                matches = re.finditer(pattern, content)
                for match in matches:
                    rel_path = fpath.relative_to(path)
                    line_num = content[: match.start()].count("\n") + 1
                    findings.append(
                        ToolFinding(
                            title=f"Secret detected: {name} in {rel_path}",
                            detail=f"Rule: {name}, File: {rel_path}:{line_num}",
                            severity="high",
                            fingerprint_key=f"secrets-sast|{name}|{rel_path}|{line_num}",
                        )
                    )
        except OSError:
            continue

    return findings

