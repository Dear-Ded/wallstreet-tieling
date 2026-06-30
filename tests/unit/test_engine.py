#!/usr/bin/env python3
"""Tests for core.engine."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# Ensure project imports resolve when tests are run directly.
_skill_root = Path(__file__).resolve().parent.parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))

import pytest

from api.agent import AgentState, DueDiligenceAgent, PersonalityProfile
from adapters.multi_datasource import AggregatedResult, QueryResult, QueryStatus
from core.engine import Engine
from core.intelligence_retrieval import EvidenceIngestor, RetrievalDomain
from core.interfaces import OutputProvider, PlatformAdapter, ToolProvider
from core.risk_event_store import RiskEventStore
from core.rules import NO_FABRICATION_TAGLINE
from core.session_bus import SessionBus


class DummyLLM:
    default_model = "dummy-model"

    async def chat(self, *args, **kwargs):  # pragma: no cover - safety net
        raise AssertionError("chat() should not be called in these unit tests")


class DummyTools(ToolProvider):
    async def search(self, query: str, tool_type: str, **kwargs):
        return SimpleNamespace(ok=True, data={}, sources=[], error="")

    def available_tools(self) -> set[str]:
        return set()


class DummyOutput(OutputProvider):
    def write(self, content: str, filename: str, subdir: str = "") -> Path:
        return Path(filename)


class FakeSearchEngine:
    async def search_available(self, query: str, params: dict, concurrency: int = 5):
        return AggregatedResult(
            results=[
                QueryResult(
                    source_name="engine_public_api",
                    source_type="rest_api",
                    status=QueryStatus.SUCCESS,
                    metadata={
                        "standardized_records": [
                            {
                                "source_name": "engine_public_api",
                                "source_type": "rest_api",
                                "entity": params["company"],
                                "title": f"{params['company']} enforcement signal",
                                "summary": "Public record indicates a possible 被执行 signal.",
                                "confidence": 0.8,
                                "evidence": [{"claim": "被执行 public record needs verification."}],
                            }
                        ]
                    },
                )
            ]
        )


class DummyRegistry:
    def __init__(self):
        self._agents: dict[str, DueDiligenceAgent] = {}
        self.woken: list[str] = []

    def ensure_agent(self, rid: str, target: str) -> DueDiligenceAgent:
        if rid not in self._agents:
            profile = PersonalityProfile(agent_id=rid, display_name=f"Agent {rid}")
            self._agents[rid] = DueDiligenceAgent(rid, profile, "")
        return self._agents[rid]

    def get(self, rid: str) -> DueDiligenceAgent | None:
        return self._agents.get(rid)

    def wake_agents(self, rids: list[str], target: str) -> None:
        for rid in rids:
            self.woken.append(rid)
            self.ensure_agent(rid, target)

    def active_role_ids(self) -> list[str]:
        return list(self._agents.keys())


def make_engine(*, target: str = "测试科技有限公司", mode: str = "standard",
                concurrency: int = 5, max_retries: int = 3) -> Engine:
    adapter = PlatformAdapter(llm=DummyLLM(), tools=DummyTools(), output=DummyOutput())
    engine = Engine(target, adapter, mode=mode, concurrency=concurrency, max_retries=max_retries)
    engine.registry = DummyRegistry()
    return engine


def make_agent(agent_id: str = "custom-role", display_name: str = "自定义角色") -> DueDiligenceAgent:
    profile = PersonalityProfile(agent_id=agent_id, display_name=display_name)
    return DueDiligenceAgent(agent_id, profile, "sub-skill")


class TestEngineInitAndCircuitBreaker:
    def test_init_clamps_concurrency_and_retries(self):
        engine = make_engine(concurrency=99, max_retries=42)
        assert engine.concurrency == 20
        assert engine.max_retries == 5

    def test_retry_delay_is_exponential_and_capped(self):
        engine = make_engine()

        assert engine._retry_delay(0) == 2
        assert engine._retry_delay(2) == 8
        assert engine._retry_delay(99) == engine._MAX_RETRY_DELAY_SEC

    def test_circuit_breaker_blocks_after_threshold(self):
        engine = make_engine()
        engine._cb_failures = engine._CB_FAIL_THRESHOLD
        engine._cb_open_since = time.monotonic()

        ok, reason = engine._cb_check()

        assert ok is False
        assert "熔断" in reason

    def test_circuit_breaker_enters_half_open_after_cooldown(self):
        engine = make_engine()
        engine._cb_failures = engine._CB_FAIL_THRESHOLD
        engine._cb_open_since = time.monotonic() - engine._CB_COOLDOWN_SEC - 1

        ok, reason = engine._cb_check()

        assert ok is True
        assert reason == "半开探测"
        assert engine._cb_half_open is True

    def test_circuit_breaker_record_resets_on_success(self):
        engine = make_engine()
        engine._cb_failures = 4
        engine._cb_half_open = True

        engine._cb_record(True)

        assert engine._cb_failures == 0
        assert engine._cb_half_open is False


class TestEngineHelpers:
    def test_build_user_prompt_includes_context_and_notes(self):
        engine = make_engine(target="华尔街驻铁岭办事处")
        agent = make_agent()
        agent.memory.key_findings.extend(["发现1", "发现2"])
        agent.memory.notes_to_self.append("内部备注")

        prompt = engine._build_user_prompt(agent, extra={"foo": "bar"})

        assert "对「华尔街驻铁岭办事处」执行尽调分析。" in prompt
        assert '"foo": "bar"' in prompt
        assert "发现1" in prompt
        assert "内部备注" in prompt
        assert NO_FABRICATION_TAGLINE in prompt

    def test_retrieval_plan_brief_is_available_for_phase_prompts(self):
        engine = make_engine(target="测试科技有限公司")

        brief = engine._build_retrieval_plan_brief()

        assert brief["seed_company"] == "测试科技有限公司"
        assert "ownership_control" in brief["coverage_domains"]
        assert "social_web" in brief["coverage_domains"]
        assert len(brief["priority_tasks"]) == 8
        assert any("实际控制人" in task["query"] for task in brief["priority_tasks"])

    def test_degraded_result_marks_agent_degraded(self):
        engine = make_engine()
        agent = make_agent()
        violations = [SimpleNamespace(rule="quality_issue")]

        result = engine._degraded_result(agent, "quality_fail", violations)

        assert agent.state == AgentState.DEGRADED
        assert result["ok"] is False
        assert result["degraded"] is True
        assert result["quality_flags"] == ["quality_issue"]

    def test_extract_to_bus_creates_facts_signals_and_contradictions(self):
        engine = make_engine()
        bus = SessionBus("目标公司")
        bus.add_fact("实控人", "张三", "source-a")
        bus.add_fact("实控人", "李四", "source-b")

        engine._extract_to_bus(
            [{"ok": True, "text": "注册资本: 1000万。实际控制人: 王五。失信记录。大存大贷。市场份额约30%。"}],
            bus,
        )

        assert any(f.key == "注册资本" for f in bus.facts)
        assert any(s.signal == "失信记录" for s in bus.risk_signals)
        assert any(s.signal == "大存大贷" for s in bus.risk_signals)
        assert any(c.item == "实控人" for c in bus.contradictions)
        assert any(u.claim == "市场份额或估值估算" for u in bus.unverified_claims)

    def test_update_bus_verified_marks_all_facts_verified(self):
        engine = make_engine()
        bus = SessionBus("目标公司")
        bus.add_fact("注册资本", "1000万", "source-a")
        bus.add_fact("实控人", "张三", "source-b")

        engine._update_bus_verified([{"ok": True, "text": "phase2 output"}], bus)

        assert all(f.verified for f in bus.facts)
        assert all(f.verifier == "郑慎之" for f in bus.facts)

    def test_detect_and_branch_appends_role_once(self):
        engine = make_engine(mode="deep")
        engine.template = {"phase1": ["zhang-tie-zhu"], "phase2": [], "conditional_branches": True}

        engine._detect_and_branch([
            {"ok": True, "text": "发现实控人不一致，需要继续核实。"}
        ])

        assert "ma-li-quan" in engine.template["phase2"]
        assert "ma-li-quan" in engine.registry.woken
        assert engine.branches_triggered
        assert engine.branches_triggered[0]["signal"] == "controller_anomaly"

    def test_assemble_report_handles_ok_and_empty_results(self):
        engine = make_engine()

        report = asyncio.run(
            engine._assemble_report([
                {"ok": True, "name": "甲", "text": "内容A"},
                {"ok": True, "name": "乙", "text": "内容B"},
                {"ok": False, "name": "丙", "text": ""},
            ])
        )
        empty = asyncio.run(engine._assemble_report([]))

        assert "## 甲" in report
        assert "内容A" in report
        assert "## 乙" in report
        assert "内容B" in report
        assert "降级输出" in empty


class TestEngineIntegrationLight:
    @pytest.mark.asyncio
    async def test_run_persists_risk_event_summary(self, tmp_path):
        engine = make_engine()
        engine.template = {"phase1": [], "phase2": [], "phase3": []}
        engine.risk_event_store = RiskEventStore(tmp_path / "risk-events.jsonl")
        seed_id = "company:测试科技有限公司"
        task = engine.retrieval_plan.by_domain(RetrievalDomain.COURT_ENFORCEMENT)[0]
        EvidenceIngestor.ingest_search_result(
            engine.retrieval_plan.graph,
            seed_entity_id=seed_id,
            task=task,
            result={
                "source": "court_fixture",
                "title": "失信与限制高消费公告",
                "evidence_type": "court_record",
                "confidence": 0.8,
                "claims": ["该公司被执行"],
            },
        )

        result = await engine.run()

        assert result["risk_event_summary"]["persisted"] == 1
        assert result["risk_event_summary"]["current"] == 1
        assert result["risk_event_summary"]["alert_count"] == 1
        assert result["risk_event_summary"]["alerts"][0]["event"]["id"].startswith("risk:")
        assert result["risk_event_summary"]["store"]["total_events"] == 1
        assert result["retrieval_summary"]["risk_event_count"] == 1
        assert result["source_diagnostics"] == []
        assert result["enterprise_cognition"]["company"] == "测试科技有限公司"
        assert result["enterprise_cognition"]["risk_events"][0]["event"]["id"].startswith("risk:")
        assert any("公开事件" in item for item in result["enterprise_cognition"]["risk_hypotheses"])
        assert result["enterprise_cognition"]["evidence_gaps"]

    @pytest.mark.asyncio
    async def test_run_executes_injected_search_engine(self, tmp_path):
        engine = make_engine(target="Demo Engine Co., Ltd.")
        engine.template = {"phase1": [], "phase2": [], "phase3": []}
        engine.risk_event_store = RiskEventStore(tmp_path / "risk-events.jsonl")
        engine.search_engine = FakeSearchEngine()

        result = await engine.run()

        assert result["retrieval_summary"]["ingested_count"] >= 1
        assert result["retrieval_summary"]["status_counts"]["success"] >= 1
        assert result["source_diagnostics"]
        assert result["risk_event_summary"]["alert_count"] >= 1
        assert result["risk_event_summary"]["alerts"][0]["event"]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_run_returns_degraded_payload_on_error(self, monkeypatch):
        engine = make_engine()

        async def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(engine, "_execute_phase", boom)

        result = await engine.run()

        assert result["error"] == "boom"
        assert result["report"]
        assert result["retrieval_plan"]["seed_company"] == engine.target
        assert result["retrieval_summary"] == {}
        assert result["source_diagnostics"] == []
        assert result["enterprise_cognition"] == {}
