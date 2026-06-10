#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from .interfaces import LLMResponse, PlatformAdapter
from .rules import (
    NO_FABRICATION_RULE, NO_FABRICATION_TAGLINE,
    ALL_USER_TEMPLATES, MODE_TEMPLATES,
    CONDITIONAL_BRANCH_RULES, SIGNAL_PRIORITY,
)
from .session_bus import SessionBus, Fact, RiskSignal, Contradiction, UnverifiedClaim

# v0.5.0 api/ 层兼容 — 仅 import agent/quality 数据结构，不 import 平台相关代码
from api.agent import DueDiligenceAgent, AgentState, AgentMemory
from api.agent_registry import AgentRegistry
from api.personality import get_personality, get_receptionist_greeting
from api.quality_rules import QualityRules, Violation

logger = logging.getLogger("wst.engine")


# ═══════════════════════════════════════════════════════════
#  编排引擎
# ═══════════════════════════════════════════════════════════

class Engine:
    """v0.5.0"ABC公司", adapter=adapter, mode="standard")
    result = await engine.run()
    """

    _CB_FAIL_THRESHOLD = 5
    _CB_COOLDOWN_SEC = 30.0
    _MAX_SIGNALS = 2  # 条件分支最多触发 2 个

    def __init__(self, target: str, adapter: PlatformAdapter, *,
                 mode: str = "standard", model: str | None = None,
                 concurrency: int = 5, max_retries: int = 3):
        self.target = target
        self.adapter = adapter
        self.mode = mode
        self.model = model or adapter.llm.default_model
        self.concurrency = min(concurrency, 20)
        self.max_retries = min(max_retries, 5)

        self.registry = AgentRegistry()
        self.template = MODE_TEMPLATES.get(mode, MODE_TEMPLATES["standard"])
        self.branches_triggered: list[dict] = []

        self._session_start = time.monotonic()
        self._all_metrics: list[dict] = []
        self._commissar_stats: dict[str, dict] = {}

        self._cb_failures = 0
        self._cb_open_since = 0.0
        self._cb_half_open = False
        self._cb_tripped = False

    # ── 熔断器 ──

    def _cb_check(self) -> tuple[bool, str]:
        if self._cb_failures < self._CB_FAIL_THRESHOLD:
            return True, ""
        elapsed = time.monotonic() - self._cb_open_since
        if elapsed < self._CB_COOLDOWN_SEC:
            return False, f"熔断 {self._CB_FAIL_THRESHOLD} 连败, 冷却 {self._CB_COOLDOWN_SEC - elapsed:.0f}s"
        if not self._cb_half_open:
            self._cb_half_open = True
            if not self._cb_tripped:
                self._cb_tripped = True
                logger.warning("熔断器打开：%d 次连续失败", self._cb_failures)
        return True, "半开探测"

    def _cb_record(self, success: bool) -> None:
        if success: self._cb_failures = 0; self._cb_half_open = False
        else:
            self._cb_failures += 1
            if self._cb_failures >= self._CB_FAIL_THRESHOLD:
                self._cb_open_since = time.monotonic(); self._cb_half_open = False

    # ── 主流程 ──

    async def run(self) -> dict:
        """完整尽调流程: P1 → Bus提取 → 信号检测 → 会议 → P2 → P3"""
        bus = SessionBus(self.target)

        # Phase 1: 并行调查
        p1 = await self._execute_phase("phase1", self.template.get("phase1", []))
        self._extract_to_bus(p1, bus)

        # 条件分支信号检测
        if self.template.get("conditional_branches") and p1:
            self._detect_and_branch(p1)

        # Phase 1.5: 团队会议
        if self.template.get("meeting") and bus.contradictions:
            transcript = await self._team_meeting(bus)
            bus.meeting_transcript = transcript

        # Phase 2: 验证 (收到结构化简报)
        verify_brief = bus.build_verify_brief()
        p2 = await self._execute_phase("phase2", self.template.get("phase2", []),
                                       extra_context=verify_brief)
        self._update_bus_verified(p2, bus)

        # Phase 3: 输出 (收到最终情报)
        report_brief = bus.build_report_brief()
        p3 = await self._execute_phase("phase3", self.template.get("phase3", []),
                                       extra_context=report_brief)

        report = await self._assemble_report(p3 + p2 + p1)
        return {
            "report": report,
            "roles_activated": self.registry.active_role_ids(),
            "branches_triggered": self.branches_triggered,
            "metrics": self._all_metrics,
            "commissar_stats": self._commissar_stats,
            "bus_summary": bus.to_dict(),
        }

    # ── Phase 执行 ──

    async def _execute_phase(self, phase: str, role_ids: list[str],
                             extra_context: dict | None = None) -> list[dict]:
        """真并发执行一个 Phase 的所有角色
        extra_context: Bus 提取的结构化情报，注入到 user prompt
        """
        if not role_ids:
            return []
        agents = [self.registry.ensure_agent(rid, self.target) for rid in role_ids]
        sem = asyncio.Semaphore(self.concurrency)

        async def _run_one(agent: DueDiligenceAgent) -> dict:
            agent.state = AgentState.WORKING
            mono = agent.inner_monologue(f"Phase {phase}")
            print(f"  [{agent.nickname}] {mono}")

            system_prompt = self._load_prompt(phase, agent.agent_id)

            for attempt in range(self.max_retries + 1):
                go, reason = self._cb_check()
                if not go:
                    return self._degraded_result(agent, f"circuit_open: {reason}")

                try:
                    resp = await self.adapter.llm.chat(
                        system_prompt=system_prompt,
                        user_prompt=self._build_user_prompt(agent, extra_context),
                        model=self.model, agent_name=agent.name,
                    )
                except Exception as e:
                    resp = LLMResponse(ok=False, text="", error=str(e))

                self._cb_record(resp.ok)
                self._all_metrics.append({
                    "agent": agent.agent_id, "name": agent.name, "phase": phase,
                    "ok": resp.ok, "ms": resp.latency_ms, "tok": resp.tokens_used, "retry": attempt,
                })

                if not resp.ok:
                    agent.emotion.update(success=False)
                    if attempt < 1:
                        await asyncio.sleep(2 ** (attempt + 1)); continue
                    return self._degraded_result(agent, resp.error)

                # ── 政委门禁 L1 + L2 ── (修复: 之前 L2 被跳过了)
                passed, violations = self._commissar_check(agent, resp.text, attempt)
                if passed:
                    agent.emotion.update(success=True, discovery=len(resp.text) > 800)
                    agent.memory.add_finding(f"[Phase {phase}] {resp.text[:200]}")
                    agent.state = AgentState.DONE
                    return {"ok": True, "text": resp.text, "name": agent.name,
                            "rid": agent.agent_id, "quality_flags": []}
                else:
                    agent.emotion.update(success=False, retry=True)
                    if attempt < self.max_retries:
                        feedback = self._pua_feedback(agent, violations, attempt + 1)
                        # PUA 反馈追加到 user prompt，不是 system prompt
                        agent.memory.notes_to_self.append(feedback)
                        await asyncio.sleep(2 ** (attempt + 1))
                    else:
                        agent.state = AgentState.DEGRADED
                        return self._degraded_result(agent, "quality_fail", violations)

            return self._degraded_result(agent, "max_retries")

        tasks = [_run_one(a) for a in agents]
        return list(await asyncio.gather(*tasks))

    # ── 政委门禁 L1 + L2 ──

    def _commissar_check(self, agent: DueDiligenceAgent, text: str,
                         attempt: int) -> tuple[bool, list[Violation]]:
        """L1: QualityRules.scan() → L2: validate_dd_output()"""
        violations = QualityRules.scan(text, agent.name)
        if violations:
            # L1 不通过 — 直接返回
            return False, violations

        # L1 通过 → L2 深度验证
        validation = QualityRules.validate_dd_output(text, agent.name)
        if validation["valid"]:
            self._commissar_stats[agent.agent_id] = {
                "name": agent.name, "pass": True,
                "attempts": attempt + 1, "degraded": False,
            }
            return True, []

        # L2 不通过
        if validation["stats"]["fabrication_indicators"] > 0:
            violations = [Violation(
                rule="fabrication_risk", field="full_text",
                detail=f"L2: {validation['stats']['fabrication_indicators']} 个编造信号",
                severity="ERROR",
            )]
        else:
            issues = "; ".join(validation.get("issues", [])[:3]) or "L2 质量不足"
            violations = [Violation(
                rule="quality_issue", field="full_text",
                detail=f"L2 不通过 (得分 {validation['score']:.0f}): {issues}",
                severity="WARN",
            )]
        self._commissar_stats[agent.agent_id] = {
            "name": agent.name, "pass": False,
            "attempts": attempt + 1, "degraded": False,
        }
        return False, violations

    # ── 条件分支 ──

    def _detect_and_branch(self, p1_results: list[dict]) -> None:
        """Phase 1 完成后: 信号检测 → 追加角色到 Phase 2"""
        all_text = " ".join(r.get("text", "") for r in p1_results if r.get("ok") and r.get("text"))
        if not all_text:
            return

        triggered = []
        for sig_id, rule in CONDITIONAL_BRANCH_RULES.items():
            for kw in rule["signal_keywords"]:
                if kw in all_text:
                    triggered.append({"signal": sig_id, "append_role": rule["append_role"],
                                      "desc": rule["desc"], "matched_keyword": kw})
                    break

        triggered.sort(key=lambda s: SIGNAL_PRIORITY.index(s["signal"])
                       if s["signal"] in SIGNAL_PRIORITY else 99)
        triggered = triggered[:self._MAX_SIGNALS]

        for sig in triggered:
            append_rid = sig["append_role"]
            p2 = self.template.setdefault("phase2", [])
            if append_rid not in p2:
                p2.append(append_rid)
                self.registry.wake_agents([append_rid], self.target)
                new_agent = self.registry.get(append_rid)
                if new_agent:
                    print(f"  🔀 条件分支: {sig['desc']} — {new_agent.name}加入")
                    self.branches_triggered.append(sig)

    # ── SessionBus 操作 ──

    def _extract_to_bus(self, p1_results: list[dict], bus: SessionBus) -> None:
        """Phase 1 原始输出 → SessionBus 结构化提取"""
        all_text = " ".join(r.get("text", "") for r in p1_results if r.get("ok"))
        if not all_text:
            return

        # 简单提取: 关键词匹配 → 结构化。后续可改为 LLM 提取。
        import re as _re

        # 注册资本
        m = _re.search(r'注册资本[：:]\s*([\d.,]+)\s*万', all_text)
        if m:
            bus.add_fact("注册资本", f"{m.group(1)}万", "张铁柱")

        # 实控人
        m = _re.search(r'实际控制人[：:为是]\s*(\S{2,10})', all_text)
        if m:
            bus.add_fact("实控人", m.group(1), "张铁柱")

        # 失信记录
        if "失信" in all_text:
            bus.add_signal("失信记录", "HIGH", "赵刚",
                          detail=all_text[all_text.find("失信"):all_text.find("失信")+80])

        # 大存大贷
        if "大存大贷" in all_text or "存贷双高" in all_text:
            bus.add_signal("大存大贷", "HIGH", "李明远")

        # 矛盾检测: 同一 key 的不同值
        key_values: dict[str, list[tuple[str, str]]] = {}
        for f in bus.facts:
            key_values.setdefault(f.key, []).append((f.value, f.source))
        for key, vals in key_values.items():
            if len(vals) >= 2 and len(set(v for v, _ in vals)) > 1:
                bus.add_contradiction(key, vals[0][0], vals[1][0],
                                      [s for _, s in vals[:2]])

        # 待验证声明
        if "市场份额" in all_text or "估值" in all_text:
            bus.unverified_claims.append(
                UnverifiedClaim(claim="市场份额或估值估算", basis="行业估算",
                               source="王思远"))

    def _update_bus_verified(self, p2_results: list[dict], bus: SessionBus) -> None:
        """Phase 2 验证结果 → 更新 Bus"""
        all_text = " ".join(r.get("text", "") for r in p2_results if r.get("ok"))
        if not all_text:
            return
        # 标记所有事实为已验证
        for f in bus.facts:
            bus.update_fact(f.key, verified=True, verifier="郑慎之")

    # ── 团队会议 ──

    async def _team_meeting(self, bus: SessionBus) -> list[str]:
        """Phase 1.5: 钱守正主持, 三轮议事"""
        agenda = bus.build_meeting_agenda()
        if not agenda:
            return ["[钱守正] 本轮无争议项，跳过会议。"]

        transcript: list[str] = []
        chair_id = "qian-shou-zheng"

        for item in agenda[:5]:  # 最多 5 项议程
            # 主持人开场
            opening = await self.adapter.llm.chat(
                system_prompt=f"你是钱守正，华尔街驻铁岭办事处总经理。主持团队会议。简洁、务实、不废话。当前调查对象: {self.target}。",
                user_prompt=f"议题: {item.get('detail', item.get('item', ''))}。简短介绍，抛给相关人员。",
                agent_name="钱守正",
            )
            transcript.append(f"[钱守正] {opening.text[:300]}")

            # 相关角色轮流发言 (仅第一个矛盾角色)
            agents = item.get("agents", [])
            if agents:
                a = agents[0]
                agent = self.registry.get(a)
                if agent:
                    context = "\n".join(transcript[-3:])
                    resp = await self.adapter.llm.chat(
                        system_prompt=f"你是{agent.name}。在团队会议中轮到你了。简洁回应。",
                        user_prompt=f"会议记录:\n{context}\n\n对'{item.get('item','')}'发表意见。",
                        agent_name=agent.name,
                    )
                    transcript.append(f"[{agent.name}] {resp.text[:200]}")

                if len(agents) >= 2:
                    b = agents[1]
                    agent2 = self.registry.get(b)
                    if agent2:
                        context = "\n".join(transcript[-3:])
                        resp2 = await self.adapter.llm.chat(
                            system_prompt=f"你是{agent2.name}。简短回应对方的观点。",
                            user_prompt=f"会议记录:\n{context}\n\n你的回应:",
                            agent_name=agent2.name,
                        )
                        transcript.append(f"[{agent2.name}] {resp2.text[:200]}")

            # 主持人裁决
            if item["type"] == "contradiction":
                bus.resolve_contradiction(
                    item["item"], f"会议裁决: {transcript[-1][:100]}", resolver="钱守正"
                )

        # 会议总结
        closing = await self.adapter.llm.chat(
            system_prompt="你是钱守正。会议总结。30字以内。",
            user_prompt=f"会议记录:\n" + "\n".join(transcript[-5:]),
            agent_name="钱守正",
        )
        transcript.append(f"[钱守正·总结] {closing.text[:100]}")

        return transcript

    # ── 辅助 ──

    def _load_prompt(self, phase: str, agent_id: str) -> str:
        """加载角色系统提示词: prompts/{platform}/ → api/sub-skills/ 回退"""
        prompt_dir = Path(__file__).resolve().parent.parent / "prompts" / "system"
        prompt_file = prompt_dir / f"{agent_id}.md"

        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")

        # 回退到 sub-skills
        sub_path = Path(__file__).resolve().parent.parent / "sub-skills" / f"{agent_id}.md"
        if sub_path.exists():
            return NO_FABRICATION_RULE + "\n\n---\n\n" + sub_path.read_text(encoding="utf-8")

        return NO_FABRICATION_RULE

    def _build_user_prompt(self, agent: DueDiligenceAgent,
                           extra: dict | None = None) -> str:
        template_fn = ALL_USER_TEMPLATES.get(agent.agent_id)
        text = template_fn(self.target) if template_fn else \
               f"对「{self.target}」执行尽调分析。按铁律要求输出。"

        # 注入 Bus 提取的结构化情报
        if extra:
            text = f"{text}\n\n# 前序阶段情报\n{json.dumps(extra, ensure_ascii=False, indent=2)}"

        if agent.memory.key_findings:
            findings = "\n".join(f"- {f}" for f in agent.memory.key_findings[-5:])
            text = f"{text}\n\n# 此前发现\n{findings}"

        # PUA 反馈（如果有）
        if agent.memory.notes_to_self:
            text = text + "\n\n" + "\n".join(agent.memory.notes_to_self[-2:])

        if NO_FABRICATION_TAGLINE not in text:
            text = f"{text}\n\n{NO_FABRICATION_TAGLINE}"

        return text

    def _degraded_result(self, agent, reason: str, violations=None) -> dict:
        agent.state = AgentState.DEGRADED
        return {"ok": False, "text": "", "name": agent.name, "rid": agent.agent_id,
                "degraded": True, "error": reason,
                "quality_flags": [v.rule for v in (violations or [])]}

    def _pua_feedback(self, agent, violations, attempt) -> str:
        v_desc = "; ".join(f"{v.rule}: {v.detail}" for v in violations[:3])
        return f"[吴政委 第{attempt}次退回] {v_desc}。重新来。"

    async def _assemble_report(self, results: list[dict]) -> str:
        ok = [r for r in results if r.get("ok") and r.get("text")]
        if not ok:
            return f"# 尽调报告 — {self.target}\n\n**状态**: 降级输出。\n建议: 检查 API Key、网络，或稍后重试。\n"
        return "\n---\n".join(
            f"## {r.get('name', 'Unknown')}\n\n{r['text']}\n" for r in ok
        )
