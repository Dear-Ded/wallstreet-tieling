#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — SessionBus 情报总线
Phase 间结构化情报传递。替代 v3.x 的散装文本拼接。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class Fact:
    """单个事实"""
    key: str                      # 如 "注册资本", "实控人"
    value: str                    # 如 "1000万", "张三"
    source: str                   # 如 "张铁柱/tyc-mcp"
    verified: bool = False
    verifier: str = ""
    confidence: float = 1.0       # 0-1, 初始来自数据源可信度


@dataclass
class RiskSignal:
    """风险信号"""
    signal: str                   # 如 "失信记录", "大存大贷"
    severity: str                 # HIGH / MEDIUM / LOW
    source: str                   # 来源角色
    detail: str = ""              # 详细描述
    resolved: bool = False
    resolution: str = ""


@dataclass
class Contradiction:
    """矛盾标注"""
    item: str                     # 矛盾项, 如 "实控人"
    value_a: str
    value_b: str
    agents: list[str]             # 产生矛盾的双方
    resolved: bool = False
    resolution: str = ""
    resolution_by: str = ""


@dataclass
class PersonLink:
    """人员关联"""
    person: str
    links: list[str]              # 关联的企业/电话/社交账号
    source: str
    risk_level: str = "LOW"


@dataclass
class UnverifiedClaim:
    """待验证声明"""
    claim: str                    # 如 "市场份额约30%"
    basis: str                    # 如 "行业估算"
    source: str                   # 来源角色
    verified: bool = False
    verification_result: str = ""


# ═══════════════════════════════════════════════════════════
#  SessionBus
# ═══════════════════════════════════════════════════════════

class SessionBus:
    """一次尽调会话的情报总线 — 引擎写入, 角色读取"""

    def __init__(self, target: str):
        self.target = target
        self.session_id = f"bus-{int(time.time())}"
        self.created_at = time.time()

        self.facts: list[Fact] = []
        self.risk_signals: list[RiskSignal] = []
        self.contradictions: list[Contradiction] = []
        self.person_links: list[PersonLink] = []
        self.unverified_claims: list[UnverifiedClaim] = []
        self.meeting_transcript: list[str] = []

    # ── 写入 ──

    def add_fact(self, key: str, value: str, source: str, confidence: float = 1.0) -> Fact:
        f = Fact(key=key, value=value, source=source, confidence=confidence)
        self.facts.append(f)
        return f

    def add_signal(self, signal: str, severity: str, source: str, detail: str = "") -> RiskSignal:
        s = RiskSignal(signal=signal, severity=severity, source=source, detail=detail)
        self.risk_signals.append(s)
        return s

    def add_contradiction(self, item: str, value_a: str, value_b: str,
                          agents: list[str]) -> Contradiction:
        c = Contradiction(item=item, value_a=value_a, value_b=value_b, agents=agents)
        self.contradictions.append(c)
        return c

    def update_fact(self, key: str, *, verified: bool = True, verifier: str = "") -> Fact | None:
        for f in self.facts:
            if f.key == key:
                f.verified = verified
                f.verifier = verifier
                return f
        return None

    def resolve_contradiction(self, item: str, resolution: str, resolver: str = "") -> Contradiction | None:
        for c in self.contradictions:
            if c.item == item:
                c.resolved = True
                c.resolution = resolution
                c.resolution_by = resolver
                return c
        return None

    # ── Phase 间视图 ──

    def build_verify_brief(self) -> dict:
        """Phase 2 验证角色收到的结构化简报"""
        return {
            "facts_to_verify": [
                {"key": f.key, "value": f.value, "source": f.source}
                for f in self.facts if not f.verified
            ],
            "risk_signals": [
                {"signal": s.signal, "severity": s.severity, "source": s.source, "detail": s.detail}
                for s in self.risk_signals if not s.resolved
            ],
            "contradictions": [
                {"item": c.item, "value_a": c.value_a, "value_b": c.value_b, "agents": c.agents}
                for c in self.contradictions if not c.resolved
            ],
            "unverified_claims": [
                {"claim": u.claim, "basis": u.basis, "source": u.source}
                for u in self.unverified_claims if not u.verified
            ],
        }

    def build_report_brief(self) -> dict:
        """Phase 3 报告角色收到的最终情报"""
        return {
            "verified_facts": [
                {"key": f.key, "value": f.value, "source": f.source, "verifier": f.verifier}
                for f in self.facts if f.verified
            ],
            "unverified_facts": [
                {"key": f.key, "value": f.value, "source": f.source}
                for f in self.facts if not f.verified
            ],
            "risk_signals": [
                {"signal": s.signal, "severity": s.severity, "resolved": s.resolved,
                 "resolution": s.resolution}
                for s in self.risk_signals
            ],
            "contradictions_resolved": [
                {"item": c.item, "resolution": c.resolution, "by": c.resolution_by}
                for c in self.contradictions if c.resolved
            ],
            "contradictions_open": [
                {"item": c.item, "value_a": c.value_a, "value_b": c.value_b}
                for c in self.contradictions if not c.resolved
            ],
            "meeting_transcript": self.meeting_transcript[-10:],
        }

    def build_meeting_agenda(self) -> list[dict]:
        """Phase 1.5 会议议程"""
        items = []
        for c in self.contradictions:
            items.append({"type": "contradiction", "item": c.item, "priority": "HIGH",
                          "detail": f"{c.value_a} vs {c.value_b}", "agents": c.agents})
        for s in self.risk_signals:
            if s.severity == "HIGH":
                items.append({"type": "risk", "signal": s.signal, "priority": "HIGH",
                              "detail": s.detail})
        return sorted(items, key=lambda x: 0 if x["priority"] == "HIGH" else 1)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "target": self.target,
            "facts_count": len(self.facts),
            "signals_count": len(self.risk_signals),
            "contradictions_count": len(self.contradictions),
            "verified_count": sum(1 for f in self.facts if f.verified),
            "unresolved_count": sum(1 for c in self.contradictions if not c.resolved),
        }
