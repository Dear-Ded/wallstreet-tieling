"""豆瓣公开用户页适配器 — /people/<uid>/ HTML 解析。数据边界: fully_public

Fetches the public profile page of a Douban user and parses the
server-rendered profile block. No login, no key. Anonymous GET returns
HTTP 200 with the profile rendered (a logged-out nudge banner is present
but does not block content).

Verified 2026-10-21 (overseas egress, US datacenter):
- GET https://www.douban.com/people/ahbei/ -> 200, 46KB server-rendered:
  title "阿北"; id="db-usr-profile" block; id="intro_display" -> "Less is more";
  class="user-info" -> "常居: 北京", uid number "1000001 (ahbei)",
  "2006-01-09加入" (注册时间), "IP属地：未知". No captcha, no login redirect,
  identical result with datacenter-style UA and browser-style UA.
- Nonexistent uid -> HTTP 404 (structured "not found").
- robots.txt: /people/<uid>/ is NOT in the Disallow list
  (only /people/*/collect|wish|all|do and /search paths are). Allowed.
- Rate limit: 3s between requests (conservative; douban is crawl-sensitive).

Fields extracted: nickname, uid (URL slug), user_id_number, intro (个人简介),
location (常居地), registered_at (加入时间), ip_location (often "未知"),
avatar URL, profile_url, self_claimed_kinship (简介亲属自述，review 级线索).

Not touched: anything behind login (私信, 关注列表分页 beyond public,
blacklist etc.). Only the single public profile page.
"""

from __future__ import annotations

import hashlib
import html as html_module
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class DoubanUserLookup(SafeResearchAdapter):
    """豆瓣公开用户页：uid -> 公开资料。"""

    source_domain = "www.douban.com"
    source_type = "social_user_douban"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0  # douban is crawl-sensitive

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # ------------------------------------------------------------------ API

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """Public profile lookup. keyword = douban uid slug (URL segment)."""
        uid = (keyword or "").strip().strip("/")
        if not uid or not re.match(r"^[A-Za-z0-9_\-\.]{1,64}$", uid):
            return self._empty(uid or keyword, "invalid_uid")

        url = f"https://www.douban.com/people/{urllib.parse.quote(uid, safe='')}/"
        self._enforce_rate_limit()
        robots_ok = self._check_robots()
        if not robots_ok:
            self._record_audit(keyword=uid, url=url, status=0, fields=[],
                               robots_allowed=False)
            return self._empty(uid, "robots_txt_disallowed")

        status, raw, error = self._execute_query(url, self._build_headers())
        if status == 404:
            self._record_audit(keyword=uid, url=url, status=404, fields=[])
            return self._empty(uid, "user_not_found")
        if status != 200 or not raw:
            self._record_audit(keyword=uid, url=url, status=status, fields=[])
            return self._empty(uid, f"fetch_failed:{error}"[:120])

        profile = self.parse_profile_page(raw, uid)
        if not profile.get("user_found"):
            self._record_audit(keyword=uid, url=url, status=status, fields=[])
            return self._empty(uid, "profile_parse_failed")

        self._record_audit(keyword=uid, url=url, status=status,
                           fields=list(profile.keys()))
        return {
            "query_subject_hash": hashlib.sha256(uid.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "status": "ok",
            "fields": {"profile": profile, "profile_url": url},
            "field_count": 2,
            "error": "",
        }

    def _empty(self, uid: str, reason: str) -> dict[str, Any]:
        return {
            "query_subject_hash": hashlib.sha256(uid.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "status": "empty",
            "fields": {},
            "field_count": 0,
            "error": reason,
        }

    # --------------------------------------------------------------- plumbing

    def _build_url(self, keyword: str, **params) -> str:
        uid = (keyword or "").strip().strip("/")
        return f"https://www.douban.com/people/{urllib.parse.quote(uid, safe='')}/"

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.douban.com/",
        }

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return (resp.status, resp.read().decode("utf-8", errors="replace"), "")
        except urllib.error.HTTPError as e:
            return (e.code, None, f"HTTPError: {e.code}")
        except Exception as e:  # network/DNS/TLS: report, don't raise
            return (0, None, f"{type(e).__name__}: {e}")

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() handles its own extraction; keep the abstract satisfied.
        return {}

    # --------------------------------------------------------------- parsing

    @staticmethod
    def _strip(raw: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_module.unescape(text)
        return re.sub(r"[ \t\xa0]+", " ", text).strip()

    @classmethod
    def parse_profile_page(cls, body: str, uid: str) -> dict[str, Any]:
        """Parse the server-rendered /people/<uid>/ page.

        Returns user_found=False when the profile block is absent
        (login wall, captcha, or deleted account) — never guesses.
        """
        out: dict[str, Any] = {
            "user_found": False,
            "uid": uid,
            "profile_url": f"https://www.douban.com/people/{uid}/",
        }
        if not body or 'id="db-usr-profile"' not in body:
            return out

        # nickname: <title>阿北</title> (some pages: "阿北 - 豆瓣" / "阿北的个人主页")
        m = re.search(r"<title>(.*?)</title>", body, re.S)
        if m:
            title = cls._strip(m.group(1))
            for suffix in (" - 豆瓣", "的个人主页", " - douban"):
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
            out["nickname"] = title.strip() or None

        # user-info block: 常居 / uid number / 加入时间 / IP属地
        info_m = re.search(r'<div class="user-info">(.*?)</div>', body, re.S)
        info_text = cls._strip(info_m.group(1)) if info_m else ""
        m = re.search(r"常居[:：]\s*([^\s]+)", info_text)
        if m:
            out["location"] = m.group(1).strip() or None
        m = re.search(r"(\d{4,12})\s*\(([^)]+)\)", info_text)
        if m:
            out["user_id_number"] = m.group(1)
            out["uid_alias"] = m.group(2).strip() or None
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*加入", info_text)
        if m:
            out["registered_at"] = m.group(1)
        m = re.search(r"IP属地[：:]\s*([^\s]+)", info_text)
        if m:
            out["ip_location"] = m.group(1).strip() or None

        # intro (个人简介)
        m = re.search(r'id="intro_display"[^>]*>(.*?)</div>', body, re.S)
        if m:
            intro = cls._strip(m.group(1))
            if intro:
                out["intro"] = intro[:2000]
                # 亲属关系 lane（2026-10-21）：简介中的亲属自述（如"张三的妻子"），
                # 低置信度（evidence_level=review），仅作线索。
                try:
                    from core.kinship_extract import extract_self_claimed_kinship
                    claimed = extract_self_claimed_kinship(
                        intro, profile_name=out.get("nickname"))
                    if claimed:
                        out["self_claimed_kinship"] = claimed
                except Exception:
                    pass

        # avatar
        m = re.search(
            r'<img[^>]+class="userface"[^>]+src="([^"]+)"', body
        ) or re.search(r'<img[^>]+src="([^"]+)"[^>]+class="userface"', body)
        if m:
            out["avatar"] = html_module.unescape(m.group(1))

        out["user_found"] = bool(out.get("nickname"))
        return out
