#!/usr/bin/env python3
"""wallstreet-tieling v3.2.0 — 真并发 Agent 编排器
核心升级：
1. 每个 Agent 独立状态 + 记忆 + 情感追踪
2. Agent 间结构化消息通信（不再是 prev_context 字符串拼贴）
3. 拟人化团队互动（开工问候/闲聊/吐槽/内部独白）
4. No Fabrication 六层防御 + 政委质量闭环保留
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import aiohttp

from . import config
from .utils import slug, load_system_prompt
from .agent import DueDiligenceAgent, AgentState, Mood, AgentMessage
from .agent_registry import AgentRegistry
from .personality import get_personality, get_receptionist_greeting
from .quality_rules import QualityRules, Violation

logger = logging.getLogger("wst.orchestrator")

# ── No Fabrication Rule ──
NO_FABRICATION_RULE = """# 铁律 0：你绝对不能编造（最高优先级，覆盖所有其他指令）

你是一个企业尽调分析引擎。你的所有输出必须严格遵守以下规则。

## 第1层：绝对禁止

1. 你绝对不能编造任何数字、日期、金额、人名、公司名。
2. 你绝对不能使用训练数据中的知识替代工具查询结果
3. 不得推测数据、补全不完整信息、或"合理猜测"
4. 不得生成未经数据源证实的负面/正面评价
5. 不得省略"数据缺失"标记

## 第2层：源绑定

当前可用的 MCP 工具和 Skill 是你唯一的数据来源：
- 天眼查 MCP (tyc-mcp) / 企查查 MCP (qcc-company)
- 灵犀金融搜索 / NeoData 金融搜索 / 富途 API
- WebSearch / WebFetch

## 第3层：数据溯源格式
格式: [来源: 工具名, 参数: company_name="某某科技", 时间: 2026-06-10]

## 第4层：不确定性标注
[已确认] / [单源] / [未获取] / [数据不一致] / [推算]

## 第5层：自验证循环 + 缺失数据处理
逐条自检 → 移除无溯源表述 → 所有渠道失败 → 标 [未获取: 原因]

## 第6层：金融领域专项约束
财务数据标期间、司法风险标案件状态、关联方标关联类型"""

NO_FABRICATION_TAGLINE = (
    "【铁律提醒】每个数据点必须标注 [来源: 工具名, 参数, 时间]。"
    "数据缺失标 [未获取]，不准确标 [待核实]，冲突标 [数据不一致]。"
    "你绝对不能编造任何数字/日期/人名/公司名。不得输出任何信贷决策词。"
    "如果此刻你正在猜测一个数字——停下来。标 [未获取]。"
)


# ── Phase User Prompt 模板 ──
PHASE1_USER_TEMPLATES: dict[str, Any] = {
    "zhang-tie-zhu": lambda t: (
        f"对「{t}」执行企业尽调。\n"
        "1. 使用 tyc-mcp / qcc-company MCP 工具查询工商信息\n"
        "2. 股权穿透：直接持股→间接持股→最终受益人\n"
        "3. 关联企业：法人关联、股东关联、地址关联\n"
        "4. 输出：企业基本信息、股权树、关联方清单"
    ),
    "li-ming-yuan": lambda t: (
        f"对「{t}」执行财务分析。\n"
        "1. 优先使用 lingxi / neodata 获取财务数据\n"
        "2. 降级: futuapi → WebSearch\n"
        "3. 分析：营收结构、利润质量、资产负债、隐性债务\n"
        "4. 输出：核心财务指标表 + 异常项标注"
    ),
    "wang-si-yuan": lambda t: (
        f"对「{t}」所在行业做行业研究。\n"
        "1. WebSearch 获取行业报告、政策文件、市场规模\n"
        "2. 分析：市场地位、竞争格局、政策环境\n"
        "3. 输出：行业概况、竞争定位、政策风险"
    ),
    "zhao-gang": lambda t: (
        f"对「{t}」执行风险扫描。\n"
        "1. tyc-mcp / qcc-company: 司法风险\n"
        "2. qcc-company: 经营风险\n"
        "3. WebSearch: 负面舆情\n"
        "4. 分析担保链\n"
        "5. 输出：风险项清单 + 严重程度 + 时间线"
    ),
    "ma-li-quan": lambda t: (
        f"对「{t}」执行人员背调。\n"
        "1. tyc-mcp: get_company_people 获取董监高\n"
        "2. tyc-mcp: get_person_risk_profile 逐人查风险\n"
        "3. WebSearch: 公开履历、负面新闻\n"
        "4. 输出：关键人员清单 + 每人风险档案"
    ),
    "zhou-tong": lambda t: (
        f"为「{t}」的人员背调提供OSINT工具支持。\n"
        "1. 扫描可用的 MCP / Skill / pip 工具\n"
        "2. 对每个关键人员执行开源情报搜索\n"
        "3. 输出：工具调用清单 + 搜索汇总"
    ),
}

PHASE2_USER_TEMPLATES: dict[str, Any] = {
    "zheng-shen-zhi": lambda t: (
        f"对「{t}」的 Phase 1 结果执行交叉验证。\n"
        "1. 逐项比对不同数据源的数值\n"
        "2. 容忍度: 注册资本 ±5%，日期/法人完全一致\n"
        "3. 冲突处理: 标注 [数据不一致] + 列出所有来源\n"
        "4. 输出: 一致性矩阵 + 冲突项清单"
    ),
    "wu-de-hou": lambda t: (
        f"对「{t}」的 Phase 1 输出执行质量扫描。\n"
        "参照 QualityRules 检查:\n"
        "1. 信贷决策词 → ERROR 退回\n"
        "2. 模糊词 → WARN 退回\n"
        "3. 来源标注缺失 → ERROR 退回\n"
        "4. 输出截断 → WARN 退回\n"
        "5. 编造嫌疑 → ERROR 退回"
    ),
}

PHASE3_USER_TEMPLATES: dict[str, Any] = {
    "liu-wen-hua": lambda t: (
        f"基于 Phase 1+2 输出，生成「{t}」尽调报告。\n"
        "结构: 企业概况/财务分析/行业分析/风险清单/人员背景/数据完整度\n"
        "格式: Markdown，保留所有 [来源: xxx] 标注\n"
        "严禁: 信贷决策词、模糊表述、未标注来源的数据"
    ),
    "yan-hao-kan": lambda t: (
        f"对「{t}」的尽调报告执行格式美化。\n"
        "1. Markdown → 格式化输出\n"
        "2. 风险项加粗/标色\n"
        "3. 保留所有 [来源: xxx] 标注\n"
        "4. 输出: 排版完成的最终报告"
    ),
}

ALL_USER_TEMPLATES = {
    **PHASE1_USER_TEMPLATES, **PHASE2_USER_TEMPLATES, **PHASE3_USER_TEMPLATES,
}

# ── 条件分支规则 ──
CONDITIONAL_BRANCH_RULES = {
    "controller_anomaly": {
        "signal_keywords": ["实控人不一致", "代持", "影子控制", "实际控制人不明",
                           "法人与实控人不一致", "隐名股东"],
        "append_role": "ma-li-quan",
        "desc": "实控人异常 → 追加马力全深度背调",
    },
    "large_deposit_loan": {
        "signal_keywords": ["大存大贷", "存贷双高", "存贷双高现象", "高存高贷",
                           "货币资金占比过高", "有息负债同时高企"],
        "append_role": "zhao-gang",
        "desc": "大存大贷 → 追加赵刚深度风险扫描",
    },
    "many_related": {
        "signal_keywords": ["关联企业超过10家", "关联方众多", "大量关联",
                           "疑似壳公司", "关联交易频繁"],
        "append_role": "zhao-gang",
        "desc": "大量关联企业 → 追加赵刚担保圈分析",
    },
    "cashflow_quality": {
        "signal_keywords": ["经营现金流/净利润低于50%", "现金流质量差",
                           "经营现金流为负", "现金流覆盖不足"],
        "append_role": "zheng-shen-zhi",
        "desc": "现金流质量差 → 追加郑慎之财务专项检查",
    },
    "dishonest_record": {
        "signal_keywords": ["失信被执行人", "被执行人", "限制高消费",
                           "列入失信名单", "失信记录"],
        "append_role": "zhang-tie-zhu",
        "desc": "失信记录 → 追加张铁柱重新核实工商状态",
    },
    "registration_mismatch": {
        "signal_keywords": ["注册资金与经营不匹配", "注册资本异常", "注册资本变更异常"],
        "append_role": "zheng-shen-zhi",
        "desc": "注册异常 → 追加郑慎之工商数据专项验证",
    },
}


# ══════════════════════════════════════════════════════════
#  编排器核心
# ══════════════════════════════════════════════════════════

class Orchestrator:
    """v3.2.0 真并发 Agent 编排器"""

    def __init__(self, target: str, model: str | None = None,
                 mode: str = "standard", concurrency: int = 5,
                 max_retries: int = 3, roles: list[str] | None = None):
        self.target = target
        self.model = model or config.DEFAULT_MODEL
        self.mode = mode
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.roles = roles

        self.registry = AgentRegistry()
        self.template = config.MODE_TEMPLATES.get(mode, config.MODE_TEMPLATES["standard"])
        self.branches_triggered: list[dict] = []
        self._session_start = time.monotonic()
        self._all_metrics: list[dict] = []
        self._commissar_stats: dict[str, dict] = {}

    # ── API 调用 ──
    def _build_system_message(self, agent: DueDiligenceAgent, system_prompt: str) -> str:
        """组装 system message: NFR → 子Skill → SKILL.md"""
        parts = [NO_FABRICATION_RULE]
        if agent.sub_skill:
            parts.append(f"---\n\n# 当前角色: {agent.name}({agent.nickname})\n\n{agent.sub_skill}")
        parts.append(f"---\n\n# 全局上下文\n\n{system_prompt}")
        return "\n\n".join(parts)

    def _make_agent_config(self, agent: DueDiligenceAgent) -> dict:
        """为 Agent 构建 API 调用配置"""
        template_fn = ALL_USER_TEMPLATES.get(agent.agent_id)
        if template_fn:
            user_prompt = template_fn(self.target)
        else:
            user_prompt = f"对「{self.target}」执行尽调分析。按铁律 0 要求输出。"

        if agent.memory.key_findings:
            findings = "\n".join(f"- {f}" for f in agent.memory.key_findings[-5:])
            user_prompt = f"{user_prompt}\n\n# 此前发现\n{findings}"

        if NO_FABRICATION_TAGLINE not in user_prompt:
            user_prompt = f"{user_prompt}\n\n{NO_FABRICATION_TAGLINE}"

        return {
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "user_prompt": user_prompt,
            "inner_monologue": agent.inner_monologue(self.target),
        }

    async def _api_call(self, session: aiohttp.ClientSession,
                        sem: asyncio.Semaphore,
                        agent: DueDiligenceAgent,
                        config_dict: dict,
                        system_prompt: str) -> dict:
        """单次 LLM API 调用"""
        if not config.API_KEY:
            raise RuntimeError("API_KEY not configured. Set DEEPSEEK_API_KEY or OPENAI_API_KEY.")

        t0 = time.monotonic()
        full_system = self._build_system_message(agent, system_prompt)
        user_text = config_dict["user_prompt"]

        headers = {
            "Authorization": f"Bearer {config.API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_text},
            ],
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        url = f"{config.API_BASE.rstrip('/')}/chat/completions"

        try:
            async with sem:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=config.API_TIMEOUT_SECONDS),
                ) as resp:
                    elapsed = (time.monotonic() - t0) * 1000
                    if resp.status != 200:
                        await resp.text()  # consume body
                        return {
                            "ok": False, "text": "", "ms": int(elapsed), "tok": 0,
                            "usage": {}, "err": f"HTTP {resp.status}",
                        }
                    data = await resp.json()
                    choice = data.get("choices", [{}])[0]
                    text = choice.get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    return {
                        "ok": True, "text": text, "ms": int(elapsed),
                        "tok": usage.get("total_tokens", 0), "usage": usage, "err": "",
                    }
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - t0) * 1000
            return {"ok": False, "text": "", "ms": int(elapsed), "tok": 0,
                    "usage": {}, "err": "timeout"}
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return {"ok": False, "text": "", "ms": int(elapsed), "tok": 0,
                    "usage": {}, "err": f"{type(e).__name__}: {e}"}

    # ── 政委门禁 ──
    def _commissar_check(self, agent: DueDiligenceAgent, text: str,
                         attempt: int) -> tuple[bool, list[Violation]]:
        """政委 L1 + L2 质量扫描"""
        violations = QualityRules.scan(text, agent.name)
        if not violations:
            # L1 通过 → L2
            validation = QualityRules.validate_dd_output(text, agent.name)
            if validation["valid"]:
                self._commissar_stats[agent.agent_id] = {
                    "name": agent.name, "pass": True,
                    "attempts": attempt + 1, "degraded": False,
                }
                return True, []
            elif validation["stats"]["fabrication_indicators"] > 0:
                violations = [Violation(
                    rule="fabrication_risk", field="full_text",
                    detail=f"L2 校验发现 {validation['stats']['fabrication_indicators']} 个编造信号",
                    severity="ERROR",
                )]
            else:
                # L2 不通过但 fabrication_indicators==0（来源覆盖率低/模糊词过多等）
                # 生成通用违规项避免空列表导致无意义重试
                issues_summary = "; ".join(validation.get("issues", [])[:3]) or "L2 校验不通过"
                violations = [Violation(
                    rule="quality_issue", field="full_text",
                    detail=f"L2 校验不通过 (得分 {validation['score']:.0f}): {issues_summary}",
                    severity="WARN",
                )]
        return False, violations

    def _generate_pua_feedback(self, agent: DueDiligenceAgent,
                                violations: list[Violation],
                                attempt: int) -> str:
        """生成政委 PUA 话术"""
        level = min(attempt, 3)
        tpls = {
            1: (
                f"{agent.name}！你的输出有 {len(violations)} 处违规。\n"
                "铁律第4条：数据来源必标注。铁律第1条：禁止信贷决策词。\n"
                "具体问题：{issues}\n给我修正后重新输出。"
            ),
            2: (
                f"第二次了{agent.name}。人家王思远一遍过，你卡了两次。\n"
                "其他人进度都卡在你这里。问题：{issues}\n最后一次机会，修正！"
            ),
            3: (
                f"{agent.name}，三次了。你就是不认真。\n"
                "你的部分降级处理，报告中标注数据缺失。下次注意。"
            ),
        }
        issues_str = "\n".join(f"  - [{v.rule}] {v.detail}" for v in violations)
        return f"\n\n[政委退回第{attempt}次]\n{tpls[level].format(issues=issues_str)}\n"

    # ── 主编排 ──
    async def orchestrate(self, output_dir: str | None = None) -> dict:
        """执行完整 3-Phase 尽调流程"""
        if not config.API_KEY:
            raise RuntimeError("API_KEY not configured.")

        system_prompt = load_system_prompt()

        # 确定要激活的角色
        all_roles = self.roles if self.roles else (
            self.template.get("phase1", []) +
            self.template.get("phase2", []) +
            self.template.get("phase3", [])
        )

        # ── 启动 Agent 注册中心 ──
        self.registry.boot(all_roles)
        self.registry.wake_agents(all_roles, self.target)

        p1_roles = self.roles if self.roles else self.template.get("phase1", [])
        p2_roles = list(self.template.get("phase2", []))
        p3_roles = self.template.get("phase3", [])

        # ── 团队开工──
        print(f"\n{'='*60}")
        print(f"  华尔街驻铁岭办事处 · v3.2.0")
        print(f"  目标: {self.target}  |  模式: {self.mode}")
        print(f"  激活: {', '.join(all_roles)}")
        print(f"{'='*60}\n")
        print(self.registry.team_chat_snapshot())

        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(self.concurrency)

            # ── Phase 1: 调查（真并发调用）──
            p1_results = []
            if p1_roles:
                print(f"\n{'─'*40}")
                print(f"  Phase 1 · 尽调调查")
                p1_agents = self.registry.get_many(p1_roles)
                p1_results = await self._run_phase(session, sem, p1_agents,
                                                    system_prompt, phase=1)
                ok_count = sum(1 for r in p1_results if r.get("ok") and not r.get("degraded"))
                print(f"  Phase 1 完成: {ok_count}/{len(p1_agents)} 有效输出")

            # ── 信号检测 → 条件分支追加 ──
            signals = self._extract_signals(p1_results) if p1_results else []
            if signals and self.template.get("conditional_branches", False):
                for sig in signals:
                    append_rid = sig["append_role"]
                    if append_rid not in p2_roles:
                        p2_roles.append(append_rid)
                        self.branches_triggered.append(sig)
                        # 唤醒追加角色
                        self.registry.boot([append_rid])
                        self.registry.wake_agents([append_rid], self.target)
                        new_agent = self.registry.get(append_rid)
                        if new_agent:
                            print(f"  🔀 条件分支: {sig['desc']} — {new_agent.name}加入")
                            self.registry.add_team_chat(
                                f"[{new_agent.name}] 临时被叫来加班……{sig['desc']}"
                            )

            # ── Phase 2: 验证 + 质检 ──
            p2_results = []
            if p2_roles:
                print(f"\n{'─'*40}")
                print(f"  Phase 2 · 验证与质检")
                # 构建上下文
                p1_context = self._build_context(p1_results, max_chars=2000)
                p2_agents = self.registry.get_many(p2_roles)
                # 注入 Phase 1 上下文
                for agent in p2_agents:
                    if p1_context:
                        agent.memory.key_findings.append(f"[Phase 1 汇总] {p1_context[:200]}")
                p2_results = await self._run_phase(session, sem, p2_agents,
                                                    system_prompt, phase=2)
                ok2 = sum(1 for r in p2_results if r.get("ok") and not r.get("degraded"))
                print(f"  Phase 2 完成: {ok2}/{len(p2_agents)} 有效输出")

            # 一致性检查
            consistency = self._check_consistency(p1_results, p2_results)
            if consistency:
                print(f"  一致性检查: {len(consistency)} 项冲突")
                for c in consistency[:3]:
                    print(f"    ⚠ {c[:100]}")

            # ── Agent 间闲聊（Phase 1 结束后互相吐槽）──
            self._generate_team_banter(p1_results, p2_results)

            # ── Phase 3: 报告 ──
            p3_results = []
            if p3_roles:
                print(f"\n{'─'*40}")
                print(f"  Phase 3 · 报告生成")
                p1_long = self._build_context(p1_results, max_chars=3000)
                p2_context = self._build_context(p2_results, max_chars=2000)
                p3_agents = self.registry.get_many(p3_roles)
                for agent in p3_agents:
                    ctx = f"{p1_long}\n\n{p2_context}"
                    agent.memory.key_findings.append(f"[前置 Phase 汇总]\n{ctx[:500]}")
                p3_results = await self._run_phase(session, sem, p3_agents,
                                                    system_prompt, phase=3)

        # ── 汇总 ──
        report_text = self._assemble_report(p3_results, p1_results, p2_results)
        total_time = time.monotonic() - self._session_start

        print(f"\n{'='*60}")
        print(f"  尽调完成 | 总耗时: {total_time:.1f}s")
        print(f"{'='*60}")
        print(self.registry.status_report())

        # ── 保存文件 ──
        out_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        sl = slug(self.target)

        report_path = out_dir / f"report-{sl}-{ts}.md"
        report_path.write_text(report_text, encoding="utf-8")
        print(f"报告已保存: {report_path}")

        return {
            "report": report_text,
            "report_path": str(report_path),
            "output_dir": str(out_dir),
            "mode": self.mode,
            "roles_activated": all_roles,
            "branches_triggered": self.branches_triggered,
            "agent_status": {a.agent_id: a.snapshot() for a in self.registry.get_all()},
            "team_chat": self.registry.team_chat_snapshot(20),
        }

    # ── Phase 执行器 ──
    async def _run_phase(self, session: aiohttp.ClientSession,
                         sem: asyncio.Semaphore,
                         agents: list[DueDiligenceAgent],
                         system_prompt: str,
                         phase: int) -> list[dict]:
        """执行一个 Phase 的所有 Agent（真并发）"""
        results: list[dict] = []

        async def _run_one(agent: DueDiligenceAgent) -> dict:
            agent.state = AgentState.WORKING
            config_dict = self._make_agent_config(agent)

            # 打印内部独白
            mono = agent.inner_monologue(f"Phase {phase}")
            print(f"  [{agent.nickname}] {mono}")

            for attempt in range(self.max_retries + 1):
                try:
                    result = await self._api_call(session, sem, agent, config_dict, system_prompt)
                except Exception as e:
                    result = {"ok": False, "text": "", "ms": 0, "tok": 0, "err": str(e)}

                # 暗哨指标
                self._all_metrics.append({
                    "agent": agent.agent_id, "name": agent.name,
                    "phase": phase, "ok": result.get("ok"),
                    "ms": result.get("ms", 0), "tok": result.get("tok", 0),
                    "retry": attempt,
                })

                if not result.get("ok"):
                    agent.emotion.update(success=False)
                    if attempt < 1:
                        continue
                    result["rid"] = agent.agent_id
                    result["name"] = agent.name
                    result["degraded"] = True
                    agent.state = AgentState.DEGRADED
                    return result

                # 政委扫描
                text = result.get("text", "")
                passed, violations = self._commissar_check(agent, text, attempt)

                if passed:
                    agent.emotion.update(success=True, discovery=len(text) > 800)
                    agent.memory.key_findings.append(f"[Phase {phase}] {text[:200]}")
                    result["rid"] = agent.agent_id
                    result["name"] = agent.name
                    result["quality_flags"] = []
                    agent.state = AgentState.DONE
                    return result

                # 不通过
                agent.emotion.update(success=False, retry=True)
                if attempt < self.max_retries:
                    feedback = self._generate_pua_feedback(agent, violations, attempt + 1)
                    config_dict["user_prompt"] += feedback
                else:
                    agent.state = AgentState.DEGRADED
                    result["rid"] = agent.agent_id
                    result["name"] = agent.name
                    result["degraded"] = True
                    result["quality_flags"] = [v.rule for v in violations]
                    self._commissar_stats[agent.agent_id] = {
                        "name": agent.name, "pass": False,
                        "attempts": attempt + 1, "degraded": True,
                    }
                    return result

            result["rid"] = agent.agent_id
            result["name"] = agent.name
            result["degraded"] = True
            agent.state = AgentState.DEGRADED
            return result

        tasks = [_run_one(a) for a in agents]
        results = await asyncio.gather(*tasks)
        return list(results)

    # ── 信号检测 ──
    def _extract_signals(self, results: list[dict]) -> list[dict]:
        all_text = " ".join(
            r.get("text", "") for r in results
            if isinstance(r, dict) and r.get("ok") and r.get("text")
        )
        triggered: list[dict] = []
        for signal_id, rule in CONDITIONAL_BRANCH_RULES.items():
            for kw in rule["signal_keywords"]:
                if kw in all_text:
                    triggered.append({
                        "signal": signal_id, "append_role": rule["append_role"],
                        "desc": rule["desc"], "matched_keyword": kw,
                    })
                    break
        priority_order = [
            "controller_anomaly", "large_deposit_loan", "dishonest_record",
            "cashflow_quality", "many_related", "registration_mismatch",
        ]
        triggered.sort(key=lambda s: (
            priority_order.index(s["signal"]) if s["signal"] in priority_order else 99
        ))
        return triggered[:2]

    # ── 上下文构建 ──
    def _build_context(self, results: list[dict], max_chars: int = 2000) -> str:
        parts = []
        for r in results:
            if not isinstance(r, dict) or not r.get("ok"):
                continue
            name = r.get("name", r.get("rid", "?"))
            text = r.get("text", "")[:max_chars]
            parts.append(f"### {name}\n{text}")
        return "\n\n".join(parts)

    # ── 一致性检查 ──
    def _check_consistency(self, p1: list[dict], p2: list[dict]) -> list[str]:
        issues = []
        for r in p2:
            if isinstance(r, dict) and r.get("rid") == "zheng-shen-zhi":
                vtext = r.get("text", "")
                conflicts = re.findall(r'\[冲突[:：][^\]]+\]', vtext)
                for c in conflicts:
                    issues.append(f"郑慎之验证: {c}")
        return issues

    # ── 团队互动生成 ──
    def _generate_team_banter(self, p1: list[dict], p2: list[dict]):
        """生成 Agent 间自然互动——吐槽/赞同/疑问"""
        agents = self.registry.get_all()
        for i, a1 in enumerate(agents):
            if a1.state == AgentState.DEGRADED:
                remark = a1.casual_remark("被政委退了三次，心情")
                print(f"  💬 {remark}")
                self.registry.add_team_chat(remark)
            elif a1.state == AgentState.DONE and a1.emotion.mood == Mood.EXCITED:
                remark = a1.casual_remark("刚完成的分析")
                print(f"  💬 {remark}")
                self.registry.add_team_chat(remark)

    # ── 报告组装 ──
    def _assemble_report(self, p3: list[dict], p1: list[dict],
                         p2: list[dict]) -> str:
        report_text = ""
        # 按报告优先级选择：刘文华（内容）> 颜好看（排版）
        report_priority = ["liu-wen-hua", "yan-hao-kan"]
        for rid in report_priority:
            for r in p3:
                if r.get("ok") and r.get("text") and r.get("rid") == rid:
                    report_text = r["text"]
                    break
            if report_text:
                break
        if not report_text:
            # 回退到任意有效 p3 输出
            for r in p3:
                if r.get("ok") and r.get("text"):
                    report_text = r["text"]
                    break
        if not report_text:
            report_text = self._fallback_report(p1, p2)

        # 附加团队互动摘要
        chat = self.registry.team_chat_snapshot(10)
        if chat:
            report_text += f"\n\n---\n\n## 📝 团队协作记录\n\n```\n{chat}\n```\n"

        report_text += "\n\n---\n\n*本报告由华尔街驻铁岭办事处 AI 协作生成，仅供参考。*"
        return report_text

    def _fallback_report(self, p1: list[dict], p2: list[dict]) -> str:
        parts = [f"# 尽调报告: {self.target}\n\n> ⚠ 自动组装后备报告\n"]
        parts.append("## 调查结果\n")
        for r in p1:
            label = r.get("name", r.get("rid", "?"))
            status = "✅" if r.get("ok") and not r.get("degraded") else ("⚠降级" if r.get("degraded") else "❌失败")
            text = r.get("text", "").strip()[:1000]
            parts.append(f"### {label} {status}\n{text}\n")
        parts.append("## 验证结果\n")
        for r in p2:
            label = r.get("name", r.get("rid", "?"))
            status = "✅" if r.get("ok") and not r.get("degraded") else ("⚠降级" if r.get("degraded") else "❌失败")
            text = r.get("text", "").strip()[:1000]
            parts.append(f"### {label} {status}\n{text}\n")
        return "\n".join(parts)


# ══════════════════════════════════════════════════════════
#  便捷入口
# ══════════════════════════════════════════════════════════

async def run_due_diligence(target: str, model: str | None = None,
                            mode: str = "standard", concurrency: int = 5,
                            max_retries: int = 3, roles: list[str] | None = None,
                            output_dir: str | None = None) -> dict:
    """便捷函数：直接运行尽调"""
    orch = Orchestrator(
        target=target, model=model, mode=mode,
        concurrency=concurrency, max_retries=max_retries,
        roles=roles,
    )
    return await orch.orchestrate(output_dir=output_dir)
