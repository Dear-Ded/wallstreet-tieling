"""风险评分引擎 — 把实体关联引擎产出的 patterns 量化成可排序、可比较的风险分。

设计原则（与 entity_association / contact_extractor 一致）：
- 所有因子都是 lead：输出标注来源和证据，绝不断言。
- 评分是调查优先级排序工具，不是定罪/定性结论。
- 输入只接受 associate() 产出的结构（entity dict / patterns / associations），
  不联网、不读私密数据。
- 分数上限 100；失信被执行是最高单项（+50），但仍需人工核实。

因子表（默认权重，可通过 RISK_WEIGHTS 覆盖）：
- 空壳信号 (+30)：企业在公开渠道无电话/无地址/无招聘痕迹
- 挂名法人 (+25)：figurehead_risk pattern 涉及该实体
- 法院案件 (+20/件)：co_party_in_case 关联去重后的案件数
- 失信被执行 (+50)：实体 context 含失信标记（当前数据源未产出，
  预留给未来接入；出现即最高优先级人工核实）
- 一号多企 (+15)：shared_phone_across_businesses pattern 涉及该实体
- 一址多企 (+15)：shared_address_across_businesses pattern 涉及该实体
- 家族企业 (+10)：family_business_signal pattern 涉及该实体
- 疑似实控人 (+10)：possible_beneficial_owner pattern 涉及该实体
- 跨平台身份归一 (0)：不直接加分——它是深挖的"放大器"，
  归一后的多平台足迹会让上述因子自然累加

等级：
- 0–19   low
- 20–49  medium
- 50–79  high
- 80–100 critical
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Weights (points per factor). Override by passing custom weights to
# score_entity(..., weights={...}).
# ---------------------------------------------------------------------------

RISK_WEIGHTS: dict[str, float] = {
    "shell_signal": 30,
    "figurehead_risk": 25,
    "court_case": 20,          # per case
    "dishonest_executor": 50,
    "shared_phone": 15,
    "shared_address": 15,
    "family_business": 10,
    "beneficial_owner": 10,
}

MAX_SCORE = 100

_LEVELS = (
    (80, "critical"),
    (50, "high"),
    (20, "medium"),
    (0, "low"),
)

_DISHONEST_MARKERS = ("失信", "被执行人", "dishonest", "laolai", "老赖")

_RECRUIT_SOURCES = {"lagou", "zhaopin", "zhipin"}

_DISCLAIMER = (
    "Risk scores are investigative leads for prioritization only. "
    "They are computed from public-source patterns and do not assert "
    "wrongdoing, ownership, or control. Verify each factor manually "
    "before acting."
)


def _pattern_involves(pattern: dict[str, Any], entity_id: str) -> bool:
    return entity_id in (pattern.get("entities") or [])


def _entity_dishonest(entity: dict[str, Any]) -> tuple[bool, str]:
    """失信被执行标记检测。

    当前公开数据源尚未产出结构化失信字段，这里检测：
    1. context["dishonest"] / context["dishonest_executor"] 显式 True；
    2. context 文本中出现失信相关关键词。
    出现即返回 True 并给出证据出处，留给人工核实。
    """
    ctx = entity.get("context") or {}
    if ctx.get("dishonest") is True or ctx.get("dishonest_executor") is True:
        return True, "context.dishonest 显式标记"
    haystack_parts: list[str] = []
    for key in ("case_type", "notice_type", "title", "description", "note"):
        val = ctx.get(key)
        if val:
            haystack_parts.append(str(val))
    for src in (entity.get("sources") or []):
        haystack_parts.append(str(src))
    haystack = " ".join(haystack_parts)
    for marker in _DISHONEST_MARKERS:
        if marker in haystack:
            return True, "context 文本含失信标记「{}」".format(marker)
    return False, ""


def _entity_shell(entity: dict[str, Any]) -> tuple[bool, str]:
    """空壳信号：企业类型，且无电话/无地址/无招聘痕迹。"""
    if entity.get("type") != "business":
        return False, ""
    ctx = entity.get("context") or {}
    sources = set(entity.get("sources") or [])
    has_phone = bool(ctx.get("phone") or ctx.get("phones") or ctx.get("tel"))
    has_address = bool(ctx.get("address") or ctx.get("addr"))
    has_recruit = bool(sources & _RECRUIT_SOURCES)
    if not has_phone and not has_address and not has_recruit:
        return True, "公开渠道未发现电话/地址/招聘痕迹（需结合其他证据判断）"
    return False, ""


def _case_count(entity_id: str, associations: list[dict[str, Any]]) -> int:
    """去重后的法院案件关联数（co_party_in_case）。"""
    cases: set[str] = set()
    for a in associations:
        if a.get("relation") != "co_party_in_case":
            continue
        if a.get("from") == entity_id:
            cases.add(str(a.get("to")))
        elif a.get("to") == entity_id:
            cases.add(str(a.get("from")))
    return len(cases)


def _collect_factor(
        factors: list[dict[str, Any]], score_parts: list[float],
        name: str, points: float, evidence: str, source: str) -> None:
    factors.append({
        "factor": name,
        "points": points,
        "evidence": evidence,
        "source": source,
    })
    score_parts.append(points)


def score_entity(
        entity: dict[str, Any],
        patterns: list[dict[str, Any]] | None = None,
        associations: list[dict[str, Any]] | None = None,
        weights: dict[str, float] | None = None) -> dict[str, Any]:
    """给单个实体打风险分。

    Args:
        entity: associate() 产出的 entity dict（需含 id/type/display）。
        patterns: associate()["interesting_patterns"]。
        associations: associate()["associations"]（用于法院案件计数）。
        weights: 覆盖默认权重的 dict。

    Returns:
        {"entity_id", "display", "type", "score", "level",
         "factors": [...], "disclaimer"}
    """
    patterns = patterns or []
    associations = associations or []
    w = dict(RISK_WEIGHTS)
    if weights:
        w.update(weights)

    eid = str(entity.get("id", ""))
    display = entity.get("display") or entity.get("value") or eid
    factors: list[dict[str, Any]] = []
    parts: list[float] = []

    # 1. 空壳信号 (+30)
    is_shell, shell_evidence = _entity_shell(entity)
    if is_shell:
        _collect_factor(factors, parts, "shell_signal", w["shell_signal"],
                        shell_evidence, "entity context 缺失三要素")

    # 2. 失信被执行 (+50，最高单项)
    is_dishonest, dishonest_evidence = _entity_dishonest(entity)
    if is_dishonest:
        _collect_factor(factors, parts, "dishonest_executor",
                        w["dishonest_executor"], dishonest_evidence,
                        "entity context 标记")

    # 3. 法院案件 (+20/件)
    n_cases = _case_count(eid, associations)
    if n_cases:
        _collect_factor(
            factors, parts, "court_cases", w["court_case"] * n_cases,
            "关联 {} 起法院案件（wenshu/court_notice，lead 非定罪）".format(n_cases),
            "associations.co_party_in_case")

    # 4. pattern 命中
    pattern_rules = [
        ("figurehead_risk", "figurehead_risk",
         "挂名法人风险", "疑似法定代表人挂名"),
        ("shared_phone_across_businesses", "shared_phone",
         "一号多企", "同一手机号关联多家企业（代办/中介/集团共用信号）"),
        ("shared_address_across_businesses", "shared_address",
         "一址多企", "同一地址关联多家企业（虚拟地址/集中办公信号）"),
        ("family_business_signal", "family_business",
         "家族企业", "同姓人员共同担任要职"),
        ("possible_beneficial_owner", "beneficial_owner",
         "疑似实控人", "非法定代表人但疑似实际控制"),
    ]
    for pattern_name, weight_key, label, desc in pattern_rules:
        hits = [p for p in patterns
                if p.get("pattern") == pattern_name
                and _pattern_involves(p, eid)]
        if hits:
            _collect_factor(
                factors, parts, weight_key, w[weight_key],
                "{}：{}".format(label, hits[0].get("description", desc)),
                "interesting_patterns.{}".format(pattern_name))

    raw = sum(parts)
    score = min(MAX_SCORE, int(round(raw)))
    level = next(lv for threshold, lv in _LEVELS if score >= threshold)

    return {
        "entity_id": eid,
        "display": display,
        "type": entity.get("type"),
        "score": score,
        "level": level,
        "factors": factors,
        "disclaimer": _DISCLAIMER,
    }


def score_investigation(result: dict[str, Any],
                        weights: dict[str, float] | None = None,
                        top_n: int = 10) -> dict[str, Any]:
    """给一次 associate() 调查结果中的实体批量打分，按分排序。

    只对 business / person 类型实体打分（seed 本身若在其中也会被覆盖）。
    """
    entities = result.get("entities") or []
    patterns = result.get("interesting_patterns") or []
    associations = result.get("associations") or []
    scored = [
        score_entity(e, patterns, associations, weights)
        for e in entities
        if e.get("type") in ("business", "person")
    ]
    scored.sort(key=lambda s: (-s["score"], str(s["display"])))
    return {
        "seed": result.get("seed"),
        "ranked": scored[:top_n],
        "count": len(scored),
        "disclaimer": _DISCLAIMER,
    }
