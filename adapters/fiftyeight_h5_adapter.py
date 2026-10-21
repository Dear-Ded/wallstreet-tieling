"""58同城移动端 H5 公开信息适配器 (m.58.com) — 免登录分类信息解析。数据边界: fully_public

Why this adapter exists:
- The desktop web (www.58.com) drops datacenter egress at the TLS/JA3 level:
  302 -> 404.58.com, so server-rendered desktop pages are unreachable
  without a full browser stack.
- The mobile H5 site (m.58.com, iPhone Safari UA) serves category listing
  pages server-rendered with no login: title, layout/area, price, infoid,
  detail link and ad tag are all in the HTML.

Verified 2026-10-21 (single low-frequency probes, no login):
- GET https://m.58.com/ (mobile UA) -> 302 to https://m.58.com/bj/
  (city geo-redirect; the /bj/ landing itself tarpits once, fine on retry).
- GET https://m.58.com/bj/zufang/ (mobile UA) -> 200, ~467KB
  server-rendered, no login wall / captcha markers, ~90 <a class="list-item">
  anchors with infoid, uid, clean detail href, title, addr, price.
- GET https://m.58.com/bj/zufang/<infoid>x.shtml (clean, no query)
  -> 200, ~104KB: title, price key, no login gate. Phone numbers are
  NOT rendered in server HTML (click-to-reveal); not extracted.
- robots.txt (https://m.58.com/robots.txt, fetched 2026-10-21):
    Allow: /shoujidaquan/*
    Disallow: /*?*          <- no query strings allowed: adapter strips all
    Disallow: /sou/*Q*      <- mobile search path is disallowed: adapter does
                               NOT support keyword search on m.58.com.
  Category listing pages (/bj/zufang/ etc.) contain no "?" and are allowed.
  app.58.com (APP API host) -> 302 Tengine redirect; APP API endpoints need
  app-signed requests (device-bound signing, login-linked); not reproducible
  with plain HTTP and NOT attempted. Documented stop: any 58 data that needs
  the APP signature or login ("需用户浏览器代管登录") stays out of scope.

What this adapter does NOT do:
- log in or hold any 58 account state,
- use /sou/ keyword search (robots Disallow),
- attach query strings to any URL (robots Disallow /*?*),
- extract or display phone numbers,
- bypass any verification, captcha, or fingerprint gate.

Association value: rental / second-hand / recruitment listings often carry
merchant names, addresses, and posting identities; listing leads feed
entity-association pipelines the same way other classifieds do.
"""

from __future__ import annotations

import html as html_module
import re
import urllib.request
from typing import Any
from urllib.parse import quote

from adapters.safe_research_adapter import (
    SafeResearchAdapter,
)

_CITY_RE = re.compile(r"^[a-z]{2,20}$")
_CHANNEL_RE = re.compile(r"^[a-z0-9_]{1,40}$")

# Common H5 channel slugs observed on m.58.com. Free-form slugs are accepted
# too, but the whitelist documents the channels that were sanity-checked.
_KNOWN_CHANNELS = frozenset({
    "zufang", "ershoufang", "xinfang", "shangpu", "xiezilou",
    "zhaopin", "jianzhi", "ershouche", "xinche",
    "shenghuofuwu", "bendishenghuo", "jiaoyu", "shouji", "diannao",
    "jiaju", "jiadian", "chongwu", "huangye",
})

_ANCHOR_RE = re.compile(
    r'<a class="list-item"\s+[^>]*?href="(https://m\.58\.com/[a-z]{2,20}/[a-z0-9_]{1,40}/\d+x\.shtml)'
    r'[^"]*"[^>]*>(.*?)</a>',
    re.S,
)
_INFOID_RE = re.compile(r'infoid="(\d+)"')
_TITLE_RE = re.compile(r'<li class="list-item-info-title[^"]*">(.*?)</li>', re.S)
_ADDR_RE = re.compile(r'<span class="list-item-info-addr-text[^"]*">(.*?)</span>', re.S)
_PRICE_RE = re.compile(
    r'<li class="list-item-info-price">.*?<i[^>]*>([\d.]+)</i>\s*([^<]{0,12})', re.S
)
_IMG_RE = re.compile(r'bg-src="(https://pic\d?\.58cdn\.com\.cn[^"]+)"')
_TAG_RE = re.compile(r'<span class="list-item-info-sp-tag">([^<]+)</span>')

_DETAIL_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_DETAIL_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_DETAIL_PRICE_RE = re.compile(r'"price"\s*:\s*"([^"]+)"')
_DETAIL_DESC_RE = re.compile(
    r'<div class="detail-[^"]*desc[^"]*"[^>]*>(.*?)</div>', re.S | re.I
)
_LOGIN_GATE_RE = re.compile(r"404\.58\.com|请登录|安全验证|立即登录")


def _clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class FiftyEightH5Listing(SafeResearchAdapter):
    """58同城移动端 H5：城市+频道公开信息流（租房/二手房/招聘等）免登录解析。"""

    source_domain = "m.58.com"
    source_type = "classifieds"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # conservative; single low-frequency probes

    _UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
    _MAX_DETAIL = 5  # opt-in detail enrichment cap

    # ------------------------------------------------------------------ API

    @staticmethod
    def normalize_city(city: str) -> str | None:
        candidate = (city or "").strip().lower()
        return candidate if _CITY_RE.match(candidate) else None

    @staticmethod
    def normalize_channel(channel: str) -> str | None:
        candidate = (channel or "").strip().lower()
        return candidate if _CHANNEL_RE.match(candidate) else None

    def _build_url(self, keyword: str, **params) -> str:
        city = self.normalize_city(params.get("city", "bj")) or "bj"
        channel = self.normalize_channel(params.get("channel", "zufang")) or "zufang"
        url = f"https://m.58.com/{quote(city)}/{quote(channel)}/"
        assert "?" not in url, "robots.txt disallows query strings on m.58.com"
        return url

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    # -------------------------------------------------------------- parsing

    @staticmethod
    def parse_listing_list(html: str) -> list[dict[str, Any]]:
        """Parse server-rendered H5 listing anchors into structured leads."""
        listings: list[dict[str, Any]] = []
        for href, body in _ANCHOR_RE.findall(html):
            infoid = _INFOID_RE.search(body)  # not used; href is authoritative
            title_m = _TITLE_RE.search(body)
            addr_m = _ADDR_RE.search(body)
            price_m = _PRICE_RE.search(body)
            img_m = _IMG_RE.search(body)
            tag_m = _TAG_RE.search(body)
            listings.append({
                "infoid": href.rstrip(".shtml").split("/")[-1].rstrip("x"),
                "detail_url": href,
                "title": _clean_text(title_m.group(1)) if title_m else "",
                "addr": _clean_text(addr_m.group(1)) if addr_m else "",
                "price": (price_m.group(1) + " " + price_m.group(2).strip()).strip()
                if price_m else "",
                "tag": _clean_text(tag_m.group(1)) if tag_m else "",
                "image": img_m.group(1) if img_m else "",
            })
        return listings

    @staticmethod
    def parse_detail(html: str) -> dict[str, Any]:
        """Parse a clean (query-free) H5 detail page; no phone extraction."""
        if _LOGIN_GATE_RE.search(html):
            return {"login_gated": True}
        title_m = _DETAIL_TITLE_RE.search(html) or _DETAIL_H1_RE.search(html)
        price_m = _DETAIL_PRICE_RE.search(html)
        desc_m = _DETAIL_DESC_RE.search(html)
        return {
            "login_gated": False,
            "title": _clean_text(title_m.group(1))[:160] if title_m else "",
            "price": price_m.group(1) if price_m else "",
            "description": _clean_text(desc_m.group(1))[:600] if desc_m else "",
        }

    # -------------------------------------------------------------- adapter

    def query(self, keyword: str, **params) -> dict[str, Any]:
        detail = params.pop("detail", False)
        result = super().query(keyword, **params)
        if detail and result.get("fields", {}).get("listings"):
            self._enrich_details(result["fields"]["listings"])
        return result

    def _enrich_details(self, listings: list[dict[str, Any]]) -> None:
        headers = self._build_headers()
        for item in listings[: self._MAX_DETAIL]:
            self._enforce_rate_limit()
            status, body, _ = self._execute_query(item["detail_url"], headers)
            if status == 200 and body:
                item["detail"] = self.parse_detail(body)
            else:
                item["detail"] = {"login_gated": status != 200, "error": status}

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        html = raw_data if isinstance(raw_data, str) else ""
        if _LOGIN_GATE_RE.search(html):
            return {"blocked": True, "listings": []}
        listings = self.parse_listing_list(html)
        return {
            "blocked": False,
            "listings": listings,
            "listing_count": len(listings),
        }
