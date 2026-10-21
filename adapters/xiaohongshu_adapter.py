#!/usr/bin/env python3
"""小红书 (xiaohongshu.com) 商户笔记查询适配器 — 线下商业 lane.

小红书是中国线下商户 (餐厅、店铺) 最重要的评价/种草平台,
个体工商户在上面有海量用户生成内容 (探店笔记、评价、实拍)。
对线下尽调的价值:商户口碑、经营活跃度、用户实拍、地址/营业时间线索。

**重要:Browser-assisted 模式**
本站要求登录后才能使用搜索 API,直接 HTTP 调用被重定向到 /login。
但公开笔记内容对未登录用户在浏览器中可见 (仅有登录弹窗遮挡),
开源项目 red-crawler (PyPI) 已验证:Playwright 打开页面后关闭登录弹窗即可继续浏览。
本适配器不绕过登录、不破解验证,而是:
1. query() 返回 interaction_required,附带浏览器/Playwright 操作指引
2. 操作员在浏览器中完成搜索 (或用 Playwright 按指引自动关闭弹窗) 后,
   将笔记列表 JSON 传入 parse_browser_result() 进行结构化提取

公开数据,无需登录,无需凭证。3 秒间隔。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class XiaohongshuNoteLookup(SafeResearchAdapter):
    """小红书商户相关笔记查询 (browser-assisted).

    查询维度:商户名称/关键词 (如"海底捞 中关村")
    提取字段:笔记标题、作者、点赞数、笔记 ID、图片、发布时间、POI 地点 (如有)
    """

    source_domain = "xiaohongshu.com"
    source_type = "social_commerce_notes"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True  # 需要浏览器辅助完成搜索
    min_request_interval = 3.0

    SEARCH_URL = "https://www.xiaohongshu.com/search_result"
    EXPLORE_URL = "https://www.xiaohongshu.com/explore"

    BROWSER_INSTRUCTIONS = (
        "小红书商户笔记查询 (无需登录,公开内容):\n"
        "方法 A — 手动浏览器:\n"
        "1. 在浏览器中打开 https://www.xiaohongshu.com/explore\n"
        "2. 如出现登录弹窗,直接关闭 (右上角 X),无需登录\n"
        "3. 在搜索框输入商户名称 (如'海底捞 中关村')\n"
        "4. 浏览搜索结果,打开浏览器开发者工具 (F12) > Network\n"
        "5. 找到搜索 API 请求,复制 Response JSON\n"
        "6. 调用 parse_browser_result(response_json) 解析\n"
        "方法 B — Playwright 自动 (参考 red-crawler):\n"
        "1. pip install playwright && playwright install chromium\n"
        "2. 打开 https://www.xiaohongshu.com/explore\n"
        "3. 等待登录弹窗出现,用 page.click() 关闭弹窗\n"
        "4. 定位搜索框,输入关键词并回车\n"
        "5. 等待笔记卡片加载,提取页面上的笔记数据\n"
        "注意:不要尝试登录,不要使用任何账号。只查看公开可见内容。"
    )

    def _build_url(self, keyword: str, **params) -> str:
        from urllib.parse import urlencode
        return f"{self.SEARCH_URL}?{urlencode({'keyword': keyword, 'source': 'web_search_result'})}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """基类抽象方法:委托给 parse_browser_result 的字段提取逻辑。"""
        parsed = self.parse_browser_result(raw_data) if isinstance(raw_data, (str, dict)) else None
        if parsed and "fields" in parsed:
            return parsed["fields"]
        return {}

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """返回 interaction_required,不直接发起搜索请求。"""
        start = time.monotonic()
        self._enforce_rate_limit()
        self._record_audit(
            keyword=keyword,
            url=self._build_url(keyword),
            status=0,
            fields=[],
        )
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "fields": {},
            "field_count": 0,
            "error": "interaction_required",
            "interaction_instructions": self.BROWSER_INSTRUCTIONS,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    def parse_browser_result(self, response_json: str | dict) -> dict[str, Any]:
        """解析从浏览器复制的小红书搜索/笔记列表 JSON.

        支持两种输入形状:
        1. 搜索 API 响应: {"data": {"items": [{"id": ..., "note_card": {...}}]}}
        2. 笔记卡片列表: [{"id": ..., "title": ..., ...}]
        """
        start = time.monotonic()
        if isinstance(response_json, str):
            try:
                data = json.loads(response_json)
            except (json.JSONDecodeError, ValueError):
                return self._empty_result("invalid_json", start)
        elif isinstance(response_json, dict):
            data = response_json
        else:
            return self._empty_result("invalid_input_type", start)

        items = self._extract_items(data)
        notes = [self._parse_note(item) for item in items]
        notes = [n for n in notes if n]  # 过滤解析失败的

        # 汇总 POI 地点线索
        poi_mentions: dict[str, int] = {}
        for n in notes:
            loc = n.get("location") or ""
            if loc:
                poi_mentions[loc] = poi_mentions.get(loc, 0) + 1

        result = {
            "query_subject_hash": "",
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 200,
            "fields": {
                "note_count": len(notes),
                "notes": notes,
                "poi_mentions": poi_mentions,
            },
            "field_count": 3,
            "duration_ms": (time.monotonic() - start) * 1000,
        }
        self._record_audit(
            keyword="browser_result_parse",
            url=self.SEARCH_URL,
            status=200,
            fields=["note_count", "notes", "poi_mentions"],
        )
        return result

    def _extract_items(self, data: dict) -> list:
        """从多种响应形状中提取笔记条目列表。"""
        # 形状 1: {"data": {"items": [...]}}
        d = data.get("data", {})
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            return d["items"]
        # 形状 2: {"items": [...]}
        if isinstance(data.get("items"), list):
            return data["items"]
        # 形状 3: {"notes": [...]}
        if isinstance(data.get("notes"), list):
            return data["notes"]
        # 形状 4: 直接是列表 (调用方传了 list,包一层)
        return []

    def _parse_note(self, item: dict) -> dict[str, Any] | None:
        """解析单条笔记。兼容 note_card 包裹和扁平两种形状。"""
        if not isinstance(item, dict):
            return None
        # 有些响应把笔记包在 note_card 里
        card = item.get("note_card", item)
        if not isinstance(card, dict):
            return None

        note_id = str(item.get("id") or card.get("note_id") or "")
        title = card.get("title") or card.get("display_title") or ""
        desc = card.get("desc") or ""
        author = ""
        user = card.get("user", {})
        if isinstance(user, dict):
            author = user.get("nickname") or user.get("nick_name") or ""

        # 互动数据
        interact = card.get("interact_info", {})
        liked_count = 0
        collected_count = 0
        comment_count = 0
        if isinstance(interact, dict):
            try:
                liked_count = int(interact.get("liked_count", 0) or 0)
                collected_count = int(interact.get("collected_count", 0) or 0)
                comment_count = int(interact.get("comment_count", 0) or 0)
            except (ValueError, TypeError):
                pass

        # 图片
        images: list[str] = []
        cover = card.get("cover", {})
        if isinstance(cover, dict):
            url = cover.get("url") or ""
            if url:
                images.append(url)

        # POI / 地点
        location = ""
        poi = card.get("poi") or item.get("poi") or {}
        if isinstance(poi, dict):
            location = poi.get("name") or poi.get("poi_name") or ""
        if not location:
            location = card.get("location") or ""

        # 发布时间
        publish_time = card.get("time") or card.get("publish_time") or ""

        if not note_id and not title:
            return None

        return {
            "note_id": note_id,
            "title": title,
            "desc": desc[:500],  # 截断过长描述
            "author": author,
            "liked_count": liked_count,
            "collected_count": collected_count,
            "comment_count": comment_count,
            "images": images[:5],
            "location": location,
            "publish_time": str(publish_time),
            "note_url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
        }

    def _empty_result(self, reason: str, start: float) -> dict[str, Any]:
        return {
            "query_subject_hash": "",
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "fields": {},
            "field_count": 0,
            "error": reason,
            "duration_ms": (time.monotonic() - start) * 1000,
        }
