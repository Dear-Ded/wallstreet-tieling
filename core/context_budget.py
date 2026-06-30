"""Context budgeting primitives for long-running intelligence workflows."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


SOURCE_RE = re.compile(
    r"\[(?:source|sources|url|来源|來源|出处|出處)\s*[:：][^\]]+\]",
    re.IGNORECASE,
)
RISK_RE = re.compile(
    r"("
    r"risk|warning|alert|abnormal|anomaly|enforcement|litigation|penalty|"
    r"风险|風險|异常|異常|失信|被执行|被執行|诉讼|訴訟|行政处罚|行政處罰|"
    r"现金流|現金流|关联交易|關聯交易|舆情|輿情|预警|預警"
    r")",
    re.IGNORECASE,
)


@dataclass
class ContextCapsule:
    """A compact, evidence-aware payload for the next agent or phase."""

    summary: str
    evidence_lines: list[str] = field(default_factory=list)
    risk_lines: list[str] = field(default_factory=list)
    recent_lines: list[str] = field(default_factory=list)
    source_count: int = 0
    original_chars: int = 0
    compressed_chars: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "evidence_lines": self.evidence_lines,
            "risk_lines": self.risk_lines,
            "recent_lines": self.recent_lines,
            "source_count": self.source_count,
            "original_chars": self.original_chars,
            "compressed_chars": self.compressed_chars,
        }

    def to_prompt_text(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"# Context Summary\n{self.summary}")
        if self.risk_lines:
            parts.append("# Risk Signals\n" + "\n".join(f"- {line}" for line in self.risk_lines))
        if self.evidence_lines:
            parts.append("# Evidence Lines\n" + "\n".join(f"- {line}" for line in self.evidence_lines))
        if self.recent_lines:
            parts.append("# Recent Lines\n" + "\n".join(f"- {line}" for line in self.recent_lines))
        return "\n\n".join(parts)


class ContextBudgetManager:
    """Compress phase outputs into bounded context capsules.

    The pattern mirrors mature agent systems: keep a short running state, retain
    evidence-bearing lines, and move full raw output to storage instead of
    sending it through every downstream prompt.
    """

    def __init__(
        self,
        *,
        max_summary_chars: int = 700,
        max_line_chars: int = 240,
        max_evidence_lines: int = 8,
        max_risk_lines: int = 8,
        max_recent_lines: int = 4,
    ) -> None:
        self.max_summary_chars = max_summary_chars
        self.max_line_chars = max_line_chars
        self.max_evidence_lines = max_evidence_lines
        self.max_risk_lines = max_risk_lines
        self.max_recent_lines = max_recent_lines

    def build_capsule(self, results: list[dict[str, Any]], *, target: str = "") -> ContextCapsule:
        ok_results = [
            item for item in results
            if isinstance(item, dict) and item.get("ok") and item.get("text")
        ]
        original_chars = sum(len(str(item.get("text", ""))) for item in ok_results)
        lines: list[str] = []
        source_count = 0

        for item in ok_results:
            name = str(item.get("name") or item.get("rid") or "agent")
            for raw_line in str(item.get("text", "")).splitlines():
                line = self._clean_line(raw_line)
                if not line:
                    continue
                source_count += len(SOURCE_RE.findall(line))
                lines.append(f"{name}: {line}")

        evidence_lines = self._dedupe(
            [line for line in lines if SOURCE_RE.search(line)]
        )[: self.max_evidence_lines]
        risk_lines = self._dedupe(
            [line for line in lines if RISK_RE.search(line)]
        )[: self.max_risk_lines]

        recent_lines: list[str] = []
        if not risk_lines and not evidence_lines:
            seen = set()
            for line in reversed(lines):
                key = line.lower()
                if key in seen:
                    continue
                seen.add(key)
                recent_lines.append(line)
                if len(recent_lines) >= self.max_recent_lines:
                    break
            recent_lines.reverse()

        summary_seed = self._dedupe(risk_lines + evidence_lines + recent_lines)
        if not summary_seed:
            summary = ""
        else:
            summary = "; ".join(self._trim(line) for line in summary_seed)
            summary = self._trim(summary, self.max_summary_chars)

        capsule = ContextCapsule(
            summary=summary,
            evidence_lines=[self._trim(line) for line in evidence_lines],
            risk_lines=[self._trim(line) for line in risk_lines],
            recent_lines=[self._trim(line) for line in recent_lines],
            source_count=source_count,
            original_chars=original_chars,
        )
        capsule.compressed_chars = len(summary)
        capsule.compressed_chars += sum(len(line) for line in capsule.evidence_lines)
        capsule.compressed_chars += sum(len(line) for line in capsule.risk_lines)
        capsule.compressed_chars += sum(len(line) for line in capsule.recent_lines)
        return capsule

    def _clean_line(self, value: str) -> str:
        return " ".join(value.strip().split())

    def _trim(self, value: str, max_chars: int | None = None) -> str:
        limit = max_chars or self.max_line_chars
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 14)].rstrip() + "...[truncated]"

    def _dedupe(self, lines: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for line in lines:
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(line)
        return unique
