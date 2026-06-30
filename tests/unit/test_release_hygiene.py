#!/usr/bin/env python3
"""Release hygiene checks for public repository artifacts."""
from __future__ import annotations

import gc
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def _join(*parts: str) -> str:
    return "".join(parts)


TOKEN_PATTERNS = [
    re.compile(_join(r"(?<![A-Za-z0-9_])", "github", r"_pat_[A-Za-z0-9_]+")),
    re.compile(_join(r"(?<![A-Za-z0-9_])", "gh", r"[pousr]_[A-Za-z0-9_]+")),
    re.compile(_join(r"(?<![A-Za-z0-9_])", "s", r"k-[A-Za-z0-9][A-Za-z0-9_-]{6,}")),
]
PUBLIC_PRIVACY_PATTERNS = [
    re.compile(_join(r"derrick", r"dad", r"@fox", r"mail\.com"), re.IGNORECASE),
    re.compile(_join(r"C:\\Users\\", "80", "983"), re.IGNORECASE),
    re.compile(_join(r"D:\\", "Pro", "gram Files", r" \(x86\)\\666\\", r"wallstreet-tieling"), re.IGNORECASE),
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
    _join("audit_reports/REASON", "IX_*.md"),
    _join("audit_reports/AUDIT", "_AUTONOMOUS_*.md"),
]
STALE_VERSION_PATTERNS = [
    re.compile(r"(?i)\bv[23]\.0\.\d+\b"),
    re.compile(r"(?i)\bV3\.0\b"),
]
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "output",
    "deliverables",
    ".archive",
    ".colab",
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

    hits = [
        path
        for path in tracked
        for pattern in TRACKED_PRIVATE_PATTERNS
        if (ROOT / path).exists() and Path(path).match(pattern)
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
