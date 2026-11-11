#!/usr/bin/env python3
"""GLEIF 全球法人机构识别编码（LEI）关联适配器。

回答："这家企业在全球 LEI 体系里是谁？它的母公司/子公司是谁？"

GLEIF (Global Legal Entity Identifier Foundation) 运营全球 LEI 数据库，
免费公开 API，无需 key。LEI 是 ISO 17442 标准的 20 位编码，
全球 200+ 万法人实体注册。

核心 OSINT 动作 — 跨国关联 pivoting：
    企业名 --(LEI 查询)--> LEI 记录（注册地址/管辖区/状态）
            --(direct-child-relationships)--> 子公司 LEI 列表
            --(ultimate-parent)--> 最终母公司

Endpoint: GET https://api.gleif.org/api/v1/lei-records
    ?filter[entity.legalName]=<name>&page[size]=<n>
    公开、无需认证、无 key。JSON:API 格式。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。

注意：
    GLEIF 主要覆盖有跨境业务/发债/金融交易的大中型企业，
    中小企业和个体工商户通常没有 LEI。查不到 ≠ 不存在，
    只是该主体未注册 LEI。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


def _fmt_address(addr: dict[str, Any] | None) -> str:
    """把 GLEIF 地址结构拼成可读字符串。"""
    if not isinstance(addr, dict):
        return ""
    parts: list[str] = []
    lines = addr.get("addressLines") or []
    if isinstance(lines, list):
        parts.extend(str(x) for x in lines if x)
    for key in ("city", "region", "postalCode", "country"):
        v = addr.get(key)
        if v:
            parts.append(str(v))
    return ", ".join(parts)


def _parse_lei_record(rec: dict[str, Any]) -> dict[str, Any]:
    """解析单条 lei-record → 公开字段。"""
    attrs = rec.get("attributes") or {}
    entity = attrs.get("entity") or {}
    reg = attrs.get("registration") or {}
    legal_name_obj = entity.get("legalName") or {}
    legal_name = legal_name_obj.get("name", "") if isinstance(legal_name_obj, dict) else str(legal_name_obj)

    # 其他曾用名
    other_names: list[str] = []
    for on in entity.get("otherNames") or []:
        if isinstance(on, dict):
            n = on.get("name")
            if n:
                other_names.append(str(n))

    out: dict[str, Any] = {
        "lei": attrs.get("lei", ""),
        "legal_name": legal_name,
        "other_names": other_names[:10],
        "jurisdiction": entity.get("jurisdiction", ""),
        "legal_form": (entity.get("legalForm") or {}).get("id", ""),
        "category": entity.get("category", ""),
        "status": entity.get("status", ""),
        "legal_address": _fmt_address(entity.get("legalAddress")),
        "hq_address": _fmt_address(entity.get("headquartersAddress")),
        "registered_as": entity.get("registeredAs", ""),
        "creation_date": (entity.get("creationDate") or "")[:10],
        "registration_status": reg.get("status", ""),
        "managing_lou": reg.get("managingLou", ""),
    }
    return out


def _parse_relationship_record(rec: dict[str, Any]) -> dict[str, Any]:
    """解析 relationship-record → 父子关联。"""
    attrs = rec.get("attributes") or {}
    rel = attrs.get("relationship") or {}
    start = (rel.get("startNode") or {}).get("id", "")
    end = (rel.get("endNode") or {}).get("id", "")
    return {
        "child_lei": start,
        "parent_lei": end,
        "type": rel.get("type", ""),
        "status": rel.get("status", ""),
    }


class GleifLookup(SafeResearchAdapter):
    """GLEIF LEI 查询：企业名 → LEI 记录 → 母子公司关联。"""

    source_domain = "api.gleif.org"
    source_type = "global_entity_registry"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        name = keyword.strip()
        size = int(params.get("page_size") or 10)
        size = max(1, min(size, 50))
        qs = urllib.parse.urlencode({
            "filter[entity.legalName]": name,
            "page[size]": size,
        })
        return "https://api.gleif.org/api/v1/lei-records?" + qs

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public GLEIF LEI query)",
            "Accept": "application/vnd.api+json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True, "data_note": "unexpected response shape"}
        if "errors" in data:
            errs = data["errors"]
            detail = ""
            if isinstance(errs, list) and errs:
                detail = str(errs[0].get("detail") or errs[0].get("title") or "")[:120]
            return {"lookup_failed": True, "reason": detail}

        records = data.get("data") or []
        entities = [_parse_lei_record(r) for r in records if isinstance(r, dict)]
        pagination = ((data.get("meta") or {}).get("pagination")) or {}
        total = pagination.get("total", len(entities))

        return {
            "entity_count": len(entities),
            "total_matches": total,
            "entities": entities,
            "data_note": (
                "GLEIF 全球 LEI 公开数据库 — 母子公司关联仅作线索，"
                "中小企业/个体户通常无 LEI 记录，查不到不代表不存在"
            ),
        }

    def query_children(self, lei: str) -> dict[str, Any]:
        """查某 LEI 的直接子公司关联（direct-child-relationships）。

        返回子公司 LEI 列表（关联线索，需再调 query(lei) 取详情）。
        """
        lei = (lei or "").strip().upper()
        if not lei or len(lei) != 20:
            return {"error": "LEI 必须为 20 位编码", "fields": {}}
        self._enforce_rate_limit()
        url = f"https://api.gleif.org/api/v1/lei-records/{urllib.parse.quote(lei)}/direct-child-relationships"
        status, raw, err = self._execute_query(url, self._build_headers())
        self._record_audit(keyword=lei, url=url, status=status, fields=["child_relationships"])
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            return {"lei": lei, "fields": {"parse_error": True}, "error": err}
        if isinstance(data, dict) and "errors" in data:
            return {"lei": lei, "fields": {"child_relationships": [], "child_count": 0},
                    "error": "无子公司关联记录或 LEI 不存在"}
        recs = data.get("data") or []
        rels = [_parse_relationship_record(r) for r in recs if isinstance(r, dict)]
        return {
            "lei": lei,
            "fields": {
                "child_relationships": rels,
                "child_count": len(rels),
                "child_leis": [r["child_lei"] for r in rels if r["child_lei"]],
            },
            "error": err,
        }

    def query_parent(self, lei: str) -> dict[str, Any]:
        """查某 LEI 的直接母公司（direct-parent）。无数据时返回 reporting-exception 说明。"""
        lei = (lei or "").strip().upper()
        if not lei or len(lei) != 20:
            return {"error": "LEI 必须为 20 位编码", "fields": {}}
        self._enforce_rate_limit()
        # 先试 direct-parent 关联端点
        url = f"https://api.gleif.org/api/v1/lei-records/{urllib.parse.quote(lei)}/direct-parent"
        status, raw, err = self._execute_query(url, self._build_headers())
        self._record_audit(keyword=lei, url=url, status=status, fields=["direct_parent"])
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            return {"lei": lei, "fields": {"parse_error": True}, "error": err}
        if isinstance(data, dict) and "errors" in data:
            # 无母公司数据 → 查 reporting-exception 说明原因
            exc_url = f"https://api.gleif.org/api/v1/lei-records/{urllib.parse.quote(lei)}/direct-parent-reporting-exception"
            self._enforce_rate_limit()
            s2, raw2, err2 = self._execute_query(exc_url, self._build_headers())
            reason = ""
            try:
                d2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or {})
                dd = (d2.get("data") or {})
                reason = str(((dd.get("attributes") or {}).get("reason")) or "")[:200]
            except Exception:
                reason = ""
            return {"lei": lei,
                    "fields": {"direct_parent_lei": "", "no_parent_reason": reason or "未申报母公司"},
                    "error": err2 or ""}
        rec = (data.get("data") or {})
        attrs = rec.get("attributes") or {}
        return {"lei": lei,
                "fields": {"direct_parent_lei": attrs.get("lei", ""),
                           "direct_parent_name": ((attrs.get("entity") or {}).get("legalName") or {}).get("name", "")},
                "error": err}
