#!/usr/bin/env python3
"""wallstreet-tieling v3.1.0 — 质量规则引擎 (提取自 unified_supervisor)
L1 纯 Python 规则扫描 + L2 No Fabrication 输出校验。
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("wst.quality")


@dataclass
class Violation:
    """质量违规项"""
    rule: str
    field: str
    detail: str
    severity: str = "ERROR"


# ── 模糊词权威列表（单一来源，消除双轨）──
VAGUE_WORDS_TERMS = [
    "大概是", "一般为", "通常为",
    "大概", "可能", "也许", "似乎", "差不多", "左右",
    "估计", "应该", "好像", "或许", "可能是", "好像是",
]


def _build_vague_regex() -> re.Pattern:
    """从 VAGUE_WORDS_TERMS 动态构建正则，消除双轨不同步"""
    escaped = [re.escape(t) for t in VAGUE_WORDS_TERMS]
    return re.compile('(' + '|'.join(escaped) + ')')


class QualityRules:
    """L1 纯 Python 规则扫描 —— 零 LLM 成本"""

    # 违规词模式
    CREDIT_WORDS = re.compile(
        r'(建议通过|不建议|建议|推荐|应授信|可放款|风险可控|建议授信|'
        r'建议额度|建议利率|审批通过|拒绝授信|可信贷|建议贷款)'
    )
    # 从 VAGUE_WORDS_TERMS 动态构建，单一来源
    VAGUE_WORDS = _build_vague_regex()
    NO_SOURCE = re.compile(r'\[来源[:：]')
    URL_PATTERN = re.compile(r'https?://[^\s\)\]】,，。]+')

    # 编造检测正则
    RE_BARE_NUMBER = re.compile(
        r'(?<!\d)(\d{2,}(?:\.\d+)?)\s*(?:亿|万|千|百|元|%|％)'
    )
    RE_BARE_DATE = re.compile(
        r'(?<!\d)\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?!\d)'
    )
    RE_ANONYMOUS_SOURCE = re.compile(
        r'(?:据悉|据[了了解]解|知情人士|业内人士|消息人士|'
        r'不愿透露姓名|匿名|内部人士|接近.*人士)'
    )

    @classmethod
    def scan(cls, text: str, agent_name: str = "") -> list[Violation]:
        """扫描一段 Agent 输出，返回违规列表"""
        violations: list[Violation] = []

        # 1. 信贷决策词
        credit_matches = cls.CREDIT_WORDS.findall(text)
        if credit_matches:
            violations.append(Violation(
                rule="credit_word",
                field="full_text",
                detail=f'检测到信贷决策词: {", ".join(set(credit_matches))}',
                severity="ERROR",
            ))

        # 2. 模糊词
        vague_matches = cls.VAGUE_WORDS.findall(text)
        if vague_matches:
            real_vague = [m for m in vague_matches
                          if f'"{m}"' not in text and f'" {m}' not in text]
            if real_vague:
                violations.append(Violation(
                    rule="vague_word",
                    field="full_text",
                    detail=f'检测到模糊词: {", ".join(set(real_vague))}',
                    severity="WARN",
                ))

        # 3. 来源标注
        if len(text) > 100 and not cls.NO_SOURCE.search(text):
            violations.append(Violation(
                rule="no_source",
                field="full_text",
                detail="输出未标注任何数据来源 [来源: xxx]",
                severity="ERROR",
            ))

        # 4. 截断检测
        if len(text) < 200:
            violations.append(Violation(
                rule="short_output",
                field="full_text",
                detail=f"疑似输出截断，仅 {len(text)} 字符",
                severity="WARN",
            ))

        return violations

    @classmethod
    def check_urls(cls, text: str) -> list[str]:
        return cls.URL_PATTERN.findall(text)

    @classmethod
    def check_fabrication_indicators(cls, text: str) -> list[dict]:
        """检测编造迹象"""
        indicators: list[dict] = []

        anon = cls.RE_ANONYMOUS_SOURCE.findall(text)
        if anon:
            indicators.append({
                "indicator": "anonymous_source",
                "count": len(anon),
                "matches": list(set(anon))[:5],
                "msg": f"发现 {len(anon)} 处匿名/无法溯源的消息来源",
            })

        numbers = cls.RE_BARE_NUMBER.findall(text)
        has_source = bool(cls.NO_SOURCE.search(text))
        if numbers and not has_source:
            indicators.append({
                "indicator": "bare_number_no_source",
                "count": len(numbers),
                "matches": numbers[:5],
                "msg": f"发现 {len(numbers)} 个数字但无任何 [来源:] 标注",
            })

        meaningful = re.sub(r'\s+', '', text)
        if len(text) > 500 and len(meaningful) < len(text) * 0.3:
            indicators.append({
                "indicator": "low_density",
                "msg": f"文本密度低 ({len(meaningful)}/{len(text)} 有效字符)",
            })

        return indicators

    @classmethod
    def validate_dd_output(cls, output: str, agent_name: str = "") -> dict:
        """尽调输出全面校验"""
        issues: list[str] = []
        stats = {
            "data_points": 0, "source_citations": 0,
            "fabrication_indicators": 0, "fuzzy_terms": 0,
            "has_data_gap_marker": False,
        }

        data_points = cls.RE_BARE_NUMBER.findall(output)
        stats["data_points"] = len(data_points)

        source_matches = cls.NO_SOURCE.findall(output)
        stats["source_citations"] = len(source_matches)

        if len(output) > 200 and stats["data_points"] > 3:
            ratio = stats["source_citations"] / max(stats["data_points"], 1)
            if ratio < 0.2:
                issues.append(
                    f"来源覆盖率低: {stats['source_citations']} 标注 / "
                    f"{stats['data_points']} 数据点 = {ratio:.0%}，建议 ≥20%"
                )

        has_gap = ("[未获取]" in output or "[数据缺失]" in output
                   or "[N/A]" in output or "[无数据]" in output)
        stats["has_data_gap_marker"] = has_gap

        if not has_gap and len(output) > 300:
            issues.append(
                "提示: 输出中未发现 [未获取] 标记，请确认所有期望字段都成功获取到数据"
            )

        for term in VAGUE_WORDS_TERMS:
            if term in output:
                stats["fuzzy_terms"] += output.count(term)

        if stats["fuzzy_terms"] > 2:
            issues.append(
                f"模糊表述较多 ({stats['fuzzy_terms']} 处)"
            )

        fab_indicators = cls.check_fabrication_indicators(output)
        stats["fabrication_indicators"] = len(fab_indicators)
        for fi in fab_indicators:
            issues.append(f"[编造风险] {fi['msg']}")

        cleaned = re.sub(r'\[来源[：:][^\]]+\]', '', output)
        bare_ints = re.findall(r'(?<!\d)\d{2,}(?![\d,.]*(?:万|亿|元|%|％|年|月|日|人|个|家|次|件|-\d))', cleaned)
        if bare_ints and len(bare_ints) > 3:
            issues.append(f"可能存在无单位的数字: {bare_ints[:5]}")

        score = 100.0
        warn_count = len([i for i in issues if not i.startswith("[编造风险]")])
        score -= warn_count * 5
        score -= stats["fabrication_indicators"] * 15
        score = max(0.0, min(100.0, score))

        valid = stats["fabrication_indicators"] == 0 and score >= 70

        return {"valid": valid, "score": score, "issues": issues, "stats": stats}
