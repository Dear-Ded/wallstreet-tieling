#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 平台无关编排引擎
核心升级: Orchestrator 不再直接调用外部 API，一切通过 PlatformAdapter 抽象。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .interfaces import LLMProvider, LLMResponse, ToolProvider, OutputProvider
from .roles import AUTHORITIES, RoleAuthority

# 保持与 v3.2.0 api/ 层的向后兼容
import sys as _sys
_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in _sys.path:
    _sys.path.insert(0, str(_skill_root))

from api.agent import DueDiligenceAgent, AgentState, Mood, AgentMemory, AgentMessage
from api.agent_registry import AgentRegistry
from api.personality import get_personality, get_all_agent_ids, get_receptionist_greeting
from api.quality_rules import QualityRules, Violation
from api.wst import (
    NO_FABRICATION_RULE, NO_FABRICATION_TAGLINE,
    ALL_USER_TEMPLATES,
    CONDITIONAL_BRANCH_RULES,
)

logger = logging.getLogger("wst.engine")


# ═══════════════════════════════════════════════════════════
#  模式模板（平台无关 — 只定义哪个角色参与哪个阶段）
# ═══════════════════════════════════════════════════════════

MODE_TEMPLATES: dict[str, dict] = {
    "simple": {
        "phase1": ["zhang-tie-zhu"],
        "phase2": [],
        "phase3": [],
    },
    "standard": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua"],
    },
    "deep": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "conditional_branches": True,
    },
    "sme": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "zhao-gang"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": ["liu-wen-hua"],
    },
    "people": {
        "phase1": ["ma-li-quan", "zhou-tong"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": [],
    },
    "report": {
        "phase1": [],
        "phase2": [],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
    },
}


# ═══════════════════════════════════════════════════════════
#  编排引擎
# ═══════════════════════════════════════════════════════════

class Engine:
    """v4.0 平台无关编排引擎

    用法:
        adapter = WorkBuddyAdapter(...)    # 或 CLIAdapter(...)
        engine = Engine(target="ABC公司", adapter=adapter, mode="standard")
        result = await engine.run()

    引擎本身:
        - 不调用 aiohttp
        - 不读环境变量
        - 不引用 MCP/Skill 工具名
        - 仅通过 adapter 的三个接口与外部交互
    """

    # ── 熔断器配置 ──
    _CB_FAIL_THRESHOLD = 5
    _CB_COOLDOWN_SEC = 30.0

    def __init__(
        self,
        target: str,
        adapter: "PlatformAdapter",
        *,
        mode: str = "standard",
        model: str | None = None,
        concurrency: int = 5,
        max_retries: int = 3,
    ):
        self.target = target
        self.adapter = adapter
        self.mode = mode
        self.model = model or adapter.llm.default_model
        self.concurrency = min(concurrency, 20)
        self.max_retries = min(max_retries, 5)

        self.registry = AgentRegistry()
        self.template = MODE_TEMPLATES.get(mode, MODE_TEMPLATES["standard"])
        self.branches_triggered: list[dict] = []

        # 指标
        self._session_start = time.monotonic()
        self._all_metrics: list[dict] = []
        self._commissar_stats: dict[str, dict] = {}

        # 熔断器
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
        if success:
            self._cb_failures = 0
            if self._cb_half_open:
                logger.info("熔断器恢复：半开探测成功")
            self._cb_half_open = False
        else:
            self._cb_failures += 1
            if self._cb_failures >= self._CB_FAIL_THRESHOLD:
                self._cb_open_since = time.monotonic()
                self._cb_half_open = False

    # ── 主流程 ──

    async def run(self) -> dict:
        """主入口：单次尽调全流程"""
        p1 = await self._execute_phase("phase1", self.template["phase1"], "Phase1 角色提示")
        p2 = await self._execute_phase("phase2", self.template.get("phase2", []), "Phase2 角色提示")
        p3 = await self._execute_phase("phase3", self.template.get("phase3", []), "Phase3 角色提示")

        report = await self._assemble_report(p3 + p2 + p1)
        return {
            "report": report,
            "roles_activated": self.registry.active_role_ids(),
            "branches_triggered": self.branches_triggered,
            "metrics": self._all_metrics,
        }

    async def _execute_phase(self, phase: str, role_ids: list[str], prompt: str) -> list[dict]:
        """执行一个 Phase → 通过 adapter 调模型"""
        results: list[dict] = []
        agents = [self.registry.ensure_agent(rid, self.target) for rid in role_ids]

        sem = asyncio.Semaphore(self.concurrency)

        async def _run_one(agent: DueDiligenceAgent) -> dict:
            agent.state = AgentState.WORKING
            # 内部独白
            mono = agent.inner_monologue(f"Phase {phase}")
            print(f"  [{agent.nickname}] {mono}")

            for attempt in range(self.max_retries + 1):
                # 熔断器检查
                go, reason = self._cb_check()
                if not go:
                    return self._degraded_result(agent, f"circuit_open: {reason}")

                try:
                    resp = await self.adapter.llm.chat(
                        system_prompt=prompt,
                        user_prompt=self._build_user_prompt(agent),
                        model=self.model,
                        agent_name=agent.name,
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
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    return self._degraded_result(agent, resp.error)

                text = resp.text
                passed, violations = QualityRules.scan(text, agent.name), []
                passed = passed == []  # scan returns violations list
                if not passed:
                    violations = QualityRules.scan(text, agent.name)

                if not violations:
                    agent.emotion.update(success=True, discovery=len(text) > 800)
                    agent.memory.add_finding(f"[Phase {phase}] {text[:200]}")
                    agent.state = AgentState.DONE
                    return {"ok": True, "text": text, "name": agent.name, "rid": agent.agent_id,
                            "quality_flags": []}

                agent.emotion.update(success=False, retry=True)
                if attempt < self.max_retries:
                    feedback = self._generate_pua_feedback(agent, violations, attempt + 1)
                    prompt = prompt + feedback
                    await asyncio.sleep(2 ** (attempt + 1))
                else:
                    agent.state = AgentState.DEGRADED
                    return self._degraded_result(agent, "quality_fail", violations)

            return self._degraded_result(agent, "max_retries")

        tasks = [_run_one(a) for a in agents]
        results = await asyncio.gather(*tasks)
        return list(results)

    def _build_user_prompt(self, agent: DueDiligenceAgent) -> str:
        """构建角色的 user prompt"""
        template_fn = ALL_USER_TEMPLATES.get(agent.agent_id)
        if template_fn:
            text = template_fn(self.target)
        else:
            text = f"对「{self.target}」执行尽调分析。按铁律要求输出。"

        if agent.memory.key_findings:
            findings = "\n".join(f"- {f}" for f in agent.memory.key_findings[-5:])
            text = f"{text}\n\n# 此前发现\n{findings}"

        if NO_FABRICATION_TAGLINE not in text:
            text = f"{text}\n\n{NO_FABRICATION_TAGLINE}"

        return text

    def _degraded_result(self, agent, reason: str, violations=None) -> dict:
        agent.state = AgentState.DEGRADED
        return {
            "ok": False, "text": "", "name": agent.name, "rid": agent.agent_id,
            "degraded": True, "error": reason,
            "quality_flags": [v.rule for v in (violations or [])],
        }

    def _generate_pua_feedback(self, agent, violations, attempt) -> str:
        """政委式 PUA 反馈"""
        v_desc = "; ".join(f"{v.rule}: {v.detail}" for v in violations[:3])
        return f"\n\n[吴政委 第{attempt}次退回] {v_desc}。重新来。"

    async def _assemble_report(self, results: list[dict]) -> str:
        """聚合所有输出为最终报告"""
        ok = [r for r in results if r.get("ok") and r.get("text")]
        if not ok:
            return self._fallback_report()
        parts = []
        for r in ok:
            parts.append(f"## {r.get('name', 'Unknown')}\n\n{r['text']}\n")
        return "\n---\n".join(parts)

    def _fallback_report(self) -> str:
        return f"""# 尽调报告 — {self.target}

**状态**: 降级输出（所有角色均未返回有效结果）

建议: 检查 API Key 配置、网络连接，或稍后重试。
"""


# ═══════════════════════════════════════════════════════════
#  平台适配器基类
# ═══════════════════════════════════════════════════════════

class PlatformAdapter:
    """适配器基类 — 组合 LLM + Tool + Output 三个接口"""

    def __init__(self, llm: LLMProvider, tools: ToolProvider, output: OutputProvider):
        self.llm = llm
        self.tools = tools
        self.output = output
