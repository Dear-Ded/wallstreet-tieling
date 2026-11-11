#!/usr/bin/env python3
"""证书透明度（Certificate Transparency）关联适配器。

回答："这个域名和哪些域名用的是同一张证书？→ 背后是不是同一个运营主体？"

核心 OSINT 动作 — 基础设施 pivoting：
    域名 --(同一证书)--> 关联域名 --(WHOIS/备案/POI)--> 关联企业图谱

Endpoint: GET https://crt.sh/?q=<domain>&output=json
    公开、无需认证、无 key。crt.sh 是 Sectigo 运营的公开 CT 日志搜索引擎，
    数据来自各大 CA 提交的证书透明度日志（RFC 6962），100% 公开。

Association 逻辑：
    同一张证书的 Subject Alternative Names (SANs) 里出现的域名，
    在绝大多数情况下属于同一运营主体（同一公司申请的多域名证书、
    或同一 CDN/云服务账号下的域名）。这是基础设施层关联的标准 pivoting 点。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。

注意：
    crt.sh 偶发 502/超时（公开服务负载高），adapter 对 5xx 做优雅降级，
    返回 service_unavailable 而不是硬崩。另提供 query_live_cert()
    直连目标 443 端口读当前证书 SAN（不依赖 crt.sh）。
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


def _parse_san_field(name_value: str) -> list[str]:
    """解析 crt.sh 的 name_value 字段（换行分隔的 SAN 列表）。"""
    domains: list[str] = []
    for line in (name_value or "").splitlines():
        d = line.strip().lower()
        if not d:
            continue
        # 去掉通配符前缀用于归一化，但保留原始记录
        domains.append(d)
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


class CertTransparencyLookup(SafeResearchAdapter):
    """crt.sh 证书透明度查询：域名 → 证书 → 同证书 SAN 域名（关联运营主体）。"""

    source_domain = "crt.sh"
    source_type = "infrastructure_cert_transparency"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0

    def _build_url(self, keyword: str, **params) -> str:
        domain = keyword.strip().lower().lstrip(".")
        # 精确域名；wildcard 模式用 %.domain，由 params 控制
        if params.get("wildcard"):
            q = "%." + domain
        else:
            q = domain
        query = urllib.parse.urlencode({"q": q, "output": "json"})
        return "https://crt.sh/?" + query

    def _build_headers(self) -> dict[str, str]:
        # crt.sh 对无 UA 的请求偶发 403，给一个合规的研究 UA
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public CT log query)",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if isinstance(data, dict) and data.get("error"):
            # crt.sh 错误形状
            return {"lookup_failed": True, "reason": str(data.get("error"))[:120]}
        if not isinstance(data, list):
            return {"parse_error": True, "data_note": "unexpected response shape"}

        certs: list[dict[str, Any]] = []
        all_sans: list[str] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            sans = _parse_san_field(str(entry.get("name_value", "")))
            for s in sans:
                if s not in all_sans:
                    all_sans.append(s)
            certs.append({
                "cert_id": entry.get("id"),
                "issuer_name": entry.get("issuer_name", ""),
                "common_name": entry.get("common_name", ""),
                "sans": sans,
                "san_count": len(sans),
                "not_before": entry.get("not_before", ""),
                "not_after": entry.get("not_after", ""),
                "serial": str(entry.get("serial_number", ""))[:64],
            })
        # 限制返回证书条数，防止超大域名（如 *.github.com）刷爆
        return {
            "cert_count": len(certs),
            "certs": certs[:50],
            "associated_domains": all_sans[:200],
            "associated_domain_count": len(all_sans),
            "data_note": (
                "crt.sh 公开 CT 日志 — 同证书 SAN 域名通常属同一运营主体，"
                "仅作关联线索，需结合 WHOIS/备案/工商进一步确认"
            ),
        }

    # -- 弹性：crt.sh 5xx 时的错误归一化 -------------------------------
    def query(self, keyword: str, **params) -> dict[str, Any]:  # type: ignore[override]
        result = super().query(keyword, **params)
        status = int(result.get("response_status") or 0)
        if status >= 500:
            fields = result.get("fields") or {}
            fields["service_unavailable"] = True
            fields["data_note"] = (
                "crt.sh 服务暂不可用（公开服务偶发 502/超时），"
                "可稍后重试或改用 query_live_cert() 直连目标 443 端口读当前证书"
            )
            result["fields"] = fields
        return result

    # -- 不依赖 crt.sh 的直连路径 --------------------------------------
    def query_live_cert(self, domain: str, timeout: float = 10.0) -> dict[str, Any]:
        """直连 domain:443 读取当前 TLS 证书的 SAN（不经过 crt.sh）。

        返回与 query() 同形的 fields 字典。目标无 HTTPS / 连接失败时
        返回 lookup_failed。
        """
        host = domain.strip().lower().lstrip(".")
        self._enforce_rate_limit()
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
        except Exception as exc:  # noqa: BLE001 - 网络错误归一化
            return {"lookup_failed": True, "reason": f"tls_fetch_failed: {type(exc).__name__}"}
        sans: list[str] = []
        for typ, val in (cert.get("subjectAltName") or []):
            if typ == "DNS" and val:
                v = val.strip().lower()
                if v not in sans:
                    sans.append(v)
        issuer = cert.get("issuer") or ()
        issuer_name = ", ".join(
            f"{k}={v}" for seq in issuer for k, v in seq
        )[:200]
        subject = cert.get("subject") or ()
        cn = ""
        for seq in subject:
            for k, v in seq:
                if k == "commonName":
                    cn = v
        return {
            "cert_count": 1,
            "certs": [{
                "cert_id": None,
                "issuer_name": issuer_name,
                "common_name": cn,
                "sans": sans,
                "san_count": len(sans),
                "not_before": cert.get("notBefore", ""),
                "not_after": cert.get("notAfter", ""),
                "serial": str(cert.get("serialNumber", ""))[:64],
            }],
            "associated_domains": sans,
            "associated_domain_count": len(sans),
            "data_note": (
                "直连 443 读取的当前证书 SAN（非历史）— 同证书域名通常属同一运营主体，仅作线索"
            ),
        }
