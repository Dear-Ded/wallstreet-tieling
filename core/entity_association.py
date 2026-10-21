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
                      "gleif", "customs", "software_copyright"],
    "person_name": ["wenshu", "sogou_wx", "douyin", "weibo", "maimai", "douban", "telegram", "phone_mark", "patent", "court_notice", "toutiao", "weibo_relation"],
    "email": ["sogou_wx", "douyin", "telegram"],
    "domain": ["icp_beian", "cert_transparency", "analytics_pivot", "sogou_wx", "fofa", "hunter", "commoncrawl", "dnsdumpster", "threatbook"],
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
            jobs.append((attr, adapter, (seed_value,), {}))

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
                sites = (result.get("fields") or {}).get("sites_found") or []
                return [{"type": "username_profile", "value": s.get("site", ""),
                         "sources": ["whatsmyname"],
                         "context": {"from": "username_reuse", "url": s.get("url", "")}}
                        for s in sites if isinstance(s, dict)]
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
                return [e for u in users if isinstance(u, dict)
                        for e in _weibo_relation_entities(u, "weibo_relation", relation)]
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
