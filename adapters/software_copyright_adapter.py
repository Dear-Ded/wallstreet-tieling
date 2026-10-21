"""软件著作权检索适配器 — 关联深挖用知识产权源。

数据边界: fully_public（软著登记信息是法定公开信息）

包含两个查询器：

1. ZhifufuSoftLookup (BROWSER-ASSISTED)
   知服服 zhifufu.com /cha/api/soft/search（Solr 后端）。
   纯服务端 curl 会被腾讯验证码拦（code 106/107 ticket is null）；
   真实浏览器过一次验证码后 API 正常返回。
   query() 返回 interaction_required + 操作指引；
   parse_browser_result() 解析从浏览器 devtools 复制的响应 JSON
   （Solr 格式：success/response.docs/response.numFound）。

2. JuheCopyrightLookup (KEY-READY)
   聚合数据 juhe.cn 企业著作权查询 API。
   key 只走构造参数（premium_keyed 模式）；无 key 返回 credentials_required。

关联价值：
  - 同一著作权人在多家公司登记软著 → 关联信号
  - 软著数量 → 科技公司技术实力信号
  - 登记日期 → 时间线关联

Philosophy: 软著登记是法定公开信息。公开的就是公开的。
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


# ---------------------------------------------------------------------------
# 知服服：接口常量（从前端 JS 逆向，2026-10-21）
# ---------------------------------------------------------------------------
_ZFF_SEARCH_URL = "https://www.zhifufu.com/cha/api/soft/search"
_ZFF_TOKEN = "svelgt5x0cpixpgayvmiwa"
_ZFF_KEY = "yyCAbxUlotrUuKpl57pNe+c"


def _zff_sign(q: str, page: int, owner: str = "") -> str:
    """ts = MD5(token_key_soft.search_<q>_<page>)；owner 查询时用 owner 参与签名。"""
    seed = owner if owner else q
    raw = f"{_ZFF_TOKEN}_{_ZFF_KEY}_soft.search_{seed}_{page}"
    return hashlib.md5(raw.encode()).hexdigest()


# Solr doc 字段名 → 统一字段的候选映射（防御式，兼容字段名漂移）
_DOC_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "soft_name": ("soft_name", "name", "title", "rjmc", "software_name"),
    "reg_no": ("reg_no", "regno", "reg_num", "djh", "cert_no", "register_no"),
    "owner": ("owner", "owner_s", "zqr", "copyright_holder", "holder"),
    "reg_date": ("reg_date", "rd", "register_date", "djrq", "approval_date"),
    "version": ("version", "ver", "bbh", "soft_version"),
    "complete_date": ("complete_date", "wcrq", "finish_date", "dev_complete_date"),
    "doc_id": ("id", "doc_id"),
}


def _pick(doc: dict[str, Any], key: str) -> str:
    for cand in _DOC_FIELD_CANDIDATES[key]:
        v = doc.get(cand)
        if v:
            if isinstance(v, list):
                v = v[0] if v else ""
            return str(v).strip()
    return ""


class ZhifufuSoftLookup(SafeResearchAdapter):
    """知服服软件著作权查询（browser-assisted）。

    用法：
        adapter = ZhifufuSoftLookup()
        result = adapter.query("小米科技", search_by="owner")  # interaction_required
        # 操作员在浏览器完成查询后，把 /cha/api/soft/search 响应 JSON 贴回来：
        parsed = adapter.parse_browser_result(copied_json)
    """

    source_domain = "www.zhifufu.com"
    source_type = "ip_copyright"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True
    min_request_interval = 3.0

    # ------------------------------------------------------------------
    def query(
        self,
        keyword: str,
        search_by: str = "keyword",
        page: int = 1,
        **params: Any,
    ) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        if not keyword:
            return self._interaction_required("", search_by, "empty keyword")
        self._record_audit(keyword)
        return self._interaction_required(keyword, search_by, "")

    def _interaction_required(
        self, keyword: str, search_by: str, reason: str
    ) -> dict[str, Any]:
        search_by = search_by if search_by in ("keyword", "owner") else "keyword"
        if search_by == "owner":
            desc = f"按著作权人“{keyword}”查询"
            url_hint = "https://www.zhifufu.com/soft/search （选择“著作权人”搜索类型）"
        else:
            desc = f"按软件名称关键词“{keyword}”查询"
            url_hint = "https://www.zhifufu.com/soft/search"
        return {
            "status": "interaction_required",
            "reason": reason or "zhifufu_soft_search_needs_captcha",
            "keyword": keyword,
            "search_by": search_by,
            "source": "www.zhifufu.com",
            "data_boundary": self.data_boundary,
            "instructions": [
                f"1. 在桌面浏览器打开 {url_hint}",
                f"2. {desc}，如遇验证码请手动完成一次验证",
                "3. 打开浏览器开发者工具 → Network 面板 → 找到",
                "   POST https://www.zhifufu.com/cha/api/soft/search 的请求",
                "4. 复制该请求的 Response（完整 JSON）",
                "5. 调用 parse_browser_result(copied_json) 解析",
            ],
            "api_url_hint": _ZFF_SEARCH_URL,
            "note": "签名算法 ts=MD5(token_key_soft.search_<q>_<page>) 已内置；"
            "浏览器过验证码后接口直接可用，无需登录。",
        }

    # ------------------------------------------------------------------
    # 解析：Solr 格式响应 → 结构化软著列表
    # ------------------------------------------------------------------
    def parse_browser_result(self, raw: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return self._empty_result("invalid_json")
        elif isinstance(raw, dict):
            data = raw
        else:
            return self._empty_result("invalid_input")
        if not isinstance(data, dict):
            return self._empty_result("unexpected_shape")

        # 验证码未过
        if data.get("code") in (106, 107):
            return self._empty_result("captcha_required")

        response = data.get("response") or {}
        docs = response.get("docs") or []
        total = response.get("numFound", 0)

        records: list[dict[str, Any]] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            rec = {
                "soft_name": _pick(doc, "soft_name"),
                "reg_no": _pick(doc, "reg_no"),
                "owner": _pick(doc, "owner"),
                "reg_date": _pick(doc, "reg_date"),
                "version": _pick(doc, "version"),
                "complete_date": _pick(doc, "complete_date"),
                "doc_id": _pick(doc, "doc_id"),
            }
            # 至少有一个关键字段才收录
            if rec["soft_name"] or rec["reg_no"] or rec["owner"]:
                records.append(rec)

        qtime = (data.get("responseHeader") or {}).get("QTime")

        return {
            "status": "ok",
            "source": "www.zhifufu.com",
            "data_boundary": self.data_boundary,
            "total": total,
            "record_count": len(records),
            "qtime_ms": qtime,
            "records": records,
        }

    # ------------------------------------------------------------------
    # 抽象方法实现（browser-assisted 模式下不实际调用）
    # ------------------------------------------------------------------
    def _build_url(self, keyword: str, **params: Any) -> str:
        return _ZFF_SEARCH_URL

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # browser-assisted：解析走 parse_browser_result，这里返回空
        return {}

    def _record_audit(self, keyword: str) -> None:
        # 基类审计：只存 keyword 的 sha256 前 12 位
        try:
            super()._record_audit(keyword=keyword, url="", status=0, fields=[])
        except Exception:
            pass

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "status": "empty",
            "reason": reason,
            "source": "www.zhifufu.com",
            "data_boundary": self.data_boundary,
            "total": 0,
            "record_count": 0,
            "records": [],
        }


# ---------------------------------------------------------------------------
# 聚合数据：企业著作权查询（key-ready）
# ---------------------------------------------------------------------------
_JUHE_URL = "http://v.juhe.cn/enterprise/App/CopyrightByName/query.php"


class JuheCopyrightLookup(SafeResearchAdapter):
    """聚合数据企业著作权查询（key-ready，premium_keyed 模式）。

    key 只走构造参数，不读磁盘/env/config，不进日志。
    无 key 时 query() 返回 credentials_required。

    用法：
        adapter = JuheCopyrightLookup(api_key="...")  # key 来自 juhe.cn 注册
        result = adapter.query("小米科技有限责任公司")
    """

    source_domain = "v.juhe.cn"
    source_type = "ip_copyright"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 2.0

    def __init__(self, api_key: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self._api_key = (api_key or "").strip()

    def _has_required_credentials(self) -> bool:
        return bool(self._api_key)

    def query(self, company: str, **params: Any) -> dict[str, Any]:
        company = (company or "").strip()
        if not company:
            return self._empty_result("empty company")
        if not self._has_required_credentials():
            self._record_audit(company)
            return {
                "status": "credentials_required",
                "reason": "juhe_copyright_needs_api_key",
                "source": "v.juhe.cn",
                "data_boundary": self.data_boundary,
                "hint": "在 juhe.cn 注册获取 key 后 JuheCopyrightLookup(api_key=...) 传入",
            }
        self._record_audit(company)
        url = (
            f"{_JUHE_URL}?key={urllib.parse.quote(self._api_key)}"
            f"&name={urllib.parse.quote(company)}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return self._empty_result(f"request_failed: {type(e).__name__}")
        return self._parse_response(body)

    def _parse_response(self, body: str) -> dict[str, Any]:
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return self._empty_result("invalid_json")
        if not isinstance(data, dict):
            return self._empty_result("unexpected_shape")
        if str(data.get("error_code")) != "0":
            return self._empty_result(
                f"api_error: {data.get('reason', '')} (code={data.get('error_code')})"
            )
        result = data.get("result") or {}
        items = result.get("items") or []
        records: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            records.append({
                "soft_name": str(it.get("name", "")).strip(),
                "reg_no": str(it.get("number", "")).strip(),
                "owner": str(it.get("company", "")).strip(),
                "reg_date": str(it.get("approval_date", "") or it.get("first_date", "")).strip(),
                "version": str(it.get("version", "")).strip(),
                "complete_date": str(it.get("success_date", "")).strip(),
                "type_name": str(it.get("type_name", "")).strip(),
                "doc_id": str(it.get("id", "")).strip(),
            })
        return {
            "status": "ok",
            "source": "v.juhe.cn",
            "data_boundary": self.data_boundary,
            "total": result.get("total", len(records)),
            "record_count": len(records),
            "records": records,
        }

    # ------------------------------------------------------------------
    # 抽象方法实现
    # ------------------------------------------------------------------
    def _build_url(self, keyword: str, **params: Any) -> str:
        return (
            f"{_JUHE_URL}?key={urllib.parse.quote(self._api_key or '')}"
            f"&name={urllib.parse.quote(keyword or '')}"
        )

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if isinstance(raw_data, str):
            return self._parse_response(raw_data)
        return self._empty_result("unexpected_input")

    def _record_audit(self, keyword: str) -> None:
        # 基类审计：只存 keyword 的 sha256 前 12 位；key 永不进日志
        try:
            super()._record_audit(keyword=keyword, url="", status=0, fields=[])
        except Exception:
            pass

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "status": "empty",
            "reason": reason,
            "source": "v.juhe.cn",
            "data_boundary": self.data_boundary,
            "total": 0,
            "record_count": 0,
            "records": [],
        }
