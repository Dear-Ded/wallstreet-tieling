"""豆瓣小组搜索 — 线下商业/关联深挖适配器。数据边界: fully_public

Douban (douban.com) groups are a major Chinese-language discussion platform.
For offline businesses (个体工商户/小店) and entity association, this surfaces:
- Groups dedicated to a business/brand (e.g. 海底捞小组)
- Group discussion topics mentioning businesses, owners, relationships
- User-generated reviews, 曝光 posts, 探店 notes

Association value (per user directive): discussion content often exposes
"这家店老板是XX", "XX和XX是夫妻店", franchise/ownership relationships —
exactly the 关联信息 the entity-association engine consumes.

Technical notes (verified 2026-10-21):
- Group search (cat=1019) is server-rendered HTML — no JS needed.
- Group topic lists use <table class="olt"> — server-rendered.
- General /search is JS-rendered (BYWATER) — NOT covered.
- No login required for group search or public group topic lists.
- No CAPTCHA observed for moderate use; 3s interval enforced.
- Philosophy: public posts are public information. Extract everything visible.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
from urllib.parse import quote


class DoubanGroupLookup(SafeResearchAdapter):
    """豆瓣小组搜索：按关键词找相关小组。"""

    source_domain = "www.douban.com"
    source_type = "social_discussion"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://www.douban.com"

    def _build_url(self, keyword: str, **params) -> str:
        q = quote(keyword)
        return f"{self._BASE}/group/search?cat=1019&q={q}"

    def _build_headers(self) -> dict:
        # Douban blocks the default research UA; use a browser UA.
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse server-rendered group search HTML."""
        if not raw_data:
            return {"group_count": 0, "groups": []}
        groups = self.parse_group_list(raw_data)
        return {
            "group_count": len(groups),
            "groups": groups,
        }

    @staticmethod
    def parse_group_list(html: str) -> list[dict[str, Any]]:
        """Extract groups from search result HTML.

        Returns: [{group_id, name, url}]
        """
        groups: list[dict[str, Any]] = []
        seen: set[str] = set()
        for m in re.finditer(
            r'href="(https://www\.douban\.com/group/(\d+)/)"[^>]*>([^<]{2,60})</a>',
            html,
        ):
            url, gid, name = m.group(1), m.group(2), m.group(3).strip()
            if gid in seen or name in ("讨论精选", "热门小组", "豆瓣小组"):
                continue
            seen.add(gid)
            groups.append({"group_id": gid, "name": name, "url": url})
        return groups

    @staticmethod
    def parse_group_topics(html: str, max_topics: int = 25) -> list[dict[str, Any]]:
        """Extract discussion topics from a group page's <table class="olt">.

        Returns: [{topic_id, title, url, author, reply_count}]
        Public topic titles often contain business intel
        (e.g. "XX店老板跑路了", "XX和XX是夫妻店").
        """
        topics: list[dict[str, Any]] = []
        m = re.search(r'<table class="olt">(.*?)</table>', html, re.S)
        if not m:
            return topics
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S)
        for row in rows[1:max_topics + 1]:  # skip header
            tm = re.search(
                r'href="https://www\.douban\.com/group/topic/(\d+)/[^"]*"[^>]*title="([^"]+)"',
                row,
            )
            if tm:
                topic_id, title = tm.group(1), tm.group(2).strip()
            else:
                tm2 = re.search(
                    r'href="(https://www\.douban\.com/group/topic/(\d+)/)[^"]*"[^>]*>([^<]{3,100})<',
                    row,
                )
                if not tm2:
                    continue
                topic_id, title = tm2.group(2), tm2.group(3).strip()
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            author: str | None = None
            reply_count: str | None = None
            if len(cells) >= 2:
                author = re.sub(r"<[^>]+>", "", cells[1]).strip() or None
            if len(cells) >= 3:
                rc = re.sub(r"<[^>]+>", "", cells[2]).strip()
                reply_count = rc if rc.isdigit() else None
            topics.append({
                "topic_id": topic_id,
                "title": title,
                "url": f"https://www.douban.com/group/topic/{topic_id}/",
                "author": author,
                "reply_count": reply_count,
            })
        return topics

    def query_group_topics(
        self, group_id: str, max_topics: int = 25
    ) -> dict[str, Any]:
        """Fetch a group's recent discussion topics (public, no login)."""
        self._enforce_rate_limit()
        robots_ok = self._check_robots()
        if not robots_ok:
            return {"group_id": group_id, "topic_count": 0, "topics": [],
                    "error": "robots_txt_disallowed"}
        url = f"{self._BASE}/group/{group_id}/"
        status, raw, error = self._execute_query(url, self._build_headers())
        topics = self.parse_group_topics(raw or "", max_topics=max_topics)
        self._record_audit(
            keyword=f"group:{group_id}", url=url, status=status,
            fields=["topic_count", "topics"], robots_allowed=robots_ok,
        )
        return {
            "group_id": group_id,
            "topic_count": len(topics),
            "topics": topics,
            "source_domain": self.source_domain,
            "error": error or None,
        }
