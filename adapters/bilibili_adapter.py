"""Bilibili video search — offline merchant footprint (探店/探店 videos).

Data boundary: fully_public. No login, no credentials.
Uses the public web search API (api.bilibili.com/x/web-interface/search/type),
the same endpoint the Bilibili website itself calls. Respects rate limits
(5s interval); handles WAF 412 gracefully.

Note: Bilibili applies IP-based rate limiting. The adapter backs off on
HTTP 412/429 and reports `rate_limited` instead of failing hard.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import time


class BilibiliVideoSearch(SafeResearchAdapter):
    """Search Bilibili videos by keyword (e.g. merchant name + 探店).

    Returns video list with title, author, play counts, danmaku counts,
    and BV links. Useful for finding 探店 (store-visit) videos about
    offline merchants.
    """

    source_domain = "api.bilibili.com"
    source_type = "video_platform_public_search"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # Bilibili rate-limits aggressively

    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """Search videos. Returns structured results or status dict."""
        if not keyword or not keyword.strip():
            return {"status": "invalid_input", "videos": []}

        self._check_robots()
        self._enforce_rate_limit()

        import urllib.request
        import urllib.parse
        import json

        query_params = {
            "search_type": "video",
            "keyword": keyword.strip(),
            "page": params.get("page", 1),
        }
        url = f"{self.SEARCH_URL}?{urllib.parse.urlencode(query_params)}"
        req = urllib.request.Request(url, headers=self._build_headers())

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return {"status": "request_failed", "error": str(e)[:200], "videos": []}

        # WAF block page (HTML instead of JSON)
        if raw.strip().startswith("<"):
            return {
                "status": "rate_limited",
                "message": "Bilibili WAF blocked this IP temporarily (HTTP 412). Retry later.",
                "videos": [],
            }

        try:
            data = json.loads(raw)
        except Exception:
            return {"status": "parse_failed", "videos": []}

        if data.get("code") != 0:
            return {
                "status": "api_error",
                "code": data.get("code"),
                "message": str(data.get("message", ""))[:200],
                "videos": [],
            }

        results = (data.get("data") or {}).get("result", [])
        videos = [self._extract_video(r) for r in results if isinstance(r, dict)]

        return {
            "status": "ok",
            "keyword": keyword.strip(),
            "video_count": len(videos),
            "videos": videos,
            "source": "bilibili.com",
        }

    def _extract_video(self, r: dict[str, Any]) -> dict[str, Any]:
        import re

        def clean_html(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s or "")

        bvid = r.get("bvid", "")
        return {
            "title": clean_html(r.get("title", "")),
            "author": r.get("author", ""),
            "author_mid": r.get("mid"),
            "bvid": bvid,
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "play_count": r.get("play"),
            "danmaku_count": r.get("danmaku"),
            "duration": r.get("duration", ""),
            "publish_time": r.get("pubdate"),
            "description": clean_html(r.get("description", ""))[:300],
        }

    def _build_url(self, keyword: str, **params) -> str:
        import urllib.parse
        return f"{self.SEARCH_URL}?{urllib.parse.urlencode({'search_type': 'video', 'keyword': keyword})}"

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        # Not used — query() returns structured data directly.
        return {}
