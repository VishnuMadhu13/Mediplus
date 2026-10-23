#!/usr/bin/env python3
"""
Merge every scan result into ONE file: reports/SECURITY_SCAN_REPORT.md

Inputs (all optional, looked up in --dir, default ./reports):
  bandit.json        SAST   - Bandit
  pip-audit.json     SCA    - pip-audit (dependency scan)
  trivy-image.json   Image  - Trivy
  zap/zap-report.json DAST  - OWASP ZAP baseline
  Sonar              SAST   - SonarQube (queried over its API if SONAR_HOST_URL + SONAR_TOKEN are set)

A scan whose report is missing is listed as NOT RUN - never silently as passed.
Exit code is 0 unless --strict is given and a report is missing or has HIGH/CRITICAL findings.
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def bandit(d):
    if d is None:
        return None
    res = d.get("results", [])
    counts = Counter(r["issue_severity"].upper() for r in res)
    rows = [
        (r["issue_severity"].upper(), r["test_id"], f'{r["filename"]}:{r["line_number"]}', r["issue_text"])
        for r in res
    ]
    return counts, rows, ["Severity", "Test", "Location", "Issue"]


def pip_audit(d):
    if d is None:
        return None
    rows = []
    for dep in d.get("dependencies", []):
        for v in dep.get("vulns", []):
            ids = [v["id"]] + [a for a in v.get("aliases", []) if a.startswith("CVE-")]
            rows.append((
                "VULN", dep["name"], dep["version"],
                ", ".join(dict.fromkeys(ids)), ", ".join(v.get("fix_versions", [])) or "-",
            ))
    # collapse exact duplicates (pip-audit can list one advisory more than once)
    rows = list(dict.fromkeys(rows))
    counts = Counter({"VULN": len(rows)}) if rows else Counter()
    return counts, rows, ["", "Package", "Version", "Advisory", "Fixed in"]


def trivy(d):
    if d is None:
        return None
    rows = []
    for res in d.get("Results", []) or []:
        for v in res.get("Vulnerabilities", []) or []:
            rows.append((
                v.get("Severity", "UNKNOWN").upper(), v.get("VulnerabilityID", ""),
                f'{v.get("PkgName", "")} {v.get("InstalledVersion", "")}',
                v.get("FixedVersion", "-") or "-", (v.get("Title") or "")[:90],
            ))
    counts = Counter(r[0] for r in rows)
    rows.sort(key=lambda r: SEV_ORDER.index(r[0]) if r[0] in SEV_ORDER else 99)
    return counts, rows, ["Severity", "ID", "Package", "Fixed in", "Title"]


def zap(d):
    if d is None:
        return None
    risk = {"3": "HIGH", "2": "MEDIUM", "1": "LOW", "0": "INFO"}
    rows = []
    for site in d.get("site", []):
        for a in site.get("alerts", []):
            rows.append((
                risk.get(str(a.get("riskcode")), "INFO"), a.get("alert", ""),
                a.get("count", ""), (a.get("solution") or "").replace("\n", " ")[:90],
            ))
    counts = Counter(r[0] for r in rows)
    rows.sort(key=lambda r: SEV_ORDER.index(r[0]))
    return counts, rows, ["Risk", "Alert", "Instances", "Solution"]


def sonar():
    host, token = os.environ.get("SONAR_HOST_URL"), os.environ.get("SONAR_TOKEN")
    key = os.environ.get("SONAR_PROJECT_KEY", "mediplus")
    if not (host and token):
        return None
    auth = "Basic " + base64.b64encode(f"{token}:".encode()).decode()

    def get(path, **params):
        req = urllib.request.Request(f"{host.rstrip('/')}{path}?{urllib.parse.urlencode(params)}",
                                     headers={"Authorization": auth})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    try:
        qg = get("/api/qualitygates/project_status", projectKey=key)["projectStatus"]["status"]
        facets = get("/api/issues/search", componentKeys=key, resolved="false", ps=1, facets="severities")
        counts = Counter()
        for f in facets.get("facets", []):
            if f["property"] == "severities":
                for v in f["values"]:
                    counts[v["val"]] = v["count"]
        return qg, counts
    except Exception as exc:  # report the failure, never hide it
        return f"ERROR ({exc})", Counter()


def table(headers, rows, limit=50):
    out = ["| " + " | ".join(h or " " for h in headers) + " |", "|" + "---|" * len(headers)]
    for r in rows[:limit]:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    if len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows omitted - see the raw JSON report._")
    return "\n".join(out)


def fmt_counts(c):
    return ", ".join(f"{k} {c[k]}" for k in SEV_ORDER + ["VULN"] if c.get(k)) or "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="reports")
    ap.add_argument("--project", default="mediplus")
    ap.add_argument("--build", default=os.environ.get("BUILD_NUMBER", "local"))
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    d = Path(a.dir)

    scans = [
        ("SAST", "Bandit", bandit(load(d / "bandit.json"))),
        ("SCA (dependency scan)", "pip-audit", pip_audit(load(d / "pip-audit.json"))),
        ("Container image", "Trivy", trivy(load(d / "trivy-image.json"))),
        ("DAST", "OWASP ZAP baseline", zap(load(d / "zap" / "zap-report.json"))),
    ]
    sq = sonar()

    lines = [
        f"# Security scan report - {a.project}",
        "",
        f"Build: {a.build}  |  Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
        "",
        "## Summary",
        "",
        "| Stage | Tool | Status | Findings |",
        "|---|---|---|---|",
    ]
    failed = False
    if sq is None:
        lines.append("| SAST | SonarQube | NOT RUN (no SONAR_HOST_URL/SONAR_TOKEN) | - |")
    else:
        qg, c = sq
        lines.append(f"| SAST | SonarQube | Quality gate: {qg} | {fmt_counts(c)} |")
        failed |= qg != "OK"
    for stage, tool, res in scans:
        if res is None:
            lines.append(f"| {stage} | {tool} | NOT RUN - no report produced | - |")
            failed = True
            continue
        counts = res[0]
        status = "FINDINGS" if sum(counts.values()) else "CLEAN"
        failed |= bool(counts.get("CRITICAL") or counts.get("HIGH") or counts.get("VULN"))
        lines.append(f"| {stage} | {tool} | {status} | {fmt_counts(counts)} |")

    for stage, tool, res in scans:
        lines += ["", f"## {stage} - {tool}", ""]
        if res is None:
            lines.append("No report was produced for this scan. Treat as NOT RUN.")
        elif not res[1]:
            lines.append("No findings.")
        else:
            lines.append(table(res[2], res[1]))

    out = d / "SECURITY_SCAN_REPORT.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")
    if a.strict and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
