"""搜狗微信搜索 — 微信公众号文章搜索适配器。数据边界: fully_public

Sogou WeChat search (weixin.sogou.com) indexes WeChat public-account articles.
For offline businesses (个体工商户/小店), this surfaces: 探店 reviews,
opening announcements, promotions, menus — public marketing footprints.

Technical notes (verified 2026-10-21):
- Homepage visit first to obtain SUID cookie, then search with cookie jar.
- Article search (type=2) is server-rendered HTML — no JS execution needed.
- Account search (type=1) is AJAX-loaded — not covered by this adapter.
- Results: 10/page, pagination via &page=N works.
- Timestamps are Unix epoch in timeConvert('...') JS calls.
- Article links go through Sogou /link?url= redirect (not resolved here).
- No CAPTCHA observed for moderate use; 3s interval enforced.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote


class SogouWxArticleLookup(SafeResearchAdapter):
    """搜狗微信文章搜索：按关键词查微信公众号文章。"""

    source_domain = "weixin.sogou.com"
    source_type = "search_engine_index"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://weixin.sogou.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def _build_url(self, keyword: str, **params) -> str:
        page = params.get("page", 1)
        q = quote(keyword)
        return f"{self._BASE}/weixin?query={q}&type=2&page={page}"

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse server-rendered article list HTML."""
        if not raw_data or "<h3" not in raw_data:
            return {"article_count": 0, "articles": []}
        articles = self.parse_article_list(raw_data)
        return {
            "article_count": len(articles),
            "articles": articles,
            "source": "weixin.sogou.com",
            "search_type": "wechat_article",
        }

    @staticmethod
    def parse_article_list(html: str) -> list[dict[str, Any]]:
        """Extract articles from Sogou WeChat search result HTML."""
        results: list[dict[str, Any]] = []
        h3_blocks = re.findall(r"<h3[^>]*>(.*?)</h3>", html, re.S)
        for h in h3_blocks:
            # Title (strip <em> highlight tags)
            title = re.sub(r"<[^>]+>", "", h).strip()
            if not title or len(title) < 2:
                continue
            # Position of this h3 in the document for context lookup
            pos = html.find(h)
            chunk = html[pos:pos + 3000]
            # Summary
            summ_m = re.search(
                r'<p class="txt-info"[^>]*>(.*?)</p>', chunk, re.S
            )
            summary = (
                re.sub(r"<[^>]+>", "", summ_m.group(1)).strip()[:300]
                if summ_m
                else ""
            )
            # Account name
            acct_m = re.search(
                r'<span class="all-time-y2">([^<]{2,60})</span>', chunk
            )
            account = acct_m.group(1).strip() if acct_m else ""
            # Publish time (Unix timestamp in timeConvert('...'))
            ts_m = re.search(r"timeConvert\('(\d{10})'\)", chunk)
            published = ""
            if ts_m:
                try:
                    dt = datetime.fromtimestamp(
                        int(ts_m.group(1)), tz=timezone.utc
                    )
                    published = dt.strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    pass
            # Sogou redirect link (article URL behind /link?url=)
            link_m = re.search(r'href="(/link\?url=[^"]{10,200})"', h)
            sogou_link = link_m.group(1)[:200] if link_m else ""
            results.append(
                {
                    "title": title,
                    "account": account,
                    "published_date": published,
                    "summary": summary,
                    "sogou_link": sogou_link,
                }
            )
        return results

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """Search WeChat articles. Handles cookie session automatically."""
        import requests

        max_pages = min(params.get("max_pages", 1), 5)
        all_articles: list[dict[str, Any]] = []
        session = requests.Session()
        session.headers.update({"User-Agent": self._UA})
        try:
            # Step 1: homepage to obtain SUID cookie
            session.get(f"{self._BASE}/", timeout=15)
            # Step 2: paginated article search
            for page in range(1, max_pages + 1):
                if page > 1:
                    time.sleep(self.min_request_interval)
                url = self._build_url(keyword, page=page)
                resp = session.get(url, timeout=20)
                if resp.status_code != 200:
                    break
                resp.encoding = "utf-8"
                articles = self.parse_article_list(resp.text)
                if not articles:
                    break
                all_articles.extend(articles)
                if len(articles) < 10:
                    break  # last page
        except Exception as e:
            return {
                "query": keyword,
                "article_count": len(all_articles),
                "articles": all_articles,
                "lookup_status": "lookup_failed",
                "error": str(e)[:200],
            }
        self._check_robots()
        self._record_audit(
            keyword=keyword,
            url=self._build_url(keyword),
            status=200 if all_articles else 0,
            fields=["title", "account", "published_date", "summary"],
        )
        return {
            "query": keyword,
            "article_count": len(all_articles),
            "articles": all_articles,
            "lookup_status": "ok" if all_articles else "no_results",
            "source": "weixin.sogou.com",
        }
