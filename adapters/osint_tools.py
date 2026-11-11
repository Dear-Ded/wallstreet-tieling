#!/usr/bin/env python3
"""Optional SOCMINT tool integration: Maigret / Sherlock / holehe / PhoneInfoga /
socid-extractor / theHarvester / GHunt.

Design (absorbed from the peer projects, re-implemented here — no code copied):

* **Honest capability detection** — every tool is detected at runtime
  (``importlib`` + ``importlib.metadata`` + ``shutil.which``). Nothing is
  claimed as installed unless this process can see it.
* **Registry contract** (Sherlock ``data.json`` / Maigret ``data.json``
  discipline) — each tool declares input kind, license, invocation boundary,
  default timeout and how it reports *found / not found / unknown / illegal*.
* **Normalized observations** (Maigret ``MaigretCheckResult`` / Sherlock
  ``QueryResult``) — every per-site answer becomes an ``AccountObservation``
  with the four-state status, URL, HTTP status, response time, extracted ids
  and the raw row.
* **First-class runs** (SpiderFoot scan/module/entity/relationship records) —
  every execution yields an ``osint_tool_run`` record with tool, version,
  query, timestamps, command, site scope and per-status counts, so absence of
  results is auditable.
* **Missing ≠ clean** — ``available`` (not found) is coverage, ``unknown`` /
  ``illegal`` / timeouts / missing tools are explicit evidence gaps. Maigret's
  JSON report only lists *claimed* sites, so non-listed sites are recorded as
  ``unreported`` coverage, never as "no account".
* **Recursive identity search** (Maigret ``--no-recursion`` off by default) —
  ids extracted from found profiles (socid-extractor style) feed a bounded
  breadth-first queue of follow-up usernames/emails.

License boundary: Maigret, Sherlock and socid-extractor are MIT and may be
imported. holehe, PhoneInfoga, theHarvester (GPL) and GHunt (AGPL) are only
ever executed as separate processes / HTTP services and their output parsed;
no GPL/AGPL code is imported or vendored.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

# --------------------------------------------------------------------------
# Status vocabulary (shared by Sherlock QueryStatus and Maigret MaigretCheckStatus)
# --------------------------------------------------------------------------
CLAIMED = "claimed"        # account detected
AVAILABLE = "available"    # tool says not detected (coverage, NOT proof of absence)
UNKNOWN = "unknown"        # error / timeout / WAF / rate-limit -> evidence gap
ILLEGAL = "illegal"        # identifier not valid for the site -> not checked
UNREPORTED = "unreported"  # tool output does not list the site at all
STATUSES = (CLAIMED, AVAILABLE, UNKNOWN, ILLEGAL, UNREPORTED)

_STATUS_ALIASES = {
    "claimed": CLAIMED, "found": CLAIMED, "true": CLAIMED, "exists": CLAIMED,
    "available": AVAILABLE, "not found": AVAILABLE, "false": AVAILABLE,
    "unknown": UNKNOWN, "error": UNKNOWN, "rate limit": UNKNOWN, "ratelimit": UNKNOWN,
    "illegal": ILLEGAL, "invalid": ILLEGAL,
}

# Confidence a single claimed observation contributes, by detection method.
# Sherlock/Maigret "status_code" checks are the noisiest (soft-404 pages),
# "message"/"response_url" checks are content-aware, API/proof checks best.
CHECK_TYPE_CONFIDENCE = {
    "api": 0.8,
    "message": 0.7,
    "response_url": 0.65,
    "status_code": 0.55,
    "email_registration": 0.7,
    "": 0.6,
}


def normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return _STATUS_ALIASES.get(text, UNKNOWN if text else UNKNOWN)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class OptionalToolSpec:
    name: str
    input_kind: str                 # username | email | phone | domain | profile_url | google_account
    homepage: str
    license: str
    boundary: str                   # "python_import" | "subprocess" | "http_service"
    python_module: str = ""
    distribution: str = ""          # PyPI distribution name for version lookup
    executable: str = ""
    install_hint: str = ""
    default_timeout_s: float = 30.0
    site_registry: str = ""
    not_found_semantics: str = ""
    notes: tuple[str, ...] = ()

    @property
    def copyleft(self) -> bool:
        return self.license.upper().startswith(("GPL", "AGPL", "LGPL"))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["copyleft"] = self.copyleft
        payload["notes"] = list(self.notes)
        return payload


OPTIONAL_TOOLS: dict[str, OptionalToolSpec] = {
    "maigret": OptionalToolSpec(
        name="maigret", input_kind="username", homepage="https://github.com/soxoj/maigret",
        license="MIT", boundary="subprocess", python_module="maigret", distribution="maigret",
        executable="maigret", install_hint="pip install maigret", default_timeout_s=30.0,
        site_registry="maigret/resources/data.json (~3000 sites; checkType, presenseStrs/absenceStrs, tags, alexaRank)",
        not_found_semantics="--json simple/ndjson lists only CLAIMED sites; every other checked site is unreported",
        notes=("recursive search over extracted ids is on by default in Maigret; we run it as a bounded queue here",),
    ),
    "sherlock": OptionalToolSpec(
        name="sherlock", input_kind="username", homepage="https://github.com/sherlock-project/sherlock",
        license="MIT", boundary="subprocess", python_module="sherlock_project", distribution="sherlock-project",
        executable="sherlock", install_hint="pip install sherlock-project", default_timeout_s=60.0,
        site_registry="sherlock_project/resources/data.json (~480 sites; errorType status_code|message|response_url, regexCheck)",
        not_found_semantics="--csv --print-all lists every site with Claimed/Available/Unknown/Illegal",
    ),
    "socid_extractor": OptionalToolSpec(
        name="socid_extractor", input_kind="profile_url", homepage="https://github.com/soxoj/socid-extractor",
        license="MIT", boundary="python_import", python_module="socid_extractor", distribution="socid-extractor",
        install_hint="pip install socid-extractor", default_timeout_s=10.0,
        site_registry="socid_extractor/schemes.py (regex/JSON extraction schemes per platform)",
        not_found_semantics="empty dict means no scheme matched the page, not that ids are absent",
    ),
    "holehe": OptionalToolSpec(
        name="holehe", input_kind="email", homepage="https://github.com/megadose/holehe",
        license="GPL-3.0", boundary="subprocess", python_module="holehe", distribution="holehe",
        executable="holehe", install_hint="pip install holehe  (GPL-3.0; run as a separate CLI process)",
        default_timeout_s=120.0,
        site_registry="holehe/modules/<category>/<site>.py (~120 registration/recovery checks)",
        not_found_semantics="exists=False is 'not registered per this check'; rateLimit=True is an evidence gap",
    ),
    "phoneinfoga": OptionalToolSpec(
        name="phoneinfoga", input_kind="phone", homepage="https://github.com/sundowndev/phoneinfoga",
        license="GPL-3.0", boundary="http_service", executable="phoneinfoga",
        install_hint="Go binary from GitHub releases or `docker run sundowndev/phoneinfoga serve`; NOT on PyPI",
        default_timeout_s=30.0,
        site_registry="scanners: local, numverify, googlesearch, googlecse, ovh",
        not_found_semantics="scanner error or empty result is a gap; local scanner always parses number metadata",
        notes=("`phoneinfoga serve` exposes POST /api/v2/scanners/{scanner}/run with JSON output",),
    ),
    "theharvester": OptionalToolSpec(
        name="theharvester", input_kind="domain", homepage="https://github.com/laramies/theHarvester",
        license="GPL-2.0", boundary="subprocess", executable="theHarvester",
        install_hint="install from GitHub (uv/pipx); GPL-2.0, run as a separate CLI process",
        default_timeout_s=300.0,
        site_registry="theHarvester/discovery/* (search engines, CT logs, DNS)",
        not_found_semantics="missing emails/hosts for a source is a coverage gap for that source",
    ),
    "ghunt": OptionalToolSpec(
        name="ghunt", input_kind="google_account", homepage="https://github.com/mxrch/GHunt",
        license="AGPL-3.0", boundary="subprocess", python_module="ghunt", distribution="ghunt",
        executable="ghunt", install_hint="pipx install ghunt; requires `ghunt login` with the operator's own Google session",
        default_timeout_s=120.0,
        site_registry="ghunt/modules/{email,gaia,drive,geolocate}",
        not_found_semantics="requires an operator-supplied authenticated session; without it the run is a gap",
        notes=("operator-session tool: only runs when the deployment owner has logged in GHunt themselves",),
    ),
}


def _distribution_version(name: str) -> str:
    if not name:
        return ""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""
    except Exception:  # pragma: no cover - defensive
        return ""


def detect_optional_tools(
    *,
    which: Callable[[str], str | None] = shutil.which,
    find_spec: Callable[[str], Any] = importlib.util.find_spec,
    version_of: Callable[[str], str] = _distribution_version,
    tools: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Detect which optional SOCMINT tools this process can actually use."""
    detected: dict[str, Any] = {}
    for name in tools or OPTIONAL_TOOLS:
        spec = OPTIONAL_TOOLS[name]
        module_ok = False
        if spec.python_module:
            try:
                module_ok = find_spec(spec.python_module) is not None
            except (ImportError, ValueError):
                module_ok = False
        exe_path = which(spec.executable) if spec.executable else None
        version = version_of(spec.distribution) if (module_ok and spec.distribution) else ""
        installed = bool(module_ok or exe_path)
        detected[name] = {
            "installed": installed,
            "python_module": spec.python_module if module_ok else "",
            "executable_path": exe_path or "",
            "version": version,
            "license": spec.license,
            "boundary": spec.boundary,
            "input_kind": spec.input_kind,
            "install_hint": spec.install_hint,
            "status": "available" if installed else "not_installed",
        }
    return {
        "type": "optional_osint_tool_detection",
        "detected_at": utc_now(),
        "method": "runtime importlib.find_spec + importlib.metadata.version + shutil.which",
        "tools": detected,
        "installed_count": sum(1 for row in detected.values() if row["installed"]),
        "total": len(detected),
    }


# --------------------------------------------------------------------------
# Observations and runs
# --------------------------------------------------------------------------
@dataclass
class AccountObservation:
    tool: str
    site: str
    identifier: str
    identifier_kind: str
    status: str
    url: str = ""
    url_main: str = ""
    http_status: int | None = None
    response_time_s: float | None = None
    check_type: str = ""
    tags: list[str] = field(default_factory=list)
    ids: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolRun:
    tool: str
    query: str
    query_kind: str
    tool_version: str = ""
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    status: str = "completed"     # completed | tool_missing | timeout | failed | parse_error
    error: str = ""
    site_scope: dict[str, Any] = field(default_factory=dict)
    depth: int = 0
    parent_identifier: str = ""
    observations: list[AccountObservation] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        digest = hashlib.sha256(f"{self.tool}|{self.query}|{self.started_at}".encode()).hexdigest()
        return f"osint-run-{digest[:16]}"

    def counts(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        for obs in self.observations:
            counts[obs.status] = counts.get(obs.status, 0) + 1
        return counts

    def provenance(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "tool_version": self.tool_version,
            "query": self.query,
            "query_kind": self.query_kind,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "command": list(self.command),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["run_id"] = self.run_id
        payload["counts"] = self.counts()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolRun":
        fields_ = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "observations"}
        run = cls(**fields_)
        run.observations = [
            AccountObservation(**{k: v for k, v in o.items() if k in AccountObservation.__dataclass_fields__})
            for o in data.get("observations", []) if isinstance(o, dict)
        ]
        return run


# --------------------------------------------------------------------------
# Parsers (tool output -> AccountObservation)
# --------------------------------------------------------------------------
def parse_maigret_report(report: str | dict[str, Any], *, username: str = "") -> list[AccountObservation]:
    """Parse Maigret ``--json simple`` (dict) or ``--json ndjson`` (lines)."""
    rows: list[tuple[str, dict[str, Any]]] = []
    if isinstance(report, dict):
        rows = [(str(k), v) for k, v in report.items() if isinstance(v, dict)]
    else:
        text = str(report or "").strip()
        if not text:
            return []
        if text.startswith("{") and "\n{" not in text:
            data = json.loads(text)
            rows = [(str(k), v) for k, v in data.items() if isinstance(v, dict)]
        else:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                rows.append((str(item.get("sitename") or item.get("site_name") or ""), item))
    out: list[AccountObservation] = []
    for sitename, item in rows:
        status_obj = item.get("status") if isinstance(item.get("status"), dict) else {}
        site_obj = item.get("site") if isinstance(item.get("site"), dict) else {}
        raw_status = status_obj.get("status") or item.get("status") or "Claimed"
        ids = status_obj.get("ids") or item.get("ids_data") or {}
        out.append(
            AccountObservation(
                tool="maigret",
                site=sitename or str(status_obj.get("site_name") or ""),
                identifier=str(item.get("username") or status_obj.get("username") or username),
                identifier_kind="username",
                status=normalize_status(raw_status if isinstance(raw_status, str) else "Claimed"),
                url=str(item.get("url_user") or status_obj.get("url") or ""),
                url_main=str(item.get("url_main") or site_obj.get("urlMain") or ""),
                http_status=_int_or_none(item.get("http_status")),
                response_time_s=_float_or_none(item.get("query_time") or status_obj.get("query_time")),
                check_type=str(site_obj.get("checkType") or ""),
                tags=[str(t) for t in (status_obj.get("tags") or site_obj.get("tags") or [])],
                ids={str(k): v for k, v in (ids.items() if isinstance(ids, dict) else [])},
                extra={
                    "rank": item.get("rank"),
                    "is_similar": bool(item.get("is_similar")),
                    "keyword_match_status": status_obj.get("keyword_match_status"),
                },
            )
        )
    return out


def parse_sherlock_csv(text: str, *, check_types: dict[str, str] | None = None) -> list[AccountObservation]:
    """Parse Sherlock ``--csv --print-all`` output."""
    reader = csv.DictReader(io.StringIO(text or ""))
    out: list[AccountObservation] = []
    for row in reader:
        site = str(row.get("name") or "")
        out.append(
            AccountObservation(
                tool="sherlock",
                site=site,
                identifier=str(row.get("username") or ""),
                identifier_kind="username",
                status=normalize_status(row.get("exists")),
                url=str(row.get("url_user") or ""),
                url_main=str(row.get("url_main") or ""),
                http_status=_int_or_none(row.get("http_status")),
                response_time_s=_float_or_none(row.get("response_time_s")),
                check_type=(check_types or {}).get(site, ""),
            )
        )
    return out


def parse_holehe_rows(rows: str | list[dict[str, Any]], *, email: str = "") -> list[AccountObservation]:
    """Parse holehe CSV export (``--csv``) or its in-memory ``out`` rows."""
    if isinstance(rows, str):
        rows = list(csv.DictReader(io.StringIO(rows)))
    out: list[AccountObservation] = []
    for row in rows:
        rate_limited = str(row.get("rateLimit")).strip().lower() == "true"
        exists = str(row.get("exists")).strip().lower()
        if rate_limited:
            status = UNKNOWN
        elif exists == "true":
            status = CLAIMED
        elif exists == "false":
            status = AVAILABLE
        else:
            status = UNKNOWN
        extra = {
            "method": row.get("method"),
            "frequent_rate_limit": row.get("frequent_rate_limit"),
            "email_recovery": _none_if_blank(row.get("emailrecovery")),
            "phone_number": _none_if_blank(row.get("phoneNumber")),
            "others": _none_if_blank(row.get("others")),
        }
        out.append(
            AccountObservation(
                tool="holehe",
                site=str(row.get("name") or row.get("domain") or ""),
                identifier=email,
                identifier_kind="email",
                status=status,
                url_main=f"https://{row.get('domain')}" if row.get("domain") else "",
                check_type="email_registration",
                extra=extra,
            )
        )
    return out


def parse_phoneinfoga_result(scanner: str, payload: dict[str, Any], *, number: str) -> list[AccountObservation]:
    """Parse ``phoneinfoga serve`` /v2/scanners/{scanner}/run JSON."""
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or not result:
        return [AccountObservation(tool="phoneinfoga", site=scanner, identifier=number,
                                   identifier_kind="phone", status=UNKNOWN,
                                   extra={"error": (payload or {}).get("error", "empty_result")})]
    return [AccountObservation(tool="phoneinfoga", site=scanner, identifier=number,
                               identifier_kind="phone", status=CLAIMED, check_type="api",
                               ids={k: v for k, v in result.items() if not isinstance(v, (list, dict))},
                               extra={"result": result})]


def extract_follow_up_identifiers(observations: Iterable[AccountObservation]) -> list[tuple[str, str]]:
    """Maigret-style recursion seeds from extracted ids (username/email/phone)."""
    seeds: list[tuple[str, str]] = []
    for obs in observations:
        if obs.status != CLAIMED:
            continue
        for key, value in (obs.ids or {}).items():
            k = str(key).lower()
            values = value if isinstance(value, list) else [value]
            for v in values:
                text = str(v or "").strip()
                if not text or len(text) > 128:
                    continue
                if "@" in text and "." in text.split("@")[-1] and ("email" in k or k.endswith("_mail")):
                    seeds.append(("email", text))
                elif k in {"username", "login", "nickname", "screen_name"} or k.endswith("_username"):
                    seeds.append(("username", text.lstrip("@")))
                elif "phone" in k:
                    seeds.append(("phone", text))
    deduped: list[tuple[str, str]] = []
    for item in seeds:
        if item not in deduped:
            deduped.append(item)
    return deduped


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------
Runner = Callable[..., Any]


class OptionalToolRunner:
    """Execute optional tools behind their license boundary and normalize output."""

    def __init__(
        self,
        *,
        runner: Runner = subprocess.run,
        detection: dict[str, Any] | None = None,
        workdir_factory: Callable[[], str] = lambda: tempfile.mkdtemp(prefix="wst-osint-"),
        http_post: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
        phoneinfoga_url: str | None = None,
        proxy: str | None = None,
    ) -> None:
        self._runner = runner
        self._detection = detection
        self._workdir_factory = workdir_factory
        self._http_post = http_post or _default_http_post
        self.phoneinfoga_url = (phoneinfoga_url or os.environ.get("WST_PHONEINFOGA_URL") or "http://127.0.0.1:5000/api").rstrip("/")
        self.proxy = proxy or os.environ.get("WST_OSINT_PROXY") or ""

    @property
    def detection(self) -> dict[str, Any]:
        if self._detection is None:
            self._detection = detect_optional_tools()
        return self._detection

    def _tool_row(self, tool: str) -> dict[str, Any]:
        return dict(self.detection.get("tools", {}).get(tool) or {})

    def _missing(self, tool: str, query: str, kind: str) -> ToolRun:
        run = ToolRun(tool=tool, query=query, query_kind=kind, status="tool_missing",
                      error=f"{tool} not installed: {OPTIONAL_TOOLS[tool].install_hint}")
        run.finished_at = utc_now()
        return run

    def _exec(self, run: ToolRun, cmd: list[str], *, cwd: str, timeout: float) -> bool:
        run.command = cmd
        try:
            proc = self._runner(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            run.status, run.error = "timeout", f"timed out after {timeout}s"
            return False
        except OSError as exc:
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            return False
        run.exit_code = getattr(proc, "returncode", None)
        if run.exit_code not in (0, None):
            run.status = "failed"
            run.error = (getattr(proc, "stderr", "") or "")[-500:]
        return True

    # ---- username -----------------------------------------------------
    def run_maigret(self, username: str, *, top_sites: int | None = 500, all_sites: bool = False,
                    sites: list[str] | None = None, tags: list[str] | None = None,
                    timeout: float | None = None, recursion: bool = False) -> ToolRun:
        row = self._tool_row("maigret")
        if not row.get("installed"):
            return self._missing("maigret", username, "username")
        spec = OPTIONAL_TOOLS["maigret"]
        per_site_timeout = timeout or spec.default_timeout_s
        workdir = self._workdir_factory()
        cmd = [row.get("executable_path") or "maigret", username, "--json", "simple",
               "--folderoutput", workdir, "--timeout", str(int(per_site_timeout)),
               "--no-progressbar", "--no-color"]
        scope: dict[str, Any] = {"per_site_timeout_s": per_site_timeout}
        if sites:
            for site in sites:
                cmd += ["--site", site]
            scope["sites"] = list(sites)
        elif all_sites:
            cmd.append("--all-sites")
            scope["all_sites"] = True
        elif top_sites:
            cmd += ["--top-sites", str(int(top_sites))]
            scope["top_sites"] = int(top_sites)
        if tags:
            cmd += ["--tags", ",".join(tags)]
            scope["tags"] = list(tags)
        if not recursion:
            cmd.append("--no-recursion")
        if self.proxy:
            cmd += ["--proxy", self.proxy]
            scope["proxy"] = "configured"
        run = ToolRun(tool="maigret", query=username, query_kind="username",
                      tool_version=row.get("version", ""), site_scope=scope)
        if self._exec(run, cmd, cwd=workdir, timeout=max(120.0, per_site_timeout * 20)):
            reports = sorted(glob.glob(os.path.join(workdir, "report_*_simple.json")))
            if not reports:
                run.status = "parse_error" if run.status == "completed" else run.status
                run.error = run.error or "maigret produced no JSON report"
            else:
                try:
                    with open(reports[0], encoding="utf-8") as handle:
                        run.observations = parse_maigret_report(handle.read(), username=username)
                except (OSError, ValueError) as exc:
                    run.status, run.error = "parse_error", f"{type(exc).__name__}: {exc}"
        run.finished_at = utc_now()
        shutil.rmtree(workdir, ignore_errors=True)
        return run

    def run_sherlock(self, username: str, *, sites: list[str] | None = None,
                     timeout: float | None = None, nsfw: bool = False) -> ToolRun:
        row = self._tool_row("sherlock")
        if not row.get("installed"):
            return self._missing("sherlock", username, "username")
        spec = OPTIONAL_TOOLS["sherlock"]
        per_site_timeout = timeout or spec.default_timeout_s
        workdir = self._workdir_factory()
        cmd = [row.get("executable_path") or "sherlock", username, "--csv", "--print-all",
               "--folderoutput", workdir, "--timeout", str(int(per_site_timeout)), "--no-color"]
        scope: dict[str, Any] = {"per_site_timeout_s": per_site_timeout, "sites": list(sites or []) or "all"}
        for site in sites or []:
            cmd += ["--site", site]
        if nsfw:
            cmd.append("--nsfw")
        if self.proxy:
            cmd += ["--proxy", self.proxy]
            scope["proxy"] = "configured"
        run = ToolRun(tool="sherlock", query=username, query_kind="username",
                      tool_version=row.get("version", ""), site_scope=scope)
        if self._exec(run, cmd, cwd=workdir, timeout=max(180.0, per_site_timeout * 10)):
            path = os.path.join(workdir, f"{username}.csv")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    run.observations = parse_sherlock_csv(handle.read())
            elif run.status == "completed":
                run.status, run.error = "parse_error", "sherlock produced no CSV report"
        run.finished_at = utc_now()
        shutil.rmtree(workdir, ignore_errors=True)
        return run

    # ---- email --------------------------------------------------------
    def run_holehe(self, email: str, *, timeout: float | None = None, only_used: bool = False) -> ToolRun:
        row = self._tool_row("holehe")
        if not row.get("installed"):
            return self._missing("holehe", email, "email")
        spec = OPTIONAL_TOOLS["holehe"]
        workdir = self._workdir_factory()
        cmd = [row.get("executable_path") or "holehe", email, "--csv", "--no-color", "--no-clear",
               "-T", str(int(timeout or 10))]
        if only_used:
            cmd.append("--only-used")
        run = ToolRun(tool="holehe", query=email, query_kind="email", tool_version=row.get("version", ""),
                      site_scope={"modules": "all", "only_used": only_used})
        if self._exec(run, cmd, cwd=workdir, timeout=timeout and timeout * 20 or spec.default_timeout_s):
            # holehe exits non-zero after writing the CSV (it calls exit(msg)).
            files = sorted(glob.glob(os.path.join(workdir, "holehe_*_results.csv")))
            if files:
                with open(files[0], encoding="utf-8") as handle:
                    run.observations = parse_holehe_rows(handle.read(), email=email)
                run.status, run.error = "completed", ""
            elif run.status == "completed":
                run.status, run.error = "parse_error", "holehe produced no CSV export"
        run.finished_at = utc_now()
        shutil.rmtree(workdir, ignore_errors=True)
        return run

    # ---- phone --------------------------------------------------------
    def run_phoneinfoga(self, number: str, *, scanners: Iterable[str] = ("local", "numverify", "googlesearch", "ovh"),
                        timeout: float | None = None) -> ToolRun:
        spec = OPTIONAL_TOOLS["phoneinfoga"]
        run = ToolRun(tool="phoneinfoga", query=number, query_kind="phone",
                      tool_version=self._tool_row("phoneinfoga").get("version", ""),
                      site_scope={"service": self.phoneinfoga_url, "scanners": list(scanners)})
        for scanner in scanners:
            url = f"{self.phoneinfoga_url}/v2/scanners/{urllib.parse.quote(scanner)}/run"
            run.command.append(f"POST {url}")
            try:
                payload = self._http_post(url, {"number": number, "options": {}}, timeout or spec.default_timeout_s)
            except Exception as exc:  # service not running, HTTP error, timeout
                payload = {"error": f"{type(exc).__name__}: {exc}"}
            run.observations.extend(parse_phoneinfoga_result(scanner, payload, number=number))
        if run.observations and all(o.status == UNKNOWN for o in run.observations):
            run.status = "failed"
            run.error = "phoneinfoga service unavailable or every scanner errored"
        run.finished_at = utc_now()
        return run

    # ---- profile id extraction -----------------------------------------
    def extract_profile_ids(self, page_text: str, *, url: str = "") -> ToolRun:
        row = self._tool_row("socid_extractor")
        run = ToolRun(tool="socid_extractor", query=url or "<page>", query_kind="profile_url",
                      tool_version=row.get("version", ""))
        if not row.get("installed"):
            run.status, run.error = "tool_missing", OPTIONAL_TOOLS["socid_extractor"].install_hint
            run.finished_at = utc_now()
            return run
        try:
            import socid_extractor  # MIT
            ids = socid_extractor.extract(page_text) or {}
        except Exception as exc:
            run.status, run.error, ids = "failed", f"{type(exc).__name__}: {exc}", {}
        run.observations.append(AccountObservation(
            tool="socid_extractor", site=urllib.parse.urlparse(url).netloc or "page", identifier=url,
            identifier_kind="profile_url", status=CLAIMED if ids else UNKNOWN, url=url, ids=dict(ids),
            check_type="api" if ids else ""))
        run.finished_at = utc_now()
        return run


def _default_http_post(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# --------------------------------------------------------------------------
# Recursive identity search (bounded BFS)
# --------------------------------------------------------------------------
@dataclass
class IdentitySearchResult:
    seed: tuple[str, str]
    runs: list[ToolRun]
    edges: list[dict[str, Any]]
    visited: list[tuple[str, str]]
    truncated: bool

    def standardized_records(self, *, subject: str = "") -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for run in self.runs:
            records.extend(tool_run_to_standardized_records(run, subject=subject))
        for edge in self.edges:
            records.append(_relationship_record(edge, subject=subject))
        return records


class RecursiveIdentitySearch:
    """Maigret-style follow-up search over ids discovered on found profiles."""

    def __init__(self, tool_runner: OptionalToolRunner, *, max_depth: int = 2, max_identifiers: int = 20,
                 username_tools: tuple[str, ...] = ("maigret", "sherlock"),
                 tool_options: dict[str, dict[str, Any]] | None = None) -> None:
        self.runner = tool_runner
        self.max_depth = max_depth
        self.max_identifiers = max_identifiers
        self.username_tools = username_tools
        self.tool_options = tool_options or {}

    def _runs_for(self, kind: str, value: str) -> list[ToolRun]:
        runs: list[ToolRun] = []
        if kind == "username":
            for tool in self.username_tools:
                fn = getattr(self.runner, f"run_{tool}")
                run = fn(value, **self.tool_options.get(tool, {}))
                runs.append(run)
                if run.status == "completed":
                    break  # first tool that actually ran is enough; others are fallbacks
        elif kind == "email":
            runs.append(self.runner.run_holehe(value, **self.tool_options.get("holehe", {})))
        elif kind == "phone":
            runs.append(self.runner.run_phoneinfoga(value, **self.tool_options.get("phoneinfoga", {})))
        return runs

    def search(self, kind: str, value: str) -> IdentitySearchResult:
        queue: deque[tuple[str, str, int, str]] = deque([(kind, value, 0, "")])
        visited: list[tuple[str, str]] = []
        runs: list[ToolRun] = []
        edges: list[dict[str, Any]] = []
        truncated = False
        while queue:
            k, v, depth, parent = queue.popleft()
            key = (k, v.lower())
            if key in [(a, b.lower()) for a, b in visited]:
                continue
            if len(visited) >= self.max_identifiers:
                truncated = True
                break
            visited.append((k, v))
            for run in self._runs_for(k, v):
                run.depth, run.parent_identifier = depth, parent
                runs.append(run)
                if depth >= self.max_depth:
                    continue
                claimed = [o for o in run.observations if o.status == CLAIMED]
                for nk, nv in extract_follow_up_identifiers(claimed):
                    source_obs = next((o for o in claimed if nv in json.dumps(o.ids, ensure_ascii=False)), None)
                    edges.append({
                        "from": {"kind": k, "value": v},
                        "to": {"kind": nk, "value": nv},
                        "relation": "profile_discloses_identifier",
                        "via_site": source_obs.site if source_obs else "",
                        "via_url": source_obs.url if source_obs else "",
                        "tool": run.tool,
                        "run_id": run.run_id,
                        "depth": depth + 1,
                    })
                    queue.append((nk, nv, depth + 1, f"{k}:{v}"))
        if queue:
            truncated = True
        return IdentitySearchResult(seed=(kind, value), runs=runs, edges=edges, visited=visited, truncated=truncated)


# --------------------------------------------------------------------------
# standardized_records mapping
# --------------------------------------------------------------------------
def tool_run_to_standardized_records(run: ToolRun, *, subject: str = "") -> list[dict[str, Any]]:
    """Map one tool run into run + account + gap records with full provenance."""
    entity = subject or run.query
    prov = run.provenance()
    counts = run.counts()
    gaps = [o for o in run.observations if o.status in {UNKNOWN, ILLEGAL}]
    records: list[dict[str, Any]] = []
    run_record = {
        "source_name": f"optional_osint_{run.tool}",
        "source_type": "optional_osint_tool_run",
        "source_hint": f"optional_osint_{run.tool}",
        "record_type": "osint_tool_run",
        "entity": entity,
        "title": f"{run.tool} run for {run.query_kind} {run.query}",
        "summary": (
            f"status={run.status}; claimed={counts[CLAIMED]}; not_detected={counts[AVAILABLE]}; "
            f"unknown={counts[UNKNOWN]}; illegal={counts[ILLEGAL]}"
        ),
        "url": "",
        "retrieved_at": run.finished_at or run.started_at,
        "confidence": 0.9 if run.status == "completed" else 0.3,
        "run": {**prov, "status": run.status, "error": run.error, "exit_code": run.exit_code,
                "site_scope": run.site_scope, "counts": counts, "depth": run.depth,
                "parent_identifier": run.parent_identifier},
        "coverage": {
            "not_detected_sites": [o.site for o in run.observations if o.status == AVAILABLE],
            "absence_semantics": OPTIONAL_TOOLS.get(run.tool, OptionalToolSpec(run.tool, "", "", "", "")).not_found_semantics,
            "absence_is_not_proof": True,
        },
        "evidence": [{"type": "osint_tool_run", "provenance": prov, "status": run.status}],
        "evidence_gaps": (
            [{"reason": run.status, "detail": run.error, "tool": run.tool}] if run.status != "completed" else []
        ) + [
            {"reason": f"site_{o.status}", "site": o.site, "detail": o.extra.get("error", ""), "tool": run.tool}
            for o in gaps
        ],
    }
    records.append(run_record)
    for obs in run.observations:
        if obs.status != CLAIMED:
            continue
        confidence = CHECK_TYPE_CONFIDENCE.get(obs.check_type, CHECK_TYPE_CONFIDENCE[""])
        if obs.extra.get("is_similar"):
            confidence = min(confidence, 0.35)
        records.append({
            "source_name": f"optional_osint_{run.tool}",
            "source_type": "optional_osint_account_observation",
            "source_hint": f"optional_osint_{run.tool}",
            "record_type": "social_account_candidate" if obs.identifier_kind != "phone" else "phone_number_intel",
            "entity": entity,
            "title": f"{obs.site}: {obs.identifier}",
            "summary": f"{run.tool} reports {obs.identifier_kind} {obs.identifier} present on {obs.site}",
            "url": obs.url or obs.url_main,
            "retrieved_at": run.finished_at or run.started_at,
            "confidence": round(confidence, 2),
            "entity_match": {
                "level": "review",
                "score": round(confidence, 2),
                "method": f"{run.tool}_{obs.check_type or 'presence'}_check",
                "identifiers": {obs.identifier_kind: obs.identifier, **{k: v for k, v in obs.ids.items() if isinstance(v, (str, int, float))}},
            },
            "entities": [{
                "kind": "online_account" if obs.identifier_kind != "phone" else "phone_number",
                "name": obs.identifier,
                "platform": obs.site,
                "url": obs.url,
                "relation": "account_candidate_of_subject",
                "confidence": round(confidence, 2),
                "attributes": dict(obs.ids),
            }],
            "profile": {"ids": dict(obs.ids), "tags": list(obs.tags), **{k: v for k, v in obs.extra.items() if v not in (None, "", [], {})}},
            "evidence": [{
                "type": "optional_osint_account_presence",
                "provider": obs.site,
                "source_url": obs.url or obs.url_main,
                "tool": run.tool,
                "tool_version": run.tool_version,
                "query": run.query,
                "run_id": run.run_id,
                "retrieved_at": run.finished_at or run.started_at,
                "check_type": obs.check_type,
                "http_status": obs.http_status,
                "response_time_s": obs.response_time_s,
                "entity_match_level": "review",
                "manual_review_required": True,
            }],
        })
    return records


def _relationship_record(edge: dict[str, Any], *, subject: str = "") -> dict[str, Any]:
    return {
        "source_name": f"optional_osint_{edge.get('tool')}",
        "source_type": "optional_osint_identity_link",
        "source_hint": f"optional_osint_{edge.get('tool')}",
        "record_type": "identity_relationship",
        "entity": subject or edge["from"]["value"],
        "title": f"{edge['from']['kind']} {edge['from']['value']} -> {edge['to']['kind']} {edge['to']['value']}",
        "summary": f"profile on {edge.get('via_site') or 'unknown site'} discloses {edge['to']['kind']} {edge['to']['value']}",
        "url": edge.get("via_url", ""),
        "retrieved_at": utc_now(),
        "confidence": 0.55,
        "relationships": [{
            "source": edge["from"], "target": edge["to"], "type": edge.get("relation"),
            "evidence_run_id": edge.get("run_id"), "depth": edge.get("depth"),
        }],
        "evidence": [{"type": "identity_link", "provider": edge.get("via_site"), "source_url": edge.get("via_url", ""),
                      "tool": edge.get("tool"), "run_id": edge.get("run_id"), "manual_review_required": True}],
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip()) if str(value or "").strip() else None
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip()) if str(value or "").strip() else None
    except ValueError:
        return None


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "", "None", "none") else value


__all__ = [
    "AccountObservation", "CLAIMED", "AVAILABLE", "UNKNOWN", "ILLEGAL", "UNREPORTED",
    "OPTIONAL_TOOLS", "OptionalToolRunner", "OptionalToolSpec", "RecursiveIdentitySearch",
    "ToolRun", "detect_optional_tools", "extract_follow_up_identifiers", "parse_holehe_rows",
    "parse_maigret_report", "parse_phoneinfoga_result", "parse_sherlock_csv",
    "tool_run_to_standardized_records",
]
