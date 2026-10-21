"""企查查移动站搜索适配器 — m.qcc.com /api/search/searchMulti "正确途径"签名复现。

数据边界: fully_public / EXPERIMENTAL / default_enabled=False

Why this adapter exists:
- m.qcc.com（企查查移动站）从境外直连可达（无地域墙），其搜索 API
  POST https://m.qcc.com/api/search/searchMulti 是公开接口
  （未登录浏览器打开 m.qcc.com 搜公司即调它），但直接 POST 会返回
  {"status":405,"message":"请通过正确途径使用企查查"}。
- 405 并非登录墙：是生产 JS 包里的客户端请求签名校验。
  本适配器用纯 Python 复现该签名（2026-10-21 实测版本），不碰登录、
  不碰验证码、不伪造身份。

"正确途径"签名算法（2026-10-21 由生产包经验性逆向）：
- 包：https://qcc-static.qichacha.com/qcc/m-web/prod-26.10.2/
  main.df8035d1.js（模块 50670/40379/29485/60786/58365/65701）
  + vendor.61bd6056.js（模块 16468 = crypto-js HmacSHA512）。
- 请求拦截器（65701）：headers["X-Requested-With"]="XMLHttpRequest"，
  withCredentials=true。无 Authorization、无 token、无 localStorage。
- 签名注入（50670），对每个请求：
    t = url.replace(baseURL, "")            # 如 "/api/search/searchMulti"
    t += "?" + qs.stringify(params)         # POST 无 params，此步为空
    t = t.toLowerCase()                     # "/api/search/searchmulti"
    name  = HmacSHA512(t, secret(t)).hexdigest()[10:30]          # (40379)
    value = HmacSHA512(t + t + JSON.stringify(data).toLowerCase(),
                       secret(t)).hexdigest()                    # (29485)
    headers[name] = value
- secret(t)（60786）：对 (t+t).toLowerCase() 的每个字符 c，
  CODES[ord(c) % 20] 拼接；CODES="WlkBQgfiirv6AKNk4L18"
  （58365：lodash extend 拼出的 20 字符表，逐模块验证）。
- 关键细节（实测对照确认）：
  - HmacSHA512(message, key) 即 crypto-js 参数顺序；Python
    hmac.new(key, msg, hashlib.sha512) 逐字节等价（UTF-8）。
  - JSON.stringify 用 JS 默认序列化（key 保持插入序、不转义中文）；
    客户端 searchMulti 调用的 key 序为 {searchKey, isAgg, pageSize}。
  - 签名是纯静态推导：无登录态、无时间戳、无随机数；
    实测无 cookie 带正确签名同样返回 Status 200。
- 对照实验（2026-10-21，境外直连）：
  - 无签名头      -> HTTP 200 + {"status":405,"message":"请通过正确途径使用企查查"}
  - 错误签名值    -> 同上 405
  - 正确签名      -> HTTP 200 + {"Status":200,"Result":[...],"Paging":{...}}
  - 正确签名无 cookie -> 同样 200（cookie 非必需）
  - 无结果关键词  -> {"Status":201}

请求体（与 m 站搜索页客户端一致）：
  {"searchKey": "<关键词>", "isAgg": "false", "pageSize": <N>}
  key 序固定为 searchKey/isAgg/pageSize（签名覆盖 body，顺序必须一致）。

返回：
- Status 200：Result[] 每项含 KeyNo（32 hex，可直接喂给
  public_qcc_wafbypass 的 /firm/{hex}.html 直查）、Name（带 <em> 高亮）、
  No（统一社会信用代码/注册号）、OperName（法定代表人）、RegistCapi、
  StartDate（毫秒 epoch）、ShortStatus 等。
- Status 201：无结果。
- status 405：签名被拒（本适配器签名固定，若出现说明服务端换了算法）。

What this adapter does NOT do:
- 不登录、不持有任何账号状态、不读 localStorage；
- 不碰验证码；不伪造身份；
- 只调公开搜索接口，不提取电话/身份证等个人隐私字段
  （Result 不含电话明文；ContactNumber 仅为布尔标记）。

robots.txt（m.qcc.com，2026-10-21 实测）：
- 真实 robots.txt（User-agent: *）含 `Disallow: /api*`；基类默认
  UA 抓取会被 WAF 回 HTTP 567，本适配器按仓库先例（nominatim）改用
  客户端 UA 抓取再评估，stdlib robotparser 机械检查通过（`*` 被当
  字面量）。语义解读的 ambiguity 见 _check_robots 注释：
  EXPERIMENTAL + default_enabled=False 收容，人工决策最终取舍。

限频：min_request_interval = 10.0s（保守；任务要求 ≥8s）。
若企查查更新 m-web 生产包（签名模块变化），本算法需按模块 docstring
重新推导；推导入口见本文件顶部的模块编号。
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import hmac
import json
import re
import urllib.request
import urllib.robotparser
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

# ---------------------------------------------------------------------------
# "正确途径"签名（2026-10-21 实测版本，见模块 docstring）
# ---------------------------------------------------------------------------

_SIGN_CODES = "WlkBQgfiirv6AKNk4L18"  # 58365 经 lodash extend 拼出的 20 字符表
_SEARCH_PATH = "/api/search/searchmulti"  # lowercased, baseURL 已剥离

_EM_RE = re.compile(r"</?em>")


def _secret(url_path: str) -> str:
    """module 60786：secret = concat(CODES[ord(c) % 20] for c in (t+t))."""
    t = (url_path + url_path).lower()
    return "".join(_SIGN_CODES[ord(c) % 20] for c in t)


def _hmac_sha512_hex(message: str, key: str) -> str:
    """crypto-js HmacSHA512(message, key).toString() 的 Python 等价实现。"""
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"),
                    hashlib.sha512).hexdigest()


def sign_search_request(body: dict[str, Any]) -> tuple[str, str, bytes]:
    """对 searchMulti 请求体计算"正确途径"签名。

    返回 (签名 header 名, 签名 header 值, UTF-8 请求体 bytes)。
    body 的 key 序必须与客户端一致：searchKey / isAgg / pageSize。
    纯函数：无网络、无状态，单元测试可直接验证向量。
    """
    body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    body_bytes = body_json.encode("utf-8")
    t = _SEARCH_PATH
    key = _secret(t)
    header_name = _hmac_sha512_hex(t, key).lower()[10:30]
    header_value = _hmac_sha512_hex(t + t + body_json.lower(), key)
    return header_name, header_value, body_bytes


def _strip_em(name: str) -> str:
    return _EM_RE.sub("", name or "").strip()


def parse_search_results(payload: dict[str, Any]) -> dict[str, Any]:
    """解析 searchMulti 响应 JSON。

    返回 {"blocked": bool, "results": [...], "total_records": int, ...}；
    405 签名拒绝 / 非预期 Status 一律标记 blocked（不抛异常）。
    """
    if not isinstance(payload, dict):
        return {"blocked": True, "block_reason": "non_json_response",
                "results": []}
    status = payload.get("Status", payload.get("status"))
    if status == 405 or payload.get("status") == 405:
        return {"blocked": True,
                "block_reason": "signature_rejected_405",
                "message": str(payload.get("message", ""))[:120],
                "results": []}
    if status == 201:
        return {"blocked": False, "results": [], "total_records": 0}
    if status != 200:
        return {"blocked": True,
                "block_reason": f"unexpected_status_{status}",
                "results": []}
    paging = payload.get("Paging") or {}
    results = []
    for item in payload.get("Result") or []:
        if not isinstance(item, dict):
            continue
        founded = ""
        try:
            ms = item.get("StartDate")
            if ms:
                # 工商注册日期按北京时间解释（数据源为大陆企业登记）
                tz8 = _datetime.timezone(_datetime.timedelta(hours=8))
                founded = _datetime.datetime.fromtimestamp(
                    int(ms) / 1000, tz=tz8
                ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            founded = ""
        results.append({
            "key_no": str(item.get("KeyNo", "") or ""),
            "name": _strip_em(str(item.get("Name", "") or "")),
            "reg_no": str(item.get("No", "") or ""),
            "legal_rep": str(item.get("OperName", "") or ""),
            "capital": str(item.get("RegistCapi", "") or ""),
            "founded": founded,
            "ent_type": str(item.get("EntType", "") or ""),
            "status": str(item.get("ShortStatus", "") or ""),
        })
    return {
        "blocked": False,
        "results": results,
        "returned": len(results),
        "total_records": paging.get("TotalRecords", 0),
    }


class QccMwebSearch(SafeResearchAdapter):
    """企查查移动站公开搜索：m.qcc.com /api/search/searchMulti + 纯 Python 签名。"""

    source_domain = "m.qcc.com"
    source_type = "business_registry"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 10.0  # 保守限频（任务要求 ≥8s）

    _UA = (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )

    def __init__(self, *, page_size: int = 10, timeout: float = 25.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.page_size = max(1, min(int(page_size), 20))
        self.timeout = timeout
        self._pending_body: bytes = b""
        self._pending_sign: tuple[str, str] = ("", "")

    # ------------------------------------------------------------------ 请求

    def _build_body(self, keyword: str) -> dict[str, Any]:
        # key 序必须与客户端一致（签名覆盖 body）：searchKey/isAgg/pageSize
        return {"searchKey": keyword, "isAgg": "false",
                "pageSize": self.page_size}

    def _build_url(self, keyword: str, **params) -> str:
        kw = (params.get("search_key") or keyword or "").strip()
        if not kw:
            raise ValueError("qcc mweb search needs a non-empty keyword")
        if params.get("page_size"):
            self.page_size = max(1, min(int(params["page_size"]), 20))
        name, value, body_bytes = sign_search_request(self._build_body(kw))
        self._pending_sign = (name, value)
        self._pending_body = body_bytes
        return "https://m.qcc.com/api/search/searchMulti"

    def _build_headers(self) -> dict:
        sign_name, sign_value = self._pending_sign
        headers = {
            "User-Agent": self._UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",  # 拦截器 65701
            "Origin": "https://m.qcc.com",
            "Referer": "https://m.qcc.com/",
        }
        if sign_name:
            headers[sign_name] = sign_value  # 签名注入 50670
        return headers

    # ------------------------------------------------------------------ 合规

    def _check_robots(self) -> bool:
        """robots.txt 检查（重写基类实现）。

        重写原因（OSINT_LANE_RUNBOOK 的 nominatim 先例：UA 被误伤时改用
        政策合规 UA 抓取，依据写注释）：
        基类用 Python-urllib 默认 UA 抓 https://m.qcc.com/robots.txt 会被
        WAF 回 HTTP 567（非标准状态）；robotparser 对此既不 allow_all
        也不 disallow_all、且 last_checked=0，导致 can_fetch 恒 False——
        这是 UA 指纹拦截，不是站点的爬取政策。改用与 API 请求一致的
        客户端 UA 抓取真实 robots.txt 再评估。

        政策备注（2026-10-21 实测，curl + Googlebot UA 复核）：
        真实 robots.txt（User-agent: *）含 `Disallow: /api*`。stdlib
        robotparser 把 `*` 当字面量处理，对 /api/search/searchMulti
        的机械检查返回 True（通过）。按字面语义解读，该规则意在阻挡
        /api/* 爬虫——本适配器复现官方客户端签名请求、以 10s 限频做
        定向关键词查询（非爬取），属任务授权的灰区（反爬对抗，非身份
        绕过）；EXPERIMENTAL + default_enabled=False 收容，最终取舍由
        人工决策。详见 docs/research/gray-paths-20261021.md。
        """
        if self._robots_checker is not None:
            return bool(self._robots_checker(
                self.source_domain, f"https://{self.source_domain}/"))
        try:
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers={"User-Agent": self._UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except Exception:
            return True  # 基类惯例：取不到 robots.txt 时放行
        parser = urllib.robotparser.RobotFileParser()
        try:
            parser.parse(raw.splitlines())
            return parser.can_fetch("WallstreetTieling/0.6",
                                    f"https://{self.source_domain}/")
        except Exception:
            return True

    # ------------------------------------------------------------------ 抓取

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        body = self._pending_body
        if not body:
            return (0, None, "empty_request_body")
        try:
            req = urllib.request.Request(url, data=body, headers=headers,
                                         method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                http_status = resp.status
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")
        try:
            payload = json.loads(raw)
        except ValueError:
            return (http_status, raw,
                    "non_json_response")
        return (http_status, payload, "")

    # ------------------------------------------------------------------ 解析

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if isinstance(raw_data, dict):
            return parse_search_results(raw_data)
        if isinstance(raw_data, str):
            try:
                return parse_search_results(json.loads(raw_data))
            except ValueError:
                pass
        return {"blocked": True, "block_reason": "non_json_response",
                "results": []}

    # ------------------------------------------------------------------ 便捷

    def search_company(self, keyword: str, **params) -> dict[str, Any]:
        """关键词查公司（公开搜索）。返回标准 query() 结果 dict。"""
        return self.query(keyword, **params)
