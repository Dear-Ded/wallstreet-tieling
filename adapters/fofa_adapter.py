#!/usr/bin/env python3
"""FOFA 网络空间测绘适配器 — domain→IP→同IP资产→关联企业。

FOFA (fofa.info) 是中文网络空间搜索引擎："互联网上的指纹"。对于企业尽调，
它的关联价值在于：
- domain="example.com" → 该域名暴露的全部资产（IP/端口/标题/ICP）
- ip="1.2.3.4" → 同一 IP 上的旁站域名（同一运营者强信号）
- icp 字段：FOFA 从页面提取的 ICP 备案号 → 接 icp_beian 适配器 → 主办单位

认证：FOFA 注册用户（免费注册即可）在个人资料页拿到 API key。
调用参数：email + key。免费版每天约 100 次查询。

设计遵循 premium_keyed 模式：
- email/api_key 只走构造参数，不读磁盘/环境变量/配置
- 不记录 key（审计只存 query 的 sha256）
- 无 key 时 query() 返回 credentials_required，不硬崩

data_boundary="fully_public"，无凭证不调接口。
"""
from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


_FOFA_FIELDS = "host,ip,port,protocol,title,icp,domain,cert,country,city,server"


class FofaLookup(SafeResearchAdapter):
    """FOFA 网络空间测绘查询。

    用法：
        f = FofaLookup(email="you@example.com", api_key="xxxxxxxx")
        f.query_domain("example.com")   # 域名 → 资产/IP/ICP
        f.query_ip("1.2.3.4")           # IP → 旁站域名
        f.query('cert="example.com"')   # 原生 FOFA 语法
    """

    source_domain = "fofa.info"
    source_type = "infra_fofa_asset_intel"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, email: str | None = None, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._email = (email or "").strip()
        self._api_key = (api_key or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._email) and bool(self._api_key)

    def _encode_query(self, fofa_query: str) -> str:
        return base64.b64encode(fofa_query.encode("utf-8")).decode("ascii")

    def _build_url(self, keyword: str, **params) -> str:
        qbase64 = self._encode_query(keyword)
        size = params.get("size", 25)
        fields = params.get("fields", _FOFA_FIELDS)
        qs = urllib.parse.urlencode({
            "email": self._email,
            "key": self._api_key,
            "qbase64": qbase64,
            "size": size,
            "fields": fields,
        })
        return f"https://fofa.info/api/v1/search/all?{qs}"

    def _check_robots(self) -> bool:
        # fofa.info/robots.txt 是 "User-Agent: * / Disallow:"（空 = 全放行），
        # 但 Python robotparser 对该格式解析出空 entries 导致 can_fetch 误判 False。
        # 2026-10-21 实测确认：空 Disallow = 允许所有路径。
        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            in_wildcard = False
            for line in content.split("\n"):
                line = line.strip()
                if line.lower().startswith("user-agent:"):
                    ua = line.split(":", 1)[1].strip()
                    in_wildcard = ua in ("*", "WallstreetTieling/0.6")
                elif in_wildcard and line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path == "" or path == "/api":
                        return path == ""
            return True
        except Exception:
            return True

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        # 与基类相同，但错误信息里不回显 key（URL 含 key，不做原文回传）
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, body, ""
        except Exception as exc:  # noqa: BLE001
            return 0, None, f"request_failed: {type(exc).__name__}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, dict):
            return {"parse_error": True}
        if data.get("error"):
            return {
                "lookup_failed": True,
                "reason": str(data.get("errmsg", ""))[:120],
            }
        results = data.get("results") or []
        assets: list[dict[str, Any]] = []
        ips: list[str] = []
        domains: list[str] = []
        icps: list[str] = []
        for row in results[:50]:
            if not isinstance(row, (list, tuple)):
                continue
            # fields 顺序: host,ip,port,protocol,title,icp,domain,cert,country,city,server
            rec = {
                "host": str(row[0]) if len(row) > 0 else "",
                "ip": str(row[1]) if len(row) > 1 else "",
                "port": row[2] if len(row) > 2 else "",
                "protocol": str(row[3]) if len(row) > 3 else "",
                "title": str(row[4])[:80] if len(row) > 4 else "",
                "icp": str(row[5]) if len(row) > 5 else "",
                "domain": str(row[6]) if len(row) > 6 else "",
                "cert": str(row[7])[:60] if len(row) > 7 else "",
                "country": str(row[8]) if len(row) > 8 else "",
                "city": str(row[9]) if len(row) > 9 else "",
                "server": str(row[10])[:40] if len(row) > 10 else "",
            }
            assets.append(rec)
            if rec["ip"] and rec["ip"] not in ips:
                ips.append(rec["ip"])
            for d in (rec["domain"], rec["host"]):
                if d and d not in domains:
                    domains.append(d)
            if rec["icp"] and rec["icp"] not in icps:
                icps.append(rec["icp"])
        return {
            "total": data.get("size", len(results)),
            "asset_count": len(assets),
            "assets": assets[:25],
            "unique_ips": ips[:30],
            "unique_ip_count": len(ips),
            "unique_domains": domains[:30],
            "unique_domain_count": len(domains),
            "icp_numbers": icps[:20],
            "data_note": "FOFA 公开测绘数据 — 旁站域名/ICP 号是关联企业线索，需交叉验证",
        }

    # ---- 高层便捷方法（关联深挖入口） ----

    def query_domain(self, domain: str, size: int = 25) -> dict[str, Any]:
        """域名 → 暴露资产、IP、ICP 备案号。

        关联用法：拿到的 IP 再调 query_ip() 找旁站；ICP 号接 icp_beian 查主办单位。
        """
        domain = (domain or "").strip().lower()
        if not domain:
            return self._build_empty_result("", "empty_domain")
        return self.query(f'domain="{domain}"', size=size)

    def query_ip(self, ip: str, size: int = 25) -> dict[str, Any]:
        """IP → 同一 IP 上的全部资产/旁站域名。

        关联用法：旁站域名 → 同一运营者/同一企业强信号。
        """
        ip = (ip or "").strip()
        if not ip:
            return self._build_empty_result("", "empty_ip")
        return self.query(f'ip="{ip}"', size=size)

    def query_icp(self, icp_no: str, size: int = 25) -> dict[str, Any]:
        """ICP 备案号 → 使用该备案号的全部站点。

        关联用法：同一备案号 → 同一主办单位 → 关联企业图谱。
        """
        icp_no = (icp_no or "").strip()
        if not icp_no:
            return self._build_empty_result("", "empty_icp")
        return self.query(f'icp="{icp_no}"', size=size)
