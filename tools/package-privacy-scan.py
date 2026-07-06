#!/usr/bin/env python3
"""Scan the npm package payload for private paths, runtime artifacts, and secrets."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_PREFIXES = (
    ".git/",
    ".tmp/",
    ".workbuddy/",
    ".codex-autonomous/",
    "audit_reports/",
    "deliverables/",
    "docs/deepseek/",
    "docs/workbuddy/",
    "output/",
    "outputs/",
)
FORBIDDEN_SUFFIXES = (
    ".cookie",
    ".cookies",
    ".db",
    ".db.backup",
    ".jsonl",
    ".sqlite",
    ".sqlite3",
)
SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9][A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_])xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    parser.add_argument("--deny", action="append", default=[], help="Additional literal term to reject.")
    args = parser.parse_args()

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("No npm executable found.")

    with tempfile.TemporaryDirectory(prefix="wst-package-privacy-", ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        pack_dir = tmp_path / "pack"
        extract_dir = tmp_path / "extract"
        pack_dir.mkdir()
        extract_dir.mkdir()
        pack = _npm_pack(npm, pack_dir)
        package_root = _extract_package(pack, extract_dir)
        issues = _scan_package(package_root, args.deny)
        result = {
            "type": "package_privacy_scan",
            "ok": not issues,
            "package": pack.name,
            "scanned_root": "npm-package",
            "issue_count": len(issues),
            "issues": issues,
        }

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))
    if issues:
        raise SystemExit(1)


def _npm_pack(npm: str, pack_dir: Path) -> Path:
    env = {**os.environ, "npm_config_cache": str(pack_dir / "npm-cache")}
    result = subprocess.run(
        [npm, "pack", "--json", "--pack-destination", str(pack_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    payload = json.loads(result.stdout)[0]
    filename = payload.get("filename")
    if not filename:
        raise RuntimeError("npm pack did not return filename")
    candidate = pack_dir / Path(filename).name
    if not candidate.exists():
        matches = list(pack_dir.glob("*.tgz"))
        if not matches:
            raise RuntimeError("npm pack did not create a tarball")
        candidate = matches[0]
    return candidate


def _extract_package(pack: Path, extract_dir: Path) -> Path:
    with tarfile.open(pack, "r:gz") as tar:
        for member in tar.getmembers():
            target = (extract_dir / member.name).resolve()
            if not str(target).startswith(str(extract_dir.resolve())):
                raise RuntimeError(f"unsafe tar path: {member.name}")
        tar.extractall(extract_dir, filter="data")
    package_root = extract_dir / "package"
    if not package_root.exists():
        raise RuntimeError("npm package root not found after extract")
    return package_root


def _scan_package(package_root: Path, extra_denies: list[str]) -> list[dict[str, Any]]:
    private_terms = _private_terms(extra_denies)
    issues: list[dict[str, Any]] = []
    for path in package_root.rglob("*"):
        rel = path.relative_to(package_root).as_posix()
        if path.is_dir():
            continue
        if rel.startswith(FORBIDDEN_PREFIXES) or rel.endswith(FORBIDDEN_SUFFIXES):
            issues.append({"path": rel, "kind": "forbidden_path", "match": rel})
            continue
        if path.stat().st_size > 2 * 1024 * 1024 or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        escaped_text = text.replace("\\\\", "\\")
        for term in private_terms:
            if term and (term in text or term in escaped_text):
                issues.append({"path": rel, "kind": "private_term", "match": _redact(term)})
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append({"path": rel, "kind": "secret_like", "match": pattern.pattern})
        for marker in MOJIBAKE_MARKERS:
            if marker in text:
                issues.append({"path": rel, "kind": "mojibake_marker", "match": _redact(marker)})
    return issues


def _private_terms(extra_denies: list[str]) -> list[str]:
    terms = [
        str(Path.home()),
        str(Path.home()).replace("\\", "/"),
        str(ROOT),
        str(ROOT).replace("\\", "/"),
    ]
    username = os.environ.get("USERNAME") or os.environ.get("USER")
    if username:
        terms.append(username)
    terms.extend(extra_denies)
    return [term for term in terms if term]


def _redact(term: str) -> str:
    if len(term) <= 4:
        return "***"
    return f"{term[:2]}***{term[-2:]}"


if __name__ == "__main__":
    main()
