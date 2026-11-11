"""HaveIBeenPwned 公开泄露事件名录 — 只读 breach 目录适配器。数据边界: fully_public

数据边界 (写死, 红线):
- 只读 https://haveibeenpwned.com/PwnedWebsites: 公开泄露事件目录
  (breach 名、pwn 计数、收录日期、泄露日期)。不查具体账号、不拉取
  任何泄露库内容。
- 永远不碰 /account/* (robots.txt 明确 Disallow, 且是红线)；
  不碰 /unifiedsearch/* 等账号查询入口。
- v3 API 全部需要 API key: 死路, 未建任何 API 客户端。

实测证据 (2026-10-21, plain HTTP, 无登录):
- GET /PwnedWebsites -> 200, ~1MB 服务端渲染 HTML 表格, 1047 个 breach 行
  (<tr id="<Name>">, td[data-name=breach|pwncount|date|breachDate])。
- robots.txt: /PwnedWebsites 不在 Disallow 列表 (Disallow 只有 /BreachSummary、
  /account/*、/unifiedsearch/* 等账号相关路径)。注意 urllib.robotparser 解析
  该 robots.txt 会因 "Content-Signal:" 行丢弃全部规则 (entries 为空) —
  本适配器用手写解析器做 Disallow 前缀检查, 不依赖 urllib 的解析结果。
- 用途: 尽调时查 "某服务/厂商是否出现在公开 breach 名录" (lead, 非定罪)。

Query 语义: query("adobe") -> 名录中名称匹配的 breach 条目。
匹配规则: 大小写不敏感, 完全匹配优先, 其次子串匹配。
"""

from __future__ import annotations

import hashlib
import html as html_module
import re
import time
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_ROW_RE = re.compile(r'<tr id="([^"]+)">(.*?)</tr>', re.S)
_TD_RE = re.compile(
    r'<td data-name="(breach|pwncount|date|breachDate)" data-value="([^"]*)"[^>]*>'
    r'(.*?)</td>',
    re.S,
)
_NAME_RE = re.compile(r"<div>\s*([^<]+?)\s*</div>", re.S)

_CATALOG_TTL = 24 * 3600  # 名录更新频率低, 进程内缓存 24h


class HIBPBreachCatalog(SafeResearchAdapter):
    """HaveIBeenPwned 公开 breach 名录查询。"""

    source_domain = "haveibeenpwned.com"
    source_type = "breach_catalog_public"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # 1MB 目录页, 保守

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._catalog: list[dict[str, Any]] | None = None
        self._catalog_fetched_at: float = 0.0

    # ------------------------------------------------------------ robots.txt

    def _check_robots(self) -> bool:
        """手写 robots.txt Disallow 前缀检查。

        urllib.robotparser 解析 haveibeenpwned.com/robots.txt 时会因
        "Content-Signal:" 非标准行丢弃全部规则 (实测 entries 为空),
        故在此处手动解析, 只认 User-agent: * 段的 Disallow 前缀。
        """
        if self._robots_checker is not None:
            return bool(self._robots_checker(self.source_domain,
                                             f"https://{self.source_domain}/"))
        path = "/PwnedWebsites"
        try:
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers=self._build_headers(),
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return False  # robots 拿不到就保守停手
        in_wildcard = False
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            low = line.lower()
            if low.startswith("user-agent:"):
                in_wildcard = line.split(":", 1)[1].strip() == "*"
            elif in_wildcard and low.startswith("disallow:"):
                rule = line.split(":", 1)[1].strip().rstrip("*")
                if rule and (path == rule or path.startswith(rule)):
                    return False
        return True

    # ----------------------------------------------------------------- query

    def query(self, keyword: str, **params) -> dict[str, Any]:
        start = time.monotonic()
        name = (keyword or "").strip()
        if not name:
            return self._build_empty_result(keyword, "empty_query")
        if self.requires_credentials and not self._has_required_credentials():
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "credentials_required")
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=keyword, url="", status=0, fields=[],
                               robots_allowed=False)
            return self._build_empty_result(keyword, "robots_txt_disallowed")
        rows, status, error = self._get_catalog()
        matches = self._match(rows, name)
        url = self._build_url(keyword)
        self._record_audit(
            keyword=keyword, url=url, status=status,
            fields=["breaches", "match_count"] if matches else ["match_count"],
        )
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "query_name": name,
            "catalog_size": len(rows),
            "match_count": len(matches),
            "breaches": matches,
            "field_count": len(matches) + 2,
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
            "fields": {
                "breaches": matches,
                "match_count": len(matches),
                "catalog_size": len(rows),
            },
        }

    def _get_catalog(self) -> tuple[list[dict[str, Any]], int, str]:
        """拉取并缓存 /PwnedWebsites 名录 (TTL 24h)。"""
        now = time.monotonic()
        if (self._catalog is not None
                and now - self._catalog_fetched_at < _CATALOG_TTL):
            return self._catalog, 200, ""
        url = self._build_url("")
        if self._execute_query_override is not None:
            status, raw, error = self._execute_query_override(
                url, self._build_headers())
        else:
            status, raw, error = self._execute_query(url, self._build_headers())
        rows = self.parse_catalog(raw) if raw and status == 200 else []
        if status == 200 and rows:
            self._catalog = rows
            self._catalog_fetched_at = now
        return rows, status, error

    @staticmethod
    def _match(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
        """大小写不敏感: 完全匹配优先, 其次子串匹配 (breach 名或展示名)。"""
        q = name.strip().lower()
        exact, partial = [], []
        for r in rows:
            rid = str(r.get("id", "")).lower()
            title = str(r.get("title", "")).lower()
            if q == rid or q == title:
                exact.append(r)
            elif q in rid or q in title:
                partial.append(r)
        return exact + partial

    # --------------------------------------------------------------- plumbing

    def _build_url(self, keyword: str, **params) -> str:
        return f"https://{self.source_domain}/PwnedWebsites"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        # query() 重写了主逻辑, 这里保留基类契约
        return {"breaches": self.parse_catalog(raw_data)} if raw_data else {}

    @staticmethod
    def _strip(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        return html_module.unescape(re.sub(r"\s+", " ", text)).strip()

    @classmethod
    def parse_catalog(cls, body: str) -> list[dict[str, Any]]:
        """解析 /PwnedWebsites 服务端渲染表格 -> breach 条目列表。"""
        out: list[dict[str, Any]] = []
        if not body:
            return out
        for row_id, row_html in _ROW_RE.findall(body):
            cells: dict[str, tuple[str, str]] = {}
            for cname, cvalue, chtml in _TD_RE.findall(row_html):
                cells[cname] = (cvalue, chtml)
            if "breach" not in cells:
                continue
            _, breach_html = cells["breach"]
            m = _NAME_RE.search(breach_html)
            title = cls._strip(m.group(1)) if m else cls._strip(breach_html)
            pwn_raw = cells.get("pwncount", ("", ""))[0]
            try:
                pwn_count = int(pwn_raw) if pwn_raw else None
            except ValueError:
                pwn_count = None
            pwn_display = cls._strip(cells.get("pwncount", ("", ""))[1]) or None
            entry: dict[str, Any] = {
                "id": html_module.unescape(row_id),
                "title": title or html_module.unescape(row_id),
                "pwn_count": pwn_count,
                "pwn_count_display": pwn_display,
                "added_date": cls._strip(cells.get("date", ("", ""))[1]) or None,
                "breach_date": cls._strip(cells.get("breachDate", ("", ""))[1]) or None,
                "breach_url": f"https://haveibeenpwned.com/Breach/{row_id}",
            }
            out.append(entry)
        return out
