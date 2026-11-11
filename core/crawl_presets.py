#!/usr/bin/env python3
"""Source presets for :mod:`core.crawl_runtime`.

* ``xueqiu`` — Xueqiu (雪球) public stock quote + symbol discussion JSON, the
  data XueQiuSuperSpider collects. Uses the normal landing-page visit to obtain
  the anonymous session cookie (what a browser does); no login, no credential
  files, no signature tricks. Blocks/challenges become handoff gaps.
* ``site_links`` — bounded same-site link follower that emits page records
  (title, description, outbound links) for public company websites.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from typing import Any, Iterable

from core.crawl_runtime import (
    CrawlRequest,
    CrawlRun,
    DomainThrottle,
    FetchResponse,
    MapperOutput,
    RetryPolicy,
    SessionPool,
    dedupe_items,
    standardize_item,
)

XUEQIU_HOME = "https://xueqiu.com/"
XUEQIU_QUOTE = "https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}&extend=detail"
XUEQIU_DISCUSSION = "https://xueqiu.com/query/v1/symbol/search/status.json?symbol={symbol}&count={count}&page={page}&sort=time"


def xueqiu_symbol(code: str) -> str:
    """600519 -> SH600519, 000001 -> SZ000001, 830799 -> BJ830799, AAPL/00700 passthrough."""
    raw = code.strip().upper()
    if raw[:2] in {"SH", "SZ", "BJ"} or not raw.isdigit():
        return raw
    if len(raw) == 6:
        if raw.startswith(("6", "9")):
            return "SH" + raw
        if raw.startswith(("4", "8")):
            return "BJ" + raw
        return "SZ" + raw
    return raw


def xueqiu_quote_mapper(req: CrawlRequest, resp: FetchResponse) -> MapperOutput:
    data = json.loads(resp.body or "{}")
    if data.get("error_code") not in (0, None):
        raise ValueError(f"xueqiu error_code={data.get('error_code')}: {data.get('error_description')}")
    quote = ((data.get("data") or {}).get("quote")) or {}
    if not quote:
        raise ValueError("xueqiu quote payload missing data.quote")
    symbol = str(quote.get("symbol") or req.user_data.get("symbol") or "")
    fields = {k: quote.get(k) for k in (
        "symbol", "code", "name", "exchange", "currency", "current", "percent", "chg", "open", "high", "low",
        "last_close", "volume", "amount", "market_capital", "float_market_capital", "total_shares",
        "pe_ttm", "pe_lyr", "pb", "dividend_yield", "turnover_rate", "high52w", "low52w", "timestamp",
        "issue_date", "pledge_ratio", "goodwill_in_net_assets") if k in quote}
    item = {
        "source_name": "crawler_xueqiu_quote",
        "source_hint": "crawler_xueqiu_quote",
        "record_type": "market_quote_snapshot",
        "url": req.url,
        "entity": req.user_data.get("entity") or quote.get("name") or symbol,
        "title": f"{quote.get('name') or symbol} ({symbol}) quote",
        "summary": f"current={quote.get('current')} percent={quote.get('percent')} market_capital={quote.get('market_capital')}",
        "confidence": 0.75,
        "fields": fields,
        "entities": [{"kind": "listed_security", "name": quote.get("name") or symbol, "symbol": symbol,
                      "relation": "quote_subject", "confidence": 0.75}],
    }
    return MapperOutput(items=[item])


def xueqiu_discussion_mapper(req: CrawlRequest, resp: FetchResponse) -> MapperOutput:
    data = json.loads(resp.body or "{}")
    posts = data.get("list") or []
    items: list[dict[str, Any]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        user = post.get("user") or {}
        text = re.sub(r"<[^>]+>", "", html.unescape(str(post.get("text") or post.get("description") or "")))
        post_id = post.get("id")
        user_id = user.get("id") or post.get("user_id")
        items.append({
            "source_name": "crawler_xueqiu_discussion",
            "source_hint": "crawler_xueqiu_discussion",
            "record_type": "public_opinion_post",
            "entity": req.user_data.get("entity") or req.user_data.get("symbol", ""),
            "title": str(post.get("title") or text[:60]),
            "summary": text[:1000],
            "url": f"https://xueqiu.com/{user_id}/{post_id}" if user_id and post_id else "",
            "published_at": post.get("created_at"),
            "confidence": 0.55,
            "post": {"id": post_id, "retweet_count": post.get("retweet_count"), "reply_count": post.get("reply_count"),
                     "like_count": post.get("like_count") or post.get("fav_count"), "source": post.get("source")},
            "author": {"user_id": user_id, "screen_name": user.get("screen_name"), "description": user.get("description"),
                       "followers_count": user.get("followers_count"), "verified": user.get("verified"),
                       "verified_description": user.get("verified_description"), "province": user.get("province"),
                       "city": user.get("city"), "gender": user.get("gender"),
                       "profile_url": f"https://xueqiu.com/u/{user_id}" if user_id else ""},
            "entities": [{"kind": "online_account", "platform": "xueqiu", "name": user.get("screen_name"),
                          "user_id": user_id, "relation": "discussed_subject", "confidence": 0.5}],
        })
    out = MapperOutput(items=items)
    page = int(req.user_data.get("page", 1))
    max_pages = int(req.user_data.get("max_pages", 1))
    if posts and page < max_pages:
        symbol = req.user_data["symbol"]
        count = int(req.user_data.get("count", 20))
        out.requests.append(CrawlRequest(
            url=XUEQIU_DISCUSSION.format(symbol=symbol, count=count, page=page + 1), label="xueqiu_discussion",
            user_data={**req.user_data, "page": page + 1}))
    return out


def build_xueqiu_run(codes: Iterable[str], *, entity: str = "", discussion_pages: int = 1, count: int = 20,
                     **kwargs: Any) -> CrawlRun:
    """Collector for Xueqiu quote + discussion pages (XueQiuSuperSpider-style)."""
    kwargs.setdefault("throttle", DomainThrottle(min_delay=1.5, max_delay=30.0))
    kwargs.setdefault("retry", RetryPolicy(max_retries=3, base_delay=1.0))
    kwargs.setdefault("session_pool", SessionPool(max_pool_size=2))
    kwargs.setdefault("obey_robots", False)  # JSON API endpoints; robots.txt governs HTML crawling
    run = CrawlRun(
        name="xueqiu",
        mappers={"xueqiu_quote": xueqiu_quote_mapper, "xueqiu_discussion": xueqiu_discussion_mapper},
        item_pipelines=[dedupe_items(("record_type", "url", "title")), standardize_item],
        allowed_domains=("xueqiu.com",),
        warmup_urls={"stock.xueqiu.com": XUEQIU_HOME, "xueqiu.com": XUEQIU_HOME},
        source_type="crawler_financial_community",
        **kwargs,
    )
    seeds: list[CrawlRequest] = []
    for code in codes:
        symbol = xueqiu_symbol(code)
        meta = {"symbol": symbol, "entity": entity or symbol}
        seeds.append(CrawlRequest(url=XUEQIU_QUOTE.format(symbol=symbol), label="xueqiu_quote", user_data=meta))
        if discussion_pages > 0:
            seeds.append(CrawlRequest(url=XUEQIU_DISCUSSION.format(symbol=symbol, count=count, page=1),
                                      label="xueqiu_discussion",
                                      user_data={**meta, "page": 1, "max_pages": discussion_pages, "count": count}))
    run.collect(seeds)
    return run


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', re.I)
_HREF = re.compile(r'href=["\']([^"\'#]+)', re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})(?!\d)")


def site_links_mapper(req: CrawlRequest, resp: FetchResponse) -> MapperOutput:
    body = resp.body or ""
    title = html.unescape((_TITLE.search(body).group(1) if _TITLE.search(body) else "").strip())
    desc = html.unescape(_DESC.search(body).group(1)) if _DESC.search(body) else ""
    base = resp.url or req.url
    host = urllib.parse.urlsplit(base).netloc.lower()
    links = []
    for href in _HREF.findall(body):
        absolute = urllib.parse.urljoin(base, href.strip())
        if absolute.startswith(("http://", "https://")):
            links.append(absolute)
    internal = [u for u in links if urllib.parse.urlsplit(u).netloc.lower() == host]
    external = sorted({urllib.parse.urlsplit(u).netloc.lower() for u in links} - {host})
    text = re.sub(r"<[^>]+>", " ", body)
    item = {
        "source_name": "crawler_site_page",
        "source_hint": "crawler_site_page",
        "record_type": "public_web_page",
        "url": base,
        "entity": req.user_data.get("entity") or host,
        "title": title or base,
        "summary": desc,
        "confidence": 0.6,
        "page": {"host": host, "internal_link_count": len(internal), "external_domains": external[:50],
                 "emails": sorted(set(_EMAIL.findall(text)))[:50], "phones": sorted(set(_PHONE.findall(text)))[:50]},
    }
    children = [CrawlRequest(url=u, label=req.label, user_data=req.user_data) for u in dict.fromkeys(internal)]
    return MapperOutput(items=[item], requests=children)


def build_site_crawl(start_urls: Iterable[str], *, entity: str = "", max_depth: int = 2, **kwargs: Any) -> CrawlRun:
    urls = list(start_urls)
    domains = sorted({urllib.parse.urlsplit(u).netloc.lower() for u in urls})
    run = CrawlRun(name="site_links", mappers={"site": site_links_mapper},
                   item_pipelines=[dedupe_items(("url",)), standardize_item],
                   allowed_domains=domains, max_depth=max_depth, source_type="crawler_public_page", **kwargs)
    run.collect(CrawlRequest(url=u, label="site", user_data={"entity": entity or domains[0]}) for u in urls)
    return run


PRESETS = {"xueqiu": build_xueqiu_run, "site_links": build_site_crawl}
