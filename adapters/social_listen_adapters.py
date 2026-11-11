#!/usr/bin/env python3
"""Social/tech-listening adapters for public-opinion and technical-signal intel.

NEWS_PUBLIC_OPINION / SOCIAL_WEB 线: 用公开技术社区的讨论信号回答 —
1. 目标公司/技术在 Hacker News 上被讨论过多少次、热度如何？(hn.algolia.com)
2. 目标技术在 Stack Overflow 上有哪些高票问答、是否活跃？(api.stackexchange.com)

Both are free, credential-free public APIs. Default-off, EXPERIMENTAL
in the connector registry. No credentials, no scraping of private state —
only the services' own public search APIs.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class HackerNewsAlgoliaSearch(SafeResearchAdapter):
    """Hacker News full-text search via the official Algolia API.

    回答：关键词在 HN 上的 story 命中数、每条标题/链接/热度/评论数/作者/发布时间。
    HN 是技术圈舆情与技术信号的重要来源；讨论热度是公众关注度的公开代理指标。
    """

    source_domain = "hn.algolia.com"
    source_type = "social_tech_community_search"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        hits = max(1, min(int(params.get("hitsPerPage", 10)), 50))
        return f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage={hits}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        hits = data.get("hits", []) or []
        stories: list[dict[str, Any]] = []
        for hit in hits[:10]:
            if not isinstance(hit, dict):
                continue
            stories.append({
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "points": hit.get("points", 0),
                "num_comments": hit.get("num_comments", 0),
                "author": hit.get("author", ""),
                "created_at": hit.get("created_at", ""),
            })
        return {
            "total_hits": data.get("nbHits", len(stories)),
            "stories": stories,
            "data_note": "Hacker News 公开 Algolia 搜索 — 技术社区讨论信号",
        }


class StackExchangeSearch(SafeResearchAdapter):
    """Stack Overflow question search via the public Stack Exchange API.

    回答：关键词相关的 Stack Overflow 问题 — 标题/链接/得分/回答数/是否已解决/创建时间。
    高票已解决问题反映技术成熟度与社区支持度；提问活跃度反映技术热度。
    免费层无需 key（有默认配额）；本适配器 3s 间隔远低于限额。
    """

    source_domain = "api.stackexchange.com"
    source_type = "social_tech_community_search"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        return (
            "https://api.stackexchange.com/2.3/search"
            f"?order=desc&sort=activity&intitle={query}&site=stackoverflow"
        )

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        items = data.get("items", []) or []
        questions: list[dict[str, Any]] = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            questions.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "score": item.get("score", 0),
                "answer_count": item.get("answer_count", 0),
                "is_answered": bool(item.get("is_answered", False)),
                "creation_date": item.get("creation_date", 0),
            })
        return {
            "total_questions": len(items),
            "has_more": bool(data.get("has_more", False)),
            "quota_remaining": data.get("quota_remaining"),
            "questions": questions,
            "data_note": "Stack Overflow 公开 API — 技术问答信号",
        }
