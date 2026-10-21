#!/usr/bin/env python3
"""Entity Association Engine.

Cross-source entity association for offline-business / people due diligence:
seed (phone | address | business_name | person_name | email)
  -> fan-out to offline-business lane adapters
  -> extract entities (business / person / phone / address / email)
  -> build association graph
  -> detect interesting patterns

Design rules (per project house rules):
- Adapters are INJECTED, never constructed here: the caller decides what is
  enabled. Nothing runs by default.
- Every adapter failure degrades to a per-source error entry; one source
  never breaks the whole investigation.
- Associations are *leads* ("same phone seen at two POIs"), never identity
  assertions. A shared phone/address suggests a relationship; it does not
  prove common ownership.
- Public data only. All values come from public sources (map POI listings,
  public shop pages, public social profiles, public court records, public
  WeChat articles). The engine does NOT mask or redact publicly obtained
  contact info -- masking public listings would destroy the association
  signal this module exists to produce.
- No credentials, no login, no CAPTCHA bypass. Adapters that need
  interaction return interaction_required and are skipped in fan-out.

Phone normalization (Chinese numbers):
- Strip spaces, dashes, parentheses, dots.
- Strip country prefixes: +86 / 86 / 0086.
- Mobile: 11 digits starting with 1 -> canonical 11-digit string.
- Landline: 0 + 2-3 digit area code + 7-8 digit number, optional ext.
- Multi-number fields split on ;, 、, /, whitespace.

Address normalization:
- match_key: strip whitespace; drop floor/room/unit suffixes; keep street
  number. Masked addresses (with * chars) are kept for display but
  excluded from matching -- a masked address cannot corroborate identity.
- display: original string, unmodified.

Name normalization: strip whitespace; exact match only.
"""

from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

try:
    from core.temporal_analysis import analyze_temporal_clusters
    _HAS_TEMPORAL = True
except ImportError:
    _HAS_TEMPORAL = False


_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")
_LANDLINE_RE = re.compile(r"^0\d{2,3}\d{7,8}(?:\d{1,6})?$")
_MOBILE_FIND_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_FIND_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def normalize_phone(raw: Any) -> str:
    """Canonical phone digits, or '' if not a plausible phone number."""
    if not raw:
        return ""
    s = str(raw).strip()
    s = re.split(r"(?:转|ext|EXT|分机)", s)[0]
    digits = re.sub(r"\D", "", s)
    if digits.startswith("0086"):
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    if _MOBILE_RE.match(digits):
        return digits
    if _LANDLINE_RE.match(digits):
        return digits
    return ""


def split_phones(raw: Any) -> list[str]:
    """Split a multi-number field into canonical phones (deduped, ordered)."""
    if not raw:
        return []
    parts = re.split(r"[;；、/／,，|｜\s]+", str(raw))
    out: list[str] = []
    for p in parts:
        n = normalize_phone(p)
        if n and n not in out:
            out.append(n)
    return out


def extract_phones_from_text(text: Any) -> list[str]:
    """Find phone numbers inside free text (bios, article summaries)."""
    if not text:
        return []
    t = str(text)
    out: list[str] = []
    for m in _MOBILE_FIND_RE.finditer(t):
        n = normalize_phone(m.group(0))
        if n and n not in out:
            out.append(n)
    for m in re.finditer(r"(?:\(0(\d{2,3})\)|0(\d{2,3}))[-\s]?(\d{7,8})", t):
        area = m.group(1) or m.group(2)
        n = normalize_phone("0" + area + m.group(3))
        if n and n not in out:
            out.append(n)
    return out


def extract_emails_from_text(text: Any) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in _EMAIL_FIND_RE.finditer(str(text)):
        e = m.group(0).lower()
        if e not in out:
            out.append(e)
    return out


def normalize_address(raw: Any) -> tuple[str, str]:
    """Return (match_key, display). match_key '' means not matchable."""
    if not raw:
        return "", ""
    display = str(raw).strip()
    if not display or len(display) < 4:
        return "", display
    if re.search(r"[*＊×xX]{2,}", display):
        return "", display
    key = re.sub(r"\s+", "", display)
    key = re.sub(r"\d+\s*(?:层|楼)", "", key)
    key = re.sub(r"(\d+室|\d+房|-\d{2,}|[A-Z]座)", "", key)
    key = key.rstrip("-")
    if len(key) < 6:
        return "", display
    return key, display


def normalize_name(raw: Any) -> str:
    if not raw:
        return ""
    s = re.sub(r"\s+", "", str(raw)).strip("【】[]()（）\"'“”")
    return s


def entity_id(entity_type: str, normalized_value: str) -> str:
    return hashlib.sha256(
        ("{}:{}".format(entity_type, normalized_value)).encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Entity extractors (per source result shape)
# ---------------------------------------------------------------------------

def _poi_entities(poi: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Extract entities from an amap/baidu POI record."""
    ents: list[dict[str, Any]] = []
    name = normalize_name(poi.get("name"))
    if name:
        ents.append({
            "type": "business", "value": name,
            "display": str(poi.get("name", ""))[:80],
            "sources": [source],
            "context": {
                k: poi.get(k) for k in
                ("province", "city", "district", "area", "type", "tag")
                if poi.get(k)
            },
        })
    for ph in split_phones(poi.get("tel")):
        ents.append({
            "type": "phone", "value": ph, "display": ph,
            "sources": [source], "context": {"of_business": name},
        })
    addr_key, addr_display = normalize_address(poi.get("address"))
    if addr_display:
        ents.append({
            "type": "address", "value": addr_key or addr_display,
            "display": addr_display, "matchable": bool(addr_key),
            "sources": [source],
            "context": {
                "province": poi.get("province", ""),
                "city": poi.get("city") or poi.get("cityname", ""),
                "district": poi.get("district") or poi.get("adname", ""),
                "of_business": name,
            },
        })
    return ents


def _dianping_entities(shop: dict[str, Any], source: str) -> list[dict[str, Any]]:
    ents: list[dict[str, Any]] = []
    if not shop.get("shop_found"):
        return ents
    name = normalize_name(shop.get("shop_name"))
    if name:
        branch = normalize_name(shop.get("branch_name"))
        disp = "{}({})".format(name, branch) if branch else name
        ents.append({
            "type": "business", "value": name, "display": disp,
            "sources": [source],
            "context": {
                "shop_id": shop.get("shop_id", ""),
                "city": shop.get("city_name", ""),
                "region": shop.get("region_name", ""),
            },
        })
    for ph in split_phones(shop.get("phone")):
        ents.append({
            "type": "phone", "value": ph, "display": ph,
            "sources": [source], "context": {"of_business": name},
        })
    addr_key, addr_display = normalize_address(shop.get("address"))
    if addr_display:
        ents.append({
            "type": "address", "value": addr_key or addr_display,
            "display": addr_display, "matchable": bool(addr_key),
            "sources": [source], "context": {"of_business": name},
        })
    return ents


def _douyin_entities(result: dict[str, Any], source: str) -> list[dict[str, Any]]:
    ents: list[dict[str, Any]] = []
    fields = result.get("fields") or {}
    profile = fields.get("profile") or {}
    if not profile:
        return ents
    nick = normalize_name(profile.get("nickname"))
    if nick:
        ents.append({
            "type": "business", "value": nick, "display": nick,
            "sources": [source],
            "context": {
                "douyin_id": profile.get("douyin_id", ""),
                "enterprise_verify": bool(profile.get("enterprise_verify")),
                "verify_reason": str(profile.get("verify_reason", ""))[:80],
                "follower_count": profile.get("follower_count"),
            },
        })
    sig = str(profile.get("signature", "") or "")
    for ph in extract_phones_from_text(sig):
        ents.append({
            "type": "phone", "value": ph, "display": ph,
            "sources": [source],
            "context": {"from": "douyin_signature", "of_account": nick},
        })
    for em in extract_emails_from_text(sig):
        ents.append({
            "type": "email", "value": em, "display": em,
            "sources": [source],
            "context": {"from": "douyin_signature", "of_account": nick},
        })
    for poi in fields.get("poi_list") or []:
        if not isinstance(poi, dict):
            continue
        pname = normalize_name(poi.get("poi_name"))
        if pname and pname != nick:
            ents.append({
                "type": "business", "value": pname, "display": pname,
                "sources": [source],
                "context": {"from": "douyin_video_poi", "account": nick},
            })
        akey, adisp = normalize_address(poi.get("poi_address"))
        if adisp:
            ents.append({
                "type": "address", "value": akey or adisp,
                "display": adisp, "matchable": bool(akey),
                "sources": [source],
                "context": {"from": "douyin_video_poi", "account": nick},
            })
    return ents


def _sogou_entities(article: dict[str, Any], source: str) -> list[dict[str, Any]]:
    ents: list[dict[str, Any]] = []
    text = "{} {}".format(article.get("title", ""), article.get("summary", ""))
    for ph in extract_phones_from_text(text):
        ents.append({
            "type": "phone", "value": ph, "display": ph,
            "sources": [source],
            "context": {
                "from": "wechat_article",
                "article_title": str(article.get("title", ""))[:60],
                "account": article.get("account", ""),
            },
        })
    for em in extract_emails_from_text(text):
        ents.append({
            "type": "email", "value": em, "display": em,
            "sources": [source],
            "context": {
                "from": "wechat_article",
                "article_title": str(article.get("title", ""))[:60],
            },
        })
    return ents


def _wenshu_entities(case: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """裁判文书当事人 -> person/business 实体.

    脱敏边界:文书网现行公开文书已做脱敏处理;本分支只提可公开字段
    (当事人姓名/名称、案号、文书标题),不抽取、不透传任何身份证号、
    住址、电话等敏感字段——即使上游 JSON 残留也不取.
    """
    ents: list[dict[str, Any]] = []
    parties = str(case.get("parties", "") or "")
    for chunk in re.split(r"[，,；;、]", parties):
        nm = re.sub(
            r"^(原告|被告|上诉人|被上诉人|申请人|被申请人|第三人|原审原告|原审被告)[:：\s]*",
            "", chunk).strip()
        nm = normalize_name(nm)
        if not nm or len(nm) > 12 or "法院" in nm:
            continue
        if "公司" in nm or "店" in nm or "厂" in nm:
            ents.append({
                "type": "business", "value": nm, "display": nm,
                "sources": [source],
                "context": {
                    "from": "court_case_party",
                    "case_number": case.get("case_number", ""),
                },
            })
        else:
            ents.append({
                "type": "person", "value": nm, "display": nm,
                "sources": [source],
                "context": {
                    "from": "court_case_party",
                    "case_number": case.get("case_number", ""),
                    "case_title": str(case.get("title", ""))[:60],
                },
            })
    return ents


def _court_notice_entities(notice: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """法院公告 -> 当事人实体 (与文书网互补:公告是程序性公开)."""
    ents: list[dict[str, Any]] = []
    parties = str(notice.get("parties", "") or "")
    for chunk in re.split(r"[，,；;、|]", parties):
        nm = normalize_name(chunk.strip())
        if not nm or len(nm) > 30 or "法院" in nm:
            continue
        if "公司" in nm or "店" in nm or "厂" in nm or "社" in nm:
            ents.append({
                "type": "business", "value": nm, "display": nm,
                "sources": [source],
                "context": {
                    "from": "court_notice_party",
                    "notice_type": notice.get("notice_type", ""),
                    "court": notice.get("court", ""),
                    "publish_date": notice.get("publish_date", ""),
                },
            })
        else:
            ents.append({
                "type": "person", "value": nm, "display": nm,
                "sources": [source],
                "context": {
                    "from": "court_notice_party",
                    "notice_type": notice.get("notice_type", ""),
                    "court": notice.get("court", ""),
                },
            })
    return ents


def _qcc_entities(profile: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """企查查公司 profile -> business 实体 + 法定代表人 person 实体。

    Expected record shape (adapters/qcc_waf_adapter.parse_firm_profile):
        {"company_name", "legal_rep", "capital", "founded", "status", ...}
    全部是 lead：context 标注来源与字段。
    """
    ents: list[dict[str, Any]] = []
    name = str(profile.get("company_name", "") or "").strip()
    if name:
        ents.append({
            "type": "business", "value": name, "display": name,
            "sources": [source],
            "context": {
                "from": "qcc_company_profile",
                "capital": profile.get("capital", ""),
                "founded": profile.get("founded", ""),
                "status": profile.get("status", ""),
                "page_title": profile.get("page_title", ""),
            },
        })
    rep = str(profile.get("legal_rep", "") or "").strip()
    if rep and name:
        ents.append({
            "type": "person", "value": rep, "display": rep,
            "sources": [source],
            "context": {
                "from": "qcc_legal_rep",
                "company": name,
            },
        })
    return ents


def _patent_entities(patent: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Google Patents 单条专利 -> 申请人(企业) + 发明人(个人).

    Expected record shape (adapters/patent_adapter._parse_patent_entry):
        {"publication_number", "title", "inventor", "assignee",
         "filing_date", "grant_date", ...}
    """
    ents: list[dict[str, Any]] = []
    assignee = normalize_name(patent.get("assignee"))
    pub_no = patent.get("publication_number", "")
    if assignee:
        ents.append({
            "type": "business", "value": assignee, "display": assignee,
            "sources": [source],
            "context": {
                "from": "patent_assignee",
                "publication_number": pub_no,
                "patent_title": str(patent.get("title", ""))[:80],
                "filing_date": patent.get("filing_date", ""),
            },
        })
    for chunk in re.split(r"[;；、]", str(patent.get("inventor") or "")):
        nm = normalize_name(chunk)
        if not nm or len(nm) > 30:
            continue
        ents.append({
            "type": "person", "value": nm, "display": nm,
            "sources": [source],
            "context": {
                "from": "patent_inventor",
                "company": assignee,
                "publication_number": pub_no,
                "patent_title": str(patent.get("title", ""))[:80],
            },
        })
    return ents


def _toutiao_entities(article: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """今日头条搜索文章 -> 作者(个人/自媒体账号).

    Expected record shape (ToutiaoSearchLookup.parse_search_dom):
        {"title", "url", "author", "publish_time"}
    """
    ents: list[dict[str, Any]] = []
    author = normalize_name(article.get("author"))
    if author and 2 <= len(author) <= 30:
        ents.append({
            "type": "person", "value": author, "display": author,
            "sources": [source],
            "context": {
                "from": "toutiao_author",
                "article_title": str(article.get("title", ""))[:80],
                "article_url": article.get("url", ""),
                "publish_time": article.get("publish_time", ""),
            },
        })
    return ents


def _gd_credit_entities(company: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """广东信用平台单条企业 -> 企业 + 法定代表人(个人) + 注册地址.

    Expected shapes (adapters/gd_credit_adapter):
        search:  {"company_name", "credit_code", "legal_rep", "address", "status", ...}
        detail:  {"found", "company_name", "credit_code", "legal_rep", "address",
                  "status", "registered_capital", "industry", ...}
    """
    ents: list[dict[str, Any]] = []
    name = normalize_name(company.get("company_name"))
    if not name:
        return ents
    ents.append({
        "type": "business", "value": name, "display": name,
        "sources": [source],
        "context": {
            "from": "gd_credit_company",
            "credit_code": company.get("credit_code", ""),
            "status": company.get("status", ""),
            "registered_capital": company.get("registered_capital", ""),
            "industry": company.get("industry", ""),
        },
    })
    rep = normalize_name(company.get("legal_rep"))
    if rep and 2 <= len(rep) <= 30:
        ents.append({
            "type": "person", "value": rep, "display": rep,
            "sources": [source],
            "context": {
                "from": "gd_credit_company",
                "company": name,
                "role": "法定代表人",
            },
        })
    akey, adisp = normalize_address(company.get("address"))
    if adisp:
        ents.append({
            "type": "address", "value": akey or adisp, "display": adisp,
            "matchable": bool(akey),
            "sources": [source],
            "context": {"from": "gd_credit_company", "of_business": name},
        })
    return ents


def _gleif_entities(record: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """GLEIF LEI 记录 -> 法人企业 (+曾用名企业).

    Expected record shape (adapters/gleif_adapter._parse_lei_record):
        {"lei", "legal_name", "other_names", "jurisdiction", "legal_form",
         "status", "legal_address", "hq_address", "registration_status", ...}
    母子公司关联在 _extract 的 gleif 分支中单独处理.
    """
    ents: list[dict[str, Any]] = []
    name = normalize_name(record.get("legal_name"))
    if not name:
        return ents
    ents.append({
        "type": "business", "value": name, "display": name,
        "sources": [source],
        "context": {
            "from": "gleif_lei_record",
            "lei": record.get("lei", ""),
            "jurisdiction": record.get("jurisdiction", ""),
            "legal_form": record.get("legal_form", ""),
            "entity_status": record.get("status", ""),
            "registration_status": record.get("registration_status", ""),
            "hq_address": record.get("hq_address", ""),
        },
    })
    for on in record.get("other_names") or []:
        onm = normalize_name(on)
        if onm and onm != name and 2 <= len(onm) <= 60:
            ents.append({
                "type": "business", "value": onm, "display": onm,
                "sources": [source],
                "context": {"from": "gleif_other_name", "of_legal_name": name},
            })
    return ents


def _customs_entities(party: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Zauba 海关进出口商 -> 企业.

    Expected shapes (adapters/customs_adapter):
        search party: {"name", "report_url", "shipment_count", "total_weight",
                       "latest_shipment"}
        detail also yields {"company_name", "address", "counterparties", ...}
    """
    ents: list[dict[str, Any]] = []
    name = normalize_name(party.get("name") or party.get("company_name"))
    if not name:
        return ents
    ents.append({
        "type": "business", "value": name, "display": name,
        "sources": [source],
        "context": {
            "from": "customs_party",
            "shipment_count": party.get("shipment_count"),
            "total_weight": party.get("total_weight", ""),
            "latest_shipment": party.get("latest_shipment", ""),
            "trade_category": party.get("category", ""),
            "report_url": party.get("report_url", ""),
        },
    })
    return ents


def _soft_copyright_entities(record: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """软著记录 -> 著作权人(企业).

    Expected record shape (知服服 ZhifufuSoftLookup / 聚合数据 JuheCopyrightLookup):
        {"soft_name", "reg_no", "owner", "reg_date", "version",
         "complete_date", "doc_id"}
    """
    ents: list[dict[str, Any]] = []
    owner = normalize_name(record.get("owner"))
    if not owner:
        return ents
    ents.append({
        "type": "business", "value": owner, "display": owner,
        "sources": [source],
        "context": {
            "from": "software_copyright_owner",
            "soft_name": str(record.get("soft_name", ""))[:80],
            "reg_no": record.get("reg_no", ""),
            "reg_date": record.get("reg_date", ""),
            "version": record.get("version", ""),
        },
    })
    return ents


def _weibo_relation_entities(user: dict[str, Any], source: str,
                             relation: str) -> list[dict[str, Any]]:
    """微博关注/粉丝单用户 -> username_profile + person.

    Expected record shape (adapters/weibo_relation_adapter._extract_user):
        {"id", "screen_name", "description", "profile_url", "verified",
         "verified_reason", "follow_me", "following", ...}
    """
    ents: list[dict[str, Any]] = []
    name = normalize_name(user.get("screen_name"))
    if not name or len(name) > 30:
        return ents
    ctx = {
        "from": "weibo_relation",
        "relation": relation,
        "weibo_uid": str(user.get("id") or ""),
        "profile_url": user.get("profile_url", ""),
        "verified": bool(user.get("verified")),
        "verified_reason": str(user.get("verified_reason", ""))[:120],
        # Unconventional association lane (2026-10-21): 互关判定
        "follow_me": bool(user.get("follow_me")),
        "following": bool(user.get("following")),
    }
    ents.append({
        "type": "username_profile", "value": name, "display": name,
        "sources": [source], "context": dict(ctx),
    })
    ents.append({
        "type": "person", "value": name, "display": name,
        "sources": [source], "context": dict(ctx),
    })
    return ents


def _dnsdumpster_entities(fields: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """DNSdumpster -> 子域名 domain 实体 + distinct IP 实体 (DNS 侦察)."""
    ents: list[dict[str, Any]] = []
    label_of: dict[str, str] = {}
    for i in (fields.get("interesting_subdomains") or []):
        if isinstance(i, dict) and i.get("host"):
            label_of[str(i["host"]).strip().lower()] = str(i.get("label", ""))
    for host in (fields.get("subdomains") or []):
        h = str(host or "").strip().lower()
        if not h:
            continue
        ctx: dict[str, Any] = {}
        if h in label_of:
            ctx["from"] = "interesting_subdomain"
            ctx["label"] = label_of[h]
        else:
            ctx["from"] = "dnsdumpster_subdomain"
        ents.append({
            "type": "domain", "value": h, "display": h,
            "sources": [source], "context": ctx,
        })
    for ip in (fields.get("distinct_ips") or []):
        ip_s = str(ip or "").strip()
        if not ip_s:
            continue
        ents.append({
            "type": "ip", "value": ip_s, "display": ip_s,
            "sources": [source],
            "context": {"from": "dnsdumpster_ip"},
        })
    return ents


def _commoncrawl_entities(fields: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Common Crawl -> 历史 URL 去重 host (domain 实体; seed 排除由引擎负责)."""
    ents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in (fields.get("urls") or []):
        if not isinstance(rec, dict):
            continue
        url = str(rec.get("url", "") or "")
        try:
            host = (urlparse(url).hostname or "").strip().lower()
        except Exception:
            host = ""
        if not host or host in seen:
            continue
        seen.add(host)
        ents.append({
            "type": "domain", "value": host, "display": host,
            "sources": [source],
            "context": {
                "from": "cc_url",
                "captured_at": rec.get("captured_at", ""),
            },
        })
    return ents


def _threatbook_entities(fields: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """微步 ThreatBook -> 域名当前解析 IP (ip 实体), ASN/判定进 context."""
    if fields.get("lookup_failed") or fields.get("no_data") or fields.get("parse_error"):
        return []
    ents: list[dict[str, Any]] = []
    asn = fields.get("asn") or {}
    ctx_base: dict[str, Any] = {"from": "threatbook_current_ip"}
    if isinstance(asn, dict):
        if asn.get("number"):
            ctx_base["asn_number"] = str(asn.get("number", ""))
        if asn.get("info"):
            ctx_base["asn_info"] = str(asn.get("info", ""))[:80]
    for key in ("severity", "is_malicious", "scene"):
        if fields.get(key) not in (None, ""):
            ctx_base[key] = fields.get(key)
    for ip in (fields.get("current_ips") or []):
        ip_s = str(ip or "").strip()
        if not ip_s:
            continue
        ents.append({
            "type": "ip", "value": ip_s, "display": ip_s,
            "sources": [source], "context": dict(ctx_base),
        })
    return ents


def _hunter_entities(fields: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Hunter.io -> 公开邮箱 (email 实体, 姓名/职位进 context)."""
    ents: list[dict[str, Any]] = []
    for e in (fields.get("emails") or []):
        if not isinstance(e, dict):
            continue
        addr = str(e.get("value", "") or "").strip().lower()
        if not addr or "@" not in addr:
            continue
        ctx: dict[str, Any] = {"from": "hunter_email"}
        for key in ("first_name", "last_name", "position", "seniority", "department"):
            v = e.get(key)
            if v:
                ctx[key] = v
        ents.append({
            "type": "email", "value": addr, "display": addr,
            "sources": [source], "context": ctx,
        })
    return ents


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_SEED_FANOUT: dict[str, list[str]] = {
    "phone": ["sogou_wx", "douyin", "amap", "baidu_map", "phone_mark", "telegram"],
    "address": ["amap", "baidu_map", "dianping", "douban"],
    "business_name": ["amap", "baidu_map", "dianping", "douyin", "sogou_wx", "wenshu", "corporate",
                      "icp_beian", "trademark", "weibo", "douban", "maimai", "telegram", "phone_mark",
                      "lagou", "zhaopin", "zhipin", "ccgp", "court_notice", "patent", "gd_credit",
                      "gleif", "customs", "software_copyright", "hibp_breach_catalog"],
    "person_name": ["wenshu", "sogou_wx", "douyin", "weibo", "maimai", "douban", "telegram", "phone_mark", "patent", "court_notice", "toutiao", "weibo_relation", "telegram_channel", "semanticscholar", "huggingface", "bilibili_user", "douban_user", "douyin_user", "xiaohongshu_user", "ens_lookup", "poap_lookup", "github_deep_extra", "keybase", "cninfo_kinship"],
    "email": ["sogou_wx", "douyin", "telegram", "pgp"],
    "domain": ["icp_beian", "cert_transparency", "crtsh_contact", "analytics_pivot", "sogou_wx", "fofa", "hunter", "commoncrawl", "dnsdumpster", "threatbook"],
    # Unconventional association lane (2026-10-21): repo -> contributors,
    # EVM address -> on-chain counterparties.
    "github_repo": ["github_contributors"],
    "evm_address": ["blockscout"],
}

_MAX_DEPTH2_FOLLOWUPS = 6


@dataclass
class EntityAssociationEngine:
    """Cross-source entity association engine.

    All adapters are injected (None = disabled). Nothing runs by default.
    """

    amap: Any = None
    baidu_map: Any = None
    dianping: Any = None
    douyin: Any = None
    sogou_wx: Any = None
    wenshu: Any = None
    court_notice: Any = None
    corporate: Any = None  # corporate role adapter: query(name) -> fields.corporate_records
    icp_beian: Any = None
    trademark: Any = None
    weibo: Any = None
    douban: Any = None
    maimai: Any = None
    telegram: Any = None
    telegram_channel: Any = None
    hibp_breach_catalog: Any = None
    huggingface: Any = None
    semanticscholar: Any = None  # academic lane: SemanticScholarLookup (no key)
    phone_mark: Any = None
    cert_transparency: Any = None
    analytics_pivot: Any = None
    fofa: Any = None
    whatsmyname: Any = None
    lagou: Any = None
    zhaopin: Any = None
    zhipin: Any = None
    ccgp: Any = None
    # New adapters (2026-10-21)
    patent: Any = None
    gleif: Any = None
    customs: Any = None
    software_copyright: Any = None
    juhe_copyright: Any = None
    hunter: Any = None
    toutiao: Any = None
    weibo_relation: Any = None
    commoncrawl: Any = None
    dnsdumpster: Any = None
    threatbook: Any = None
    gd_credit: Any = None
    # Social user lanes (2026-10-21): person-dimension adapters
    bilibili_user: Any = None
    douban_user: Any = None
    douyin_user: Any = None
    xiaohongshu_user: Any = None
    keybase: Any = None  # KeybaseIdentityLookup: username -> proofs + identity_deep (people-unconventional p2)
    # Unconventional association lane (2026-10-21): github repo -> contributors,
    # EVM address -> on-chain counterparties (both EXPERIMENTAL, default off)
    github_contributors: Any = None
    blockscout: Any = None
    # Unconventional identity lane (2026-10-21): PGP public key directory
    pgp: Any = None
    # Unconventional identity lane (2026-10-21): on-chain + git deep + cert contacts
    ens_lookup: Any = None  # ENSLookup: .eth name <-> address
    poap_lookup: Any = None  # POAPBadgeLookup: address -> attendance badges
    github_deep_extra: Any = None  # GitHubDeepExtra: commit emails + starred taste
    crtsh_contact: Any = None  # CrtshContactLookup: cert -> org names + contact emails
    cninfo_kinship: Any = None  # CninfoKinshipLookup: listed-company disclosure -> kinship statements (kinship lane 2026-10-21)
    max_workers: int = 4
    extra: dict[str, Any] = field(default_factory=dict)

    def associate(self, seed: dict[str, Any], max_depth: int = 2) -> dict[str, Any]:
        started = time.monotonic()
        seed_type = str(seed.get("type", "")).strip()
        seed_value = str(seed.get("value", "")).strip()
        if seed_type not in _SEED_FANOUT or not seed_value:
            return {
                "seed": seed, "entities": [], "associations": [],
                "interesting_patterns": [], "source_results": {},
                "error": "unsupported seed type: {!r}".format(seed_type),
                "duration_ms": 0,
            }

        source_results: dict[str, Any] = {}
        entities: dict[str, dict[str, Any]] = {}
        associations: list[dict[str, Any]] = []

        d1 = self._fanout(seed_type, seed_value, source_results)
        self._merge_entities(entities, d1["entities"])
        associations.extend(d1["associations"])

        if max_depth >= 2:
            d2 = self._depth2_followup(entities, source_results)
            self._merge_entities(entities, d2["entities"])
            associations.extend(d2["associations"])

        associations.extend(self._build_associations(entities))
        associations.extend(self._infer_family_control(entities))
        # 亲属关系 lane（2026-10-21）：披露/文书/自述的亲属关系升级为关联
        associations.extend(self._kinship_disclosure_associations(entities))
        associations.extend(self._resolve_person_identity(entities))
        # Extract contacts (QQ/WeChat/phone/email/UID) from entity contexts
        associations.extend(self._extract_entity_contacts(entities))
        patterns = self._detect_patterns(entities, associations)

        entity_list = sorted(entities.values(),
                             key=lambda e: (e["type"], e["value"]))
        # Temporal analysis: find time-based patterns
        if _HAS_TEMPORAL:
            try:
                temporal = analyze_temporal_clusters(entity_list)
                patterns.extend(temporal.get("patterns", []))
            except Exception:
                pass
        # Risk scoring: quantify patterns into a sortable risk ranking
        try:
            from core.risk_scorer import score_investigation as _score_inv
            risk_scores = _score_inv({
                "seed": {"type": seed_type, "value": seed_value},
                "entities": entity_list,
                "interesting_patterns": patterns,
                "associations": associations,
            })
        except Exception:
            risk_scores = {"ranked": [], "count": 0,
                           "disclaimer": "risk scoring unavailable"}
        return {
            "seed": {"type": seed_type, "value": seed_value},
            "entities": entity_list,
            "associations": self._dedupe_associations(associations),
            "interesting_patterns": patterns,
            "risk_scores": risk_scores,
            "source_results": source_results,
            "data_boundary": "fully_public",
            "disclaimer": (
                "All entities are extracted from public sources only. "
                "Associations are investigative leads, not identity assertions. "
                "Shared contact info suggests a possible relationship; "
                "it does not prove common ownership or control."
            ),
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }

    # -- fan-out ------------------------------------------------------

    def _fanout(self, seed_type: str, seed_value: str,
                source_results: dict[str, Any]) -> dict[str, Any]:
        jobs: list[tuple] = []
        for attr in _SEED_FANOUT[seed_type]:
            adapter = getattr(self, attr, None)
            if adapter is None:
                continue
            # person_name -> patent 走发明人定向检索 (inventor:"姓名"),
            # 而非默认 keyword 全字段检索,避免企业/标题同名噪音.
            # (2026-10-21 官方公示反查人 lane)
            kwargs = {"mode": "inventor"} \
                if (attr == "patent" and seed_type == "person_name") else {}
            jobs.append((attr, adapter, (seed_value,), kwargs))

        entities: list[dict[str, Any]] = []
        per_seed_assoc: list[dict[str, Any]] = []
        if not jobs:
            return {"entities": entities, "associations": per_seed_assoc}

        with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(jobs))) as ex:
            futs = {
                ex.submit(self._safe_call, attr, adapter, args, kwargs): attr
                for attr, adapter, args, kwargs in jobs
            }
            for fut in as_completed(futs):
                attr = futs[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"error": "{}: {}".format(type(e).__name__, e)}
                source_results[attr] = _summarize_result(result)
                if isinstance(result, dict) and not result.get("error") \
                        and not result.get("interaction_required") \
                        and not result.get("credentials_required"):
                    entities.extend(self._extract(attr, result))

        seed_eid = entity_id(seed_type, self._seed_norm(seed_type, seed_value))
        for e in entities:
            eid = entity_id(e["type"], e["value"])
            if eid == seed_eid:
                continue
            rel = self._seed_relation(seed_type, e["type"])
            if rel:
                per_seed_assoc.append({
                    "from": seed_eid, "to": eid, "relation": rel,
                    "strength": "strong",
                    "sources": sorted(set(e.get("sources", []))),
                    "note": "seed fan-out hit",
                })
        return {"entities": entities, "associations": per_seed_assoc}

    @staticmethod
    def _safe_call(attr: str, adapter: Any, args: tuple,
                   kwargs: dict) -> dict[str, Any]:
        try:
            if attr == "dianping":
                kw = str(args[0]).strip()
                if re.fullmatch(r"\d{4,}", kw) or "dianping.com/shop/" in kw:
                    return adapter.query_by_shop_id(kw)
                return adapter.query(kw, **kwargs)
            return adapter.query(*args, **kwargs)
        except Exception as e:
            return {"error": "{}: {}".format(type(e).__name__, e)}

    # -- depth 2 ------------------------------------------------------

    def _depth2_followup(self, entities: dict[str, dict[str, Any]],
                         source_results: dict[str, Any]) -> dict[str, Any]:
        followups: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for eid, e in entities.items():
            if len(followups) >= _MAX_DEPTH2_FOLLOWUPS:
                break
            if e["type"] == "phone" and self.sogou_wx is not None:
                key = ("sogou_wx", e["value"])
                if key not in seen:
                    seen.add(key)
                    followups.append(("sogou_wx", e["value"]))
            elif e["type"] == "address" and e.get("matchable"):
                for attr in ("amap", "baidu_map"):
                    if getattr(self, attr, None) is None:
                        continue
                    key = (attr, e["value"])
                    if key not in seen:
                        seen.add(key)
                        followups.append((attr, e["value"]))
                        break

        out_entities: list[dict[str, Any]] = []
        out_assoc: list[dict[str, Any]] = []
        if not followups:
            return {"entities": out_entities, "associations": out_assoc}

        with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(followups))) as ex:
            futs = {
                ex.submit(self._safe_call, attr, getattr(self, attr),
                          (qv,), {}): (attr, qv)
                for attr, qv in followups
            }
            for fut in as_completed(futs):
                attr, qv = futs[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"error": "{}: {}".format(type(e).__name__, e)}
                source_results[attr + ":depth2"] = _summarize_result(result)
                if isinstance(result, dict) and not result.get("error") \
                        and not result.get("interaction_required") \
                        and not result.get("credentials_required"):
                    out_entities.extend(self._extract(attr, result))
        return {"entities": out_entities, "associations": out_assoc}

    # -- extraction ----------------------------------------------------

    def _extract(self, attr: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            if attr == "amap":
                pois = (result.get("fields") or {}).get("pois") or []
                return [e for p in pois if isinstance(p, dict)
                        for e in _poi_entities(p, "amap")]
            if attr == "baidu_map":
                pois = (result.get("fields") or {}).get("pois") or []
                return [e for p in pois if isinstance(p, dict)
                        for e in _poi_entities(p, "baidu_map")]
            if attr == "dianping":
                if result.get("shop_found"):
                    return _dianping_entities(result, "dianping")
                return []
            if attr == "douyin":
                return _douyin_entities(result, "douyin")
            if attr == "sogou_wx":
                arts = (result.get("fields") or {}).get("articles") or []
                return [e for a in arts if isinstance(a, dict)
                        for e in _sogou_entities(a, "sogou_wx")]
            if attr == "wenshu":
                fields = result.get("fields") or {}
                cases = fields.get("cases") or []
                return [e for c in cases if isinstance(c, dict)
                        for e in _wenshu_entities(c, "wenshu")]
            if attr == "court_notice":
                fields = result.get("fields") or {}
                notices = fields.get("notices") or []
                return [e for n in notices if isinstance(n, dict)
                        for e in _court_notice_entities(n, "court_notice")]
            if attr == "qcc":
                fields = result.get("fields") or {}
                profile = fields.get("profile") or {}
                if not isinstance(profile, dict) or profile.get("blocked"):
                    return []
                return _qcc_entities(profile, "qcc")
            if attr == "corporate":
                fields = result.get("fields") or {}
                recs = fields.get("corporate_records") or []
                if isinstance(recs, dict):
                    recs = [recs]
                return [e for r in recs if isinstance(r, dict)
                        for e in _corporate_entities(r, "corporate")]
            if attr == "icp_beian":
                return _icp_entities(result, "icp_beian")
            if attr == "trademark":
                return _trademark_entities(result, "trademark")
            if attr == "weibo":
                posts = (result.get("fields") or {}).get("posts") or []
                return [e for p in posts if isinstance(p, dict)
                        for e in _weibo_entities(p, "weibo")]
            if attr == "douban":
                groups = (result.get("fields") or {}).get("groups") or []
                return [e for g in groups if isinstance(g, dict)
                        for e in _douban_entities(g, "douban")]
            if attr == "maimai":
                arts = (result.get("fields") or {}).get("articles") or []
                return [e for a in arts if isinstance(a, dict)
                        for e in _maimai_entities(a, "maimai")]
            if attr == "telegram":
                msgs = (result.get("fields") or {}).get("messages") or []
                return [e for m in msgs if isinstance(m, dict)
                        for e in _telegram_entities(m, "telegram")]
            if attr == "phone_mark":
                return _phonemark_entities(result, "phone_mark")
            if attr == "cert_transparency":
                domains = (result.get("fields") or {}).get("associated_domains") or []
                return [{"type": "domain", "value": d, "sources": ["cert_transparency"],
                         "context": {"from": "cert_san"}} for d in domains if d]
            if attr == "analytics_pivot":
                domains = (result.get("fields") or {}).get("related_domains") or []
                return [{"type": "domain", "value": d, "sources": ["analytics_pivot"],
                         "context": {"from": "shared_analytics_id"}} for d in domains if d]
            if attr == "fofa":
                fields = result.get("fields") or {}
                assets = fields.get("assets") or []
                out = []
                for a in assets:
                    if isinstance(a, dict):
                        ip = a.get("ip") or ""
                        host = a.get("host") or a.get("domain") or ""
                        if host:
                            out.append({"type": "domain", "value": host, "sources": ["fofa"],
                                        "context": {"from": "co_hosted", "ip": ip}})
                        if ip:
                            out.append({"type": "ip", "value": ip, "sources": ["fofa"],
                                        "context": {"from": "fofa_asset"}})
                        icp = a.get("icp") or ""
                        if icp:
                            out.append({"type": "icp_license", "value": icp, "sources": ["fofa"],
                                        "context": {"from": "fofa_icp"}})
                return out
            if attr == "whatsmyname":
                fields = result.get("fields") or {}
                sites = fields.get("sites_found") or []
                out = [{"type": "username_profile", "value": s.get("site", ""),
                        "sources": ["whatsmyname"],
                        "context": {"from": "username_reuse", "url": s.get("url", "")}}
                       for s in sites if isinstance(s, dict)]
                for pm in fields.get("profile_metadata") or []:
                    out.extend(_wmn_profile_entities(pm, "whatsmyname"))
                return out
            if attr == "telegram_channel":
                fields = result.get("fields") or {}
                if not fields.get("channel_found"):
                    return []
                return _telegram_channel_entities(fields.get("channel") or {}, fields,
                                                  "telegram_channel")
            if attr == "hibp_breach_catalog":
                fields = result.get("fields") or {}
                out = []
                for b in fields.get("breaches") or []:
                    if not isinstance(b, dict):
                        continue
                    bname = str(b.get("title") or b.get("id") or "").strip()
                    if not bname:
                        continue
                    out.append({
                        "type": "breach_signal",
                        "value": bname,
                        "display": bname,
                        "sources": ["hibp_breach_catalog"],
                        "context": {
                            "from": "hibp_public_breach_catalog",
                            "pwn_count": b.get("pwn_count"),
                            "pwn_count_display": b.get("pwn_count_display"),
                            "added_date": b.get("added_date"),
                            "breach_date": b.get("breach_date"),
                            "breach_url": b.get("breach_url"),
                            "note": "公开 breach 名录命中是 lead, 非账号泄露确认",
                        },
                    })
                return out
            if attr == "huggingface":
                fields = result.get("fields") or {}
                return _huggingface_entities(fields, "huggingface")
            if attr == "semanticscholar":
                fields = result.get("fields") or {}
                return _semanticscholar_entities(fields, "semanticscholar")
            # Social user lanes (2026-10-21): user -> person entities.
            # nickname/bio/location/verify go into context; bio under
            # context["description"] so _extract_entity_contacts can mine
            # contact info; username/location feed _resolve_person_identity.
            if attr == "bilibili_user":
                fields = result.get("fields") or {}
                users = fields.get("users") or []
                return [e for u in users if isinstance(u, dict)
                        for e in _bilibili_user_entities(u, "bilibili_user")]
            if attr == "douban_user":
                fields = result.get("fields") or {}
                profile = fields.get("profile") or {}
                if not isinstance(profile, dict) or not profile.get("user_found"):
                    return []
                return _douban_user_entities(profile, fields, "douban_user")
            if attr == "douyin_user":
                fields = result.get("fields") or {}
                if not fields.get("user_found"):
                    return []
                return _douyin_user_entities(fields, "douyin_user")
            if attr == "xiaohongshu_user":
                fields = result.get("fields") or {}
                if not fields.get("user_found"):
                    return []
                return _xiaohongshu_user_entities(fields, "xiaohongshu_user")
            if attr == "keybase":
                fields = result.get("fields") or {}
                return _keybase_entities(fields, "keybase")
            # Unconventional association lane (2026-10-21)
            if attr == "github_contributors":
                fields = result.get("fields") or {}
                return _github_contributors_entities(fields, "github_contributors")
            if attr == "blockscout":
                fields = result.get("fields") or {}
                return _blockscout_entities(fields, "blockscout")
            if attr in ("lagou", "zhaopin", "zhipin"):
                fields = result.get("fields") or {}
                out = []
                addr = fields.get("address") or fields.get("company_address") or ""
                if addr:
                    out.append({"type": "address", "value": addr, "sources": [attr],
                                "context": {"from": f"{attr}_company"}})
                phone = fields.get("phone") or fields.get("contact_phone") or ""
                if phone:
                    out.append({"type": "phone", "value": phone, "sources": [attr],
                                "context": {"from": f"{attr}_company"}})
                # hiring signal
                hiring = fields.get("hiring_count") or fields.get("job_count") or 0
                if hiring:
                    out.append({"type": "hiring_signal", "value": str(hiring), "sources": [attr],
                                "context": {"from": f"{attr}_hiring"}})
                return out
            if attr == "ccgp":
                fields = result.get("fields") or {}
                bids = fields.get("bids") or []
                out = []
                for b in bids:
                    if isinstance(b, dict):
                        supplier = b.get("supplier") or b.get("company") or ""
                        if supplier:
                            out.append({"type": "business", "value": supplier, "sources": ["ccgp"],
                                        "context": {"from": "ccgp_bid", "amount": b.get("amount", "")}})
                        phone = b.get("phone") or b.get("contact_phone") or ""
                        if phone:
                            out.append({"type": "phone", "value": phone, "sources": ["ccgp"],
                                        "context": {"from": "ccgp_contact"}})
                # 招投标联系人 (people-unconventional p2): 公告详情中的
                # contacts -> person, phone -> contact 字段
                contacts = fields.get("contacts") or []
                for b in bids:
                    if isinstance(b, dict) and b.get("contacts"):
                        contacts = contacts + b["contacts"]
                for c in contacts:
                    if not isinstance(c, dict):
                        continue
                    nm = normalize_name(c.get("name") or "")
                    ph = str(c.get("phone") or "").strip()
                    if nm and len(nm) <= 30:
                        out.append({"type": "person", "value": nm, "display": nm,
                                    "sources": ["ccgp"],
                                    "context": {"from": "ccgp_contact_person", "phone": ph}})
                    if ph:
                        out.append({"type": "phone", "value": ph, "sources": ["ccgp"],
                                    "context": {"from": "ccgp_contact", "contact_name": nm}})
                return out
            if attr == "pgp":
                fields = result.get("fields") or {}
                if not fields.get("found"):
                    return []
                out = []
                fp = str(fields.get("fingerprint") or "")
                created = str(fields.get("key_created") or "")
                seen_emails: set[str] = set()
                for uid in (fields.get("uids") or []):
                    if not isinstance(uid, dict):
                        continue
                    name = normalize_name(uid.get("name") or "")
                    email = str(uid.get("email") or "").strip().lower()
                    if email and email not in seen_emails:
                        seen_emails.add(email)
                        out.append({"type": "email", "value": email, "display": email,
                                    "sources": ["pgp"],
                                    "context": {"from": "pgp_uid_email",
                                                "fingerprint": fp, "key_created": created,
                                                "key_name": name}})
                    # VKS 隐私设计下 UID 常只有邮箱 → 以邮箱为 person 标识
                    label = name or email
                    if label and len(label) <= 60:
                        out.append({"type": "person", "value": label, "display": label,
                                    "sources": ["pgp"],
                                    "context": {"from": "pgp_key_holder",
                                                "fingerprint": fp, "key_created": created,
                                                "email": email, "name": name}})
                for em in (fields.get("emails") or []):
                    em = str(em).strip().lower()
                    if em and em not in seen_emails:
                        seen_emails.add(em)
                        out.append({"type": "email", "value": em, "display": em,
                                    "sources": ["pgp"],
                                    "context": {"from": "pgp_uid_email",
                                                "fingerprint": fp, "key_created": created}})
                return out
            if attr == "patent":
                fields = result.get("fields") or {}
                patents = fields.get("patents") or []
                return [e for p in patents if isinstance(p, dict)
                        for e in _patent_entities(p, "patent")]
            if attr == "toutiao":
                arts = (result.get("fields") or {}).get("articles") or []
                return [e for a in arts if isinstance(a, dict)
                        for e in _toutiao_entities(a, "toutiao")]
            if attr == "gd_credit":
                fields = result.get("fields") or {}
                if fields.get("found") and fields.get("company_name"):
                    return _gd_credit_entities(fields, "gd_credit")
                comps = fields.get("companies") or []
                return [e for c in comps if isinstance(c, dict)
                        for e in _gd_credit_entities(c, "gd_credit")]
            if attr == "gleif":
                fields = result.get("fields") or {}
                out = [e for r in (fields.get("entities") or []) if isinstance(r, dict)
                       for e in _gleif_entities(r, "gleif")]
                parent_name = normalize_name(fields.get("direct_parent_name"))
                if parent_name:
                    out.append({
                        "type": "business", "value": parent_name, "display": parent_name,
                        "sources": ["gleif"],
                        "context": {
                            "from": "gleif_parent",
                            "parent_lei": fields.get("direct_parent_lei", ""),
                        },
                    })
                child_leis = fields.get("child_leis") or []
                if child_leis:
                    for e in out:
                        if e["type"] == "business" and isinstance(e.get("context"), dict):
                            e["context"].setdefault("child_leis", child_leis)
                return out
            if attr == "customs":
                fields = result.get("fields") or {}
                out = [e for p in (fields.get("parties") or []) if isinstance(p, dict)
                       for e in _customs_entities(p, "customs")]
                for cp in (fields.get("counterparties") or []):
                    cn = normalize_name(cp) if isinstance(cp, str) else ""
                    if cn and len(cn) <= 60:
                        out.append({
                            "type": "business", "value": cn, "display": cn,
                            "sources": ["customs"],
                            "context": {"from": "customs_counterparty"},
                        })
                addr = fields.get("address")
                if addr:
                    akey, adisp = normalize_address(addr)
                    if adisp:
                        out.append({
                            "type": "address", "value": akey or adisp, "display": adisp,
                            "matchable": bool(akey), "sources": ["customs"],
                            "context": {"from": "customs_detail"},
                        })
                return out
            if attr in ("software_copyright", "juhe_copyright"):
                fields = result.get("fields") or {}
                # zhifufu parse_browser_result / juhe query() put records at top
                # level (no "fields" envelope); handle both.
                records = fields.get("records") or result.get("records") or []
                return [e for r in records if isinstance(r, dict)
                        for e in _soft_copyright_entities(r, attr)]
            if attr == "weibo_relation":
                fields = result.get("fields") or {}
                # parse_browser_result puts users at top level; handle both.
                users = fields.get("users") or result.get("users") or []
                relation = fields.get("relation") or result.get("relation") or "followers"
                ents = [e for u in users if isinstance(u, dict)
                        for e in _weibo_relation_entities(u, "weibo_relation", relation)]
                # seed 用户实体：从 pagination.containerid 解析 uid
                # (格式 231051_-_followers_-_123456)，供 mutual_follow 关联。
                # Unconventional association lane (2026-10-21).
                pag = fields.get("pagination") or result.get("pagination") or {}
                cid = str(pag.get("containerid") or "")
                m = re.search(r"231051_-_.*?_-_(\d+)", cid)
                if m:
                    uid = m.group(1)
                    ents.append({
                        "type": "person",
                        "value": "weibo:{}".format(uid),
                        "display": "微博用户 {}".format(uid),
                        "sources": ["weibo_relation"],
                        "context": {
                            "from": "weibo_relation_seed",
                            "weibo_uid": uid,
                            "relation": relation,
                            "profile_url": "https://m.weibo.cn/u/{}".format(uid),
                        },
                    })
                return ents
            if attr == "dnsdumpster":
                fields = result.get("fields") or {}
                return _dnsdumpster_entities(fields, "dnsdumpster")
            if attr == "commoncrawl":
                fields = result.get("fields") or {}
                return _commoncrawl_entities(fields, "commoncrawl")
            if attr == "threatbook":
                fields = result.get("fields") or {}
                return _threatbook_entities(fields, "threatbook")
            if attr == "hunter":
                fields = result.get("fields") or {}
                return _hunter_entities(fields, "hunter")
            # Unconventional identity lanes (2026-10-21):
            # on-chain identity + git deep + cert contacts.
            if attr == "ens_lookup":
                fields = result.get("fields") or {}
                if not fields.get("resolved"):
                    return []
                out = []
                name = str(fields.get("name") or "").strip()
                address = str(fields.get("address") or "").strip()
                if name:
                    out.append({"type": "username_profile", "value": name,
                                "sources": ["ens_lookup"],
                                "context": {"from": "ens_name",
                                             "address": address,
                                             "note": "链上自选别名，非实名"}})
                if address:
                    out.append({"type": "crypto_address", "value": address,
                                "sources": ["ens_lookup"],
                                "context": {"from": "ens_resolve",
                                             "ens_name": name}})
                return out
            if attr == "poap_lookup":
                fields = result.get("fields") or {}
                out = []
                for b in (fields.get("badges") or []):
                    if not isinstance(b, dict):
                        continue
                    ename = str(b.get("event_name") or "").strip()
                    if not ename:
                        continue
                    out.append({"type": "event_attendance", "value": ename,
                                "sources": ["poap_lookup"],
                                "context": {"from": "poap_badge",
                                             "city": b.get("city", ""),
                                             "country": b.get("country", ""),
                                             "start_date": b.get("start_date", ""),
                                             "note": "公开出席徽章，可转赠/代领"}})
                return out
            if attr == "github_deep_extra":
                fields = result.get("fields") or {}
                out = []
                ce = fields.get("commit_author_emails") or {}
                for e in (ce.get("emails") or []):
                    if not isinstance(e, dict):
                        continue
                    email = str(e.get("email") or "").strip()
                    if not email:
                        continue
                    out.append({"type": "email", "value": email,
                                "sources": ["github_deep_extra"],
                                "context": {"from": "commit_author_email",
                                             "names": e.get("names", []),
                                             "repos": e.get("repos", [])[:5],
                                             "note": "git 自填元数据，可伪造"}})
                sp = fields.get("starred_profile") or {}
                for lang, count in list((sp.get("languages") or {}).items())[:5]:
                    out.append({"type": "tech_interest", "value": str(lang),
                                "sources": ["github_deep_extra"],
                                "context": {"from": "starred_languages",
                                             "star_count": count}})
                return out
            if attr == "crtsh_contact":
                fields = result.get("fields") or {}
                out = []
                for o in (fields.get("org_names") or []):
                    if not isinstance(o, dict):
                        continue
                    name = str(o.get("name") or "").strip()
                    if not name:
                        continue
                    out.append({"type": "org", "value": name,
                                "sources": ["crtsh_contact"],
                                "context": {"from": "cert_subject_issuer",
                                             "origin": o.get("origin", ""),
                                             "note": "证书组织字段，lead 级别"}})
                for e in (fields.get("contact_emails") or []):
                    if not isinstance(e, dict):
                        continue
                    email = str(e.get("email") or "").strip()
                    if not email:
                        continue
                    out.append({"type": "email", "value": email,
                                "sources": ["crtsh_contact"],
                                "context": {"from": "cert_contact",
                                             "origin": e.get("origin", "")}})
                return out
            # Kinship lane (2026-10-21): cninfo 公告亲属关系抽取 ->
            # person 实体（kinship statement 上下文），关联在
            # _kinship_disclosure_associations() 中生成。
            if attr == "cninfo_kinship":
                fields = result.get("fields") or {}
                out = []
                for st in (fields.get("kinship_statements") or []):
                    if not isinstance(st, dict):
                        continue
                    for key in ("person_a", "person_b"):
                        name = str(st.get(key) or "").strip()
                        if not name:
                            continue
                        out.append({
                            "type": "person", "value": name,
                            "sources": ["cninfo_kinship"],
                            "context": {
                                "from": "kinship_statement",
                                "kinship": {
                                    "person_a": st.get("person_a", ""),
                                    "person_b": st.get("person_b", ""),
                                    "relation_kind": st.get("relation_kind", ""),
                                    "evidence_level": st.get("evidence_level", ""),
                                    "quote": str(st.get("quote") or "")[:180],
                                    "source_ref": str(st.get("source_ref") or "")[:200],
                                    "pdf_url": st.get("pdf_url", ""),
                                },
                            }})
                return out
        except Exception:
            return []
        return []

    def _merge_entities(self, entities: dict[str, dict[str, Any]],
                        new_ents: list[dict[str, Any]]) -> None:
        for e in new_ents:
            eid = entity_id(e["type"], e["value"])
            if eid in entities:
                old = entities[eid]
                old["sources"] = sorted(
                    set(old.get("sources", [])) | set(e.get("sources", [])))
                old_ctx = old.setdefault("context", {})
                for k, v in (e.get("context") or {}).items():
                    if k == "of_business" and v:
                        # accumulate: one phone/address may belong to many businesses
                        owners = old_ctx.setdefault("of_businesses", [])
                        existing = [old_ctx.get("of_business")]
                        for cand in [v]:
                            if cand and cand not in existing and cand not in owners:
                                owners.append(cand)
                        if not old_ctx.get("of_business"):
                            old_ctx["of_business"] = v
                    elif k in ("role", "company") and v:
                        # accumulate: one person may hold many roles / companies
                        plural = {"role": "roles", "company": "companies"}[k]
                        acc = old_ctx.setdefault(plural, [])
                        seen_vals = [old_ctx.get(k)] + acc
                        if v not in seen_vals:
                            acc.append(v)
                        if not old_ctx.get(k):
                            old_ctx[k] = v
                    else:
                        old_ctx.setdefault(k, v)
            else:
                e["id"] = eid
                e.setdefault("sources", [])
                # normalize single owner into list form for uniform handling
                ctx = e.setdefault("context", {})
                if ctx.get("of_business") and "of_businesses" not in ctx:
                    ctx["of_businesses"] = [ctx["of_business"]]
                entities[eid] = e

    # -- association building ------------------------------------------

    def _build_associations(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        assocs: list[dict[str, Any]] = []
        by_type: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            by_type.setdefault(e["type"], []).append(e)

        businesses = by_type.get("business", [])
        phones = by_type.get("phone", [])
        addresses = [a for a in by_type.get("address", []) if a.get("matchable")]
        persons = by_type.get("person", [])

        phone_to_biz: dict[str, set[str]] = {}
        for p in phones:
            for owner in self._owners(p):
                phone_to_biz.setdefault(p["value"], set()).add(owner)

        addr_to_biz: dict[str, set[str]] = {}
        for a in addresses:
            for owner in self._owners(a):
                addr_to_biz.setdefault(a["value"], set()).add(owner)

        def biz_eid(name: str) -> str | None:
            for b in businesses:
                if b["value"] == name:
                    return b["id"]
            return None

        for ph, biznames in phone_to_biz.items():
            eids = [x for x in (biz_eid(n) for n in biznames) if x]
            for i in range(len(eids)):
                for j in range(i + 1, len(eids)):
                    assocs.append({
                        "from": eids[i], "to": eids[j],
                        "relation": "same_phone", "strength": "strong",
                        "sources": self._sources_of(entities, [eids[i], eids[j]]),
                        "note": "shared phone {}".format(ph),
                    })

        for ak, biznames in addr_to_biz.items():
            eids = [x for x in (biz_eid(n) for n in biznames) if x]
            for i in range(len(eids)):
                for j in range(i + 1, len(eids)):
                    assocs.append({
                        "from": eids[i], "to": eids[j],
                        "relation": "same_address", "strength": "strong",
                        "sources": self._sources_of(entities, [eids[i], eids[j]]),
                        "note": "shared normalized address",
                    })

        for a in addresses:
            for owner in self._owners(a):
                be = biz_eid(owner)
                if be:
                    assocs.append({
                        "from": be, "to": a["id"],
                        "relation": "located_at", "strength": "exact",
                        "sources": sorted(set(a.get("sources", []))),
                        "note": "",
                    })

        for p in phones:
            for owner in self._owners(p):
                be = biz_eid(owner)
                if be:
                    assocs.append({
                        "from": p["id"], "to": be,
                        "relation": "contact_of", "strength": "strong",
                        "sources": sorted(set(p.get("sources", []))),
                        "note": "",
                    })

        # QQ/WeChat: same contact across persons = strong link
        for ctype in ("qq", "wechat"):
            contacts = by_type.get(ctype, [])
            contact_to_persons: dict[str, set[str]] = {}
            for c in contacts:
                owners = (c.get("context") or {}).get("owners", [])
                for owner in owners:
                    if owner:
                        contact_to_persons.setdefault(c["value"], set()).add(owner)
            for cval, person_names in contact_to_persons.items():
                if len(person_names) >= 2:
                    # Find person eids
                    peids = []
                    for pn in person_names:
                        for per in persons:
                            if per["value"] == pn:
                                peids.append(per["id"])
                                break
                    for i in range(len(peids)):
                        for j in range(i + 1, len(peids)):
                            assocs.append({
                                "from": peids[i], "to": peids[j],
                                "relation": f"same_{ctype}", "strength": "strong",
                                "sources": self._sources_of(entities, [peids[i], peids[j]]),
                                "note": f"shared {ctype} {cval}",
                            })

        for per in persons:
            case_no = (per.get("context") or {}).get("case_number", "")
            if not case_no:
                continue
            for b in businesses:
                bctx = b.get("context") or {}
                if bctx.get("from") == "court_case_party" and \
                        bctx.get("case_number") == case_no:
                    assocs.append({
                        "from": per["id"], "to": b["id"],
                        "relation": "co_party_in_case", "strength": "weak",
                        "sources": sorted(set(per.get("sources", [])) |
                                         set(b.get("sources", []))),
                        "note": "same case {}".format(case_no),
                    })

        # ---- Unconventional association lane (2026-10-21) ----
        assocs.extend(self._unconventional_associations(entities))
        return assocs

    def _unconventional_associations(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """非常规关联人关系构建（全部带来源标注，置信度分级）。

        新增 relation kind：
          co_inventor / co_party_in_case(person-person) / co_author /
          co_mentioned_in / mutual_follow / co_contributor /
          onchain_counterparty / consortium_member_of
        """
        assocs: list[dict[str, Any]] = []
        by_type: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            by_type.setdefault(e["type"], []).append(e)
        persons = by_type.get("person", [])

        def _pairwise(group: list[dict[str, Any]], relation: str,
                      strength: str, note: str,
                      sources: list[str] | None = None) -> None:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    assocs.append({
                        "from": a["id"], "to": b["id"],
                        "relation": relation, "strength": strength,
                        "sources": sources or self._sources_of(
                            entities, [a["id"], b["id"]]),
                        "note": note,
                    })

        # 1. co_party_in_case person<->person：同一案件共同当事人（weak）
        by_case: dict[str, list[dict[str, Any]]] = {}
        for per in persons:
            ctx = per.get("context") or {}
            if ctx.get("from") == "court_case_party" and ctx.get("case_number"):
                by_case.setdefault(ctx["case_number"], []).append(per)
        for case_no, group in by_case.items():
            if len(group) >= 2:
                _pairwise(group, "co_party_in_case", "weak",
                          "same case {} (co-party, lead)".format(case_no))

        # 2. co_inventor：同一专利共同发明人（strong）
        by_patent: dict[str, list[dict[str, Any]]] = {}
        patent_meta: dict[str, dict[str, str]] = {}
        for per in persons:
            ctx = per.get("context") or {}
            if ctx.get("from") == "patent_inventor" and ctx.get("publication_number"):
                pub = ctx["publication_number"]
                by_patent.setdefault(pub, []).append(per)
                patent_meta.setdefault(pub, {
                    "title": str(ctx.get("patent_title", ""))[:60],
                    "url": "https://patents.google.com/patent/{}/en".format(pub),
                })
        for pub, group in by_patent.items():
            if len(group) >= 2:
                meta = patent_meta[pub]
                _pairwise(group, "co_inventor", "strong",
                          "同为专利 {}《{}》的发明人 {}".format(
                              pub, meta["title"], meta["url"]))

        # 3. co_author：学术合著（strong；Semantic Scholar 公开合著关系）
        main_authors = [p for p in persons
                        if (p.get("context") or {}).get("from")
                        == "semanticscholar_author"]
        for co in persons:
            ctx = co.get("context") or {}
            if ctx.get("relation") != "co_author":
                continue
            with_author = str(ctx.get("with_author", ""))
            titles = "; ".join((ctx.get("paper_titles") or [])[:3])
            for main in main_authors:
                if main["display"] == with_author or main["id"] == co["id"]:
                    if main["id"] == co["id"]:
                        continue
                    assocs.append({
                        "from": main["id"], "to": co["id"],
                        "relation": "co_author", "strength": "strong",
                        "sources": self._sources_of(
                            entities, [main["id"], co["id"]]),
                        "note": "学术合著（{}篇共享论文）：{}".format(
                            ctx.get("shared_papers") or 0, titles),
                    })

        # 4. co_mentioned_in：同一公开报道/名单共现（review，带URL+标题）
        by_url: dict[str, list[dict[str, Any]]] = {}
        cooccur_meta: dict[str, str] = {}
        for per in persons:
            ctx = per.get("context") or {}
            url = ctx.get("cooccur_url", "")
            if url:
                by_url.setdefault(url, []).append(per)
                cooccur_meta.setdefault(
                    url, str(ctx.get("cooccur_title", ""))[:80])
        for url, group in by_url.items():
            if len(group) >= 2:
                _pairwise(group, "co_mentioned_in", "review",
                          "同篇公开报道《{}》共现 {}".format(
                              cooccur_meta[url], url))

        # 5. mutual_follow：微博互关（review；seed 用户 <-> 互关用户）
        seed_uid = ""
        seed_ent = None
        for per in persons:
            ctx = per.get("context") or {}
            if ctx.get("from") == "weibo_relation_seed" and ctx.get("weibo_uid"):
                seed_uid = ctx["weibo_uid"]
                seed_ent = per
                break
        if seed_ent is not None:
            for per in persons:
                ctx = per.get("context") or {}
                if ctx.get("from") != "weibo_relation":
                    continue
                if ctx.get("follow_me") and ctx.get("following"):
                    assocs.append({
                        "from": seed_ent["id"], "to": per["id"],
                        "relation": "mutual_follow", "strength": "review",
                        "sources": sorted(set(seed_ent.get("sources", [])) |
                                         set(per.get("sources", []))),
                        "note": "微博互关（双方互相关注） {}".format(
                            ctx.get("profile_url", "")),
                    })

        # 6. co_contributor：同一 GitHub 仓库贡献者（review；排除 Bot 配对）
        profiles = [e for e in by_type.get("username_profile", [])
                    if (e.get("context") or {}).get("from")
                    == "github_contributor"]
        by_repo: dict[str, list[dict[str, Any]]] = {}
        for pr in profiles:
            ctx = pr.get("context") or {}
            repo = ctx.get("repo", "")
            if repo and not ctx.get("is_bot"):
                by_repo.setdefault(repo, []).append(pr)
        for repo, group in by_repo.items():
            if len(group) >= 2:
                repo_url = (group[0].get("context") or {}).get("repo_url", "")
                _pairwise(group, "co_contributor", "review",
                          "同为 GitHub 仓库 {} 的公开贡献者 {}".format(
                              repo, repo_url))

        # 7. onchain_counterparty：链上频繁交易对手（weak）
        evm_addrs = by_type.get("evm_address", [])
        seed_map = {e["value"]: e for e in evm_addrs
                    if (e.get("context") or {}).get("from")
                    == "blockscout_seed"}
        for cp in evm_addrs:
            ctx = cp.get("context") or {}
            if ctx.get("from") != "blockscout_counterparty":
                continue
            seed_ent = seed_map.get(ctx.get("of_address", ""))
            if seed_ent is None:
                continue
            assocs.append({
                "from": seed_ent["id"], "to": cp["id"],
                "relation": "onchain_counterparty", "strength": "weak",
                "sources": sorted(set(seed_ent.get("sources", [])) |
                                 set(cp.get("sources", []))),
                "note": "链上交易对手：近 {} 笔扫描中出现 {} 次"
                        "（发出 {} / 收到 {}），弱关联 lead {}".format(
                            seed_ent.get("context", {}).get(
                                "transactions_scanned", 0),
                            ctx.get("tx_count", 0),
                            ctx.get("sent", 0), ctx.get("received", 0),
                            ctx.get("explorer_url", "")),
            })

        # 8. consortium_member_of：同一中标公告联合体成员（strong，法定公告）
        businesses = by_type.get("business", [])
        by_ann: dict[str, list[dict[str, Any]]] = {}
        ann_meta: dict[str, str] = {}
        for b in businesses:
            ctx = b.get("context") or {}
            url = ctx.get("announcement_url", "")
            if ctx.get("from") == "consortium_member" and url:
                by_ann.setdefault(url, []).append(b)
                ann_meta.setdefault(
                    url, str(ctx.get("announcement_title", ""))[:80])
        for url, group in by_ann.items():
            if len(group) >= 2:
                _pairwise(group, "consortium_member_of", "strong",
                          "同一中标公告《{}》联合体成员 {}".format(
                              ann_meta[url], url))
        return assocs

    @staticmethod
    def _owners(ent: dict[str, Any]) -> list[str]:
        """All business names linked as owner in entity context."""
        ctx = ent.get("context") or {}
        owners: list[str] = []
        for cand in [ctx.get("of_business")] + list(ctx.get("of_businesses") or []):
            if cand and cand not in owners:
                owners.append(cand)
        return owners

    @staticmethod
    def _sources_of(entities: dict[str, dict[str, Any]],
                    eids: list[str]) -> list[str]:
        s: set[str] = set()
        for eid in eids:
            s.update(entities.get(eid, {}).get("sources", []))
        return sorted(s)

    @staticmethod
    def _dedupe_associations(
            assocs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple] = set()
        out: list[dict[str, Any]] = []
        for a in assocs:
            key = (a["from"], a["to"], a["relation"])
            rkey = (a["to"], a["from"], a["relation"])
            if key in seen or rkey in seen:
                continue
            seen.add(key)
            out.append(a)
        return out

    # -- pattern detection ----------------------------------------------

    def _detect_patterns(self, entities: dict[str, dict[str, Any]],
                         assocs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        patterns: list[dict[str, Any]] = []
        by_type: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            by_type.setdefault(e["type"], []).append(e)

        phone_biz: dict[str, set[str]] = {}
        for a in assocs:
            if a["relation"] == "contact_of":
                phone_biz.setdefault(a["from"], set()).add(a["to"])
        for pid, bizs in phone_biz.items():
            if len(bizs) >= 2 and pid in entities:
                patterns.append({
                    "pattern": "shared_phone_across_businesses",
                    "description": (
                        "同一手机号关联 {} 家企业 ({})："
                        "可能是代办/中介/集团共用号码"
                    ).format(len(bizs), entities[pid]["display"]),
                    "entities": sorted(bizs) + [pid],
                    "severity": "medium",
                })

        addr_biz: dict[str, set[str]] = {}
        for a in assocs:
            if a["relation"] == "located_at":
                addr_biz.setdefault(a["to"], set()).add(a["from"])
        for aid, bizs in addr_biz.items():
            if len(bizs) >= 2 and aid in entities:
                patterns.append({
                    "pattern": "shared_address_across_businesses",
                    "description": (
                        "同一地址关联 {} 家企业："
                        "可能是虚拟地址/集中办公/孵化器"
                    ).format(len(bizs)),
                    "entities": sorted(bizs) + [aid],
                    "severity": "medium",
                })

        person_biz: dict[str, set[str]] = {}
        for a in assocs:
            if a["relation"] == "co_party_in_case":
                person_biz.setdefault(a["from"], set()).add(a["to"])
        for pid, bizs in person_biz.items():
            if len(bizs) >= 2 and pid in entities:
                patterns.append({
                    "pattern": "person_linked_multiple_businesses",
                    "description": (
                        "同一自然人 ({}) 出现在 {} 家企业的案件当事人中："
                        "关联企业线索"
                    ).format(entities[pid]["display"], len(bizs)),
                    "entities": sorted(bizs) + [pid],
                    "severity": "low",
                })

        biz_with_contact: set[str] = set()
        for a in assocs:
            if a["relation"] in ("contact_of", "located_at"):
                biz_with_contact.add(a["from"])
        if len(by_type.get("business", [])) > 1:
            for b in by_type.get("business", []):
                if b["id"] not in biz_with_contact:
                    patterns.append({
                        "pattern": "business_no_contact_footprint",
                        "description": (
                            "企业「{}」在公开渠道未发现电话/地址："
                            "空壳或纯线上经营信号（需结合其他证据判断）"
                        ).format(b["display"]),
                        "entities": [b["id"]],
                        "severity": "low",
                    })

        # ---- family / beneficial-owner patterns ----
        patterns.extend(self._family_patterns(entities, assocs))
        return patterns

    def _family_patterns(self, entities: dict[str, dict[str, Any]],
                         assocs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """家族企业信号 / 疑似实控人 / 挂名风险。均为 leads，非事实断言。"""
        patterns: list[dict[str, Any]] = []

        # company -> persons with corporate roles
        company_roles: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            if ctx.get("from") == "corporate_roles" and ctx.get("company"):
                company_roles.setdefault(ctx["company"], []).append(e)

        def _eid(t: str, v: str) -> str:
            return entity_id(t, v)

        for company, persons in company_roles.items():
            comp_eid = _eid("business", company)
            # same-surname count among role holders
            surnames: dict[str, list[dict[str, Any]]] = {}
            for p in persons:
                sn = (p.get("context") or {}).get("surname") or \
                    extract_surname(p["value"])
                surnames.setdefault(sn, []).append(p)
            for sn, members in surnames.items():
                if sn and len(members) >= 2:
                    roles = sorted({(m.get("context") or {}).get("role", "成员")
                                    for m in members})
                    patterns.append({
                        "pattern": "family_business_signal",
                        "description": (
                            "疑似家族企业：{} 中 {} 名同姓「{}」人员担任 {}"
                            "（{}），亲属共同经营信号"
                        ).format(company, len(members), sn,
                                 "、".join(roles),
                                 "、".join(m["display"] for m in members)),
                        "entities": [comp_eid] + [m["id"] for m in members],
                        "severity": "medium",
                    })

        # suspected beneficial owners (not the legal rep)
        for a in assocs:
            if a["relation"] != "suspected_controls":
                continue
            pid, ceid = a["from"], a["to"]
            if pid not in entities or ceid not in entities:
                continue
            # skip if this person IS the legal rep of that company
            is_lr = any(
                x["relation"] == "legal_rep_of" and x["from"] == pid
                and x["to"] == ceid for x in assocs)
            if not is_lr:
                patterns.append({
                    "pattern": "possible_beneficial_owner",
                    "description": (
                        "疑似实控人：{} 可能实际控制{}（非法定代表人）。"
                        "{}"
                    ).format(entities[pid]["display"],
                             entities[ceid]["display"], a.get("note", "")),
                    "entities": [pid, ceid],
                    "severity": "medium",
                })

        # figurehead risk: legal_rep_of + suspected_controls on same company
        # by a different person
        for a in assocs:
            if a["relation"] != "suspected_controls":
                continue
            ceid = a["to"]
            lr_holders = [x["from"] for x in assocs
                          if x["relation"] == "legal_rep_of" and x["to"] == ceid]
            if lr_holders and a["from"] not in lr_holders \
                    and a["from"] in entities and ceid in entities:
                lr_name = entities[lr_holders[0]]["display"] \
                    if lr_holders[0] in entities else "未知"
                patterns.append({
                    "pattern": "figurehead_risk",
                    "description": (
                        "挂名风险：{} 的法定代表人{}疑似挂名，"
                        "实际控制人可能是{}。{}"
                    ).format(entities[ceid]["display"], lr_name,
                             entities[a["from"]]["display"],
                             a.get("note", "")),
                    "entities": [ceid, a["from"]] + lr_holders,
                    "severity": "medium",
                })
        return patterns

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _seed_norm(seed_type: str, seed_value: str) -> str:
        if seed_type == "phone":
            return normalize_phone(seed_value) or seed_value
        if seed_type == "address":
            key, _ = normalize_address(seed_value)
            return key or seed_value
        if seed_type == "evm_address":
            return seed_value.strip().lower()
        if seed_type == "github_repo":
            return seed_value.strip().strip("/").lower()
        return normalize_name(seed_value) or seed_value.strip()

    @staticmethod
    def _seed_relation(seed_type: str, entity_type: str) -> str | None:
        # NOTE: seed links use seed_hit_* relations (not contact_of/located_at)
        # so pattern detection on entity-entity relations stays clean.
        mapping = {
            ("business_name", "phone"): "seed_hit_phone",
            ("business_name", "address"): "seed_hit_address",
            ("business_name", "business"): "seed_hit_business",
            ("business_name", "person"): "seed_hit_person",
            ("phone", "business"): "seed_hit_business",
            ("address", "business"): "seed_hit_business",
            ("person_name", "business"): "seed_hit_business",
            ("person_name", "person"): "seed_hit_person",
            ("email", "business"): "seed_hit_business",
            # Unconventional association lane (2026-10-21)
            ("github_repo", "username_profile"): "seed_hit_contributor",
            # ("evm_address", "evm_address") intentionally unmapped:
            # counterparties get the specific onchain_counterparty relation.
        }
        return mapping.get((seed_type, entity_type))


    @staticmethod
    def _roles(p: dict[str, Any]) -> list[str]:
        """All roles a person holds (accumulated across merged records)."""
        ctx = p.get("context") or {}
        roles: list[str] = []
        for cand in [ctx.get("role")] + list(ctx.get("roles") or []):
            if cand and cand not in roles:
                roles.append(cand)
        return roles

    @staticmethod
    def _person_companies(p: dict[str, Any]) -> list[str]:
        ctx = p.get("context") or {}
        out: list[str] = []
        for cand in [ctx.get("company")] + list(ctx.get("companies") or []):
            if cand and cand not in out:
                out.append(cand)
        return out

    def _infer_family_control(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """家族/实控推断：同姓聚类、挂名信号、夫妻店、控制链穿透。

        All outputs are leads (疑似/可能) with confidence levels, never facts.
        """
        assocs: list[dict[str, Any]] = []

        # index persons by company from corporate_roles context
        company_roles: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            if ctx.get("from") != "corporate_roles":
                continue
            company = ctx.get("company", "")
            if company:
                company_roles.setdefault(company, []).append(e)

        def _biz_eid(name: str) -> str | None:
            eid = entity_id("business", name)
            return eid if eid in entities else None

        for company, persons in company_roles.items():
            comp_eid = _biz_eid(company)
            if not comp_eid:
                continue

            # group by surname
            by_surname: dict[str, list[dict[str, Any]]] = {}
            for p in persons:
                sn = (p.get("context") or {}).get("surname") or extract_surname(p["value"])
                by_surname.setdefault(sn, []).append(p)

            legal_rep = next(
                (p for p in persons if "法人" in self._roles(p)), None)
            shareholders = [p for p in persons if "股东" in self._roles(p)]
            supervisors = [p for p in persons if "监事" in self._roles(p)]

            # -- role relations (exact, factual from corporate records) --
            if legal_rep:
                assocs.append({
                    "from": legal_rep["id"], "to": comp_eid,
                    "relation": "legal_rep_of", "strength": "exact",
                    "sources": sorted(set(legal_rep.get("sources", []))),
                    "note": "法定代表人（公开登记信息）",
                })
            for sh in shareholders:
                pct = (sh.get("context") or {}).get("share_pct")
                note = "股东（公开登记信息）"
                if pct is not None:
                    note += "，持股约{}%".format(pct)
                assocs.append({
                    "from": sh["id"], "to": comp_eid,
                    "relation": "shareholder_of", "strength": "exact",
                    "sources": sorted(set(sh.get("sources", []))),
                    "note": note,
                })
            for sv in supervisors:
                assocs.append({
                    "from": sv["id"], "to": comp_eid,
                    "relation": "supervisor_of", "strength": "exact",
                    "sources": sorted(set(sv.get("sources", []))),
                    "note": "监事（公开登记信息）",
                })
            for p in persons:
                proles = self._roles(p)
                extra_roles = [r for r in proles
                               if r not in ("法人", "股东", "监事")]
                for role in extra_roles:
                    assocs.append({
                        "from": p["id"], "to": comp_eid,
                        "relation": "executive_of", "strength": "exact",
                        "sources": sorted(set(p.get("sources", []))),
                        "note": "担任{}（公开登记信息）".format(role),
                    })

            # -- 1. 同姓聚类 -> possible_family_with (weak lead) --
            for sn, members in by_surname.items():
                if not sn or len(members) < 2:
                    continue
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        assocs.append({
                            "from": members[i]["id"], "to": members[j]["id"],
                            "relation": "possible_family_with",
                            "strength": "weak",
                            "sources": self._sources_of(
                                entities, [members[i]["id"], members[j]["id"]]),
                            "note": "疑似亲属关系：同姓「{}」，同任职于{}".format(sn, company),
                        })

            # -- 2. 挂名信号：年轻法人 + 年长同姓大股东 --
            if legal_rep:
                lr_ctx = legal_rep.get("context") or {}
                lr_surname = lr_ctx.get("surname") or extract_surname(legal_rep["value"])
                lr_age = lr_ctx.get("age_hint", "unknown")
                lr_share = lr_ctx.get("share_pct") or 0
                for sh in shareholders:
                    if sh["id"] == legal_rep["id"]:
                        continue
                    sh_ctx = sh.get("context") or {}
                    sh_surname = sh_ctx.get("surname") or extract_surname(sh["value"])
                    sh_age = sh_ctx.get("age_hint", "unknown")
                    try:
                        sh_share = float(sh_ctx.get("share_pct") or 0)
                    except (TypeError, ValueError):
                        sh_share = 0
                    if (sh_surname and sh_surname == lr_surname
                            and lr_age == "young"
                            and sh_age in ("middle", "old")
                            and sh_share > (lr_share or 0)):
                        assocs.append({
                            "from": sh["id"], "to": comp_eid,
                            "relation": "suspected_controls",
                            "strength": "weak",
                            "sources": self._sources_of(
                                entities, [sh["id"], comp_eid]),
                            "note": (
                                "疑似实控人：{}（年长同姓大股东，持股约{}%）与"
                                "年轻法人{}同姓，法人可能为挂名"
                            ).format(sh["value"], sh_ctx.get("share_pct"),
                                     legal_rep["value"]),
                        })
                        break

            # -- 3. 夫妻店模式：两名异姓股东 --
            person_sh = [s for s in shareholders]
            if len(person_sh) == 2:
                sn1 = (person_sh[0].get("context") or {}).get("surname") or \
                    extract_surname(person_sh[0]["value"])
                sn2 = (person_sh[1].get("context") or {}).get("surname") or \
                    extract_surname(person_sh[1]["value"])
                if sn1 and sn2 and sn1 != sn2:
                    assocs.append({
                        "from": person_sh[0]["id"], "to": person_sh[1]["id"],
                        "relation": "possible_couple_business",
                        "strength": "weak",
                        "sources": self._sources_of(
                            entities, [person_sh[0]["id"], person_sh[1]["id"]]),
                        "note": "疑似夫妻店：两名异姓股东共同持股{}".format(company),
                    })

        # -- 4. 穿透持股：公司股东 -> 该公司的法人 --
        for e in entities.values():
            if e["type"] != "business":
                continue
            ctx = e.get("context") or {}
            if ctx.get("from") != "corporate_roles" or ctx.get("role") != "股东":
                continue
            holding_co = e["value"]
            target_co = ctx.get("of_company", "")
            target_eid = _biz_eid(target_co)
            if not target_eid:
                continue
            # find holding company's legal rep among persons
            for p in entities.values():
                if p["type"] != "person":
                    continue
                pctx = p.get("context") or {}
                if (pctx.get("from") == "corporate_roles"
                        and pctx.get("company") == holding_co
                        and pctx.get("role") == "法人"):
                    assocs.append({
                        "from": p["id"], "to": target_eid,
                        "relation": "suspected_controls",
                        "strength": "weak",
                        "sources": self._sources_of(entities, [p["id"], target_eid]),
                        "note": (
                            "疑似实控人（穿透）：{}为{}股东，"
                            "{}为{}的法定代表人"
                        ).format(target_co, holding_co, p["value"], holding_co),
                    })

        # -- 5. 一人多企：同一人在多家公司任职 -> 控制网 --
        person_companies: dict[str, set[str]] = {}
        for e in entities.values():
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            if ctx.get("from") == "corporate_roles":
                for co in self._person_companies(e):
                    person_companies.setdefault(e["id"], set()).add(co)
        for pid, companies in person_companies.items():
            if len(companies) >= 2:
                for co in companies:
                    ceid = _biz_eid(co)
                    if ceid and ceid != pid:
                        assocs.append({
                            "from": pid, "to": ceid,
                            "relation": "multi_company_role",
                            "strength": "weak",
                            "sources": sorted(set(entities[pid].get("sources", []))),
                            "note": "疑似控制网节点：{}在{}家公司任职".format(
                                entities[pid]["display"], len(companies)),
                        })
        return assocs

    def _kinship_disclosure_associations(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """亲属关系 lane（2026-10-21）：披露/文书/自述的亲属关系 -> 关联。

        relation kind: kinship_spouse / kinship_parent_child /
                       kinship_sibling / kinship_family。
        strength 直接映射 evidence_level：exact / strong / review。
        措辞一律"披露显示 / 文书载明 / 自述/疑似"，绝不断言为事实。
        """
        from core.kinship_extract import (EVIDENCE_LEVELS, RELATION_KINDS,
                                         statement_note)

        # person name -> eid 索引
        name_to_eid: dict[str, str] = {}
        for eid, e in entities.items():
            if e["type"] == "person":
                name_to_eid.setdefault(str(e.get("value") or ""), eid)

        statements: list[dict[str, Any]] = []
        for eid, e in entities.items():
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            if ctx.get("from") == "kinship_statement":
                st = dict(ctx.get("kinship") or {})
                if st.get("relation_kind"):
                    statements.append(st)
            elif ctx.get("from") == "douban_user":
                # 简介亲属自述：person_a 回填资料主人
                for st in ctx.get("self_claimed_kinship") or []:
                    if not isinstance(st, dict):
                        continue
                    st = dict(st)
                    if not st.get("person_a"):
                        st["person_a"] = str(e.get("value") or "")
                    statements.append(st)

        assocs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for st in statements:
            kind = st.get("relation_kind")
            level = st.get("evidence_level")
            if kind not in RELATION_KINDS or level not in EVIDENCE_LEVELS:
                continue
            a, b = str(st.get("person_a") or ""), str(st.get("person_b") or "")
            eid_a, eid_b = name_to_eid.get(a), name_to_eid.get(b)
            if not eid_a or not eid_b or eid_a == eid_b:
                continue
            relation = "kinship_" + kind
            key = (min(eid_a, eid_b), max(eid_a, eid_b), relation)
            if key in seen:
                continue
            seen.add(key)
            assocs.append({
                "from": eid_a, "to": eid_b,
                "relation": relation, "strength": level,
                "sources": sorted(set(
                    (entities[eid_a].get("sources") or []) +
                    (entities[eid_b].get("sources") or []))),
                "note": statement_note(st),
            })
        return assocs

    def _resolve_person_identity(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """跨平台身份归一：同一人在多平台的账号归一。

        Signals (all leads, never facts):
        - Same username across platforms (exact match) → strong
        - Same username + matching location/bio → exact (high confidence)
        - Same phone across profiles → exact
        - Username similarity (levenshtein) + same city → weak

        This is the core of person deep-dive: merging footprints.
        """
        assocs: list[dict[str, Any]] = []
        # group person entities by normalized username
        by_username: dict[str, list[dict[str, Any]]] = {}
        for e in entities.values():
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            # username from various sources
            uname = (ctx.get("username") or ctx.get("nickname") or
                     ctx.get("screen_name") or e.get("display") or "")
            uname_norm = uname.strip().lower()
            if uname_norm and len(uname_norm) >= 3:
                by_username.setdefault(uname_norm, []).append(e)

        for uname, persons in by_username.items():
            if len(persons) < 2:
                continue
            # same username on multiple platforms
            platforms = set()
            for p in persons:
                srcs = p.get("sources") or []
                platforms.update(srcs)
            if len(platforms) >= 2:
                # check for corroborating signals
                locations = set()
                for p in persons:
                    ctx = p.get("context") or {}
                    loc = (ctx.get("location") or ctx.get("city") or "").strip()
                    if loc:
                        locations.add(loc)
                confidence = "strong"
                if len(locations) == 1:
                    confidence = "exact"  # same username + same location
                assocs.append({
                    "pattern": "cross_platform_identity",
                    "description": f"疑似同一人：用户名 '{uname}' 在 {len(platforms)} 个平台出现",
                    "confidence": confidence,
                    "entities": [p["display"] for p in persons],
                    "platforms": sorted(platforms),
                    "note": "lead，不是身份证明；需人工核实头像/内容",
                })
        return assocs

    def _extract_entity_contacts(
            self, entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """从实体上下文提取联系方式（QQ/微信/手机/邮箱/平台UID）。

        Uses core/contact_extractor.py. Each found contact becomes:
        1. An entity (qq/wechat) so cross-person matching works
        2. An association linking the person to the contact value
        """
        try:
            from core.contact_extractor import extract_contacts
        except ImportError:
            return []
        assocs: list[dict[str, Any]] = []
        for eid, e in list(entities.items()):
            if e["type"] != "person":
                continue
            ctx = e.get("context") or {}
            # gather text from bio/description/intro fields
            texts = []
            for k in ("bio", "description", "intro", "signature", "about"):
                v = ctx.get(k)
                if v and isinstance(v, str):
                    texts.append(v)
            if not texts:
                continue
            combined = "\n".join(texts)
            try:
                contacts = extract_contacts(combined)
            except Exception:
                continue
            for c in contacts:
                ctype = c.get("type", "")
                cval = c.get("value", "")
                if not cval:
                    continue
                # Create entity for matchable contact types
                if ctype in ("qq", "wechat"):
                    ceid = entity_id(ctype, cval)
                    if ceid not in entities:
                        entities[ceid] = {
                            "type": ctype, "value": cval, "display": cval,
                            "sources": e.get("sources", []),
                            "context": {"from": "contact_extraction", "owners": [e["display"]]},
                        }
                    else:
                        # Add this person to owners list
                        ctx = entities[ceid].get("context") or {}
                        owners = ctx.get("owners", [])
                        if e["display"] not in owners:
                            owners.append(e["display"])
                            ctx["owners"] = owners
                    # Association: person -> contact
                    assocs.append({
                        "pattern": "has_contact",
                        "contact_type": ctype,
                        "description": f"{e['display']} 使用 {ctype}: {cval}",
                        "confidence": c.get("confidence", "weak"),
                        "entities": [e["display"], cval],
                    })
                else:
                    assocs.append({
                        "pattern": "contact_found",
                        "contact_type": ctype,
                        "description": f"在 {e['display']} 的资料中发现{ctype}",
                        "confidence": c.get("confidence", "weak"),
                        "entities": [e["display"]],
                        "note": "lead，需核实",
                    })
        return assocs



def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Small, PII-free summary for source_results (no raw values)."""
    if not isinstance(result, dict):
        return {"status": "invalid_result"}
    if result.get("error"):
        return {"status": "error", "error": str(result["error"])[:120]}
    if result.get("interaction_required"):
        return {"status": "interaction_required"}
    if result.get("credentials_required"):
        return {"status": "credentials_required"}
    fields = result.get("fields") or {}
    summary: dict[str, Any] = {"status": "ok"}
    for k in ("poi_count", "article_count", "post_count", "shop_found",
              "total_count", "field_count"):
        if k in fields or k in result:
            summary[k] = fields.get(k, result.get(k))
    return summary


# ---------------------------------------------------------------------------
# New-source entity extractors (ICP, trademark, weibo, douban, maimai,
# telegram, phone_mark). All extract public entities for association.
# ---------------------------------------------------------------------------

def _icp_entities(result: dict, source: str) -> list:
    """ICP: domain -> company/individual."""
    out = []
    fields = result.get("fields") or {}
    unit = fields.get("unit_name") or fields.get("company_name") or ""
    if unit:
        out.append({"type": "business" if "公司" in unit or "企业" in unit else "person",
                    "value": unit, "sources": [source],
                    "context": {"from": "icp_filing", "license": fields.get("license", "")}})
    return out


def _trademark_entities(result: dict, source: str) -> list:
    """Trademark: brand -> applicant."""
    out = []
    fields = result.get("fields") or {}
    applicant = fields.get("applicant") or ""
    if applicant:
        out.append({"type": "business" if "公司" in applicant else "person",
                    "value": applicant, "sources": [source],
                    "context": {"from": "trademark_applicant",
                                "mark": fields.get("mark_name", "")}})
    return out


def _weibo_entities(post: dict, source: str) -> list:
    """Weibo: author -> person, bio mentions -> business."""
    out = []
    author = post.get("author") or {}
    nick = author.get("nickname") or author.get("screen_name") or ""
    if nick:
        out.append({"type": "person", "value": nick, "sources": [source],
                    "context": {"from": "weibo_author",
                                "verified": author.get("verified", False),
                                "bio": (author.get("description") or "")[:200]}})
    bio = author.get("description") or ""
    # bio often contains "XX公司创始人" - extract as lead
    if bio and ("公司" in bio or "创始人" in bio or "法人" in bio):
        out.append({"type": "business", "value": bio[:100], "sources": [source],
                    "context": {"from": "weibo_bio", "author": nick}})
    return out


def _douban_entities(group: dict, source: str) -> list:
    """Douban: group -> topic mentions."""
    out = []
    name = group.get("name") or ""
    if name:
        out.append({"type": "business", "value": name, "sources": [source],
                    "context": {"from": "douban_group"}})
    return out


def _maimai_entities(article: dict, source: str) -> list:
    """Maimai: article author -> person + company."""
    out = []
    author = article.get("author") or {}
    name = author.get("name") or ""
    company = author.get("company") or ""
    position = author.get("position") or ""
    if name:
        out.append({"type": "person", "value": name, "sources": [source],
                    "context": {"from": "maimai_author", "company": company,
                                "position": position}})
    if company:
        out.append({"type": "business", "value": company, "sources": [source],
                    "context": {"from": "maimai_author_company", "person": name}})
    return out


def _telegram_entities(msg: dict, source: str) -> list:
    """Telegram: message text -> extract phones/names as leads."""
    out = []
    text = msg.get("text") or ""
    if not text:
        return out
    # extract phone numbers from message text
    import re
    phones = re.findall(r'1[3-9]\d{9}', text)
    for p in set(phones):
        out.append({"type": "phone", "value": p, "sources": [source],
                    "context": {"from": "telegram_message"}})
    return out


def _phonemark_entities(result: dict, source: str) -> list:
    """Phone mark: phone -> business name."""
    out = []
    fields = result.get("fields") or {}
    biz = fields.get("business_name") or fields.get("company") or ""
    if biz:
        out.append({"type": "business", "value": biz, "sources": [source],
                    "context": {"from": "phone_mark", "city": fields.get("city", "")}})
    return out


# contact 类型 -> 实体类型词汇映射（只用已有实体类型词汇）
_WMN_CONTACT_ENTITY_TYPE = {
    "mobile": "phone",
    "landline": "phone",
    "email": "email",
    "qq": "username_profile",
    "wechat": "username_profile",
    "weibo_uid": "username_profile",
    "douyin_id": "username_profile",
    "platform_uid": "username_profile",
    "service_number": "phone",
}


def _wmn_profile_entities(pm: dict, source: str = "whatsmyname") -> list:
    """WhatsMyName profile_metadata -> 实体（Maigret 式深挖的第二跳）。

    person: profile 昵称；email/phone: 联系方式实体；
    qq/微信/平台 UID: username_profile 实体（contact_type 标注）。
    全部是 lead：context 标注来源站点与 url。
    """
    if not isinstance(pm, dict):
        return []
    out = []
    site = pm.get("site_name") or pm.get("site") or ""
    url = pm.get("url") or ""
    base_ctx = {"from": "wmn_profile", "site": site, "url": url}

    display = (pm.get("display_name") or "").strip()
    if display:
        ctx = dict(base_ctx)
        if pm.get("bio"):
            ctx["bio"] = str(pm["bio"])[:200]
        if pm.get("company"):
            ctx["company"] = str(pm["company"])[:120]
        if pm.get("location"):
            ctx["location"] = str(pm["location"])[:120]
        out.append({"type": "person", "value": display, "display": display,
                    "sources": [source], "context": ctx})

    for c in pm.get("contacts") or []:
        if not isinstance(c, dict):
            continue
        ctype, value = c.get("type"), (c.get("value") or "").strip()
        if not ctype or not value:
            continue
        etype = _WMN_CONTACT_ENTITY_TYPE.get(ctype)
        if not etype:
            continue
        ctx = dict(base_ctx)
        ctx["contact_type"] = ctype
        ctx["contact_confidence"] = c.get("confidence", "")
        out.append({"type": etype, "value": value,
                    "display": value if etype != "username_profile" else None,
                    "sources": [source], "context": ctx})
    return out


def _telegram_channel_entities(channel: dict, fields: dict,
                               source: str = "telegram_channel") -> list:
    """Telegram 公开频道 -> 实体。

    person: 频道标题（同名公开频道是人物线索）；description/about 进 context，
    由 _extract_entity_contacts 统一从中挖联系方式。全部是 lead。
    username_profile: tgstat 关联 handle（频道主的其他公开频道，强归一信号）。
    """
    if not isinstance(channel, dict):
        return []
    out: list = []
    title = (channel.get("title") or "").strip()
    if title:
        ctx = {"from": "telegram_channel",
               "url": fields.get("preview_url") or "",
               "subscribers": channel.get("subscribers") or channel.get("subscribers_raw") or ""}
        desc = (channel.get("description") or "").strip()
        if desc:
            ctx["description"] = desc[:500]
        texts = []
        for p in (fields.get("posts") or [])[:10]:
            t = (p.get("text") or "").strip() if isinstance(p, dict) else ""
            if t:
                texts.append(t)
        if texts:
            ctx["about"] = "\n".join(texts)[:2000]
        name = normalize_name(title) or title
        out.append({"type": "person", "value": name, "display": title,
                    "sources": [source], "context": ctx})
    # tgstat 关联 handle: 同一频道主的其他公开频道 -> username_profile 实体，
    # 供跨源身份归一 (_resolve_person_identity 及图谱 username 匹配) 消费。
    tgstat = fields.get("tgstat") or {}
    related = tgstat.get("related_handles") or []
    owner = (tgstat.get("handle") or "").lower()
    for h in related:
        handle = str(h or "").strip().lower()
        if not handle or handle == owner:
            continue
        out.append({
            "type": "username_profile",
            "value": handle,
            "display": f"@{handle}",
            "sources": [source],
            "context": {
                "from": "tgstat_related_handle",
                "owner_handle": owner,
                "subscribers_exact": tgstat.get("subscribers_exact"),
                "url": f"https://t.me/{handle}",
                "note": "频道主的其他公开频道, 同人多频道归一的强信号, lead",
            },
        })
    return out


def _huggingface_entities(fields: dict, source: str = "huggingface") -> list:
    """HuggingFace 公开开发者画像 -> 实体。

    person: HF 用户（username 为稳定标识；fullname 无则用 username）。
    context: username（供 _resolve_person_identity 跨平台归一）、所属组织、
    模型数、粉丝数、简介（description 走联系方式管道统一挖联系方式）。
    全部是 lead。
    """
    if not isinstance(fields, dict) or not fields.get("user_found"):
        return []
    profile = fields.get("profile") or {}
    username = (profile.get("username") or "").strip()
    if not username:
        return []
    fullname = (profile.get("fullname") or "").strip()
    name = normalize_name(fullname) or username
    orgs = [str(o.get("name", "")).strip()
            for o in (profile.get("orgs") or [])
            if isinstance(o, dict) and str(o.get("name", "")).strip()]
    ctx = {
        "from": "huggingface_profile",
        "username": username,
        "account_type": profile.get("type") or "user",
    }
    if orgs:
        ctx["orgs"] = orgs
    for key in ("num_models", "num_datasets", "num_spaces",
                "num_followers", "created_at"):
        if profile.get(key) not in (None, ""):
            ctx[key] = profile.get(key)
    desc = (profile.get("description") or "").strip()
    if desc:
        ctx["description"] = desc[:500]
    top_models = [m.get("model_id", "")
                  for m in (fields.get("models") or [])[:5]
                  if isinstance(m, dict) and m.get("model_id")]
    if top_models:
        ctx["top_models"] = top_models
    return [{"type": "person", "value": username,
             "display": fullname or username,
             "sources": [source], "context": ctx}]


def _semanticscholar_entities(fields: dict, source: str = "semanticscholar") -> list:
    """Semantic Scholar 学者 -> 本人(个人) + 合作者(个人).

    Expected fields shape (adapters/semanticscholar_adapter):
        {"author_found", "match_level", "author": {"author_id","name",
          "affiliations","paper_count","citation_count","h_index","url","homepage"},
         "top_papers": [...], "co_authors": [{"name","author_id","shared_papers","paper_titles"}]}
    本人实体 context 携带 affiliations/论文数/引用数/h-index、homepage；
    合作者实体 relation="co_author"。全部是 lead，绝不做身份断言。
    """
    if not isinstance(fields, dict) or not fields.get("author_found"):
        return []
    author = fields.get("author") or {}
    if not isinstance(author, dict):
        return []
    name = normalize_name(author.get("name")) or (author.get("name") or "").strip()
    if not name:
        return []
    display_name = (author.get("name") or "").strip() or name
    affs = [a for a in (author.get("affiliations") or []) if a]
    desc_parts = []
    if affs:
        desc_parts.append("affiliations: " + "; ".join(affs))
    if author.get("homepage"):
        desc_parts.append("homepage: " + author["homepage"])
    paper_titles = [p.get("title") for p in (fields.get("top_papers") or [])
                    if isinstance(p, dict) and p.get("title")]
    if paper_titles:
        desc_parts.append("recent papers: " + " | ".join(paper_titles[:5]))
    ctx = {
        "from": "semanticscholar_author",
        "username": name,
        "homepage": author.get("homepage") or "",
        "location": "; ".join(affs),
        "affiliations": affs,
        "paper_count": author.get("paper_count") or 0,
        "citation_count": author.get("citation_count") or 0,
        "h_index": author.get("h_index") or 0,
        "author_url": author.get("url") or "",
        "author_id": author.get("author_id") or "",
        "match_level": fields.get("match_level") or "review",
    }
    # bio/homepage text for the contact-extraction pipeline (_extract_entity_contacts)
    description = "\n".join(desc_parts).strip()
    if description:
        ctx["description"] = description[:1000]
    ents = [{"type": "person", "value": name, "display": display_name,
             "sources": [source], "context": ctx}]
    for co in (fields.get("co_authors") or []):
        if not isinstance(co, dict):
            continue
        co_name = normalize_name(co.get("name")) or (co.get("name") or "").strip()
        if not co_name or co_name == name or len(co_name) > 60:
            continue
        ents.append({
            "type": "person", "value": co_name, "display": co.get("name") or co_name,
            "sources": [source],
            "context": {
                "from": "semanticscholar_coauthor",
                "relation": "co_author",
                "with_author": display_name,
                "shared_papers": co.get("shared_papers") or 0,
                "paper_titles": (co.get("paper_titles") or [])[:3],
                "author_id": co.get("author_id") or "",
                "match_level": fields.get("match_level") or "review",
            },
        })
    return ents


# ---------------------------------------------------------------------------
# Social user lanes (2026-10-21): B站 / 豆瓣 / 抖音 / 小红书 user -> person.
#
# Each source yields person entities: nickname as the identity handle,
# bio/intro under context["description"] (mined by _extract_entity_contacts),
# username/location in context for _resolve_person_identity cross-platform
# merge. Everything is a lead, never an identity assertion.
# ---------------------------------------------------------------------------


def _bilibili_user_entities(u: dict, source: str = "bilibili_user") -> list:
    """B站用户 -> person。uname 为 handle；认证信息/粉丝数/等级进 context。"""
    if not isinstance(u, dict):
        return []
    uname = (u.get("uname") or "").strip()
    mid = u.get("mid")
    if not uname and not mid:
        return []
    name = normalize_name(uname) or uname or str(mid)
    ctx = {
        "from": "bilibili_user",
        "username": uname,
        "platform_mid": mid,
        "profile_url": u.get("profile_url") or "",
    }
    for key in ("fans", "level", "video_count", "gender", "is_upuser",
                "official_type"):
        if u.get(key) not in (None, ""):
            ctx[key] = u.get(key)
    official_desc = (u.get("official_desc") or "").strip()
    if official_desc:
        ctx["verified"] = official_desc
    verify_info = (u.get("verify_info") or "").strip()
    if verify_info:
        ctx["verify_info"] = verify_info[:200]
    bio = (u.get("bio") or "").strip()
    if bio:
        ctx["description"] = bio[:500]
    return [{"type": "person", "value": name, "display": uname or str(mid),
             "sources": [source], "context": ctx}]


def _douban_user_entities(profile: dict, fields: dict,
                          source: str = "douban_user") -> list:
    """豆瓣用户 -> person。昵称为 handle；简介/常居地/注册时间进 context。"""
    nickname = (profile.get("nickname") or "").strip()
    if not nickname:
        return []
    name = normalize_name(nickname) or nickname
    ctx = {
        "from": "douban_user",
        "username": profile.get("uid_alias") or profile.get("uid") or "",
        "platform_user_id": profile.get("user_id_number") or "",
        "profile_url": fields.get("profile_url") or profile.get("profile_url") or "",
    }
    location = (profile.get("location") or "").strip()
    if location:
        ctx["location"] = location
    registered = (profile.get("registered_at") or "").strip()
    if registered:
        ctx["registered_at"] = registered
    ip_loc = (profile.get("ip_location") or "").strip()
    if ip_loc and ip_loc != "未知":
        ctx["ip_location"] = ip_loc
    intro = (profile.get("intro") or "").strip()
    if intro:
        ctx["description"] = intro[:500]
    # 亲属关系 lane（2026-10-21）：简介亲属自述 -> review 级线索，
    # 关联在 _kinship_disclosure_associations() 中生成。
    claimed = profile.get("self_claimed_kinship") or []
    if claimed:
        ctx["self_claimed_kinship"] = claimed
    return [{"type": "person", "value": name, "display": nickname,
             "sources": [source], "context": ctx}]


def _douyin_user_entities(fields: dict, source: str = "douyin_user") -> list:
    """抖音用户 -> person。抖音号/昵称为 handle；签名/IP属地/认证进 context。"""
    profile = fields.get("profile") or {}
    if not isinstance(profile, dict):
        return []
    nickname = (profile.get("nickname") or "").strip()
    username = (profile.get("username") or "").strip()
    if not nickname and not username:
        return []
    handle = nickname or username
    name = normalize_name(handle) or handle
    ctx = {
        "from": "douyin_user",
        "username": username,
        "nickname": nickname,
        "profile_url": fields.get("profile_url") or "",
    }
    location = (profile.get("location") or "").strip()
    if location:
        ctx["location"] = location
    for key in ("follower_count", "following_count", "aweme_count",
                "total_favorited"):
        if profile.get(key) not in (None, ""):
            ctx[key] = profile.get(key)
    verified = (profile.get("verified") or "").strip()
    if verified:
        ctx["verified"] = verified[:200]
    bio = (profile.get("bio") or "").strip()
    if bio:
        ctx["description"] = bio[:500]
    return [{"type": "person", "value": name, "display": handle,
             "sources": [source], "context": ctx}]


def _xiaohongshu_user_entities(fields: dict,
                              source: str = "xiaohongshu_user") -> list:
    """小红书用户 -> person。昵称为 handle；简介/属地/小红书号进 context。"""
    profile = fields.get("profile") or {}
    if not isinstance(profile, dict):
        return []
    nickname = (profile.get("nickname") or "").strip()
    if not nickname:
        return []
    name = normalize_name(nickname) or nickname
    ctx = {
        "from": "xiaohongshu_user",
        "username": (profile.get("red_id") or "").strip(),
        "nickname": nickname,
        "platform_user_id": profile.get("user_id") or "",
        "profile_url": profile.get("profile_url") or "",
    }
    location = (profile.get("location") or "").strip()
    if location:
        ctx["location"] = location
    for key in ("fans_count", "follows_count", "notes_count", "gender"):
        if profile.get(key) not in (None, ""):
            ctx[key] = profile.get(key)
    bio = (profile.get("bio") or "").strip()
    if bio:
        ctx["description"] = bio[:500]
    return [{"type": "person", "value": name, "display": nickname,
             "sources": [source], "context": ctx}]


def _keybase_entities(fields: dict, source: str = "keybase") -> list:
    """Keybase 用户 -> person。full_name/username 为 handle；deep 字段进 context。

    proofs 链给出跨平台账号绑定（linked_platforms/linked_identities）；
    identity_deep 给出 Stellar/加密币地址/设备/PGP kid/签名链锚点——
    均为用户主动公开的声明，按 leads 处理。
    """
    if not isinstance(fields, dict) or not fields.get("user_found"):
        return []
    username = (fields.get("username") or "").strip()
    full_name = (fields.get("full_name") or "").strip()
    handle = full_name or username
    if not handle:
        return []
    name = normalize_name(handle) or handle
    ctx = {
        "from": "keybase",
        "username": username,
        "profile_url": f"https://keybase.io/{username}" if username else "",
        "proof_count": fields.get("proof_count", 0),
    }
    location = (fields.get("location") or "").strip()
    if location:
        ctx["location"] = location
    bio = (fields.get("bio") or "").strip()
    if bio:
        ctx["description"] = bio[:500]
    linked = fields.get("linked_platforms") or []
    if linked:
        ctx["linked_platforms"] = list(linked)[:20]
    identities = fields.get("linked_identities") or {}
    if isinstance(identities, dict) and identities:
        ctx["linked_identities"] = {k: v for k, v in list(identities.items())[:20]}
    deep = fields.get("identity_deep") or {}
    if isinstance(deep, dict):
        if deep.get("stellar_account"):
            ctx["stellar_account"] = deep["stellar_account"]
        crypto = deep.get("crypto_addresses") or {}
        if isinstance(crypto, dict):
            flat = [a["address"] for items in crypto.values()
                    if isinstance(items, list)
                    for a in items if isinstance(a, dict) and a.get("address")]
            if flat:
                ctx["crypto_addresses"] = flat[:10]
        if deep.get("device_count"):
            ctx["keybase_device_count"] = deep["device_count"]
        sig = deep.get("sig_chain") or {}
        if isinstance(sig, dict) and sig.get("last_sig_id"):
            ctx["keybase_sig_seqno"] = sig.get("last_seqno")
    return [{"type": "person", "value": name, "display": handle,
             "sources": [source], "context": ctx}]


# ---------------------------------------------------------------------------
# Unconventional association lane (2026-10-21): 非常规关联人发现
#
# 新增 relation kind 一览（全部带来源标注，置信度分级）:
#   co_inventor          person<->person  同一专利的共同发明人            strong
#   co_party_in_case     person<->person  同一案件共同当事人（已有人->企业） weak
#   co_author            person<->person  学术合著（Semantic Scholar）     strong
#   co_mentioned_in      person<->person  同一公开报道/名单共现（带URL）   review
#   mutual_follow        person<->person  微博互关                        review
#   co_contributor       username_profile<->username_profile
#                                       同一 GitHub 仓库贡献者            review
#   onchain_counterparty evm_address<->evm_address 链上频繁交易对手      weak
#   consortium_member_of business<->business 同一中标公告联合体成员       strong
# ---------------------------------------------------------------------------


def _github_contributors_entities(fields: dict,
                                 source: str = "github_contributors") -> list:
    """GitHub 仓库贡献者 -> username_profile 实体。

    Expected fields (adapters/github_contributors_adapter):
        {"contributors": [{"login","contributions","type","is_bot","profile_url"}],
         "repo"(缺省，用 repo_url 解析), "repo_url"(缺省)}
    Bot 账号保留实体但标注 is_bot，由关联层排除配对。
    全部是 lead。
    """
    if not isinstance(fields, dict):
        return []
    contributors = fields.get("contributors") or []
    repo_url = str(fields.get("repo_url") or "")
    repo = str(fields.get("repo") or "")
    if not repo and repo_url:
        m = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
        if m:
            repo = m.group(1)
    out = []
    for c in contributors:
        if not isinstance(c, dict) or not c.get("login"):
            continue
        login = str(c["login"]).strip()
        if not login:
            continue
        out.append({
            "type": "username_profile",
            "value": login,
            "display": login,
            "sources": [source],
            "context": {
                "from": "github_contributor",
                "repo": repo,
                "repo_url": repo_url or (f"https://github.com/{repo}" if repo else ""),
                "contributions": c.get("contributions") or 0,
                "account_type": c.get("type") or "User",
                "is_bot": bool(c.get("is_bot")),
                "profile_url": c.get("profile_url") or f"https://github.com/{login}",
            },
        })
    return out


def _blockscout_entities(fields: dict, source: str = "blockscout") -> list:
    """Blockscout 地址交易对手 -> evm_address 实体（seed + 对手方）。

    Expected fields (adapters/blockscout_adapter.parse_transactions):
        {"chain","explorer","explorer_url","transactions_scanned",
         "counterparties": [{"address","tx_count","sent","received",
                             "first_seen","last_seen"}],
         "address"(缺省，用 explorer_url 解析)}
    实体类型 evm_address 为本 lane 新增；value 为小写 0x 地址。
    全部是 lead（弱关联）。
    """
    if not isinstance(fields, dict):
        return []
    counterparties = fields.get("counterparties") or []
    if not counterparties:
        return []
    explorer_url = str(fields.get("explorer_url") or "")
    seed = str(fields.get("address") or "")
    if not seed and explorer_url:
        m = re.search(r"/address/(0x[0-9a-fA-F]{40})", explorer_url)
        if m:
            seed = m.group(1).lower()
    seed = seed.lower()
    out = []
    if seed:
        out.append({
            "type": "evm_address", "value": seed, "display": seed,
            "sources": [source],
            "context": {
                "from": "blockscout_seed",
                "chain": fields.get("chain") or "ethereum",
                "ens_name": fields.get("ens_name") or "",
                "explorer_url": explorer_url,
                "transactions_scanned": fields.get("transactions_scanned") or 0,
            },
        })
    for cp in counterparties:
        if not isinstance(cp, dict) or not cp.get("address"):
            continue
        addr = str(cp["address"]).strip().lower()
        if not addr or addr == seed:
            continue
        out.append({
            "type": "evm_address", "value": addr, "display": addr,
            "sources": [source],
            "context": {
                "from": "blockscout_counterparty",
                "of_address": seed,
                "tx_count": cp.get("tx_count") or 0,
                "sent": cp.get("sent") or 0,
                "received": cp.get("received") or 0,
                "first_seen": cp.get("first_seen") or "",
                "last_seen": cp.get("last_seen") or "",
                "explorer_url": f"https://eth.blockscout.com/address/{addr}",
            },
        })
    return out


def _news_cooccurrence_entities(records: list[dict],
                                source: str = "news_cooccurrence") -> list:
    """新闻/名单共现 -> person 实体（通用 contract，供各报道源接入）。

    Contract（兄弟 lane 的 public_news_lookup 判死后，此 contract 保持开放，
    任何能产出 {"title","url","persons"} 的报道/名单源均可接入）:
        [{"title": 报道/名单标题, "url": 报道链接, "persons": [人名...]}]
    共现实体携带 cooccur_url/cooccur_title，由关联层生成 co_mentioned_in。
    persons 去重；单人记录仍建实体（不产生关系）。
    """
    out = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        title = str(rec.get("title") or "")[:120]
        url = str(rec.get("url") or "")
        if not url:
            continue
        seen: set[str] = set()
        for raw in rec.get("persons") or []:
            nm = normalize_name(raw)
            if not nm or nm in seen or len(nm) > 30:
                continue
            seen.add(nm)
            out.append({
                "type": "person", "value": nm, "display": nm,
                "sources": [source],
                "context": {
                    "from": "news_cooccurrence",
                    "cooccur_title": title,
                    "cooccur_url": url,
                },
            })
    return out


_CONSORTIUM_PATTERNS = [
    # "联合体：A公司（牵头人）、B公司"
    re.compile(r"联合体[：:]\s*([^。\n；;]+)"),
    # "联合体成员：A公司、B公司" / "联合体成员为 A公司和B公司"
    re.compile(r"联合体成员[：:为]?\s*([^。\n；;]+)"),
    # "以联合体形式投标，成员包括 A公司、B公司"
    re.compile(r"联合体[^。\n]*?(?:成员|包括|由)[：:，,、\s]*([^。\n；;]+)"),
]
_CONSORTIUM_SPLIT_RE = re.compile(r"[、，,；;]")
_CONSORTIUM_NAME_RE = re.compile(
    r"([\u4e00-\u9fa5a-zA-Z0-9（）()·\-—]{2,60}"
    r"(?:公司|厂|所|中心|院|社|集团|企业|工作室|店|行|场|局|部))")
_LEADER_MARK_RE = re.compile(r"[（(](?:牵头人|牵头方|牵头单位|主办方)[）)]")


def parse_consortium_members(text: str) -> list[dict[str, str]]:
    """从中标/投标公告文本解析联合体成员。

    返回 [{"name": 企业名, "role": "leader"|"member"}]；不足 2 家返回 []。
    纯函数：公告获取由招投标 lane 负责，本函数只做关系层解析。
    """
    if not text:
        return []
    t = str(text)
    members: list[dict[str, str]] = []
    seen: set[str] = set()
    for pat in _CONSORTIUM_PATTERNS:
        for m in pat.finditer(t):
            chunk = m.group(1)
            for part in _CONSORTIUM_SPLIT_RE.split(chunk):
                part = part.strip().strip("和与及")
                if not part:
                    continue
                role = "leader" if _LEADER_MARK_RE.search(part) else "member"
                part = _LEADER_MARK_RE.sub("", part).strip()
                nm_m = _CONSORTIUM_NAME_RE.search(part)
                if not nm_m:
                    continue
                name = normalize_name(nm_m.group(1))
                if not name or name in seen:
                    continue
                seen.add(name)
                members.append({"name": name, "role": role})
        if len(members) >= 2:
            break
    return members if len(members) >= 2 else []


def _consortium_entities(announcement: dict,
                         source: str = "ccgp") -> list:
    """联合体公告 -> business 实体（成员）。

    Contract: {"members": [{"name","role"}], "url": 公告链接, "title": 公告标题}
    实体携带 announcement_url，由关联层生成 consortium_member_of。
    """
    if not isinstance(announcement, dict):
        return []
    members = announcement.get("members") or []
    url = str(announcement.get("url") or "")
    title = str(announcement.get("title") or "")[:120]
    out = []
    for mb in members:
        if not isinstance(mb, dict) or not mb.get("name"):
            continue
        name = normalize_name(mb["name"])
        if not name:
            continue
        out.append({
            "type": "business", "value": name, "display": name,
            "sources": [source],
            "context": {
                "from": "consortium_member",
                "consortium_role": mb.get("role") or "member",
                "announcement_url": url,
                "announcement_title": title,
            },
        })
    return out


# ---------------------------------------------------------------------------
# Family / beneficial-owner inference layer (家族/实控推断层)
#
# Background (user): many companies are family businesses; the legal
# representative may be a figurehead while the real controller is a
# spouse / child / relative / friend. Legal structure is surface;
# association digging finds the real controller.
#
# ALL inferences here are leads, never facts. Every output uses
# 疑似/可能 language with confidence levels (exact/strong/weak).
# ---------------------------------------------------------------------------

# common Chinese compound surnames (first-two-char surnames)
_COMPOUND_SURNAMES = frozenset([
    "欧阳", "司马", "上官", "皇甫", "令狐", "诸葛", "司徒", "申屠",
    "南宫", "夏侯", "闻人", "公孙", "慕容", "长孙", "宇文", "司空",
])


def extract_surname(name: str) -> str:
    """Extract Chinese surname (handles common compound surnames)."""
    s = normalize_name(name)
    if not s:
        return ""
    if len(s) >= 3 and s[:2] in _COMPOUND_SURNAMES:
        return s[:2]
    return s[0]


def _corporate_entities(record: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Extract entities from a corporate role record.

    Expected record shape:
        {
          "company_name": "...",
          "legal_rep": {"name": "...", "age_hint": "young|middle|old|unknown"},
          "shareholders": [
             {"name": "...", "kind": "person|company",
              "share_pct": 60.0, "age_hint": "young|middle|old|unknown"},
          ],
          "personnel": [{"name": "...", "role": "监事|董事|经理|财务负责人"}],
        }
    """
    ents: list[dict[str, Any]] = []
    company = normalize_name(record.get("company_name"))
    if not company:
        return ents
    ents.append({
        "type": "business", "value": company, "display": company,
        "sources": [source],
        "context": {"from": "corporate_roles"},
    })

    def _person(name: str, role: str, extra: dict | None = None) -> None:
        nm = normalize_name(name)
        if not nm:
            return
        ctx = {"from": "corporate_roles", "company": company,
               "companies": [company],
               "role": role, "roles": [role],
               "surname": extract_surname(nm)}
        if extra:
            ctx.update(extra)
        ents.append({
            "type": "person", "value": nm, "display": nm,
            "sources": [source], "context": ctx,
        })

    lr = record.get("legal_rep") or {}
    if isinstance(lr, dict) and lr.get("name"):
        _person(lr["name"], "法人",
                {"age_hint": lr.get("age_hint", "unknown")})

    for sh in record.get("shareholders") or []:
        if not isinstance(sh, dict) or not sh.get("name"):
            continue
        kind = sh.get("kind", "person")
        if kind == "company":
            cn = normalize_name(sh["name"])
            if cn:
                ents.append({
                    "type": "business", "value": cn, "display": cn,
                    "sources": [source],
                    "context": {
                        "from": "corporate_roles",
                        "role": "股东", "of_company": company,
                        "share_pct": sh.get("share_pct"),
                    },
                })
        else:
            _person(sh["name"], "股东", {
                "share_pct": sh.get("share_pct"),
                "age_hint": sh.get("age_hint", "unknown"),
            })

    for p in record.get("personnel") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        _person(p["name"], p.get("role", "高管"))
    return ents

    # -- family / beneficial-owner inference --------------------------------
def create_engine_with_all_adapters(**kwargs) -> "EntityAssociationEngine":
    """Factory: build EntityAssociationEngine with all available adapters injected.

    Adapters that require credentials (API keys) are skipped unless the key
    is provided via kwargs.
    """
    engine = EntityAssociationEngine()

    # No-key adapters
    try:
        from adapters.dnsdumpster_adapter import DNSdumpsterLookup
        engine.dnsdumpster = DNSdumpsterLookup()
    except Exception:
        pass

    try:
        from adapters.gleif_adapter import GleifLookup
        engine.gleif = GleifLookup()
    except Exception:
        pass

    try:
        from adapters.commoncrawl_adapter import CommonCrawlLookup
        engine.commoncrawl = CommonCrawlLookup()
    except Exception:
        pass

    try:
        from adapters.patent_adapter import PatentLookup
        engine.patent = PatentLookup()
    except Exception:
        pass

    # Unconventional identity lane (2026-10-21): PGP public key directory
    try:
        from adapters.public_pgp_adapter import PgpKeyLookup
        engine.pgp = PgpKeyLookup()
    except Exception:
        pass

    try:
        from adapters.toutiao_adapter import ToutiaoSearchLookup
        engine.toutiao = ToutiaoSearchLookup()
    except Exception:
        pass

    try:
        from adapters.customs_adapter import ZaubaCustomsLookup
        engine.customs = ZaubaCustomsLookup()
    except Exception:
        pass

    try:
        from adapters.software_copyright_adapter import ZhifufuSoftLookup
        engine.software_copyright = ZhifufuSoftLookup()
    except Exception:
        pass

    try:
        from adapters.weibo_relation_adapter import WeiboRelationLookup
        engine.weibo_relation = WeiboRelationLookup()
    except Exception:
        pass

    try:
        from adapters.telegram_channel_adapter import TelegramChannelLookup
        engine.telegram_channel = TelegramChannelLookup()
    except Exception:
        pass

    # Social user lanes (2026-10-21): B站 / 豆瓣 / 抖音 / 小红书 user dimension
    try:
        from adapters.bilibili_user_adapter import BilibiliUserLookup
        engine.bilibili_user = BilibiliUserLookup()
    except Exception:
        pass

    try:
        from adapters.douban_user_adapter import DoubanUserLookup
        engine.douban_user = DoubanUserLookup()
    except Exception:
        pass

    try:
        from adapters.douyin_adapter import DouyinUserLookup
        engine.douyin_user = DouyinUserLookup()
    except Exception:
        pass

    try:
        from adapters.xiaohongshu_adapter import XiaohongshuNoteLookup
        engine.xiaohongshu_user = XiaohongshuNoteLookup()
    except Exception:
        pass

    # 企查查 WAF-bypass (2026-10-21): 代理 + acw_sc__v2 纯 Python 求解；
    # 代理地址可配（默认公开代理），走通需干净出口。
    try:
        from adapters.qcc_waf_adapter import QccWafBypassLookup
        engine.qcc = QccWafBypassLookup()
    except Exception:
        pass

    try:
        from adapters.keybase_adapter import KeybaseIdentityLookup
        engine.keybase = KeybaseIdentityLookup()
    except Exception:
        pass

    # Kinship lane (2026-10-21): 巨潮资讯公告亲属关系抽取
    # (EXPERIMENTAL, default off at registry level)
    try:
        from adapters.cninfo_kinship_adapter import CninfoKinshipLookup
        engine.cninfo_kinship = CninfoKinshipLookup()
    except Exception:
        pass

    # Unconventional association lane (2026-10-21): EXPERIMENTAL, default off
    # (registry default_enabled=False; callers opt in explicitly).
    try:
        from adapters.github_contributors_adapter import GithubContributorsLookup
        engine.github_contributors = GithubContributorsLookup()
    except Exception:
        pass

    try:
        from adapters.blockscout_adapter import BlockscoutAddressLookup
        engine.blockscout = BlockscoutAddressLookup()
    except Exception:
        pass

    try:
        from adapters.hibp_breach_adapter import HIBPBreachCatalog
        engine.hibp_breach_catalog = HIBPBreachCatalog()
    except Exception:
        pass

    try:
        from adapters.huggingface_adapter import HuggingFaceLookup
        engine.huggingface = HuggingFaceLookup()
    except Exception:
        pass

    try:
        from adapters.semanticscholar_adapter import SemanticScholarLookup
        engine.semanticscholar = SemanticScholarLookup()
    except Exception:
        pass

    # Key-based adapters (only if key provided)
    if kwargs.get("hunter_api_key"):
        try:
            from adapters.hunter_adapter import HunterDomainLookup
            engine.hunter = HunterDomainLookup(api_key=kwargs["hunter_api_key"])
        except Exception:
            pass

    if kwargs.get("threatbook_api_key"):
        try:
            from adapters.threatbook_adapter import ThreatBookLookup
            engine.threatbook = ThreatBookLookup(api_key=kwargs["threatbook_api_key"])
        except Exception:
            pass

    if kwargs.get("juhe_api_key"):
        try:
            from adapters.software_copyright_adapter import JuheCopyrightLookup
            engine.juhe_copyright = JuheCopyrightLookup(api_key=kwargs["juhe_api_key"])
        except Exception:
            pass

    return engine

    return engine
