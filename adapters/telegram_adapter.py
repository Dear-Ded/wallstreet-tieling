"""Telegram 公开频道检索 — t.me/s/ 网页预览适配器。数据边界: fully_public

Telegram's official public preview (t.me/s/{channel}) renders the latest
messages of any public channel/group as server-side HTML — no login needed.
This is a standard OSINT source for: business announcements, whistleblower
leaks ("XX公司爆料"), missing-person/business-owner lookups ("找XX老板").

Technical notes (verified 2026-10-21):
- https://t.me/s/{username} returns HTTP 200 with ~20 latest messages.
- Pagination: ?before={post_id} loads older messages (post_id from data-post).
- Channel title: tgme_channel_info_header_title; subscribers: counter_value.
- Message fields: text (js-message_text), <time datetime>, views, data-post id.
- Nonexistent/private channel: HTTP 200 but zero message wraps -> channel_found=False.
- No CAPTCHA, no login, no JS execution needed. 3s interval enforced.
- t.me has no robots.txt (404) — default allow per base-class policy.

Association value: TG channels frequently carry "找人/找公司/爆料" posts
that name businesses, owners, phones — direct leads for entity association.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
import html as html_lib
from urllib.parse import quote


class TelegramChannelLookup(SafeResearchAdapter):
    """Telegram 公开频道检索：按频道 username 抓取最近公开消息。"""

    source_domain = "t.me"
    source_type = "social_messaging_public"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://t.me"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def _build_url(self, keyword: str, **params) -> str:
        username = keyword.strip().lstrip("@").split("/")[-1]
        before = params.get("before")
        q = quote(username, safe="")
        url = f"{self._BASE}/s/{q}"
        if before:
            url += f"?before={quote(str(before), safe='')}"
        return url

    def _build_headers(self) -> dict:
        return {"User-Agent": self._UA}

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        if not raw_data:
            return {"channel_found": False, "message_count": 0, "messages": []}
        channel = self.parse_channel_page(raw_data)
        channel["source"] = "t.me"
        channel["preview_type"] = "public_channel_preview"
        return channel

    # -- parsing ---------------------------------------------------------

    @staticmethod
    def _clean_text(html_fragment: str) -> str:
        """Strip tags, unescape entities, collapse whitespace."""
        text = re.sub(r"<br\s*/?>", "\n", html_fragment)
        text = re.sub(r"<[^>]+>", "", text)
        text = html_lib.unescape(text)
        text = re.sub(r"[ \t\xa0]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def parse_channel_page(cls, html: str) -> dict[str, Any]:
        """Parse a t.me/s/{channel} preview page into structured data."""
        # Channel title
        title_m = re.search(
            r'tgme_channel_info_header_title[^"]*"><span[^>]*>(.*?)</span>',
            html, re.S,
        )
        title = cls._clean_text(title_m.group(1)) if title_m else ""

        # Subscriber/member counter
        sub_m = re.search(
            r'counter_value">([^<]+)</span>.*?<span class="counter_type">([^<]+)</span>',
            html, re.S,
        )
        subscribers = f"{sub_m.group(1).strip()} {sub_m.group(2).strip()}" if sub_m else ""

        # Description (may be absent)
        desc_m = re.search(
            r'tgme_channel_info_description[^"]*">(.*?)</div>', html, re.S,
        )
        description = cls._clean_text(desc_m.group(1))[:500] if desc_m else ""

        messages = cls.parse_messages(html)

        return {
            "channel_found": bool(messages) or bool(title),
            "channel_title": title,
            "subscribers": subscribers,
            "description": description,
            "message_count": len(messages),
            "messages": messages,
        }

    @classmethod
    def parse_messages(cls, html: str) -> list[dict[str, Any]]:
        """Extract individual messages from a preview page."""
        results: list[dict[str, Any]] = []
        blocks = re.findall(
            r'tgme_widget_message_wrap js-widget_message_wrap(.*?)'
            r'<!--/?tgme_widget_message_wrap',
            html, re.S,
        )
        # Fallback: split on the wrap div if comment markers absent
        if not blocks:
            parts = html.split('<div class="tgme_widget_message_wrap js-widget_message_wrap"')
            blocks = parts[1:] if len(parts) > 1 else []
        for b in blocks:
            # Post id: data-post="channel/123"
            post_m = re.search(r'data-post="([^"]+)"', b)
            post_id = post_m.group(1) if post_m else ""
            # Text
            text_m = re.search(
                r'tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>',
                b, re.S,
            )
            text = cls._clean_text(text_m.group(1)) if text_m else ""
            # Datetime
            dt_m = re.search(r'<time datetime="([^"]+)"', b)
            published = dt_m.group(1) if dt_m else ""
            # Views
            views_m = re.search(
                r'tgme_widget_message_views">([^<]+)</span>', b,
            )
            views = views_m.group(1).strip() if views_m else ""
            # Author (usually channel name; groups show sender)
            author_m = re.search(
                r'tgme_widget_message_from_author"[^>]*>(.*?)</span>', b, re.S,
            )
            author = cls._clean_text(author_m.group(1)) if author_m else ""
            # Linkback
            link = f"https://t.me/{post_id}" if post_id else ""
            if not text and not post_id:
                continue
            results.append({
                "post_id": post_id,
                "text": text[:2000],
                "published_at": published,
                "views": views,
                "author": author,
                "link": link,
            })
        return results

    # -- convenience ------------------------------------------------------

    def query_channel(self, username: str, before: str = "") -> dict[str, Any]:
        """Fetch a public channel's recent messages (alias for query)."""
        return self.query(username, before=before)
