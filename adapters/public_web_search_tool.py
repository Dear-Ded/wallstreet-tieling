#!/usr/bin/env python3
"""Public web-search result normalizer for risk discovery."""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from core.interfaces import ToolProvider, ToolResult
from core.record_quality import audit_standardized_records


@dataclass(frozen=True)
class PublicWebSearchConfig:
    """Config contract for a public web-search provider."""

    provider_type: str = "auto"
    enabled: bool = True
    searxng_base_url: str = ""
    max_results: int = 10
    request_timeout_seconds: float = 10.0
    provider_options: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "enabled": self.enabled,
            "searxng_base_url": self.searxng_base_url,
            "max_results": self.max_results,
            "request_timeout_seconds": self.request_timeout_seconds,
            "provider_options": dict(self.provider_options or {}),
        }



def reality_drill_extract(snippet: str, url: str = "", source_type: str = "public_web_search") -> dict:
    """EV-007: Extract structured leads from public web snippets.
    Returns money/goods/people leads with confidence and evidence_id."""
    t = snippet.lower()
    result = {"source_url": url, "source_type": source_type, "money_leads": [], "goods_leads": [], "people_leads": []}
    # Money
    if any(k in t for k in ("revenue","sales","income","profit","debt","funding","investment","acquisition","融资","收入","利润","债务")):
        result["money_leads"].append({"hint": "financial_metric", "snippet": snippet[:100], "confidence": "lead"})
    if any(k in t for k in ("financial results","earnings","annual report","10-k","10-q","年报","财报")):
        result["money_leads"].append({"hint": "financial_filing", "snippet": snippet[:100], "confidence": "lead"})
    # Goods
    if any(k in t for k in ("product","launch","release","patent","trademark","supplier","customer","market share","产品","发布","专利","供应商","客户")):
        result["goods_leads"].append({"hint": "product_or_market", "snippet": snippet[:100], "confidence": "lead"})
    # People
    if any(k in t for k in ("ceo","cfo","cto","founder","director","executive","appointed","resigned","board","总裁","创始人","董事")):
        result["people_leads"].append({"hint": "personnel", "snippet": snippet[:100], "confidence": "lead"})
    return result


def reality_drill_extract(snippet: str, url: str = "", source_type: str = "public_web_search") -> dict:
    """EV-007: Extract structured leads from public web snippets.
    Returns money/goods/people leads with confidence and evidence_id."""
    t = snippet.lower()
    result = {"source_url": url, "source_type": source_type, "money_leads": [], "goods_leads": [], "people_leads": []}
    # Money
    if any(k in t for k in ("revenue","sales","income","profit","debt","funding","investment","acquisition","融资","收入","利润","债务")):
        result["money_leads"].append({"hint": "financial_metric", "snippet": snippet[:100], "confidence": "lead"})
    if any(k in t for k in ("financial results","earnings","annual report","10-k","10-q","年报","财报")):
        result["money_leads"].append({"hint": "financial_filing", "snippet": snippet[:100], "confidence": "lead"})
    # Goods
    if any(k in t for k in ("product","launch","release","patent","trademark","supplier","customer","market share","产品","发布","专利","供应商","客户")):
        result["goods_leads"].append({"hint": "product_or_market", "snippet": snippet[:100], "confidence": "lead"})
    # People
    if any(k in t for k in ("ceo","cfo","cto","founder","director","executive","appointed","resigned","board","总裁","创始人","董事")):
        result["people_leads"].append({"hint": "personnel", "snippet": snippet[:100], "confidence": "lead"})
    return result

class PublicWebSearchTool(ToolProvider):
    """Normalizes public web-search hits into standardized evidence records.

    The tool can wrap a host-provided search function later. Today it accepts
    explicit `results` from callers/tests and turns them into evidence-shaped
    records so downstream graph/risk logic stays provider-neutral.
    """

    def __init__(
        self,
        provider: Any = None,
        *,
        config: PublicWebSearchConfig | dict[str, Any] | None = None,
    ):
        self._available = {"public_web_search", "web_search", "web"}
        self.provider = provider
        self.config = coerce_public_web_search_config(config)

    def available_tools(self) -> set[str]:
        return set(self._available)

    def health_check(self) -> dict[str, Any]:
        provider_report = self.provider_report()
        return {
            "ok": provider_report["ok"],
            "standardized_records": True,
            "live_provider_configured": provider_report["provider_configured"],
            "zero_config_ready": provider_report["zero_config_ready"],
            "supports_live_provider": True,
            "supports_url_fetcher": True,
            "provider_report": provider_report,
            "notes": [
                "This bridge provides a default zero-config public search provider and supports injected providers or self-hosted SearXNG JSON endpoints.",
            ],
        }

    async def provider_validation_report(
        self,
        *,
        sample_query: str = "public company profile",
        fetcher: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a bounded live-provider smoke check for user-configured search."""
        provider_report = self.provider_report()
        provider = kwargs.get("provider") or self._provider_from_config(kwargs)
        if provider is None:
            return {
                "ok": False,
                "status": "provider_not_configured",
                "sample_query": sample_query,
                "provider_report": provider_report,
                "result_count": 0,
                "standardized_record_count": 0,
                "next_action": provider_report["next_action"],
            }

        try:
            raw_results = await search_public_web_provider(
                sample_query,
                provider=provider,
                max_results=int(kwargs.get("max_results", min(self.config.max_results, 3)) or 3),
                provider_options=dict(kwargs.get("provider_options", self.config.provider_options or {}) or {}),
            )
        except Exception as exc:
            return {
                "ok": False,
                "status": "provider_error",
                "sample_query": sample_query,
                "provider_report": provider_report,
                "result_count": 0,
                "standardized_record_count": 0,
                "error": f"{type(exc).__name__}: {exc}",
                "next_action": "fix_public_web_search_provider_or_endpoint",
            }

        records = await public_web_results_to_standardized_records(
            sample_query,
            raw_results,
            fetcher=fetcher,
            fetch_contents=dict(kwargs.get("fetch_contents", {}) or {}),
        )
        quality = audit_standardized_records(records).to_dict()
        status = "ready" if records and quality.get("ok") else "provider_returned_no_standard_records"
        return {
            "ok": bool(records) and bool(quality.get("ok")),
            "status": status,
            "sample_query": sample_query,
            "provider_report": provider_report,
            "result_count": len(raw_results),
            "standardized_record_count": len(records),
            "record_quality": quality,
            "next_action": (
                "ready_for_risk_discovery_routing"
                if records and quality.get("ok")
                else "provider_reachable_but_needs_result_mapping_or_broader_query"
            ),
        }

    def provider_report(self) -> dict[str, Any]:
        """Return provider readiness in product-facing terms."""
        config = self.config
        missing: list[str] = []
        provider_configured = self.provider is not None
        zero_config_ready = config.provider_type in {"auto", "duckduckgo_instant", "default"}
        if config.enabled:
            if config.provider_type == "searxng":
                if config.searxng_base_url.strip():
                    provider_configured = True
                else:
                    missing.append("searxng_base_url")
            elif zero_config_ready:
                provider_configured = True
            elif config.provider_type in {"disabled", "none", ""}:
                missing.append("provider_type")
            elif self.provider is None:
                missing.append("provider_instance")
        return {
            "ok": not config.enabled or (provider_configured and not missing),
            "default_enabled": config.enabled and zero_config_ready,
            "provider_configured": provider_configured,
            "zero_config_ready": zero_config_ready,
            "config": config.to_dict(),
            "missing": missing,
            "next_action": (
                "ready_for_live_search"
                if provider_configured and not missing
                else "configure_public_web_search_provider_or_use_fixture_results"
            ),
        }

    async def search(self, query: str, tool_type: str = "public_web_search", **kwargs: Any) -> ToolResult:
        if tool_type not in self._available:
            return ToolResult(
                ok=False,
                error=f"unsupported web-search tool type: {tool_type}",
                data={"query": query, "tool_type": tool_type},
                sources=["public_web_search:error"],
            )

        raw_results = kwargs.get("results") or []
        request_timeout_seconds = _coerce_timeout(
            kwargs.get("request_timeout_seconds"),
            self.config.request_timeout_seconds,
        )
        provider = kwargs.get("provider") or self._provider_from_config(
            kwargs,
            request_timeout_seconds=request_timeout_seconds,
        )
        provider_configured = provider is not None
        provider_attempted = False
        if not raw_results:
            provider_attempted = provider is not None
            raw_results = await asyncio.wait_for(
                search_public_web_provider(
                    query,
                    provider=provider,
                    max_results=int(kwargs.get("max_results", self.config.max_results) or 10),
                    provider_options=dict(kwargs.get("provider_options", self.config.provider_options or {}) or {}),
                ),
                timeout=request_timeout_seconds,
            )
        fetcher = kwargs.get("fetcher")
        fetch_contents = kwargs.get("fetch_contents") or {}
        records = await public_web_results_to_standardized_records(
            query,
            raw_results,
            fetcher=fetcher,
            fetch_contents=fetch_contents,
        )
        quality = audit_standardized_records(records)
        return ToolResult(
            ok=True,
            data={
                "query": query,
                "source_name": "public_web_search",
                "source_type": "search_engine",
                "provider_configured": provider_configured,
                "provider_attempted": provider_attempted,
                "provider_report": self.provider_report(),
                "execution_state": self._execution_state(
                    records=records,
                    provider_configured=provider_configured,
                    provider_attempted=provider_attempted,
                ),
                "standardized_records": records,
                "record_quality": quality.to_dict(),
                "result_count": len(records),
            },
            sources=["public_web_search:standardized_records"],
        )

    def _provider_from_config(
        self,
        kwargs: dict[str, Any],
        *,
        request_timeout_seconds: float | None = None,
    ) -> Any:
        if self.provider is not None:
            return self.provider
        base_url = str(kwargs.get("searxng_base_url") or self.config.searxng_base_url or "").strip()
        timeout_seconds = _coerce_timeout(request_timeout_seconds, self.config.request_timeout_seconds)
        if base_url:
            return SearxngSearchProvider(
                base_url,
                http_get=kwargs.get("http_get"),
                request_timeout_seconds=timeout_seconds,
            )
        if self.config.provider_type in {"auto", "duckduckgo_instant", "default"} and self.config.enabled:
            return DuckDuckGoInstantAnswerProvider(
                http_get=kwargs.get("http_get"),
                request_timeout_seconds=timeout_seconds,
            )
        return None

    @staticmethod
    def _execution_state(
        *,
        records: list[dict[str, Any]],
        provider_configured: bool,
        provider_attempted: bool,
    ) -> str:
        if records:
            return "records_ready"
        if provider_attempted:
            return "provider_returned_no_results"
        if provider_configured:
            return "provider_configured_not_attempted"
        return "fixture_or_provider_required"


def coerce_public_web_search_config(raw: PublicWebSearchConfig | dict[str, Any] | None) -> PublicWebSearchConfig:
    if raw is None:
        return PublicWebSearchConfig()
    if isinstance(raw, PublicWebSearchConfig):
        return raw
    return PublicWebSearchConfig(
        provider_type=str(raw.get("provider_type") or raw.get("type") or "auto"),
        enabled=bool(raw.get("enabled", True)),
        searxng_base_url=str(raw.get("searxng_base_url") or raw.get("base_url") or ""),
        max_results=int(raw.get("max_results", 10) or 10),
        request_timeout_seconds=float(raw.get("request_timeout_seconds", raw.get("timeout", 10.0)) or 10.0),
        provider_options=dict(raw.get("provider_options", {}) or {}),
    )


async def search_public_web_provider(
    query: str,
    *,
    provider: Any = None,
    max_results: int = 10,
    provider_options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run a configured live search provider and return provider-neutral hits."""
    if provider is None:
        return []
    provider_options = provider_options or {}
    if hasattr(provider, "search") and callable(provider.search):
        raw = provider.search(query, max_results=max_results, **provider_options)
    elif callable(provider):
        raw = provider(query, max_results=max_results, **provider_options)
    else:
        return []
    if hasattr(raw, "__await__"):
        raw = await raw
    return normalize_search_provider_results(raw)


class SearxngSearchProvider:
    """Minimal SearXNG JSON provider for self-hosted public web search."""

    def __init__(
        self,
        base_url: str,
        *,
        http_get: Any = None,
        request_timeout_seconds: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.http_get = http_get
        self.request_timeout_seconds = max(0.1, float(request_timeout_seconds))

    async def search(self, query: str, *, max_results: int = 10, **options: Any) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": "json",
            "language": options.get("language", "auto"),
        }
        if options.get("categories"):
            params["categories"] = options["categories"]
        search_url = urljoin(self.base_url, "search") + "?" + urlencode(params)
        if self.http_get is None:
            return await _default_json_get(search_url, timeout_seconds=self.request_timeout_seconds)
        payload = self.http_get(search_url)
        if hasattr(payload, "__await__"):
            payload = await payload
        return normalize_search_provider_results(payload)[:max_results]


class DuckDuckGoInstantAnswerProvider:
    """Zero-config public provider for installation smoke and starter UX."""

    def __init__(
        self,
        *,
        http_get: Any = None,
        request_timeout_seconds: float = 10.0,
    ):
        self.http_get = http_get
        self.request_timeout_seconds = max(0.1, float(request_timeout_seconds))

    async def search(self, query: str, *, max_results: int = 10, **options: Any) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "1",
        }
        search_url = "https://api.duckduckgo.com/?" + urlencode(params)
        if self.http_get is None:
            payload = await _default_json_get(search_url, timeout_seconds=self.request_timeout_seconds)
        else:
            payload = self.http_get(search_url)
            if hasattr(payload, "__await__"):
                payload = await payload
        return normalize_search_provider_results(payload)[:max_results]


async def _default_json_get(url: str, *, timeout_seconds: float = 10.0) -> Any:
    import urllib.request

    def load() -> Any:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - user-configured endpoint
            import json

            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(load)


def normalize_search_provider_results(raw: Any) -> list[dict[str, Any]]:
    """Map common live-search provider payloads into title/url/snippet hits."""
    if raw is None:
        return []
    normalized: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        if (
            raw.get("AbstractText")
            or raw.get("AbstractURL")
            or raw.get("Heading")
            or raw.get("RelatedTopics")
        ):
            normalized.extend(_normalize_duckduckgo_instant_answer(raw))
        candidates = raw.get("results") or raw.get("web", {}).get("results") or raw.get("items") or raw.get("data")
    else:
        candidates = raw
    if not isinstance(candidates, list):
        return normalized

    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or item.get("headline")
        url = item.get("url") or item.get("link") or item.get("href")
        snippet = item.get("content") or item.get("snippet") or item.get("description") or item.get("summary")
        if not (title or url or snippet):
            continue
        normalized.append(
            {
                "title": title or url or "",
                "url": url or "",
                "snippet": snippet or "",
                "published_at": item.get("publishedDate") or item.get("published_at") or item.get("date"),
                "confidence": item.get("score", item.get("confidence", 0.5)),
                "raw": item,
            }
        )
    return normalized


def _normalize_duckduckgo_instant_answer(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    heading = raw.get("Heading") or raw.get("AbstractSource") or "DuckDuckGo instant answer"
    abstract = raw.get("AbstractText") or raw.get("Abstract") or ""
    abstract_url = raw.get("AbstractURL") or ""
    if heading or abstract or abstract_url:
        rows.append(
            {
                "title": heading,
                "url": abstract_url,
                "snippet": abstract,
                "confidence": 0.48,
                "raw": {"provider": "duckduckgo_instant_answer"},
            }
        )
    for topic in raw.get("RelatedTopics") or []:
        if not isinstance(topic, dict):
            continue
        nested_topics = topic.get("Topics")
        if isinstance(nested_topics, list):
            for nested in nested_topics:
                if isinstance(nested, dict):
                    rows.extend(_duckduckgo_topic_to_rows(nested))
            continue
        rows.extend(_duckduckgo_topic_to_rows(topic))
    return rows


def _duckduckgo_topic_to_rows(topic: dict[str, Any]) -> list[dict[str, Any]]:
    text = topic.get("Text") or topic.get("Result") or ""
    url = topic.get("FirstURL") or ""
    if not (text or url):
        return []
    title = str(text).split(" - ", 1)[0][:120] or url
    return [
        {
            "title": title,
            "url": url,
            "snippet": text,
            "confidence": 0.42,
            "raw": {"provider": "duckduckgo_related_topic"},
        }
    ]


async def public_web_results_to_standardized_records(
    query: str,
    results: list[dict[str, Any]],
    *,
    fetcher: Any = None,
    fetch_contents: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    fetch_contents = fetch_contents or {}
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or query).strip()
        url = normalize_public_url(str(item.get("url") or item.get("link") or "").strip())
        snippet = str(item.get("snippet") or item.get("summary") or item.get("content") or "").strip()
        if not title and not snippet and not url:
            continue
        dedupe_key = public_web_dedupe_key(title=title, url=url, snippet=snippet)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        fetched = await fetch_public_web_content(url, fetcher=fetcher, fetch_contents=fetch_contents)
        confidence = _clamp(item.get("confidence", item.get("score", 0.45)))
        if fetched["ok"]:
            confidence = min(1.0, confidence + 0.1)
        cognition_claims = public_web_cognition_claims(
            query=query,
            title=title,
            snippet=snippet,
            fetched_preview=str(fetched.get("content_preview") or ""),
        )
        public_entities = public_web_people_entities(
            query=query,
            title=title,
            snippet=snippet,
            fetched_preview=str(fetched.get("content_preview") or ""),
        )
        records.append(
            {
                "source_name": "public_web_search",
                "source_type": "search_engine",
                "dedupe_key": dedupe_key,
                "entity": str(item.get("entity") or query),
                "title": title or query,
                "summary": snippet,
                "url": url,
                "published_at": item.get("published_at") or item.get("date"),
                "confidence": confidence,
                "entities": public_entities,
                "evidence": [
                    {"claim": "Public web-search result requires URL-level verification."},
                    *([{"claim": snippet}] if snippet else []),
                    *[{"claim": claim} for claim in cognition_claims],
                    *(
                        [{"claim": f"URL-level fetch verified public page content: {fetched['content_preview']}"}]
                        if fetched["ok"] and fetched.get("content_preview")
                        else []
                    ),
                ],
                "url_verification": fetched,
                "raw": item,
            }
        )
    return records


def public_web_cognition_claims(
    *,
    query: str,
    title: str,
    snippet: str,
    fetched_preview: str = "",
) -> list[str]:
    """Extract conservative industry/product leads from public web text.

    These claims are not authority by themselves. The investigation packet only
    promotes them when the evidence row has exact/strong subject resolution.
    """
    text = " ".join(str(item or "") for item in (title, snippet, fetched_preview)).strip()
    if not text:
        return []
    if not _looks_subject_specific(query, title, text):
        return []

    industry = _public_web_industry_label(text)
    product = _public_web_product_label(text)
    customer_value = _public_web_customer_value(text)
    product_signals = _public_web_product_signals(text)
    industry_signals = _public_web_industry_signals(text)
    supply_chain_signals = _public_web_supply_chain_signals(text)
    capital_signals = _public_web_capital_signals(text)
    market_position_signals = _public_web_market_position_signals(text)
    business_model_signals = _public_web_business_model_signals(text)
    people_signals = _public_web_people_claim_signals(text)
    claims: list[str] = []
    if industry:
        signal_text = "; ".join(industry_signals)
        claims.append(
            "Public web industry lead: "
            f"industry={industry}; sources=public web title/snippet/fetch preview"
            + (f"; {signal_text}" if signal_text else "")
        )
    if product:
        product_parts = [
            f"product={product}",
            f"customer_value={customer_value or 'publicly described offering'}",
            *product_signals,
            "sources=public web title/snippet/fetch preview",
        ]
        claims.append(
            "Public web product lead: "
            + "; ".join(product_parts)
        )
    if supply_chain_signals:
        claims.append(
            "Public web supply-chain lead: "
            + "; ".join([*supply_chain_signals, "sources=public web title/snippet/fetch preview"])
        )
    # Supplier concentration
    sc_signals = _public_web_supplier_concentration_signals(text)
    if sc_signals:
        claims.append(
            "Public web supplier-concentration lead: "
            + "; ".join([*sc_signals, "sources=public web title/snippet/fetch preview"])
        )
    # Customer concentration
    substitution_risk_signals = _public_web_substitution_risk_signals(text)
    pd_signals = _public_web_product_dependency_signals(text)
    ue_signals = _public_web_unit_economics_signals(text)
    if ue_signals:
        claims.append("Public web unit-economics lead: " + "; ".join([*ue_signals, "sources=public web title/snippet/fetch preview"]))
    if pd_signals:
        claims.append("Public web product-dependency lead: " + "; ".join([*pd_signals, "sources=public web title/snippet/fetch preview"]))
    if substitution_risk_signals:
        claims.append("Public web substitution-risk lead: " + "; ".join([*substitution_risk_signals, "sources=public web title/snippet/fetch preview"]))
    cc_signals = _public_web_customer_concentration_signals(text)
    if cc_signals:
        claims.append(
            "Public web customer-concentration lead: "
            + "; ".join([*cc_signals, "sources=public web title/snippet/fetch preview"])
        )
    if market_position_signals:
        claims.append(
            "Public web market-position lead: "
            + "; ".join([*market_position_signals, "sources=public web title/snippet/fetch preview"])
        )
    if business_model_signals:
        claims.append(
            "Public web business-model lead: "
            + "; ".join([*business_model_signals, "sources=public web title/snippet/fetch preview"])
        )
    if capital_signals:
        claims.append(
            "Public web capital lead: "
            + "; ".join([*capital_signals, "sources=public web title/snippet/fetch preview"])
        )
    if people_signals:
        claims.append(
            "Public web people lead: "
            + "; ".join([*people_signals, "sources=public web title/snippet/fetch preview"])
        )
    extra_text = " ".join([snippet, title, fetched_preview])
    for signal in _public_web_bond_signals(extra_text)[:3]:
        claims.append(f"Public web bond lead: {signal}; sources=public web title/snippet/fetch preview")
    for signal in _public_web_credit_signals(extra_text)[:3]:
        claims.append(f"Public web credit lead: {signal}; sources=public web title/snippet/fetch preview")
    for signal in _public_web_recruiting_signals(extra_text)[:3]:
        claims.append(f"Public web recruiting lead: {signal}; sources=public web title/snippet/fetch preview")
    for signal in _public_web_market_structure_signals(extra_text)[:3]:
        claims.append(f"Public web market-structure lead: {signal}; sources=public web title/snippet/fetch preview")
    for signal in _public_web_procurement_signals(extra_text)[:3]:
        claims.append(f"Public web procurement lead: {signal}; sources=public web title/snippet/fetch preview")
    for signal in _public_web_annual_report_signals(extra_text)[:3]:
        claims.append(f"Public web annual-report lead: {signal}; sources=public web title/snippet/fetch preview")
    # Commercial: tax/trade/procurement/annual-report signals
    for s in _public_web_tax_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"commercial-tax={s}")
    for s in _public_web_trade_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"commercial-trade={s}")
    for s in _public_web_procurement_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"commercial-procurement={s}")
    for s in _public_web_annual_report_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"financial-annual={s}")
    for s in _public_web_policy_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"policy-regulatory={s}")
    for s in _public_web_competitor_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"competitor={s}")
    for s in _public_web_switching_cost_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"switching-cost={s}")
    for s in _public_web_upstream_power_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"upstream-power={s}")
    for s in _public_web_downstream_power_signals(" ".join([snippet, title]))[:2]:
        if _looks_subject_specific(snippet, title, query):
            claims.append(f"downstream-power={s}")
    return claims


def public_web_people_entities(
    *,
    query: str,
    title: str,
    snippet: str,
    fetched_preview: str = "",
) -> list[dict[str, Any]]:
    text = " ".join(str(item or "") for item in (title, snippet, fetched_preview)).strip()
    if not text or not _looks_subject_specific(query, title, text):
        return []
    entities: list[dict[str, Any]] = []
    for relation, name in _public_web_people_pairs(text):
        entities.append(
            {
                "kind": "person",
                "name": name,
                "relation": relation,
                "confidence": 0.62,
                "extraction": "public_web_role_pattern",
            }
        )
    return _dedupe_public_entities(entities)[:8]


def _looks_subject_specific(query: str, title: str, text: str) -> bool:
    query_tokens = {
        token
        for token in _tokenize_companyish(query)
        if token not in {"inc", "ltd", "limited", "co", "company", "corp", "corporation", "group"}
    }
    if not query_tokens:
        return False
    title_tokens = set(_tokenize_companyish(title))
    text_tokens = set(_tokenize_companyish(text))
    return bool(query_tokens & title_tokens) or len(query_tokens & text_tokens) >= min(2, len(query_tokens))


def _tokenize_companyish(raw: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", str(raw or "").lower())
        if len(token) >= 2
    ]


def _public_web_industry_label(text: str) -> str | None:
    clean = text.lower()
    cn = str(text or "")
    patterns = (
        ("manufacturing", ("manufacturing", "factory", "production line", "assembly", "工业制造", "工厂", "生产", "制造")),
        ("logistics_and_supply_chain", ("logistics", "supply chain", "warehousing", "freight", "物流", "仓储", "运输", "供应链")),
        ("education_and_training", ("education", "training", "e-learning", "academic", "教育", "培训", "在线教育")),
        ("agriculture_and_food", ("agriculture", "farming", "food processing", "livestock", "农业", "食品", "养殖")),
        ("telecom_and_networks", ("telecommunications", "telecom", "networking", "5g", "broadband", "通信", "电信", "网络")),
        ("media_and_entertainment", ("media", "entertainment", "streaming", "gaming", "content", "媒体", "娱乐", "游戏")),
        ("construction_and_real_estate", ("construction", "real estate", "property", "infrastructure", "建筑", "房地产", "基建")),

        ("technology", ("technology company", "software", "cloud", "artificial intelligence", "ai platform")),
        ("industrial equipment", ("industrial equipment", "precision equipment", "machinery", "pump", "manufacturing equipment")),
        ("financial services", ("bank", "insurance", "asset management", "brokerage", "fintech")),
        ("life sciences", ("pharmaceutical", "biotechnology", "medical device", "healthcare")),
        ("automotive", ("automotive", "electric vehicle", "automobile", "mobility")),
        ("energy", ("energy", "solar", "wind power", "oil and gas", "battery storage")),
        ("retail", ("retail", "e-commerce", "consumer goods", "marketplace")),
        ("real estate", ("real estate", "property developer", "commercial property")),
    )
    for label, keywords in patterns:
        matched = False
        for keyword in keywords:
            if len(keyword) <= 4 and keyword.isascii() and keyword.isalpha():
                # Use word boundary for short acronyms (avoid substring matches like erp in counterparty)
                if re.search(r'\b' + re.escape(keyword) + r'\b', clean):
                    matched = True
                    break
            elif keyword in clean:
                matched = True
                break
        if matched:
            return label
    return None


def _public_web_product_label(text: str) -> str | None:
    clean = text.lower()
    cn = str(text or "")
    patterns = (
        ("payment_platform", ("payment platform", "payment gateway", "payment processing", "支付", "收单", "结算")),
        ("enterprise_software", ("enterprise software", "business software", "企业软件", "erp系统", "企业管理")),
        ("logistics_platform", ("logistics platform", "delivery platform", "freight platform", "物流平台", "配送", "快递")),
        ("industrial_machinery", ("industrial machine", "heavy machinery", "precision tool", "manufacturing line", "工业设备", "机械")),
        ("semiconductor_chip", ("semiconductor", "chip", "integrated circuit", "wafer", "芯片", "半导体", "集成电路")),
        ("new_energy", ("solar panel", "wind turbine", "battery system", "energy storage", "光伏", "风电", "储能", "新能源")),
        ("pharmaceutical", ("pharmaceutical", "drug", "biologic", "medicine", "药品", "制药", "生物药")),
        ("consumer_goods", ("consumer goods", "household", "apparel", "food product", "消费品", "日用品", "食品")),

        ("risk intelligence platform", ("risk intelligence platform", "counterparty risk", "due diligence platform")),
        ("ai platform", ("ai platform", "artificial intelligence platform", "machine learning platform")),
        ("cloud software", ("cloud software", "saas", "software platform")),
        ("industrial pump", ("precision pump", "industrial pump", "pump system")),
        ("electric vehicle", ("electric vehicle", "ev model", "battery electric")),
        ("medical device", ("medical device", "diagnostic device", "implant")),
    )
    for label, keywords in patterns:
        if any(keyword in clean for keyword in keywords):
            return label
    return None


def _public_web_customer_value(text: str) -> str | None:
    clean = text.lower()
    if "mission-critical" in clean or "mission critical" in clean:
        if "compliance" in clean or "risk" in clean:
            return "mission-critical compliance or risk workflow support"
        return "mission-critical workflow support"
    if "compliance" in clean and ("workflow" in clean or "teams" in clean):
        return "compliance workflow support"
    if "cost reduction" in clean or "reduce costs" in clean:
        return "cost reduction"
    if "automation" in clean and "workflow" in clean:
        return "workflow automation"
    if "efficiency" in clean or "productivity" in clean:
        return "efficiency_or_productivity"
    if "data" in clean and ("analytics" in clean or "insights" in clean):
        return "data_analytics_or_insights"
    if "security" in clean or "safety" in clean:
        return "security_or_safety"
    return None


def _public_web_product_signals(text: str) -> list[str]:
    clean = text.lower()
    signals: list[str] = []
    if "subscription" in clean or "saas" in clean:
        signals.append("subscription_revenue_ratio=subscription_or_saas_model_publicly_described")
    if "embedded" in clean and "workflow" in clean:
        signals.append("switching_cost=0.6")
    if "mission-critical" in clean or "mission critical" in clean:
        signals.append("switching_cost=0.6")
    return list(dict.fromkeys(signals))


def _public_web_industry_signals(text: str) -> list[str]:
    clean = text.lower()
    cn = str(text or "")
    signals: list[str] = []
    if "saas" in clean or "software platform" in clean or "cloud software" in clean or "软件平台" in cn:
        signals.append("value_chain_role=software_platform")
    if "oem" in clean:
        signals.append("value_chain_role=oem")
    if "distributor" in clean or "经销商" in cn or "分销" in cn:
        signals.append("value_chain_role=distributor")
    if "manufacturer" in clean or "生产" in cn or "制造" in cn:
        signals.append("value_chain_role=manufacturer")
    if "supplier concentration" in clean or "供应商集中" in cn:
        signals.append("supplier_power=0.7")
    if "enterprise customers" in clean or "large customers" in clean or "企业客户" in cn:
        signals.append("customer_power=0.6")
    if "competition" in clean or "competitive" in clean or "竞争" in cn:
        signals.append("competitive_pressure=publicly_described")
    if any(term in clean for term in ("rapid growth", "fast growing", "expanding market", "growing demand", "快速增长", "增长迅速")):
        signals.append("industry_growth=high")
    if "policy risk" in clean or "regulatory" in clean or "政策风险" in cn or "监管" in cn:
        signals.append("policy_risk=publicly_described")
    if "substitution" in clean or "替代" in cn:
        signals.append("substitution_risk=publicly_described")
    return list(dict.fromkeys(signals))[:8]

def _public_web_supply_chain_signals(text: str) -> list[str]:
    signals: list[str] = []
    # Customer references (English)
    for value in _extract_public_web_list(text, (
        r"\bcustomers?\s+(?:include|includes|included|are|such as)\s+([^.;]+)",
        r"\btop customers?\s*(?:include|includes|:)\s+([^.;]+)",
    )):
        signals.append(f"customer={value}")
    # Customer references (Chinese)
    for value in _extract_public_web_list(text, (
        r"客户(?:包括|有|为|主要)\s*([^；。，]+)",
        r"主要客户\s*(?:包括|有|为|:)\s*([^；。，]+)",
    )):
        signals.append(f"customer={value}")
    # Supplier references (English)
    for value in _extract_public_web_list(text, (
        r"\bsuppliers?\s+(?:include|includes|included|are|such as)\s+([^.;]+)",
        r"\btop suppliers?\s*(?:include|includes|:)\s+([^.;]+)",
    )):
        signals.append(f"supplier={value}")
    # Supplier references (Chinese)
    for value in _extract_public_web_list(text, (
        r"供应商(?:包括|有|为|主要)\s*([^；。，]+)",
        r"主要供应商\s*(?:包括|有|为|:)\s*([^；。，]+)",
    )):
        signals.append(f"supplier={value}")
    # Partner references (English)
    for value in _extract_public_web_list(text, (
        r"\bpartners?\s+(?:include|includes|included|are)\s+([^.;]+)",
        r"\bpartners?\s+with\s+([^.;]+)",
    )):
        signals.append(f"partner={value}")
    # Partner references (Chinese)
    for value in _extract_public_web_list(text, (
        r"合作(?:伙伴|方)(?:包括|有|为)\s*([^；。，]+)",
    )):
        signals.append(f"partner={value}")
    # Dealer / distributor references (English)
    for value in _extract_public_web_list(text, (
        r"\bdealers?\s+(?:include|includes|included|are)\s+([^.;]+)",
        r"\bdistributors?\s+(?:include|includes|included|are)\s+([^.;]+)",
    )):
        signals.append(f"distributor={value}")
    # Dealer / distributor references (Chinese)
    for value in _extract_public_web_list(text, (
        r"经销商(?:包括|有|为|主要)\s*([^；。，]+)",
        r"代理商(?:包括|有|为|主要)\s*([^；。，]+)",
    )):
        signals.append(f"distributor={value}")
    # Channel / sales channel references
    for value in _extract_public_web_list(text, (
        r"\b(?:sales channels?|distribution channels?|channel partners?)\s+(?:include|includes|are|:)\s+([^.;]+)",
    )):
        signals.append(f"channel={value}")
    for value in _extract_public_web_list(text, (
        r"销售渠道(?:包括|有|为)\s*([^；。，]+)",
        r"渠道(?:伙伴|商)(?:包括|有|为)\s*([^；。，]+)",
    )):
        signals.append(f"channel={value}")
    # Upstream / downstream (English)
    upstream = _extract_public_web_phrase(text, r"\bupstream(?:\s+(?:inputs|materials|suppliers|exposure))?\s*(?:include|includes|is|are|:)?\s+([^.;]+)")
    if upstream:
        signals.append(f"upstream={upstream}")
    downstream = _extract_public_web_phrase(text, r"\bdownstream(?:\s+(?:markets|customers|applications|exposure))?\s*(?:include|includes|is|are|:)?\s+([^.;]+)")
    if downstream:
        signals.append(f"downstream={downstream}")
    # Upstream / downstream (Chinese)
    upstream_cn = _extract_public_web_phrase(text, r"[上][游](?:\s*(?:原材料|供应商|产业|环节))?\s*(?:包括|有|为|:)?\s*([^；。，]+)")
    if upstream_cn and upstream_cn not in [s.split('=', 1)[-1] for s in signals if s.startswith('upstream=')]:
        signals.append(f"upstream={upstream_cn}")
    downstream_cn = _extract_public_web_phrase(text, r"[下][游](?:\s*(?:市场|客户|产业|环节))?\s*(?:包括|有|为|:)?\s*([^；。，]+)")
    if downstream_cn and downstream_cn not in [s.split('=', 1)[-1] for s in signals if s.startswith('downstream=')]:
        signals.append(f"downstream={downstream_cn}")
    # Concentration (English)
    if "customer concentration" in text.lower():
        signals.append(f"customer_concentration={_public_web_ratio_signal(text, 'customer concentration')}")
    if "supplier concentration" in text.lower():
        signals.append(f"supplier_concentration={_public_web_ratio_signal(text, 'supplier concentration')}")
    # Concentration (Chinese)
    cn_lowered = text.lower() if text else ""
    if "客户集中" in cn_lowered or "客户集中度" in cn_lowered:
        signals.append(f"customer_concentration={_public_web_ratio_signal(text, '客户集中')}")
    if "供应商集中" in cn_lowered or "供应商集中度" in cn_lowered:
        signals.append(f"supplier_concentration={_public_web_ratio_signal(text, '供应商集中')}")
    return list(dict.fromkeys(signals))[:12]

def _public_web_market_position_signals(text: str) -> list[str]:
    """Extract market share / position / competitive standing signals. Lead-only."""
    clean = str(text or "")
    lowered = clean.lower()
    signals: list[str] = []
    # Market share / leadership (English)
    if re.search(r"\bmarket share\b", lowered):
        share = _public_web_ratio_signal(text, 'market share')
        signals.append(f"market_share={share}")
    if re.search(r"\bmarket leader\b|\bindustry leader\b|\bleading player\b|\bdominant position\b", lowered):
        signals.append("market_position=market_leader_or_dominant")
    if re.search(r"\btop \d+\b", lowered) and re.search(r"\b(company|supplier|manufacturer|player)\b", lowered):
        signals.append("market_position=top_ranked")
    if re.search(r"\b(market position|competitive advantage|competitive landscape|market presence)\b", lowered):
        signals.append("market_position=publicly_described")
    # Market share / leadership (Chinese)
    if re.search(r"市场份额|市占率|市场占有率", clean):
        share = _public_web_ratio_signal(text, r'市场(?:份额|占有率|占率)')
        signals.append(f"market_share={share}")
    if re.search(r"行业龙头|行业领先|头部企业|领先地位|市场主导", clean):
        signals.append("market_position=market_leader_or_dominant")
    if re.search(r"市场份额排名|行业排名第|全国第", clean):
        signals.append("market_position=top_ranked")
    return list(dict.fromkeys(signals))[:6]

def _public_web_business_model_signals(text: str) -> list[str]:
    """Extract business model / revenue model / sales model signals. Lead-only."""
    clean = str(text or "")
    lowered = clean.lower()
    signals: list[str] = []
    # Sales / go-to-market model (English)
    if re.search(r"\b(b2b|business.to.business|enterprise sales)\b", lowered):
        signals.append("sales_model=b2b")
    if re.search(r"\b(b2c|business.to.consumer|direct.to.consumer|d2c)\b", lowered):
        signals.append("sales_model=b2c_or_d2c")
    if re.search(r"\b(b2b2c|platform business|marketplace|two.sided)\b", lowered):
        signals.append("business_model=platform_or_marketplace")
    if re.search(r"\bdirect sales\b|\bonline sales\b|\be.commerce\b", lowered):
        signals.append("sales_channel=direct_or_online")
    if re.search(r"\bchannel sales\b|\bindirect sales\b|\breseller\b", lowered):
        signals.append("sales_channel=indirect_or_channel")
    # Revenue model (English)
    if re.search(r"\b(subscription|saas|recurring revenue|annual recurring|arr)\b", lowered):
        signals.append("revenue_model=subscription_or_saas")
    if re.search(r"\b(transaction fee|commission|take rate|markup)\b", lowered):
        signals.append("revenue_model=transaction_or_commission")
    if re.search(r"\b(advertising|ad.revenue|ad supported)\b", lowered):
        signals.append("revenue_model=advertising")
    if re.search(r"\b(licensing|license fee|software license)\b", lowered):
        signals.append("revenue_model=licensing")
    # Business model (Chinese)
    if re.search(r"商业模式|盈利模式|营收模式", clean):
        signals.append("business_model=publicly_described")
    if re.search(r"直销|线上销售|电商|电子商务", clean):
        signals.append("sales_channel=direct_or_online")
    if re.search(r"经销商模式|代理模式|分销模式", clean):
        signals.append("sales_channel=indirect_or_channel")
    if re.search(r"订阅|会员费|年费|saas", clean):
        signals.append("revenue_model=subscription_or_saas")
    if re.search(r"佣金|抽成|交易费|服务费", clean):
        signals.append("revenue_model=transaction_or_commission")
    return list(dict.fromkeys(signals))[:8]
def _public_web_customer_concentration_signals(text: str) -> list[str]:
    signals: list[str] = []
    lowered = str(text or "").lower()
    ratio = None
    import re
    m = re.search(r"(?:customer concentration|customer concentration ratio|client concentration|客户集中度)\D{0,40}(\d+(?:\.\d+)?)\s*%", lowered)
    if m:
        ratio = float(m.group(1)) / 100.0
        signals.append(f"customer_concentration={ratio:.2f}" if ratio < 1 else f"customer_concentration=publicly_described")
    if "top customer" in lowered or "top client" in lowered or "客户集中" in str(text or ""):
        if not signals:
            signals.append("customer_concentration=publicly_described")
    return list(dict.fromkeys(signals))[:4]




def _public_web_court_specific(text: str, query: str) -> list[str]:
    lowered = (text or "").lower()
    signals = []
    if re.search(r"(被执行人|失信被执行人|debtor|被执行|执行标的)", lowered):
        signals.append("enforcement_subject=publicly_described")
    if re.search(r"(执行标的|execution amount|执行金额)\D{0,30}(\d[\d,.]*)", lowered):
        m=re.search(r"(执行标的|execution amount|执行金额)\D{0,30}(\d[\d,.]*)", lowered)
        if m: signals.append(f"execution_amount={m.group(2)}")
    return signals[:5]

def _public_web_supplier_concentration_signals(text: str) -> list[str]:
    """Detect supplier concentration signals from public web text."""
    signals: list[str] = []
    lowered = str(text or "").lower()
    m = re.search(r"(?:supplier concentration|supplier concentration ratio|供应商集中度)\D{0,40}(\d+(?:\.\d+)?)\s*%", lowered)
    if m:
        ratio = float(m.group(1)) / 100.0
        signals.append(f"supplier_concentration={ratio:.2f}")
    if "top supplier" in lowered or "供应商集中" in str(text or ""):
        if not signals:
            signals.append("supplier_concentration=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_substitution_risk_signals(text: str) -> list[str]:
    clean = str(text or "")
    lowered = clean.lower()
    signals: list[str] = []
    if re.search(
        r"\b(substitution risk|substitute product|alternative product|disruption risk|disruptive technology)\b",
        lowered,
    ) or re.search(r"替代风险|被替代|颠覆性", clean):
        signals.append("substitution_risk=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_product_dependency_signals(text: str) -> list[str]:
    signals=[]
    lowered=str(text or "").lower()
    if re.search(r"\\b(single product|single customer|product dependency|product concentration|产品单一|依赖单一)",lowered):
        signals.append("product_dependency=publicly_described")
    if re.search(r"(\\d+)\\s*%\\s*(of revenue|of sales|from one|from single|来自单一)",lowered):
        signals.append("product_dependency=publicly_described")
    return signals[:4]



_PAGE_TYPE_PATTERNS: list[tuple[str,str]] = [
    ("annual_report","年度报告|annual report|年报|季报|半年报|10-K|10-Q|financial statements|财报"),
    ("procurement","招标|中标|采购公告|procurement|tender|bid notice"),
    ("court_enforcement","执行裁定|被执行人|失信被执行人|court order|enforcement notice|被执行"),
    ("official_company","公司简介|about us|company profile|企业简介|官网首页|official website"),
    ("industry_report","行业分析|行业报告|industry report|market report|市场报告"),
    ("credit_event","违约公告|评级调整|credit default|rating alert|债券公告|兑付公告"),
]

def _classify_page_type(title: str, snippet: str) -> str:
    text = f"{title or ''} {snippet or ''}"
    for ptype, pattern in _PAGE_TYPE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ptype
    return "general"
def _public_web_unit_economics_signals(text: str) -> list[str]:
    signals=[]
    lowered=str(text or "").lower()
    en = r"\b(unit economics|lifetime value|customer acquisition cost|ltv/cac|ltv:cac|gross margin|contribution margin)\b"
    cn = r"(单位经济|毛利率|边际贡献|用户生命周期价值|获客成本)"
    if re.search(en,lowered) or re.search(cn,str(text or "")):
        signals.append("unit_economics=publicly_described")
    return signals[:4]



def _public_web_market_structure_signals(text: str) -> list[str]:
    """Extract market structure signals: concentration, competitiveness, barriers."""
    lowered = str(text or "").lower()
    signals = []
    hhi_match = re.search(r"(?:hhi|herfindahl)\D{0,30}(\d{3,5})", lowered)
    if hhi_match:
        hhi = int(hhi_match.group(1))
        level = "high" if hhi > 2500 else "moderate" if hhi > 1500 else "low"
        signals.append(f"market_concentration=hhi_{level}:{hhi}")
    # HHI reference
    m = re.search(r"(?:HHI|Herfindahl|赫芬达尔|市场集中度)\D{0,30}(\d{3,5})", lowered)
    if m:
        hhi = int(m.group(1))
        level = "high" if hhi > 2500 else "moderate" if hhi > 1500 else "low"
        signals.append(f"market_concentration=hhi_{level}:{hhi}")
    # Competitive landscape
    if re.search(r"(fragmented|分散|竞争激烈|highly competitive|many players)", lowered):
        signals.append("competitive_landscape=fragmented")
    if re.search(r"(consolidated|集中|oligopoly|寡头|few players)", lowered):
        signals.append("competitive_landscape=consolidated")
    # Barriers to entry
    if re.search(r"(barriers? to entry|entry barriers?|准入门槛|进入壁垒|capital intensive|资本密集)", lowered):
        signals.append("entry_barriers=publicly_described")
    # Price/capacity cycle
    if re.search(r"(overcapacity|产能过剩|price war|价格战|supply glut)", lowered):
        signals.append("capacity_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:6]


def _public_web_bond_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(default|违约|debt default|债券违约|利息逾期)", lowered):
        signals.append("bond_default=publicly_described")
    m = re.search(r"(bond amount|债券规模|发行规模|发行金额)\D{0,40}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"bond_amount={m.group(2)}")
    if re.search(r"(rating downgrade|评级下调|评级负面|negative outlook|credit watch)", lowered):
        signals.append("bond_rating_negative=publicly_described")
    return list(dict.fromkeys(signals))[:6]

def _public_web_credit_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(credit line|授信|credit facility|credit rating|信用评级|credit risk|信用风险)", lowered):
        signals.append("credit_obligation=publicly_described")
    m = re.search(r"(credit amount|授信额度|credit limit|贷款额度)\D{0,40}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"credit_amount={m.group(2)}")
    if re.search(r"(non-performing|不良贷款|坏账|坏帐|overdue|逾期|NPL)", lowered):
        signals.append("credit_quality_concern=publicly_described")
    return list(dict.fromkeys(signals))[:6]

def _public_web_recruiting_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(hiring|招聘|recruiting|大量招人|扩招|岗位|职位)", lowered):
        signals.append("recruiting_active=publicly_described")
    if re.search(r"(layoff|裁员|downsizing|缩减|人员优化)", lowered):
        signals.append("headcount_reduction=publicly_described")
    m = re.search(r"(招聘|hiring|岗位|职位)\D{0,40}(\d+)\s*(人|位)", lowered)
    if m: signals.append(f"headcount_scale={m.group(2)}")
    if re.search(r"(salary|薪资|薪酬|工资|compensation)\D{0,20}(increase|增长|提高|上调|涨)", lowered):
        signals.append("wage_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:6]


def _public_web_procurement_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(中标|winning bid|中标单位|winning bidder|中标人)", lowered):
        signals.append("winning_bid=publicly_described")
    m = re.search(r"(中标金额|bid amount|中标价|合同金额)\D{0,40}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"bid_amount={m.group(2)}")
    if re.search(r"(政府采?购|government procurement|public procurement|公开招标)", lowered):
        signals.append("government_procurement=publicly_described")
    m = re.search(r"(招标编号|bid number|项目编号)\D{0,20}([A-Za-z0-9\-_]+)", lowered)
    if m: signals.append(f"bid_reference={m.group(2)}")
    return list(dict.fromkeys(signals))[:6]


def _public_web_annual_report_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    m = re.search(r"(?:revenue|营收|营业收入|收入)\D{0,40}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"revenue_amount={m.group(1)}")
    m = re.search(r"(?:net profit|净利润|净利)\D{0,40}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"profit_amount={m.group(1)}")
    if re.search(r"(?:yoy growth|同比增长|year-over-year|同比)", lowered):
        signals.append("yoy_growth=publicly_described")
    if re.search(r"(?:audit opinion|审计意见|auditor|审计)", lowered):
        signals.append("audit_opinion=publicly_described")
    return list(dict.fromkeys(signals))[:6]


def _public_web_tax_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(tax credit|税收优惠|tax incentive|tax break|退税)", lowered):
        signals.append("tax_benefit=publicly_described")
    if re.search(r"(tax penalty|税务处罚|tax audit|税务稽查|tax investigation|偷税|漏税)", lowered):
        signals.append("tax_risk=publicly_described")
    m = re.search(r"(tax rate|税率|effective tax rate|实际税负)\D{0,20}(\d+[\.]?\d*)\s*%", lowered)
    if m: signals.append("tax_rate=" + m.group(2) + "%")
    return list(dict.fromkeys(signals))[:5]

def _public_web_trade_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(export|出口|exports?)\D{0,30}(increase|增长|rise|上升)", lowered):
        signals.append("export_growth=publicly_described")
    if re.search(r"(import|进口|imports?)\D{0,30}(increase|增长|rise|上升)", lowered):
        signals.append("import_growth=publicly_described")
    if re.search(r"(tariff|关税|trade barrier|贸易壁垒|贸易摩擦)", lowered):
        signals.append("trade_barrier_risk=publicly_described")
    if re.search(r"(customs|海关|customs clearance|报关)", lowered):
        signals.append("customs_activity=publicly_described")
    return list(dict.fromkeys(signals))[:5]


def _public_web_policy_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(policy change|政策变化|regulation|监管|regulatory|新规|法规)", lowered):
        signals.append("regulatory_change=publicly_described")
    if re.search(r"(anti-monopoly|反垄断|antitrust|反不正当竞争)", lowered):
        signals.append("antitrust_risk=publicly_described")
    if re.search(r"(environmental|环境|环保|ESG|碳排放|carbon emission)", lowered):
        signals.append("environmental_regulation=publicly_described")
    if re.search(r"(data privacy|数据安全|data security|个人信息保护|cybersecurity)", lowered):
        signals.append("data_regulation=publicly_described")
    return list(dict.fromkeys(signals))[:5]


def _public_web_switching_cost_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(switching cost|转换成本|high retention|高留存|高粘性)", lowered):
        signals.append("high_switching_cost=publicly_described")
    if re.search(r"(repeat purchase|复购|recurring revenue|续费|subscription renewal)", lowered):
        signals.append("repeat_purchase=publicly_described")
    if re.search(r"(lock.?in|锁定|vendor lock|平台锁定)", lowered):
        signals.append("vendor_lock_in=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_downstream_power_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(customer concentration|客户集中|buyer power|买方议价|大客户依赖)", lowered):
        signals.append("customer_concentration_risk=publicly_described")
    if re.search(r"(price sensitive|价格敏感|price elasticity|议价能力)", lowered):
        signals.append("price_sensitivity=publicly_described")
    if re.search(r"(distribution channel|销售渠道|channel power|渠道集中)", lowered):
        signals.append("channel_dependency=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_upstream_power_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(supplier concentration|供应商集中|supplier power|卖方议价|供应商依赖)", lowered):
        signals.append("supplier_concentration_risk=publicly_described")
    if re.search(r"(raw material|原材料|commodity price|大宗商品|原料价格)", lowered):
        signals.append("raw_material_pressure=publicly_described")
    if re.search(r"(supply shortage|供应短缺|supply chain disruption|供应链中断)", lowered):
        signals.append("supply_chain_disruption=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_competitor_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    m = re.search(r"(?:competitors?|竞争对?手|主要竞争者|peer group|对标)\s*(?:include|包括|including|:)?\s*([A-Za-z\u4e00-\u9fff·., ]{3,80})", lowered)
    if m: signals.append(f"competitor_mentioned={m.group(1).strip()[:60]}")
    if re.search(r"(market leader|行业龙头|leading|第一大|首位)", lowered):
        signals.append("market_position=leader")
    if re.search(r"(challenger|挑战者|追赶|second place|第二)", lowered):
        signals.append("market_position=challenger")
    return list(dict.fromkeys(signals))[:4]


def _public_web_customer_concentration_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    m = re.search(r"(?:customer concentration|客户集中度|top\s*\d+\s*customer|前\d+\s*客户|largest customer)\D{0,40}(\d+(?:\.\d+)?)\s*%", lowered)
    if m: signals.append(f"customer_concentration_ratio={float(m.group(1))/100:.2f}")
    if re.search(r"(revenue concentration|收入集中|reliance on few|少数客户依赖)", lowered):
        signals.append("revenue_concentration_risk=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_pricing_power_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(pricing power|定价权|price setter|价格制定|涨价|price increase)", lowered):
        signals.append("pricing_power=publicly_described")
    if re.search(r"(margin expansion|毛利率提升|margin improvement|利润改善)", lowered):
        signals.append("margin_expansion=publicly_described")
    if re.search(r"(premium pricing|高端定价|brand premium|品牌溢价)", lowered):
        signals.append("brand_premium=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_market_size_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    m = re.search(r"(?:market size|市场规模|TAM|total addressable market|市场容量)\D{0,40}(\d[\d,.]*)\s*(万亿|亿|百万|billion|million|trillion)", lowered)
    if m: signals.append(f"market_size={m.group(1)}{m.group(2)}")
    if re.search(r"(growing market|增长市场|rapid growth|高速增长|CAGR|复合增长)", lowered):
        signals.append("market_growth=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_peer_comparison_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(peer comparison|同行比较|industry average|行业平均|sector benchmark)", lowered):
        signals.append("peer_comparison=publicly_described")
    if re.search(r"(outperform|跑赢|beat sector|优于同行|领先行业)", lowered):
        signals.append("outperform_peers=publicly_described")
    if re.search(r"(underperform|跑输|lag sector|落后同行|低于行业)", lowered):
        signals.append("underperform_peers=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_solvency_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    m = re.search(r"(?:debt ratio|debt-to-equity|负债率|资产负债率|leverage ratio|杠杆率)\D{0,30}(\d+(?:\.\d+)?)\s*%", lowered)
    if m: signals.append(f"debt_ratio={m.group(1)}%")
    if re.search(r"(interest coverage|利息保障|利息覆盖率|ICR|debt service)", lowered):
        signals.append("debt_service_concern=publicly_described")
    if re.search(r"(refinancing risk|refinance risk|再融资风险|rollover risk)", lowered):
        signals.append("refinancing_risk=publicly_described")
    if re.search(r"(short-term debt|短期债务|current portion|一年内到期)", lowered):
        signals.append("short_term_debt_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:5]


def _public_web_governance_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(board change|董事会变更|board reshuffle|管理层变更|management change)", lowered):
        signals.append("board_or_mgmt_change=publicly_described")
    if re.search(r"(independent director|独立董事|独立非执行|outside director)", lowered):
        signals.append("independent_director_mentioned=publicly_described")
    if re.search(r"(related party loan|关联方借款|related party guarantee|关联担保|资金占用)", lowered):
        signals.append("related_party_financing=publicly_described")
    if re.search(r"(accounting issue|会计问题|financial restatement|财务重述|审计问题|audit issue)", lowered):
        signals.append("accounting_concern=publicly_described")
    return list(dict.fromkeys(signals))[:5]


def _public_web_equity_pledge_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(equity pledge|股权质押|share pledge|股票质押|股份质押)", lowered):
        signals.append("equity_pledge=publicly_described")
    m = re.search(r"(pledge ratio|质押比例|质押率)\D{0,20}(\d+(?:\.\d+)?)\s*%", lowered)
    if m: signals.append(f"pledge_ratio={m.group(1)}%")
    if re.search(r"(margin call|平仓|追加保证金|margin pressure|爆仓)", lowered):
        signals.append("pledge_margin_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_industry_lifecycle_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(emerging industry|新兴|nascent|early stage|早期|startup phase)", lowered):
        signals.append("lifecycle=emerging")
    if re.search(r"(growth phase|增长期|expansion|扩张期|快速成长)", lowered):
        signals.append("lifecycle=growth")
    if re.search(r"(mature|成熟|成熟期|saturated|饱和)", lowered):
        signals.append("lifecycle=mature")
    if re.search(r"(decline|衰退|declining|夕阳|shrink)", lowered):
        signals.append("lifecycle=decline")
    return list(dict.fromkeys(signals))[:3]


def _public_web_working_capital_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(working capital|营运资金|营运资本|流动资金|operating cash)", lowered):
        signals.append("working_capital=publicly_described")
    if re.search(r"(cash conversion|现金转换|CCC|cash cycle|资金周转)", lowered):
        signals.append("cash_conversion=publicly_described")
    if re.search(r"(inventory days|库存天数|DSO|days sales|应收账款天数|DPO|应付账款)", lowered):
        signals.append("working_capital_efficiency=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_ownership_transfer_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(ownership transfer|股权转让|equity transfer|股份转让|控制权变更|change of control)", lowered):
        signals.append("ownership_transfer=publicly_described")
    if re.search(r"(stake sale|出售股权|sell stake|减持|exit)", lowered):
        signals.append("stake_disposal=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_capex_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(capital expenditure|资本支出|capex|资本开支|投资支出)", lowered):
        signals.append("capex=publicly_described")
    if re.search(r"(expansion plan|扩产|expansion project|扩建|新项目|new facility|新工厂)", lowered):
        signals.append("expansion_plans=publicly_described")
    if re.search(r"(R&D|研发|research and development|创新投入|技术投入)", lowered):
        signals.append("rd_investment=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_goodwill_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(goodwill impairment|商誉减值|goodwill write.?down|商誉)", lowered):
        signals.append("goodwill_risk=publicly_described")
    if re.search(r"(intangible asset|无形资产|intangible impairment)", lowered):
        signals.append("intangible_impairment=publicly_described")
    if re.search(r"(acquisition premium|溢价收购|overpay|高溢价)", lowered):
        signals.append("acquisition_premium=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_ipo_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(IPO|initial public offering|首次公开发行|上市申请|listing|挂牌)", lowered):
        signals.append("ipo_status=publicly_described")
    if re.search(r"(pre-IPO|pre.?ipo|上市前|pre.?listing)", lowered):
        signals.append("pre_ipo=publicly_described")
    m = re.search(r"(?:valuation|估值|market cap|市值)\D{0,30}(\d[\d,.]*)\s*(万亿|亿|百万|billion|million|trillion)", lowered)
    if m: signals.append(f"valuation={m.group(1)}{m.group(2)}")
    return list(dict.fromkeys(signals))[:4]


def _public_web_logistics_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(logistics|物流|warehouse|仓储|distribution center|配送)", lowered):
        signals.append("logistics_mentioned=publicly_described")
    if re.search(r"(inventory buildup|库存积压|inventory write.?down|存货减值|excess stock)", lowered):
        signals.append("inventory_risk=publicly_described")
    if re.search(r"(shipping cost|运输成本|freight|运费|物流成本)", lowered):
        signals.append("logistics_cost_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_regulatory_penalty_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(fine|罚款|penalty|处罚|civil penalty|行政处罚)", lowered):
        signals.append("regulatory_penalty=publicly_described")
    if re.search(r"(license revoked|吊销|license suspend|暂停|执照|许可证)", lowered):
        signals.append("license_action=publicly_described")
    m = re.search(r"(?:fine amount|罚款金额|penalty amount|处罚金额)\D{0,30}(\d[\d,.]*[万亿]?)", lowered)
    if m: signals.append(f"penalty_amount={m.group(2)}")
    return list(dict.fromkeys(signals))[:4]


def _public_web_tech_innovation_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(patent filing|专利申请|patent application|new patent|专利授权)", lowered):
        signals.append("patent_activity=publicly_described")
    if re.search(r"(technology breakthrough|技术突破|innovation|创新|disruptive|颠覆)", lowered):
        signals.append("tech_breakthrough=publicly_described")
    if re.search(r"(AI|artificial intelligence|人工智能|machine learning|深度学习|blockchain|区块链)", lowered):
        signals.append("emerging_tech=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_insurance_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(insurance claim|保险理赔|insurance coverage|保险覆盖|insured|已投保)", lowered):
        signals.append("insurance_mentioned=publicly_described")
    if re.search(r"(underinsured|不足额投保|uninsured|未投保|insurance gap)", lowered):
        signals.append("insurance_gap=publicly_described")
    if re.search(r"(catastrophe risk|巨灾风险|force majeure|不可抗力)", lowered):
        signals.append("catastrophe_exposure=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_legal_dispute_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(lawsuit|诉讼|litigation|控告|被告|原告|plaintiff|defendant)", lowered):
        signals.append("litigation_pending=publicly_described")
    if re.search(r"(class action|集体诉讼|representative action|集团诉讼)", lowered):
        signals.append("class_action=publicly_described")
    if re.search(r"(settlement|和解|settlement agreement|调解)", lowered):
        signals.append("settlement=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_cybersecurity_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(cyber attack|网络攻击|data breach|数据泄露|hack|黑客|ransomware)", lowered):
        signals.append("cyber_incident=publicly_described")
    if re.search(r"(cyber security|网?络安全|information security|信息安全|data protection)", lowered):
        signals.append("cyber_compliance=publicly_described")
    if re.search(r"(personal data|个人数据|个人信息|privacy violation|隐私)", lowered):
        signals.append("privacy_concern=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_bank_exposure_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(bank exposure|银行风险敞口|bank counterparty|银行交易对手|creditor bank|债权银行)", lowered):
        signals.append("bank_exposure=publicly_described")
    if re.search(r"(syndicated loan|银团贷款|syndicate|loan syndication)", lowered):
        signals.append("syndicated_loan=publicly_described")
    if re.search(r"(lender concentration|贷款集中|lender risk|银行集中度)", lowered):
        signals.append("lender_concentration=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_subsidiary_risk_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(subsidiary risk|子公司风险|子公司|affiliate risk|关联公司风险)", lowered):
        signals.append("subsidiary_mentioned=publicly_described")
    if re.search(r"(guarantee for subsidiary|为子公司担保|cross guarantee|交叉担保)", lowered):
        signals.append("subsidiary_guarantee=publicly_described")
    if re.search(r"(subsidiary default|子公司违约|off.?balance.?sheet entity|表外实体)", lowered):
        signals.append("subsidiary_distress=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_fraud_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(fraud|欺诈|fraud investigation|诈骗|financial fraud|财务造假)", lowered):
        signals.append("fraud_risk=publicly_described")
    if re.search(r"(whistleblower|举报|whistle.?blowing|内幕爆料)", lowered):
        signals.append("whistleblower=publicly_described")
    if re.search(r"(regulatory investigation|监管调查|regulatory probe|证监会调查|SEC investigation)", lowered):
        signals.append("regulatory_probe=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_operational_risk_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(business continuity|业务连续性|BCP|disaster recovery|灾备|灾难恢复)", lowered):
        signals.append("business_continuity=publicly_described")
    if re.search(r"(operational failure|运营故障|system outage|系统中断|outage|停机)", lowered):
        signals.append("operational_outage=publicly_described")
    if re.search(r"(key person risk|关键人风险|key man|succession risk|继任风险)", lowered):
        signals.append("key_person_risk=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_sentiment_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(positive outlook|正面展望|strong buy|买入|bullish|看好|optimistic)", lowered):
        signals.append("sentiment=positive")
    if re.search(r"(negative outlook|负面展望|sell|卖出|bearish|看空|pessimistic|悲观)", lowered):
        signals.append("sentiment=negative")
    if re.search(r"(analyst downgrade|分析师下调|target cut|目标下调|rating downgrade)", lowered):
        signals.append("analyst_downgrade=publicly_described")
    if re.search(r"(analyst upgrade|分析师上调|target raise|目标上调|rating upgrade)", lowered):
        signals.append("analyst_upgrade=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_labor_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(labor dispute|劳动争议|罢工|strike|劳资纠纷|labor union|工会)", lowered):
        signals.append("labor_dispute=publicly_described")
    if re.search(r"(employee lawsuit|员工诉讼|wrongful termination|非法解雇|discrimination|歧视)", lowered):
        signals.append("employee_litigation=publicly_described")
    if re.search(r"(wage arrears|欠薪|工资拖欠|unpaid wages|salary dispute)", lowered):
        signals.append("wage_arrears=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_carbon_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(carbon neutral|碳中和|carbon emission|碳排放|net.?zero|零碳)", lowered):
        signals.append("carbon_neutral_commitment=publicly_described")
    if re.search(r"(carbon tax|碳税|emission trading|碳交易|carbon credit)", lowered):
        signals.append("carbon_regulation=publicly_described")
    if re.search(r"(ESG score|ESG评级|ESG rating|sustainability|可持续)", lowered):
        signals.append("esg_disclosure=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_contract_risk_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(contract expiration|合同到期|contract renewal|续约|contract termination|合同终止)", lowered):
        signals.append("contract_risk=publicly_described")
    if re.search(r"(long.?term contract|长期合同|长期协议|strategic partnership|战略合作)", lowered):
        signals.append("long_term_contract=publicly_described")
    if re.search(r"(revenue backlog|在手订单|order backlog|合同负债|contract liability)", lowered):
        signals.append("order_backlog=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_geopolitical_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(geopolitical|地缘政治|trade war|贸易战|sanctions?|制裁|export control|出口管制)", lowered):
        signals.append("geopolitical_risk=publicly_described")
    if re.search(r"(supply chain decoupling|供应链脱钩|reshoring|制造业回流|nearshoring)", lowered):
        signals.append("supply_chain_decoupling=publicly_described")
    if re.search(r"(currency risk|汇率风险|FX risk|外汇风险|devaluation|贬值)", lowered):
        signals.append("currency_risk=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_litigation_funding_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(litigation funding|诉讼融资|litigation finance|legal funding|第三方资助)", lowered):
        signals.append("litigation_funding=publicly_described")
    if re.search(r"(contingent liability|或有负债|contingent obligation|off.?balance.?sheet liability)", lowered):
        signals.append("contingent_liability=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_business_model_signals2(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(subscription model|订阅模式|SaaS|software as a service|platform model|平台模式)", lowered):
        signals.append("business_model=subscription_or_platform")
    if re.search(r"(asset.?heavy|重资产|capital.?intensive|资本密集|manufacturing model|制造模式)", lowered):
        signals.append("business_model=asset_heavy")
    if re.search(r"(asset.?light|轻资产|franchise|特许经营|licensing model|授权模式)", lowered):
        signals.append("business_model=asset_light")
    return list(dict.fromkeys(signals))[:3]


def _public_web_brand_value_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(brand value|品牌价值|brand equity|brand ranking|品牌排名|top brand)", lowered):
        signals.append("brand_value=publicly_described")
    if re.search(r"(brand damage|品牌损害|reputation damage|声誉损害|brand crisis)", lowered):
        signals.append("brand_damage=publicly_described")
    if re.search(r"(consumer complaint|消费者投诉|customer complaint|客户投诉|质量投诉)", lowered):
        signals.append("consumer_complaint=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_strategic_alliance_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(joint venture|合资|strategic alliance|战略联盟|partnership|合作|collaboration)", lowered):
        signals.append("strategic_alliance=publicly_described")
    if re.search(r"(cross.?shareholding|交叉持股|mutual shareholding|互相持股)", lowered):
        signals.append("cross_shareholding=publicly_described")
    if re.search(r"(technology transfer|技术转让|IP licensing|知识产权许可|technology licensing)", lowered):
        signals.append("technology_transfer=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_macro_economic_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(interest rate|利率|rate hike|加息|rate cut|降息|monetary policy|货币政策)", lowered):
        signals.append("interest_rate_exposure=publicly_described")
    if re.search(r"(inflation|通胀|deflation|通缩|CPI|PPI|物价)", lowered):
        signals.append("inflation_exposure=publicly_described")
    if re.search(r"(GDP growth|经济增长|economic slowdown|经济放缓|recession|衰退)", lowered):
        signals.append("macro_growth_exposure=publicly_described")
    return list(dict.fromkeys(signals))[:4]


def _public_web_related_party_loan_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(related party loan|关联方借款|关联企业借款|fund diversion|资金占用|intercorporate loan)", lowered):
        signals.append("related_party_loan=publicly_described")
    if re.search(r"(tunnelling|掏空|tunneling|asset stripping|资产转移|利益输送)", lowered):
        signals.append("tunnelling_risk=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_off_balance_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(off.?balance.?sheet|表外|off balance|off-balance|SPV|special purpose vehicle)", lowered):
        signals.append("off_balance_sheet=publicly_described")
    if re.search(r"(structured finance|结构化融资|securitization|资产证券化|ABS|asset.?backed)", lowered):
        signals.append("structured_finance=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_revenue_recognition_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    signals=[]
    if re.search(r"(revenue recognition|收入确认|revenue manipulation|收入操纵|channel stuffing|渠道压货|bill.?and.?hold)",lowered):
        signals.append("revenue_recognition_risk=publicly_described")
    if re.search(r"(premature revenue|提前确认收入|aggressive accounting|激进会计|round.?tripping|循环交易)",lowered):
        signals.append("aggressive_accounting=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_impairment_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    signals=[]
    if re.search(r"(impairment|减值|write.?down|减记|asset impairment|资产减值)",lowered):
        signals.append("asset_impairment=publicly_described")
    if re.search(r"(inventory write.?down|存货跌价|receivable impairment|坏账计提|loan loss provision|拨备)",lowered):
        signals.append("provision_risk=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_employee_benefit_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(pension deficit|养老金缺口|pension obligation|退休金|retiree benefit|员工福利)",lowered):s.append("pension_obligation=publicly_described")
    if re.search(r"(stock option|股权激励|ESOP|期权|stock compensation|股份支付)",lowered):s.append("equity_compensation=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_government_subsidy_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(government subsidy|政府补贴|government grant|财政补贴|补贴收入|tax refund|退税)",lowered):s.append("govt_subsidy=publicly_described")
    if re.search(r"(subsidy dependence|补贴依赖|reliance on subsidy|靠补贴)",lowered):s.append("subsidy_dependence=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_product_quality_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(product recall|产品召回|product defect|产品缺陷|quality issue|质量问题|quality failure)",lowered):s.append("product_quality_issue=publicly_described")
    if re.search(r"(safety incident|安全事故|safety violation|安全违规|product safety|产品安全)",lowered):s.append("safety_incident=publicly_described")
    if re.search(r"(certification revoked|认证撤销|quality certification|质量认证|ISO|GMP)",lowered):s.append("certification_status=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_customer_churn_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(customer churn|客户流失|customer loss|client departure|customer attrition)",lowered):s.append("customer_churn=publicly_described")
    if re.search(r"(contract non.?renewal|合同不续|non.?renewal|未续约)",lowered):s.append("contract_nonrenewal=publicly_described")
    if re.search(r"(NPS|net promoter|净推荐值|CSAT|customer satisfaction|客户满意度)",lowered):s.append("customer_satisfaction=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_share_buyback_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(share buyback|股票回购|share repurchase|buy.?back program|回购计划)",lowered):s.append("share_buyback=publicly_described")
    if re.search(r"(treasury stock|库存股|cancellation of shares|注销股份|capital reduction|减资)",lowered):s.append("capital_reduction=publicly_described")
    if re.search(r"(dividend|分红|dividend payout|派息|股息)",lowered):s.append("dividend_policy=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_warranty_liability_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(warranty claim|质保索赔|warranty liability|质保负债|product warranty|产品保修)",lowered):s.append("warranty_liability=publicly_described")
    if re.search(r"(warranty reserve|质保准备金|warranty expense|保修费用)",lowered):s.append("warranty_reserve=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_lease_obligation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(lease liability|租赁负债|lease obligation|租赁义务|operating lease|经营租赁)",lowered):s.append("lease_liability=publicly_described")
    if re.search(r"(sale.?leaseback|售后回租|leaseback|售后租回)",lowered):s.append("sale_leaseback=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_debt_covenant_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(debt covenant|债务契约|covenant breach|违反契约|financial covenant|财务契约)",lowered):s.append("covenant_breach=publicly_described")
    if re.search(r"(covenant waiver|契约豁免|waiver request|豁免申请|covenant relaxation)",lowered):s.append("covenant_waiver=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_credit_rating_migration_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(rating downgrade|评级下调|credit rating downgrade|negative rating action)",lowered):s.append("rating_downgrade=publicly_described")
    if re.search(r"(watch negative|负面观察|credit watch negative|outlook negative|展望负面)",lowered):s.append("credit_watch_negative=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_cross_guarantee_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(cross guarantee|交叉担保|cross.?default|交叉违约|mutual guarantee|互相担保)",lowered):s.append("cross_guarantee=publicly_described")
    if re.search(r"(guarantee circle|担保圈|互保圈|guarantee chain|担保链)",lowered):s.append("guarantee_circle=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_contingent_equity_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(convertible bond|可转债|convertible note|可转换债券|CB|convertible debt)",lowered):s.append("convertible_debt=publicly_described")
    if re.search(r"(warrant|认股权证|stock warrant|权证|dilution risk|稀释)",lowered):s.append("dilution_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_financial_restatement_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(financial restatement|财务重述|restated financial|restated accounts|restatement)",lowered):s.append("restatement=publicly_described")
    if re.search(r"(accounting error|会计差错|accounting irregularity|会计违规|material weakness|重大缺陷)",lowered):s.append("accounting_weakness=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_intellectual_property_dispute_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(IP dispute|知识产权纠纷|IP infringement|知识产权侵权|patent infringement|专利侵权)",lowered):s.append("ip_dispute=publicly_described")
    if re.search(r"(trade secret|商业秘密|IP theft|知识产权窃取|IP litigation|知识产权诉讼)",lowered):s.append("trade_secret_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_government_relation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(government contract|政府合同|government procurement|政府采购|govt contract|政府项目)",lowered):s.append("government_contract=publicly_described")
    if re.search(r"(SOE|国有企业|state.?owned|国有|state enterprise|央企)",lowered):s.append("soe_connection=publicly_described")
    if re.search(r"(corruption investigation|腐败调查|graft|贪污|bribery|贿赂|anti.?corruption)",lowered):s.append("corruption_risk=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_management_turnover_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(CEO departure|CEO离职|CEO resignation|总经理辞职|CFO departure|财务总监离职)",lowered):s.append("key_executive_departure=publicly_described")
    if re.search(r"(management turnover|管理层变动|senior management change|高管变动)",lowered):s.append("management_turnover=publicly_described")
    if re.search(r"(succession planning|继任计划|succession risk|继任风险)",lowered):s.append("succession_concern=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_industry_disruption_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(disruption|颠覆|disruptive technology|颠覆性技术|industry disruption|行业颠覆)",lowered):s.append("disruption_risk=publicly_described")
    if re.search(r"(digital transformation|数字化转型|digitization|数字化|AI disruption|AI颠覆)",lowered):s.append("digital_transformation=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_regulatory_compliance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(compliance failure|合规失败|compliance breach|违反合规|regulatory breach|违反监管)",lowered):s.append("compliance_breach=publicly_described")
    if re.search(r"(license requirement|牌照要求|permit|许可证|regulatory approval|监管审批)",lowered):s.append("regulatory_approval_required=publicly_described")
    if re.search(r"(AML|anti.?money laundering|反洗钱|KYC|know your customer|尽职调查|compliance program)",lowered):s.append("aml_compliance=publicly_described")
    return list(dict.fromkeys(s))[:4]



def _public_web_competitor_set_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    s = []
    if re.search(r"(competitor|竞争对手|rival|競爭對手|peer group|同行)", lowered):
        s.append("competitor_set=publicly_mentioned")
    if re.search(r"(market leader|市场领导者|market challenger|挑战者|market share|市场份额)", lowered):
        s.append("competitive_position=publicly_described")
    if re.search(r"(new entrant|新进入者|disruptor|颠覆者|market consolidation|市场整合)", lowered):
        s.append("competitive_dynamics=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_substitution_risk_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    s = []
    if re.search(r"(substitut|替代|代替|replaceable|switching cost|转换成本|switching_cost)", lowered):
        s.append("substitution_risk=publicly_described")
    if re.search(r"(alternative product|替代产品|alternative technology|替代技术|generic|通用替代)", lowered):
        s.append("substitute_availability=publicly_described")
    if re.search(r"(customer switching|客户迁移|churn risk|流失风险|switching barrier|转换壁垒)", lowered):
        s.append("switching_behavior=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_capacity_cycle_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    s = []
    if re.search(r"(capacity expansion|产能扩张|capacity addition|新增产能|overcapacity|产能过剩)", lowered):
        s.append("capacity_cycle=publicly_described")
    if re.search(r"(capacity utilization|产能利用率|utilization rate|开工率|price cycle|价格周期)", lowered):
        s.append("capacity_utilization=publicly_described")
    if re.search(r"(supply glut|供过于求|supply shortage|供不应求|inventory buildup|库存积压)", lowered):
        s.append("supply_demand_balance=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_switching_cost_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(switching cost|转换成本|migration cost|迁移成本|lock.?in|锁定效应|vendor lock)",lowered):s.append("switching_cost=publicly_described")
    if re.search(r"(high retention|高留存|low churn|低流失|sticky product|粘性产品)",lowered):s.append("customer_stickiness=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_moat_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(economic moat|经济护城河|competitive moat|竞争壁垒|wide moat|narrow moat)",lowered):s.append("moat=publicly_described")
    if re.search(r"(network effect|网络效应|scale advantage|规模优势|cost advantage|成本优势|intangible asset|无形资产壁垒)",lowered):s.append("moat_source=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_policy_cycle_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(policy change|政策变化|regulatory change|监管变化|new regulation|新规|policy shift)",lowered):s.append("policy_cycle=publicly_described")
    if re.search(r"(subsidy change|补贴变化|tax policy|税收政策|tariff change|关税变化|trade policy|贸易政策)",lowered):s.append("policy_risk=publicly_described")
    if re.search(r"(compliance deadline|合规期限|phase.?in|逐步实施|grandfather|过渡期)",lowered):s.append("compliance_timeline=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_procurement_tender_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(procurement|采购|tender|招标|bid|投标|government contract|政府合同)",lowered):s.append("procurement_tender=publicly_described")
    if re.search(r"(sole source|单一来源|competitive bid|竞标|winning bid|中标)",lowered):s.append("tender_competition=publicly_described")
    if re.search(r"(contract value|合同金额|procurement budget|采购预算|award notice|中标公告)",lowered):s.append("contract_value=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_environmental_liability_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(environmental liability|环境责任|pollution|污染|contamination|污染|cleanup cost|清理成本|remediation|修复)",lowered):s.append("environmental_liability=publicly_described")
    if re.search(r"(EPA|环保|environmental fine|环境罚款|emission violation|排放违规)",lowered):s.append("environmental_enforcement=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_insurance_actuarial_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(insurance risk|保险风险|actuarial|精算|underwriting risk|承保风险|claims ratio|赔付率)",lowered):s.append("insurance_actuarial=publicly_described")
    if re.search(r"(catastrophe risk|巨灾风险|cat bond|巨灾债券|reserve adequacy|准备金充足)",lowered):s.append("catastrophe_exposure=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_corporate_governance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(corporate governance|公司治理|board independence|董事会独立|audit committee|审计委员会|shareholder rights|股东权利)",lowered):s.append("corporate_governance=publicly_described")
    if re.search(r"(related party transaction|关联交易|self.?dealing|利益输送|tunneling|掏空)",lowered):s.append("governance_red_flag=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_data_breach_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(data breach|数据泄露|data leak|数据泄漏|cyber attack|网络攻击|ransomware|勒索软件)",lowered):s.append("data_breach=publicly_described")
    if re.search(r"(personal data|个人数据|privacy violation|隐私侵犯|GDPR|个人信息保护|data protection)",lowered):s.append("privacy_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_antitrust_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(antitrust|反垄断|anti.?competitive|反竞争|monopoly|垄断|cartel|卡特尔)",lowered):s.append("antitrust_risk=publicly_described")
    if re.search(r"(market dominance|市场支配|abuse of dominance|滥用支配|antitrust fine|反垄断罚款|competition authority|竞争监管)",lowered):s.append("antitrust_enforcement=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_trade_finance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(trade finance|贸易融资|letter of credit|信用证|LC|documentary collection|跟单托收|export credit|出口信贷)",lowered):s.append("trade_finance=publicly_described")
    if re.search(r"(trade credit insurance|贸易信用保险|forfaiting|福费廷|factoring|保理|receivable finance|应收账款融资)",lowered):s.append("trade_credit=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_supply_chain_finance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(supply chain finance|供应链金融|reverse factoring|反向保理|inventory finance|存货融资|payable finance|应付账款融资)",lowered):s.append("supply_chain_finance=publicly_described")
    if re.search(r"(supplier financing|供应商融资|distributor finance|经销商融资|channel finance|渠道融资)",lowered):s.append("channel_financing=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_brand_value_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(brand value|品牌价值|brand ranking|品牌排名|brand equity|品牌资产|trademark value|商标价值)",lowered):s.append("brand_value=publicly_described")
    if re.search(r"(brand damage|品牌损害|reputation risk|声誉风险|brand crisis|品牌危机)",lowered):s.append("brand_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_tech_innovation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(R&D|研发|research and development|innovation|创新|patent filing|专利申请|technology leadership|技术领先)",lowered):s.append("tech_innovation=publicly_described")
    if re.search(r"(R&D intensity|研发强度|R&D spending|研发支出|technology roadmap|技术路线|tech obsolescence|技术过时)",lowered):s.append("tech_investment=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_cac_ltv_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(customer acquisition cost|CAC|获客成本|LTV|life.?time value|客户终身价值|LTV.CAC)",lowered):s.append("cac_ltv=publicly_described")
    if re.search(r"(payback period|回收期|customer economics|客户经济学|unit economics|单位经济|cohort|用户群组)",lowered):s.append("unit_economics=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_revenue_model_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(subscription revenue|订阅收入|recurring revenue|经常性收入|ARR|MRR|annual recurring|monthly recurring)",lowered):s.append("subscription_model=publicly_described")
    if re.search(r"(transaction revenue|交易收入|advertising revenue|广告收入|freemium|免费增值|marketplace|平台交易)",lowered):s.append("revenue_model=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_cross_border_ma_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(cross.?border acquisition|跨境收购|overseas acquisition|海外收购|CFIUS|foreign investment review|外资审查)",lowered):s.append("cross_border_ma=publicly_described")
    if re.search(r"(national security review|国家安全审查|investment screening|投资审查|outbound M&A|对外并购)",lowered):s.append("investment_review=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_sovereign_debt_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(sovereign debt|主权债务|government bond|国债|sovereign bond|主权债券|treasury yield|国债收益率)",lowered):s.append("sovereign_debt=publicly_described")
    if re.search(r"(sovereign default|主权违约|debt restructuring|债务重组|Paris Club|巴黎俱乐部|IMF program|IMF项目)",lowered):s.append("sovereign_credit=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_crypto_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(cryptocurrency|加密货币|bitcoin|以太坊|digital asset|数字资产|crypto exchange|加密交易所|stablecoin|稳定币)",lowered):s.append("crypto_exposure=publicly_described")
    if re.search(r"(crypto loss|加密损失|crypto hack|加密黑客|wallet breach|钱包泄露|DeFi|去中心化金融)",lowered):s.append("crypto_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_commodity_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(commodity exposure|大宗商品敞口|commodity price|大宗价格|oil exposure|石油敞口|metal exposure|金属敞口|agricultural commodity|农产品)",lowered):s.append("commodity_exposure=publicly_described")
    if re.search(r"(commodity hedging|大宗套保|commodity derivative|商品衍生品|commodity shock|大宗冲击)",lowered):s.append("commodity_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_interest_rate_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(interest rate risk|利率风险|rate hike|加息|rate cut|降息|yield curve|收益率曲线|duration risk|久期风险)",lowered):s.append("interest_rate_risk=publicly_described")
    if re.search(r"(floating rate|浮动利率|fixed rate|固定利率|rate sensitivity|利率敏感|interest rate hedge|利率对冲)",lowered):s.append("rate_sensitivity=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_currency_peg_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(currency peg|货币挂钩|pegged currency|挂钩货币|fixed exchange|固定汇率|dollar peg|美元挂钩)",lowered):s.append("currency_peg=publicly_described")
    if re.search(r"(peg pressure|挂钩压力|devaluation risk|贬值风险|currency board|货币局|de-peg|脱钩)",lowered):s.append("peg_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_sanctions_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(sanctions|制裁|OFAC|制裁名单|asset freeze|资产冻结|trade embargo|贸易禁运|export control|出口管制)",lowered):s.append("sanctions_risk=publicly_described")
    if re.search(r"(sanctions violation|违反制裁|secondary sanctions|二级制裁|SDN list|特别指定名单|entity list|实体清单)",lowered):s.append("sanctions_enforcement=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_capital_controls_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(capital control|资本管制|capital flow restriction|资本流动限制|repatriation restriction|资金汇出限制|currency control|外汇管制)",lowered):s.append("capital_controls=publicly_described")
    if re.search(r"(capital account|资本账户|outflow restriction|流出限制|inflow control|流入管控|convertibility|可兑换)",lowered):s.append("convertibility_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_real_estate_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(real estate exposure|房地产敞口|property market|房地产市场|housing bubble|房地产泡沫|vacancy rate|空置率)",lowered):s.append("real_estate_risk=publicly_described")
    if re.search(r"(property developer|房地产开发商|REIT|房地产信托|mortgage stress|按揭压力|housing downturn|楼市下行)",lowered):s.append("property_market_stress=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_financial_sector_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(financial sector risk|金融行业风险|systemic risk|系统性风险|contagion|传染|financial stability|金融稳定)",lowered):s.append("financial_sector_risk=publicly_described")
    if re.search(r"(bank run|银行挤兑|liquidity crisis|流动性危机|credit crunch|信贷紧缩|shadow banking|影子银行)",lowered):s.append("systemic_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_leverage_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(high leverage|高杠杆|debt.?to.?EBITDA|debt burden|债务负担|over.?leveraged|过度杠杆|gearing|杠杆率)",lowered):s.append("leverage_risk=publicly_described")
    if re.search(r"(deleveraging|去杠杆|leverage ratio|杠杆比率|net debt|净债务|gross debt|总债务)",lowered):s.append("leverage_metrics=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_covenant_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(covenant breach|违反契约|covenant violation|契约违规|financial covenant|财务契约|debt covenant|债务契约|loan covenant|贷款契约)",lowered):s.append("covenant_risk=publicly_described")
    if re.search(r"(covenant waiver|契约豁免|technical default|技术性违约|covenant renegotiation|契约重新协商)",lowered):s.append("covenant_stress=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_water_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(water risk|水资源风险|water scarcity|水资源短缺|water stress|用水压力|drought risk|干旱风险)",lowered):s.append("water_risk=publicly_described")
    if re.search(r"(water permit|取水许可|wastewater|废水|water pollution|水污染|effluent|排放)",lowered):s.append("water_compliance=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_biodiversity_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(biodiversity|生物多样性|habitat loss|栖息地丧失|deforestation|森林砍伐|species risk|物种风险)",lowered):s.append("biodiversity_risk=publicly_described")
    if re.search(r"(conservation|保护|ecological impact|生态影响|natural capital|自然资本|ecosystem service|生态系统服务)",lowered):s.append("ecological_impact=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_community_relations_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(community relations|社区关系|social license|社会许可|stakeholder conflict|利益相关方冲突|local opposition|当地反对)",lowered):s.append("community_relations=publicly_described")
    if re.search(r"(land dispute|土地纠纷|resettlement|拆迁安置|indigenous rights|原住民权利|community protest|社区抗议)",lowered):s.append("social_license_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_labor_rights_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(labor rights|劳工权利|worker rights|工人权利|union|工会|collective bargaining|集体谈判|strike|罢工)",lowered):s.append("labor_rights=publicly_described")
    if re.search(r"(forced labor|强迫劳动|child labor|童工|wage theft|工资拖欠|unsafe condition|不安全条件|OSHA violation)",lowered):s.append("labor_violation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_executive_compensation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(executive compensation|高管薪酬|CEO pay|CEO薪酬|executive pay ratio|薪酬比|say.?on.?pay|薪酬投票)",lowered):s.append("executive_compensation=publicly_described")
    if re.search(r"(excessive compensation|过高薪酬|compensation clawback|薪酬追回|golden parachute|金色降落伞|equity grant|股权授予)",lowered):s.append("compensation_governance=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_board_diversity_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(board diversity|董事会多元化|gender diversity|性别多样性|board composition|董事会构成|independent director|独立董事)",lowered):s.append("board_diversity=publicly_described")
    if re.search(r"(board refreshment|董事会更新|director tenure|董事任期|overboarded|兼职过多|board skills|董事会技能)",lowered):s.append("board_governance=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_whistleblower_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(whistleblower|举报人|whistle.?blow|举报|internal report|内部举报|hotline|举报热线)",lowered):s.append("whistleblower_event=publicly_described")
    if re.search(r"(retaliation|报复|whistleblower protection|举报人保护|SEC whistleblower|SEC举报|Dodd.?Frank)",lowered):s.append("whistleblower_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_audit_quality_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(audit quality|审计质量|auditor change|审计师变更|going concern|持续经营|material weakness|重大缺陷|internal control|内部控制)",lowered):s.append("audit_quality=publicly_described")
    if re.search(r"(audit fee|审计费用|auditor independence|审计师独立性|restatement|重述|accounting irregularity|会计违规)",lowered):s.append("audit_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_social_media_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(social media risk|社交媒体风险|reputation crisis|声誉危机|viral negative|负面传播|online backlash|网络反弹|boycott|抵制)",lowered):s.append("social_media_risk=publicly_described")
    if re.search(r"(misinformation|错误信息|disinformation|虚假信息|fake account|虚假账号|bot campaign|机器人活动|influencer risk|网红风险)",lowered):s.append("information_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_ai_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(AI risk|人工智能风险|deepfake|深度伪造|algorithm bias|算法偏见|AI ethics|AI伦理|automation risk|自动化风险)",lowered):s.append("ai_risk=publicly_described")
    if re.search(r"(AI regulation|AI监管|model risk|模型风险|training data|训练数据|AI liability|AI责任|generative AI|生成式AI)",lowered):s.append("ai_governance=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_supply_chain_visibility_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(supply chain visibility|供应链可见性|traceability|可追溯|supply chain mapping|供应链图谱|tier.?N supplier|N级供应商)",lowered):s.append("supply_chain_visibility=publicly_described")
    if re.search(r"(supply chain disruption|供应链中断|single source|单一来源|sole source risk|独家供应风险|supply chain audit|供应链审计)",lowered):s.append("supply_chain_resilience=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_inventory_management_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(inventory management|库存管理|inventory turnover|库存周转|stockpile|囤货|inventory buildup|库存积压|inventory write.?down|存货跌价)",lowered):s.append("inventory_management=publicly_described")
    if re.search(r"(just.?in.?time|准时制|JIT|safety stock|安全库存|lead time|交货周期|inventory obsolescence|存货过时)",lowered):s.append("inventory_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_market_abuse_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(market abuse|市场滥用|insider trading|内幕交易|market manipulation|市场操纵|spoofing|幌骗|front.?running|抢先交易)",lowered):s.append("market_abuse=publicly_described")
    if re.search(r"(SEC investigation|SEC调查|FCA investigation|FCA调查|market surveillance|市场监控|trading suspension|停牌)",lowered):s.append("market_enforcement=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_extraterritorial_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(extraterritorial|域外管辖|long.?arm jurisdiction|长臂管辖|cross.?border enforcement|跨境执法|FCPA|反海外腐败|UK Bribery Act)",lowered):s.append("extraterritorial_risk=publicly_described")
    if re.search(r"(DOJ investigation|司法部调查|multi.?jurisdictional|多辖区|mutual legal assistance|司法互助|Interpol|国际刑警)",lowered):s.append("cross_border_enforcement=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_financial_reporting_quality_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(financial reporting|财务报告|earnings quality|盈利质量|revenue recognition|收入确认|aggressive accounting|激进会计|creative accounting|创造性会计)",lowered):s.append("reporting_quality=publicly_described")
    if re.search(r"(restatement|财务重述|material weakness|重大缺陷|internal control deficiency|内控缺陷|late filing|延迟申报|audit opinion|审计意见)",lowered):s.append("reporting_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_business_continuity_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(business continuity|业务连续性|disaster recovery|灾难恢复|pandemic risk|疫情风险|force majeure|不可抗力|supply disruption|供应中断)",lowered):s.append("business_continuity=publicly_described")
    if re.search(r"(BCP|业务连续性计划|redundancy|冗余|failover|故障转移|resilience|韧性|crisis management|危机管理)",lowered):s.append("continuity_readiness=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_pension_fund_status_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(pension fund|养老基金|pension deficit|养老金赤字|unfunded pension|未计提养老金|pension liability|养老金负债|retirement plan|退休计划)",lowered):s.append("pension_fund_status=publicly_described")
    if re.search(r"(pension underfunding|养老金不足|actuarial deficit|精算赤字|benefit obligation|福利义务|pension reform|养老金改革)",lowered):s.append("pension_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_derivative_valuation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(derivative valuation|衍生品估值|mark.?to.?market|市值计价|level.?3 asset|三级资产|fair value|公允价值|valuation uncertainty|估值不确定性)",lowered):s.append("derivative_valuation=publicly_described")
    if re.search(r"(derivative notional|衍生品名义金额|off.?balance.?sheet|表外|structured product|结构性产品|complex instrument|复杂工具)",lowered):s.append("off_balance_sheet_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_media_sentiment_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(media sentiment|媒体情绪|negative coverage|负面报道|positive coverage|正面报道|press scrutiny|媒体审查|investigative report|调查报道)",lowered):s.append("media_sentiment=publicly_described")
    if re.search(r"(media campaign|媒体运动|PR crisis|公关危机|spin|舆论引导|astroturf|虚假草根|influencer backlash|网红反弹)",lowered):s.append("media_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_event_driven_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(event risk|事件风险|black swan|黑天鹅|tail risk|尾部风险|force majeure|不可抗力|natural disaster|自然灾害)",lowered):s.append("event_driven_risk=publicly_described")
    if re.search(r"(terrorism|恐怖主义|civil unrest|内乱|political instability|政治不稳定|pandemic|大流行|supply shock|供给冲击)",lowered):s.append("extreme_event=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_carbon_pricing_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(carbon pricing|碳定价|carbon tax|碳税|carbon market|碳市场|ETS|排放交易|carbon credit|碳信用|offset|碳抵消)",lowered):s.append("carbon_pricing=publicly_described")
    if re.search(r"(carbon price|碳价格|EU.?ETS|欧盟碳交易|carbon border|碳边境|CBAM|碳边境调节|carbon leakage|碳泄漏)",lowered):s.append("carbon_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_green_bond_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(green bond|绿色债券|sustainability bond|可持续债券|ESG bond|ESG债券|social bond|社会债券|transition bond|转型债券)",lowered):s.append("green_bond=publicly_described")
    if re.search(r"(green bond framework|绿色债券框架|use of proceeds|资金用途|greenwashing|漂绿|second party opinion|第二方意见|green certification|绿色认证)",lowered):s.append("green_bond_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_aerospace_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(aerospace|航空航天|space industry|航天产业|satellite|卫星|defense contract|国防合同|ITAR|国际武器贸易条例|export control|出口管制)",lowered):s.append("aerospace_risk=publicly_described")
    if re.search(r"(space debris|太空碎片|launch failure|发射失败|defense budget|国防预算|geopolitical space|太空地缘)",lowered):s.append("space_security=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_maritime_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(maritime risk|海事风险|shipping risk|航运风险|port congestion|港口拥堵|vessel detention|船舶扣押|piracy|海盗)",lowered):s.append("maritime_risk=publicly_described")
    if re.search(r"(shipping route|航线|Suez Canal|苏伊士运河|Panama Canal|巴拿马运河|Malacca Strait|马六甲海峡|freight rate|运费)",lowered):s.append("shipping_disruption=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_biotech_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(biotech|生物技术|clinical trial|临床试验|FDA approval|FDA审批|drug pipeline|药品管线|patent cliff|专利悬崖|biosimilar|生物类似药)",lowered):s.append("biotech_risk=publicly_described")
    if re.search(r"(phase.?III|三期临床|drug safety|药品安全|recall|召回|regulatory setback|监管挫折|trial failure|试验失败)",lowered):s.append("drug_development_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_telecom_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(telecom infrastructure|电信基础设施|5G|spectrum auction|频谱拍卖|network security|网络安全|Huawei ban|华为禁令|equipment ban|设备禁令)",lowered):s.append("telecom_risk=publicly_described")
    if re.search(r"(fiber optic|光纤|broadband|宽带|universal service|普遍服务|net neutrality|网络中立|data localization|数据本地化)",lowered):s.append("telecom_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_nuclear_energy_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(nuclear energy|核能|nuclear power|核电|nuclear reactor|核反应堆|uranium|铀|nuclear safety|核安全|Fukushima|福岛)",lowered):s.append("nuclear_energy=publicly_described")
    if re.search(r"(nuclear waste|核废料|decommissioning|退役|nuclear regulatory|核监管|IAEA|国际原子能|NRC|核管理委员会)",lowered):s.append("nuclear_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_rare_earth_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(rare earth|稀土|critical mineral|关键矿产|lithium|锂|cobalt|钴|nickel supply|镍供应|semiconductor material|半导体材料)",lowered):s.append("rare_earth_risk=publicly_described")
    if re.search(r"(mineral dependency|矿产依赖|supply concentration|供应集中|export restriction|出口限制|mineral processing|矿产加工|resource nationalism|资源民族主义)",lowered):s.append("critical_mineral_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_sovereign_wealth_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(sovereign wealth|主权财富|SWF|sovereign fund|主权基金|state investment|国家投资|national wealth fund|国家财富基金)",lowered):s.append("sovereign_wealth=publicly_described")
    if re.search(r"(SWF investment|主权基金投资|strategic investment|战略投资|state.?owned fund|国有基金|foreign reserve|外汇储备投资)",lowered):s.append("swf_strategic=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_infrastructure_fund_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(infrastructure fund|基建基金|infra fund|基础设施基金|PPP|公私合营|infrastructure investment|基建投资|toll road|收费公路)",lowered):s.append("infrastructure_fund=publicly_described")
    if re.search(r"(infrastructure asset|基础设施资产|brownfield|棕地|greenfield|绿地|regulated asset|受监管资产|concession|特许经营)",lowered):s.append("infra_asset_class=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_microfinance_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(microfinance|小额信贷|microcredit|微型信贷|microloan|小额贷款|financial inclusion|普惠金融|MFI|小额信贷机构)",lowered):s.append("microfinance_risk=publicly_described")
    if re.search(r"(microfinance regulation|小额信贷监管|over.?indebtedness|过度负债|loan shark|高利贷|informal lending|民间借贷|peer.?to.?peer lending|P2P借贷)",lowered):s.append("microfinance_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_fintech_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(fintech|金融科技|digital payment|数字支付|neobank|数字银行|open banking|开放银行|blockchain finance|区块链金融|robo.?advisor|智能投顾)",lowered):s.append("fintech_risk=publicly_described")
    if re.search(r"(fintech regulation|金融科技监管|digital currency|数字货币|CBDC|央行数字货币|regtech|监管科技|API banking|API银行)",lowered):s.append("fintech_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_quantum_computing_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(quantum computing|量子计算|quantum supremacy|量子霸权|quantum encryption|量子加密|post.?quantum|后量子|quantum threat|量子威胁)",lowered):s.append("quantum_risk=publicly_described")
    if re.search(r"(quantum advantage|量子优势|quantum safe|量子安全|quantum key|量子密钥|QKD|量子密钥分发)",lowered):s.append("quantum_security=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_food_security_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(food security|粮食安全|food supply|粮食供应|food price|粮价|food crisis|粮食危机|staple food|主粮)",lowered):s.append("food_security=publicly_described")
    if re.search(r"(food inflation|食品通胀|agricultural yield|农业产量|crop failure|作物歉收|fertilizer supply|化肥供应|grain export|粮食出口)",lowered):s.append("food_supply_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_medical_device_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(medical device|医疗器械|FDA 510k|CE marking|CE认证|device recall|器械召回|implant|植入物|diagnostic|诊断)",lowered):s.append("medical_device_risk=publicly_described")
    if re.search(r"(device approval|器械审批|MDR|医疗器械法规|post.?market surveillance|上市后监管|adverse event|不良事件)",lowered):s.append("device_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_pharma_pricing_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(drug pricing|药品定价|pharma pricing|药品价格|price negotiation|价格谈判|reference pricing|参考定价|value.?based pricing|价值定价)",lowered):s.append("pharma_pricing=publicly_described")
    if re.search(r"(drug price control|药价管控|price cap|价格上限|compulsory license|强制许可|parallel import|平行进口|patent linkage|专利链接)",lowered):s.append("pricing_regulation=publicly_described")
    return list(dict.fromkeys(s))[:3]
def _public_web_working_hours_compliance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(overtime violation|超时用工|996|overtime|加班|working hours violation|工时违规)",lowered):s.append("overtime_risk=publicly_described")
    if re.search(r"(child labor|童工|forced labor|强迫劳动|labour rights|劳工权益)",lowered):s.append("labor_rights_violation=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_supply_chain_finance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(supply chain finance|供应链金融|SCF|reverse factoring|反向保理|receivable finance)",lowered):s.append("scf_activity=publicly_described")
    if re.search(r"(factoring|保理|invoice discounting|票据贴现|receivable discounting)",lowered):s.append("factoring=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_investor_relations_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(investor communication|投资者沟通|investor complaint|投资者投诉|shareholder activism|股东积极主义)",lowered):s.append("investor_pressure=publicly_described")
    if re.search(r"(proxy fight|委托书争夺|proxy contest|代理权争夺|hostile takeover|敌意收购)",lowered):s.append("proxy_contest=publicly_described")
    if re.search(r"(activist investor|激进投资者|hedge fund activism|对冲基金施压)",lowered):s.append("activist_pressure=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_natural_disaster_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(natural disaster|自然灾害|earthquake|地震|flood|洪水|typhoon|台风|extreme weather)",lowered):s.append("disaster_exposure=publicly_described")
    if re.search(r"(business interruption|业务中断|force majeure|不可抗力|supply disruption|供应中断)",lowered):s.append("business_interruption_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_credit_insurance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(credit insurance|信用保险|trade credit insurance|贸易信用保险|export credit|出口信用)",lowered):s.append("credit_insurance=publicly_described")
    if re.search(r"(receivable insurance|应收账款保险|credit guarantee|信用保证|credit enhancement)",lowered):s.append("credit_enhancement=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_commodity_price_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(commodity price|大宗商品价格|oil price|油价|metal price|金属价格|raw material cost)",lowered):s.append("commodity_exposure=publicly_described")
    if re.search(r"(hedging loss|对冲损失|derivative loss|衍生品损失|commodity derivatives)",lowered):s.append("commodity_hedging_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_market_manipulation_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(market manipulation|市场操纵|price manipulation|价格操纵|insider trading|内幕交易)",lowered):s.append("market_manipulation=publicly_described")
    if re.search(r"(stock manipulation|股价操纵|pump and dump|拉高出货|wash trading|虚假交易)",lowered):s.append("stock_manipulation=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_product_concentration_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    m=re.search(r"(?:product concentration|产品集中度|single product|单一产品|revenue from top|收入来自|product mix)\D{0,40}(\d+(?:\.\d+)?)\s*%",lowered)
    if m:s.append(f"product_concentration={float(m.group(1))/100:.2f}")
    if re.search(r"(single product risk|单一产品风险|over.?reliance on product|过度依赖)",lowered):s.append("single_product_dependency=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_strategic_dependence_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(single supplier|单一供应商|sole supplier|独家供应商|sole source|唯一来源)",lowered):s.append("sole_supplier_risk=publicly_described")
    if re.search(r"(single customer dependency|单一客户依赖|key customer risk|大客户依赖)",lowered):s.append("key_customer_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_social_controversy_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(social controversy|社会争议|public backlash|公众反对|consumer boycott|消费者抵制)",lowered):s.append("social_controversy=publicly_described")
    if re.search(r"(discrimination lawsuit|歧视诉讼|racism|种族歧视|gender discrimination|性别歧视)",lowered):s.append("discrimination_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_capital_structure_complexity_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(VIE structure|VIE结构|variable interest entity|协议控制|complex structure)",lowered):s.append("complex_structure=publicly_described")
    if re.search(r"(offshore structure|离岸结构|offshore entity|境外架构|SPV structure)",lowered):s.append("offshore_structure=publicly_described")
    if re.search(r"(pyramid structure|金字塔结构|multi.?layer holding|多层控股)",lowered):s.append("pyramid_structure=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_asset_quality_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(non.?performing asset|不良资产|NPA|non.?performing loan|NPL|problem asset)",lowered):s.append("nonperforming_asset=publicly_described")
    if re.search(r"(asset quality deterioration|资产质量恶化|asset quality decline)",lowered):s.append("asset_quality_deterioration=publicly_described")
    if re.search(r"(collateral value decline|抵押物贬值|collateral shortfall)",lowered):s.append("collateral_decline=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_earnings_quality_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(earnings quality|盈利质量|earnings manipulation|利润操纵|accrual quality|应计质量)",lowered):s.append("earnings_quality_concern=publicly_described")
    if re.search(r"(non.?recurring income|非经常性损益|one.?off gain|一次性收益|exceptional item)",lowered):s.append("nonrecurring_income=publicly_described")
    if re.search(r"(cash flow mismatch|现金流不匹配|earnings vs cash|利润与现金流差异)",lowered):s.append("cash_flow_mismatch=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_cash_management_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(cash shortage|现金短缺|cash crunch|现金流紧张|liquidity squeeze|流动性紧张)",lowered):s.append("cash_shortage=publicly_described")
    if re.search(r"(cash pooling|资金归集|cash concentration|资金集中|cash management)",lowered):s.append("cash_pooling=publicly_described")
    if re.search(r"(restricted cash|受限资金|frozen cash|冻结资金|cash restriction)",lowered):s.append("restricted_cash=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_business_restructuring_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(business restructuring|业务重组|corporate restructuring|公司重组|divestiture|剥离)",lowered):s.append("restructuring=publicly_described")
    if re.search(r"(spin.?off|分拆|carve.?out|分拆上市|demerger|分立)",lowered):s.append("spinoff=publicly_described")
    if re.search(r"(asset sale|资产出售|asset disposal|资产处置|non.?core asset)",lowered):s.append("asset_disposal=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_tax_controversy_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(tax dispute|税务争议|tax audit|税务稽查|tax investigation|税务调查)",lowered):s.append("tax_dispute=publicly_described")
    if re.search(r"(transfer pricing|转让定价|tax avoidance|避税|tax evasion|逃税)",lowered):s.append("transfer_pricing_risk=publicly_described")
    if re.search(r"(tax haven|避税天堂|offshore tax|离岸避税)",lowered):s.append("tax_haven_risk=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_related_party_guarantee_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(related party guarantee|关联方担保|connected party guarantee|关联担保|related guarantee)",lowered):s.append("related_guarantee=publicly_described")
    if re.search(r"(guarantee exposure|担保敞口|contingent guarantee|或有担保|guarantee commitment)",lowered):s.append("guarantee_exposure=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_consumer_credit_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(consumer credit|消费信贷|consumer loan|个人贷款|retail lending|零售贷款)",lowered):s.append("consumer_credit=publicly_described")
    if re.search(r"(consumer NPL|消费不良|consumer default|个人违约|retail NPL)",lowered):s.append("consumer_credit_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_regulatory_capital_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(regulatory capital|监管资本|capital adequacy|资本充足率|CAR|Tier 1|核心资本)",lowered):s.append("regulatory_capital=publicly_described")
    if re.search(r"(capital shortfall|资本缺口|capital deficiency|资本不足|undercapitalized)",lowered):s.append("capital_shortfall=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_export_credit_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(export credit|出口信贷|export financing|出口融资|buyer.s credit|买方信贷)",lowered):s.append("export_credit=publicly_described")
    if re.search(r"(export insurance|出口保险|sinosure|中信保|ECA|export credit agency)",lowered):s.append("export_insurance=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_refinancing_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(refinancing risk|再融资风险|rollover risk|滚动风险|refinance|再融资)",lowered):s.append("refinancing_risk=publicly_described")
    if re.search(r"(bond maturity wall|债券到期墙|maturity wall|集中到期|debt maturity)",lowered):s.append("maturity_wall=publicly_described")
    if re.search(r"(refinancing difficulty|再融资困难|refinancing gap|再融资缺口)",lowered):s.append("refinancing_difficulty=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_sovereign_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(sovereign risk|主权风险|sovereign default|主权违约|country risk|国别风险)",lowered):s.append("sovereign_risk=publicly_described")
    if re.search(r"(sovereign downgrade|主权评级下调|country downgrade)",lowered):s.append("sovereign_downgrade=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_interbank_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(interbank exposure|同业敞口|interbank lending|同业拆借|interbank market)",lowered):s.append("interbank_exposure=publicly_described")
    if re.search(r"(interbank contagion|同业传染|systemic risk|系统性风险)",lowered):s.append("interbank_contagion=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_financial_sponsor_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(PE fund|私募股权|private equity|venture capital|风险投资|VC investment)",lowered):s.append("pe_vc_investment=publicly_described")
    if re.search(r"(buyout|收购|leveraged buyout|杠杆收购|LBO|management buyout)",lowered):s.append("buyout_activity=publicly_described")
    if re.search(r"(exit plan|退出计划|IPO plan|上市计划|PE exit)",lowered):s.append("pe_exit_planned=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_cross_border_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(cross.?border risk|跨境风险|cross.?border exposure|跨境敞口|overseas exposure)",lowered):s.append("cross_border_exposure=publicly_described")
    if re.search(r"(capital control|资本管制|capital outflow|资本外流|repatriation risk)",lowered):s.append("capital_control_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_merger_regulatory_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(merger review|并购审查|antitrust review|反垄断审查|merger approval|并购审批)",lowered):s.append("merger_regulatory_review=publicly_described")
    if re.search(r"(merger blocked|并购被否|deal blocked|交易受阻|merger rejection)",lowered):s.append("merger_blocked=publicly_described")
    if re.search(r"(remedy|救济措施|divestiture condition|剥离条件|conditional approval)",lowered):s.append("merger_remedy=publicly_described")
    return list(dict.fromkeys(s))[:4]


def _public_web_asset_securitization_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(securitization|资产证券化|ABS issuance|ABS发行|asset.?backed security)",lowered):s.append("securitization_activity=publicly_described")
    if re.search(r"(originate.?to.?distribute|发起.?分销|loan sale|贷款出售|portfolio sale)",lowered):s.append("loan_portfolio_sale=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_ipo_underwriting_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(underwriting|承销|IPO underwriting|证券承销|book.?building|簿记)",lowered):s.append("ipo_underwriting=publicly_described")
    if re.search(r"(greenshoe|超额配售|over.?allotment|绿鞋|stabilization agent)",lowered):s.append("greenshoe_option=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_project_finance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(project finance|项目融资|BOT|build.?operate.?transfer|PPP|public.?private.?partnership)",lowered):s.append("project_finance=publicly_described")
    if re.search(r"(project cost overrun|项目超支|construction delay|建设延误|project delay)",lowered):s.append("project_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_deposit_franchise_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(deposit base|存款基础|deposit franchise|存款业务|core deposits|核心存款)",lowered):s.append("deposit_strength=publicly_described")
    if re.search(r"(deposit outflow|存款流失|deposit flight|存款外流|run risk)",lowered):s.append("deposit_outflow_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_financial_guarantee_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(financial guarantee|融资担保|credit guarantee|信用担保|bond guarantee|债券担保)",lowered):s.append("financial_guarantee=publicly_described")
    if re.search(r"(guarantee call|担保追索|guarantor default|担保人违约|guarantor distress)",lowered):s.append("guarantor_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_vendor_financing_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(vendor financing|供应商融资|supplier credit|供应商信贷|trade credit|商业信用)",lowered):s.append("vendor_financing=publicly_described")
    if re.search(r"(extended payment terms|延长付款期|payment delay|付款延迟|supplier squeeze)",lowered):s.append("supplier_payment_pressure=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_acquisition_financing_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(acquisition financing|并购融资|M&A financing|收购融资|deal financing)",lowered):s.append("acquisition_financing=publicly_described")
    if re.search(r"(bridge loan|过桥贷款|bridge financing|过桥融资|acquisition debt)",lowered):s.append("bridge_financing=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_distressed_debt_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(distressed debt|困境债务|NPL sale|不良资产出售|debt workout|债务重组)",lowered):s.append("distressed_debt=publicly_described")
    if re.search(r"(vulture fund|秃鹫基金|distressed asset investor|困境资产投资)",lowered):s.append("distressed_investor_activity=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_structured_deposit_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(structured deposit|结构性存款|structured product|结构性产品|wealth management product|理财产品)",lowered):s.append("structured_deposit=publicly_described")
    if re.search(r"(principal.?protected|保本|capital.?guaranteed|本金保障|non.?principal.?protected)",lowered):s.append("principal_protection_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_shadow_banking_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(shadow bank|影子银行|shadow banking|非银信贷|non.?bank lending)",lowered):s.append("shadow_banking=publicly_described")
    if re.search(r"(trust company|信托公司|trust loan|信托贷款|entrusted loan|委托贷款)",lowered):s.append("trust_lending=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_money_market_stress_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(money market stress|货币市场压力|funding stress|融资压力|LIBOR|SHIBOR|interbank rate)",lowered):s.append("money_market_stress=publicly_described")
    if re.search(r"(liquidity crunch|流动性危机|cash crunch|资金紧张|funding squeeze)",lowered):s.append("liquidity_crunch=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_bankruptcy_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(bankruptcy|破产|bankruptcy filing|破产申请|Chapter 11|insolvency|资不抵债)",lowered):s.append("bankruptcy_risk=publicly_described")
    if re.search(r"(bankruptcy protection|破产保护|restructuring plan|重组计划|creditor committee)",lowered):s.append("bankruptcy_protection=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_regional_bank_risk_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(regional bank|区域性银行|local bank|地方银行|city commercial bank)",lowered):s.append("regional_bank_exposure=publicly_described")
    if re.search(r"(rural bank|农商行|village bank|村镇银行|cooperative bank)",lowered):s.append("rural_bank_exposure=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_stock_exchange_action_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(trading halt|停牌|trading suspension|暂停交易|delisting|退市)",lowered):s.append("exchange_action=publicly_described")
    if re.search(r"(ST designation|特别处理|ST|special treatment|regulatory inquiry|监管问询)",lowered):s.append("regulatory_action=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_investment_portfolio_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(investment portfolio|投资组合|investment loss|投资损失|portfolio loss)",lowered):s.append("investment_loss=publicly_described")
    if re.search(r"(fair value loss|公允价值损失|mark.?to.?market loss|市值损失|unrealized loss)",lowered):s.append("fair_value_loss=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_reinsurance_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(reinsurance|再保险|reinsurer|再保险公司|retrocession|转分保)",lowered):s.append("reinsurance_exposure=publicly_described")
    if re.search(r"(reinsurance recoverable|再保险应收|reinsurance receivable|分保应收)",lowered):s.append("reinsurance_credit_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_pension_asset_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(pension asset|养老金资产|pension fund|养老基金|retirement asset)",lowered):s.append("pension_asset=publicly_described")
    if re.search(r"(pension underfunding|养老金不足|pension shortfall|养老金缺口|funding gap)",lowered):s.append("pension_shortfall=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_trust_capital_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(trust capital|信托资本|trust registration capital|信托注册资本|trust company capital)",lowered):s.append("trust_capital=publicly_described")
    if re.search(r"(capital injection|注资|capital increase|增资|recapitalization|再资本化)",lowered):s.append("capital_injection=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_operating_lease_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(operating lease|经营租赁|lease commitment|租赁承诺|off.?balance.?sheet lease)",lowered):s.append("operating_lease=publicly_described")
    if re.search(r"(lease expense|租赁费用|rental expense|租金|lease cost)",lowered):s.append("lease_cost=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_derivatives_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(derivative exposure|衍生品敞口|derivative position|衍生品头寸|derivatives trading)",lowered):s.append("derivative_exposure=publicly_described")
    if re.search(r"(derivative loss|衍生品损失|derivatives loss|speculative loss|投机损失)",lowered):s.append("derivative_loss=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_credit_card_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(credit card|信用卡|card receivable|信用卡应收|card NPL|信用卡不良)",lowered):s.append("credit_card_exposure=publicly_described")
    if re.search(r"(card charge.?off|信用卡核销|card delinquency|信用卡逾期)",lowered):s.append("card_credit_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_auto_loan_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(auto loan|汽车贷款|auto finance|汽车金融|car loan|车贷)",lowered):s.append("auto_loan_exposure=publicly_described")
    if re.search(r"(auto NPL|汽车不良|auto loan default|车贷违约)",lowered):s.append("auto_credit_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_mortgage_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(mortgage loan|按揭贷款|home loan|住房贷款|mortgage exposure|按揭敞口)",lowered):s.append("mortgage_exposure=publicly_described")
    if re.search(r"(mortgage NPL|按揭不良|mortgage default|按揭违约)",lowered):s.append("mortgage_credit_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_exchange_rate_exposure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(exchange rate|汇率|currency fluctuation|货币波动|forex exposure|外汇风险)",lowered):s.append("exchange_rate_exposure=publicly_described")
    if re.search(r"(devaluation risk|贬值风险|appreciation pressure|升值压力)",lowered):s.append("currency_volatility=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_equity_fundraising_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(rights issue|配股|equity offering|股票发行|placement|定向增发|seasoned offering)",lowered):s.append("equity_fundraising=publicly_described")
    if re.search(r"(private placement|私募|private offering|非公开发行)",lowered):s.append("private_placement=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_hybrid_security_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(hybrid security|混合证券|perpetual bond|永续债|preferred share|优先股|永续)",lowered):s.append("hybrid_security=publicly_described")
    if re.search(r"(AT1|additional tier 1|Tier 2|二级资本|subordinated debt|次级债)",lowered):s.append("subordinated_capital=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_sovereign_wealth_fund_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(sovereign wealth fund|主权基金|SWF|sovereign fund|国家投资基金)",lowered):s.append("sovereign_fund_investment=publicly_described")
    if re.search(r"(state capital|国有资本|state investment|国家投资)",lowered):s.append("state_capital=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_asset_management_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(asset management|资产管理|AUM|asset under management|fund management)",lowered):s.append("asset_management=publicly_described")
    if re.search(r"(AUM decline|管理规模下降|fund outflow|资金流出|redemption|赎回)",lowered):s.append("aum_decline=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_collateralized_loan_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(collateralized loan|抵押贷款|secured loan|担保贷款|pledged loan|质押贷款)",lowered):s.append("collateralized_lending=publicly_described")
    if re.search(r"(loan.?to.?value|LTV|抵质押率|collateral coverage)",lowered):s.append("ltv_ratio=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_financial_market_infrastructure_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(clearing house|清算所|settlement system|结算系统|payment system|支付系统)",lowered):s.append("market_infrastructure=publicly_described")
    if re.search(r"(CCP|central counterparty|中央对手方|settlement risk|结算风险)",lowered):s.append("settlement_risk=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_fx_exposure_signals(text: str) -> list[str]:
    lowered = str(text or "").lower()
    signals = []
    if re.search(r"(foreign exchange|外汇|FX exposure|汇率风险|currency exposure)", lowered):
        signals.append("fx_exposure=publicly_described")
    if re.search(r"(hedge|对冲|hedging|套期保值|currency swap|货币互换)", lowered):
        signals.append("fx_hedging=publicly_described")
    return list(dict.fromkeys(signals))[:3]


def _public_web_leveraged_buyout_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(leveraged buyout|LBO|杠杆收购|buyout fund|收购基金)",lowered):s.append("leveraged_buyout=publicly_described")
    if re.search(r"(LBO financing|收购融资|acquisition debt|收购债务)",lowered):s.append("lbo_leverage=publicly_described")
    return list(dict.fromkeys(s))[:3]


def _public_web_mezzanine_debt_signals(text: str) -> list[str]:
    lowered=str(text or "").lower()
    s=[]
    if re.search(r"(mezzanine debt|夹层债务|mezzanine financing|夹层融资|junior debt|次级债务)",lowered):s.append("mezzanine_debt=publicly_described")
    if re.search(r"(mezzanine default|夹层违约|subordination|劣后)",lowered):s.append("mezzanine_credit_quality=publicly_described")
    return list(dict.fromkeys(s))[:3]

def _public_web_capital_signals(text: str) -> list[str]:
    clean = str(text or "")
    lowered = clean.lower()
    signals: list[str] = []
    amount = _extract_public_web_money_amount(clean)
    # Financing / funding (English patterns use \b, Chinese use plain match)
    if re.search(
        r"\b(series\s+[a-z]|financing round|funding round|raised|secured financing|pre-ipo|ipo\s+计划)\b",
        lowered,
    ) or re.search(r'融资|增资', lowered):
        signals.append("financing_event=publicly_described")
        if amount:
            signals.append(f"financing_amount={amount}")
    # Major investment / strategic investment
    if re.search(
        r"\b(strategic investment|major investment|significant investment|capex\s+plan)\b",
        lowered,
    ) or re.search(r'重大投资|战略投资|项目投资|资本支出', lowered):
        signals.append("major_investment=publicly_described")
        if amount and "financing_event" not in " ".join(signals):
            signals.append(f"investment_amount={amount}")
    # Debt / credit / refinancing
    if re.search(
        r"\b(bond\b|notes?\b|debenture|credit facility|loan|debt|refinancing|debt financing)\b",
        lowered,
    ) or re.search(r'担保|债券|贷款|再融资|债务融资|授信', lowered):
        signals.append("debt_or_credit_obligation=publicly_described")
        if amount:
            signals.append(f"debt_or_credit_amount={amount}")
    # Cash flow / liquidity / solvency pressure
    if re.search(
        r"\b(cash flow pressure|liquidity pressure|working capital pressure|going concern"
        r"|solvency|defaulted|overdue)\b",
        lowered,
    ) or re.search(r'偿债压力|流动性压力|现金流压力|偿付能力|违约|逾期|资不抵债', lowered):
        signals.append("cash_or_liquidity_pressure=publicly_described")
    # Solvency / capital structure (positive or neutral signal)
    if re.search(
        r"\b(debt-to-equity|debt to equity|gearing ratio|capital structure)\b",
        lowered,
    ) or re.search(r'资产负债率|资本结构', lowered):
        signals.append("capital_structure=publicly_described")
    # Asset / equity pressure (pledge, freeze, auction)
    if re.search(
        r"\b(pledged shares|share pledge|asset freeze|frozen shares|judicial auction"
        r"|equity pledge)\b",
        lowered,
    ) or re.search(r'股权质押|冻结|司法拍卖|资产查封|股权冻结', lowered):
        signals.append("asset_or_equity_pressure=publicly_described")
    return list(dict.fromkeys(signals))[:10]
def _public_web_people_claim_signals(text: str) -> list[str]:
    signals = [f"{relation}={name}" for relation, name in _public_web_people_pairs(text)]
    return list(dict.fromkeys(signals))[:8]


def _public_web_people_pairs(text: str) -> list[tuple[str, str]]:
    clean = str(text or "")
    pairs: list[tuple[str, str]] = []
    # English role patterns (structured role + is/:/named statement)
    en_patterns = (
        ("legal_representative", r"\blegal representative\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("actual_controller", r"\bactual controller\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("beneficial_owner", r"\b(?:ultimate beneficial owner|beneficial owner|ubo)\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("chairman", r"\bchairman\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("ceo", r"\bceo\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("director", r"\bdirector\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("shareholder", r"\b(?:shareholder|investor)\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("founder", r"\bfounder\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("co_founder", r"\bco-founder\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("president", r"\bpresident\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("cfo", r"\bcfo\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
        ("cto", r"\bcto\s+(?:is|:)?\s*([A-Z][A-Za-z.\- ]{1,60})"),
    )
    for relation, pattern in en_patterns:
        for match in re.finditer(pattern, clean, flags=re.IGNORECASE):
            name = _clean_public_web_person_name(match.group(1))
            if name:
                pairs.append((relation, name))

    # English role-found-company patterns (e.g. "Alice Zhang founded", "Bob Li co-founded")
    en_founder_patterns = (
        ("founder", r"\b(?:founded|co-founded|founded by)\s+([A-Z][A-Za-z.\- ]{1,60})"),
    )
    for relation, pattern in en_founder_patterns:
        for match in re.finditer(pattern, clean, flags=re.IGNORECASE):
            name = _clean_public_web_person_name(match.group(1))
            if name:
                pairs.append((relation, name))

    # Chinese role patterns (structured role + name)
    cn_role_patterns = (
        ("legal_representative", r"法定代表人[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("actual_controller", r"实际控制人[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("legal_representative", r"法人代表[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("founder", r"创始人[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("chairman", r"董事长[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("ceo", r"总经理[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("cfo", r"财务总监[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("cto", r"(?:技术总监|技术负责人)[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("director", r"董事(?!长)(?:会成员)?[：:为]?\s*([\u4e00-\u9fff\u3400-\u4dbf\u00b7]{2,8})"),
        ("board_secretary", r"董事会秘书[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("supervisor", r"监事[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
        ("shareholder", r"股东[:：为]?\s*([\u4e00-\u9fff\u3400-\u4dbf·]{2,8})"),
    )
    for relation, pattern in cn_role_patterns:
        for match in re.finditer(pattern, clean):
            name = match.group(1).strip()
            if name and len(name) <= 10:
                pairs.append((relation, name))

    return list(dict.fromkeys(pairs))[:12]

def _extract_public_web_money_amount(text: str) -> str | None:
    match = re.search(
        r"((?:US\$|\$|RMB\s*|CNY\s*)\s?\d+(?:\.\d+)?\s?(?:billion|million|bn|m)?)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _clean_public_web_person_name(raw: str) -> str | None:
    value = re.split(
        r"\b(?:and|who|with|from|of|at|as|was|is|serves|served|joined|appointed|founded|co-founded|cofounded|leads|manages|oversees|heads|runs|became|named|,|\.)\b|\.\s+",
        str(raw or ""),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"\s+", " ", value).strip(" :;,.()[]")
    if not value or len(value) > 60:
        return None
    lowered = value.lower()
    if lowered in {"the company", "company", "management", "board"}:
        return None
    if len(value.split()) > 5:
        return None
    return value


def _dedupe_public_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entity in entities:
        key = (
            str(entity.get("kind") or ""),
            str(entity.get("relation") or ""),
            str(entity.get("name") or "").casefold(),
        )
        if key not in deduped:
            deduped[key] = entity
    return list(deduped.values())


def _extract_public_web_list(text: str, patterns: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
            values.extend(_split_public_web_values(match.group(1)))
    return list(dict.fromkeys(values))[:4]


def _extract_public_web_phrase(text: str, pattern: str) -> str | None:
    match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    if not match:
        return None
    values = _split_public_web_values(match.group(1))
    return values[0] if values else None


def _split_public_web_values(raw: str) -> list[str]:
    clipped = re.split(
        r"\b(?:while|with|where|which|that|and downstream|and upstream)\b",
        str(raw or ""),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    parts = re.split(r",|\band\b|/|、|，", clipped, flags=re.IGNORECASE)
    values: list[str] = []
    stopwords = {
        "large customers",
        "enterprise customers",
        "major customers",
        "key customers",
        "public customers",
        "core suppliers",
        "major suppliers",
        "strategic partners",
    }
    for part in parts:
        value = re.sub(r"\s+", " ", part).strip(" :;,.()[]")
        if not value:
            continue
        lowered = value.lower()
        if lowered in stopwords or len(value) > 80:
            continue
        if not re.search(r"[A-Za-z0-9]", value) and not re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", value):
            continue
        values.append(value)
    return values


def _public_web_ratio_signal(text: str, label: str) -> str:
    pattern = re.escape(label) + r"[^0-9]{0,40}(\d+(?:\.\d+)?)\s*%"
    match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    if not match:
        return "publicly_described"
    value = float(match.group(1)) / 100
    return f"{value:.2f}".rstrip("0").rstrip(".")


async def fetch_public_web_content(
    url: str,
    *,
    fetcher: Any = None,
    fetch_contents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch or attach URL-level content verification from an approved provider."""
    if not url:
        return {
            "ok": False,
            "status": "missing_url",
            "provider": "none",
            "content_preview": "",
        }

    fetch_contents = fetch_contents or {}
    if url in fetch_contents:
        content = fetch_contents[url]
        return _verification_from_content(url, content, provider="fixture")

    if fetcher is None:
        return {
            "ok": False,
            "status": "fetcher_not_configured",
            "provider": "none",
            "url": url,
            "content_preview": "",
        }

    try:
        content = fetcher(url)
        if hasattr(content, "__await__"):
            content = await content
        return _verification_from_content(url, content, provider=getattr(fetcher, "__name__", "callable"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "fetch_failed",
            "provider": getattr(fetcher, "__name__", "callable"),
            "url": url,
            "error_type": type(exc).__name__,
            "content_preview": "",
        }


def _verification_from_content(url: str, content: Any, *, provider: str) -> dict[str, Any]:
    if isinstance(content, dict):
        status_code = content.get("status_code", content.get("status"))
        text = str(content.get("text") or content.get("content") or "")
        final_url = normalize_public_url(str(content.get("url") or url))
    else:
        status_code = None
        text = str(content or "")
        final_url = url
    ok = bool(text.strip()) and (status_code is None or int(status_code) < 400)
    return {
        "ok": ok,
        "status": "fetched" if ok else "empty_or_error",
        "provider": provider,
        "url": final_url,
        "http_status": status_code,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else "",
        "content_preview": " ".join(text.split())[:240],
    }


def normalize_public_url(url: str) -> str:
    """Normalize public result URLs for stable dedupe and provenance display."""
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "spm", "from", "ref"}
    ]
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            path,
            "",
            urlencode(query_pairs, doseq=True),
            "",
        )
    )


def public_web_dedupe_key(*, title: str, url: str, snippet: str) -> str:
    """Return a stable key for duplicate search hits from multiple providers."""
    if url:
        basis = f"url:{url}"
    else:
        basis = "text:" + " ".join((title + " " + snippet).lower().split())[:300]
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _clamp(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.45
    return max(0.0, min(1.0, value))


def _coerce_timeout(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default)
    return max(0.1, value)


def create_public_web_search_tool() -> PublicWebSearchTool:
    return PublicWebSearchTool()
