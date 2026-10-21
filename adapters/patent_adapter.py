#!/usr/bin/env python3
"""专利检索适配器（Google Patents）。

回答："这家公司/这个人申请过哪些专利？→ 技术实力？→ 同一发明人在多家公司出现？"

数据源：Google Patents 公开搜索（patents.google.com/xhr/query）
    - 无需登录、无需 key、无验证码
    - 覆盖全球专利，CN 专利全（数据来自各国专利局公开数据）
    - 支持 assignee:"公司名" / inventor:"人名" 定向搜索

Association 逻辑：
    发明人 → 在多家公司申请专利 → 人员-企业关联（跳槽/兼职/技术合作信号）
    申请人 → 专利组合 → 技术实力、经营方向
    申请日时间线 → temporal_analysis 的输入（批量申请=研发投入期）

注意：中国官方专利检索（pss-system.cponline.cnipa.gov.cn）境外 IP 不可达，
Google Patents 是 CN 专利最完整的免费公开源。

data_boundary="fully_public"；EXPERIMENTAL，默认关闭。
公开专利数据不打码（用户明确要求：公开的就是公开的）。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


def _build_gp_url(query_str: str) -> str:
    """构建 Google Patents xhr query URL。"""
    inner = "q=" + urllib.parse.quote(query_str) + "&oq=" + urllib.parse.quote(query_str)
    return "https://patents.google.com/xhr/query?url=" + urllib.parse.quote(inner) + "&exp="


def _parse_patent_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """解析单条专利记录。"""
    pat = entry.get("patent") or {}
    pub_no = pat.get("publication_number", "") or ""
    # id 形如 patent/CN110086609B/en
    return {
        "publication_number": pub_no,
        "title": (pat.get("title") or "").strip(),
        "inventor": (pat.get("inventor") or "").strip(),
        "assignee": (pat.get("assignee") or "").strip(),
        "filing_date": pat.get("filing_date", "") or "",
        "grant_date": pat.get("grant_date", "") or "",
        "publication_date": pat.get("publication_date", "") or "",
        "priority_date": pat.get("priority_date", "") or "",
        "language": pat.get("language", "") or "",
        "url": f"https://patents.google.com/patent/{pub_no}/en" if pub_no else "",
    }


class PatentLookup(SafeResearchAdapter):
    """Google Patents 专利检索：关键词/申请人/发明人 → 专利列表。"""

    source_domain = "patents.google.com"
    source_type = "patent_public_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    def _build_url(self, keyword: str, **params) -> str:
        mode = str(params.get("mode", "keyword")).strip().lower()
        kw = keyword.strip()
        if mode == "assignee":
            q = f'assignee:"{kw}"'
        elif mode == "inventor":
            q = f'inventor:"{kw}"'
        else:
            q = kw
        return _build_gp_url(q)

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {"patent_count": 0, "patents": []}
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception:
            return {"patent_count": 0, "patents": [], "parse_error": True}
        results = (data.get("results") or {})
        total = results.get("total_num_results", 0) or 0
        patents: list[dict[str, Any]] = []
        for cluster in results.get("cluster") or []:
            for entry in cluster.get("result") or []:
                if not isinstance(entry, dict) or "patent" not in entry:
                    continue
                patents.append(_parse_patent_entry(entry))
                if len(patents) >= 50:  # 单次最多 50 条
                    break
            if len(patents) >= 50:
                break
        # 关联信号：去重后的发明人/申请人
        inventors = sorted({p["inventor"] for p in patents if p["inventor"]})
        assignees = sorted({p["assignee"] for p in patents if p["assignee"]})
        return {
            "patent_count": total,
            "patents_returned": len(patents),
            "patents": patents,
            "distinct_inventors": inventors[:30],
            "distinct_assignees": assignees[:30],
        }

    # -- 便捷方法 ------------------------------------------------------

    def query_by_assignee(self, company_name: str) -> dict[str, Any]:
        """按申请人（公司）搜索专利。"""
        return self.query(company_name, mode="assignee")

    def query_by_inventor(self, person_name: str) -> dict[str, Any]:
        """按发明人搜索专利。"""
        return self.query(person_name, mode="inventor")
