#!/usr/bin/env python3
"""tests for v4.0 core — interfaces, roles, session_bus, deep_graph"""
from __future__ import annotations

import sys
from pathlib import Path

# Add skill root to path for core imports
_skill_root = Path(__file__).resolve().parent.parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))

import pytest
from core.interfaces import LLMResponse, ToolResult
from core.session_bus import SessionBus, Fact, RiskSignal, Contradiction
from core.roles import AUTHORITIES, RoleAuthority
from core.deep_graph import DeepGraph, Entity, EntityType, RelationType
from core.query_cache import QueryCache
from core.org_memory import OrgMemory


# ═══════════════════════════════════════════════════════════
#  Interfaces
# ═══════════════════════════════════════════════════════════

class TestLLMResponse:
    def test_defaults(self):
        r = LLMResponse(ok=True, text="hello")
        assert r.ok is True
        assert r.text == "hello"
        assert r.tokens_used == 0

    def test_all_fields(self):
        r = LLMResponse(ok=False, text="", model="test", tokens_used=100,
                        latency_ms=500, error="timeout")
        assert r.ok is False
        assert r.model == "test"
        assert r.error == "timeout"

class TestToolResult:
    def test_basic(self):
        r = ToolResult(ok=True, data={"key": "val"}, sources=["src1"])
        assert r.ok is True
        assert r.data["key"] == "val"
        assert "src1" in r.sources


# ═══════════════════════════════════════════════════════════
#  Roles
# ═══════════════════════════════════════════════════════════

class TestRoleAuthorities:
    def test_all_13_roles_defined(self):
        assert len(AUTHORITIES) == 13

    def test_every_role_has_report_to(self):
        for rid, auth in AUTHORITIES.items():
            assert auth.report_to, f"{rid} missing report_to"

    def test_every_role_has_must_not(self):
        for rid, auth in AUTHORITIES.items():
            assert len(auth.must_not) >= 1, f"{rid} missing must_not rules"

    def test_qian_reports_to_user(self):
        assert "用户" in AUTHORITIES["qian-shou-zheng"].report_to

    def test_an_shao_no_requests(self):
        """暗哨不主动请求任何人"""
        assert AUTHORITIES["an-shao"].can_request == []

    def test_wu_de_hou_can_request_all(self):
        """吴政委可以对所有人提要求"""
        assert len(AUTHORITIES["wu-de-hou"].can_request) >= 1


# ═══════════════════════════════════════════════════════════
#  SessionBus
# ═══════════════════════════════════════════════════════════

class TestSessionBus:
    def test_basic_flow(self):
        bus = SessionBus("test-company")
        bus.add_fact("注册资本", "1000万", "张铁柱")
        bus.add_signal("失信记录", "HIGH", "赵刚")
        bus.add_contradiction("实控人", "张三", "李四", ["张铁柱", "马力全"])

        assert len(bus.facts) == 1
        assert len(bus.risk_signals) == 1
        assert len(bus.contradictions) == 1

    def test_verify_brief(self):
        bus = SessionBus("test")
        bus.add_fact("a", "1", "src")
        bus.add_fact("b", "2", "src2")
        bus.add_signal("s1", "HIGH", "src")

        brief = bus.build_verify_brief()
        assert len(brief["facts_to_verify"]) == 2
        assert len(brief["risk_signals"]) == 1

    def test_update_fact_verified(self):
        bus = SessionBus("test")
        bus.add_fact("x", "val", "src")
        bus.update_fact("x", verified=True, verifier="郑慎之")
        assert bus.facts[0].verified is True
        assert bus.facts[0].verifier == "郑慎之"

    def test_resolve_contradiction(self):
        bus = SessionBus("test")
        bus.add_contradiction("y", "a", "b", ["A", "B"])
        bus.resolve_contradiction("y", "确认为a", "钱守正")
        assert bus.contradictions[0].resolved is True

    def test_meeting_agenda(self):
        bus = SessionBus("test")
        bus.add_contradiction("z", "v1", "v2", ["A", "B"])
        bus.add_signal("risk", "HIGH", "src")
        agenda = bus.build_meeting_agenda()
        assert len(agenda) >= 2

    def test_report_brief(self):
        bus = SessionBus("test")
        bus.add_fact("a", "1", "src")
        bus.update_fact("a", verified=True, verifier="v")
        brief = bus.build_report_brief()
        assert len(brief["verified_facts"]) == 1
        assert len(brief["unverified_facts"]) == 0


# ═══════════════════════════════════════════════════════════
#  DeepGraph
# ═══════════════════════════════════════════════════════════

class TestDeepGraph:
    def test_create_graph(self):
        e = Entity(id="p1", type=EntityType.PERSON)
        g = DeepGraph(seed=e)
        assert g.seed.id == "p1"

    def test_add_entities(self):
        e = Entity(id="p1", type=EntityType.PERSON)
        g = DeepGraph(seed=e)
        g.add_entity(Entity(id="c1", type=EntityType.COMPANY))
        g.add_entity(Entity(id="c2", type=EntityType.COMPANY))
        assert len(g.nodes) == 3

    def test_add_relation(self):
        e = Entity(id="p1", type=EntityType.PERSON)
        g = DeepGraph(seed=e)
        g.add_relation("p1", "c1", RelationType.SHAREHOLDER, strength=0.8,
                       evidence=["tyc-mcp"])
        assert len(g.edges) == 1
        assert g.edges[0].strength == 0.8

    def test_summary(self):
        e = Entity(id="p1", type=EntityType.PERSON)
        g = DeepGraph(seed=e)
        g.add_entity(Entity(id="c1", type=EntityType.COMPANY))
        g.add_relation("p1", "c1", RelationType.EXECUTIVE)
        s = g.summary()
        assert s["total_nodes"] == 2
        assert s["total_edges"] == 1

    def test_cycle_detection(self):
        e = Entity(id="p1", type=EntityType.PERSON)
        g = DeepGraph(seed=e)
        g.add_entity(Entity(id="c1", type=EntityType.COMPANY))
        g.add_relation("p1", "c1", RelationType.SHAREHOLDER)
        g.add_relation("c1", "p1", RelationType.SAME_ADDRESS)
        cycles = g.detect_cycles()
        assert len(cycles) >= 1


# ═══════════════════════════════════════════════════════════
#  QueryCache
# ═══════════════════════════════════════════════════════════

class TestQueryCache:
    def test_key_generation(self):
        c = QueryCache()
        k1 = c.key("abc", "company_search")
        k2 = c.key("abc", "company_search")
        assert k1 == k2
        k3 = c.key("xyz", "company_search")
        assert k1 != k3

    def test_cache_hit(self):
        import asyncio

        c = QueryCache()
        call_count = 0

        async def fetcher(target, query_type):
            nonlocal call_count
            call_count += 1
            return {"data": target}

        async def run():
            r1 = await c.get_or_fetch("abc", "search", fetcher)
            r2 = await c.get_or_fetch("abc", "search", fetcher)
            return r1, r2

        r1, r2 = asyncio.run(run())
        assert r1 == r2
        assert call_count == 1
        assert c.stats["hits"] == 1
        assert c.stats["misses"] == 1


# ═══════════════════════════════════════════════════════════
#  OrgMemory
# ═══════════════════════════════════════════════════════════

class TestOrgMemory:
    def test_record_and_retrieve(self):
        m = OrgMemory()
        inv = m.record({
            "target": "test-company",
            "mode": "standard",
            "bus_summary": {"facts_count": 3},
            "branches_triggered": [],
            "roles_activated": ["zhang-tie-zhu"],
            "commissar_stats": {},
            "metrics": [],
        })
        assert inv["target"] == "test-company"
        recent = m.get_recent(5)
        assert len(recent) >= 1

    def test_agent_stats(self):
        m = OrgMemory()
        m.record({
            "target": "t1", "mode": "standard",
            "bus_summary": {}, "branches_triggered": [],
            "roles_activated": ["zhang-tie-zhu"],
            "commissar_stats": {},
            "metrics": [
                {"agent": "zhang-tie-zhu", "ok": True, "tok": 100, "phase": "phase1"},
                {"agent": "zhang-tie-zhu", "ok": True, "tok": 200, "phase": "phase1"},
            ],
        })
        stats = m.get_agent_stats("zhang-tie-zhu")
        assert stats is not None
        assert stats["total_tasks"] >= 2

    def test_build_injection_empty(self):
        m = OrgMemory()
        injection = m.build_injection()
        assert isinstance(injection, str)

    def test_reset(self):
        m = OrgMemory()
        m.record({"target": "t1", "mode": "standard", "bus_summary": {},
                   "branches_triggered": [], "roles_activated": [],
                   "commissar_stats": {}, "metrics": []})
        m.reset()
        recent = m.get_recent(10)
        assert len(recent) == 0
