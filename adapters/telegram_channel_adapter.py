"""Telegram 公开频道/群组情报 — t.me/s/<handle> 公开预览页解析适配器。数据边界: fully_public

Telegram offers a public, login-free channel preview at https://t.me/s/<handle>
(server-rendered HTML, the same page you see when you share a channel link).
This adapter parses that preview only. It does NOT:
- log in or use any Telegram account / Bot API session,
- touch private groups, private chats, invite links, or members-only content,
- bypass any verification, captcha, or rate gate.

Verified 2026-10-21:
- GET https://t.me/s/durov -> 200, server-rendered: channel title, description,
  subscriber counter ("10.3M subscribers"), ~20 recent posts with text,
  <time datetime=...> timestamps, per-post URLs, view counts, media flags.
- Nonexistent / private handle: 302 redirect to https://t.me/<handle> (no /s/),
  which is treated as "no public preview" — never followed blindly.
- tgstat.com keyword search: 429 + auth wall from server egress. Dead end.
- telemetr.io: 301 auth redirect. Dead end.
- DuckDuckGo html endpoint: timed out from this egress. Dead end.
- Bing: RSS ignores site: operator; HTML SERP shows no t.me result links
  from datacenter egress. Dead end.
=> Keyword discovery is limited to direct handle resolution
   (query("durov") resolves to t.me/s/durov). No handle guessing from
   web search: an invalid handle returns a structured "not found".

tgstat excavation (2026-10-21, frontend JS bundle reverse):
- Search page inline script: new TopSearch({requestUrl: '/channels/global-search'}).
- app.js TopSearch class: POST /channels/global-search, data={query: <text>},
  expects JSON {"status": "ok", "html": "..."}.
- Plain-HTTP reproduction WITH session cookie + CSRF token:
  POST /channels/global-search -> {"status":"restricted",
  "html":"...Authentication Required...Please log in to continue using TGStat"}.
- POST /search (form: _tgstat_csrk + q) -> HTML "Sign in to access this page".
- POST /channels/search XHR (_tgstat_csrk + q) -> same restricted JSON;
  form-style POST -> re-renders the search form, no results.
  Conclusion: all tgstat SEARCH endpoints are login-walled. No login
  attempted (red line); no captcha bypass attempted. Documented stop.
- PUBLIC and usable: GET /channel/@<handle> -> 200, server-rendered
  (robots.txt allows it): exact subscriber count, channel description
  (meta), and the owner's other/related channel handles rendered as
  @-buttons under the <h1> (discovery route: seed handle -> related handles).
  This adapter exposes it as opt-in enrichment (enrich=True):
  fields["tgstat"] = {subscribers_exact, description, related_handles}.

Association value: public channel posts often mention companies, founders,
events, and announcements; channel name/description/subscriber counts
identify official vs. impostor channels; related handles reveal an
owner's other public channels.
"""

from __future__ import annotations

import hashlib
import html as html_module
import re
import time
import urllib.request
from typing import Any
from urllib.parse import quote

from adapters.safe_research_adapter import (
    ResearchAuditRecord,
    SafeResearchAdapter,
)


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    """Records redirect targets while still following them."""

    def __init__(self) -> None:
        self.final_url: str | None = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.final_url = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_HANDLE_RE = re.compile(r"^[a-z0-9_]{4,32}$")


class TelegramChannelLookup(SafeResearchAdapter):
    """Telegram 公开频道/群组：t.me/s/<handle> 公开预览页解析。"""

    source_domain = "t.me"
    source_type = "social_media"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # conservative; public preview page

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    _TGSTAT_UA = _UA
    _TGSTAT_BASE = "https://tgstat.com"
    _TGSTAT_INTERVAL = 5.0  # conservative, public page

    # ------------------------------------------------------------------ API

    @staticmethod
    def normalize_handle(keyword: str) -> str | None:
        """Keyword -> plausible public channel handle, or None."""
        candidate = (keyword or "").strip().lstrip("@").lower()
        if _HANDLE_RE.match(candidate):
            return candidate
        return None

    def query(self, keyword: str, **params) -> dict[str, Any]:
        enrich = params.pop("enrich", False)
        handle = params.pop("handle", None) or self.normalize_handle(keyword)
        if not handle:
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "handle_invalid")
        self._last_handle = handle
        result = super().query(keyword, **params)
        if enrich and result.get("fields", {}).get("channel_found"):
            tg = self.enrich_with_tgstat(handle)
            if tg:
                result["fields"]["tgstat"] = tg
                result["field_count"] = len(result["fields"])
        return result

    def query_channel(self, handle: str, **params) -> dict[str, Any]:
        """Explicit-handle lookup: query_channel("durov") -> recent posts.

        Pass enrich=True to also pull tgstat.com public channel metadata
        (exact subscriber count, related handles).
        """
        normalized = self.normalize_handle(handle)
        if not normalized:
            self._record_audit(keyword=handle, url="", status=0, fields=[])
            return self._build_empty_result(handle, "handle_invalid")
        return self.query(handle, handle=normalized, **params)

    # -------------------------------------------- tgstat public enrichment

    def enrich_with_tgstat(self, handle: str) -> dict[str, Any] | None:
        """Public tgstat.com channel page -> exact subs + related handles.

        GET https://tgstat.com/channel/@<handle>: 200, server-rendered,
        robots.txt allows it, no login. Returns None on any failure.
        """
        now = time.monotonic()
        last = getattr(self, "_tgstat_last", 0.0)
        wait = self._TGSTAT_INTERVAL - (now - last)
        if wait > 0:
            self._sleeper(wait)
        url = f"{self._TGSTAT_BASE}/channel/@{handle}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self._TGSTAT_UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    return None
                body = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None
        finally:
            self._tgstat_last = time.monotonic()
        self.audit.log(ResearchAuditRecord(
            operation_type="public_record_query",
            source_domain="tgstat.com",
            source_type=self.source_type,
            access_method="standard_http_get",
            rate_limit_applied=f"{self._TGSTAT_INTERVAL}s",
            query_params_hash=hashlib.sha256(handle.encode()).hexdigest()[:12],
            response_status=200,
            fields_extracted=["tgstat"],
            data_boundary=self.data_boundary,
        ))
        return self.parse_tgstat_channel(body, handle)

    @staticmethod
    def parse_tgstat_channel(body: str, own_handle: str) -> dict[str, Any]:
        """Parse tgstat.com public channel page."""
        out: dict[str, Any] = {"source": "tgstat.com", "handle": own_handle}
        m = re.search(r'<meta name="description" content="([^"]{0,500})"', body)
        if m:
            out["description"] = html_module.unescape(m.group(1)).strip() or None
        m = re.search(
            r'<h2 class="mb-1 text-dark">([\d ]+)</h2>\s*'
            r'<div class="text-uppercase[^"]*">\s*subscribers',
            body,
        )
        if m:
            try:
                out["subscribers_exact"] = int(m.group(1).replace(" ", ""))
            except ValueError:
                pass
        related: list[str] = []
        for hm in re.finditer(
            r'<a href="https://t\.me/([a-zA-Z0-9_]{4,32})"[^>]*'
            r'class="[^"]*btn-outline-info[^"]*"',
            body,
        ):
            h = hm.group(1).lower()
            if h != own_handle.lower() and h not in related:
                related.append(h)
        if related:
            out["related_handles"] = related
        out["channel_url"] = f"https://tgstat.com/channel/@{own_handle}"
        return out

    # --------------------------------------------------------------- plumbing

    def _build_url(self, keyword: str, **params) -> str:
        handle = params.get("handle") or getattr(self, "_last_handle", None) or keyword
        return f"https://t.me/s/{quote(handle, safe='')}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        """Fetch the preview page, capturing the final URL after redirects.

        A 302 chain ending at https://t.me/<handle> (without /s/) means the
        handle has no public preview (nonexistent or private).
        """
        if self._execute_query_override is not None:
            status, raw, err = self._execute_query_override(url, headers)
            return status, (url, raw), err
        try:
            recorder = _RedirectRecorder()
            opener = urllib.request.build_opener(recorder)
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                final_url = recorder.final_url or resp.geturl()
                return (resp.status, (final_url, body), "")
        except Exception as e:  # network/DNS/TLS: report, don't raise
            return (0, None, f"{type(e).__name__}: {e}")

    # --------------------------------------------------------------- parsing

    @staticmethod
    def _strip(html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_module.unescape(text)
        return re.sub(r"[ \t\xa0]+", " ", text).strip()

    @staticmethod
    def _parse_compact_count(raw: str) -> int | None:
        """'10.3M' / '531K' / '1,234' -> int."""
        raw = (raw or "").strip().replace(",", "").replace(" ", "")
        m = re.match(r"^([\d.]+)([KMB])?$", raw, re.I)
        if not m:
            return None
        num = float(m.group(1))
        mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(
            (m.group(2) or "").upper(), 1
        )
        return int(num * mult)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {"channel_found": False, "posts": [], "post_count": 0,
                    "transport_error": True}
        final_url, body = raw_data if isinstance(raw_data, tuple) else ("", raw_data)
        # Preview pages always live under /s/; anything else = no public preview.
        if not re.match(r"^https?://t\.me/s/", final_url or ""):
            return {"channel_found": False, "posts": [], "post_count": 0,
                    "final_url": final_url or ""}
        if not body or "tgme_channel_info" not in body:
            return {"channel_found": False, "posts": [], "post_count": 0}

        channel = self.parse_channel_header(body)
        posts = self.parse_posts(body)
        return {
            "channel_found": True,
            "channel": channel,
            "posts": posts,
            "post_count": len(posts),
            "preview_url": final_url,
        }

    # ---------------------------------------------------------- static parser

    @classmethod
    def parse_channel_header(cls, body: str) -> dict[str, Any]:
        header: dict[str, Any] = {}
        m = re.search(
            r'<div class="tgme_channel_info_header_title"[^>]*>(.*?)</div>',
            body, re.S,
        )
        if m:
            header["title"] = cls._strip(m.group(1)) or None
        m = re.search(
            r'<div class="tgme_channel_info_description"[^>]*>(.*?)</div>',
            body, re.S,
        )
        if m:
            header["description"] = cls._strip(m.group(1)) or None
        for cm in re.finditer(
            r'<span class="counter_value">([^<]+)</span>\s*'
            r'<span class="counter_type">([^<]+)</span>',
            body,
        ):
            value, kind = cm.group(1).strip(), cm.group(2).strip().lower()
            key = {
                "subscribers": "subscribers",
                "photos": "photos",
                "videos": "videos",
                "files": "files",
                "links": "links",
            }.get(kind)
            if key:
                header[key] = cls._parse_compact_count(value)
                header[f"{key}_raw"] = value
        m = re.search(r"https://t\.me/s/([a-zA-Z0-9_]{4,32})", body)
        if m:
            header["handle"] = m.group(1).lower()
        return header

    @classmethod
    def parse_posts(cls, body: str, max_posts: int = 20) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        blocks = re.split(
            r'<div class="tgme_widget_message_wrap js-widget_message_wrap">', body
        )[1:]
        for block in blocks[:max_posts]:
            post: dict[str, Any] = {}
            m = re.search(r'data-post="([a-zA-Z0-9_]{4,32})/(\d+)"', block)
            if m:
                post["handle"], post["post_id"] = m.group(1).lower(), m.group(2)
                post["url"] = f"https://t.me/{post['handle']}/{post['post_id']}"
            else:
                m = re.search(r'tgme_widget_message_date" href="([^"]+)"', block)
                if m:
                    post["url"] = m.group(1)
            m = re.search(r'<time datetime="([^"]+)"', block)
            if m:
                post["posted_at"] = m.group(1)
            m = re.search(
                r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>',
                block, re.S,
            )
            if m:
                text = cls._strip(m.group(1))
                if text:
                    post["text"] = text[:2000]
            m = re.search(r'tgme_widget_message_views">([^<]+)</span>', block)
            if m:
                post["views"] = cls._parse_compact_count(m.group(1).strip())
            media: list[str] = []
            if "tgme_widget_message_photo_wrap" in block:
                media.append("photo")
            if "tgme_widget_message_video_wrap" in block or "tgme_widget_message_video_player" in block:
                media.append("video")
            if "tgme_widget_message_document_wrap" in block:
                media.append("document")
            if "tgme_widget_message_sticker_wrap" in block:
                media.append("sticker")
            if media:
                post["media"] = media
            if post:
                posts.append(post)
        return posts
