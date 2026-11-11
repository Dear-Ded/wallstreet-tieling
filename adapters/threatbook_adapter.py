#!/usr/bin/env python3
"""微步在线 ThreatBook 威胁情报适配器 — IP/域名信誉查询。

微步在线 (threatbook.com / threatbook.cn) 是中文威胁情报厂商。
社区版免费 API 查 IP/域名是否涉恶：C2、挖矿、僵尸网络、扫描器等。

对于企业尽调，关联价值在于：
- query_ip("1.2.3.4") → 该 IP 是否恶意（severity/judgments/is_malicious）
  + 地理位置、ASN、运营商、应用场景（scene：IDC/企业专线/家庭宽带）
- query_domain("example.com") → 域名威胁判定 + 当前解析 IP（cur_ips）
  → 拿到 IP 后可再调 query_ip() 深挖基础设施是否"干净"

认证：x.threatbook.cn 免费注册 → 个人中心拿 API key。
调用参数：apikey（query 参数）。社区版每天约 1000 次。

端点说明（2026-10-21 实测）：
- 实际可用：https://api.threatbook.cn/v3/scene/ip_reputation
             https://api.threatbook.cn/v3/scene/dns
  参数：apikey, resource, lang=zh
  无效 key 返回 {"response_code":-1,"verbose_msg":"无效的API key"}
- 任务说明里的 https://x.threatbook.com/api/v1 实测 302 → /v5/notFound，
  不存在；/api/v2/* 也不存在。已按实际可用端点实现。

设计遵循 premium_keyed 模式：
- api_key 只走构造参数，不读磁盘/环境变量/配置
- 不记录 key（审计只存 query 的 sha256）
- 无 key 时 query() 返回 credentials_required，不硬崩

data_boundary="fully_public"，无凭证不调接口。
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


_API_BASE = "https://api.threatbook.cn/v3/scene"
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


class ThreatBookLookup(SafeResearchAdapter):
    """微步在线 ThreatBook 威胁情报查询。

    用法：
        t = ThreatBookLookup(api_key="xxxxxxxx")
        t.query_ip("1.2.3.4")        # IP 信誉：是否恶意、场景、ASN
        t.query_domain("example.com")  # 域名：威胁判定 + 当前解析 IP
        t.query("1.2.3.4")           # 自动识别 IP/域名
    """

    source_domain = "api.threatbook.cn"
    source_type = "infra_threatbook_threat_intel"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = (api_key or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)

    def _build_url(self, keyword: str, **params) -> str:
        kind = params.get("kind") or ("ip" if _IP_RE.match(keyword.strip()) else "domain")
        endpoint = "ip_reputation" if kind == "ip" else "dns"
        qs = urllib.parse.urlencode({
            "apikey": self._api_key,
            "resource": keyword.strip(),
            "lang": "zh",
        })
        return f"{_API_BASE}/{endpoint}?{qs}"

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        # 与基类相同，但错误信息里不回显 key（URL 含 apikey，不做原文回传）
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
        code = data.get("response_code")
        if code != 0:
            return {
                "lookup_failed": True,
                "reason": str(data.get("verbose_msg", ""))[:120],
                "response_code": code,
            }
        payload = data.get("data") or {}
        # data 是 {resource: {...}} 结构，取第一个 value
        rec: dict[str, Any] = {}
        if isinstance(payload, dict):
            for v in payload.values():
                if isinstance(v, dict):
                    rec = v
                    break
        if not rec:
            return {"no_data": True, "data_note": "接口返回成功但无数据"}

        judgments = rec.get("judgments") or []
        basic = rec.get("basic") or {}
        location = basic.get("location") or {}
        asn = rec.get("asn") or {}
        tags_classes = rec.get("tags_classes") or []

        out: dict[str, Any] = {
            "severity": rec.get("severity", ""),
            "is_malicious": rec.get("is_malicious", False),
            "judgments": judgments[:10],
            "judgment_count": len(judgments),
            "scene": rec.get("scene", ""),
            "confidence_level": rec.get("confidence_level", ""),
            "location": {
                "country": location.get("country", ""),
                "province": location.get("province", ""),
                "city": location.get("city", ""),
                "country_code": location.get("country_code", ""),
            },
            "asn": {
                "number": asn.get("number", ""),
                "info": str(asn.get("info", ""))[:80],
            },
            "carrier": basic.get("carrier", ""),
            "tags_classes": tags_classes[:10],
            "update_time": rec.get("update_time", ""),
        }

        # 域名查询额外字段：当前解析 IP（IP pivot 入口）、whois、证书
        cur_ips = rec.get("cur_ips") or []
        if cur_ips:
            out["current_ips"] = [
                str(x.get("ip", "")) for x in cur_ips
                if isinstance(x, dict) and x.get("ip")
            ][:20]
            out["current_ip_count"] = len(out["current_ips"])
        cur_whois = rec.get("cur_whois") or {}
        if cur_whois:
            out["whois_registrar"] = str(cur_whois.get("registrar_name", ""))[:60]
            out["whois_create"] = str(cur_whois.get("cdate", ""))[:20]
        cas = rec.get("cas") or []
        if cas:
            out["cert_subject"] = str(cas[0].get("subject", ""))[:80] if isinstance(cas[0], dict) else ""
        categories = rec.get("categories") or []
        if categories:
            out["categories"] = [str(c)[:30] for c in categories[:10]]

        out["data_note"] = (
            "微步 ThreatBook 社区版公开威胁情报 — "
            "malicious 判定是线索非定罪，需交叉验证"
        )
        return out

    # ---- 高层便捷方法（关联深挖入口） ----

    def query_ip(self, ip: str) -> dict[str, Any]:
        """IP → 威胁信誉（是否恶意、威胁类型、场景、ASN/位置）。

        关联用法：目标企业服务器 IP 若被标记恶意 → 基础设施风险红灯。
        """
        ip = (ip or "").strip()
        if not ip:
            return self._build_empty_result("", "empty_ip")
        return self.query(ip, kind="ip")

    def query_domain(self, domain: str) -> dict[str, Any]:
        """域名 → 威胁判定 + 当前解析 IP。

        关联用法：current_ips → 接 query_ip() 查基础设施；whois_create 看域名年龄。
        """
        domain = (domain or "").strip().lower()
        if not domain:
            return self._build_empty_result("", "empty_domain")
        return self.query(domain, kind="domain")
