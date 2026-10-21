"""微博关系链适配器 — 个人深挖用社交媒体源。

数据边界: fully_public（仅公开关注/粉丝列表，不碰私信/私密）

状态: BROWSER-ASSISTED
  m.weibo.cn 的关系链 API（containerid=231051_-_followers_-_ / 231051_-_fans_-_）
  与搜索 API 一样需要 visitor 通行证（JS 指纹+设备验证），纯服务端 curl
  会被 302 到 visitor.passport.weibo.cn。真实浏览器会自动获取通行证。
  query() 返回 interaction_required + 操作指引；
  parse_browser_result() 解析从浏览器 devtools 复制的 getIndex 响应 JSON。

关联价值：
  - 关注列表 = 用户主动建立的社会关系（商业伙伴/家人/同行常互关）
  - 粉丝列表 = 影响力辐射面
  - 被关注者的简介/认证理由经常暴露「XX公司」「XX职务」→ 人-企业关联
  - 互关（follow_me + following）是强关系信号

Philosophy: 微博公开关注/粉丝列表是用户自己公开的信息。只取公开可见的。
"""

from __future__ import annotations

from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


# m.weibo.cn 关系链 containerid
# 注意微博的命名：followers = 该用户"关注"的人；fans = 该用户的"粉丝"
_CONTAINER_RELATION = "231051_-_{relation}_-_{uid}"
_API_URL_TMPL = "https://m.weibo.cn/api/container/getIndex?containerid={cid}&page={page}"

_VALID_RELATIONS = ("followers", "fans")


class WeiboRelationLookup(SafeResearchAdapter):
    """微博关注/粉丝关系链（browser-assisted）。

    用法：
        adapter = WeiboRelationLookup()
        result = adapter.query("123456", relation="followers")  # 返回 interaction_required
        # 操作员在浏览器完成访问后，把 getIndex 响应 JSON 贴回来：
        parsed = adapter.parse_browser_result(copied_json, relation="followers")
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
    def query(self, user_id: str, relation: str = "followers", page: int = 1,
              **params: Any) -> dict[str, Any]:
        user_id = (user_id or "").strip()
        relation = (relation or "followers").strip().lower()
        if not user_id:
            return self._interaction_required("", relation, page, "empty user_id")
        if relation not in _VALID_RELATIONS:
            return self._interaction_required(
                user_id, relation, page, f"invalid relation (want {list(_VALID_RELATIONS)})"
            )
        try:
            page = max(1, int(page))
        except (TypeError, ValueError):
            page = 1
        self._record_audit(f"{relation}:{user_id}")
        return self._interaction_required(user_id, relation, page)

    def _interaction_required(self, user_id: str, relation: str, page: int,
                              reason: str = "") -> dict[str, Any]:
        from urllib.parse import quote

        cid = _CONTAINER_RELATION.format(relation=relation, uid=user_id)
        api_url = _API_URL_TMPL.format(cid=quote(cid, safe=""), page=page)
        relation_cn = "关注" if relation == "followers" else "粉丝"
        return {
            "status": "interaction_required",
            "reason": reason or "weibo_relation_needs_visitor_pass",
            "user_id": user_id,
            "relation": relation,
            "relation_cn": relation_cn,
            "page": page,
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "instructions": [
                "1. 在浏览器打开 https://m.weibo.cn/ 并等待加载（自动获取 visitor 通行证，无需登录）",
                "2. 如不知道数字 uid：先访问用户主页 https://m.weibo.cn/u/<uid>，",
                "   或在浏览器 Network 面板找 containerid=100505 开头的 getIndex 请求，uid 即后缀数字；",
                f"   也可直接搜索用户后从搜索结果 JSON 的 user.id 字段获取。",
                "3. 直接访问该用户的" + relation_cn + "列表 API：",
                f"   {api_url}",
                "   （翻页：把 page=N 改大，或用响应里 cardlistInfo.since_id 拼 containerid）",
                "4. 打开浏览器开发者工具 → Network 面板 → 找到 getIndex 请求",
                "5. 复制该请求的 Response JSON",
                "6. 调用 parse_browser_result(copied_json, relation=\""
                + relation + "\") 解析",
            ],
            "api_url_hint": api_url,
        }

    # ------------------------------------------------------------------
    # 解析：从浏览器复制的 getIndex 响应 JSON → 结构化关系列表
    # ------------------------------------------------------------------
    def parse_browser_result(
        self, raw: str | dict[str, Any], relation: str = "followers"
    ) -> dict[str, Any]:
        import json

        relation = (relation or "followers").strip().lower()
        if relation not in _VALID_RELATIONS:
            relation = "followers"

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return self._empty_result(relation, "invalid_json")
        elif isinstance(raw, dict):
            data = raw
        else:
            return self._empty_result(relation, "invalid_input")

        if not isinstance(data, dict):
            return self._empty_result(relation, "unexpected_shape")

        data_node = data.get("data")
        cards = data_node.get("cards", []) if isinstance(data_node, dict) else []
        cardlist_info = (
            data_node.get("cardlistInfo", {}) if isinstance(data_node, dict) else {}
        )

        users: list[dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            user = card.get("user")
            if isinstance(user, dict):
                extracted = self._extract_user(user)
                if extracted:
                    users.append(extracted)

        total = cardlist_info.get("total")
        since_id = cardlist_info.get("since_id")
        containerid = cardlist_info.get("containerid", "")

        return {
            "status": "ok",
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "relation": relation,
            "relation_cn": "关注" if relation == "followers" else "粉丝",
            "user_count": len(users),
            "total": total,
            "users": users,
            "pagination": {
                "since_id": since_id,
                "containerid": containerid,
                "next_page_hint": (
                    "用 cardlistInfo.containerid + '&since_id=' + since_id 拼出下一页 API URL"
                    if since_id else ""
                ),
            },
        }

    # ------------------------------------------------------------------
    # 单个用户提取
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_user(u: dict[str, Any]) -> dict[str, Any] | None:
        uid = u.get("id")
        screen_name = (u.get("screen_name") or "").strip()
        if not uid and not screen_name:
            return None
        uid_str = str(uid) if uid is not None else ""
        return {
            "id": uid_str,
            "screen_name": screen_name,
            "description": (u.get("description") or "")[:500],
            "profile_url": u.get("profile_url") or (
                f"https://m.weibo.cn/u/{uid_str}" if uid_str else ""
            ),
            "verified": bool(u.get("verified", False)),
            "verified_type": u.get("verified_type", -1),
            "verified_reason": (u.get("verified_reason") or "")[:300],
            "followers_count": u.get("followers_count", 0),
            "follow_count": u.get("follow_count", 0),
            "gender": u.get("gender", ""),
            # 关系方向信号（存在时）：是否关注了我 / 我是否关注了他
            "follow_me": u.get("follow_me"),
            "following": u.get("following"),
        }

    # ------------------------------------------------------------------
    # 抽象方法实现（browser-assisted 模式下不实际调用）
    # ------------------------------------------------------------------
    def _build_url(self, keyword: str, **params: Any) -> str:
        from urllib.parse import quote

        relation = str(params.get("relation", "followers")).strip().lower()
        if relation not in _VALID_RELATIONS:
            relation = "followers"
        try:
            page = max(1, int(params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        cid = _CONTAINER_RELATION.format(relation=relation, uid=(keyword or "").strip())
        return _API_URL_TMPL.format(cid=quote(cid, safe=""), page=page)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # browser-assisted：解析走 parse_browser_result，这里返回空
        return {}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _empty_result(self, relation: str, reason: str) -> dict[str, Any]:
        return {
            "status": "parse_failed",
            "reason": reason,
            "source": "m.weibo.cn",
            "data_boundary": self.data_boundary,
            "relation": relation,
            "user_count": 0,
            "users": [],
        }

    def _record_audit(self, keyword: str) -> None:
        # 基类审计：只存 keyword 的 sha256 前 12 位
        try:
            super()._record_audit(
                keyword=keyword, url="", status=0, fields=[]
            )
        except Exception:
            pass
