"""企查查公开公司页适配器 — 经由阿里云 WAF acw_sc__v2 透明 JS 挑战的纯 Python 求解。

数据边界: fully_public / EXPERIMENTAL / default_enabled=False

Why this adapter exists:
- 企查查 (www.qcc.com) 的 /firm/{hex}.html 公司详情页是公开页面
  （搜索引擎收录、无需登录），但其阿里云 WAF 会对部分出口 IP 下发
  acw_sc__v2 JS 挑战页（HTTP 200 + 透明 proof-of-work，真人浏览器自动
  通过，无验证码、无登录）。
- 本适配器用纯 Python 复现该挑战计算（2026-10-21 实测版本），拿到
  cookie 后复访真实页面。不碰登录、不碰验证码、不伪造身份。

acw_sc__v2 算法（2026-10-21 经验性逆向，4 个独立 challenge 样本验证）：
- 挑战页 textarea#renderData 内 "var arg1='<50 hex chars>'"。
- cookie = '1234cf0d46-' + permute40(arg1[0:40]) + rand10hex
  其中 permute40 为固定 40 元置换（由 4 样本联合约束求解，唯一解模
  arg1[0:5] 固定头 '5df5b' 的等价类）：
  [7,34,35,21,0,16,4,26,11,30,15,3,32,38,31,39,5,10,14,13,2,12,8,
   17,18,22,9,23,33,24,36,25,20,6,28,27,1,37,19,29]
- 尾部 10 位随机 hex：服务端无法预知，校验时忽略（实测：带任意随机尾
  的 cookie 均通过 WAF，到达企查查应用层）。
- 若企查查更新 WAF JS（置换表/前缀变化），本算法需重新推导；
  推导方法见 docs/research/qcc-acwsv2-20261021.md。

出口：
- 经由可配置的 SOCKS5 代理（socks5h，远端 DNS）做 HTTPS 抓取，
  纯 Python 实现（socket + ssl），零新增依赖。
- 默认代理 121.46.226.221:10808 为公开免费代理（2026-10-21 可用，
  随时可能失效）；代理地址为构造参数，可替换。
- 实测记录（2026-10-21）：该默认代理 IP 已被企查查应用层暂停服务
  （423 "访问超频：当前IP触发安全规则"，verify.qcc.com/block），
  属 IP 信誉问题，与 WAF 求解无关。换干净出口即走通。

robots.txt (www.qcc.com, 2026-10-21 实测):
- Disallow: /*?*  -> 所有带 query 的 URL 禁止抓取：
  /web/search?key= 等关键词搜索路径本适配器不支持。
- /firm/{hex}.html 为干净 URL，未被 disallow：本适配器仅支持该路径。

What this adapter does NOT do:
- 不登录、不持有任何账号状态；
- 不做关键词搜索（robots Disallow /*?*）；
- 不绕验证码、不解 WAF 以外的任何验证；
- 不提取个人隐私字段（电话/身份证等不渲染不提取）。

Association value: 公司名称/法定代表人/注册资本/成立日期/经营状态
 feeding entity-association 的 business 实体（lead 级别）。
"""

from __future__ import annotations

import html as html_module
import random
import re
import socket
import ssl
import time
from typing import Any
from urllib.parse import urlparse

from adapters.safe_research_adapter import SafeResearchAdapter

# ---------------------------------------------------------------------------
# acw_sc__v2 纯 Python 求解（2026-10-21 实测版本，见模块 docstring）
# ---------------------------------------------------------------------------

_ACW_PERM = (
    7, 34, 35, 21, 0, 16, 4, 26, 11, 30,
    15, 3, 32, 38, 31, 39, 5, 10, 14, 13,
    2, 12, 8, 17, 18, 22, 9, 23, 33, 24,
    36, 25, 20, 6, 28, 27, 1, 37, 19, 29,
)
_ACW_PREFIX = "1234cf0d46-"
_ACW_ARG1_RE = re.compile(r"var arg1='([0-9a-f]{40,64})'")
_HEX16 = "0123456789abcdef"


def solve_acw_sc__v2(arg1: str) -> str:
    """由挑战页 arg1 计算 acw_sc__v2 cookie 值（纯 Python）。"""
    body = "".join(arg1[i] for i in _ACW_PERM)
    tail = "".join(random.choice(_HEX16) for _ in range(10))
    return _ACW_PREFIX + body + tail


def extract_arg1(challenge_html: str) -> str | None:
    """从 WAF 挑战页提取 arg1；非挑战页返回 None。"""
    m = _ACW_ARG1_RE.search(challenge_html)
    return m.group(1) if m else None


def is_waf_challenge(html: str) -> bool:
    return "acw_sc__v2" in html and "renderData" in html


# ---------------------------------------------------------------------------
# 纯 Python SOCKS5h + HTTPS GET（零新增依赖）
# ---------------------------------------------------------------------------

_BLOCK_MARKERS = (
    "访问超频",
    "405错误页面",
    "verify.qcc.com/block",
    "触发安全规则",
    "被暂停服务",
)

_FIRM_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S)
_FIELD_PATTERNS: dict[str, list[str]] = {
    # label -> regexes tried in order; first hit wins
    "legal_rep": [
        r"法定代表人[：:\s]*([^<>\s&]{2,12})",
        r'"legalPerson"\s*:\s*"([^"]+)"',
    ],
    "capital": [
        r"注册资本[：:\s]*([^<>\s&]{2,30})",
        r'"registCapi"\s*:\s*"([^"]+)"',
    ],
    "founded": [
        r"成立日期[：:\s]*(\d{4}[-年]\d{1,2}[-月]\d{1,2})",
        r'"foundDate"\s*:\s*"([^"]+)"',
        r'"establishDate"\s*:\s*"([^"]+)"',
    ],
    "status": [
        r"经营状态[：:\s]*([^<>\s&]{2,12})",
        r"企业状态[：:\s]*([^<>\s&]{2,12})",
        r'"entStatus"\s*:\s*"([^"]+)"',
    ],
}


def _clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def socks5h_https_get(
    proxy_host: str,
    proxy_port: int,
    host: str,
    path: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """经 SOCKS5h 代理的 HTTPS GET。返回 (status, header_text, body_text)。"""
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    try:
        # SOCKS5 greeting: no auth
        sock.sendall(b"\x05\x01\x00")
        if sock.recv(2) != b"\x05\x00":
            raise RuntimeError("socks5: proxy requires auth (unsupported)")
        # CONNECT host:443, remote DNS (socks5h)
        host_b = host.encode("idna")
        sock.sendall(
            b"\x05\x01\x00\x03" + bytes([len(host_b)]) + host_b
            + (443).to_bytes(2, "big"))
        rep = sock.recv(16)
        if len(rep) < 2 or rep[1] != 0x00:
            raise RuntimeError(f"socks5: CONNECT failed ({rep!r})")
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(sock, server_hostname=host)
        try:
            h = {
                "Host": host,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "close",
            }
            if headers:
                h.update(headers)
            req = ("GET %s HTTP/1.1\r\n" % path
                   + "".join(f"{k}: {v}\r\n" for k, v in h.items())
                   + "\r\n")
            tls.sendall(req.encode("utf-8"))
            data = b""
            while True:
                chunk = tls.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 8 * 1024 * 1024:  # 8MB cap
                    break
        finally:
            tls.close()
        head, _, body = data.partition(b"\r\n\r\n")
        head_s = head.decode("utf-8", "replace")
        try:
            status = int(head_s.split(" ", 2)[1])
        except (IndexError, ValueError):
            status = 0
        return status, head_s, body.decode("utf-8", "replace")
    finally:
        sock.close()


def parse_proxy(proxy: str) -> tuple[str, int]:
    """'host:port' 或 'socks5h://host:port' -> (host, port)。"""
    p = proxy.strip()
    if "://" in p:
        p = p.split("://", 1)[1]
    host, _, port = p.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"invalid proxy spec: {proxy!r}")
    return host, int(port)


class QccWafBypassLookup(SafeResearchAdapter):
    """企查查 /firm/{hex}.html 公开公司页：代理 + acw_sc__v2 求解。"""

    source_domain = "www.qcc.com"
    source_type = "business_registry"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 8.0  # 保守限频（任务要求 ≥8s）

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, *, proxy: str = "121.46.226.221:10808", **kwargs):
        super().__init__(**kwargs)
        self.proxy_spec = proxy
        self.proxy_host, self.proxy_port = parse_proxy(proxy)

    # ------------------------------------------------------------------ URL

    @staticmethod
    def normalize_firm_id(value: str) -> str | None:
        candidate = (value or "").strip().lower()
        if _FIRM_ID_RE.match(candidate):
            return candidate
        # allow full /firm/ URL as keyword
        m = re.search(r"/firm/([0-9a-f]{32})\.html", candidate)
        return m.group(1) if m else None

    def _build_url(self, keyword: str, **params) -> str:
        firm_id = self.normalize_firm_id(params.get("firm_id") or keyword)
        if not firm_id:
            raise ValueError(
                "qcc adapter needs a 32-hex firm id (robots.txt disallows "
                "query-string search URLs)")
        url = f"https://www.qcc.com/firm/{firm_id}.html"
        assert "?" not in url, "robots.txt Disallow /*?*"
        return url

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.qcc.com/",
        }

    # -------------------------------------------------------------- fetching

    def _fetch_via_proxy(
        self, url: str, headers: dict
    ) -> tuple[int, str, str]:
        parts = urlparse(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return socks5h_https_get(
            self.proxy_host, self.proxy_port, parts.hostname or "",
            path, headers)

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            status, head, html = self._fetch_via_proxy(url, headers)
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")
        # 阿里云 WAF 挑战：解一次，带 cookie 复访一次
        if status == 200 and is_waf_challenge(html):
            arg1 = extract_arg1(html)
            if not arg1:
                return (status, html, "waf_challenge_unparseable")
            cookie = solve_acw_sc__v2(arg1)
            headers2 = dict(headers)
            headers2["Cookie"] = "acw_sc__v2=" + cookie
            self._sleeper(2.0)
            try:
                status, head, html = self._fetch_via_proxy(url, headers2)
            except Exception as e:
                return (0, None, f"waf_retry: {type(e).__name__}: {e}")
            if is_waf_challenge(html):
                return (status, html, "waf_challenge_retry_failed")
        # 302 跳转到 405.html：WAF 按路径拦截
        if status in (301, 302):
            m = re.search(r"[Ll]ocation:\s*(\S+)", head)
            loc = m.group(1) if m else ""
            return (status, html, f"redirect_blocked: {loc}")
        return (status, html, "")

    # -------------------------------------------------------------- parsing

    @staticmethod
    def parse_firm_profile(html: str) -> dict[str, Any]:
        """解析公司详情页。返回 profile 字典；被拦返回 {'blocked': True}。"""
        if is_waf_challenge(html):
            return {"blocked": True, "block_reason": "waf_challenge_unsolved"}
        if any(mk in html for mk in _BLOCK_MARKERS):
            return {"blocked": True, "block_reason": "ip_suspended_or_405"}
        title_m = _TITLE_RE.search(html)
        title = _clean_text(title_m.group(1)) if title_m else ""
        # 公司名：标题通常为 "公司全名_企查查" / "公司全名 - 企查查"
        name = re.split(r"[_|-]\s*企查查", title)[0].strip() if title else ""
        profile: dict[str, Any] = {
            "blocked": False,
            "company_name": name,
            "page_title": title[:120],
        }
        for field, patterns in _FIELD_PATTERNS.items():
            for pat in patterns:
                m = re.search(pat, html)
                if m:
                    profile[field] = _clean_text(m.group(1))[:80]
                    break
            else:
                profile[field] = ""
        # JSON-LD 兜底
        for ld_m in _JSONLD_RE.finditer(html):
            try:
                import json as _json
                ld = _json.loads(ld_m.group(1))
            except Exception:
                continue
            if isinstance(ld, dict):
                if not profile["company_name"] and ld.get("name"):
                    profile["company_name"] = str(ld["name"])[:80]
                break
        return profile

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        html = raw_data if isinstance(raw_data, str) else ""
        profile = self.parse_firm_profile(html)
        out: dict[str, Any] = {
            "blocked": profile.get("blocked", False),
            "profile": profile,
        }
        if profile.get("block_reason"):
            out["block_reason"] = profile["block_reason"]
        return out

    # -------------------------------------------------------------- adapter

    def query_by_firm_id(self, firm_id: str, **params) -> dict[str, Any]:
        return self.query(firm_id, firm_id=firm_id, **params)
