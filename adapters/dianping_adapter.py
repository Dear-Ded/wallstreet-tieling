#!/usr/bin/env python3
"""大众点评 (Dianping) 线下商户适配器（线下商业 lane）。

回答："这家店在点评上有吗？地址/电话/评分/人均/营业状态？"

## 访问模式

**自主模式** (`query_by_shop_id` / `query_by_url`)：
大众点评移动端店铺页 (m.dianping.com/shop/{id}) 无需登录即可访问，
商户基础信息以内嵌 JSON 形式存在于 HTML 中。实测 2026-10-21 可用。

注意：非登录态下地址/电话会被掩码（如 "广州大道北******"），
这是平台的数据脱敏，不是 adapter 的问题。店名、商圈、品类、
人均、评分等基础字段可见。

**按店名搜索**：需要登录，`query()` 返回 interaction_required + 操作指引。

## 提取字段

- shop_id、shop_name、branch_name（分店名）
- address（掩码）、region_name（商圈）、city_name
- phone（掩码/可能为空）、avg_price（人均）、shop_type（品类码）
- taste_score / env_score / service_score（口味/环境/服务评分）
- comment_count（评价数）、营业状态

## 合规

- 只读公开数据，不登录、不绕过验证码
- 移动端 UA；3 秒请求间隔
- data_boundary="fully_public"；EXPERIMENTAL，默认关闭
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)
_SHOP_URL = "https://m.dianping.com/shop/{shop_id}"

# 店铺不存在时的页面特征：HTML 大小约 196608 且无有效 shopName
_NOT_FOUND_SIZE = 196608


def _extract_field(html: str, field: str, max_len: int = 80) -> str | None:
    """从内嵌 JSON 提字符串字段。"""
    m = re.search(r'"' + re.escape(field) + r'":"?([^",}]{1,' + str(max_len) + r'})', html)
    if m:
        v = m.group(1).strip()
        return v if v else None
    return None


def _extract_number(html: str, field: str) -> float | None:
    m = re.search(r'"' + re.escape(field) + r'":([0-9.]+)', html)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _fetch_html(url: str, timeout: int = 20) -> tuple[str, int]:
    """抓取页面，容忍服务器提前掐连接（IncompleteRead 取 partial）。"""
    req = urllib.request.Request(url, headers={"User-Agent": _MOBILE_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            try:
                return resp.read().decode("utf-8", errors="ignore"), status
            except Exception as e:
                partial = getattr(e, "partial", b"")
                if partial:
                    return partial.decode("utf-8", errors="ignore"), status
                raise
    except Exception:
        return "", 0


def _parse_shop_html(html: str, shop_id: str) -> dict[str, Any]:
    """解析移动端店铺页 HTML。"""
    name = _extract_field(html, "shopName", 60)
    if not name:
        return {"shop_id": shop_id, "shop_found": False}

    return {
        "shop_id": shop_id,
        "shop_found": True,
        "shop_name": name,
        "branch_name": _extract_field(html, "branchName", 60),
        "address": _extract_field(html, "address", 100),
        "region_name": _extract_field(html, "regionName", 40),
        "city_name": _extract_field(html, "cityName", 30),
        "phone": _extract_field(html, "phone", 30),
        "avg_price": _extract_number(html, "avgPrice"),
        "shop_type": _extract_number(html, "shopType"),
        "taste_score": _extract_number(html, "tasteScore"),
        "env_score": _extract_number(html, "envScore"),
        "service_score": _extract_number(html, "serviceScore"),
        "comment_count": _extract_number(html, "commentCount"),
        "source": "m.dianping.com",
        "note": "非登录态：地址/电话可能被掩码",
    }


class DianpingShopLookup(SafeResearchAdapter):
    """大众点评店铺信息查询。"""

    source_domain = "m.dianping.com"
    source_type = "local_business_listing"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params: Any) -> str:
        sid = re.sub(r"\D", "", keyword) or "0"
        return _SHOP_URL.format(shop_id=sid)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if isinstance(raw_data, dict):
            return raw_data
        return {}

    def query_by_shop_id(self, shop_id: str, **kwargs) -> dict[str, Any]:
        """按店铺 ID 查询（自主模式）。"""
        shop_id = re.sub(r"\D", "", str(shop_id))
        if not shop_id:
            return {"shop_found": False, "error": "invalid_shop_id"}

        self._check_robots()
        self._enforce_rate_limit()
        url = _SHOP_URL.format(shop_id=shop_id)
        req = urllib.request.Request(url, headers={"User-Agent": _MOBILE_UA})
        html, status = _fetch_html(url)
        if not html:
            self._record_audit(shop_id, url, 0, ["shop_id"])
            return {"shop_id": shop_id, "shop_found": False, "error": "fetch_failed"}

        result = _parse_shop_html(html, shop_id)
        fields = [k for k in result.keys() if k not in ("shop_id",)]
        self._record_audit(shop_id, url, status, fields)
        return result

    def query_by_url(self, url: str, **kwargs) -> dict[str, Any]:
        """按店铺 URL 查询（自动提取 ID）。"""
        m = re.search(r"dianping\.com/shop/(\d+)", url)
        if not m:
            return {"shop_found": False, "error": "invalid_url"}
        return self.query_by_shop_id(m.group(1), **kwargs)

    def query(self, keyword: str, **kwargs) -> dict[str, Any]:
        """按店名搜索需要登录态，返回操作指引。

        如果 keyword 看起来像店铺 ID 或 URL，走自主模式。
        """
        kw = keyword.strip()
        if re.fullmatch(r"\d{5,12}", kw):
            return self.query_by_shop_id(kw, **kwargs)
        if "dianping.com/shop/" in kw:
            return self.query_by_url(kw, **kwargs)
        return {
            "interaction_required": True,
            "reason": "dianping_search_requires_login",
            "instructions": [
                "1. 在手机/浏览器打开大众点评，搜索目标店铺",
                "2. 进入店铺页，复制 URL（形如 m.dianping.com/shop/12345678）",
                "3. 调用 query_by_url(url) 或 query_by_shop_id(shop_id) 获取结构化数据",
            ],
            "autonomous_alternative": "已知店铺 ID 时可直接调用 query_by_shop_id",
        }
