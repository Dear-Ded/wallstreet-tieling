"""Semantic Scholar 学者公开情报 — api.semanticscholar.org 公开 REST API 适配器。数据边界: fully_public

Semantic Scholar exposes a public, keyless REST API
(https://api.semanticscholar.org/graph/v1/, documented at
/api-docs). This adapter uses three public endpoints and nothing else:

  GET /graph/v1/author/search?query=<name>&fields=...&limit=10
  GET /graph/v1/author/<authorId>?fields=name,affiliations,paperCount,citationCount,hIndex,url,homepage
  GET /graph/v1/author/<authorId>/papers?fields=title,year,authors&limit=10

Verified 2026-10-21:
- api.semanticscholar.org/robots.txt -> {"error":"Not found"} (no robots file);
  the endpoints are the officially documented public API. No robots conflict.
- Anonymous quota: 100 req / 5 min (documented). This adapter enforces a
  conservative 2.0s between requests (worst case 3 requests per query).
- Author search returns multiple candidates for a name (e.g. "Geoffrey Hinton"
  -> 22 hits: "G. Hinton", "Geoffrey Hinton", ...), so candidates are graded
  exact/strong/review against the query name; only the best-graded candidate
  is promoted, the rest stay in fields["candidates_considered"].
- Chinese name search works: query=李飞飞 -> 200, total=934, returns
  near-name variants ("飞飞 李", "飞翔 李", "飞 李") with paperCount /
  citationCount populated. Caveat: high homonym rate for Chinese names, so
  exact requires full-character match and most Chinese hits land in "review".
- Co-authors come from the authors[] array of the author's recent papers.
  Papers with >50 authors (big-science noise) are skipped; co-authors are
  deduplicated and capped at 20.
- Detail endpoint returns name, affiliations (list of strings), paperCount,
  citationCount, hIndex, url (S2 author page), homepage (personal site).

Dead ends on the academic lane (see docs/research/):
- ORCID: pub.orcid.org robots.txt is "User-agent: * / Disallow: /" — full
  automated-access ban, so the framework's own robots check blocks it.
- Google Scholar: robots.txt Disallow: /scholar and /citations? (search);
  only /citations?user= is allowed but there is no public name->userId
  resolution endpoint, and datacenter egress is 429/CAPTCHA-blocked.
- ResearchGate: robots.txt allows, but profile URLs 301 to /directory/profiles
  (login wall) for anonymous visitors.

Association value: affiliations tie a person to institutions (employer leads);
paperCount/citationCount/hIndex are capability signals; co-authors are
professional-network leads; homepage URLs feed the contact-extraction pipeline.
Everything returned is a lead, never an identity proof.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from typing import Any
from urllib.parse import quote

from adapters.safe_research_adapter import (
    ResearchAuditRecord,
    SafeResearchAdapter,
)


class SemanticScholarLookup(SafeResearchAdapter):
    """Semantic Scholar 公开学者 API：姓名 -> 学者画像 + 合作者。"""

    source_domain = "api.semanticscholar.org"
    source_type = "academic_public"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0  # conservative; anonymous quota is 100 req / 5 min

    _BASE = "https://api.semanticscholar.org/graph/v1"
    _AUTHOR_FIELDS = "name,affiliations,paperCount,citationCount,hIndex,url,homepage"
    _MAX_PAPERS = 10
    _MAX_AUTHORS_PER_PAPER = 50  # skip big-science megacollaborations
    _MAX_CO_AUTHORS = 20

    _UA = (
        "WallstreetTieling/0.6 (academic due diligence; "
        "contact: public research use)"
    )

    # ------------------------------------------------------------------ API

    def query(self, keyword: str, **params) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        if not keyword:
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "keyword_empty")
        self._last_keyword = keyword  # used by _execute_query for match grading
        return super().query(keyword, **params)

    # --------------------------------------------------------------- plumbing

    def _build_url(self, keyword: str, **params) -> str:
        fields = quote(self._AUTHOR_FIELDS, safe=",")
        return (
            f"{self._BASE}/author/search?query={quote(keyword)}"
            f"&fields={fields}&limit=10"
        )

    def _build_headers(self) -> dict[str, str]:
        return {"User-Agent": self._UA, "Accept": "application/json"}

    def _get_json(self, url: str) -> tuple[int, Any, str]:
        """Single GET with rate-limit spacing; override-aware for tests."""
        now = time.monotonic()
        last = self._last_request_time.get(self.source_domain, 0.0)
        wait = self.min_request_interval - (now - last)
        if wait > 0:
            self._sleeper(wait)
        self._last_request_time[self.source_domain] = time.monotonic()
        if self._execute_query_override is not None:
            return self._execute_query_override(url, self._build_headers())
        try:
            req = urllib.request.Request(url, headers=self._build_headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, json.loads(body), "")
        except Exception as e:  # network/DNS/TLS/JSON: report, don't raise
            return (0, None, f"{type(e).__name__}: {e}")

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        """Multi-step flow: search -> detail -> papers.

        `url` is the author/search URL built by _build_url. Returns
        (status, combined_payload, error) where combined_payload is parsed
        by _extract_public_fields.
        """
        status, search, err = self._get_json(url)
        if status != 200 or not isinstance(search, dict):
            return (status, None, err or "author search failed")
        candidates = [c for c in (search.get("data") or []) if isinstance(c, dict)]
        best, level = self.select_best(candidates, getattr(self, "_last_keyword", ""))
        combined: dict[str, Any] = {
            "search_total": search.get("total", 0),
            "candidates": candidates,
            "best": best,
            "match_level": level,
        }
        if not best or not best.get("authorId"):
            return (200, combined, "")
        detail_url = f"{self._BASE}/author/{quote(str(best['authorId']))}?fields={self._AUTHOR_FIELDS}"
        d_status, detail, d_err = self._get_json(detail_url)
        self._log_extra_request("author_detail", d_status)
        if d_status == 200 and isinstance(detail, dict):
            combined["detail"] = detail
        papers_url = (
            f"{self._BASE}/author/{quote(str(best['authorId']))}/papers"
            f"?fields=title,year,authors&limit={self._MAX_PAPERS}"
        )
        p_status, papers, p_err = self._get_json(papers_url)
        self._log_extra_request("author_papers", p_status)
        if p_status == 200 and isinstance(papers, dict):
            combined["papers"] = papers.get("data") or []
        combined["partial_errors"] = [e for e in (d_err, p_err) if e]
        return (200, combined, "")

    def _log_extra_request(self, kind: str, status: int) -> None:
        self.audit.log(ResearchAuditRecord(
            operation_type="public_record_query",
            source_domain=self.source_domain,
            source_type=self.source_type,
            access_method="standard_http_get",
            rate_limit_applied=f"{self.min_request_interval}s",
            query_params_hash=hashlib.sha256(kind.encode()).hexdigest()[:12],
            response_status=status,
            fields_extracted=[kind],
            data_boundary=self.data_boundary,
        ))

    # ----------------------------------------------------------- match grading

    @staticmethod
    def _norm_name(name: str) -> str:
        return re.sub(r"[^a-z\u4e00-\u9fff]", "", (name or "").lower())

    @classmethod
    def grade_match(cls, query: str, candidate: str) -> str:
        """Grade a candidate author name against the query name.

        exact:  normalized names identical (full-character match).
        strong: same last token + first initial, or one normalized name
                contains the other with a shared surname token.
        review: everything else. All grades are leads, not identity proofs.
        """
        q, c = cls._norm_name(query), cls._norm_name(candidate)
        if not q or not c:
            return "review"
        if q == c:
            return "exact"
        q_tokens = [t for t in re.split(r"[\s.\-]+", (query or "").lower()) if t]
        c_tokens = [t for t in re.split(r"[\s.\-]+", (candidate or "").lower()) if t]
        if q_tokens and c_tokens and q_tokens[-1] == c_tokens[-1]:
            q_first = q_tokens[0][0] if q_tokens[0] else ""
            c_first = c_tokens[0][0] if c_tokens[0] else ""
            if q_tokens[0] == c_tokens[0] or (q_first and q_first == c_first):
                return "strong"
        if len(q) >= 2 and (q in c or c in q):
            return "strong"
        return "review"

    @classmethod
    def select_best(
        cls, candidates: list[dict[str, Any]], query: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Pick the best-graded candidate; ties break on citationCount."""
        best: dict[str, Any] | None = None
        best_level = "review"
        rank = {"exact": 3, "strong": 2, "review": 1}
        for cand in candidates:
            level = cls.grade_match(query, cand.get("name") or "")
            score = (rank[level], int(cand.get("citationCount") or 0))
            if best is None or score > (rank[best_level], int(best.get("citationCount") or 0)):
                best, best_level = cand, level
        return best, best_level

    # --------------------------------------------------------------- parsing

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data or not isinstance(raw_data, dict):
            return {"author_found": False, "transport_error": True}
        best = raw_data.get("best")
        fields: dict[str, Any] = {
            "author_found": bool(best),
            "match_level": raw_data.get("match_level", "review"),
            "search_total": raw_data.get("search_total", 0),
            "candidates_considered": len(raw_data.get("candidates") or []),
        }
        if not best:
            return fields
        detail = raw_data.get("detail") or best
        author = self.parse_author(detail)
        fields["author"] = author
        papers_raw = raw_data.get("papers") or []
        top_papers, co_authors = self.parse_papers(papers_raw, author.get("name") or "")
        fields["top_papers"] = top_papers
        fields["co_authors"] = co_authors
        fields["co_author_count"] = len(co_authors)
        return fields

    @staticmethod
    def parse_author(detail: dict[str, Any]) -> dict[str, Any]:
        """Author detail -> normalized author record."""
        affs = [a for a in (detail.get("affiliations") or []) if a]
        return {
            "author_id": str(detail.get("authorId") or ""),
            "name": detail.get("name") or "",
            "affiliations": affs,
            "paper_count": detail.get("paperCount") or 0,
            "citation_count": detail.get("citationCount") or 0,
            "h_index": detail.get("hIndex") or 0,
            "url": detail.get("url") or "",
            "homepage": detail.get("homepage") or "",
        }

    @classmethod
    def parse_papers(
        cls, papers: list[dict[str, Any]], self_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Papers -> top papers + deduplicated co-authors (self excluded)."""
        self_norm = cls._norm_name(self_name)
        top_papers: list[dict[str, Any]] = []
        co_map: dict[str, dict[str, Any]] = {}
        for p in papers:
            if not isinstance(p, dict):
                continue
            authors = [a for a in (p.get("authors") or []) if isinstance(a, dict)]
            top_papers.append({
                "paper_id": p.get("paperId") or "",
                "title": p.get("title") or "",
                "year": p.get("year"),
                "author_count": len(authors),
            })
            if len(authors) > cls._MAX_AUTHORS_PER_PAPER:
                continue  # big-science megacollaboration: not a personal network signal
            for a in authors:
                name = (a.get("name") or "").strip()
                if not name or cls._norm_name(name) == self_norm:
                    continue
                key = cls._norm_name(name)
                entry = co_map.get(key)
                if entry is None:
                    entry = {"name": name, "author_id": str(a.get("authorId") or ""),
                             "shared_papers": 0, "paper_titles": []}
                    co_map[key] = entry
                entry["shared_papers"] += 1
                title = p.get("title") or ""
                if title and title not in entry["paper_titles"]:
                    entry["paper_titles"].append(title[:120])
        co_authors = sorted(
            co_map.values(), key=lambda e: (-e["shared_papers"], e["name"])
        )[: cls._MAX_CO_AUTHORS]
        return top_papers, co_authors
