#!/usr/bin/env python3
"""时间线关联分析 (Temporal correlation): dig to root via time.

社工学看"时机"：公司注册日期 vs 域名注册日期 vs 社交账号创建时间——
同一批时间创建的账号/主体，极可能是同一人操作。时间线对齐是找关联的利器。

Public-data only: timestamps come from public sources (POI records, corporate
registries, social profiles, ICP filings). All outputs are investigative
leads, never identity assertions.

Conventions (match core/entity_association.py):
- pattern dict: {"pattern", "description", "entities", "severity"}
- severity: "low" | "medium" | "high"
- entity identity: entity.get("id") or (type, value) tuple
"""

import re
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

_CN_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
_ISO_RE = re.compile(
    r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?"
)
_SLASH_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})")
_DOT_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})")
_COMPACT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp from the wild into a naive datetime.

    Accepts: datetime, int/float (unix seconds or milliseconds),
    ISO "YYYY-MM-DD[ HH:MM[:SS]]", "YYYY/MM/DD", "YYYY.MM.DD",
    Chinese "YYYY年M月D日", compact "YYYYMMDD".
    Returns None when unparseable. All results are timezone-naive.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts <= 0:
            return None
        # Heuristic: > 1e12 means milliseconds, > 1e10 also ms for
        # post-2001 dates; seconds otherwise.
        if ts > 1e12:
            ts /= 1000.0
        elif ts > 1e10:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None

    m = _CN_DATE_RE.search(s)
    if m:
        return _safe_dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _ISO_RE.match(s)
    if m:
        return _safe_dt(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4) or 0), int(m.group(5) or 0),
                        int(m.group(6) or 0))
    m = _SLASH_RE.match(s) or _DOT_RE.match(s)
    if m:
        return _safe_dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _COMPACT_RE.match(s)
    if m:
        return _safe_dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Last resort: fromisoformat handles a few extra shapes.
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def _safe_dt(year: int, month: int, day: int,
             hour: int = 0, minute: int = 0, second: int = 0) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Entity time extraction
# ---------------------------------------------------------------------------

# Fields (top-level or inside entity["context"]) that may carry a
# creation/registration timestamp for the entity itself.
_CREATED_KEYS = (
    "created_at", "create_time", "create_date", "creation_time",
    "reg_date", "reg_time", "register_date", "registered_at",
    "establish_date", "established_at", "founded_date", "founded_at",
    "domain_reg_date", "domain_registered", "account_created",
    "first_seen", "publish_date",
    # Chinese variants seen in corporate/POI records
    "成立日期", "注册日期", "创建时间", "注册时间", "开业日期",
    "核准日期", "发证日期",
)

# Fields that carry a *modification* timestamp (for simultaneous_update).
_UPDATED_KEYS = (
    "updated_at", "update_time", "last_modified", "modified_at",
    "变更日期", "更新时间", "最后更新",
)


def entity_time(entity: dict[str, Any],
                keys: tuple = _CREATED_KEYS) -> datetime | None:
    """Extract an entity's timestamp from itself or its context."""
    if not isinstance(entity, dict):
        return None
    for k in keys:
        v = entity.get(k)
        if v is not None:
            dt = parse_timestamp(v)
            if dt is not None:
                return dt
    ctx = entity.get("context")
    if isinstance(ctx, dict):
        for k in keys:
            v = ctx.get(k)
            if v is not None:
                dt = parse_timestamp(v)
                if dt is not None:
                    return dt
    return None


def entity_uid(entity: dict[str, Any]) -> str:
    """Stable identity for an entity dict."""
    eid = entity.get("id")
    if eid:
        return str(eid)
    return "{}:{}".format(entity.get("type", "?"), entity.get("value", "?"))


# ---------------------------------------------------------------------------
# Entity type categories (for relative patterns)
# ---------------------------------------------------------------------------

_COMPANY_TYPES = {"business", "company", "corporation", "enterprise",
                  "个体工商户", "firm"}
_DOMAIN_TYPES = {"domain", "website", "site", "web_site"}
_ACCOUNT_TYPES = {
    "account", "social_account", "user_account",
    "douyin", "douyin_account", "weibo", "weibo_account",
    "kuaishou", "bilibili", "xiaohongshu", "xhs_account",
    "wechat", "wechat_account", "telegram", "maimai",
    "douban", "tieba",
}

STRONG_WINDOW_DAYS = 7
WEAK_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def analyze_temporal_clusters(
    entities: list[dict[str, Any]],
    strong_window_days: int = STRONG_WINDOW_DAYS,
    weak_window_days: int = WEAK_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Cluster entities by creation/registration time.

    Sliding window from each cluster's first entity:
    - span <= strong_window_days -> "strong"  (同一批次操作)
    - span <= weak_window_days   -> "weak"

    Returns clusters sorted by start time. Entities without a parseable
    timestamp are ignored (reported via analyze_temporal coverage).
    """
    timed: list[tuple[datetime, dict[str, Any]]] = []
    for e in entities:
        dt = entity_time(e)
        if dt is not None:
            timed.append((dt, e))
    timed.sort(key=lambda t: t[0])

    clusters: list[dict[str, Any]] = []
    i = 0
    n = len(timed)
    while i < n:
        start = timed[i][0]
        members = [timed[i]]
        j = i + 1
        while j < n and (timed[j][0] - start) <= timedelta(days=weak_window_days):
            members.append(timed[j])
            j += 1
        if len(members) >= 2:
            end = members[-1][0]
            span_days = (end - start).days
            strength = ("strong" if span_days <= strong_window_days
                        else "weak")
            clusters.append({
                "cluster_id": "tc{:02d}".format(len(clusters) + 1),
                "time_window": {
                    "start": start.date().isoformat(),
                    "end": end.date().isoformat(),
                },
                "span_days": span_days,
                "strength": strength,
                "size": len(members),
                "entity_ids": [entity_uid(e) for _, e in members],
                "entity_types": sorted({str(e.get("type", "?"))
                                        for _, e in members}),
            })
        i = j if j > i else i + 1
    return clusters


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def detect_temporal_patterns(
    entities: list[dict[str, Any]],
    clusters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect time-based association patterns. All are leads, not facts."""
    if clusters is None:
        clusters = analyze_temporal_clusters(entities)
    patterns: list[dict[str, Any]] = []

    by_uid: dict[str, dict[str, Any]] = {}
    for e in entities:
        by_uid[entity_uid(e)] = e

    def disp(uid: str) -> str:
        e = by_uid.get(uid, {})
        return str(e.get("display") or e.get("value") or uid)[:60]

    # -- batch_creation: >=3 entities within 7 days -> same operator --
    for c in clusters:
        if c["strength"] == "strong" and c["size"] >= 3:
            patterns.append({
                "pattern": "batch_creation",
                "description": (
                    "7天内集中创建 {} 个主体/账号 ({} ~ {})："
                    "极可能是同一人/同一批次操作，深挖其关联"
                ).format(c["size"], c["time_window"]["start"],
                         c["time_window"]["end"]),
                "entities": c["entity_ids"],
                "severity": "medium",
                "cluster_id": c["cluster_id"],
            })

    timed = [(entity_time(e), e) for e in entities]
    timed = [(dt, e) for dt, e in timed if dt is not None]
    companies = [(dt, e) for dt, e in timed
                 if str(e.get("type", "")) in _COMPANY_TYPES]
    domains = [(dt, e) for dt, e in timed
               if str(e.get("type", "")) in _DOMAIN_TYPES]
    accounts = [(dt, e) for dt, e in timed
                if str(e.get("type", "")) in _ACCOUNT_TYPES]

    # -- domain_after_company: domain registered 0-90d after company --
    for cdt, ce in companies:
        for ddt, de in domains:
            delta = (ddt - cdt).days
            if 0 <= delta <= 90:
                patterns.append({
                    "pattern": "domain_after_company",
                    "description": (
                        "公司 [{}] 成立后 {} 天注册域名 [{}]："
                        "正常经营建站信号；域名备案主体可继续深挖"
                    ).format(disp(entity_uid(ce)), delta,
                             disp(entity_uid(de))),
                    "entities": [entity_uid(ce), entity_uid(de)],
                    "severity": "low",
                    "delta_days": delta,
                })

    # -- account_before_company: social account predates company >= 30d --
    for adt, ae in accounts:
        for cdt, ce in companies:
            delta = (cdt - adt).days
            if delta >= 30:
                patterns.append({
                    "pattern": "account_before_company",
                    "description": (
                        "社交账号 [{}] 比公司 [{}] 早 {} 天创建："
                        "可能是个人IP转企业经营，账号历史内容值得深挖"
                    ).format(disp(entity_uid(ae)), disp(entity_uid(ce)),
                             delta),
                    "entities": [entity_uid(ae), entity_uid(ce)],
                    "severity": "low",
                    "delta_days": delta,
                })

    # -- simultaneous_update: >=2 entities updated within 1 day --
    updated: list[tuple[datetime, dict[str, Any]]] = []
    for e in entities:
        dt = entity_time(e, keys=_UPDATED_KEYS)
        if dt is not None:
            updated.append((dt, e))
    updated.sort(key=lambda t: t[0])
    i, n = 0, len(updated)
    while i < n:
        start = updated[i][0]
        group = [updated[i]]
        j = i + 1
        while j < n and (updated[j][0] - start) <= timedelta(days=1):
            group.append(updated[j])
            j += 1
        if len(group) >= 2:
            uids = [entity_uid(e) for _, e in group]
            patterns.append({
                "pattern": "simultaneous_update",
                "description": (
                    "{} 个主体在同一天 ({}) 变更信息："
                    "可能由同一控制人统一操作"
                ).format(len(group), start.date().isoformat()),
                "entities": uids,
                "severity": "medium",
            })
        i = j if j > i else i + 1

    return patterns


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def analyze_temporal(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Full temporal analysis: clusters + patterns + coverage.

    Input: entity dicts (as produced by EntityAssociationEngine), each
    optionally carrying a timestamp in `created_at` or inside `context`
    under a known date field.
    """
    if not isinstance(entities, list):
        entities = []
    clusters = analyze_temporal_clusters(entities)
    patterns = detect_temporal_patterns(entities, clusters)
    timed_count = sum(1 for e in entities if entity_time(e) is not None)
    times = [entity_time(e) for e in entities]
    times = [t for t in times if t is not None]
    time_range = None
    if times:
        time_range = {
            "earliest": min(times).date().isoformat(),
            "latest": max(times).date().isoformat(),
        }
    return {
        "clusters": clusters,
        "patterns": patterns,
        "timed_entity_count": timed_count,
        "total_entity_count": len(entities),
        "time_range": time_range,
        "data_boundary": "fully_public",
        "disclaimer": (
            "Temporal proximity is an investigative lead suggesting a "
            "possible common operator; it does not prove common ownership "
            "or control. All timestamps come from public sources only."
        ),
    }
