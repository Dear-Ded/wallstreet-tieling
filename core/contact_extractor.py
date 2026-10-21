"""联系方式深度提取器 — 个人深挖的核心模块。

"身份特征代码"：QQ 号、微信号、手机号、邮箱、平台 UID ——
串起一个人在全网足迹的串联键。

设计原则（与 entity_association 一致）：
- 所有输出都是 lead，标注置信度 (exact/strong/weak)，绝不断言。
- 只从传入文本中提取，不联网、不登录、不碰私密数据。
- 审计友好：不返回原文长串，只返回提取值 + 短上下文。

Confidence 语义：
- exact   — 格式本身无歧义（手机号 11 位、标准邮箱）。
- strong  — 有明确的上下文关键词（"QQ：12345"、"微信号：abc"）。
- weak    — 裸数字/裸 ID，无上下文，只能作候选。
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_MOBILE_FIND_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LANDLINE_FIND_RE = re.compile(
    r"(?<!\d)(0\d{2,3})[-\s]?(\d{7,8})(?!\d)"
)
_EMAIL_FIND_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

# QQ：5-12 位数字，首位非 0。裸匹配时与手机号段互斥（手机号先行）。
_QQ_FIND_RE = re.compile(r"(?<!\d)[1-9]\d{4,11}(?!\d)")
_QQ_CONTEXT_RE = re.compile(
    r"(?:QQ|qq|Q\s*Q)[号\s:：]*([1-9]\d{4,11})"
)

# 微信号：字母开头，6-20 位，允许字母/数字/_/-。wxid_ 开头为系统分配号。
_WECHAT_ID_RE = r"[a-zA-Z][a-zA-Z0-9_-]{5,19}|wxid_[a-zA-Z0-9]{8,}"
_WECHAT_CONTEXT_RE = re.compile(
    r"(?:微信号|微信|WeChat|wechat|V\s*信)[号\s:：]*(" + _WECHAT_ID_RE + r")"
)
_WECHAT_BARE_RE = re.compile(r"(?<!\w)(" + _WECHAT_ID_RE + r")(?!\w)")

# 微博 UID：纯数字 ID，常出现在 "uid:123456" / "微博：12345678" 语境
_WEIBO_UID_CONTEXT_RE = re.compile(
    r"(?:微博\s*(?:UID|uid|号|ID)?|uid|UID)[\s:：]*(\d{6,12})"
)

# 抖音号：抖音号：xxx / 抖音：xxx
_DOUYIN_CONTEXT_RE = re.compile(
    r"抖音号?[\s:：]*([a-zA-Z0-9_.-]{2,30})"
)

# 快手号 / B站 UID / 小红书号 —— 通用"平台+号"模式
_PLATFORM_ID_CONTEXT_RE = re.compile(
    r"(快手号|快手|B站|哔哩哔哩|小红书号|小红书|知乎号|豆瓣|贴吧)[号\s:：]*([a-zA-Z0-9_.\u4e00-\u9fa5-]{2,30})"
)

# 400/800 客服号（企业联系方式，非个人，但值得标注）
_SERVICE_NUM_RE = re.compile(r"(?<!\d)(?:400\d{7}|800\d{7})(?!\d)")

# 上下文窗口：前后各 N 字符
_CONTEXT_WINDOW = 30

# 明显不是 QQ 的数字黑名单（年份、常见量级）
_QQ_BLACKLIST = frozenset(
    str(y) for y in range(1990, 2031)
) | {"10000", "10086", "10010", "10001", "95588", "12306", "110", "120", "119"}


def _snippet(text: str, start: int, end: int, window: int = _CONTEXT_WINDOW) -> str:
    s = max(0, start - window)
    e = min(len(text), end + window)
    out = text[s:e].replace("\n", " ").strip()
    return out[: 2 * window + 40]


def _is_mobile_span(text: str, start: int, end: int) -> bool:
    """裸 QQ 候选是否其实是手机号（11 位 1[3-9] 开头）。"""
    frag = text[start:end]
    return bool(re.fullmatch(r"1[3-9]\d{9}", frag))


# ---------------------------------------------------------------------------
# extract_contacts
# ---------------------------------------------------------------------------

def extract_contacts(text: Any, source_label: str = "") -> list[dict[str, Any]]:
    """从文本中提取联系方式/身份特征代码。

    返回 [{"type", "value", "confidence", "context", "source_label"}]，
    按 (confidence, type) 排序，去重。
    """
    if not text:
        return []
    t = str(text)
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(ctype: str, value: str, confidence: str, start: int, end: int) -> None:
        value = value.strip()
        if not value:
            return
        key = (ctype, value.lower() if ctype == "email" else value)
        if key in seen:
            return
        seen.add(key)
        found.append({
            "type": ctype,
            "value": value,
            "confidence": confidence,
            "context": _snippet(t, start, end),
            "source_label": source_label,
        })

    # 1) 手机号 — 格式无歧义 → exact
    for m in _MOBILE_FIND_RE.finditer(t):
        _add("mobile", m.group(0), "exact", m.start(), m.end())

    # 2) 座机 — 格式较明确 → strong
    for m in _LANDLINE_FIND_RE.finditer(t):
        _add("landline", m.group(1) + "-" + m.group(2), "strong", m.start(), m.end())

    # 3) 400/800 客服号 → strong（企业联系方式）
    for m in _SERVICE_NUM_RE.finditer(t):
        _add("service_number", m.group(0), "strong", m.start(), m.end())

    # 4) 邮箱 — 格式无歧义 → exact
    for m in _EMAIL_FIND_RE.finditer(t):
        _add("email", m.group(0).lower(), "exact", m.start(), m.end())

    # 5) QQ（带上下文）— "QQ：123456" → strong
    for m in _QQ_CONTEXT_RE.finditer(t):
        _add("qq", m.group(1), "strong", m.start(), m.end())

    # 6) QQ（裸数字）— 5-12 位非手机号 → weak；排除黑名单
    for m in _QQ_FIND_RE.finditer(t):
        frag = m.group(0)
        if _is_mobile_span(t, m.start(), m.end()):
            continue  # 手机号已在步骤 1 提取
        if frag in _QQ_BLACKLIST:
            continue
        if len(frag) == 11:
            continue  # 11 位非 1 开头：疑似座机/其他，降级不收
        _add("qq", frag, "weak", m.start(), m.end())

    # 7) 微信号（带上下文）— "微信号：abc123" → strong
    for m in _WECHAT_CONTEXT_RE.finditer(t):
        _add("wechat", m.group(1), "strong", m.start(), m.end())

    # 8) 微博 UID（带上下文）→ strong
    for m in _WEIBO_UID_CONTEXT_RE.finditer(t):
        _add("weibo_uid", m.group(1), "strong", m.start(), m.end())

    # 9) 抖音号（带上下文）→ strong
    for m in _DOUYIN_CONTEXT_RE.finditer(t):
        _add("douyin_id", m.group(1), "strong", m.start(), m.end())

    # 10) 其他平台号（带上下文）→ strong（平台名已明确）
    for m in _PLATFORM_ID_CONTEXT_RE.finditer(t):
        _add("platform_uid", m.group(2), "strong", m.start(), m.end())

    order = {"exact": 0, "strong": 1, "weak": 2}
    found.sort(key=lambda c: (order.get(c["confidence"], 3), c["type"], c["value"]))
    return found


# ---------------------------------------------------------------------------
# aggregate_person_contacts
# ---------------------------------------------------------------------------

# entity_association 产出的 entity 结构：{"type", "value"/"display", "sources", "context"}
# 这里从每个实体的 value + context 文本里再挖联系方式，聚合成"一个人"的联系清单。

_CONTACT_TYPE_PRIORITY = (
    "mobile", "landline", "email", "wechat", "qq",
    "weibo_uid", "douyin_id", "platform_uid", "service_number",
)


def aggregate_person_contacts(
    entities: dict[str, dict[str, Any]] | list[dict[str, Any]],
    person_key: str | None = None,
) -> dict[str, Any]:
    """从实体关联结果中聚合联系方式。

    entities: associate() 返回的 entities（dict keyed by id，或 list）。
    person_key: 可选，只聚合与该人物相关的实体（按 context 中的 of_account/
                of_person / display 匹配）；None 则聚合全部。

    返回 {"contacts": [...], "by_entity": {entity_id: [...]}, "summary": {...}}。
    contacts 按置信度排序，同 (type, value) 合并 sources。
    """
    if isinstance(entities, dict):
        items = list(entities.items())
    else:
        items = [(str(i), e) for i, e in enumerate(entities)]

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    by_entity: dict[str, list[dict[str, Any]]] = {}

    for eid, e in items:
        if not isinstance(e, dict):
            continue
        if person_key:
            ctx = e.get("context") or {}
            hay = " ".join([
                str(e.get("display", "")),
                str(e.get("value", "")),
                str(ctx.get("of_account", "")),
                str(ctx.get("of_person", "")),
                str(ctx.get("author", "")),
            ])
            if person_key not in hay:
                continue
        # 待挖掘文本：display/value + context 里的文本字段
        ctx = e.get("context") or {}
        texts: list[str] = []
        for k in ("display", "value"):
            v = e.get(k)
            if v:
                texts.append(str(v))
        for k in ("bio", "signature", "description", "text", "summary",
                  "company", "position", "author"):
            v = ctx.get(k)
            if v:
                texts.append(str(v))
        label = str(e.get("display") or e.get("value") or eid)
        local: list[dict[str, Any]] = []
        for tx in texts:
            for c in extract_contacts(tx, source_label=label):
                local.append(c)
                key = (c["type"], c["value"])
                if key not in merged:
                    merged[key] = dict(c)
                    merged[key]["sources"] = sorted(set(
                        (e.get("sources") or []) + [label]
                    ))
                else:
                    ex = merged[key]
                    ex["sources"] = sorted(set(
                        ex.get("sources", []) + (e.get("sources") or []) + [label]
                    ))
                    # 置信度取最高
                    rank = {"exact": 0, "strong": 1, "weak": 2}
                    if rank.get(c["confidence"], 3) < rank.get(ex["confidence"], 3):
                        ex["confidence"] = c["confidence"]
                        ex["context"] = c["context"]
        if local:
            by_entity[eid] = local

    contacts = sorted(
        merged.values(),
        key=lambda c: (
            {"exact": 0, "strong": 1, "weak": 2}.get(c["confidence"], 3),
            _CONTACT_TYPE_PRIORITY.index(c["type"])
            if c["type"] in _CONTACT_TYPE_PRIORITY else 99,
            c["value"],
        ),
    )
    type_counts: dict[str, int] = {}
    for c in contacts:
        type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1

    return {
        "contacts": contacts,
        "by_entity": by_entity,
        "summary": {
            "total": len(contacts),
            "by_type": type_counts,
            "disclaimer": "提取结果为 lead，weak 项需人工核实；"
                          "QQ/微信号等需结合其他证据确认归属。",
        },
    }
