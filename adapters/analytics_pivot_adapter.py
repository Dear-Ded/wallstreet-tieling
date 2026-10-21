"""网站统计代码指纹关联 — Analytics ID pivoting 适配器。数据边界: fully_public

社工学经典思路"人有习惯"：网站主经常在多个站点复用同一个统计 ID。
抓一个站的统计代码 → 搜哪些域名用了同一个 ID → 同一运营者（强关联信号）。

覆盖的统计平台（全部通过公开 HTML 正则提取，站长自己放上去的）：
- 百度统计：hm.js?<32位hex> / _hmt
- Google Analytics (UA)：UA-123456-7
- Google Analytics 4：G-XXXXXXXXXX
- CNZZ：s*.cnzz.com/z_stat.php?id=<siteid>
- 51.la：js.users.51.la/<id>.js
- 百度统计新版：hm.baidu.com/hm.js

Pivot 渠道（免费、无需 key）：
- urlscan.io 公开搜索 API：q=<analytics_id>，返回含该 ID 的扫描记录 → 提域名
  （urlscan.io 记录是提交者主动公开的扫描数据）

Philosophy: 网站 HTML 是公开的，统计代码是站长主动部署的。
提取公开代码、关联公开扫描记录，不碰任何隐私数据。
同一统计 ID → 同一运营者，这是强关联信号（exact 级别）。
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
import json
import urllib.parse
import urllib.request


class AnalyticsPivotLookup(SafeResearchAdapter):
    """网站统计 ID 提取 + 跨域名 pivot 关联。"""

    source_domain = "target-site + urlscan.io"
    source_type = "analytics_id_pivot"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # ── 正则：各平台统计 ID ──────────────────────────────────────
    _PATTERNS: dict[str, re.Pattern] = {
        # 百度统计：hm.js?后面跟 32 位 hex
        "baidu_tongji": re.compile(
            r"hm\.baidu\.com/hm\.js\?([0-9a-f]{32})", re.I
        ),
        # Google Analytics UA：UA-12345678-1
        "google_ua": re.compile(
            r"\bUA-(\d{4,10}-\d{1,3})\b"
        ),
        # Google Analytics 4：G-XXXXXXXXXX（10位字母数字）
        "google_ga4": re.compile(
            r"\bG-([A-Z0-9]{10})\b"
        ),
        # CNZZ：z_stat.php?id=12345678 或 siteid
        "cnzz": re.compile(
            r"cnzz\.com/z_stat\.php\?id=(\d+)|['\"]siteid['\"]\s*[:=]\s*['\"]?(\d+)['\"]?",
            re.I,
        ),
        # 51.la：js.users.51.la/12345678.js
        "la51": re.compile(
            r"js\.users\.51\.la/(\d+)\.js", re.I
        ),
        # 百度统计 _hmt 变量形式（兜底）
        "baidu_hmt": re.compile(
            r"_hmt\.push\(\[['_\"]_setAccount['\"],\s*['\"]([0-9a-f]{32})['\"]\]",
            re.I,
        ),
    }

    _URLSCAN_SEARCH = "https://urlscan.io/api/v1/search/"

    # ── SafeResearchAdapter 接口 ─────────────────────────────────

    def _build_url(self, keyword: str, **params) -> str:
        """keyword 可以是 URL（提取模式）或 analytics ID（pivot 模式）。"""
        mode = params.get("mode", "extract")
        if mode == "pivot":
            q = urllib.parse.quote(keyword)
            size = max(1, min(int(params.get("size", 20)), 100))
            return f"{self._URLSCAN_SEARCH}?q={q}&size={size}"
        # extract 模式：直接返回目标 URL（_execute_query 会处理）
        url = keyword.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def _build_headers(self) -> dict[str, str]:
        return {"User-Agent": self._UA, "Accept": "text/html,application/json,*/*"}

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {"ids_found": 0, "analytics_ids": {}}
        # raw_data 可能是 HTML（extract）或 JSON（pivot），由调用方分支处理
        # 默认按 HTML 提取
        if isinstance(raw_data, str) and raw_data.lstrip().startswith("{"):
            return self._parse_pivot_response(raw_data)
        return self._format_extract_result(
            self.extract_ids_from_html(raw_data)
            if isinstance(raw_data, str)
            else {}
        )

    # ── 核心能力 1：从 HTML 提取统计 ID ──────────────────────────

    @classmethod
    def extract_ids_from_html(cls, html: str) -> dict[str, list[str]]:
        """从页面 HTML 提取各平台统计 ID。返回 {平台: [id列表]}。"""
        found: dict[str, list[str]] = {}
        if not html:
            return found
        for platform, pattern in cls._PATTERNS.items():
            ids: list[str] = []
            for m in pattern.finditer(html):
                # 取第一个非空捕获组
                vid = next((g for g in m.groups() if g), "")
                if not vid:
                    continue
                # 规范化：UA/GA4 补前缀
                if platform == "google_ua" and not vid.startswith("UA-"):
                    vid = "UA-" + vid
                elif platform == "google_ga4" and not vid.startswith("G-"):
                    vid = "G-" + vid
                if vid not in ids:
                    ids.append(vid)
            if ids:
                # baidu_hmt 并入 baidu_tongji
                key = "baidu_tongji" if platform == "baidu_hmt" else platform
                found.setdefault(key, []).extend(
                    i for i in ids if i not in found.get(key, [])
                )
        return found

    def _format_extract_result(
        self, ids: dict[str, list[str]]
    ) -> dict[str, Any]:
        total = sum(len(v) for v in ids.values())
        flat = [i for v in ids.values() for i in v]
        return {
            "ids_found": total,
            "analytics_ids": ids,
            "all_ids": flat,
            "pivot_hint": (
                "用 pivot_search(analytics_id) 在 urlscan.io 查同 ID 域名"
                if flat
                else ""
            ),
        }

    def extract_ids(self, url: str) -> dict[str, Any]:
        """便捷方法：抓 URL → 提 ID（走完整审计链路）。"""
        return self.query(url, mode="extract")

    # ── 核心能力 2：用 ID pivot 找关联域名 ───────────────────────

    def pivot_search(self, analytics_id: str, size: int = 20) -> dict[str, Any]:
        """用统计 ID 在 urlscan.io 搜关联域名。走完整审计链路。"""
        return self.query(analytics_id, mode="pivot", size=size)

    def _parse_pivot_response(self, raw_json: str) -> dict[str, Any]:
        """解析 urlscan.io 搜索响应，提关联域名。"""
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True, "related_domains": []}
        results = data.get("results", []) or []
        domains: dict[str, dict[str, Any]] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            task = item.get("task", {}) or {}
            page = item.get("page", {}) or {}
            url = task.get("url", "")
            try:
                host = urllib.parse.urlparse(url).netloc.lower()
            except Exception:
                continue
            if not host or host in domains:
                continue
            domains[host] = {
                "domain": host,
                "first_seen_url": url,
                "scan_date": task.get("time", ""),
                "page_title": (page.get("title") or "")[:120],
                "country": page.get("country", ""),
            }
        domain_list = list(domains.values())
        return {
            "total_scans": data.get("total", 0),
            "related_domains": domain_list,
            "related_domain_count": len(domain_list),
            "association_note": (
                "同一统计 ID 出现在多个域名 → 同一运营者（强关联信号）。"
                "urlscan.io 记录为提交者主动公开的扫描数据。"
            ),
        }

    # ── 一站式：URL → ID → 关联域名 ──────────────────────────────

    def investigate(self, url: str, pivot_size: int = 20) -> dict[str, Any]:
        """完整链路：抓站 → 提 ID → 每个 ID pivot → 汇总关联域名。

        不走 query() 的单 URL 审计（内部多步），调用方自行记录审计。
        """
        self._enforce_rate_limit()
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            target = "https://" + target
        html = self._fetch_html(target)
        ids = self.extract_ids_from_html(html)
        flat = [i for v in ids.values() for i in v]

        pivots: dict[str, Any] = {}
        all_domains: dict[str, dict[str, Any]] = {}
        for aid in flat:
            self._enforce_rate_limit()
            pres = self._pivot_via_urlscan(aid, pivot_size)
            pivots[aid] = pres
            for d in pres.get("related_domains", []):
                host = d["domain"]
                entry = all_domains.setdefault(
                    host, {**d, "matched_ids": []}
                )
                if aid not in entry["matched_ids"]:
                    entry["matched_ids"].append(aid)

        # 排除目标自身域名
        try:
            self_host = urllib.parse.urlparse(target).netloc.lower()
        except Exception:
            self_host = ""
        related = [
            d for h, d in all_domains.items() if h != self_host
        ]
        return {
            "target_url": target,
            "target_host": self_host,
            "analytics_ids": ids,
            "ids_found": len(flat),
            "pivot_results": pivots,
            "related_domains": related,
            "related_domain_count": len(related),
            "association_note": (
                f"从 {target} 提取 {len(flat)} 个统计 ID，"
                f"pivot 发现 {len(related)} 个关联域名（排除自身）。"
                "同一 ID → 同一运营者。"
            ),
        }

    # ── 内部 HTTP ────────────────────────────────────────────────

    def _fetch_html(self, url: str, timeout: int = 20) -> str:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self._UA, "Accept": "text/html,*/*"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            # 尝试多种编码
            for enc in ("utf-8", "gbk", "gb2312", "big5"):
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _pivot_via_urlscan(
        self, analytics_id: str, size: int = 20
    ) -> dict[str, Any]:
        q = urllib.parse.quote(analytics_id)
        url = f"{self._URLSCAN_SEARCH}?q={q}&size={size}"
        req = urllib.request.Request(
            url, headers={"User-Agent": self._UA, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            return self._parse_pivot_response(raw)
        except Exception as e:
            return {"error": str(e)[:200], "related_domains": []}
