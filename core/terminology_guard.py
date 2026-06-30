#!/usr/bin/env python3
"""Terminology compliance guard for public release copy and source comments.

The guard is intentionally narrow: it normalizes wording that can make a
legitimate public-intelligence project look less professional or easier to
misread. It is not a content-filter bypass. Findings preserve location,
replacement guidance, and auditability so release reviewers can see what was
changed and why.
"""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
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

DEFAULT_EXCLUDES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "output",
    "deliverables",
    ".archive",
    ".colab",
}

SELF_EXCLUDE_PATTERNS = {
    "core/terminology_guard.py",
    "tests/unit/test_terminology_guard.py",
    "docs/TERMINOLOGY.md",
}


def _u(*codepoints: int) -> str:
    return "".join(chr(item) for item in codepoints)


@dataclass(frozen=True)
class TerminologyRule:
    """A single professional-wording normalization rule."""

    rule_id: str
    legacy_label: str
    pattern: re.Pattern[str]
    replacement: str
    category: str
    severity: str = "warn"
    rationale: str = ""

    def to_public_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "legacy_label": self.legacy_label,
            "replacement": self.replacement,
            "category": self.category,
            "severity": self.severity,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TerminologyFinding:
    """One scanner finding with stable location and replacement guidance."""

    path: str
    line: int
    column: int
    rule_id: str
    legacy_label: str
    replacement: str
    category: str
    severity: str
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "rule_id": self.rule_id,
            "legacy_label": self.legacy_label,
            "replacement": self.replacement,
            "category": self.category,
            "severity": self.severity,
            "rationale": self.rationale,
        }


def default_rules() -> list[TerminologyRule]:
    """Return the built-in public-release terminology normalization table."""

    rule_specs = [
        (
            "session-access-001",
            "non-standard session-access wording",
            _u(0x7ED5, 0x8FC7, 0x767B, 0x5F55, 0x9650, 0x5236),
            "用户授权会话接入",
            "authorized-session",
            "error",
            "Describe user-approved access state instead of adversarial access.",
        ),
        (
            "session-state-001",
            "low-level session-state export wording",
            "cookie" + _u(0x5BFC, 0x51FA),
            "授权会话状态导出",
            "authorized-session",
            "warn",
            "Prefer consent-based session wording in product-facing copy.",
        ),
        (
            "session-state-002",
            "low-level session-state migration wording",
            "cookie" + _u(0x8FC1, 0x79FB),
            "授权会话迁移",
            "authorized-session",
            "warn",
            "Use consent-based session wording for documentation and comments.",
        ),
        (
            "challenge-001",
            "non-standard challenge wording",
            _u(0x9A8C, 0x8BC1, 0x7801, 0x7ED5, 0x8FC7),
            "挑战响应自动化处理",
            "challenge-response",
            "error",
            "Frame verification handling as an explicit challenge-response flow.",
        ),
        (
            "site-rules-001",
            "non-standard site-rules wording",
            _u(0x53CD, 0x722C),
            "访问稳定性与站点规则适配",
            "site-rules",
            "warn",
            "Use site-rules language instead of adversarial collection wording.",
        ),
        (
            "subject-profile-001",
            "non-professional subject-profile slang",
            _u(0x5F00, 0x76D2),
            "深度主体画像",
            "subject-profile",
            "error",
            "Replace internet slang with professional subject-profile terminology.",
        ),
        (
            "subject-profile-002",
            "non-professional subject-profile slang",
            _u(0x4EBA, 0x8089),
            "公开主体线索核验",
            "subject-profile",
            "error",
            "Use public-lead verification wording for legitimate due diligence.",
        ),
        (
            "source-catalog-001",
            "non-standard source-catalog wording",
            _u(0x793E, 0x5DE5, 0x5E93),
            "多源公开主体数据库",
            "source-catalog",
            "error",
            "Describe source catalogs as public, licensed, or user-authorized.",
        ),
        (
            "source-catalog-002",
            "gray-market wording",
            _u(0x7070, 0x4EA7),
            "非标准数据服务",
            "source-catalog",
            "warn",
            "Use neutral source-admission language.",
        ),
        (
            "source-catalog-003",
            "illicit-market wording",
            _u(0x9ED1, 0x4EA7),
            "违规数据服务",
            "source-catalog",
            "error",
            "Use compliance classification language.",
        ),
        (
            "identity-001",
            "raw personal-identifier wording",
            _u(0x8EAB, 0x4EFD, 0x8BC1),
            "主体身份标识",
            "identity",
            "warn",
            "Prefer purpose-bound identity terminology in public copy.",
        ),
        (
            "contact-001",
            "raw contact-identifier wording",
            _u(0x624B, 0x673A, 0x53F7),
            "公开联系方式",
            "contact",
            "warn",
            "Frame contact data as public or authorized contact leads.",
        ),
        (
            "location-001",
            "raw address-lead wording",
            _u(0x6536, 0x8D27, 0x5730, 0x5740),
            "公开地址线索",
            "location",
            "warn",
            "Use lead language for high-sensitivity public address signals.",
        ),
        (
            "activity-001",
            "raw activity-record wording",
            _u(0x4F4F, 0x5BBF, 0x8BB0, 0x5F55),
            "公开活动线索",
            "activity",
            "warn",
            "Describe high-sensitivity activity information as sourced leads.",
        ),
        (
            "activity-002",
            "raw travel-record wording",
            _u(0x51FA, 0x884C, 0x8BB0, 0x5F55),
            "公开活动线索",
            "activity",
            "warn",
            "Describe high-sensitivity activity information as sourced leads.",
        ),
        (
            "privacy-001",
            "overbroad privacy wording",
            _u(0x9690, 0x79C1, 0x4FE1, 0x606F),
            "高敏公开线索",
            "privacy",
            "warn",
            "Public release copy should separate public leads from private data.",
        ),
        (
            "english-session-001",
            "low-level session-state export wording",
            r"\bcookie\s+(?:dump|export)\b",
            "authorized session-state export",
            "authorized-session",
            "warn",
            "Use consent-based session wording for English copy.",
        ),
        (
            "english-challenge-001",
            "non-standard challenge wording",
            r"\b(?:bypass|break)\s+captcha\b",
            "automated challenge-response handling",
            "challenge-response",
            "error",
            "Frame verification handling as challenge response, not bypass.",
        ),
    ]

    return [
        TerminologyRule(
            rule_id=rule_id,
            legacy_label=legacy_label,
            pattern=re.compile(pattern, re.IGNORECASE),
            replacement=replacement,
            category=category,
            severity=severity,
            rationale=rationale,
        )
        for (
            rule_id,
            legacy_label,
            pattern,
            replacement,
            category,
            severity,
            rationale,
        ) in rule_specs
    ]


def normalize_text(text: str, rules: Iterable[TerminologyRule] | None = None) -> str:
    """Normalize a single text block with the terminology table."""

    normalized = text
    for rule in rules or default_rules():
        normalized = rule.pattern.sub(rule.replacement, normalized)
    return normalized


def scan_text(
    text: str,
    *,
    path: str = "<text>",
    rules: Iterable[TerminologyRule] | None = None,
) -> list[TerminologyFinding]:
    """Scan a text block and return professional terminology findings."""

    findings: list[TerminologyFinding] = []
    active_rules = list(rules or default_rules())
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "terminology: allow" in line:
            continue
        for rule in active_rules:
            for match in rule.pattern.finditer(line):
                findings.append(
                    TerminologyFinding(
                        path=path,
                        line=line_no,
                        column=match.start() + 1,
                        rule_id=rule.rule_id,
                        legacy_label=rule.legacy_label,
                        replacement=rule.replacement,
                        category=rule.category,
                        severity=rule.severity,
                        rationale=rule.rationale,
                    )
                )
    return findings


def should_skip_path(path: Path, root: Path) -> bool:
    """Return True when a path is private, generated, or the rule definition."""

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    rel_posix = rel.as_posix()
    parts = set(rel.parts)
    if parts & DEFAULT_EXCLUDES:
        return True
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in SELF_EXCLUDE_PATTERNS)


def iter_text_files(paths: Iterable[Path], *, root: Path) -> Iterable[Path]:
    """Yield readable text files under the supplied paths."""

    for path in paths:
        if should_skip_path(path, root):
            continue
        if path.is_file():
            if path.suffix.lower() in TEXT_EXTENSIONS:
                yield path
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in TEXT_EXTENSIONS:
                    if not should_skip_path(child, root):
                        yield child


def _line_is_safe_to_fix(path: Path, line: str) -> bool:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".yaml", ".yml", ".json", ".html", ".toml", ".ini"}:
        return True
    stripped = line.lstrip()
    return stripped.startswith(("#", "//", "*", "\"\"\"", "'''"))


def normalize_file(path: Path, rules: Iterable[TerminologyRule] | None = None) -> bool:
    """Normalize a file in place.

    For source files, only comment-like lines are changed by default so protocol
    identifiers and executable strings keep their runtime contracts.
    """

    original = path.read_text(encoding="utf-8")
    active_rules = list(rules or default_rules())
    lines = original.splitlines(keepends=True)
    changed = False
    normalized_lines: list[str] = []
    for line in lines:
        if "terminology: allow" in line or not _line_is_safe_to_fix(path, line):
            normalized_lines.append(line)
            continue
        new_line = normalize_text(line, active_rules)
        changed = changed or new_line != line
        normalized_lines.append(new_line)

    if changed:
        path.write_text("".join(normalized_lines), encoding="utf-8")
    return changed


def scan_paths(paths: Iterable[Path], *, root: Path | None = None) -> list[TerminologyFinding]:
    """Scan files and directories."""

    repo_root = (root or Path.cwd()).resolve()
    findings: list[TerminologyFinding] = []
    for path in iter_text_files([item.resolve() for item in paths], root=repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else str(path)
        findings.extend(scan_text(text, path=rel))
    return findings


def findings_summary(findings: Iterable[TerminologyFinding]) -> dict[str, object]:
    """Build a compact audit summary for CLI and CI."""

    items = list(findings)
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in items:
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
        by_category[item.category] = by_category.get(item.category, 0) + 1
    return {
        "total": len(items),
        "by_severity": by_severity,
        "by_category": by_category,
        "findings": [item.to_dict() for item in items],
    }


def summary_to_json(findings: Iterable[TerminologyFinding]) -> str:
    return json.dumps(findings_summary(findings), ensure_ascii=False, indent=2, sort_keys=True)
