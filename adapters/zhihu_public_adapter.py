"""知乎公开信息适配器 (www.zhihu.com) — 免登录公开 API 解析。数据边界: fully_public

知乎全站页面(HTML)对未登录访问是登录墙，但两条公开 JSON 接口
经 2026-10-21 实测免登录可用(单次低频探测，无登录、无验证码绕过):

- 热榜: GET https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true
  -> 200, JSON: data[].target{title_area.text, excerpt_area.text,
  metrics_area.text(热度), link.url}。标题/热度/问题链接均为公开信息。
- 用户公开资料: GET https://www.zhihu.com/api/v4/members/<url_token>
  -> 200, JSON: name, url_token, headline, avatar_url, gender, user_type,
  is_org, is_realname, org_verify_status, ip_info, url。
- 回答列表 https://www.zhihu.com/api/v4/members/<token>/answers -> 401
  {"error":{"message":"第三方应用独立请求时，无此操作权限","code":602}}。
  结论: 内容级(回答/文章列表)接口要登录态，画像级接口公开。本适配器只用
  公开的两条,回答/文章抓取判为"需用户浏览器代管登录"。

robots.txt 语义(2026-10-21 实测): www.zhihu.com/robots.txt 只给
Googlebot/bingbot 等命名爬虫下规则，没有 User-agent: * 通配组；
按惯例对未命名客户端无约束。本适配器实现 _check_robots 时若文件中
不存在通配组则视为允许，若存在通配组则按其规则执行。

不做的事: 不登录；不用 /search 等 robots 明确 Disallow 的路径；
不碰回答列表等 401 接口；不绕任何验证。
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_TOKEN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$")

_HOT_URL = (
    "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true"
)
_PROFILE_URL = "https://www.zhihu.com/api/v4/members/{token}"


class ZhihuPublic(SafeResearchAdapter):
    """知乎：热榜(mode=hot) / 用户公开资料(mode=profile, keyword=url_token)。"""

    source_domain = "www.zhihu.com"
    source_type = "qa_knowledge"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # conservative; public JSON endpoints

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # ------------------------------------------------------------------ API

    def _build_url(self, keyword: str, **params) -> str:
        mode = params.get("mode", "hot")
        self._last_mode = mode
        if mode == "profile":
            token = (params.get("url_token") or keyword or "").strip()
            if not _TOKEN_RE.match(token):
                raise ValueError("invalid url_token")
            return _PROFILE_URL.format(token=token)
        self._last_mode = "hot"
        return _HOT_URL

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.zhihu.com/hot",
        }

    def _check_robots(self) -> bool:
        """知乎 robots.txt 无 User-agent: * 通配组 -> 对未命名客户端无约束。"""
        if self._robots_checker is not None:
            return bool(self._robots_checker(self.source_domain, f"https://{self.source_domain}/"))
        try:
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers={"User-Agent": self._UA},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return True
        has_wildcard = bool(
            re.search(r"(?im)^\s*user-agent\s*:\s*\*\s*$", text)
        )
        if not has_wildcard:
            return True
        import urllib.robotparser

        rp = urllib.robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        return bool(rp.can_fetch(self._UA, _HOT_URL))

    # -------------------------------------------------------------- parsing

    @staticmethod
    def parse_hot_list(payload: dict) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entry in payload.get("data", []) or []:
            target = entry.get("target") or {}
            title = (target.get("title_area") or {}).get("text", "")
            excerpt = (target.get("excerpt_area") or {}).get("text", "")
            heat = (target.get("metrics_area") or {}).get("text", "")
            link = (target.get("link") or {}).get("url", "")
            if not title and not link:
                continue
            items.append({
                "title": title,
                "excerpt": excerpt[:400],
                "heat": heat,
                "url": link,
            })
        return items

    @staticmethod
    def parse_profile(payload: dict) -> dict[str, Any]:
        return {
            "name": payload.get("name", ""),
            "url_token": payload.get("url_token", ""),
            "headline": payload.get("headline", ""),
            "user_type": payload.get("user_type", ""),
            "is_org": bool(payload.get("is_org")),
            "is_realname": bool(payload.get("is_realname")),
            "org_verify_status": payload.get("org_verify_status"),
            "gender": payload.get("gender"),
            "avatar_url": payload.get("avatar_url", ""),
            "ip_info": payload.get("ip_info", ""),
            "profile_url": payload.get("url", ""),
        }

    # -------------------------------------------------------------- adapter

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"blocked": True, "items": []}
        if not isinstance(payload, dict):
            return {"blocked": True, "items": []}
        if getattr(self, "_last_mode", "hot") == "profile":
            profile = self.parse_profile(payload)
            return {"blocked": False, "profile": profile, "profile_found": bool(profile.get("name"))}
        items = self.parse_hot_list(payload)
        return {"blocked": False, "hot_items": items, "hot_count": len(items)}

    # ------------------------------------------------- invalid input handling

    def query(self, keyword: str, **params):
        mode = params.get("mode", "hot")
        if mode == "profile":
            token = (params.get("url_token") or keyword or "").strip()
            if not _TOKEN_RE.match(token):
                self._record_audit(keyword=keyword, url="", status=0, fields=[])
                return self._build_empty_result(keyword, "url_token_invalid")
        return super().query(keyword, **params)
