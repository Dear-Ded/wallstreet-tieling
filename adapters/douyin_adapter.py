#!/usr/bin/env python3
"""抖音 (Douyin) 线下商户足迹适配器（线下商业 lane）。

回答："这家线下店在抖音上有号吗？粉丝多少？发什么内容？视频带 POI 地址吗？"

## 两种模式

1. **自主模式** (`query_by_sec_uid` / `query_by_share_url`)：
   已知 sec_user_id 或分享链接 → 全自动拉取主页 + 视频列表。
   签名：vendored a_bogus 纯 Python 实现（Apache-2.0，
   源自 Evil0ctal/Douyin_TikTok_Download_API），ttwid 经官方
   union/register 接口获取（无登录、无凭证）。

2. **浏览器辅助模式** (`query`)：
   按店名搜索需要完整的搜索签名链，纯服务端复现不稳定。
   `query()` 返回 interaction_required + 操作指引；操作员在浏览器
   搜完后用 `parse_browser_search()` 解析粘贴的 JSON。

## 提取字段

- 抖音号 (unique_id)、昵称、签名（常含地址/电话）、粉丝数、获赞数、视频数
- 企业认证 / 蓝V（entity_type）
- 视频列表：标题、发布时间、点赞/评论/分享数、POI（地点名+地址+经纬度）
- POI 是线下商户最有价值的信号：视频挂载的店铺位置

## 合规

- 只读公开数据，不登录、不绕过验证码
- 3 秒请求间隔；a_bogus 签名是平台公开 JS 的算法复现（Apache-2.0 开源项目已验证）
- data_boundary="fully_public"；EXPERIMENTAL，默认关闭

Vendored signing: adapters/_vendor/douyin_sign/ (abogus.py + sm3.py)
"""

from __future__ import annotations

import json
import random
import time
import urllib.parse
import urllib.request
from typing import Any

from adapters._vendor.douyin_sign.abogus import ABogus
from adapters.safe_research_adapter import SafeResearchAdapter

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
_PROFILE_URL = "https://www.douyin.com/aweme/v1/web/user/profile/other/"
_POSTS_URL = "https://www.douyin.com/aweme/v1/web/aweme/post/"


def _gen_ms_token(rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    return "".join(rng.choices(alphabet, k=107)) + "=="


def _fetch_ttwid(timeout: int = 15) -> str | None:
    """经官方 union/register 接口获取游客 ttwid（无登录）。"""
    payload = json.dumps({
        "region": "cn", "aid": 1768, "needFid": False,
        "service": "www.ixigua.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https", "union": True,
    }).encode()
    req = urllib.request.Request(
        _TTWID_URL, data=payload,
        headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        for h in resp.headers.get_all("Set-Cookie") or []:
            if h.startswith("ttwid="):
                return h.split(";")[0].split("=", 1)[1]
    except Exception:
        pass
    return None


class DouyinBusinessLookup(SafeResearchAdapter):
    """抖音商户足迹：主页 + 视频列表 + POI。"""

    source_domain = "www.douyin.com"
    source_type = "offline_business_douyin_footprint"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._signer = ABogus(_USER_AGENT)
        self._ttwid: str | None = None
        self._ms_token: str | None = None

    # -- identity -----------------------------------------------------
    def _ensure_identity(self) -> bool:
        if self._ttwid:
            return True
        self._ttwid = _fetch_ttwid()
        if self._ttwid:
            self._ms_token = _gen_ms_token()
        return bool(self._ttwid)

    def _signed_get(self, base_url: str, params: dict[str, str],
                    timeout: int = 20) -> tuple[int, Any, str]:
        """a_bogus 签名 GET。返回 (status, parsed_json, error)。"""
        if not self._ensure_identity():
            return (0, None, "ttwid_mint_failed")
        q = params.copy()
        q.setdefault("msToken", self._ms_token or "")
        query = "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in q.items()
        )
        try:
            bogus = self._signer.get_value(query, body="", content_type="")
        except Exception as e:
            return (0, None, f"sign_failed: {e}")
        url = f"{base_url}?{query}&a_bogus={urllib.parse.quote(bogus, safe='')}"
        cookie = f"ttwid={self._ttwid}; msToken={self._ms_token}"
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Cookie": cookie,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if not body:
                    return (resp.status, None, "empty_response")
                return (resp.status, json.loads(body), "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    # -- SafeResearchAdapter interface --------------------------------
    def _build_url(self, keyword: str, **params: Any) -> str:
        # 搜索走浏览器辅助；此 URL 仅作审计占位
        return f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() 走 browser-assisted，不经过此路径
        return {}

    def query(self, keyword: str, **params: Any) -> dict[str, Any]:
        """按店名搜索 → browser-assisted（搜索签名链服务端不稳定）。"""
        self._enforce_rate_limit()
        self._record_audit(keyword=keyword, url=self._build_url(keyword),
                           status=0, fields=[])
        return {
            "query_subject_hash": __import__("hashlib").sha256(
                keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "interaction_required": True,
            "fields": {},
            "field_count": 0,
            "error": "",
            "interaction_guide": self._search_guide(keyword),
            "duration_ms": 0,
        }

    @staticmethod
    def _search_guide(keyword: str) -> list[str]:
        return [
            f"1. 浏览器打开 https://www.douyin.com/search/{keyword}（或抖音 App 搜）",
            "2. 找到目标商户的账号，点进主页",
            "3. 复制地址栏 sec_user_id（user/ 后面的那串），或复制一条分享链接",
            "4. 调 query_by_sec_uid(sec_user_id) 全自动拉取主页+视频；",
            "   或调 parse_browser_search() 解析从 devtools 拷的搜索 JSON",
        ]

    # -- autonomous: profile + posts ----------------------------------
    def query_by_sec_uid(self, sec_user_id: str,
                         max_posts: int = 20) -> dict[str, Any]:
        """已知 sec_user_id → 主页 + 视频列表（全自动）。"""
        start = time.monotonic()
        self._enforce_rate_limit()
        base = {
            "device_platform": "webapp", "aid": "6383",
            "channel": "channel_pc_web",
        }
        # profile
        p_params = {**base, "sec_user_id": sec_user_id,
                    "publish_video_strategy_type": "2"}
        st, profile_json, err = self._signed_get(_PROFILE_URL, p_params)
        profile = self._parse_profile(profile_json) if profile_json else {}
        if err:
            profile["fetch_error"] = err

        # posts (first page)
        posts: list[dict[str, Any]] = []
        if not err or profile:
            v_params = {**base, "sec_user_id": sec_user_id,
                        "count": str(min(max_posts, 20)), "max_cursor": "0"}
            st2, posts_json, err2 = self._signed_get(_POSTS_URL, v_params)
            if posts_json:
                posts = self._parse_posts(posts_json, limit=max_posts)
            if err2 and not posts:
                profile["posts_fetch_error"] = err2

        fields = {
            "profile": profile,
            "post_count": len(posts),
            "posts": posts,
            "poi_list": self._collect_pois(posts),
        }
        self._record_audit(keyword=sec_user_id[:16], url=_PROFILE_URL,
                           status=st, fields=list(fields.keys()))
        return {
            "query_subject_hash": __import__("hashlib").sha256(
                sec_user_id.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": st,
            "fields": fields,
            "field_count": len(fields),
            "error": err,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def query_by_share_url(self, share_url: str,
                           max_posts: int = 20) -> dict[str, Any]:
        """分享链接 (v.douyin.com/xxx 或 /video/xxx) → 解析出 sec_user_id → 全自动。"""
        sec_uid = self._resolve_share_url(share_url)
        if not sec_uid:
            return {"error": "share_url_resolve_failed",
                    "interaction_required": True,
                    "hint": "在浏览器打开分享链接，从最终 URL 或页面源码取 sec_user_id"}
        return self.query_by_sec_uid(sec_uid, max_posts=max_posts)

    @staticmethod
    def _resolve_share_url(share_url: str) -> str | None:
        """跟随跳转，从最终页面 HTML 提取 sec_user_id。"""
        try:
            req = urllib.request.Request(
                share_url,
                headers={"User-Agent": _USER_AGENT},
            )
            # 不自动跟随以外的手动处理：urllib 默认跟随 302
            with urllib.request.urlopen(req, timeout=15) as resp:
                final_url = resp.geturl()
                html = resp.read().decode("utf-8", errors="replace")
            import re
            m = re.search(r"sec_user_id[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_-]{40,})[\"']",
                          html)
            if m:
                return m.group(1)
            m2 = re.search(r"/user/([A-Za-z0-9_-]{40,})", final_url)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return None

    # -- browser-assisted search parsing ------------------------------
    @staticmethod
    def parse_browser_search(raw: str | dict) -> dict[str, Any]:
        """解析从浏览器 devtools 复制的搜索响应 JSON → 结构化账号列表。"""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            return {"parse_error": f"invalid_json: {e}", "users": []}
        users: list[dict[str, Any]] = []
        # 兼容 general/search/single 与 discover/search 两种形状
        candidates: list[dict[str, Any]] = []
        if isinstance(data.get("data"), list):
            for block in data["data"]:
                if isinstance(block, dict):
                    candidates += block.get("user_list", []) or []
        candidates += data.get("user_list", []) or []
        for item in candidates:
            u = item.get("user_info", item) if isinstance(item, dict) else {}
            if not isinstance(u, dict):
                continue
            users.append({
                "sec_user_id": u.get("sec_uid", ""),
                "douyin_id": u.get("unique_id", ""),
                "nickname": u.get("nickname", ""),
                "signature": u.get("signature", ""),
                "follower_count": u.get("follower_count"),
                "aweme_count": u.get("aweme_count"),
                "total_favorited": u.get("total_favorited"),
                "enterprise_verify": bool(u.get("enterprise_verify_reason")),
                "verify_reason": u.get("enterprise_verify_reason")
                or u.get("verify_reason", ""),
                "avatar": (u.get("avatar_larger") or {}).get("url_list", [None])[0],
            })
        users = [u for u in users if u["sec_user_id"] or u["nickname"]]
        return {"user_count": len(users), "users": users}

    # -- parsers ------------------------------------------------------
    @staticmethod
    def _parse_profile(data: dict[str, Any]) -> dict[str, Any]:
        user = (data.get("user") or {}) if isinstance(data, dict) else {}
        return {
            "sec_user_id": user.get("sec_uid", ""),
            "douyin_id": user.get("unique_id", ""),
            "nickname": user.get("nickname", ""),
            "signature": user.get("signature", ""),
            "follower_count": user.get("follower_count"),
            "following_count": user.get("following_count"),
            "aweme_count": user.get("aweme_count"),
            "total_favorited": user.get("total_favorited"),
            "enterprise_verify": bool(user.get("enterprise_verify_reason")),
            "verify_reason": user.get("enterprise_verify_reason", ""),
            "ip_location": user.get("ip_location", ""),
        }

    @staticmethod
    def _parse_posts(data: dict[str, Any],
                     limit: int = 20) -> list[dict[str, Any]]:
        items = (data.get("aweme_list") or []) if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            stats = it.get("statistics") or {}
            poi = it.get("poi_info") or it.get("poi") or {}
            out.append({
                "aweme_id": it.get("aweme_id", ""),
                "desc": (it.get("desc") or "")[:200],
                "create_time": it.get("create_time"),
                "digg_count": stats.get("digg_count"),
                "comment_count": stats.get("comment_count"),
                "share_count": stats.get("share_count"),
                "poi_name": poi.get("poi_name") or poi.get("title", ""),
                "poi_address": poi.get("address") or poi.get("poi_address", ""),
                "poi_latitude": poi.get("latitude"),
                "poi_longitude": poi.get("longitude"),
            })
        return out

    @staticmethod
    def _collect_pois(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        pois: list[dict[str, Any]] = []
        for p in posts:
            name = p.get("poi_name", "")
            if name and name not in seen:
                seen.add(name)
                pois.append({
                    "poi_name": name,
                    "poi_address": p.get("poi_address", ""),
                    "latitude": p.get("poi_latitude"),
                    "longitude": p.get("poi_longitude"),
                })
        return pois
