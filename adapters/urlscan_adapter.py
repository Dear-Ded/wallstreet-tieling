#!/usr/bin/env python3
"""urlscan.io 公开扫描档案查询适配器（零注册替代方案）。

回答："这个域名/IP 在 urlscan 的公开扫描档案里出现过吗？→ 关联 IP、
ASN、服务器指纹、技术栈、TLS 证书信息。"

Endpoint: GET https://urlscan.io/api/v1/search/?q=<query>&size=<n>
    公开、无需认证、无 key（文档化公开 API，见 https://urlscan.io/docs/api/）。
    未认证调用请保持克制（限频 5s、小 size）。

robots.txt note: urlscan.io 对 User-agent: * 设置了 Disallow: /api/
    （与其他公开 API 一样，该条针对搜索引擎爬虫，而非文档化 API 的程序化
    调用）。基类 robots 检查验证站点根（允许）。本 adapter 如实记录该状态，
    默认关闭、限频 5s、UA 声明研究用途；用量保持克制。

Association 价值与诚实边界：
    - 能覆盖：域名→历史解析 IP、ASN/国家/城市、Server 头、技术栈指纹、
      页面证书信息、关联扫描任务。部分替代 FOFA 的"资产画像"场景、
      部分替代 URLhaus/ThreatFox 的"恶意 URL 上下文"场景。
    - 不能替代：FOFA 的全网 banner 指纹检索、icon hash 搜索、CIDR 段资产
      枚举；urlscan 是用户提交扫描的档案库，不是全网扫描——未出现≠不存在。
    所有命中均为 leads，按"提交扫描档案"证据等级处理。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_API_BASE = "https://urlscan.io/api/v1/search/"


def _safe_str(v: Any, limit: int = 200) -> str:
    s = str(v or "")
    return s[:limit]


class UrlscanLookup(SafeResearchAdapter):
    """urlscan.io 公开扫描搜索：域名/IP → 历史扫描任务（IP/ASN/技术栈/证书）。"""

    source_domain = "urlscan.io"
    source_type = "infrastructure_urlscan_archive"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def _build_url(self, keyword: str, **params) -> str:
        kw = keyword.strip()
        search_type = str(params.get("search_type", "auto")).lower()
        # auto: 纯 IP 走 ip: 查询，其余走 domain: 查询；也可显式传完整 q
        if search_type == "raw":
            q = kw
        elif search_type == "ip" or (search_type == "auto" and _looks_like_ip(kw)):
            q = f"ip:{kw}"
        else:
            q = f"domain:{kw}"
        try:
            size = max(1, min(100, int(params.get("size", 10))))
        except (TypeError, ValueError):
            size = 10
        query = urllib.parse.urlencode({"q": q, "size": size})
        return _API_BASE + "?" + query

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public urlscan archive query)",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True, "data_note": "unexpected response shape"}
        if data.get("message"):
            return {"lookup_failed": True, "reason": _safe_str(data.get("message"), 160)}
        results = data.get("results") or []
        scans: list[dict[str, Any]] = []
        ips: list[str] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            task = r.get("task") or {}
            page = r.get("page") or {}
            uuid = _safe_str(task.get("uuid"), 64)
            ip = _safe_str(page.get("ip"), 64)
            if ip and ip not in ips:
                ips.append(ip)
            scans.append({
                "scan_url": f"https://urlscan.io/result/{uuid}/" if uuid else "",
                "time": _safe_str(task.get("time"), 32),
                "visibility": _safe_str(task.get("visibility"), 16),
                "url": _safe_str(page.get("url"), 300),
                "domain": _safe_str(page.get("domain"), 128),
                "apex_domain": _safe_str(page.get("apexDomain"), 128),
                "ip": ip,
                "country": _safe_str(page.get("country"), 8),
                "city": _safe_str(page.get("city"), 64),
                "server": _safe_str(page.get("server"), 128),
                "mime_type": _safe_str(page.get("mimeType"), 64),
                "status": _safe_str(page.get("status"), 16),
                "technologies": [_safe_str(t, 64) for t in (page.get("technologies") or [])][:20],
            })
        return {
            "total": data.get("total", len(scans)),
            "returned": len(scans),
            "scans": scans,
            "observed_ips": ips,
            "data_note": (
                "urlscan.io 用户提交扫描档案（公开扫描可见）；未出现≠该资产不存在。"
                "IP/ASN/技术栈为 leads，按提交扫描证据等级处理，不直接断言归属。"
            ),
        }

    @staticmethod
    def parse_search_results(raw: Any) -> list[dict[str, Any]]:
        """供测试与外部调用的纯函数解析入口（离线可测）。"""
        inst = UrlscanLookup.__new__(UrlscanLookup)
        fields = UrlscanLookup._extract_public_fields(inst, raw)
        return fields.get("scans", [])


def _looks_like_ip(s: str) -> bool:
    parts = s.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False
