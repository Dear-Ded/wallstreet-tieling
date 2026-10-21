"""Common Crawl 历史 URL 检索适配器。数据边界: fully_public

Common Crawl (commoncrawl.org) is a free, open web archive crawled monthly
since 2007. Its CDX index API lets us list every URL ever captured for a
domain — the time dimension of "digging to the root":

- Deleted pages: old contact/about pages with phone numbers, addresses,
  company names that no longer exist on the live site.
- Historical associations: old partner links, old brand names, old ICP
  filing references embedded in archived HTML.
- Temporal signals: first-seen / last-seen timestamps per URL feed the
  temporal-analysis module (batch creation, site death, rebranding).

Technical notes (verified 2026-10-21):
- CDX endpoint: https://index.commoncrawl.org/{INDEX}-index?url=...&output=json
- Latest index discovered at runtime from /collinfo.json (fallback hardcoded).
- matchType=domain lists all URLs under a domain; collapse=urlkey dedupes
  to one record per URL (latest capture).
- The index service is flaky from this egress: ~50% of requests 504 at the
  nginx gateway (~10s). Adapter retries up to 4x with backoff; degrades to
  service_unavailable instead of crashing.
- Exact-URL queries are cheaper than prefix wildcards; matchType=domain is
  the supported bulk path. Wildcard `url=example.com/*` queries are NOT used
  (consistently time out).
- No auth, no key, no login. robots.txt on index.commoncrawl.org allows.
- Public data only: the CDX index returns metadata (URL/timestamp/status),
  never page bodies. WARC fetching is out of scope for this adapter.

Association value: historical URLs are leads — an old /contact.html URL
proves the page existed; fetching its archived body (via data.commoncrawl.org
or Wayback) is the follow-up step.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import json
import re
import time
import urllib.parse


class CommonCrawlLookup(SafeResearchAdapter):
    """Common Crawl 历史 URL 检索：按域名查历史捕获的 URL 列表。"""

    source_domain = "index.commoncrawl.org"
    source_type = "web_archive_public"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _COLLECTION_INFO_URL = "https://index.commoncrawl.org/collinfo.json"
    _FALLBACK_INDEX = "CC-MAIN-2026-39"
    _MAX_RETRIES = 4
    _RETRY_BACKOFF_S = [2.0, 4.0, 8.0]
    _REQUEST_TIMEOUT_S = 45

    _TIMESTAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$")

    def _discover_latest_index(self) -> str:
        """Return the newest crawl index id from collinfo.json, fallback hardcoded."""
        try:
            import urllib.request
            req = urllib.request.Request(
                self._COLLECTION_INFO_URL, headers={"User-Agent": self._build_headers()["User-Agent"]}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                info = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(info, list) and info:
                return str(info[0].get("id", self._FALLBACK_INDEX))
        except Exception:
            pass
        return self._FALLBACK_INDEX

    def _build_url(self, keyword: str, **params) -> str:
        domain = self._normalize_domain(keyword)
        index = params.get("index") or self._discover_latest_index()
        limit = int(params.get("limit", 200))
        match_type = params.get("matchType", "domain")
        query = {
            "url": domain,
            "matchType": match_type,
            "output": "json",
            "limit": str(limit),
            "collapse": "urlkey",
            "filter": "status:200",
        }
        if params.get("from"):
            query["from"] = str(params["from"])
        if params.get("to"):
            query["to"] = str(params["to"])
        qs = urllib.parse.urlencode(query)
        return f"https://index.commoncrawl.org/{index}-index?{qs}"

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence; +https://commoncrawl.org)",
            "Accept": "application/json",
        }

    def _execute_query(self, url: str, headers: dict) -> tuple:
        """Retry wrapper around the flaky CDX index (intermittent 504s)."""
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        import urllib.request
        last_error = ""
        for attempt in range(self._MAX_RETRIES):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self._REQUEST_TIMEOUT_S) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    if resp.status == 200 and body.lstrip().startswith("{"):
                        return (resp.status, body, "")
                    last_error = f"HTTP {resp.status}: non-JSON body"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
            if attempt < self._MAX_RETRIES - 1:
                time.sleep(self._RETRY_BACKOFF_S[min(attempt, len(self._RETRY_BACKOFF_S) - 1)])
        return (0, None, f"cdx_unavailable_after_{self._MAX_RETRIES}_retries: {last_error}")

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {"url_count": 0, "urls": [], "index_used": None}
        records = self.parse_cdx_lines(raw_data)
        return {
            "url_count": len(records),
            "urls": records,
            "index_used": self._last_index,
        }

    _last_index: str | None = None

    # ------------------------------------------------------------------
    # Public helpers (also used by tests / entity association)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_domain(keyword: str) -> str:
        d = keyword.strip().lower()
        d = re.sub(r"^https?://", "", d)
        d = d.split("/")[0].split("?")[0].split("#")[0]
        d = d.split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        return d

    @classmethod
    def parse_cdx_lines(cls, raw: str) -> list[dict[str, Any]]:
        """Parse CDX JSON-lines into structured URL records."""
        records: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            ts = str(item.get("timestamp", ""))
            records.append({
                "url": item.get("url", ""),
                "captured_at": cls._format_timestamp(ts),
                "captured_at_raw": ts,
                "status": str(item.get("status", "")),
                "mime": item.get("mime", "") or item.get("mime-detected", ""),
                "digest": item.get("digest", ""),
                "warc_file": item.get("filename", ""),
                "warc_offset": item.get("offset", ""),
                "warc_length": item.get("length", ""),
                "languages": item.get("languages", ""),
            })
        return records

    @classmethod
    def _format_timestamp(cls, ts: str) -> str:
        m = cls._TIMESTAMP_RE.match(ts or "")
        if not m:
            return ts
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}Z"

    def query(self, keyword: str, **params) -> dict[str, Any]:
        # Capture which index was used so fields can report it.
        domain = self._normalize_domain(keyword)
        index = params.get("index") or self._discover_latest_index()
        self._last_index = index
        return super().query(domain, index=index, **{k: v for k, v in params.items() if k != "index"})
