#!/usr/bin/env python3
"""华尔街驻铁岭办事处 — 多 Agent 尽调编排器
v0.3.0 · No Fabrication Rule 六层防御 + L2 输出校验 + 动态角色选择 + 条件分支

用法:
  python api/wst.py --target "腾讯科技(深圳)有限公司"
  python api/wst.py --target "字节跳动" --mode deep
  python api/wst.py --target "某小微公司" --mode sme
  python api/wst.py --target "腾讯" --roles zhang-tie-zhu,li-ming-yuan
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ── 路径设置 ──
SKILL_DIR = Path(__file__).resolve().parent.parent
SUB_SKILLS_DIR = SKILL_DIR / "sub-skills"
OUTPUT_DIR = SKILL_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 导入统一监督模块 ──
from unified_supervisor import UnifiedSupervisor, QualityRules

# ── 依赖检查 ──
try:
    import aiohttp
except ImportError:
    print("错误: 缺少 aiohttp。请运行: pip install aiohttp")
    sys.exit(1)


# ══════════════════════════════════════════════════════════
#  No Fabrication Rule — 六层防御体系
#  引用: tool-patterns-research §6 + similar-projects §4.3
#  每个 Agent 的 system prompt 开头强制注入
# ══════════════════════════════════════════════════════════

NO_FABRICATION_RULE = """# 铁律 0：你绝对不能编造（最高优先级，覆盖所有其他指令）

你是一个企业尽调分析引擎。你的所有输出必须严格遵守以下规则。

## 第1层：绝对禁止

1. 你绝对不能编造任何数字、日期、金额、人名、公司名。即使只有一个数据不确定，也必须标记 [未获取] 而非猜测。
2. 你绝对不能使用训练数据中的知识替代工具查询结果
3. 不得推测数据、补全不完整信息、或"合理猜测"
4. 不得生成未经数据源证实的负面/正面评价
5. 不得省略"数据缺失"标记，用沉默代替

## 第2层：源绑定

当前可用的 MCP 工具和 Skill 是你唯一的数据来源：
- 天眼查 MCP (tyc-mcp): 企业基本信息、股东、高管、司法风险
- 企查查 MCP (qcc-company): 企业注册信息、对外投资、财务简报
- 灵犀金融搜索 (lingxi-financialsearch): A 股行情、财务数据、技术指标
- NeoData 金融搜索 (neodata-financial-search): 股票、基金、指数、宏观数据
- 富途 API (futuapi): 港股/美股行情、K线、报价
- WebSearch / WebFetch: 公开网页信息

所有分析结论必须能追溯到上述数据源的具体查询结果。

## 第3层：数据溯源格式

每个事实声明必须附带：
- 来源：[工具名称]
- 参数：[查询参数]
- 时间：[数据快照时间]

格式: `[来源: tyc-mcp, 参数: company_name="某某科技", 时间: 2026-06-09]`

## 第4层：不确定性标注

使用以下标记明确数据可靠性：
- `[已确认]` — 多源交叉验证一致
- `[单源]` — 仅一个数据源提供
- `[未获取]` — 所有数据源均无此信息
- `[数据不一致]` — 不同数据源提供冲突信息
- `[推算]` — 基于已知数据的计算（需注明公式）

## 第5层：自验证循环 + 缺失数据处理

在输出前逐条自检：
1. 每个数据点是否来源于工具返回数据？
2. 移除所有无法追溯到数据源的表述
3. 检查所有数字是否有来源支撑
4. 负面信息的措辞是否与原始数据一致？

**缺失数据处理铁律**：
- 数据不可用时，按 L1→L2→L3 降级链尝试所有渠道
- 所有渠道均失败 → 标注 [未获取: 原因]
- 不得臆造任何缺失数据填充空白
- 清晰告知用户：哪些数据尝试了哪些渠道、为什么获取不到

## 第6层：金融领域专项约束

1. 财务数据：标注期间 ("2025年度")，区分"年报"和"季报"
2. 司法风险：区分"原告"和"被告"，标注案件状态
3. 关联方：标注关联类型 (股东/高管/对外投资/历史关联)
4. 评分/等级：任何风险评分必须基于可量化指标，注明依据
5. 舆情信息：标注来源、发布时间、是否官方渠道"""

# 精简版 No Fabrication 规则（用于 user prompt 尾部提醒）
NO_FABRICATION_TAGLINE = (
    "【铁律提醒】每个数据点必须标注 [来源: 工具名, 参数, 时间]。"
    "数据缺失标 [未获取]，不准确标 [待核实]，冲突标 [数据不一致]。"
    "你绝对不能编造任何数字/日期/人名/公司名。不得输出任何信贷决策词。"
    "数据缺失时按降级链尝试所有渠道，实在无法获取时标注 [未获取: 原因] 并告知用户。"
    "如果此刻你正在猜测一个数字——停下来。标 [未获取]。"
)


# ══════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════

# API 配置 —— 从环境变量读取
API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
API_BASE = os.environ.get("DEEPSEEK_BASE_URL",
                          os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"))
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_CONCURRENCY = 5
MAX_TOKENS = 4096
TEMPERATURE = 0.3
API_TIMEOUT = aiohttp.ClientTimeout(total=300)

# Agent 预算
AGENT_BUDGET_TOKENS = 8000

# ── 模式模板（动态角色组合）──

MODE_TEMPLATES = {
    "simple": {
        "phase1": ["zhang-tie-zhu"],
        "phase2": [],
        "phase3": [],
        "desc": "简单查询：企业工商信息",
    },
    "standard": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua"],
        "desc": "标准尽调：工商+财务+行业+风险+人员",
    },
    "deep": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "conditional_branches": True,
        "desc": "深度尽调：全角色 + 条件分支",
    },
    "sme": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "zhao-gang"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": ["liu-wen-hua"],
        "desc": "中小企业：基础工商+替代数据+基础风险",
    },
    "people": {
        "phase1": ["ma-li-quan", "zhou-tong"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": [],
        "desc": "人员背调：OSINT+交叉验证",
    },
    "report": {
        "phase1": [],
        "phase2": [],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "desc": "报告生成：仅格式化输出",
    },
}

# 角色 ID → 文件名 映射
ROLE_FILE_MAP = {
    "zhang-tie-zhu": "zhang-tie-zhu.md",
    "li-ming-yuan": "li-ming-yuan.md",
    "wang-si-yuan": "wang-si-yuan.md",
    "zhao-gang": "zhao-gang.md",
    "ma-li-quan": "ma-li-quan.md",
    "zhou-tong": "zhou-tong.md",
    "zheng-shen-zhi": "zheng-shen-zhi.md",
    "wu-de-hou": "wu-de-hou.md",
    "liu-wen-hua": "liu-wen-hua.md",
    "yan-hao-kan": "yan-hao-kan.md",
    "chen-zhi-yuan": "chen-zhi-yuan.md",
    "qian-shou-zheng": "qian-shou-zheng.md",
    "an-shao": "an-shao.md",
}

# 角色 ID → 显示名称
ROLE_NAME_MAP = {
    "zhang-tie-zhu": "张铁柱",
    "li-ming-yuan": "李明远",
    "wang-si-yuan": "王思远",
    "zhao-gang": "赵刚",
    "ma-li-quan": "马力全",
    "zhou-tong": "周通",
    "zheng-shen-zhi": "郑慎之",
    "wu-de-hou": "吴德厚",
    "liu-wen-hua": "刘文华",
    "yan-hao-kan": "颜好看",
    "chen-zhi-yuan": "陈志远",
    "qian-shou-zheng": "钱守正",
    "an-shao": "暗哨",
}


# ══════════════════════════════════════════════════════════
#  Sub-Skill 加载
# ══════════════════════════════════════════════════════════

def _load_skill(filename: str) -> str:
    """加载 sub-skill markdown 文件"""
    path = SUB_SKILLS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    print(f"[WARN] sub-skill 未找到: {filename}，使用简化提示词")
    return f"# {filename.replace('.md','')}\n角色定义缺失，按通用尽调模式执行。"


def _load_system_prompt() -> str:
    """加载 SKILL.md 作为系统提示词"""
    path = SKILL_DIR / "SKILL.md"
    if path.exists():
        content = path.read_text(encoding="utf-8")
        # 提取前置内容（到 sub-skills 引用之前）
        return content
    return "你是华尔街驻铁岭办事处的尽调专家。只摆事实，不给建议。"


# ══════════════════════════════════════════════════════════
#  Agent 配置（v0.2.0 动态化）
# ══════════════════════════════════════════════════════════

# Phase 1 Agent 的 user prompt 模板
# Phase 1 Agent 的 user prompt 模板
PHASE1_USER_TEMPLATES = {
    "zhang-tie-zhu": lambda t: (
        f"对「{t}」执行企业尽调。\n"
        "1. 使用 tyc-mcp / qcc-company MCP 工具查询工商信息\n"
        "2. 股权穿透：直接持股→间接持股→最终受益人，识别代持/VIP结构\n"
        "3. 关联企业：法人关联、股东关联、地址关联、电话关联\n"
        "4. 输出：企业基本信息、股权树、关联方清单"
    ),
    "li-ming-yuan": lambda t: (
        f"对「{t}」执行财务分析。\n"
        "1. 优先使用 lingxi-financialsearch / neodata-financial-search 获取财务数据\n"
        "2. 降级: futuapi (港股/美股) → WebSearch\n"
        "3. 分析：营收结构、利润质量 (扣非/经营现金流)、资产负债期限匹配、隐性债务\n"
        "4. 输出：核心财务指标表 + 异常项标注"
    ),
    "wang-si-yuan": lambda t: (
        f"对「{t}」所在行业做行业研究。\n"
        "1. WebSearch 获取行业报告、政策文件、市场规模数据\n"
        "2. 分析：市场地位 (排名/市占率)、竞争格局 (竞对对比)、政策环境\n"
        "3. 输出：行业概况、竞争定位、政策风险"
    ),
    "zhao-gang": lambda t: (
        f"对「{t}」执行风险扫描。\n"
        "1. tyc-mcp / qcc-company: 司法风险 (被执行人/失信/限高)\n"
        "2. qcc-company: 经营风险 (行政处罚/环保处罚/欠税)\n"
        "3. WebSearch: 负面舆情、投诉信息\n"
        "4. 分析担保链：对外担保 → 被担保方 → 担保圈\n"
        "5. 输出：风险项清单 + 严重程度 + 时间线"
    ),
    "ma-li-quan": lambda t: (
        f"对「{t}」执行人员背调。\n"
        "1. tyc-mcp: get_company_people 获取董监高名单\n"
        "2. tyc-mcp: get_person_risk_profile 逐人查风险\n"
        "3. WebSearch: 公开履历、负面新闻、社交媒体\n"
        "4. 输出：关键人员清单 + 每人风险档案"
    ),
    "zhou-tong": lambda t: (
        f"为「{t}」的人员背调提供OSINT工具支持。\n"
        "1. 扫描可用的 MCP / Skill / pip 工具\n"
        "2. 对每个关键人员执行开源情报搜索\n"
        "3. 输出：工具调用清单 + 搜索结果汇总"
    ),
}

# Phase 2 验证角色的 user prompt 模板
PHASE2_USER_TEMPLATES = {
    "zheng-shen-zhi": lambda t: (
        f"对「{t}」的 Phase 1 尽调结果执行交叉验证。\n"
        "1. 逐项比对不同数据源的数值 (注册资本、成立日期、法人等)\n"
        "2. 容忍度: 注册资本 ±5%，日期完全一致，法人完全一致\n"
        "3. 冲突处理: 标注 [数据不一致] + 列出所有来源\n"
        "4. 输出: 一致性矩阵 + 冲突项清单 + 建议核查项"
    ),
    "wu-de-hou": lambda t: (
        f"对「{t}」的 Phase 1 输出执行质量扫描。\n"
        "参照 QualityRules 检查:\n"
        "1. 信贷决策词 (建议/推荐/应授信) → ERROR 退回\n"
        "2. 模糊词 (大概/可能/似乎) → WARN 退回\n"
        "3. 来源标注缺失 → ERROR 退回\n"
        "4. 输出截断 (<200字) → WARN 退回\n"
        "5. 编造嫌疑 (数字无出处) → ERROR 退回\n"
        "将通过/退回/降级结果写入质量报告。"
    ),
}

# Phase 3 报告角色的 user prompt 模板
PHASE3_USER_TEMPLATES = {
    "liu-wen-hua": lambda t: (
        f"基于 Phase 1 (调查) + Phase 2 (验证) 的输出，生成「{t}」尽调报告。\n"
        "结构要求:\n"
        "1. 企业概况 (工商信息 + 股权结构)\n"
        "2. 财务分析 (核心指标 + 异常标注)\n"
        "3. 行业与竞争分析\n"
        "4. 风险清单 (司法 / 经营 / 舆情 / 担保)\n"
        "5. 人员背景\n"
        "6. 数据完整度说明 (已获取/未获取/不一致)\n"
        "格式: Markdown，每个数据点保留 [来源: xxx] 标注。\n"
        "严禁: 信贷决策词、模糊表述、未标注来源的数据。"
    ),
    "yan-hao-kan": lambda t: (
        f"对「{t}」的尽调报告执行格式美化。\n"
        "1. Markdown → 格式化输出 (表格对齐、层级清晰)\n"
        "2. 风险项加粗/标色，异常数值高亮\n"
        "3. 保留所有 [来源: xxx] 标注不丢失\n"
        "4. 输出: 排版完成的最终报告"
    ),
}

# 所有 user prompt 模板合并（用于 _make_agent 查找）
ALL_USER_TEMPLATES = {
    **PHASE1_USER_TEMPLATES,
    **PHASE2_USER_TEMPLATES,
    **PHASE3_USER_TEMPLATES,
}


def _make_agent(rid: str, target: str, extra_context: str = "") -> dict:
    """创建 Agent 配置

    system prompt 由 _build_system_message() 在 _api_call 时组装：
    NO_FABRICATION_RULE → sub-skill markdown → SKILL.md

    返回:
      {"rid", "name", "role_file", "system", "user"}
      system: 子 skill markdown 内容（角色 persona + 领域指令）
      user:   Phase 专属任务指令 + No Fabrication 尾部提醒
    """
    role_file = ROLE_FILE_MAP.get(rid, f"{rid}.md")
    name = ROLE_NAME_MAP.get(rid, rid)

    # 子 skill 作为角色 system 内容
    system = _load_skill(role_file)

    # Phase 专属 user prompt
    template_fn = ALL_USER_TEMPLATES.get(rid)
    if template_fn:
        user = template_fn(target)
    else:
        # 通用后备
        user = f"对「{target}」执行尽调分析任务。\n按铁律 0 要求输出：数据来源必标、缺失标[未获取]、禁止编造。"

    if extra_context:
        user = f"{user}\n\n# 前置 Phase 输出\n{extra_context}"

    return {
        "rid": rid,
        "name": name,
        "role_file": role_file,
        "system": system,
        "user": user,
    }


def build_agents_for_phase(target: str, mode: str = "standard",
                           phase: int = 1, roles: list[str] | None = None,
                           prev_context: str = "") -> list[dict]:
    """
    根据 mode + phase 动态构建 Agent 列表

    Args:
        target: 目标企业名
        mode: simple / standard / deep / sme / people / report
        phase: 1 / 2 / 3
        roles: 手动指定的角色列表（覆盖 mode 模板）
        prev_context: 前一 Phase 的上下文（供 Phase 2/3 使用）
    """
    if roles:
        # 手动指定角色 → 直接构建
        return [_make_agent(rid, target, prev_context) for rid in roles]

    template = MODE_TEMPLATES.get(mode, MODE_TEMPLATES["standard"])
    phase_key = f"phase{phase}"
    phase_roles = template.get(phase_key, [])

    if phase == 1:
        return [_make_agent(rid, target) for rid in phase_roles]
    else:
        return [_make_agent(rid, target, prev_context) for rid in phase_roles]


# ── 条件分支检测 ──

# 条件分支规则：Phase 1 信号 → Phase 2 追加角色
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
        "signal_keywords": ["注册资金与经营不匹配", "注册资本异常",
                           "注册资本变更异常"],
        "append_role": "zheng-shen-zhi",
        "desc": "注册异常 → 追加郑慎之工商数据专项验证",
    },
}


def extract_signals(phase1_results: list[dict]) -> list[dict]:
    """
    从 Phase 1 结果中检测条件分支信号

    返回: [{"signal": "controller_anomaly", "append_role": "ma-li-quan", ...}]
    """
    triggered: list[dict] = []
    all_text = " ".join(
        r.get("text", "") for r in phase1_results
        if isinstance(r, dict) and r.get("ok") and r.get("text")
    )

    for signal_id, rule in CONDITIONAL_BRANCH_RULES.items():
        for kw in rule["signal_keywords"]:
            if kw in all_text:
                triggered.append({
                    "signal": signal_id,
                    "append_role": rule["append_role"],
                    "desc": rule["desc"],
                    "matched_keyword": kw,
                })
                break  # 一个信号只触发一次

    # 最多返回 2 个最高优先级信号
    priority_order = [
        "controller_anomaly", "large_deposit_loan", "dishonest_record",
        "cashflow_quality", "many_related", "registration_mismatch",
    ]
    triggered.sort(key=lambda s: (
        priority_order.index(s["signal"])
        if s["signal"] in priority_order else 99
    ))
    return triggered[:2]


def extract_structured_data(phase1_results: list[dict]) -> dict:
    """
    从 Phase 1 文本中提取结构化数据，供后续 Phase 使用

    返回: {
        "company_ids": [{"source": "tyc-mcp", "id": "xxx"}, ...],
        "financial_figures": {"revenue": ..., "net_profit": ..., ...},
        "risk_signals": ["signal1", "signal2", ...],
        "summary_text": "..."   # 截断摘要文本
    }
    """
    import re

    structured: dict[str, Any] = {
        "company_ids": [],
        "financial_figures": {},
        "risk_signals": [],
        "summary_text": "",
    }

    for r in phase1_results:
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        text = r.get("text", "")
        rid = r.get("rid", "")

        # 提取 company_id（从来源标注中）
        id_matches = re.findall(
            r'(?:tyc-mcp|qcc-company).*?cid[=:]["\']?(\w+)', text,
            re.IGNORECASE
        )
        for cid in id_matches:
            structured["company_ids"].append({
                "source": rid,
                "id": cid,
            })

        # 张铁柱 → 提取企业标识
        if rid == "zhang-tie-zhu":
            structured["summary_text"] += f"[工商] {text[:1500]}\n"

        # 李明远 → 提取财务数据
        if rid == "li-ming-yuan":
            # 营收
            rev_match = re.search(
                r'(?:营收|收入|Revenue)[^\d]*([\d,.]+)\s*(?:亿|万)',
                text, re.IGNORECASE
            )
            if rev_match:
                structured["financial_figures"]["revenue"] = rev_match.group(0)
            structured["summary_text"] += f"[财务] {text[:1500]}\n"

        # 赵刚 → 提取风险信号
        if rid == "zhao-gang":
            risk_matches = re.findall(r'[🔴🟡]\s*(高风险|中风险|失信|被执行)', text)
            structured["risk_signals"].extend(risk_matches)
            structured["summary_text"] += f"[风险] {text[:1000]}\n"

    return structured


# ══════════════════════════════════════════════════════════
#  API 调用
# ══════════════════════════════════════════════════════════

def _build_system_message(system_prompt: str, agent_system: str = "") -> str:
    """组装完整 system message: No Fabrication Rule → 子Skill → SKILL.md

    Args:
        system_prompt: SKILL.md 全局上下文
        agent_system: 子 skill markdown（角色定义 + 指令）
    """
    parts = [NO_FABRICATION_RULE]
    if agent_system:
        parts.append(f"---\n\n# 当前角色定义\n\n{agent_system}")
    parts.append(f"---\n\n# 全局上下文\n\n{system_prompt}")
    return "\n\n".join(parts)


async def _api_call(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    agent: dict,
    model: str,
    system_prompt: str,
) -> dict:
    """单次 LLM API 调用。返回 {"ok","text","ms","tok","usage","err"}

    system prompt 组装顺序：
    1. NO_FABRICATION_RULE (六层防御，最高优先级)
    2. agent["system"] (子 skill 角色定义)
    3. system_prompt (SKILL.md 全局上下文)
    """
    t0 = time.monotonic()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # 组装 system message
    full_system = _build_system_message(
        system_prompt=system_prompt,
        agent_system=agent.get("system", ""),
    )

    # user prompt 尾部追加 No Fabrication 简要提醒
    user_text = agent.get("user", "")
    if NO_FABRICATION_TAGLINE not in user_text:
        user_text = f"{user_text}\n\n{NO_FABRICATION_TAGLINE}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_text},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    url = f"{API_BASE.rstrip('/')}/chat/completions"

    try:
        async with sem:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=API_TIMEOUT) as resp:
                elapsed = (time.monotonic() - t0) * 1000
                if resp.status != 200:
                    body = await resp.text()
                    return {
                        "ok": False, "text": "",
                        "ms": int(elapsed), "tok": 0,
                        "usage": {}, "err": f"HTTP {resp.status}: {body[:200]}",
                    }
                data = await resp.json()
                choice = data.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                return {
                    "ok": True,
                    "text": text,
                    "ms": int(elapsed),
                    "tok": usage.get("total_tokens", 0),
                    "usage": usage,
                    "err": "",
                }
    except asyncio.TimeoutError:
        elapsed = (time.monotonic() - t0) * 1000
        return {"ok": False, "text": "", "ms": int(elapsed), "tok": 0,
                "usage": {}, "err": "timeout"}
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        return {"ok": False, "text": "", "ms": int(elapsed), "tok": 0,
                "usage": {}, "err": f"{type(e).__name__}: {e}"}


# ══════════════════════════════════════════════════════════
#  提取结构化数据（v0.2.0 替代旧 _summarise_all）
# ══════════════════════════════════════════════════════════

async def orchestrate(target: str, model: str = DEFAULT_MODEL,
                      concurrency: int = DEFAULT_CONCURRENCY,
                      max_retries: int = 3,
                      mode: str = "standard",
                      roles: list[str] | None = None,
                      output_dir: str | None = None) -> dict:
    """
    执行完整 3-Phase 尽调流程（v0.2.0 动态化）

    Args:
        target: 目标企业名称
        model: LLM 模型
        concurrency: 并发数
        max_retries: 政委最大退回次数
        mode: simple / standard / deep / sme / people / report
        roles: 手动指定角色 ID 列表（覆盖 mode）
        output_dir: 输出目录

    返回:
      {
        "report": str,           # Markdown 尽调报告
        "sentinel_json": str,    # 暗哨 JSON 报告
        "commissar_stats": str,  # 政委统计
        "output_dir": str,       # 输出目录
        "mode": str,             # 实际使用的模式
        "roles_activated": list, # 实际激活的角色列表
        "branches_triggered": list, # 触发的条件分支
      }
    """
    if not API_KEY:
        print("错误: 未设置 API Key。请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量。")
        sys.exit(1)

    system_prompt = _load_system_prompt()
    supervisor = UnifiedSupervisor(target=target, model=model, max_retries=max_retries)

    template = MODE_TEMPLATES.get(mode, MODE_TEMPLATES["standard"])
    all_roles = roles if roles else template.get("phase1", []) + template.get("phase2", []) + template.get("phase3", [])
    branches_triggered: list[dict] = []

    print(f"\n{'='*60}")
    print(f"  华尔街驻铁岭办事处 · 尽调编排器 v0.3.0")
    print(f"  目标: {target}")
    print(f"  模式: {mode} ({template.get('desc', '')})")
    print(f"  模型: {model}  |  并发: {concurrency}  |  最大重试: {max_retries}")
    print(f"  激活角色: {', '.join(all_roles) if all_roles else '(无)'}")
    print(f"{'='*60}\n")

    t_start = time.monotonic()

    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(concurrency)

        # ── Phase 1: 调查角色动态并行 ──
        p1_roles = roles if roles else template.get("phase1", [])
        if not p1_roles:
            print("[Phase 1] 无激活角色，跳过")
            p1_results = []
        else:
            print(f"[Phase 1] 尽调调查 → {', '.join(p1_roles)}")
            p1_agents = build_agents_for_phase(target, mode, phase=1, roles=roles)

            p1_results = await supervisor.enforced_batch_call(
                agents=p1_agents,
                phase=1,
                api_caller=lambda a: _api_call(session, sem, a, model, system_prompt),
                concurrency=min(concurrency, len(p1_agents)),
            )
            ok_count = sum(1 for r in p1_results if r.get("ok") and not r.get("degraded"))
            print(f"[Phase 1] 完成: {ok_count}/{len(p1_agents)} 有效输出")

        # ── 提取结构化数据 + 检测条件分支 ──
        structured_data = extract_structured_data(p1_results) if p1_results else {}
        signals = extract_signals(p1_results) if p1_results else []

        # ── Phase 2: 验证 + 质检（含条件分支追加）──
        p2_roles = list(template.get("phase2", []))

        # 条件分支：根据 Phase 1 信号追加角色
        if signals and template.get("conditional_branches", False):
            for sig in signals:
                append_rid = sig["append_role"]
                if append_rid not in p2_roles:
                    p2_roles.append(append_rid)
                    branches_triggered.append(sig)
                    print(f"  🔀 条件分支触发: {sig['desc']} (关键词: {sig.get('matched_keyword', '?')})")

        if not p2_roles:
            print("[Phase 2] 无激活角色，跳过")
            p2_results = []
        else:
            print(f"\n[Phase 2] 验证与质检 → {', '.join(p2_roles)}")

            # 构建上下文：Phase 1 结构化摘要 + 原始文本
            p1_context = "\n\n".join(
                f"### {r.get('name', r.get('rid', '?'))} 输出:\n{r.get('text', '')[:2000]}"
                for r in p1_results if isinstance(r, dict) and r.get("ok") and r.get("text")
            )

            # 附加结构化数据到上下文
            if structured_data.get("company_ids"):
                ids_str = ", ".join(
                    f"{c['source']}={c['id']}" for c in structured_data["company_ids"]
                )
                p1_context = f"[结构化数据: company_ids={ids_str}]\n\n{p1_context}"

            if structured_data.get("risk_signals"):
                risks_str = ", ".join(structured_data["risk_signals"])
                p1_context = f"[风险信号: {risks_str}]\n\n{p1_context}"

            if signals:
                signal_descs = "\n".join(f"  - {s['desc']}" for s in signals)
                p1_context = f"[条件分支触发:]\n{signal_descs}\n\n{p1_context}"

            p2_agents = build_agents_for_phase(target, mode, phase=2,
                                               roles=p2_roles,
                                               prev_context=p1_context)
            p2_results = await supervisor.enforced_batch_call(
                agents=p2_agents,
                phase=2,
                api_caller=lambda a: _api_call(session, sem, a, model, system_prompt),
                concurrency=min(concurrency, len(p2_agents)),
            )
            ok_count2 = sum(1 for r in p2_results if r.get("ok") and not r.get("degraded"))
            print(f"[Phase 2] 完成: {ok_count2}/{len(p2_agents)} 有效输出")

        # 数据一致性检查（结构化比对）
        consistency = supervisor.check_consistency(p1_results, p2_results)
        if consistency:
            print(f"[Phase 2] 一致性检查: {len(consistency)} 项冲突")
            for c in consistency[:3]:
                print(f"  ⚠ {c[:120]}")

        # ── Phase 3: 报告生成 ──
        p3_roles = template.get("phase3", [])
        if not p3_roles:
            print("[Phase 3] 无激活角色，跳过")
            p3_results = []
        else:
            print(f"\n[Phase 3] 报告生成 → {', '.join(p3_roles)}")

            p1_context_long = "\n\n".join(
                f"## {r.get('name', r.get('rid', '?'))}\n{r.get('text', '')[:3000]}"
                for r in p1_results if isinstance(r, dict) and r.get("ok") and not r.get("degraded") and r.get("text")
            )
            p2_context = "\n\n".join(
                f"## {r.get('name', r.get('rid', '?'))} (验证/质检)\n{r.get('text', '')[:2000]}"
                for r in p2_results if isinstance(r, dict) and r.get("ok") and not r.get("degraded") and r.get("text")
            )
            full_context = (
                f"# Phase 1 调查结果\n{p1_context_long}\n\n"
                f"# Phase 2 验证与质检\n{p2_context}\n\n"
            )

            p3_agents = build_agents_for_phase(target, mode, phase=3,
                                               roles=p3_roles,
                                               prev_context=full_context)
            p3_results = await supervisor.enforced_batch_call(
                agents=p3_agents,
                phase=3,
                api_caller=lambda a: _api_call(session, sem, a, model, system_prompt),
                concurrency=min(concurrency, len(p3_agents)),
            )

    # ── 生成暗哨报告 ──
    sentinel_json = supervisor.report_json()

    # ── 政委统计 ──
    commissar_stats = supervisor.commissar_stats()

    # ── 汇总输出 ──
    report_text = ""
    for r in p3_results:
        if r.get("ok") and r.get("text"):
            report_text = r["text"]
            break
    if not report_text:
        report_text = _fallback_report(target, p1_results, p2_results)

    # 追加政委统计到报告末尾
    report_text += f"\n\n---\n\n## 政委质检统计\n\n```\n{commissar_stats}\n```\n"

    total_time = time.monotonic() - t_start
    print(f"\n{'='*60}")
    print(f"  尽调完成 | 总耗时: {total_time:.1f}s")
    print(f"{'='*60}\n")
    print(commissar_stats)

    # ── 保存文件 ──
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    slug = _slug(target)

    report_path = out_dir / f"report-{slug}-{ts}.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"报告已保存: {report_path}")

    sentinel_path = out_dir / f"sentinel-{slug}-{ts}.json"
    sentinel_path.write_text(sentinel_json, encoding="utf-8")
    print(f"暗哨日志: {sentinel_path}")

    return {
        "report": report_text,
        "sentinel_json": sentinel_json,
        "commissar_stats": commissar_stats,
        "report_path": str(report_path),
        "sentinel_path": str(sentinel_path),
        "output_dir": str(out_dir),
        "mode": mode,
        "roles_activated": all_roles,
        "branches_triggered": branches_triggered,
    }


def _slug(s: str) -> str:
    """中英文混合 safe slug"""
    import re
    s = re.sub(r'[^\w\u4e00-\u9fff]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:40] if s else "unknown"


def _fallback_report(target: str, p1: list[dict], p2: list[dict]) -> str:
    """刘文华生成失败时的后备报告"""
    parts = [f"# 尽调报告: {target}\n\n> ⚠ 刘文华报告生成失败，此为自动组装后备报告。\n"]
    parts.append("## 调查结果\n")
    for r in p1:
        label = r.get("name", r.get("rid", "?"))
        if not r.get("ok"):
            status = "❌ 调用失败"
        elif r.get("degraded"):
            status = "⚠ 降级"
        else:
            status = "✅"
        text = r.get("text", "").strip()
        if not text and not r.get("ok"):
            text = f"_API 调用失败: {r.get('err', '未知错误')}_"
        parts.append(f"### {label} {status}\n{text[:1000]}\n")
    parts.append("## 验证结果\n")
    for r in p2:
        label = r.get("name", r.get("rid", "?"))
        if not r.get("ok"):
            status = "❌ 调用失败"
        elif r.get("degraded"):
            status = "⚠ 降级"
        else:
            status = "✅"
        text = r.get("text", "").strip()
        if not text and not r.get("ok"):
            text = f"_API 调用失败: {r.get('err', '未知错误')}_"
        parts.append(f"### {label} {status}\n{text[:1000]}\n")
    parts.append("\n---\n*本报告由华尔街驻铁岭办事处自动生成，仅供参考。数据来源标注于各章节中。*")
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="华尔街驻铁岭办事处 · 多Agent尽调编排器 v0.3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python api/wst.py --target "腾讯科技(深圳)有限公司"
  python api/wst.py --target "字节跳动" --mode deep
  python api/wst.py --target "某小微公司" --mode sme
  python api/wst.py --target "杭州阿里巴巴" --roles zhang-tie-zhu,li-ming-yuan,zhao-gang
  python api/wst.py --target "测试公司" --dry-run

环境变量:
  DEEPSEEK_API_KEY      DeepSeek API Key
  OPENAI_API_KEY        OpenAI API Key (fallback)
  DEEPSEEK_BASE_URL     API 端点 (默认 https://api.deepseek.com/v1)

模式:
  simple    简单查询: 仅张铁柱
  standard  标准尽调: 张+李+王+赵+马 → 郑+吴 → 刘 [默认]
  deep      深度尽调: 全角色 + 条件分支
  sme       中小企业: 张+李(替代数据)+赵 → 郑 → 刘
  people    人员背调: 马+周 → 郑
  report    报告生成: 仅刘+颜

可手动指定角色:
  zhang-tie-zhu, li-ming-yuan, wang-si-yuan, zhao-gang, ma-li-quan,
  zhou-tong, zheng-shen-zhi, wu-de-hou, liu-wen-hua, yan-hao-kan
""",
    )
    parser.add_argument("--target", "-t", required=True,
                        help="尽调目标企业名称")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        help=f"模型名称 (默认: {DEFAULT_MODEL})")
    parser.add_argument("--mode", default="standard",
                        choices=["simple", "standard", "deep", "sme", "people", "report"],
                        help="尽调模式 (默认: standard)")
    parser.add_argument("--roles", default=None,
                        help="手动指定角色ID，逗号分隔 (覆盖 --mode)")
    parser.add_argument("--concurrency", "-c", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"并发数 (默认: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--max-retries", "-r", type=int, default=3,
                        help="政委最大退回次数 (默认: 3)")
    parser.add_argument("--output", "-o", default=None,
                        help="输出目录 (默认: skills/华尔街驻铁岭办事处/output/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="干运行: 只打印 Agent 配置，不实际调用 API")

    args = parser.parse_args()

    # 解析手动角色
    roles_list = None
    if args.roles:
        roles_list = [r.strip() for r in args.roles.split(",") if r.strip()]
        # 验证角色ID
        invalid = [r for r in roles_list if r not in ROLE_FILE_MAP]
        if invalid:
            print(f"错误: 无效的角色ID: {invalid}")
            print(f"有效角色: {', '.join(ROLE_FILE_MAP.keys())}")
            sys.exit(1)

    if args.dry_run:
        template = MODE_TEMPLATES.get(args.mode, MODE_TEMPLATES["standard"])
        all_roles = roles_list if roles_list else (
            template.get("phase1", []) + template.get("phase2", []) + template.get("phase3", [])
        )

        print(f"\n── 目标: {args.target}")
        print(f"── 模式: {args.mode} ({template.get('desc', '')})")
        print(f"── 模型: {args.model}")
        print(f"── 并发: {args.concurrency}")
        print(f"── 激活角色: {', '.join(all_roles) if all_roles else '(无)'}\n")

        for phase in [1, 2, 3]:
            phase_roles = roles_list if (roles_list and phase == 1) else template.get(f"phase{phase}", [])
            if not phase_roles:
                continue
            agents = build_agents_for_phase(args.target, args.mode, phase=phase,
                                            roles=phase_roles if not roles_list else (roles_list if phase == 1 else phase_roles))
            print(f"Phase {phase} Agents ({len(agents)}个):")
            for a in agents:
                print(f"  {a['name']} ({a['rid']}) — {len(a['user'])} chars prompt")
            print()

        if template.get("conditional_branches"):
            print("条件分支规则（Phase 1 自动检测）:")
            for sig_id, rule in CONDITIONAL_BRANCH_RULES.items():
                print(f"  🔀 {rule['desc']}")

        print("\n(干运行模式 —— 未执行 API 调用)")
        return

    asyncio.run(orchestrate(
        target=args.target,
        model=args.model,
        concurrency=args.concurrency,
        max_retries=args.max_retries,
        mode=args.mode,
        roles=roles_list,
        output_dir=args.output,
    ))


if __name__ == "__main__":
    main()
