"""微博公开搜索适配器 — 关联深挖用社交媒体源。

数据边界: fully_public（仅公开微博/公开简介，不碰私密）

状态: BROWSER-ASSISTED
  m.weibo.cn 的搜索 API 需要 visitor 通行证（JS 指纹+设备验证），
  纯服务端 curl 无法通过。真实浏览器会自动获取通行证。
  query() 返回 interaction_required + 操作指引；
  parse_browser_result() 解析从浏览器 devtools 复制的 getIndex 响应 JSON。

关联价值：
  - 微博简介经常写"我是XX公司创始人/法人" → 人物身份关联
  - 公开微博内容暴露商业关联、家庭关系、合作动态
  - 转发/评论数反映影响力

Philosophy: 微博公开内容就是用户自己公开的信息。只取公开可见的。
"""

from __future__ import annotations

from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


# m.weibo.cn 综合搜索 containerid（type=1 综合，type=2 实时，type=3 热门）
_CONTAINER_SEARCH = (
    "100103type=1&q={keyword}"
)
_SEARCH_URL_TMPL = "https://m.weibo.cn/api/container/getIndex?containerid={cid}"


class WeiboSearchLookup(SafeResearchAdapter):
    """微博公开搜索（browser-assisted）。

    用法：
        adapter = WeiboSearchLookup()
        result = adapter.query("蜜雪冰城")   # 返回 interaction_required + 操作指引
        # 操作员在浏览器完成搜索后，把 getIndex 响应 JSON 贴回来：
        parsed = adapter.parse_browser_result(copied_json)
    """

    source_domain = "m.weibo.cn"
    source_type = "social_media"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True
    min_request_interval = 3.0

    # ------------------------------------------------------------------
    # 主入口：返回操作指引（browser-assisted）
    # ------------------------------------------------------------------
    def query(self, keyword: str, **params: Any) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        if not keyword:
            return self._interaction_required("", "empty keyword")
        self._record_audit(keyword)
        return self._interaction_required(keyword)

    def _interaction_required(self, keyword: str, reason: str = "") -> dict[str, Any]:
        from urllib.parse import quote

        cid = _CONTAINER_SEARCH.format(keyword=quote(keyword))
        api_url = _SEARCH_URL_TMPL.format(cid=quote(cid, safe=""))
        return {
            "status": "interaction_required",
            "reason": reason or "weibo_search_needs_visitor_pass",
            "keyword": keyword,
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "instructions": [
                "1. 在手机浏览器或桌面浏览器打开 https://m.weibo.cn/",
                "2. 等待页面加载（会自动获取 visitor 通行证，无需登录）",
                "3. 在搜索框输入关键词并搜索，或直接访问：",
                f"   {api_url}",
                "4. 打开浏览器开发者工具 → Network 面板 → 找到 getIndex 请求",
                "5. 复制该请求的 Response JSON",
                "6. 调用 parse_browser_result(copied_json) 解析",
            ],
            "api_url_hint": api_url,
        }

    # ------------------------------------------------------------------
    # 解析：从浏览器复制的 getIndex 响应 JSON → 结构化微博列表
    # ------------------------------------------------------------------
    def parse_browser_result(
        self, raw: str | dict[str, Any]
    ) -> dict[str, Any]:
        import json

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return self._empty_result("invalid_json")
        elif isinstance(raw, dict):
            data = raw
        else:
            return self._empty_result("invalid_input")

        if not isinstance(data, dict):
            return self._empty_result("unexpected_shape")

        cards = (
            data.get("data", {}).get("cards", [])
            if isinstance(data.get("data"), dict)
            else []
        )

        posts: list[dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            # 微博卡片通常在 card_group 或直接 mblog
            mblogs: list[dict[str, Any]] = []
            if isinstance(card.get("mblog"), dict):
                mblogs.append(card["mblog"])
            for sub in card.get("card_group", []) or []:
                if isinstance(sub, dict) and isinstance(sub.get("mblog"), dict):
                    mblogs.append(sub["mblog"])
            for mb in mblogs:
                post = self._extract_post(mb)
                if post:
                    posts.append(post)

        return {
            "status": "ok",
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "post_count": len(posts),
            "posts": posts,
        }

    # ------------------------------------------------------------------
    # 单条微博提取
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_post(mb: dict[str, Any]) -> dict[str, Any] | None:
        import re

        text_raw = mb.get("text", "") or ""
        # 去 HTML 标签
        text = re.sub(r"<[^>]+>", "", text_raw).strip()
        if not text and not mb.get("id"):
            return None

        user = mb.get("user", {}) if isinstance(mb.get("user"), dict) else {}

        # 发布时间：m.weibo.cn 返回如 "2026-10-21" 或相对时间
        created = mb.get("created_at", "")

        return {
            "mid": str(mb.get("mid", "") or mb.get("id", "")),
            "text": text[:2000],
            "created_at": created,
            "reposts": mb.get("reposts_count", 0),
            "comments": mb.get("comments_count", 0),
            "likes": mb.get("attitudes_count", 0),
            "author": {
                "id": str(user.get("id", "")),
                "screen_name": user.get("screen_name", ""),
                "description": (user.get("description", "") or "")[:500],
                "followers": user.get("followers_count", 0),
                "verified": bool(user.get("verified", False)),
                "verified_reason": user.get("verified_reason", "") or "",
            },
            "profile_url": (
                f"https://m.weibo.cn/u/{user.get('id')}" if user.get("id") else ""
            ),
        }

    # ------------------------------------------------------------------
    # 抽象方法实现（browser-assisted 模式下不实际调用）
    # ------------------------------------------------------------------
    def _build_url(self, keyword: str, **params: Any) -> str:
        from urllib.parse import quote

        cid = _CONTAINER_SEARCH.format(keyword=quote(keyword or ""))
        return _SEARCH_URL_TMPL.format(cid=quote(cid, safe=""))

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # browser-assisted：解析走 parse_browser_result，这里返回空
        return {}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "status": "parse_failed",
            "reason": reason,
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "post_count": 0,
            "posts": [],
        }

    def _record_audit(self, keyword: str) -> None:
        # 基类审计：只存 keyword 的 sha256 前 12 位
        try:
            super()._record_audit(
                keyword=keyword, url="", status=0, fields=[]
            )
        except Exception:
            pass
