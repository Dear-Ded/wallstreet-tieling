#!/usr/bin/env python3
"""中国政府采购网 (ccgp.gov.cn) 招投标/成交公告适配器。

回答："这家企业中过政府采购的标吗？中了多少金额？联系人是谁？"

## 数据价值

政府采购成交公告是法定公开信息，包含：
- 中标/成交供应商名称、社会信用代码
- 中标金额、项目名称
- 采购人联系人/电话、代理机构联系人/电话

关联价值：
- 同一联系人/电话出现在多个中标公告 → 关联企业线索
- 中标金额 → 企业经营实力的硬证据
- 社会信用代码 → 精确的企业身份标识

## 访问模式

**搜索** (`query`)：`search.ccgp.gov.cn/bxsearch` GET 搜索
- 按关键词（企业名/项目名）搜索采购公告
- 结果以内嵌 JSON 形式存在于 HTML 中
- 注意：该端点有严格的限频（实测 2026-10-21 触发"访问过于频繁"）
- 10 秒请求间隔；被限时返回 rate_limited

**详情页** (`query_detail`)：`www.ccgp.gov.cn/.../*.htm`
- 公告详情页无限制，可直接解析
- 提取：供应商名称、信用代码、地址、中标金额、联系人/电话

**单一来源公示** (`query_eanotice`)：`search.ccgp.gov.cn/eanotice`
- 限频较宽松，可作为补充

## 合规

- 只读公开数据，不登录、不绕验证码
- 桌面端 UA；搜索 10 秒间隔，详情页 3 秒间隔
- data_boundary="fully_public"；EXPERIMENTAL，默认关闭
- 政府采购公告是法定公开信息，字段不打码
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class CcgpBidLookup(SafeResearchAdapter):
    """中国政府采购网招投标/成交公告检索。"""

    source_domain = "www.ccgp.gov.cn"
    data_boundary = "fully_public"
    requires_interaction = False

    # 端点
    SEARCH_URL = "http://search.ccgp.gov.cn/bxsearch"
    EANOTICE_URL = "http://search.ccgp.gov.cn/eanotice"

    # 限频：搜索 10 秒，详情 3 秒
    SEARCH_INTERVAL = 10.0
    DETAIL_INTERVAL = 3.0

    _last_search_ts: float = 0.0
    _last_detail_ts: float = 0.0

    def __init__(self, timeout: float = 30.0):
        super().__init__()
        self._timeout = timeout
        self._ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def _build_url(self, keyword: str, **params: Any) -> str:
        """构建搜索 URL（基类抽象方法实现）。"""
        page = params.get("page", 1)
        query_params = {
            "searchtype": "1",
            "page_index": str(page),
            "bidSort": "0",
            "pinMu": "0",
            "bidType": "0",
            "kw": keyword,
            "start_time": "2020:01:01",
            "end_time": time.strftime("%Y:%m:%d"),
            "timeType": "2",
            "dbselect": "bidx",
        }
        return self.SEARCH_URL + "?" + urllib.parse.urlencode(query_params)

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """提取公开字段（基类抽象方法实现）。"""
        if isinstance(raw_data, dict):
            return raw_data
        return {}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _fetch(self, url: str, referer: str = "http://www.ccgp.gov.cn/") -> str | None:
        """抓取页面，返回 HTML 文本。None 表示失败。"""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._ua,
                "Referer": referer,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                # 尝试解码
                for enc in ("utf-8", "gbk", "gb2312"):
                    try:
                        return raw.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return None

    def _throttle_search(self):
        elapsed = time.time() - self._last_search_ts
        if elapsed < self.SEARCH_INTERVAL:
            time.sleep(self.SEARCH_INTERVAL - elapsed)
        self._last_search_ts = time.time()

    def _throttle_detail(self):
        elapsed = time.time() - self._last_detail_ts
        if elapsed < self.DETAIL_INTERVAL:
            time.sleep(self.DETAIL_INTERVAL - elapsed)
        self._last_detail_ts = time.time()

    def _audit(self, action: str, query: str):
        """审计日志：只存 query 的 sha256，不存原文。"""
        qhash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        self.log_audit(action, {"query_sha256": qhash})

    # ------------------------------------------------------------------
    # 搜索解析
    # ------------------------------------------------------------------

    @staticmethod
    def parse_search_results(html: str) -> dict[str, Any]:
        """解析 bxsearch 结果页的内嵌 JSON。

        返回 {"total": int, "results": [...], "rate_limited": bool}
        每条 result: {number, title, dep, proj_nm, date, lnk}
        """
        if "访问过于频繁" in html or "频繁访问" in html:
            return {"total": 0, "results": [], "rate_limited": True}

        # 结果以内嵌 JSON 形式存在：var a='[{...}]'
        # 注意：JSON 可能很长，用括号匹配而非正则
        results = []
        var_idx = html.find("var a='")
        if var_idx >= 0:
            start = html.find("[", var_idx)
            if start >= 0:
                # 括号匹配找结束位置
                depth = 0
                in_str = False
                esc = False
                end = -1
                for i in range(start, min(start + 500000, len(html))):
                    c = html[i]
                    if esc:
                        esc = False
                        continue
                    if c == "\\":
                        esc = True
                        continue
                    if c == '"' and not esc:
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    json_str = html[start:end]
                    try:
                        results = json.loads(json_str)
                    except json.JSONDecodeError:
                        # JSON 可能被截断，用正则提取完整的对象
                        import re as _re
                        obj_pattern = _re.compile(
                            r'\{"number":"[^"]*","title":"[^"]*","dep":"[^"]*",'
                            r'"proj_nm":"[^"]*","date":"[^"]*","lnk":"[^"]*"\}'
                        )
                        for m in obj_pattern.finditer(json_str):
                            try:
                                results.append(json.loads(m.group(0)))
                            except json.JSONDecodeError:
                                continue

        # 总数
        total = len(results)
        m_total = re.search(r"共\s*(\d+)\s*条", html)
        if m_total:
            total = int(m_total.group(1))

        return {"total": total, "results": results, "rate_limited": False}

    @staticmethod
    def parse_detail_page(html: str) -> dict[str, Any]:
        """解析成交公告详情页。

        提取：供应商名称、信用代码、地址、中标金额、联系人/电话。
        """
        # 转纯文本
        text = re.sub(r"<[^>]+>", "\n", html)
        text = re.sub(r"\n\s*\n+", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        result: dict[str, Any] = {
            "suppliers": [],
            "buyer": {},
            "agent": {},
            "experts": [],
        }

        # 标题
        m = re.search(r"<title>([^<]+)</title>", html)
        if m:
            result["title"] = m.group(1).strip()

        # --- 中标供应商表格 ---
        # 格式：序号 / 供应商名称 / 社会信用代码 / 供应商地址 / 评审报价 / 中标金额
        # 只取"中标（成交）信息"到"主要标的信息"之间的区域，避免抓到后面的代理服务费
        bid_section = ""
        idx = text.find("中标")
        if idx >= 0:
            end_markers = ["主要标的信息", "四、", "评审专家"]
            end_idx = len(text)
            for marker in end_markers:
                m_idx = text.find(marker, idx + 10)
                if m_idx > idx and m_idx < end_idx:
                    end_idx = m_idx
            bid_section = text[idx:end_idx]

        # 提取供应商：名称 + 信用代码 + 金额
        # 信用代码格式：18 位统一社会信用代码
        credit_codes = re.findall(r"\b[0-9A-Z]{18}\b", bid_section)
        for cc in credit_codes:
            # 找信用代码前面的企业名（通常在同一行或前一行）
            cc_idx = bid_section.find(cc)
            context = bid_section[max(0, cc_idx - 100) : cc_idx]
            # 企业名通常以"公司"/"厂"/"所"/"中心"等结尾
            name_m = re.search(
                r"([\u4e00-\u9fa5a-zA-Z0-9（）()·\-—]{4,60}(?:公司|厂|所|中心|院|社|部|局|集团|企业|工作室|店|行|场))",
                context,
            )
            supplier: dict[str, Any] = {"credit_code": cc}
            if name_m:
                supplier["name"] = name_m.group(1).strip()

            # 找金额：中标金额通常是该行最后一个"X元"（评审报价在前，中标金额在后）
            after = bid_section[cc_idx : cc_idx + 300]
            amt_matches = re.findall(r"([\d,]+\.?\d*)\s*元", after)
            if amt_matches:
                # 取最后一个作为中标金额
                supplier["amount"] = amt_matches[-1]
                supplier["amount_raw"] = amt_matches[-1] + "元"

            result["suppliers"].append(supplier)

        # --- 联系人/电话 ---
        # 格式：联系人：XXX / 联系电话：XXX（可能在下一行）
        contacts = re.findall(r"联系人[：:]\s*([^\n\s]{2,10})", text)
        # 电话：只匹配数字和横杠，不跨行贪婪
        phones = []
        for m in re.finditer(r"联系电话[：:]?\s*\n*\s*([\d][\d\-–— ]{6,18}[\d])", text):
            phones.append(m.group(1))
        # 也匹配"电话："（非"联系电话"）
        for m in re.finditer(r"(?<!联系)电话[：:]?\s*\n*\s*([\d][\d\-–— ]{6,18}[\d])", text):
            phones.append(m.group(1))

        result["contacts"] = [
            {"name": c.strip(), "phone": phones[i].strip() if i < len(phones) else ""}
            for i, c in enumerate(contacts)
        ]
        # 去重电话（清理换行/序号残留）
        seen_phones = set()
        unique_phones = []
        for p in phones:
            # 去掉末尾的换行+数字（如 "\n2" 是列表序号残留）
            p_clean = re.sub(r"[\s\-–—]", "", p)
            p_clean = re.sub(r"\n\d+$", "", p_clean)
            # 只保留纯数字+区号横杠
            p_clean = re.sub(r"[^\d]", "", p_clean)
            if p_clean and p_clean not in seen_phones and len(p_clean) >= 7:
                seen_phones.add(p_clean)
                # 格式化：手机号 11 位直接返回，座机保留原始
                unique_phones.append(p_clean)
        result["phones"] = unique_phones

        # --- 采购人 ---
        buyer_m = re.search(r"采购人信息?\s*\n?\s*单位名称[：:]\s*([^\n]+)", text)
        if buyer_m:
            result["buyer"]["name"] = buyer_m.group(1).strip()

        # --- 评审专家 ---
        expert_m = re.search(r"评审专家[^\n]*名单[：:]\s*([^\n]+)", text)
        if expert_m:
            experts = re.split(r"[、，,；;]", expert_m.group(1))
            result["experts"] = [e.strip() for e in experts if e.strip()]

        return result

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def query(self, keyword: str, page: int = 1) -> dict[str, Any]:
        """按关键词搜索采购公告。

        Args:
            keyword: 企业名或项目关键词
            page: 页码（从 1 开始）

        Returns:
            {"status": ..., "total": int, "results": [...]}
            status: ok / rate_limited / error / invalid_input
        """
        if not keyword or not keyword.strip():
            return {"status": "invalid_input", "total": 0, "results": []}

        keyword = keyword.strip()
        self._audit("query", keyword)
        self._throttle_search()

        params = {
            "searchtype": "1",
            "page_index": str(page),
            "bidSort": "0",
            "pinMu": "0",
            "bidType": "0",
            "kw": keyword,
            "start_time": "2020:01:01",
            "end_time": time.strftime("%Y:%m:%d"),
            "timeType": "2",
            "dbselect": "bidx",
        }
        url = self.SEARCH_URL + "?" + urllib.parse.urlencode(params)
        html = self._fetch(url)

        if html is None:
            return {"status": "error", "total": 0, "results": [],
                    "note": "fetch failed"}

        parsed = self.parse_search_results(html)
        if parsed["rate_limited"]:
            return {"status": "rate_limited", "total": 0, "results": [],
                    "note": "ccgp 限频，请稍后重试（建议间隔 60 秒以上）"}

        return {
            "status": "ok",
            "total": parsed["total"],
            "results": parsed["results"],
            "keyword": keyword,
            "page": page,
        }

    def query_detail(self, url: str) -> dict[str, Any]:
        """解析单个公告详情页。

        Args:
            url: 公告详情页 URL（从 query 结果的 lnk 字段获取）

        Returns:
            结构化详情：suppliers, contacts, phones, buyer, experts 等
        """
        if not url or not url.startswith("http"):
            return {"status": "invalid_input"}

        self._audit("query_detail", url)
        self._throttle_detail()

        html = self._fetch(url)
        if html is None:
            return {"status": "error", "note": "fetch failed"}

        detail = self.parse_detail_page(html)
        detail["status"] = "ok"
        detail["url"] = url
        return detail

    def investigate(self, keyword: str, max_details: int = 3) -> dict[str, Any]:
        """一站式：搜索 + 解析前 N 个详情页。

        Args:
            keyword: 企业名
            max_details: 最多解析几个详情页

        Returns:
            搜索结果 + 详情汇总
        """
        search_result = self.query(keyword)
        if search_result["status"] != "ok":
            return search_result

        details = []
        for r in search_result["results"][:max_details]:
            lnk = r.get("lnk", "")
            if lnk:
                d = self.query_detail(lnk)
                if d.get("status") == "ok":
                    d["search_title"] = r.get("title", "")
                    d["search_date"] = r.get("date", "")
                    details.append(d)

        # 汇总供应商（去重）
        all_suppliers: dict[str, dict] = {}
        for d in details:
            for s in d.get("suppliers", []):
                key = s.get("credit_code") or s.get("name", "")
                if key and key not in all_suppliers:
                    all_suppliers[key] = s

        # 汇总电话
        all_phones: list[str] = []
        for d in details:
            for p in d.get("phones", []):
                if p not in all_phones:
                    all_phones.append(p)

        return {
            "status": "ok",
            "keyword": keyword,
            "search_total": search_result["total"],
            "details_parsed": len(details),
            "suppliers": list(all_suppliers.values()),
            "phones": all_phones,
            "details": details,
        }
