"""脉脉职业文章检索 — 通过公开文章找人找关联。数据边界: fully_public

Maimai (maimai.cn) is China's professional social network. While personal
profile pages require login, ARTICLE pages are publicly accessible and
contain full author professional info in __NEXT_DATA__ JSON:
  - author name / realname
  - company (主办单位/任职公司)
  - position / career (职位)
  - article full text, likes, views, publish time

For 找人 (people-finding): search articles by company name or person name,
extract author professional info → "XX公司 总经理" type associations.

Technical notes (verified 2026-10-21):
- Article URL: https://maimai.cn/article/detail?fid={fid}&efid={efid}
- Both fid AND efid required (fid alone → 404).
- Article list pages require login; discovery via Bing site: search.
- __NEXT_DATA__ JSON: props.pageProps.data.feed.main.{text,u,html}
- Author: main.u.{name, realname, company, position, career, mmid}
- No CAPTCHA observed; 3s interval enforced.
- Personal profile pages (non-article) require login — NOT covered.

Philosophy: Article authors publish professionally. Name/company/position
in a byline is public professional disclosure, not private data.
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
import json
import time
from urllib.parse import quote, urlparse, parse_qs
from html import unescape


class MaimaiArticleLookup(SafeResearchAdapter):
    """脉脉文章检索：按关键词找职业文章，提取作者公司/职位信息。"""

    source_domain = "maimai.cn"
    source_type = "professional_social"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    _BING = "https://www.sogou.com"

    def _build_url(self, keyword: str, **params) -> str:
        """Build Sogou web search URL for maimai articles."""
        q = quote(f"site:maimai.cn {keyword}")
        return f"https://www.sogou.com/web?query={q}"

    def _build_article_url(self, fid: str, efid: str) -> str:
        return f"https://maimai.cn/article/detail?fid={fid}&efid={efid}"

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse Bing RSS results → article URLs."""
        if not raw_data or "maimai.cn/article/detail" not in raw_data:
            return {"article_count": 0, "articles": []}
        return {"articles": self.parse_search_results(raw_data),
                "article_count": len(self.parse_search_results(raw_data))}

    @staticmethod
    def parse_search_results(html: str) -> list[dict[str, Any]]:
        """Extract maimai article URLs from Sogou web search HTML."""
        articles = []
        seen = set()
        # Sogou: maimai.cn/article/detail?fid=123&amp;efid=xxx
        for m in re.finditer(
            r'maimai\.cn/article/detail\?fid=(\d+)&(?:amp;)?efid=([^"\'&\s]+)',
            html,
        ):
            fid, efid = m.group(1), unescape(m.group(2))
            key = f"{fid}:{efid}"
            if key in seen:
                continue
            seen.add(key)
            articles.append({
                "fid": fid,
                "efid": efid,
                "url": f"https://maimai.cn/article/detail?fid={fid}&efid={efid}",
            })
        return articles

    @staticmethod
    def parse_article(html: str) -> dict[str, Any]:
        """Parse maimai article page __NEXT_DATA__ → author + content.

        Returns dict with: title, text, author{name, company, position,
        mmid}, likes, views, publish_time. Empty dict if unparseable.
        """
        if not html:
            return {}
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.S,
        )
        if not m:
            return {}
        try:
            data = json.loads(m.group(1))
            feed = data["props"]["pageProps"]["data"]["feed"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return {}

        main = feed.get("main", {}) or {}
        author_raw = main.get("u", {}) or {}

        # Strip <dref> tags from title for clean text
        raw_title = feed.get("title", "")
        clean_title = re.sub(r"<dref[^>]*>", "", raw_title)
        clean_title = re.sub(r"</dref>", "", clean_title).strip()

        # Likes may be dict {"n": N} or int
        likes_raw = feed.get("likes", 0)
        likes = likes_raw.get("n", 0) if isinstance(likes_raw, dict) else likes_raw

        return {
            "fid": str(feed.get("id", "")),
            "title": clean_title,
            "text": main.get("text", ""),
            "text_length": len(main.get("text", "")),
            "author": {
                "name": author_raw.get("name", ""),
                "realname": author_raw.get("realname", ""),
                "company": author_raw.get("company", ""),
                "position": author_raw.get("position", "")
                    or author_raw.get("career", ""),
                "mmid": str(author_raw.get("mmid", "")),
            },
            "likes": likes,
            "views": feed.get("dviews", 0) or feed.get("views", 0),
            "publish_time": feed.get("crtime", ""),
            "url": (
                f"https://maimai.cn/article/detail"
                f"?fid={feed.get('id', '')}&efid={feed.get('efid', '')}"
            ),
        }

    def query(self, keyword: str, max_articles: int = 5, **kwargs) -> dict[str, Any]:
        """Two-step: Bing discovery → fetch articles → extract author info.

        Returns articles with author professional info for association mining.
        """
        import hashlib
        import urllib.request

        self._enforce_rate_limit()
        self._check_robots()

        # Step 1: discover via Sogou web search
        search_url = self._build_url(keyword)
        req = urllib.request.Request(search_url, headers={"User-Agent": self._UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            self._record_audit(keyword=keyword, url=search_url,
                              status=0, fields=[])
            return {"article_count": 0, "articles": [],
                    "lookup_status": f"search_failed: {e}"}

        candidates = self.parse_search_results(html)[:max_articles]

        # Step 2: fetch each article
        results = []
        for cand in candidates:
            time.sleep(self.min_request_interval)
            areq = urllib.request.Request(
                cand["url"], headers={"User-Agent": self._UA})
            try:
                with urllib.request.urlopen(areq, timeout=20) as aresp:
                    html = aresp.read().decode("utf-8", errors="ignore")
                parsed = self.parse_article(html)
                if parsed.get("author", {}).get("name"):
                    results.append(parsed)
            except Exception:
                continue

        self._record_audit(
            keyword=keyword, url=search_url, status=200,
            fields=["article_count", "articles"],
        )
        return {
            "query_subject_hash": hashlib.sha256(
                keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "keyword": keyword,
            "article_count": len(results),
            "articles": results,
            "lookup_status": "ok",
        }
