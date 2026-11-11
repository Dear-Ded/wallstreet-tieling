#!/usr/bin/env python3
"""巨潮资讯 (cninfo.com.cn) 公告亲属关系抽取 — 亲属关系 lane 金标准路径.

中国证监会指定信息披露网站（巨潮资讯网）:上市公司公告为法定强制披露,
其中的亲属关系表述（一致行动人/关联自然人/收购报告书/权益变动报告书）
是"挂名法人/疑似实控"推理从"疑似"走向"实锤披露"的最高证据等级。

Survey（2026-10-21 实测）:
- `POST http://www.cninfo.com.cn/new/hisAnnouncement/query`
  (pageNum/pageSize/column=szse/tabName=fulltext/searchkey=关键词):
  免登录、无 key,实测返回 200 + 公告 JSON（含 adjunctUrl -> PDF）。
- robots.txt: www.cninfo.com.cn/robots.txt 返回错误页（非明确 Disallow），
  基类 robots 检查按"无规则=允许"处理；本 adapter 仅访问公开查询接口。
- PDF: `http://static.cninfo.com.cn/<adjunctUrl>` 免登录可下载；
  权益变动报告书等多为文字版 PDF，pdftotext 可提取正文。
- 限速: 5 秒间隔（巨潮接口注意限频，保守）。

工作流: query(人名/公司名) -> 公告搜索 -> 按相关性取前 N 篇 PDF ->
正文抽取亲属关系表述（evidence_level="exact"）-> kinship_statements。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter
from core.kinship_extract import extract_kinship_statements

_API_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_PDF_BASE = "http://static.cninfo.com.cn/"
_MAX_PDF_BYTES = 12 * 1024 * 1024

# 标题相关性加权：亲属披露最可能出现在这些公告类型中
_TITLE_BOOST = (
    "权益变动报告书", "收购报告书", "上市公告书", "年度报告",
)


def _to_date(ms: Any) -> str:
    # 公告时间为北京时间（Asia/Shanghai）午夜；显式指定避免 UTC 机器差一天
    try:
        from datetime import datetime, timedelta, timezone
        tz = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(int(ms) / 1000, tz=tz).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return ""


class CninfoKinshipLookup(SafeResearchAdapter):
    """巨潮资讯公告亲属关系抽取：人名/公司名 -> 披露的亲属关系。"""

    source_domain = "cninfo.com.cn"
    source_type = "listed_company_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0  # 巨潮接口限频，保守

    # -- 纯函数解析入口（离线可测） ------------------------------------

    @staticmethod
    def parse_announcement_list(raw: Any) -> list[dict[str, Any]]:
        """解析 hisAnnouncement/query 返回的公告列表。"""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, dict):
            return []
        out: list[dict[str, Any]] = []
        for item in data.get("announcements") or []:
            if not isinstance(item, dict):
                continue
            adjunct = str(item.get("adjunctUrl") or "")
            out.append({
                "sec_code": str(item.get("secCode") or ""),
                "sec_name": str(item.get("secName") or item.get("tileSecName") or ""),
                "title": str(item.get("announcementTitle") or item.get("shortTitle") or ""),
                "date": _to_date(item.get("announcementTime")),
                "announcement_id": str(item.get("announcementId") or ""),
                "pdf_url": _PDF_BASE + adjunct if adjunct else "",
            })
        return out

    @staticmethod
    def extract_kinship_from_text(text: str, focus_name: str | None,
                                  source_ref: str = "") -> list[dict[str, Any]]:
        """公告正文 -> kinship statements（法定披露原文，exact）。"""
        return extract_kinship_statements(
            text, focus_name=focus_name,
            evidence_level="exact", source_ref=source_ref)

    # -- 网络层（可 monkeypatch，便于测试） ------------------------------

    def _post_search(self, keyword: str, page_size: int) -> tuple[int, str, str]:
        form = urllib.parse.urlencode({
            "pageNum": 1,
            "pageSize": max(1, min(page_size, 30)),
            "column": "szse",
            "tabName": "fulltext",
            "searchkey": keyword,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                _API_URL, data=form,
                headers={**self._build_headers(),
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except Exception as exc:  # noqa: BLE001 - 网络错误归一化
            return (0, "", "{}: {}".format(type(exc).__name__, exc))

    def _fetch_pdf_text(self, pdf_url: str) -> tuple[str | None, str]:
        """下载 PDF 并提文本。返回 (text|None, note)。"""
        try:
            req = urllib.request.Request(pdf_url, headers=self._build_headers())
            with urllib.request.urlopen(req, timeout=45) as resp:
                chunks: list[bytes] = []
                total = 0
                while True:
                    blk = resp.read(65536)
                    if not blk:
                        break
                    total += len(blk)
                    if total > _MAX_PDF_BYTES:
                        return None, "pdf_too_large"
                    chunks.append(blk)
                pdf_bytes = b"".join(chunks)
        except Exception as exc:  # noqa: BLE001
            return None, "pdf_download_failed:{}".format(type(exc).__name__)
        if not pdf_bytes.startswith(b"%PDF"):
            return None, "pdf_not_pdf_content"
        pdftotext = shutil.which("pdftotext")
        if not pdftotext:
            return None, "pdf_tool_unavailable"
        try:
            proc = subprocess.run(
                [pdftotext, "-layout", "-", "-"],
                input=pdf_bytes, capture_output=True, timeout=90)
        except Exception as exc:  # noqa: BLE001
            return None, "pdf_parse_failed:{}".format(type(exc).__name__)
        if proc.returncode != 0:
            return None, "pdf_parse_failed:exit{}".format(proc.returncode)
        text = proc.stdout.decode("utf-8", errors="replace")
        if len(text.strip()) < 50:
            return None, "pdf_no_extractable_text"
        return text, ""

    # -- SafeResearchAdapter 接口 ---------------------------------------

    def _build_url(self, keyword: str, **params) -> str:
        return _API_URL

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        return {"announcements": self.parse_announcement_list(raw_data)}

    def _ranked(self, announcements: list[dict[str, Any]],
                limit: int) -> list[dict[str, Any]]:
        def _score(a: dict[str, Any]) -> tuple[int, str]:
            title = a.get("title") or ""
            boost = 100 if any(k in title for k in _TITLE_BOOST) else 0
            return (boost, a.get("date") or "")
        cands = [a for a in announcements if a.get("pdf_url")]
        cands.sort(key=_score, reverse=True)
        return cands[:limit]

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """人名/公司名 -> 公告搜索 +（默认）前 N 篇 PDF 正文亲属抽取。"""
        start = time.monotonic()
        name = (keyword or "").strip()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=name, url=_API_URL, status=0,
                               fields=[], robots_allowed=False)
            return self._build_empty_result(name, "robots_txt_disallowed")

        page_size = int(params.get("page_size", 10) or 10)
        fetch_text = bool(params.get("fetch_text", True))
        max_pdfs = int(params.get("max_pdfs", 2) or 0)

        status, raw, error = self._post_search(name, page_size)
        announcements = self.parse_announcement_list(raw) if raw else []
        fields: dict[str, Any] = {
            "query_name": name,
            "total_count": len(announcements),
            "announcements": announcements[:10],
            "kinship_statements": [],
            "pdfs_fetched": 0,
        }
        if error:
            fields["search_error"] = error[:160]

        focus = name if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", name) else None
        if fetch_text and status == 200:
            for ann in self._ranked(announcements, max_pdfs):
                self._enforce_rate_limit()
                text, note = self._fetch_pdf_text(ann["pdf_url"])
                if text is None:
                    ann["pdf_note"] = note
                    continue
                fields["pdfs_fetched"] += 1
                src_ref = "《{}》{}".format(
                    ann["title"][:60], "（{}）".format(ann["date"]) if ann["date"] else "")
                for st in self.extract_kinship_from_text(text, focus, src_ref):
                    st["announcement_id"] = ann["announcement_id"]
                    st["pdf_url"] = ann["pdf_url"]
                    fields["kinship_statements"].append(st)

        fields["data_note"] = (
            "巨潮资讯法定披露公告的亲属关系抽取：命中表述为原文引用 "
            "（evidence_level=exact），仍属线索，需结合其他来源核实；"
            "未命中不代表无亲属关系。"
        )
        self._record_audit(keyword=name, url=_API_URL, status=status,
                           fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(name.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "fields": fields,
            "field_count": len(fields),
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }
