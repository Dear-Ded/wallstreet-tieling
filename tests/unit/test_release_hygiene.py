#!/usr/bin/env python3
"""Release hygiene checks for public repository artifacts."""
from __future__ import annotations

import gc
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent


def _join(*parts: str) -> str:
    return "".join(parts)


TOKEN_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9][A-Za-z0-9_-]{6,}"),
]
PUBLIC_PRIVACY_PATTERNS = [
    re.compile(_join(r"derrickdad", r"@foxmail\.com"), re.IGNORECASE),
    re.compile(r"C:\\Users\\[0-9A-Za-z_.-]+\\", re.IGNORECASE),
    re.compile(r"[A-Z]:\\(?:Program Files(?: \(x86\))?|Users)\\[^\\]+\\wallstreet-tieling", re.IGNORECASE),
    re.compile(_join(r"Dear-Ded/", r"wallstreet-tieling", r"-dev"), re.IGNORECASE),
    re.compile(_join(r"wallstreet-tieling", r"-dev\.git"), re.IGNORECASE),
    re.compile(_join(r"support", r"@multi-datasource\.com"), re.IGNORECASE),
    re.compile(_join(r"OWNER", r"_COLLABORATION", r"_PROFILE"), re.IGNORECASE),
    re.compile(_join(r"CODEX", r"_MAINLINE", r"_TAKEOVER"), re.IGNORECASE),
    re.compile(_join(r"REASON", r"IX_"), re.IGNORECASE),
    re.compile(_join(r"REASON", r"IX_OFFLINE", r"_AUDIT_PACKET"), re.IGNORECASE),
    re.compile(_join(r"\b13800", r"138000\b")),
    re.compile(_join(r"\b14158", r"586273\b")),
    re.compile(_join(r"zhangsan", r"(?:1990)?", r"@gmail\.com"), re.IGNORECASE),
]
TRACKED_PRIVATE_PATTERNS = [
    ".colab/*",
    ".pytest_cache/*",
    "AGENT_COORDINATION_BOARD.md",
    "demo/*",
    "*.db",
    "*.db.backup",
    "*.sqlite",
    "*.sqlite3",
    "*.cookies",
    "*.cookie",
    "cookies.json",
    "browser-profile/*",
    "browser_profiles/*",
    _join("docs/REASON", "IX_*.md"),
    _join("docs/OWNER", "_COLLABORATION", "_PROFILE.md"),
    _join("docs/CODEX", "_MAINLINE", "_TAKEOVER.md"),
    _join("docs/AGENT", "_DIVISION", "_OF_LABOR.md"),
    _join("docs/PERSONA", "_OFFICE_CHAT", "_BRANCH.md"),
    _join("docs/WORKBUDDY", "_CURRENT_COMMAND.md"),
    _join("docs/WORKBUDDY", "_UI_QUALITY", "_DIRECTIVE.md"),
    "docs/WORKBUDDY_OFFICE_CHAT_BACKLOG.md",
    "docs/BEAUTIFICATION_ISOLATION_REVIEW.md",
    "docs/DD_V3_AGENT_AUDIT.md",
    "docs/PROJECT_MANAGEMENT.md",
    "docs/SUPERPOWERS_FINAL_REVIEW.md",
    "docs/WORKTREE_REVIEW_QUEUE.md",
    "docs/deepseek/*",
    "docs/workbuddy/*",
    "docs/data_source_research_*.md",
    "docs/COMPREHENSIVE_AUDIT_REPORT_*.md",
    "docs/FINAL_DELIVERY_REPORT_*.md",
    _join("audit_reports/REASON", "IX_*.md"),
    _join("audit_reports/AUDIT", "_AUTONOMOUS_*.md"),
    "gen_ci.py",
    "overview.md",
    "sessions/*",
    "send_message_to_product_ai.py",
]
PACKAGE_FILE_DENYLIST = [
    ".colab/",
    ".tmp/",
    ".workbuddy/",
    "audit_reports/",
    "browser-profile/",
    "browser_profiles/",
    "demo/",
    "deliverables/",
    "docs/deepseek/",
    "docs/PRIVATE_DEV_HANDOFF.md",
    "docs/workbuddy/",
    "output/",
    "outputs/",
    "sessions/",
    "tmp-events.jsonl",
]
STALE_VERSION_PATTERNS = [
    re.compile(r"(?i)\bv[23]\.0\.\d+\b"),
    re.compile(r"(?i)\bV3\.0\b"),
]
MOJIBAKE_MARKERS = (
    "\u9357",
    "\u95c2",
    "\u6fde",
    "\u6fe0",
    "\u5a75",
    "\u7ef1",
    "\u7f01",
    "\u95b8",
    "\u6d93",
    "\u935b",
    "\u6748",
    "\u9286",
    "\u947e",
    "\u690b",
    "\ufffd",
)
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "output",
    "deliverables",
    ".archive",
    ".colab",
    ".codex-autonomous",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _iter_public_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if set(rel.parts) & EXCLUDED_PARTS:
            continue
        yield path


def _git_ls_files() -> list[str]:
    last_error: OSError | None = None
    for attempt in range(3):
        try:
            return subprocess.run(
                ["git", "ls-files"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.splitlines()
        except OSError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 1455 or attempt >= 2:
                raise
            gc.collect()
            time.sleep(0.8 * (attempt + 1))
    if last_error:
        raise last_error
    return []


def test_public_repo_does_not_ship_secret_like_tokens() -> None:
    hits: list[str] = []
    for path in _iter_public_text_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in TOKEN_PATTERNS:
            for match in pattern.finditer(text):
                if "TOKEN_PATTERNS" in text[max(0, match.start() - 80):match.end() + 80]:
                    continue
                hits.append(f"{path.relative_to(ROOT)}:{match.start()}:{pattern.pattern}")

    assert hits == []


def test_public_repo_does_not_ship_private_contact_or_local_paths() -> None:
    hits: list[str] = []
    for path in _iter_public_text_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PUBLIC_PRIVACY_PATTERNS:
            for match in pattern.finditer(text):
                if "PUBLIC_PRIVACY_PATTERNS" in text[max(0, match.start() - 80):match.end() + 80]:
                    continue
                hits.append(f"{path.relative_to(ROOT)}:{pattern.pattern}")

    assert hits == []


def test_public_repo_does_not_track_private_runtime_artifacts() -> None:
    tracked = _git_ls_files()
    top_level_private_files = {"test_optimized_cache.py"}

    hits = [
        path
        for path in tracked
        for pattern in TRACKED_PRIVATE_PATTERNS
        if (ROOT / path).exists() and Path(path).match(pattern)
    ]
    hits.extend(path for path in tracked if path in top_level_private_files and (ROOT / path).exists())

    assert hits == []


def test_npm_package_file_allowlist_excludes_runtime_and_private_artifacts() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    package_files = [str(item).replace("\\", "/").strip() for item in package.get("files", [])]

    hits = [
        entry
        for entry in package_files
        for denied in PACKAGE_FILE_DENYLIST
        if entry == denied.rstrip("/") or entry.startswith(denied)
    ]

    assert hits == []


def test_public_release_copy_has_no_stale_version_markers() -> None:
    hits: list[str] = []
    checked_roots = [
        ROOT / "README.md",
        ROOT / "index.html",
        ROOT / "package.json",
        ROOT / ".codex-plugin",
        ROOT / "deploy",
        ROOT / "release",
        ROOT / "references",
    ]
    for path in checked_roots:
        candidates = [path] if path.is_file() else list(path.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = candidate.read_text(encoding="utf-8")
            for pattern in STALE_VERSION_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{candidate.relative_to(ROOT)}:{pattern.pattern}")

    assert hits == []


def test_npm_package_metadata_is_public_and_readable() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    metadata_text = json.dumps(
        {
            "description": package.get("description", ""),
            "keywords": package.get("keywords", []),
            "repository": package.get("repository", {}),
            "homepage": package.get("homepage", ""),
            "install": package.get("install", {}),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "wallstreet-tieling-dev" not in metadata_text
    assert "C:\\Users\\" not in metadata_text
    assert "D:\\Program Files" not in metadata_text
    assert not [marker for marker in MOJIBAKE_MARKERS if marker in metadata_text]
    assert {"尽调", "信贷", "风控", "反洗钱", "多智能体"} <= set(package["keywords"])
    assert package["repository"]["url"] == "https://github.com/Dear-Ded/wallstreet-tieling"


def test_npm_package_dry_run_excludes_private_and_local_artifacts(tmp_path) -> None:
    npm = shutil.which("npm")
    if not npm:
        pytest.skip("npm runtime not available")

    env = {
        **os.environ,
        "npm_config_cache": str(tmp_path / "npm-cache"),
    }
    result = subprocess.run(
        [npm, "pack", "--dry-run", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    package = json.loads(result.stdout)[0]
    paths = {item["path"] for item in package["files"]}

    required = {
        ".codex-plugin/plugin.json",
        "bin/cli.js",
        "bin/verify_report_bundle.py",
        "lib/mcp-server.js",
        "tools/codex-mcp-smoke.js",
        "tools/agent-host-smoke.js",
        "tools/api-smoke.py",
        "tools/run-acceptance.ps1",
        "docs/API_CONTRACTS.md",
        "docs/DESKTOP_AGENT_ALPHA_DELIVERY.md",
        "skills/wallstreet-tieling/SKILL.md",
    }
    assert required <= paths

    forbidden_exact = {
        "AGENT_COORDINATION_BOARD.md",
        "docs/COMPREHENSIVE_AUDIT_REPORT_2026-06-16.md",
        "docs/FINAL_DELIVERY_REPORT_2026-06-16.md",
        "gen_ci.py",
        "overview.md",
        "package-lock.json",
        "send_message_to_product_ai.py",
    }
    assert paths.isdisjoint(forbidden_exact)

    forbidden_prefixes = (
        ".git/",
        ".pytest_cache/",
        ".tmp/",
        "audit_reports/",
        "deliverables/",
        "docs/deepseek/",
        "docs/workbuddy/",
        "output/",
    )
    assert not [path for path in paths if path.startswith(forbidden_prefixes)]

    forbidden_suffixes = (
        ".cookie",
        ".cookies",
        ".db",
        ".db.backup",
        ".jsonl",
        ".sqlite",
        ".sqlite3",
    )
    assert not [path for path in paths if path.endswith(forbidden_suffixes)]


def test_npm_package_privacy_scan_contract_is_packaged() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    scanner = (ROOT / "tools" / "package-privacy-scan.py").read_text(encoding="utf-8")

    assert package["scripts"]["release:privacy-scan"] == (
        "powershell -NoProfile -ExecutionPolicy Bypass -File "
        "tools/run-python.ps1 tools/package-privacy-scan.py --json"
    )
    assert "tools/package-privacy-scan.py" in package["files"]
    assert "FORBIDDEN_PREFIXES" in scanner
    assert '".codex-autonomous/"' in scanner
    assert '"docs/deepseek/"' in scanner
    assert '"docs/workbuddy/"' in scanner
    assert "SECRET_PATTERNS" in scanner
    assert "MOJIBAKE_MARKERS" in scanner
    assert "mojibake_marker" in scanner
