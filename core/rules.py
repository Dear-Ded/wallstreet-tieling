#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 引擎规则与模板
从 api/orchestrator.py 迁移，切断 engine 对 api/ 的依赖。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════
#  No Fabrication 六层防御
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
#  Phase User Prompt 模板
# ═══════════════════════════════════════════════════════════

PHASE1_TEMPLATES: dict[str, Any] = {
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

PHASE2_TEMPLATES: dict[str, Any] = {
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

PHASE3_TEMPLATES: dict[str, Any] = {
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

ALL_USER_TEMPLATES = {**PHASE1_TEMPLATES, **PHASE2_TEMPLATES, **PHASE3_TEMPLATES}


# ═══════════════════════════════════════════════════════════
#  模式模板
# ═══════════════════════════════════════════════════════════

MODE_TEMPLATES: dict[str, dict] = {
    "simple": {"phase1": ["zhang-tie-zhu"], "phase2": [], "phase3": []},
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
    "deep_people": {
        "phase1": ["ma-li-quan", "zhang-tie-zhu"],
        "phase2": ["zhao-gang", "zheng-shen-zhi"],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "conditional_branches": True,
        "meeting": True,
    },
    "report": {
        "phase1": [],
        "phase2": [],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
    },
}


# ═══════════════════════════════════════════════════════════
#  条件分支规则（从 references/conditional-branch-rules.json 加载）
# ═══════════════════════════════════════════════════════════

def _load_branch_rules() -> dict:
    import json as _json
    rules_path = Path(__file__).resolve().parent.parent / "references" / "conditional-branch-rules.json"
    if rules_path.exists():
        try:
            data = _json.loads(rules_path.read_text(encoding="utf-8"))
            return data.get("rules", {})
        except Exception:
            pass
    return {
        "controller_anomaly": {
            "signal_keywords": ["实控人不一致", "代持", "影子控制", "实际控制人不明",
                               "法人与实控人不一致", "隐名股东"],
            "append_role": "ma-li-quan", "desc": "实控人异常 → 追加马力全深度背调",
        },
        "large_deposit_loan": {
            "signal_keywords": ["大存大贷", "存贷双高", "存贷双高现象", "高存高贷",
                               "货币资金占比过高", "有息负债同时高企"],
            "append_role": "zhao-gang", "desc": "大存大贷 → 追加赵刚深度风险扫描",
        },
        "many_related": {
            "signal_keywords": ["关联企业超过10家", "关联方众多", "大量关联",
                               "疑似壳公司", "关联交易频繁"],
            "append_role": "zhao-gang", "desc": "大量关联企业 → 追加赵刚担保圈分析",
        },
        "cashflow_quality": {
            "signal_keywords": ["经营现金流/净利润低于50%", "现金流质量差",
                               "经营现金流为负", "现金流覆盖不足"],
            "append_role": "zheng-shen-zhi", "desc": "现金流质量差 → 追加郑慎之财务专项检查",
        },
        "dishonest_record": {
            "signal_keywords": ["失信被执行人", "被执行人", "限制高消费",
                               "列入失信名单", "失信记录"],
            "append_role": "zhang-tie-zhu", "desc": "失信记录 → 追加张铁柱重新核实工商状态",
        },
        "registration_mismatch": {
            "signal_keywords": ["注册资金与经营不匹配", "注册资本异常", "注册资本变更异常"],
            "append_role": "zheng-shen-zhi", "desc": "注册异常 → 追加郑慎之工商数据专项验证",
        },
    }

CONDITIONAL_BRANCH_RULES = _load_branch_rules()

SIGNAL_PRIORITY = [
    "dishonest_record", "controller_anomaly", "large_deposit_loan",
    "cashflow_quality", "many_related", "registration_mismatch",
]
