"""Kuaishou video/profile lookup — offline merchant footprint.

Data boundary: fully_public. No login, no credentials.

Two modes:
1. Share-URL parsing (autonomous): given a Kuaishou share URL
   (v.kuaishou.com/xxx or www.kuaishou.com/short-video/xxx),
   follows redirects and extracts embedded video/author JSON.
   Approach follows wujunwei928/parse-video (URL-only parser).
2. Name search (browser-assisted): Kuaishou web search requires JS
   rendering; query() returns interaction_required with instructions.

Useful for 下沉市场 merchants with strong Kuaishou presence.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re


class KuaishouVideoLookup(SafeResearchAdapter):
    source_domain = "www.kuaishou.com"
    source_type = "video_platform_public_page"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        return keyword  # URL is passed directly

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        return self.parse_share_page(raw_data)

    def query_by_share_url(self, share_url: str) -> dict[str, Any]:
        """Fetch a Kuaishou share URL and extract video/author metadata."""
        if not share_url or "kuaishou" not in share_url:
            return {"status": "invalid_input", "video": None}

        self._check_robots()
        self._enforce_rate_limit()

        import urllib.request

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        req = urllib.request.Request(share_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                final_url = resp.geturl()
        except Exception as e:
            return {"status": "request_failed", "error": str(e)[:200], "video": None}

        video = self.parse_share_page(html)
        video["final_url"] = final_url
        return {"status": "ok" if video.get("photo_id") else "no_data",
                "video": video}

    def parse_share_page(self, html: str) -> dict[str, Any]:
        """Extract video/author fields from a Kuaishou share page HTML."""
        out: dict[str, Any] = {}
        # photoId
        m = re.search(r'"photoId"\s*:\s*"([^"]+)"', html)
        if m:
            out["photo_id"] = m.group(1)
        # caption
        m = re.search(r'"caption"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if m:
            out["caption"] = m.group(1).encode().decode("unicode_escape", errors="ignore")[:500]
        # author
        m = re.search(r'"userName"\s*:\s*"([^"]+)"', html)
        if m:
            out["author"] = m.group(1)
        m = re.search(r'"userId"\s*:\s*(\d+)', html)
        if m:
            out["author_id"] = m.group(1)
        # counts
        for key, field in (("likeCount", "like_count"), ("commentCount", "comment_count"),
                           ("viewCount", "view_count"), ("shareCount", "share_count")):
            m = re.search(rf'"{key}"\s*:\s*(\d+)', html)
            if m:
                out[field] = int(m.group(1))
        # location / POI
        m = re.search(r'"location"\s*:\s*"([^"]+)"', html)
        if m:
            out["location"] = m.group(1)
        return out

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """Name search is browser-assisted (Kuaishou web search needs JS)."""
        if keyword and ("kuaishou.com" in keyword or "v.kuaishou" in keyword):
            return self.query_by_share_url(keyword)
        return {
            "status": "interaction_required",
            "message": (
                "Kuaishou web search requires JavaScript rendering. "
                "Open https://www.kuaishou.com/search/video?searchKey=<keyword> "
                "in a browser, find the merchant's video, copy its share URL, "
                "then call query_by_share_url()."
            ),
            "video": None,
        }
