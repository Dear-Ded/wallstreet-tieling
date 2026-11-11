#!/usr/bin/env python3
"""东方财富 F10 上市公司档案 — 上市公司基本信息 / 法人 / 十大股东（免登录匿名）.

覆盖场景: 企查查/天眼查/启信宝免登录面已死之后, 对**上市公司**主体的
基本信息 + 法定代表人 + 十大股东仍可经公开渠道匿名获取, 无需注册/实名/绑卡。

Survey（2026-10-21 实测, plain curl, 桌面 UA, 无登录无 key）:
- `GET https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code=SH600519`
  → 200, JSON `jbzl`（公司名称/证券类别/所属行业/交易所/法人代表/董事长/
  总经理/董秘/联系方式/注册地址/注册资本/统一社会信用代码/经营范围/公司简介）
  + `fxxg`（发行上市信息）。SZ000001 同样 200。
- `GET https://datacenter-web.eastmoney.com/api/data/v1/get`
  `?reportName=RPT_F10_EH_HOLDERS&filter=(SECUCODE="600519.SH")&...`
  → 200, JSON `result.data[]`（HOLDER_NAME/HOLD_NUM_RATIO/HOLDER_RANK 等十大股东）。
- robots.txt: `emweb.securities.eastmoney.com/robots.txt` 返回 IIS 404
  （无规则=允许, 基类 robotparser 同样处理）;
  `datacenter-web.eastmoney.com/robots.txt` 返回 200 + JSON 错误体
  `{"code":"200","message":"全局错误:请求url格式异常:/robots.txt"}`（非 robots
  文件, 无 Disallow 声明）。两处均如实记录。
- 限速: 5 秒间隔（datacenter-web 对频率敏感, 保守）。

工作流: query(股票代码) -> 公司概况 + 十大股东 -> 合并抽取公开字段。
股票代码归一化: 接受 "600519"/"SH600519"/"sh600519"/"600519.SH" 等写法;
前缀按 A 股编码规则推断（60/68/90/58→SH, 00/30/20→SZ, 43/83/87/88→BJ）,
无法推断时返回空结果并明示原因。

公司名→代码需调用方先行解析（深交所 A股列表 API CATALOGID=1110 可匿名
按简称检索, 见 docs/research/gray-paths-20261021.md）; 本 adapter 只收代码。

诚实边界:
- 仅覆盖**上市公司**（沪深北交易所）; 非上市企业无解, 不伪装成企查查替代。
- 十大股东为定期报告披露口径（END_DATE 取最新一期）, 非实时工商股东。
- 法人代表/董监高为 F10 公开档案口径, 交叉验证线索用, 不做身份断言。

data_boundary="fully_public"; EXPERIMENTAL, 默认关闭。
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_SURVEY_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
_HOLDERS_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HOLDERS_REPORT = "RPT_F10_EH_HOLDERS"

# 接受: 600519 / SH600519 / sh600519 / 600519.SH / 600519.sh
_CODE_RE = re.compile(r"^(?:(SH|SZ|BJ))?(\d{6})(?:\.(SH|SZ|BJ))?$", re.IGNORECASE)


def normalize_stock_code(keyword: str) -> str | None:
    """归一化为 SH600519 / SZ000001 / BJ430000 形式；无法推断返回 None。"""
    m = _CODE_RE.match(keyword.strip())
    if not m:
        return None
    prefix = (m.group(1) or m.group(3) or "").upper()
    digits = m.group(2)
    if not prefix:
        if digits[:2] in ("60", "68", "90", "58"):
            prefix = "SH"
        elif digits[:2] in ("00", "30", "20"):
            prefix = "SZ"
        elif digits[:2] in ("43", "83", "87", "88"):
            prefix = "BJ"
        else:
            return None
    return f"{prefix}{digits}"


def _datacenter_secucode(code: str) -> str:
    """SH600519 -> 600519.SH（datacenter-web filter 口径）。"""
    return f"{code[2:]}.{code[:2]}"


class EastmoneyF10Lookup(SafeResearchAdapter):
    """东方财富 F10 上市公司档案查询（匿名、无 key）。"""

    source_domain = "emweb.securities.eastmoney.com"
    source_type = "exchange_public_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def _build_url(self, keyword: str, **params) -> str:
        code = normalize_stock_code(keyword) or ""
        return f"{_SURVEY_URL}?code={code}"

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            survey = self._http_get_json(url, headers)
            if not isinstance(survey, dict) or not survey.get("jbzl"):
                return (200, {"survey": survey, "holders": []}, "")
            # 实测 SecuCode 为 "600519.SH" 口径（datacenter 格式），经归一化再使用
            code = normalize_stock_code(survey.get("SecuCode") or "") or self._code_from_url(url)
            holders = []
            if code:
                holders = self._fetch_holders(code, headers)
            return (200, {"survey": survey, "holders": holders}, "")
        except Exception as e:  # noqa: BLE001 - 统一降级为可审计的空结果
            return (0, None, f"{type(e).__name__}: {e}")

    @staticmethod
    def _code_from_url(url: str) -> str:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        raw = (qs.get("code") or [""])[0]
        return normalize_stock_code(raw) or ""

    def _fetch_holders(self, code: str, headers: dict) -> list[dict]:
        params = {
            "sortColumns": "END_DATE,HOLDER_RANK",
            "sortTypes": "-1,1",
            "pageSize": "50",
            "pageNumber": "1",
            "reportName": _HOLDERS_REPORT,
            "columns": "ALL",
            "filter": f'(SECUCODE="{_datacenter_secucode(code)}")',
        }
        body = self._http_get_json(f"{_HOLDERS_URL}?{urllib.parse.urlencode(params)}", headers)
        rows = ((body or {}).get("result") or {}).get("data") or []
        if not rows:
            return []
        latest = max((r.get("END_DATE") or "" for r in rows))
        return [r for r in rows if r.get("END_DATE") == latest][:10]

    @staticmethod
    def _http_get_json(url: str, headers: dict) -> Any:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    # -- 字段抽取 ---------------------------------------------------------
    _JBZL_MAP = {
        "gsmc": "company_name",
        "ywmc": "english_name",
        "agdm": "a_share_code",
        "agjc": "a_share_name",
        "zqlb": "security_type",
        "sshy": "industry",
        "ssjys": "exchange",
        "sszjhhy": "csic_industry",
        "frdb": "legal_rep",
        "dsz": "chairman",
        "zjl": "ceo",
        "dm": "board_secretary",
        "zqswdb": "securities_affairs_rep",
        "dlds": "independent_directors",
        "lxdh": "phone",
        "dzxx": "email",
        "cz": "fax",
        "gswz": "website",
        "bgdz": "office_addr",
        "zcdz": "reg_addr",
        "qy": "province",
        "yzbm": "zip_code",
        "zczb": "reg_capital",
        "gsdj": "credit_code",
        "gyrs": "employees",
        "lssws": "law_firm",
        "kjssws": "auditor",
    }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not isinstance(raw_data, dict):
            return {}
        survey = raw_data.get("survey") or {}
        jbzl = survey.get("jbzl") or {}
        if not jbzl:
            return {}
        fields: dict[str, Any] = {}
        for src, dst in self._JBZL_MAP.items():
            val = jbzl.get(src)
            if val not in (None, "", "--"):
                fields[dst] = val
        for src, dst in (("gsjj", "intro"), ("jyfw", "business_scope")):
            val = (jbzl.get(src) or "").strip()
            if val:
                fields[dst] = val[:600]
        fxxg = survey.get("fxxg") or {}
        for src, dst in (("ssrq", "ipo_date"), ("mgfxj", "ipo_price"),
                         ("fxl", "ipo_volume"), ("clrq", "founded_date")):
            if fxxg.get(src) not in (None, "", "--"):
                fields[dst] = fxxg[src]
        holders = []
        for r in raw_data.get("holders") or []:
            holders.append({
                "rank": r.get("HOLDER_RANK"),
                "name": r.get("HOLDER_NAME"),
                "ratio": r.get("HOLD_NUM_RATIO"),
                "shares": r.get("HOLD_NUM"),
                "change": r.get("HOLD_NUM_CHANGE"),
                "report_date": (r.get("END_DATE") or "")[:10],
            })
        if holders:
            fields["top_holders"] = holders
            fields["holder_count"] = len(holders)
        fields["source"] = "eastmoney_f10"
        return fields
