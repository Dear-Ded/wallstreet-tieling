"""海关进出口数据 — Zauba 公开贸易记录查询。数据边界: fully_public

US import/export shipment records searchable by company keyword.
Zauba (zauba.com) aggregates US CBP bill-of-lading data — public records.

Sources (verified 2026-10-21):
- Search: GET https://www.zauba.com/search?query={kw}&search-category={importers|exporters}
  → table#data-table: party-name / shipment count / total weight / latest shipment
- Detail: /{slug}-report-{id} → address, HS codes, ports, suppliers/buyers, shipment history
- No login, no CAPTCHA observed. Server-rendered HTML.

Association value (实体关联):
- Company name → import/export activity = hard business-existence evidence
- Importer ↔ exporter links = trade relationship graph
- Address on trade records → address association
- Shipment volume trends → business health signal

Philosophy: 美国海关提单数据是公开记录。只取公开搜索可见的企业级汇总，
不碰提单明细中的个人隐私。公开的就是公开的。

Rate limit: 3s between requests. No credentials. Default-off.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
from urllib.parse import quote


class ZaubaCustomsLookup(SafeResearchAdapter):
    """海关进出口查询：企业关键词 → 进出口商名单/贸易记录汇总。"""

    source_domain = "www.zauba.com"
    source_type = "customs_trade_data"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://www.zauba.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    _VALID_CATEGORIES = ("importers", "exporters")

    def _build_headers(self) -> dict:
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _check_robots(self) -> bool:
        # Verified 2026-10-21: zauba.com/robots.txt allows search pages
        # for general crawlers (only admin/login paths disallowed).
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self._BASE}/robots.txt",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore").lower()
            # Blocked only if /search is explicitly disallowed
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("disallow:") and "/search" in line:
                    return False
            return True
        except Exception:
            return True  # fail-open for research adapter base; query() still validates

    def _build_url(self, keyword: str, **params) -> str:
        category = params.get("category", "importers")
        if category not in self._VALID_CATEGORIES:
            category = "importers"
        return (
            f"{self._BASE}/search?query={quote(keyword.strip())}"
            f"&search-category={category}"
        )

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """Parse zauba search HTML → parties list."""
        parties = self.parse_search_page(raw_data or "", max_results=50)
        return {
            "party_count": len(parties),
            "parties": parties,
            "lookup_type": "customs_trade_data",
        }
        # Verified 2026-10-21: zauba.com/robots.txt allows search pages
        # for general crawlers (only admin/login paths disallowed).
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self._BASE}/robots.txt",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore").lower()
            # Blocked only if /search is explicitly disallowed
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("disallow:") and "/search" in line:
                    return False
            return True
        except Exception:
            return True  # fail-open for research adapter base; query() still validates

    def query(self, keyword: str, category: str = "importers",
              max_results: int = 20, **kwargs) -> dict[str, Any]:
        """按企业关键词查进出口商名单。

        category: "importers" | "exporters"
        Returns SafeResearchAdapter standard envelope with fields.parties[].
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return {
                "status": "invalid_input",
                "keyword": keyword,
                "message": "Empty keyword",
                "source": self.source_domain,
            }
        if category not in self._VALID_CATEGORIES:
            return {
                "status": "invalid_input",
                "keyword": keyword,
                "message": f"category must be one of {self._VALID_CATEGORIES}",
                "source": self.source_domain,
            }
        result = super().query(keyword, category=category, **kwargs)
        # Trim parties to max_results for caller convenience
        fields = result.get("fields") or {}
        parties = fields.get("parties") or []
        fields["parties"] = parties[:max_results]
        fields["party_count"] = len(fields["parties"])
        fields["category"] = category
        result["fields"] = fields
        return result

    @staticmethod
    def parse_search_page(html: str, max_results: int = 20) -> list[dict[str, Any]]:
        """解析搜索结果页的 data-table。"""
        out: list[dict[str, Any]] = []
        if not html:
            return out
        # rows: <td class="party-name"><a href="...">NAME</a></td>[<td>COUNTRY</td>]<td class="metric-cell">COUNT</td>...
        # (exporters table has an extra country <td>; importers does not)
        pat = re.compile(
            r'<td class="party-name"><a href="([^"]+)">([^<]+)</a></td>\s*'
            r'(?:<td(?![^>]*class="metric-cell")[^>]*>[^<]*</td>\s*)?'
            r'<td class="metric-cell">([^<]*)</td>\s*'
            r'<td class="metric-cell[^"]*">([^<]*)</td>\s*'
            r'<td class="metric-cell">([^<]*)</td>',
            re.S,
        )
        for m in pat.finditer(html):
            href, name, count, weight, latest = (g.strip() for g in m.groups())
            try:
                shipment_count = int(count.replace(",", ""))
            except ValueError:
                shipment_count = 0
            out.append({
                "name": name,
                "report_url": f"https://www.zauba.com{href}" if href.startswith("/") else href,
                "shipment_count": shipment_count,
                "total_weight": weight,
                "latest_shipment": latest,
            })
            if len(out) >= max_results:
                break
        return out

    def query_company_detail(self, report_url: str) -> dict[str, Any]:
        """抓企业详情页：地址/HS编码/港口/供应商/买方。"""
        report_url = (report_url or "").strip()
        if not report_url or "zauba.com" not in report_url:
            return {"error": "invalid_report_url", "fields": {}}
        if not self._check_robots():
            return {"error": "robots_disallowed", "fields": {}}
        import requests
        try:
            self._enforce_rate_limit()
            resp = requests.get(report_url, headers=self._build_headers(), timeout=20)
        except Exception as e:
            return {"error": f"request_failed: {type(e).__name__}", "fields": {}}
        if resp.status_code != 200:
            return {"error": f"http_{resp.status_code}", "fields": {}}
        detail = self.parse_detail_page(resp.text)
        detail["report_url"] = report_url
        detail["source"] = self.source_domain
        self._record_audit(keyword=report_url, url=report_url, status=resp.status_code,
                           fields=list(detail.keys()))
        return {"fields": detail, **{k: v for k, v in detail.items()
                                    if k in ("company_name", "address")}}

    @staticmethod
    def parse_detail_page(html: str) -> dict[str, Any]:
        """解析企业详情页关键字段（真实结构，2026-10-21 验证）。"""
        out: dict[str, Any] = {}
        if not html:
            return out
        # company name from title
        m = re.search(r"<title>([^<|]+)", html)
        if m:
            out["company_name"] = m.group(1).strip()
        # HS codes mentioned
        hs = re.findall(r"\bHS\s*(?:Code)?\s*:?\s*(\d{4,10})", html, re.I)
        if hs:
            out["hs_codes"] = sorted(set(hs))[:20]
        # counterparties: links to other company report pages
        cps = re.findall(
            r'href="/[a-z0-9-]+-report-[a-z0-9]+"[^>]*>([^<]{3,80})</a>', html)
        seen: list = []
        for c in cps:
            c = c.strip()
            if c and c not in seen:
                seen.append(c)
        if seen:
            out["counterparties"] = seen[:20]
        # ports of discharge: table rows after "Port of Discharge" header
        ports: list = []
        for pm in re.finditer(
                r"Port of Discharge</th>.*?</thead>\s*<tbody>(.*?)</tbody>",
                html, re.S | re.I):
            for rm in re.finditer(
                    r"<tr><td>([^<]{2,60})</td><td>([\d,]+)</td><td>([\d,]+)</td></tr>",
                    pm.group(1)):
                port, ships, weight = (g.strip() for g in rm.groups())
                try:
                    ports.append({
                        "port": port,
                        "shipments": int(ships.replace(",", "")),
                        "total_weight_kg": int(weight.replace(",", "")),
                    })
                except ValueError:
                    continue
        if ports:
            out["ports_of_discharge"] = ports[:15]
        return out
