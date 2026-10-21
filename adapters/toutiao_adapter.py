"""今日头条搜索 — 自媒体作者/内容检索适配器。数据边界: fully_public

Toutiao (so.toutiao.com) is ByteDance's news/self-media platform.
For person/entity investigation, this surfaces:
- Self-media author articles mentioning a person/company
- Author names and media accounts from search results
- Article timestamps, read counts

Technical notes (verified 2026-10-21):
- so.toutiao.com/search?format=json returns JSON with rendered HTML in `dom` field
- No login required. Rate limiting is strict (empty responses after ~2-3 rapid requests)
- 10s interval enforced to avoid rate limits
- Author pages (/c/user/) use token anti-scraping — NOT covered
- Article content extraction from search-result HTML only

Association value: articles often mention "XX公司创始人", author bylines
reveal person-company links.

Philosophy: public search results are public information. Extract everything visible.
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
import html as html_module
from urllib.parse import quote


class ToutiaoSearchLookup(SafeResearchAdapter):
    """今日头条搜索：按关键词查相关文章/作者。"""

    source_domain = "so.toutiao.com"
    source_type = "social_media"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 10.0  # strict rate limiting observed

    _BASE = "https://so.toutiao.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def _build_url(self, keyword: str, **params) -> str:
        q = quote(keyword)
        return f"{self._BASE}/search?format=json&keyword={q}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._UA,
            "Referer": f"{self._BASE}/search/?dvpf=pc",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """Parse JSON API response with embedded HTML."""
        if not raw_data:
            return {"article_count": 0, "articles": [], "rate_limited": True}
        try:
            import json
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception:
            return {"article_count": 0, "articles": [], "parse_error": True}

        dom = data.get("dom", "")
        if not dom:
            return {"article_count": 0, "articles": [], "empty_result": True}

        articles = self.parse_search_dom(dom)
        return {
            "article_count": len(articles),
            "articles": articles,
            "total_count": data.get("count", 0),
            "source": "so.toutiao.com",
        }

    @staticmethod
    def parse_search_dom(dom: str) -> list[dict[str, Any]]:
        """Extract articles from the embedded HTML in JSON response."""
        results: list[dict[str, Any]] = []
        if not dom:
            return results
        # Unescape the HTML
        text = html_module.unescape(dom)
        # Find article blocks - toutiao uses various structures
        # Look for title links
        for m in re.finditer(
            r'<a[^>]+href="([^"]*(?:/a\d+|/i\d+)[^"]*)"[^>]*>(.*?)</a>',
            text, re.S
        ):
            url, title_html = m.group(1), m.group(2)
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            if not title or len(title) < 4:
                continue
            # Skip nav/ads
            if any(x in title for x in ["首页", "登录", "注册", "下载"]):
                continue
            # Get context around this link for author/source info
            pos = m.start()
            chunk = text[max(0, pos - 500):pos + 2000]
            # Author/source - often in nearby spans
            author = ""
            author_m = re.search(
                r'(?:来源|作者)[：:]\s*([^<>\s]{2,20})', chunk
            )
            if author_m:
                author = author_m.group(1).strip()
            # Time
            time_str = ""
            time_m = re.search(r'(\d{4}-\d{2}-\d{2}[ \d:]*)', chunk)
            if time_m:
                time_str = time_m.group(1)

            results.append({
                "title": title[:200],
                "url": url if url.startswith("http") else f"https://www.toutiao.com{url}",
                "author": author,
                "publish_time": time_str,
            })
            if len(results) >= 20:
                break
        return results

    def query_by_author(self, author_name: str, **params) -> dict[str, Any]:
        """Search for articles by a specific author name."""
        return self.query(f"{author_name} 头条号", **params)
