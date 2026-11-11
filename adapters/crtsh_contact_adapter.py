#!/usr/bin/env python3
"""证书联系人提取适配器（crt.sh 历史证书 + 直连 443 当前证书）。

回答："这个域名的证书里出现过哪些组织名/联系人邮箱？→ person/org 实体。"

与现有 CertTransparencyLookup（adapters/cert_transparency_adapter.py，
connector public_cert_transparency）的去重说明：
    - 现有 adapter 做"同证书 → 关联域名"的 infra pivoting（domain 实体）。
    - 本 adapter 做"证书主体/签发者 → 组织名/联系邮箱"的 person/org 提取，
      字段（org_names / contact_emails / subject）与现有 adapter 无重叠。

Survey（2026-10-21 实测）：
    - https://crt.sh/?q=%.<domain>&output=json 免 key、无认证（Sectigo
      运营的公开 CT 日志搜索引擎）；实测时段连续 502（该服务偶发过载，
      已知 flaky），adapter 对 5xx 优雅降级（service_unavailable）。
    - crt.sh output=json 字段：issuer_name / common_name / name_value(SAN) /
      not_before / not_after —— 不含 subject 组织/邮箱字段。
    - 诚实结论：现代 DV 证书主体几乎不含邮箱（emailAddress 已绝迹多年）
      与组织名（OV/EV 才有 O 字段）。本 adapter 的联系人产出来源：
      (1) crt.sh 的 issuer_name（CA 组织，可排除噪音）、common_name；
      (2) 直连目标 443 读取当前证书 subject 的 O/OU/emailAddress
      （query_live_subject，不依赖 crt.sh）。
      产出以 org 名为主、邮箱为辅，均为 leads。

robots：crt.sh 根 robots.txt 实测时段同样 502；基类 robots 检查走站点根，
失败时按 RobotFileParser 默认语义处理；本 adapter 另对 443 直连不做
robots 检查（TLS 握手非 HTTP 抓取）。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_CRTSH_BASE = "https://crt.sh/"


def _safe_str(v: Any, limit: int = 200) -> str:
    return str(v or "")[:limit]


# 常见 CA 组织名噪音：issuer 里出现即视为 CA 而非目标组织
_CA_NOISE = (
    "let's encrypt", "letsencrypt", "digicert", "sectigo", "comodo",
    "globalsign", "godaddy", "amazon", "cloudflare", "google trust",
    "entrust", "geotrust", "thawte", "rapidssl", "zerossl",
)


def _looks_like_ca(org: str) -> bool:
    low = org.lower()
    return any(n in low for n in _CA_NOISE)


class CrtshContactLookup(SafeResearchAdapter):
    """证书联系人提取：域名 → 证书主体/签发者中的组织名与联系邮箱。"""

    source_domain = "crt.sh"
    source_type = "infrastructure_cert_contacts"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        domain = keyword.strip().lower().lstrip(".")
        q = "%." + domain if params.get("wildcard", True) else domain
        query = urllib.parse.urlencode({"q": q, "output": "json"})
        return _CRTSH_BASE + "?" + query

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "wallstreet-tieling/0.5 (research; public CT log contact query)",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True, "org_names": [], "contact_emails": []}
        if isinstance(data, dict) and data.get("error"):
            return {"lookup_failed": True, "reason": _safe_str(data.get("error"), 120),
                    "org_names": [], "contact_emails": []}
        if not isinstance(data, list):
            return {"parse_error": True, "data_note": "unexpected response shape",
                    "org_names": [], "contact_emails": []}

        orgs: list[str] = []
        emails: list[str] = []

        def _add_org(o: str, origin: str) -> None:
            o = _safe_str(o, 160).strip()
            if not o or _looks_like_ca(o):
                return
            if all(x["name"] != o for x in orgs):
                orgs.append({"name": o, "origin": origin})

        def _add_email(e: str, origin: str) -> None:
            e = _safe_str(e, 160).strip()
            if not e or "@" not in e:
                return
            if all(x["email"] != e for x in emails):
                emails.append({"email": e, "origin": origin})

        for entry in data[:200]:
            if not isinstance(entry, dict):
                continue
            issuer = str(entry.get("issuer_name", ""))
            # issuer_name 形如 "C=US, O=Let's Encrypt, CN=R3"：取 O= 段
            for part in issuer.split(","):
                part = part.strip()
                if part.upper().startswith("O="):
                    _add_org(part[2:], "crtsh_issuer")
            cn = str(entry.get("common_name", "") or "")
            if "@" in cn:
                _add_email(cn, "crtsh_common_name")
            # SAN 里偶见 rfc822Name 邮箱
            for line in str(entry.get("name_value", "") or "").splitlines():
                line = line.strip()
                if "@" in line and " " not in line:
                    _add_email(line, "crtsh_san")

        return {
            "cert_count": len(data),
            "org_names": orgs[:20],
            "org_count": len(orgs),
            "contact_emails": emails[:20],
            "contact_email_count": len(emails),
            "data_note": (
                "crt.sh 公开 CT 日志的联系人提取：现代 DV 证书主体通常无"
                "邮箱/组织字段，产出以 OV/EV 证书的组织名为主；"
                "issuer 中的 CA 名已过滤。均为 leads，需其他来源佐证。"
            ),
        }

    def query(self, keyword: str, **params) -> dict[str, Any]:  # type: ignore[override]
        result = super().query(keyword, **params)
        status = int(result.get("response_status") or 0)
        if status >= 500:
            fields = result.get("fields") or {}
            fields["service_unavailable"] = True
            fields["data_note"] = (
                "crt.sh 服务暂不可用（公开服务偶发 502/超时），"
                "可稍后重试或改用 query_live_subject() 直连目标 443 读取当前证书主体"
            )
            result["fields"] = fields
        return result

    # -- 不依赖 crt.sh 的直连路径 --------------------------------------
    def query_live_subject(self, domain: str, timeout: float = 10.0) -> dict[str, Any]:
        """直连 domain:443 读取当前 TLS 证书 subject 的 O/OU/emailAddress。

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
            return {"lookup_failed": True, "reason": f"tls_fetch_failed: {type(exc).__name__}",
                    "org_names": [], "contact_emails": []}
        orgs: list[dict[str, str]] = []
        emails: list[dict[str, str]] = []
        for seq in (cert.get("subject") or ()):  # type: ignore[union-attr]
            for key, val in seq:
                v = _safe_str(val, 160)
                if key == "organizationName" and v and not _looks_like_ca(v):
                    if all(x["name"] != v for x in orgs):
                        orgs.append({"name": v, "origin": "live_cert_subject"})
                elif key == "organizationalUnitName" and v:
                    if all(x["name"] != v for x in orgs):
                        orgs.append({"name": v, "origin": "live_cert_subject_ou"})
                elif key == "emailAddress" and "@" in v:
                    if all(x["email"] != v for x in emails):
                        emails.append({"email": v, "origin": "live_cert_subject"})
        return {
            "cert_count": 1,
            "org_names": orgs[:20],
            "org_count": len(orgs),
            "contact_emails": emails[:20],
            "contact_email_count": len(emails),
            "data_note": (
                "直连 443 读取的当前证书主体（非历史）：O/OU 组织名仅 OV/EV"
                "证书有；emailAddress 在现代公网证书中已绝迹。均为 leads。"
            ),
        }

    @staticmethod
    def parse_crtsh_result(raw: Any) -> dict[str, Any]:
        """供测试与外部调用的纯函数解析入口（离线可测）。"""
        inst = CrtshContactLookup.__new__(CrtshContactLookup)
        return CrtshContactLookup._extract_public_fields(inst, raw)
