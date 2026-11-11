#!/usr/bin/env python3
"""Render intel-enrichment payloads into report sections (Markdown + HTML).

纯渲染模块：不采集、不构造 adapter、不改注册表、不改任何字段语义。
接受的 payload 形状：

- ``{"type": "domain_intel_enrichment", ...}``
  （``core.intel_enrichment.enrich_domain`` 产出）
- ``{"type": "people_lead_graph", ...}``
  （``PeopleIntelOrchestrator.investigate`` 产出）
- ``{"seed": ..., "entities": [...], "associations": [...],
  "risk_scores": {...}, ...}``
  （``EntityAssociationEngine.associate`` 产出：关联发现 + 风险评分）
- ``{"contacts": [...], "by_entity": {...}, "summary": {...}}``
  （``core.contact_extractor.aggregate_person_contacts`` 产出：联系方式提取）

证据口径：所有富化输出一律按「线索（lead）」渲染，不做事实断言；
每节附带来源与原 payload 的 policy 口径。空结果/缺失字段时优雅降级，
不输出空节。
"""

from __future__ import annotations

import html as _html
from typing import Any

_DOMAIN_TYPE = "domain_intel_enrichment"
_PEOPLE_TYPE = "people_lead_graph"

_LEAD_BADGE = "线索（lead，需复核）"

# packet 中可能携带富化结果的常规 key；extract_enrichments 也会扫描
# 顶层 dict 值做类型标记匹配。
_ENRICHMENT_KEYS = (
    "enrichment",
    "enrichments",
    "intel_enrichment",
    "domain_enrichment",
    "people_enrichment",
    "entity_association",
    "association_result",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _short(text: Any, limit: int = 120) -> str:
    text = str(text or "").strip().replace("\n", " ")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def payload_kind(payload: Any) -> str:
    """Return one of: domain / people / association / contacts / unknown."""
    p = _dict(payload)
    if not p:
        return "unknown"
    ptype = str(p.get("type") or "")
    if ptype == _DOMAIN_TYPE:
        return "domain"
    if ptype == _PEOPLE_TYPE:
        return "people"
    if isinstance(p.get("seed"), dict) and isinstance(p.get("associations"), list) \
            and isinstance(p.get("entities"), (list, dict)):
        return "association"
    if isinstance(p.get("contacts"), list) and isinstance(p.get("by_entity"), dict):
        return "contacts"
    return "unknown"


def extract_enrichments(packet: Any) -> list[dict[str, Any]]:
    """Find enrichment payloads inside an investigation packet.

    只识别、不改造：按常规 key 与类型标记收集，去重（type+subject）。
    """
    packet = _dict(packet)
    found: list[dict[str, Any]] = []

    def _collect(candidate: Any) -> None:
        if payload_kind(candidate) == "unknown":
            return
        for existing in found:
            if _payload_identity(existing) == _payload_identity(candidate):
                return
        found.append(_dict(candidate))

    for key in _ENRICHMENT_KEYS:
        value = packet.get(key)
        if isinstance(value, list):
            for item in value:
                _collect(item)
        else:
            _collect(value)
    # 兜底：扫描顶层所有 dict 值
    for value in packet.values():
        _collect(value)
    return found


def _payload_identity(payload: dict[str, Any]) -> tuple:
    kind = payload_kind(payload)
    if kind == "domain":
        return (kind, str(payload.get("domain") or ""))
    if kind == "people":
        return (kind, str(payload.get("subject_hash") or ""))
    if kind == "association":
        seed = _dict(payload.get("seed"))
        return (kind, str(seed.get("type") or ""), str(seed.get("value") or ""))
    return (kind, str(sorted(payload.keys())))


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render_enrichment_markdown(payload: dict[str, Any]) -> list[str]:
    """Render one enrichment payload as Markdown lines (empty if nothing)."""
    kind = payload_kind(payload)
    if kind == "domain":
        return _domain_markdown(_dict(payload))
    if kind == "people":
        return _people_markdown(_dict(payload))
    if kind == "association":
        return _association_markdown(_dict(payload))
    if kind == "contacts":
        return _contacts_markdown(_dict(payload))
    return []


def render_enrichments_markdown(payloads: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for payload in payloads or []:
        section = render_enrichment_markdown(payload)
        if section:
            lines.extend([""] + section)
    return lines


def _domain_markdown(p: dict[str, Any]) -> list[str]:
    sources = _dict(p.get("sources"))
    if not sources and not _list(p.get("risk_notes")):
        return []
    lines = ["## 情报富化 · 域名基础设施"]
    lines.append(
        f"- 目标域名: {_short(p.get('domain'))} | 数据源: {p.get('source_count', len(sources))} 个"
        f" | 证据分级: {_LEAD_BADGE}"
    )
    # urlscan
    urlscan = _dict(_dict(sources.get("urlscan")).get("fields"))
    if urlscan and not _dict(sources.get("urlscan")).get("error"):
        lines.append("### urlscan.io 公开扫描历史")
        lines.append(f"- 公开扫描记录: {urlscan.get('total_scans', 0)} 条")
        for scan in _list(urlscan.get("recent_scans"))[:3]:
            if not isinstance(scan, dict):
                continue
            lines.append(
                f"- {_short(scan.get('scanned_url'), 90)} | {_short(scan.get('scan_date'), 24)}"
                f" | {_short(scan.get('page_title'), 60)}"
            )
            if scan.get("result_url"):
                lines.append(f"  - 来源: {scan.get('result_url')}")
        lines.append(
            f"- 来源: https://urlscan.io/search/#domain:{_short(p.get('domain'))}"
        )
    elif _dict(sources.get("urlscan")).get("error"):
        lines.append(
            f"- urlscan 数据源失败: {_short(_dict(sources.get('urlscan')).get('error'))}"
        )
    # hackertarget
    ht_raw = _dict(sources.get("hackertarget"))
    ht = _dict(ht_raw.get("fields"))
    if ht and not ht_raw.get("error"):
        lines.append("### DNS 与反查（hackertarget 公开接口）")
        records = _dict(_dict(ht.get("dnslookup")).get("records"))
        a_records = [str(x) for x in _list(records.get("A"))[:5] if str(x).strip()]
        if a_records:
            lines.append(f"- A 记录: {'; '.join(a_records)}")
        reverse = _dict(ht.get("reverseiplookup"))
        neighbor_count = reverse.get("neighbor_count")
        if isinstance(neighbor_count, int):
            lines.append(f"- 同 IP 邻居域名: {neighbor_count} 个（共享主机线索）")
            neighbors = [str(x) for x in _list(reverse.get("neighbors"))[:5]]
            if neighbors:
                lines.append(f"  - 示例: {'; '.join(_short(n, 40) for n in neighbors)}")
    elif ht_raw.get("error"):
        lines.append(
            f"- hackertarget 数据源失败: {_short(ht_raw.get('error'))}"
        )
    # ipapi
    ip_raw = _dict(sources.get("ipapi"))
    ipf = _dict(ip_raw.get("fields"))
    if ipf and not ip_raw.get("error"):
        lines.append("### IP 地理与 ASN（ip-api 公开数据）")
        geo = " / ".join(x for x in (
            _short(ipf.get("country")), _short(ipf.get("regionName")),
            _short(ipf.get("city"))) if x)
        if geo:
            lines.append(f"- 地理: {geo}")
        org_parts = [x for x in (
            _short(ipf.get("org"), 80), _short(ipf.get("as"), 40)) if x]
        if org_parts:
            lines.append(f"- 组织/ASN: {' | '.join(org_parts)}")
        flags = []
        if ipf.get("is_hosting") is True:
            flags.append("位于托管机房")
        if ipf.get("is_proxy") is True:
            flags.append("疑似代理出口（地理归属仅供参考）")
        if flags:
            lines.append(f"- 标记: {'；'.join(flags)}")
    elif ip_raw.get("error"):
        lines.append(f"- ip-api 数据源失败: {_short(ip_raw.get('error'))}")
    # risk notes
    risk_notes = [str(x).strip() for x in _list(p.get("risk_notes")) if str(x).strip()]
    if risk_notes:
        lines.append("### 线索提示（仅为线索，不做归属或风险断言）")
        for note in risk_notes[:8]:
            lines.append(f"- ⚠️ {_short(note, 160)}")
    if p.get("policy"):
        lines.append(f"- 口径: {_short(p.get('policy'), 180)}")
    return lines


def _people_markdown(p: dict[str, Any]) -> list[str]:
    sources = _dict(p.get("sources"))
    if not sources and not _list(p.get("corroborations")):
        if p.get("note"):
            return [
                "## 情报富化 · 人物公开情报",
                f"- {_short(p.get('note'), 200)} | 证据分级: {_LEAD_BADGE}",
            ]
        return []
    lines = ["## 情报富化 · 人物公开情报"]
    provided = _dict(p.get("identifiers_provided"))
    if provided:
        marks = []
        for key, label in (("name", "姓名"), ("email", "邮箱"),
                           ("username", "用户名"), ("github_username", "GitHub")):
            marks.append(f"{label}{'✓' if provided.get(key) else '–'}")
        lines.append(f"- 已提供标识: {' '.join(marks)}")
    lines.append(
        f"- 数据源: {p.get('source_count', len(sources))} 个"
        f" | 证据分级: {_LEAD_BADGE}"
    )
    if p.get("subject_hash"):
        lines.append(f"- 主体引用: `{_short(p.get('subject_hash'), 16)}`（内部去重用哈希，非身份断言）")
    # 画像摘要：各源 fields 提炼
    profile_lines = _people_profile_lines(sources)
    if profile_lines:
        lines.append("### 画像摘要")
        lines.extend(profile_lines)
    # 跨平台身份
    footprint = _dict(_dict(sources.get("username_footprint")).get("fields"))
    if footprint and not _dict(sources.get("username_footprint")).get("error"):
        lines.append("### 跨平台身份（用户名公开足迹）")
        if footprint.get("platforms_found"):
            lines.append(
                f"- 命中公开平台: {footprint.get('platforms_found')} 个"
                + (f"（覆盖率 {footprint.get('coverage_ratio')}）"
                   if footprint.get("coverage_ratio") else "")
            )
        by_category = _dict(footprint.get("by_category"))
        shown = 0
        for category, plats in by_category.items():
            if shown >= 6:
                break
            names = [str(x) for x in _list(plats)[:8] if str(x).strip()]
            if names:
                lines.append(f"- {category}: {'; '.join(_short(n, 40) for n in names)}")
                shown += 1
        meta = _dict(footprint.get("profile_metadata") or footprint.get("metadata"))
        for key, label in (("bio", "简介"), ("location", "地点"),
                           ("blog", "博客"), ("company", "公司")):
            if meta.get(key):
                lines.append(f"- {label}: {_short(meta.get(key), 120)}")
    # 交叉印证
    corroborations = [c for c in _list(p.get("corroborations")) if isinstance(c, dict)]
    if corroborations:
        lines.append("### 交叉印证（仅为线索，不做身份断言）")
        for c in corroborations[:8]:
            lines.append(f"- 🔗 {_short(c.get('detail'), 200)}")
    if p.get("policy"):
        lines.append(f"- 口径: {_short(p.get('policy'), 180)}")
    return lines


def _people_profile_lines(sources: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    def _source_block(key: str) -> tuple[dict[str, Any], dict[str, Any]]:
        raw = _dict(sources.get(key))
        return raw, _dict(raw.get("fields"))

    # email_intel
    raw, fields = _source_block("email_intel")
    if raw.get("error"):
        lines.append(f"- 邮箱情报: 数据源失败（{_short(raw.get('error'), 80)}）")
    elif fields:
        bits = []
        if fields.get("domain"):
            bits.append(f"域名 {fields.get('domain')}")
        if fields.get("is_disposable"):
            bits.append("⚠️一次性邮箱（标识可信度低）")
        if fields.get("is_role_account"):
            bits.append("角色账号（非个人）")
        if fields.get("mx_valid") is not None:
            bits.append(f"MX {'有效' if fields.get('mx_valid') else '无效'}")
        if bits:
            lines.append(f"- 邮箱情报: {'；'.join(bits)}")
    # github_deep
    raw, fields = _source_block("github_deep")
    if raw.get("error"):
        lines.append(f"- GitHub 画像: 数据源失败（{_short(raw.get('error'), 80)}）")
    elif fields:
        profile = _dict(fields.get("profile"))
        bits = []
        for key, label in (("login", "账号"), ("name", "昵称"),
                           ("company", "公司"), ("location", "地点"),
                           ("blog", "博客")):
            if profile.get(key):
                bits.append(f"{label} {_short(profile.get(key), 60)}")
        for key, label in (("public_repos", "公开仓库"),
                           ("followers", "粉丝"), ("following", "关注")):
            if profile.get(key) is not None:
                bits.append(f"{label} {profile.get(key)}")
        aff = _dict(fields.get("affiliations"))
        orgs = [str(o.get("login")) for o in _list(aff.get("orgs"))[:5]
                if isinstance(o, dict) and o.get("login")]
        if orgs:
            bits.append(f"公开组织: {'; '.join(orgs)}")
        if bits:
            lines.append(f"- GitHub 画像: {'；'.join(bits)}")
    # officer_records
    raw, fields = _source_block("officer_records")
    if raw.get("error"):
        lines.append(f"- 任职记录: 数据源失败（{_short(raw.get('error'), 80)}）")
    elif fields:
        samples = [s for s in _list(fields.get("samples"))[:3] if isinstance(s, dict)]
        if samples:
            names = "; ".join(_short(s.get("company_name"), 50)
                              for s in samples if s.get("company_name"))
            if names:
                lines.append(f"- 任职记录: {names}")
                if fields.get("total") is not None:
                    lines[-1] += f"（共 {fields.get('total')} 条）"
        elif fields.get("total") == 0:
            lines.append("- 任职记录: 无公开任职记录")
    # social_listening
    raw, fields = _source_block("social_listening")
    if raw.get("error"):
        lines.append(f"- 社交聆听: 数据源失败（{_short(raw.get('error'), 80)}）")
    elif fields:
        summary = fields.get("summary") or fields.get("note")
        if summary:
            lines.append(f"- 社交聆听: {_short(summary, 160)}")
    # dev_* adapters
    for key in sorted(sources.keys()):
        if not key.startswith("dev_"):
            continue
        raw = _dict(sources.get(key))
        fields = _dict(raw.get("fields"))
        label = key[4:]
        if raw.get("error"):
            continue
        hit = fields.get("found") or fields.get("hit") or fields.get("username")
        if hit is not None and hit is not False:
            lines.append(f"- 开发者足迹 {label}: {_short(hit if isinstance(hit, str) else fields.get('profile_url') or '命中', 120)}")
    return lines


def _association_markdown(p: dict[str, Any]) -> list[str]:
    entities = p.get("entities")
    entity_list = list(entities.values()) if isinstance(entities, dict) else _list(entities)
    associations = [a for a in _list(p.get("associations")) if isinstance(a, dict)]
    patterns = [x for x in _list(p.get("interesting_patterns")) if isinstance(x, dict)]
    risk = _dict(p.get("risk_scores"))
    ranked = [r for r in _list(risk.get("ranked")) if isinstance(r, dict)]
    if not entity_list and not associations and not patterns and not ranked:
        return []
    seed = _dict(p.get("seed"))
    lines = ["## 情报富化 · 实体关联发现"]
    lines.append(
        f"- 种子: {seed.get('type') or '?'} = {_short(seed.get('value'), 80)}"
        f" | 实体 {len(entity_list)} 个 | 关联 {len(associations)} 条"
        f" | 证据分级: {_LEAD_BADGE}"
    )
    if patterns:
        lines.append("### 关联模式（疑似，需复核）")
        for pat in patterns[:8]:
            ptype = pat.get("pattern_type") or pat.get("type") or "pattern"
            lines.append(
                f"- [{ptype}] {_short(pat.get('detail') or pat.get('description'), 200)}"
                + (f"（置信度 {pat.get('confidence')}）" if pat.get("confidence") else "")
            )
    if associations:
        lines.append("### 关联关系（抽样）")
        for a in associations[:10]:
            src = _short(a.get("from") or a.get("source") or a.get("entity_a"), 50)
            dst = _short(a.get("to") or a.get("target") or a.get("entity_b"), 50)
            rel = a.get("relation") or a.get("type") or "关联"
            conf = f"（置信度 {a.get('confidence')}）" if a.get("confidence") else ""
            lines.append(f"- {src} —[{rel}]→ {dst}{conf}")
    if ranked:
        lines.append("### 风险评分（Top）")
        for r in ranked[:5]:
            lines.append(
                f"- {_short(r.get('display') or r.get('entity'), 80)}"
                f" | {r.get('score', '?')} 分"
                + (f" | {r.get('level')}" if r.get("level") else "")
            )
        if risk.get("disclaimer"):
            lines.append(f"- 口径: {_short(risk.get('disclaimer'), 160)}")
    if p.get("disclaimer"):
        lines.append(f"- 口径: {_short(p.get('disclaimer'), 200)}")
    return lines


_CONTACT_TYPE_LABELS = {
    "mobile": "手机", "phone": "电话", "tel": "固话", "qq": "QQ",
    "wechat": "微信", "email": "邮箱", "weibo": "微博", "douyin": "抖音",
}


def _contacts_markdown(p: dict[str, Any]) -> list[str]:
    contacts = [c for c in _list(p.get("contacts")) if isinstance(c, dict)]
    if not contacts:
        return []
    lines = ["## 情报富化 · 联系方式提取"]
    lines.append(
        f"- 提取 {len(contacts)} 个联系方式（来自公开文本挖掘）"
        f" | 证据分级: {_LEAD_BADGE}"
    )
    for c in contacts[:15]:
        ctype = str(c.get("type") or "")
        label = _CONTACT_TYPE_LABELS.get(ctype, ctype or "未知")
        conf = f"（置信度 {c.get('confidence')}）" if c.get("confidence") else ""
        srcs = c.get("sources")
        src_text = ""
        if isinstance(srcs, list) and srcs:
            src_text = f" | 来源: {'; '.join(_short(s, 40) for s in srcs[:3])}"
        lines.append(f"- {label}: `{_short(c.get('value'), 60)}`{conf}{src_text}")
    summary = _dict(p.get("summary"))
    if summary.get("note"):
        lines.append(f"- 说明: {_short(summary.get('note'), 160)}")
    return lines


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def render_enrichment_html(payload: dict[str, Any]) -> str:
    """Render one enrichment payload as an HTML visual-panel fragment."""
    kind = payload_kind(payload)
    if kind == "domain":
        return _domain_html(_dict(payload))
    if kind == "people":
        return _people_html(_dict(payload))
    if kind == "association":
        return _association_html(_dict(payload))
    if kind == "contacts":
        return _contacts_html(_dict(payload))
    return ""


def render_enrichments_html(payloads: list[dict[str, Any]]) -> str:
    parts = []
    for payload in payloads or []:
        fragment = render_enrichment_html(payload)
        if fragment:
            parts.append(fragment)
    return "\n".join(parts)


def _esc(value: Any) -> str:
    return _html.escape(_short(value, 200), quote=True)


def _metric(label: str, value: Any) -> str:
    return (
        f"<div><b>{_html.escape(_short(value, 60), quote=True)}</b>"
        f"<span>{_html.escape(label, quote=True)}</span></div>"
    )


def _table_row(cells: list[str], header: bool = False) -> str:
    tag = "th" if header else "td"
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def _domain_html(p: dict[str, Any]) -> str:
    sources = _dict(p.get("sources"))
    if not sources and not _list(p.get("risk_notes")):
        return ""
    domain = _short(p.get("domain"))
    rows: list[str] = []
    urlscan = _dict(_dict(sources.get("urlscan")).get("fields"))
    if urlscan and not _dict(sources.get("urlscan")).get("error"):
        rows.append(_table_row(["urlscan 扫描记录", str(urlscan.get("total_scans", 0)) + " 条"]))
        for scan in _list(urlscan.get("recent_scans"))[:3]:
            if not isinstance(scan, dict):
                continue
            link = ""
            if scan.get("result_url"):
                link = (f" <a href=\"{_html.escape(str(scan['result_url']), quote=True)}\""
                        f" target=\"_blank\" rel=\"noopener\">来源</a>")
            rows.append(_table_row([
                _esc(scan.get("scanned_url")),
                f"{_esc(scan.get('scan_date'))} | {_esc(scan.get('page_title'))}{link}",
            ]))
    ht = _dict(_dict(sources.get("hackertarget")).get("fields"))
    if ht and not _dict(sources.get("hackertarget")).get("error"):
        a_records = [str(x) for x in _list(_dict(ht.get("records")).get("A"))[:3]]
        if a_records:
            rows.append(_table_row(["A 记录", _html.escape("; ".join(a_records), quote=True)]))
        neighbor_count = _dict(ht.get("reverseiplookup")).get("neighbor_count")
        if isinstance(neighbor_count, int):
            rows.append(_table_row(["同 IP 邻居域名", f"{neighbor_count} 个（共享主机线索）"]))
    ipf = _dict(_dict(sources.get("ipapi")).get("fields"))
    if ipf and not _dict(sources.get("ipapi")).get("error"):
        geo = " / ".join(x for x in (
            _short(ipf.get("country")), _short(ipf.get("city"))) if x)
        if geo:
            rows.append(_table_row(["IP 地理", _html.escape(geo, quote=True)]))
        org = _short(ipf.get("org"), 80)
        if org:
            rows.append(_table_row(["组织/ASN", _html.escape(org, quote=True)]))
        flags = []
        if ipf.get("is_hosting") is True:
            flags.append("托管机房")
        if ipf.get("is_proxy") is True:
            flags.append("疑似代理出口")
        if flags:
            rows.append(_table_row(["标记", _html.escape("；".join(flags), quote=True)]))
    notes = [str(x).strip() for x in _list(p.get("risk_notes")) if str(x).strip()][:6]
    notes_html = ""
    if notes:
        items = "".join(f"<li>⚠️ {_html.escape(_short(n, 160), quote=True)}（线索，非断言）</li>"
                        for n in notes)
        notes_html = f"<ul>{items}</ul>"
    policy = _html.escape(_short(p.get("policy"), 180), quote=True) if p.get("policy") else ""
    return (
        "<section class=\"visual-panel\" aria-label=\"情报富化：域名基础设施\">\n"
        "  <h2>情报富化 · 域名基础设施</h2>\n"
        "  <div class=\"metric-strip\">\n"
        f"    {_metric('目标域名', domain)}\n"
        f"    {_metric('数据源', p.get('source_count', len(sources)))}\n"
        f"    {_metric('证据分级', 'lead · 线索')}\n"
        "  </div>\n"
        f"  <table>{_table_row(['项目', '详情'], header=True)}{''.join(rows)}</table>\n"
        f"  {notes_html}\n"
        + (f"  <p class=\"premium-copy\">口径：{policy}</p>\n" if policy else "")
        + "</section>\n"
    )


def _people_html(p: dict[str, Any]) -> str:
    sources = _dict(p.get("sources"))
    if not sources and not _list(p.get("corroborations")) and not p.get("note"):
        return ""
    provided = _dict(p.get("identifiers_provided"))
    marks = " ".join(
        f"{label}{'✓' if provided.get(key) else '–'}"
        for key, label in (("name", "姓名"), ("email", "邮箱"),
                           ("username", "用户名"), ("github_username", "GitHub"))
    ) if provided else "未记录"
    rows: list[str] = []
    # 画像摘要
    for line in _people_profile_lines(sources)[:10]:
        text = line[2:] if line.startswith("- ") else line
        if ":" in text or "：" in text:
            label, _, rest = text.replace("：", ":").partition(":")
            rows.append(_table_row([_html.escape(_short(label, 30), quote=True),
                                    _html.escape(_short(rest, 160), quote=True)]))
        else:
            rows.append(_table_row([_html.escape(_short(text, 160), quote=True), ""]))
    # 跨平台身份
    footprint = _dict(_dict(sources.get("username_footprint")).get("fields"))
    if footprint and not _dict(sources.get("username_footprint")).get("error"):
        if footprint.get("platforms_found"):
            rows.append(_table_row([
                "用户名公开足迹",
                _html.escape(f"{footprint.get('platforms_found')} 个平台"
                             + (f"（覆盖率 {footprint.get('coverage_ratio')}）"
                                if footprint.get("coverage_ratio") else ""), quote=True),
            ]))
    # 交叉印证
    notes = [c for c in _list(p.get("corroborations")) if isinstance(c, dict)][:6]
    notes_html = ""
    if notes:
        items = "".join(
            f"<li>🔗 {_html.escape(_short(c.get('detail'), 200), quote=True)}（线索，非断言）</li>"
            for c in notes)
        notes_html = f"<ul>{items}</ul>"
    if p.get("note") and not sources:
        notes_html += f"<p class=\"premium-copy\">{_html.escape(_short(p.get('note'), 200), quote=True)}</p>"
    policy = _html.escape(_short(p.get("policy"), 180), quote=True) if p.get("policy") else ""
    return (
        "<section class=\"visual-panel\" aria-label=\"情报富化：人物公开情报\">\n"
        "  <h2>情报富化 · 人物公开情报</h2>\n"
        "  <div class=\"metric-strip\">\n"
        f"    {_metric('已提供标识', marks)}\n"
        f"    {_metric('数据源', p.get('source_count', len(sources)))}\n"
        f"    {_metric('证据分级', 'lead · 线索')}\n"
        "  </div>\n"
        + (f"  <table>{_table_row(['画像维度', '摘要'], header=True)}{''.join(rows)}</table>\n" if rows else "")
        + f"  {notes_html}\n"
        + (f"  <p class=\"premium-copy\">口径：{policy}</p>\n" if policy else "")
        + "</section>\n"
    )


def _association_html(p: dict[str, Any]) -> str:
    entities = p.get("entities")
    entity_list = list(entities.values()) if isinstance(entities, dict) else _list(entities)
    associations = [a for a in _list(p.get("associations")) if isinstance(a, dict)]
    patterns = [x for x in _list(p.get("interesting_patterns")) if isinstance(x, dict)]
    ranked = [r for r in _list(_dict(p.get("risk_scores")).get("ranked")) if isinstance(r, dict)]
    if not entity_list and not associations and not patterns and not ranked:
        return ""
    seed = _dict(p.get("seed"))
    rows: list[str] = []
    for pat in patterns[:6]:
        ptype = pat.get("pattern_type") or pat.get("type") or "pattern"
        rows.append(_table_row([
            _html.escape(f"[{_short(ptype, 30)}] 疑似模式", quote=True),
            _html.escape(_short(pat.get("detail") or pat.get("description"), 160), quote=True),
        ]))
    for a in associations[:8]:
        src = _short(a.get("from") or a.get("source") or a.get("entity_a"), 40)
        dst = _short(a.get("to") or a.get("target") or a.get("entity_b"), 40)
        rel = a.get("relation") or a.get("type") or "关联"
        rows.append(_table_row([
            _html.escape(f"{src} —[{_short(rel, 30)}]→ {dst}", quote=True),
            _html.escape(f"置信度 {a.get('confidence')}" if a.get("confidence") else "线索", quote=True),
        ]))
    for r in ranked[:5]:
        rows.append(_table_row([
            _html.escape(f"风险评分：{_short(r.get('display') or r.get('entity'), 60)}", quote=True),
            _html.escape(f"{r.get('score', '?')} 分" + (f" | {r.get('level')}" if r.get("level") else ""), quote=True),
        ]))
    disclaimer = _html.escape(_short(p.get("disclaimer"), 200), quote=True) if p.get("disclaimer") else ""
    return (
        "<section class=\"visual-panel\" aria-label=\"情报富化：实体关联发现\">\n"
        "  <h2>情报富化 · 实体关联发现</h2>\n"
        "  <div class=\"metric-strip\">\n"
        f"    {_metric('种子', f"{seed.get('type') or '?'}={_short(seed.get('value'), 30)}")}\n"
        f"    {_metric('实体', len(entity_list))}\n"
        f"    {_metric('关联', len(associations))}\n"
        f"    {_metric('证据分级', 'lead · 线索')}\n"
        "  </div>\n"
        f"  <table>{_table_row(['发现', '详情'], header=True)}{''.join(rows)}</table>\n"
        + (f"  <p class=\"premium-copy\">口径：{disclaimer}</p>\n" if disclaimer else "")
        + "</section>\n"
    )


def _contacts_html(p: dict[str, Any]) -> str:
    contacts = [c for c in _list(p.get("contacts")) if isinstance(c, dict)]
    if not contacts:
        return ""
    rows = []
    for c in contacts[:12]:
        ctype = str(c.get("type") or "")
        label = _CONTACT_TYPE_LABELS.get(ctype, ctype or "未知")
        rows.append(_table_row([
            _html.escape(label, quote=True),
            f"<code>{_html.escape(_short(c.get('value'), 60), quote=True)}</code>"
            + (_html.escape(f"（置信度 {c.get('confidence')}）", quote=True)
               if c.get("confidence") else ""),
        ]))
    return (
        "<section class=\"visual-panel\" aria-label=\"情报富化：联系方式提取\">\n"
        "  <h2>情报富化 · 联系方式提取</h2>\n"
        "  <div class=\"metric-strip\">\n"
        f"    {_metric('提取数量', len(contacts))}\n"
        f"    {_metric('证据分级', 'lead · 线索')}\n"
        "  </div>\n"
        f"  <table>{_table_row(['类型', '值'], header=True)}{''.join(rows)}</table>\n"
        "  <p class=\"premium-copy\">来自公开文本挖掘的联系方式，仅为线索，需核验后使用。</p>\n"
        "</section>\n"
    )
