"""HuggingFace 开发者画像情报 — 公开 Hub API 适配器。数据边界: fully_public

HuggingFace Hub exposes a public, keyless REST API for exactly the same
profile/model data you see on a user's public page
(https://huggingface.co/<username>). This adapter only calls two endpoints:
  - GET https://huggingface.co/api/users/<username>/overview
    -> fullname, type (user/org), org memberships, numModels/numDatasets/
       numSpaces/numFollowers, bio ("details"), avatarUrl, createdAt.
  - GET https://huggingface.co/api/models?author=<username>&limit=50
       &sort=lastModified&direction=-1
    -> the author's public model list (modelId, likes, downloads,
       pipeline_tag, library_name, tags, createdAt).
This adapter does NOT:
- use any API token or authenticated session,
- read private models/datasets/spaces (all listed items are public),
- crawl the HTML UI (API only).

Verified 2026-10-21 (see docs/research/dev-intel-hf-pypi-sourcegraph-survey-20261021.md):
- GET /api/users/karpathy/overview -> 200 JSON: fullname "Andrej K",
  type "user", orgs [compvis-community, llmc], numModels 7,
  numFollowers 2052, createdAt 2022-08-13T23:40:17.000Z.
- GET /api/models?author=karpathy -> 200 JSON list: karpathy/nanochat-d32
  (96 likes, 5749 downloads), karpathy/tinyllamas, karpathy/774M_export, ...
- Nonexistent user overview -> 404 (structured "user_not_found");
  models?author=<nobody> -> 200 [].
- robots.txt (huggingface.co): "User-agent: * / Allow: /" — both endpoints
  allowed. No key, no login wall.

Dead ends documented in the same survey (NOT implemented):
- /api/users/<username> (no /overview suffix) -> 404. Endpoint does not exist.
- PyPI /pypi/<project>/json: technically 200 but robots.txt
  Disallow: /pypi/*/json -> red line, not touched.
- PyPI /search/?q=: robots.txt Disallow: /search* and no author filter anyway.
- Sourcegraph /.api/search/stream: keyless 200, but robots.txt
  Disallow: /search?q=* covers the search backend; weak identity mapping
  (commit emails are often noreply placeholders); not built.

Association value: ML/AI developers publish under their real names on HF;
username matches GitHub handles; org membership reveals employer/affiliation;
model counts and pipeline tags reveal specialty; profile bio is contact-lead
material (mined by the shared contact pipeline from context.description).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode

from adapters.safe_research_adapter import (
    ResearchAuditRecord,
    SafeResearchAdapter,
)

_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,37}[a-z0-9])?$")


class HuggingFaceLookup(SafeResearchAdapter):
    """HuggingFace 公开开发者画像：username -> 画像/组织/公开模型列表。"""

    source_domain = "huggingface.co"
    source_type = "developer_platform"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 2.0  # conservative; public keyless API

    _API_BASE = "https://huggingface.co/api"
    _MODEL_LIMIT = 50

    # ------------------------------------------------------------------ API

    @staticmethod
    def normalize_username(keyword: str) -> str | None:
        """Keyword -> plausible HF username/org handle, or None."""
        candidate = (keyword or "").strip().lstrip("@").lower()
        if _USERNAME_RE.match(candidate):
            return candidate
        return None

    def query(self, keyword: str, **params) -> dict[str, Any]:
        username = params.pop("username", None) or self.normalize_username(keyword)
        if not username:
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "username_invalid")
        self._last_username = username
        result = super().query(keyword, **params)
        fields = result.get("fields") or {}
        if not fields and result.get("response_status") == 404:
            # base query() skips extraction on empty body; emit structured miss
            fields = self._extract_public_fields(None)
            result["fields"] = fields
            result["field_count"] = len(fields)
        if fields.get("user_found"):
            models = self.fetch_public_models(username)
            if models is not None:
                fields["models"] = models
                fields["model_count"] = len(models)
                result["field_count"] = len(fields)
        return result

    def query_user(self, username: str, **params) -> dict[str, Any]:
        """Explicit-username lookup: query_user("karpathy") -> profile + models."""
        normalized = self.normalize_username(username)
        if not normalized:
            self._record_audit(keyword=username, url="", status=0, fields=[])
            return self._build_empty_result(username, "username_invalid")
        return self.query(username, username=normalized, **params)

    # --------------------------------------------------- public model listing

    def fetch_public_models(self, username: str) -> list[dict[str, Any]] | None:
        """Author's public model list. None on transport failure; [] when none."""
        self._enforce_rate_limit()
        url = self._build_models_url(username)
        status, raw, err = self._execute_query(
            url, {"User-Agent": "WallstreetTieling/0.6.0"}
        )
        self.audit.log(ResearchAuditRecord(
            operation_type="public_record_query",
            source_domain=self.source_domain,
            source_type=self.source_type,
            access_method="standard_http_get",
            rate_limit_applied=f"{self.min_request_interval}s",
            query_params_hash=hashlib.sha256(username.encode()).hexdigest()[:12],
            response_status=status,
            fields_extracted=["models"],
            data_boundary=self.data_boundary,
        ))
        self._models_last_status = status
        if status != 200 or not isinstance(raw, list):
            return None
        return [self.parse_model(m) for m in raw[: self._MODEL_LIMIT]
                if isinstance(m, dict)]

    @classmethod
    def _build_models_url(cls, username: str) -> str:
        qs = urlencode({
            "author": username,
            "limit": cls._MODEL_LIMIT,
            "sort": "lastModified",
            "direction": -1,
        })
        return f"{cls._API_BASE}/models?{qs}"

    # --------------------------------------------------------------- plumbing

    def _build_url(self, keyword: str, **params) -> str:
        username = (params.get("username") or getattr(self, "_last_username", None)
                    or keyword)
        return f"{self._API_BASE}/users/{quote(username, safe='')}/overview"

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        """JSON fetch. Returns (404, None, ...) for missing users instead of
        collapsing into a generic transport error."""
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, json.loads(body), "")
        except urllib.error.HTTPError as e:
            return (e.code, None, f"HTTPError: {e.code}")
        except Exception as e:  # network/DNS/TLS: report, don't raise
            return (0, None, f"{type(e).__name__}: {e}")

    # --------------------------------------------------------------- parsing

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        username = getattr(self, "_last_username", "")
        if not isinstance(raw_data, dict):
            return {"user_found": False, "username": username,
                    "profile_url": f"https://huggingface.co/{quote(username, safe='')}"}
        return {
            "user_found": True,
            "profile": self.parse_profile(raw_data, username),
        }

    @classmethod
    def parse_profile(cls, data: dict[str, Any], username: str) -> dict[str, Any]:
        orgs = []
        for o in (data.get("orgs") or []):
            if not isinstance(o, dict):
                continue
            name = (o.get("name") or "").strip()
            if name:
                orgs.append({
                    "name": name,
                    "fullname": (o.get("fullname") or "").strip() or None,
                })
        return {
            "username": data.get("user") or data.get("name") or username,
            "fullname": (data.get("fullname") or "").strip() or None,
            "type": data.get("type") or "user",
            "description": (data.get("details") or "").strip() or None,
            "orgs": orgs,
            "num_models": data.get("numModels"),
            "num_datasets": data.get("numDatasets"),
            "num_spaces": data.get("numSpaces"),
            "num_followers": data.get("numFollowers"),
            "num_following": data.get("numFollowing"),
            "is_pro": data.get("isPro"),
            "avatar_url": data.get("avatarUrl"),
            "created_at": data.get("createdAt"),
            "profile_url": f"https://huggingface.co/{quote(username, safe='')}",
        }

    @classmethod
    def parse_model(cls, m: dict[str, Any]) -> dict[str, Any]:
        model_id = m.get("modelId") or m.get("id") or ""
        return {
            "model_id": model_id,
            "likes": m.get("likes"),
            "downloads": m.get("downloads"),
            "pipeline_tag": m.get("pipeline_tag"),
            "library_name": m.get("library_name"),
            "tags": list(m.get("tags") or []),
            "created_at": m.get("createdAt"),
            "model_url": f"https://huggingface.co/{model_id}" if model_id else None,
        }
