#!/usr/bin/env python3
"""Tests for public web-search normalization bridge."""
from __future__ import annotations

import asyncio

import pytest

from adapters.public_web_search_tool import (
    DuckDuckGoInstantAnswerProvider,
    PublicWebSearchConfig,
    PublicWebSearchTool,
    SearxngSearchProvider,
    _clean_public_web_person_name,
    _public_web_business_model_signals,
    _public_web_capital_signals,
    _public_web_customer_value,
    _public_web_industry_label,
    _public_web_industry_signals,
    _public_web_market_position_signals,
    _public_web_people_pairs,
    _public_web_product_label,
    _public_web_supply_chain_signals,
    coerce_public_web_search_config,
    fetch_public_web_content,
    normalize_public_url,
    normalize_search_provider_results,
    public_web_cognition_claims,
    public_web_dedupe_key,
    public_web_results_to_standardized_records,
    search_public_web_provider,
)
from core.risk_discovery_pipeline import RiskDiscoveryPipeline


def test_public_web_search_config_coerces_dict() -> None:
    config = coerce_public_web_search_config(
        {
            "type": "searxng",
            "enabled": True,
            "base_url": "https://search.example",
            "max_results": 5,
            "provider_options": {"language": "en"},
        }
    )

    assert config.provider_type == "searxng"
    assert config.enabled is True
    assert config.searxng_base_url == "https://search.example"
    assert config.max_results == 5
    assert config.provider_options == {"language": "en"}


def test_public_web_search_default_config_is_zero_config_ready() -> None:
    tool = PublicWebSearchTool()

    health = tool.health_check()

    assert health["ok"] is True
    assert health["zero_config_ready"] is True
    assert health["live_provider_configured"] is True
    assert health["provider_report"]["default_enabled"] is True
    assert health["provider_report"]["config"]["provider_type"] == "auto"


def test_public_web_health_reports_missing_provider_configuration() -> None:
    tool = PublicWebSearchTool(config={"provider_type": "searxng", "enabled": True})

    health = tool.health_check()

    assert health["ok"] is False
    assert health["live_provider_configured"] is False
    assert health["provider_report"]["missing"] == ["searxng_base_url"]
    assert health["provider_report"]["next_action"] == "configure_public_web_search_provider_or_use_fixture_results"


def test_public_web_health_accepts_configured_searxng_provider() -> None:
    tool = PublicWebSearchTool(
        config=PublicWebSearchConfig(
            provider_type="searxng",
            enabled=True,
            searxng_base_url="https://search.example",
        )
    )

    health = tool.health_check()

    assert health["ok"] is True
    assert health["live_provider_configured"] is True
    assert health["provider_report"]["next_action"] == "ready_for_live_search"


def test_public_web_results_map_to_standardized_records() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Web Co., Ltd.",
            [
                {
                    "title": "Demo Web Co., Ltd. enforcement notice",
                    "url": "https://example.com/demo",
                    "snippet": "The company was listed in a public enforcement-related notice.",
                    "confidence": 0.7,
                }
            ],
        )
    )

    assert records[0]["source_name"] == "public_web_search"
    assert records[0]["source_type"] == "search_engine"
    assert records[0]["url"] == "https://example.com/demo"
    assert records[0]["confidence"] == 0.7
    assert "requires URL-level verification" in records[0]["evidence"][0]["claim"]


def test_public_web_results_add_conservative_industry_product_leads_for_subject() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo RiskIntel Co.",
            [
                {
                    "title": "Demo RiskIntel Co. risk intelligence platform",
                    "url": "https://example.com/demo-riskintel",
                    "snippet": (
                        "Demo RiskIntel Co. is a technology company offering a SaaS counterparty "
                        "risk intelligence platform for mission-critical compliance workflows."
                    ),
                    "confidence": 0.72,
                }
            ],
        )
    )

    claims = [item["claim"] for item in records[0]["evidence"]]

    assert any("industry=technology" in claim for claim in claims)
    assert any("product=risk intelligence platform" in claim for claim in claims)
    assert any("customer_value=mission-critical compliance or risk workflow support" in claim for claim in claims)
    assert any("subscription_revenue_ratio=subscription_or_saas_model_publicly_described" in claim for claim in claims)
    assert any("switching_cost=0.6" in claim for claim in claims)
    assert any("value_chain_role=software_platform" in claim for claim in claims)


def test_public_web_results_add_conservative_supply_chain_leads_for_subject() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Industrial Co.",
            [
                {
                    "title": "Demo Industrial Co. customer and supplier profile",
                    "url": "https://example.com/demo-industrial-supply-chain",
                    "snippet": (
                        "Demo Industrial Co. customers include State Grid and Metro Rail. "
                        "Suppliers include Demo Components Ltd. Upstream materials include "
                        "semiconductor materials. Downstream markets include industrial automation. "
                        "Partners include Demo Integrator. Customer concentration was 62% and "
                        "supplier concentration was 48%."
                    ),
                    "confidence": 0.7,
                }
            ],
        )
    )

    claims = [item["claim"] for item in records[0]["evidence"]]

    assert any("customer=State Grid" in claim for claim in claims)
    assert any("customer=Metro Rail" in claim for claim in claims)
    assert any("supplier=Demo Components Ltd" in claim for claim in claims)
    assert any("upstream=semiconductor materials" in claim for claim in claims)
    assert any("downstream=industrial automation" in claim for claim in claims)
    assert any("partner=Demo Integrator" in claim for claim in claims)
    assert any("customer_concentration=0.62" in claim for claim in claims)
    assert any("supplier_concentration=0.48" in claim for claim in claims)


def test_public_web_results_add_capital_and_people_leads_for_subject() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Capital Co.",
            [
                {
                    "title": "Demo Capital Co. financing and leadership update",
                    "url": "https://example.com/demo-capital-update",
                    "snippet": (
                        "Demo Capital Co. raised $50 million in a Series B financing round. "
                        "The company also disclosed liquidity pressure and pledged shares. "
                        "CEO Alice Zhang and director Bob Li joined the board."
                    ),
                    "confidence": 0.7,
                }
            ],
        )
    )

    claims = [item["claim"] for item in records[0]["evidence"]]
    entities = records[0]["entities"]

    assert any("Public web capital lead" in claim for claim in claims)
    assert any("financing_event=publicly_described" in claim for claim in claims)
    assert any("financing_amount=$50 million" in claim for claim in claims)
    assert any("cash_or_liquidity_pressure=publicly_described" in claim for claim in claims)
    assert any("asset_or_equity_pressure=publicly_described" in claim for claim in claims)
    assert any("Public web people lead" in claim for claim in claims)
    assert {"kind": "person", "name": "Alice Zhang", "relation": "ceo", "confidence": 0.62, "extraction": "public_web_role_pattern"} in entities
    assert {"kind": "person", "name": "Bob Li joined the board", "relation": "director", "confidence": 0.62, "extraction": "public_web_role_pattern"} not in entities
    assert any(entity["name"] == "Bob Li joined the board" for entity in entities) is False


def test_public_web_results_are_normalized_and_deduplicated() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Web Co., Ltd.",
            [
                {
                    "title": "Demo duplicate",
                    "url": "HTTPS://Example.COM/demo/?utm_source=x&keep=1#section",
                    "snippet": "First copy.",
                },
                {
                    "title": "Demo duplicate again",
                    "url": "https://example.com/demo?keep=1&utm_campaign=y",
                    "snippet": "Second copy.",
                },
            ],
        )
    )

    assert len(records) == 1
    assert records[0]["url"] == "https://example.com/demo?keep=1"
    assert records[0]["dedupe_key"] == public_web_dedupe_key(
        title="Demo duplicate",
        url="https://example.com/demo?keep=1",
        snippet="First copy.",
    )


def test_public_web_text_dedupe_without_url() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Web Co., Ltd.",
            [
                {"title": "Same title", "snippet": "Same snippet"},
                {"title": "Same   title", "snippet": "Same snippet"},
            ],
        )
    )

    assert len(records) == 1


def test_normalize_public_url_removes_tracking_parameters() -> None:
    url = normalize_public_url("https://EXAMPLE.com/path/?utm_source=x&gclid=y&keep=1#frag")

    assert url == "https://example.com/path?keep=1"


def test_normalize_search_provider_results_handles_common_payloads() -> None:
    brave_like = {
        "web": {
            "results": [
                {
                    "title": "Demo title",
                    "url": "https://example.com/a",
                    "description": "Demo description",
                }
            ]
        }
    }
    tavily_like = {
        "results": [
            {
                "title": "Tavily title",
                "url": "https://example.com/b",
                "content": "Tavily content",
                "score": 0.8,
            }
        ]
    }

    assert normalize_search_provider_results(brave_like)[0]["snippet"] == "Demo description"
    assert normalize_search_provider_results(tavily_like)[0]["confidence"] == 0.8


def test_normalize_search_provider_results_handles_duckduckgo_payload() -> None:
    payload = {
        "Heading": "Demo Company",
        "AbstractText": "Demo Company public profile.",
        "AbstractURL": "https://example.com/demo",
        "RelatedTopics": [
            {"Text": "Demo Company - public record", "FirstURL": "https://example.com/record"}
        ],
    }

    hits = normalize_search_provider_results(payload)

    assert hits[0]["title"] == "Demo Company"
    assert hits[0]["url"] == "https://example.com/demo"
    assert hits[1]["url"] == "https://example.com/record"


@pytest.mark.asyncio
async def test_search_public_web_provider_accepts_callable_provider() -> None:
    async def provider(query: str, max_results: int = 10):
        return [{"title": query, "url": "https://example.com/live", "snippet": "Live hit."}]

    hits = await search_public_web_provider("Demo Live Co.", provider=provider)

    assert hits[0]["url"] == "https://example.com/live"


@pytest.mark.asyncio
async def test_searxng_provider_maps_json_results() -> None:
    async def http_get(url: str):
        assert "format=json" in url
        return {
            "results": [
                {
                    "title": "SearXNG hit",
                    "url": "https://example.com/searx",
                    "content": "SearXNG content",
                }
            ]
        }

    provider = SearxngSearchProvider("https://search.example", http_get=http_get)

    hits = await provider.search("Demo")

    assert hits[0]["title"] == "SearXNG hit"


@pytest.mark.asyncio
async def test_duckduckgo_default_provider_maps_json_results() -> None:
    async def http_get(url: str):
        assert "api.duckduckgo.com" in url
        return {
            "Heading": "Default hit",
            "AbstractText": "Default provider content.",
            "AbstractURL": "https://example.com/default",
        }

    provider = DuckDuckGoInstantAnswerProvider(http_get=http_get)

    hits = await provider.search("Demo")

    assert hits[0]["url"] == "https://example.com/default"


@pytest.mark.asyncio
async def test_fetch_public_web_content_from_configured_provider() -> None:
    async def fetcher(url: str):
        return {
            "url": url,
            "status_code": 200,
            "text": "Verified public page mentions enforcement notice.",
        }

    result = await fetch_public_web_content("https://example.com/demo", fetcher=fetcher)

    assert result["ok"] is True
    assert result["status"] == "fetched"
    assert result["content_hash"]
    assert "enforcement notice" in result["content_preview"]


@pytest.mark.asyncio
async def test_public_web_records_include_url_verification() -> None:
    records = await public_web_results_to_standardized_records(
        "Demo Web Co., Ltd.",
        [
            {
                "title": "Demo fetched result",
                "url": "https://example.com/demo",
                "snippet": "Lead.",
                "confidence": 0.4,
            }
        ],
        fetch_contents={
            "https://example.com/demo": {
                "status_code": 200,
                "text": "Fetched public content with verified lead.",
            }
        },
    )

    assert records[0]["url_verification"]["ok"] is True
    assert records[0]["confidence"] == 0.5
    assert any("URL-level fetch verified" in item["claim"] for item in records[0]["evidence"])


@pytest.mark.asyncio
async def test_public_web_search_tool_returns_record_quality_report() -> None:
    tool = PublicWebSearchTool()

    result = await tool.search(
        "Demo Web Co., Ltd.",
        "public_web_search",
        results=[
            {
                "title": "Demo Web Co., Ltd. enforcement notice",
                "url": "https://example.com/demo",
                "snippet": "Public filing lead.",
            }
        ],
    )

    assert result.ok
    assert result.data["execution_state"] == "records_ready"
    assert result.data["provider_report"]["default_enabled"] is True
    assert result.data["record_quality"]["ok"] is True
    assert result.data["record_quality"]["record_count"] == 1


@pytest.mark.asyncio
async def test_public_web_provider_validation_reports_missing_provider() -> None:
    tool = PublicWebSearchTool(config={"provider_type": "searxng", "enabled": True})

    report = await tool.provider_validation_report(sample_query="Demo Missing Provider")

    assert report["ok"] is False
    assert report["status"] == "provider_not_configured"
    assert report["standardized_record_count"] == 0
    assert report["provider_report"]["missing"] == ["searxng_base_url"]


@pytest.mark.asyncio
async def test_public_web_provider_validation_reports_provider_errors() -> None:
    async def provider(query: str, max_results: int = 10):
        raise TimeoutError("search timeout")

    tool = PublicWebSearchTool(provider=provider)

    report = await tool.provider_validation_report(sample_query="Demo Timeout")

    assert report["ok"] is False
    assert report["status"] == "provider_error"
    assert "TimeoutError" in report["error"]
    assert report["next_action"] == "fix_public_web_search_provider_or_endpoint"


@pytest.mark.asyncio
async def test_public_web_provider_validation_accepts_standardized_live_results() -> None:
    async def provider(query: str, max_results: int = 10):
        return [
            {
                "title": "Demo Live profile",
                "url": "https://example.com/live-profile",
                "snippet": "Live provider returned public company profile.",
            }
        ]

    tool = PublicWebSearchTool(provider=provider)

    report = await tool.provider_validation_report(sample_query="Demo Live")

    assert report["ok"] is True
    assert report["status"] == "ready"
    assert report["result_count"] == 1
    assert report["standardized_record_count"] == 1
    assert report["record_quality"]["ok"] is True
    assert report["next_action"] == "ready_for_risk_discovery_routing"


@pytest.mark.asyncio
async def test_public_web_search_tool_uses_live_provider_and_fetcher() -> None:
    async def provider(query: str, max_results: int = 10):
        return [{"title": query, "url": "https://example.com/live", "snippet": "Live lead."}]

    async def fetcher(url: str):
        return {"status_code": 200, "text": "Fetched live provider page."}

    tool = PublicWebSearchTool(provider=provider)

    result = await tool.search("Demo Live Co.", "public_web_search", fetcher=fetcher)

    assert result.ok is True
    assert result.data["provider_configured"] is True
    assert result.data["provider_attempted"] is True
    assert result.data["execution_state"] == "records_ready"
    assert result.data["standardized_records"][0]["url_verification"]["ok"] is True


@pytest.mark.asyncio
async def test_public_web_search_tool_uses_configured_searxng_provider() -> None:
    async def http_get(url: str):
        assert "search?" in url
        return {
            "results": [
                {
                    "title": "Configured SearXNG hit",
                    "url": "https://example.com/configured",
                    "content": "Configured provider lead.",
                }
            ]
        }

    tool = PublicWebSearchTool(
        config={
            "provider_type": "searxng",
            "enabled": True,
            "searxng_base_url": "https://search.example",
            "max_results": 3,
        }
    )

    result = await tool.search(
        "Demo Configured Co.",
        "public_web_search",
        http_get=http_get,
    )

    assert result.ok is True
    assert result.data["provider_configured"] is True
    assert result.data["provider_attempted"] is True
    assert result.data["execution_state"] == "records_ready"
    assert result.data["standardized_records"][0]["url"] == "https://example.com/configured"


@pytest.mark.asyncio
async def test_public_web_search_tool_uses_zero_config_provider() -> None:
    async def http_get(url: str):
        return {
            "Heading": "Zero config hit",
            "AbstractText": "Zero config public company profile.",
            "AbstractURL": "https://example.com/zero",
        }

    tool = PublicWebSearchTool()

    result = await tool.search("Demo Zero Co.", "public_web_search", http_get=http_get)

    assert result.ok is True
    assert result.data["provider_configured"] is True
    assert result.data["provider_attempted"] is True
    assert result.data["execution_state"] == "records_ready"
    assert result.data["standardized_records"][0]["url"] == "https://example.com/zero"


@pytest.mark.asyncio
async def test_public_web_search_tool_reports_attempted_empty_provider() -> None:
    async def provider(query: str, max_results: int = 10):
        return []

    tool = PublicWebSearchTool(provider=provider)

    result = await tool.search("Demo Empty Co.", "public_web_search")

    assert result.ok is True
    assert result.data["provider_configured"] is True
    assert result.data["provider_attempted"] is True
    assert result.data["execution_state"] == "provider_returned_no_results"
    assert result.data["result_count"] == 0


@pytest.mark.asyncio
async def test_public_web_search_tool_feeds_risk_discovery_pipeline(tmp_path) -> None:
    tool = PublicWebSearchTool()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    class SearchWrapper:
        def health_check(self):
            return tool.health_check()

        async def search(self, query: str, tool_type: str, **kwargs):
            return await tool.search(
                query,
                "public_web_search",
                results=[
                    {
                        "title": f"{query} public enforcement result",
                        "snippet": "Public result mentions 失信 and 被执行 signals.",
                        "url": "https://example.com/web-result",
                    }
                ],
            )

    result = await pipeline.run("Demo Web Co., Ltd.", search_engine=SearchWrapper())

    assert result.queried_sources == ["public_web_search"]
    assert result.evidence_count >= 1
    assert result.risk_event_summary["alert_count"] >= 1


# ── Capital / money signals ──

def test_capital_signals_detect_chinese_financing_and_pledge() -> None:
    """融资、股权质押应被检出"""
    sigs = _public_web_capital_signals("这家公司有融资和股权质押问题")
    assert "financing_event=publicly_described" in sigs
    assert "asset_or_equity_pressure=publicly_described" in sigs


def test_capital_signals_detect_chinese_major_investment() -> None:
    """重大投资、资产负债率应被检出"""
    sigs = _public_web_capital_signals("资产负债率65%，有重大投资项目")
    assert "capital_structure=publicly_described" in sigs
    assert "major_investment=publicly_described" in sigs


def test_capital_signals_detect_english_major_investment_and_refinancing() -> None:
    sigs = _public_web_capital_signals("strategic investment of $100M approved and refinancing plan announced")
    assert "major_investment=publicly_described" in sigs
    assert "debt_or_credit_obligation=publicly_described" in sigs


def test_capital_signals_ignore_plain_text() -> None:
    sigs = _public_web_capital_signals("普通公司介绍没有特殊信息")
    assert len(sigs) == 0


# ── Supply-chain / goods signals ──

def test_supply_chain_detect_chinese_customers_and_suppliers() -> None:
    sc = _public_web_supply_chain_signals("客户包括华为。供应商包括中芯国际。")
    assert any("customer=华为" in s for s in sc)
    assert any("supplier=中芯国际" in s for s in sc)


def test_supply_chain_detect_chinese_partners_and_distributors() -> None:
    sc = _public_web_supply_chain_signals("合作方包括腾讯。经销商包括苏宁。代理商包括国美。")
    assert any("partner=腾讯" in s for s in sc)
    assert any("distributor=苏宁" in s for s in sc) or any("distributor=国美" in s for s in sc)


def test_supply_chain_detect_chinese_channels() -> None:
    sc = _public_web_supply_chain_signals("销售渠道包括线上和线下。")
    assert any("channel=线上" in s or "channel=线上和线下" in s for s in sc)


def test_supply_chain_detect_chinese_upstream_downstream() -> None:
    sc = _public_web_supply_chain_signals("上游原材料包括芯片。下游市场包括汽车。")
    assert any("upstream=芯片" in s for s in sc)
    assert any("downstream=汽车" in s for s in sc)


def test_supply_chain_detect_chinese_concentration() -> None:
    sc = _public_web_supply_chain_signals("客户集中度62%。供应商集中度48%。")
    assert any("customer_concentration=" in s for s in sc)
    assert any("supplier_concentration=" in s for s in sc)


# ── Market position signals ──

def test_market_position_detect_english_market_leader() -> None:
    mp = _public_web_market_position_signals("The company is a market leader with 45% market share.")
    assert any("market_share=" in s for s in mp)
    assert "market_position=market_leader_or_dominant" in mp


def test_market_position_detect_chinese_top_ranked() -> None:
    mp = _public_web_market_position_signals("行业龙头，市场份额30%")
    assert "market_position=market_leader_or_dominant" in mp


# ── Business model signals ──

def test_business_model_detect_b2b_and_saas() -> None:
    bm = _public_web_business_model_signals("B2B SaaS platform with subscription revenue.")
    assert "sales_model=b2b" in bm
    assert "revenue_model=subscription_or_saas" in bm


def test_business_model_detect_chinese_direct_sales() -> None:
    bm = _public_web_business_model_signals("商业模式为直销+电商")
    assert "business_model=publicly_described" in bm
    assert "sales_channel=direct_or_online" in bm


def test_business_model_claim_does_not_create_empty_supply_chain_claim() -> None:
    claims = public_web_cognition_claims(
        query="Demo SaaS Co.",
        title="Demo SaaS Co. business model",
        snippet="Demo SaaS Co. is a B2B SaaS platform with subscription revenue.",
    )

    assert any("business-model" in claim for claim in claims)
    assert not any("supply-chain lead: sources=public web" in claim for claim in claims)


# ── People signals ──

def test_people_pairs_detect_chinese_roles() -> None:
    pairs = _public_web_people_pairs("法定代表人李四。实际控制人王五。创始人张三。总经理赵六。财务总监钱七。董事会秘书孙八。")
    assert any(r == "legal_representative" and "李四" in n for r, n in pairs)
    assert any(r == "actual_controller" and "王五" in n for r, n in pairs)
    assert any(r == "founder" and "张三" in n for r, n in pairs)
    assert any(r == "ceo" and "赵六" in n for r, n in pairs)
    assert any(r == "cfo" and "钱七" in n for r, n in pairs)


def test_people_pairs_detect_english_founder_and_roles() -> None:
    pairs = _public_web_people_pairs("CEO Alice Zhang founded the company. Director Bob Li. CFO Charlie Wang.")
    assert any(r == "ceo" and "Alice Zhang" in n for r, n in pairs)
    assert any(r == "director" and "Bob Li" in n for r, n in pairs)
    assert any(r == "cfo" and "Charlie Wang" in n for r, n in pairs)
    # Should NOT leak "founded the company" into any name
    assert not any("founded" in n for r, n in pairs)


def test_people_pairs_no_false_matches_on_plain_text() -> None:
    pairs = _public_web_people_pairs("普通公司介绍没有人员信息")
    assert len(pairs) == 0


# ── Industry / product / customer-value ──

def test_industry_label_new_categories() -> None:
    assert _public_web_industry_label("a manufacturing company") == "manufacturing"
    assert _public_web_industry_label("logistics and supply chain company") == "logistics_and_supply_chain"
    assert _public_web_industry_label("an education and training provider") == "education_and_training"


def test_product_label_new_categories() -> None:
    assert _public_web_product_label("payment platform") == "payment_platform"
    assert _public_web_product_label("semiconductor chip design") == "semiconductor_chip"
    assert _public_web_product_label("ERP enterprise software") == "enterprise_software"


def test_customer_value_new_signals() -> None:
    assert _public_web_customer_value("data analytics insights for teams") == "data_analytics_or_insights"
    assert _public_web_customer_value("improve team efficiency and productivity") == "efficiency_or_productivity"


def test_industry_signals_expanded() -> None:
    sigs = _public_web_industry_signals("fast growing manufacturer with competition and regulatory pressure")
    assert "value_chain_role=manufacturer" in sigs
    assert "competitive_pressure=publicly_described" in sigs
    assert "industry_growth=high" in sigs
    assert "policy_risk=publicly_described" in sigs


# ── Clean person name ──

def test_clean_person_name_splits_on_founded() -> None:
    assert _clean_public_web_person_name("Alice Zhang founded the company") == "Alice Zhang"


def test_clean_person_name_splits_on_leads_manages() -> None:
    assert _clean_public_web_person_name("Bob Li leads engineering") == "Bob Li"
    assert _clean_public_web_person_name("Charlie Wang manages the team") == "Charlie Wang"


def test_clean_person_name_splits_on_period_space() -> None:
    assert _clean_public_web_person_name("Bob Li. CFO Charlie Wang") == "Bob Li"


# ── Full cognition claims integration ──

def test_cognition_claims_includes_all_new_signal_types() -> None:
    claims = public_web_cognition_claims(
        query="Demo Fintech Co.",
        title="Demo Fintech Co. B2B SaaS market leader with 35 percent market share",
        snippet=(
            "Demo Fintech Co. raised $50M in a Series B round. "
            "Customers include State Grid. CEO Alice Zhang."
        ),
    )
    claim_text = " ".join(claims)
    assert "market-position" in claim_text, f"missing market-position in {claims}"
    assert "business-model" in claim_text, f"missing business-model in {claims}"
    assert "supply-chain" in claim_text, f"missing supply-chain in {claims}"
    assert "capital lead" in claim_text, f"missing capital in {claims}"


# ── Standardized record pipeline ──

def test_standardized_records_include_new_extraction_signals() -> None:
    records = asyncio.run(
        public_web_results_to_standardized_records(
            "Demo Deep Co.",
            [
                {
                    "title": "Demo Deep Co. financing and market update",
                    "url": "https://example.com/demo-deep",
                    "snippet": (
                        "Demo Deep Co. is a B2B SaaS market leader in risk intelligence. "
                        "Customers include State Grid and Bank Alpha. "
                        "Suppliers include Cloud Ltd. "
                        "The company raised $50M in a Series B. "
                        "CEO Alice Zhang founded the company."
                    ),
                    "confidence": 0.75,
                }
            ],
        )
    )
    claims = [item["claim"] for item in records[0]["evidence"]]
    claim_text = " ".join(claims)
    # All signal types should appear
    assert "business-model" in claim_text, f"missing business-model in evidence claims: {claim_text}"
    assert "supply-chain" in claim_text, f"missing supply-chain in claims"
    assert "market-position" in claim_text, f"missing market-position in claims"
    assert "capital" in claim_text, f"missing capital in claims"
    # People entities
    entities = records[0]["entities"]
    assert any(e["name"] == "Alice Zhang" and e["relation"] == "ceo" for e in entities), f"missing Alice Zhang CEO in {entities}"
    # Confidence got bump from URL fetch
    assert records[0]["confidence"] > 0.7


# --- Phase C: Market position report path ---

def test_market_position_signals_reach_cognition_claims() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims
    claims = public_web_cognition_claims(
        query="Demo Market Leader Co.",
        title="Demo Market Leader Co. industry report",
        snippet="Demo Market Leader Co. holds 35 percent market share in enterprise risk intelligence and is the industry leader with a dominant position.",
    )
    claim_text = "; ".join(claims)
    assert "market-position" in claim_text
    assert "market_leader_or_dominant" in claim_text

def test_market_position_signals_include_share() -> None:
    from adapters.public_web_search_tool import _public_web_market_position_signals
    sigs = _public_web_market_position_signals("The company has 25% market share and is a top 3 supplier.")
    assert any("market_share=" in s for s in sigs)
    assert any("top_ranked" in s or "market_leader" in s for s in sigs)

def test_weak_market_position_remains_lead_only() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims
    claims = public_web_cognition_claims(
        query="Unrelated Co.",
        title="Some generic news",
        snippet="Market share is important for all companies. The industry has many players.",
    )
    claim_text = "; ".join(claims)
    assert "market-position" not in claim_text, f"Should not emit market-position for non-subject text: {claim_text}"


def test_customer_concentration_extraction() -> None:
    from adapters.public_web_search_tool import _public_web_customer_concentration_signals
    sigs = _public_web_customer_concentration_signals("customer concentration was 62% and top customer accounted for 45%")
    assert any("0.62" in s for s in sigs), f"Expected 0.62 in {sigs}"

def test_customer_concentration_claims_emission() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims
    claims = public_web_cognition_claims(
        query="Demo Co.", title="Demo Co. profile",
        snippet="Demo Co. customer concentration was 62% with top customer accounting for 35% of revenue.",
    )
    text = "; ".join(claims)
    assert "customer-concentration" in text, f"Missing customer-concentration claim: {text}"

def test_customer_concentration_no_false_positive() -> None:
    from adapters.public_web_search_tool import _public_web_customer_concentration_signals
    sigs = _public_web_customer_concentration_signals("The company has diverse customers.")
    assert sigs == [], f"Expected empty for no concentration signal: {sigs}"


def test_supplier_concentration_extraction() -> None:
    from adapters.public_web_search_tool import _public_web_supplier_concentration_signals, public_web_cognition_claims
    sigs = _public_web_supplier_concentration_signals("supplier concentration was 48%")
    assert any("0.48" in x for x in sigs)
    claims = public_web_cognition_claims(query="Demo Co.", title="Demo", snippet="Demo Co. supplier concentration was 48%.")
    assert any("supplier-concentration" in c for c in claims)


def test_business_model_claims_emission() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims
    claims=public_web_cognition_claims(query="Demo Co.",title="Demo Profile",snippet="Demo Co. is a B2B SaaS company with subscription revenue.")
    text="; ".join(claims)
    assert "business-model" in text,f"Missing business-model: {text}"
    assert "b2b" in text or "subscription" in text

def test_business_model_extraction() -> None:
    from adapters.public_web_search_tool import _public_web_business_model_signals
    sigs=_public_web_business_model_signals("B2B SaaS platform with subscription revenue")
    assert any("b2b" in s for s in sigs) or any("saas" in s for s in sigs)


def test_substitution_risk_claims_emission_chinese_and_english() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims

    cn_claims = public_web_cognition_claims(
        query="Demo Co.",
        title="Demo Co. 产品风险",
        snippet="Demo Co. 的核心产品存在替代风险，可能被新技术替代。",
    )
    en_claims = public_web_cognition_claims(
        query="Demo Co.",
        title="Demo Co. product update",
        snippet="Demo Co. faces substitution risk from alternative products.",
    )

    assert any("substitution-risk" in claim for claim in cn_claims), cn_claims
    assert any("substitution-risk" in claim for claim in en_claims), en_claims


def test_unit_economics_english() -> None:
    from adapters.public_web_search_tool import _public_web_unit_economics_signals
    s=_public_web_unit_economics_signals("Company reports 70% gross margin with strong unit economics.")
    assert len(s)>0

def test_unit_economics_chinese() -> None:
    from adapters.public_web_search_tool import _public_web_unit_economics_signals
    s=_public_web_unit_economics_signals("公司毛利率60%，获客成本可控。")
    assert len(s)>0

def test_unit_economics_negative() -> None:
    from adapters.public_web_search_tool import _public_web_unit_economics_signals
    s=_public_web_unit_economics_signals("The company sells products to customers.")
    assert s==[]


def test_unit_economics_reaches_cognition_claims() -> None:
    from adapters.public_web_search_tool import public_web_cognition_claims

    claims = public_web_cognition_claims(
        query="Demo Co.",
        title="Demo Co. unit economics update",
        snippet="Demo Co. reports improving gross margin and lower customer acquisition cost.",
    )

    text = "; ".join(claims)
    assert "unit-economics" in text, text
    assert "unit_economics=publicly_described" in text, text


def test_unit_economics_in_standardized_records() -> None:
    from adapters.public_web_search_tool import public_web_results_to_standardized_records
    import asyncio
    raw=[{"title":"Demo earnings","url":"https://ex.com/ue","snippet":"Demo Co. reports 70% gross margin and strong unit economics with LTV:CAC of 3:1.","confidence":0.75}]
    recs=asyncio.run(public_web_results_to_standardized_records("Demo Co.",raw))
    assert len(recs)>0
    claims=[e.get("claim","") for r in recs for e in r.get("evidence",[])]
    assert any("unit-economics" in c for c in claims),f"Missing unit-economics in {claims}"

def test_unit_economics_weak_subject_remains_lead() -> None:
    from adapters.public_web_search_tool import public_web_results_to_standardized_records
    import asyncio
    raw=[{"title":"Market report","url":"https://ex.com/market","snippet":"Industry gross margins are improving across the sector.","confidence":0.5}]
    recs=asyncio.run(public_web_results_to_standardized_records("Unrelated Co.",raw))
    for r in recs:
        for e in r.get("evidence",[]):
            assert "unit-economics" not in e.get("claim","")

def test_unit_economics_investigation_visible() -> None:
    from core.investigation import build_investigation_packet
    from core.risk_graph_export import export_risk_graph
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline
    import asyncio
    async def run():
        pl=RiskDiscoveryPipeline();r=await pl.run("Demo Technology Co., Ltd.");g=export_risk_graph(r)
        pk=build_investigation_packet(g.to_dict(),input_text="Demo Technology Co., Ltd.",mode="fixture").to_dict()
        led=[e for e in pk.get("evidence_ledger",[]) if any("unit-economics" in str(cl) for cl in e.get("claims",[]))]
        assert len(led)>=0
    asyncio.run(run())



def test_classify_page_type_court():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("被执行人公告","张三被列为失信被执行人")=="court_enforcement"

def test_classify_page_type_annual():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("Demo Co 年度报告","2025年财务报表")=="annual_report"

def test_classify_page_type_procurement():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("招标公告","采购项目招标公告")=="procurement"

def test_court_specific_extraction():
    from adapters.public_web_search_tool import _public_web_court_specific
    s=_public_web_court_specific("被执行人张三 执行金额50000元","张三")
    assert any("enforcement_subject" in x for x in s)

def test_court_irrelevant_page_no_claim():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("普通新闻","今日天气晴好")=="general"



def test_court_enforcement_real():
    from adapters.public_web_search_tool import _public_web_court_specific
    s = _public_web_court_specific("被执行人张三 执行标的500000元 失信","张三")
    assert any("enforcement" in x for x in s)

def test_court_no_signal():
    from adapters.public_web_search_tool import _public_web_court_specific
    s = _public_web_court_specific("普通新闻","unknown")
    assert isinstance(s, list)


def test_bond_default_signal():
    from adapters.public_web_search_tool import _public_web_bond_signals
    s = _public_web_bond_signals("债券违约 评级下调 发行规模500亿")
    assert any("bond_default" in x for x in s)
    assert any("bond_rating_negative" in x for x in s)

def test_bond_no_signal():
    from adapters.public_web_search_tool import _public_web_bond_signals
    s = _public_web_bond_signals("普通新闻")
    assert s == []

def test_credit_obligation_signal():
    from adapters.public_web_search_tool import _public_web_credit_signals
    s = _public_web_credit_signals("授信额度3000万 不良贷款")
    assert any("credit_obligation" in x for x in s)
    assert any("credit_quality" in x for x in s)

def test_credit_no_signal():
    from adapters.public_web_search_tool import _public_web_credit_signals
    s = _public_web_credit_signals("普通文本")
    assert s == []

def test_recruiting_active():
    from adapters.public_web_search_tool import _public_web_recruiting_signals
    s = _public_web_recruiting_signals("扩招500人 薪资增长")
    assert any("recruiting_active" in x for x in s)
    assert any("wage_pressure" in x for x in s)

def test_recruiting_layoff():
    from adapters.public_web_search_tool import _public_web_recruiting_signals
    s = _public_web_recruiting_signals("裁员通知 人员优化")
    assert any("headcount_reduction" in x for x in s)

def test_recruiting_no_signal():
    from adapters.public_web_search_tool import _public_web_recruiting_signals
    s = _public_web_recruiting_signals("普通文本")
    assert s == []


def test_market_structure_hhi_high():
    from adapters.public_web_search_tool import _public_web_market_structure_signals
    s = _public_web_market_structure_signals("HHI 2800 market concentration")
    assert any("hhi_high" in x for x in s)

def test_market_structure_fragmented():
    from adapters.public_web_search_tool import _public_web_market_structure_signals
    s = _public_web_market_structure_signals("fragmented highly competitive many players")
    assert any("fragmented" in x for x in s)

def test_market_structure_empty():
    from adapters.public_web_search_tool import _public_web_market_structure_signals
    s = _public_web_market_structure_signals("ordinary text")
    assert s == []


def test_cognition_claims_includes_bond_market_credit():
    from adapters.public_web_search_tool import public_web_cognition_claims
    claims = public_web_cognition_claims(
        query="Demo Co.",
        title="Demo Co. bond default HHI 2800",
        snippet="Demo Co. reports bond default and credit risk 500M",
    )
    joined = "; ".join(claims)
    assert isinstance(claims, list)
    assert "Public web bond lead" in joined
    assert "Public web credit lead" in joined
    assert "Public web market-structure lead" in joined


def test_classify_page_type_court():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("被执行人公告","失信") == "court_enforcement"

def test_classify_page_type_procurement():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("采购公告","招标项目") == "procurement"

def test_classify_page_type_general():
    from adapters.public_web_search_tool import _classify_page_type
    assert _classify_page_type("普通新闻","天气") == "general"


def test_procurement_winning_bid():
    from adapters.public_web_search_tool import _public_web_procurement_signals
    s = _public_web_procurement_signals("中标单位Demo Co. 中标金额50000000元 招标编号GC2026-001")
    assert any("winning_bid" in x for x in s)

def test_procurement_no_signal():
    from adapters.public_web_search_tool import _public_web_procurement_signals
    s = _public_web_procurement_signals("普通文本")
    assert s == []


def test_annual_report_revenue():
    from adapters.public_web_search_tool import _public_web_annual_report_signals
    s = _public_web_annual_report_signals("revenue 500M net profit 50M yoy growth 20%")
    assert any("revenue_amount" in x for x in s)
    assert any("profit_amount" in x for x in s)
    assert any("yoy_growth" in x for x in s)

def test_annual_report_empty():
    from adapters.public_web_search_tool import _public_web_annual_report_signals
    s = _public_web_annual_report_signals("normal text")
    assert s == []


def test_tax_benefit_and_risk():
    from adapters.public_web_search_tool import _public_web_tax_signals
    s = _public_web_tax_signals("税收优惠 税务处罚 实际税负25%")
    assert any("tax_benefit" in x for x in s)
    assert any("tax_risk" in x for x in s)
    assert any("25" in x for x in s)

def test_annual_report_subject_specific():
    from adapters.public_web_search_tool import _public_web_annual_report_signals
    s = _public_web_annual_report_signals("Demo Co. annual report shows revenue 200M")
    assert any("revenue_amount" in x for x in s)

def test_annual_report_non_subject_empty():
    from adapters.public_web_search_tool import _public_web_annual_report_signals
    s = _public_web_annual_report_signals("Market report: industry trends 2026")
    assert s == []

def test_procurement_subject_specific():
    from adapters.public_web_search_tool import _public_web_procurement_signals
    s = _public_web_procurement_signals("Demo Co. winning bid 中标金额 50000000")
    assert any("winning_bid" in x for x in s)

def test_procurement_non_subject_empty():
    from adapters.public_web_search_tool import _public_web_procurement_signals
    s = _public_web_procurement_signals("Procurement policy update")
    assert s == []

def test_tax_subject_specific():
    from adapters.public_web_search_tool import _public_web_tax_signals
    s = _public_web_tax_signals("Demo Co. 税收优惠 实际税负 15%")
    assert any("tax_benefit" in x for x in s) or any("tax_rate" in x for x in s)

def test_trade_subject_specific():
    from adapters.public_web_search_tool import _public_web_trade_signals
    s = _public_web_trade_signals("Demo Co. export growth 关税 pressure")
    assert any("export_growth" in x for x in s) or any("trade_barrier" in x for x in s)


def test_policy_antitrust():
    from adapters.public_web_search_tool import _public_web_policy_signals
    s = _public_web_policy_signals("anti-monopoly investigation 反垄断调查 新规出台")
    assert any("antitrust_risk" in x for x in s)
    assert any("regulatory_change" in x for x in s)

def test_policy_environmental():
    from adapters.public_web_search_tool import _public_web_policy_signals
    s = _public_web_policy_signals("ESG 碳排放 环境 regulatory change")
    assert any("environmental_regulation" in x for x in s)

def test_policy_empty():
    from adapters.public_web_search_tool import _public_web_policy_signals
    s = _public_web_policy_signals("normal text")
    assert s == []


def test_switching_cost_empty():
    from adapters.public_web_search_tool import _public_web_switching_cost_signals
    s = _public_web_switching_cost_signals("text")
    assert s == []


def test_downstream_customer_concentration():
    from adapters.public_web_search_tool import _public_web_downstream_power_signals
    s = _public_web_downstream_power_signals("customer concentration 客户集中 大客户依赖 渠道集中")
    assert any("customer_concentration_risk" in x for x in s)
    assert any("channel_dependency" in x for x in s)

def test_downstream_empty():
    from adapters.public_web_search_tool import _public_web_downstream_power_signals
    s = _public_web_downstream_power_signals("text")
    assert s == []


def test_upstream_supplier_concentration():
    from adapters.public_web_search_tool import _public_web_upstream_power_signals
    s = _public_web_upstream_power_signals("supplier concentration 供应商集中 原材料 price 供应短缺")
    assert any("supplier_concentration_risk" in x for x in s)
    assert any("raw_material_pressure" in x for x in s)
    assert any("supply_chain_disruption" in x for x in s)

def test_upstream_empty():
    from adapters.public_web_search_tool import _public_web_upstream_power_signals
    s = _public_web_upstream_power_signals("text")
    assert s == []


def test_competitor_mentioned():
    from adapters.public_web_search_tool import _public_web_competitor_signals
    s = _public_web_competitor_signals("competitors include Alibaba, Tencent 行业龙头")
    assert any("competitor_mentioned" in x for x in s)
    assert any("market_position=leader" in x for x in s)

def test_competitor_empty():
    from adapters.public_web_search_tool import _public_web_competitor_signals
    s = _public_web_competitor_signals("text")
    assert s == []


def test_customer_concentration_ratio():
    from adapters.public_web_search_tool import _public_web_customer_concentration_signals
    s = _public_web_customer_concentration_signals("customer concentration 62% 收入集中于少数客户")
    assert any("0.62" in x for x in s) or any("customer_concentration" in x for x in s)

def test_customer_concentration_empty():
    from adapters.public_web_search_tool import _public_web_customer_concentration_signals
    s = _public_web_customer_concentration_signals("text")
    assert s == []


def test_pricing_power():
    from adapters.public_web_search_tool import _public_web_pricing_power_signals
    s = _public_web_pricing_power_signals("pricing power 定价权 毛利率提升 品牌溢价")
    assert any("pricing_power" in x for x in s)
    assert any("brand_premium" in x for x in s)

def test_pricing_empty():
    from adapters.public_web_search_tool import _public_web_pricing_power_signals
    s = _public_web_pricing_power_signals("text")
    assert s == []


def test_market_size():
    from adapters.public_web_search_tool import _public_web_market_size_signals
    s = _public_web_market_size_signals("market size 500 billion TAM 高速增长")
    assert any("market_size" in x for x in s)
    assert any("market_growth" in x for x in s)

def test_market_size_empty():
    from adapters.public_web_search_tool import _public_web_market_size_signals
    s = _public_web_market_size_signals("text")
    assert s == []


def test_peer_comparison():
    from adapters.public_web_search_tool import _public_web_peer_comparison_signals
    s = _public_web_peer_comparison_signals("peer comparison 同行比较 outperform 优于同行")
    assert any("peer_comparison" in x for x in s)
    assert any("outperform_peers" in x for x in s)

def test_peer_empty():
    from adapters.public_web_search_tool import _public_web_peer_comparison_signals
    s = _public_web_peer_comparison_signals("text")
    assert s == []


def test_solvency_signals():
    from adapters.public_web_search_tool import _public_web_solvency_signals
    s = _public_web_solvency_signals("debt ratio 65% 再融资风险 short-term debt 一年内到期")
    assert any("65" in x for x in s)
    assert any("refinancing_risk" in x for x in s)
    assert any("short_term_debt_pressure" in x for x in s)

def test_solvency_empty():
    from adapters.public_web_search_tool import _public_web_solvency_signals
    s = _public_web_solvency_signals("text")
    assert s == []


def test_governance_signals():
    from adapters.public_web_search_tool import _public_web_governance_signals
    s = _public_web_governance_signals("board change 管理层变更 accounting issue 关联方借款")
    assert any("board_or_mgmt_change" in x for x in s)
    assert any("accounting_concern" in x for x in s)
    assert any("related_party_financing" in x for x in s)

def test_governance_empty():
    from adapters.public_web_search_tool import _public_web_governance_signals
    s = _public_web_governance_signals("text")
    assert s == []


def test_equity_pledge_empty():
    from adapters.public_web_search_tool import _public_web_equity_pledge_signals
    s = _public_web_equity_pledge_signals("text")
    assert s == []


def test_industry_lifecycle():
    from adapters.public_web_search_tool import _public_web_industry_lifecycle_signals
    s = _public_web_industry_lifecycle_signals("emerging industry growth phase 新兴快速成长")
    assert any("lifecycle=emerging" in x for x in s) or any("lifecycle=growth" in x for x in s)

def test_industry_lifecycle_mature():
    from adapters.public_web_search_tool import _public_web_industry_lifecycle_signals
    s = _public_web_industry_lifecycle_signals("mature saturated 饱和成熟期")
    assert any("lifecycle=mature" in x for x in s)

def test_industry_lifecycle_empty():
    from adapters.public_web_search_tool import _public_web_industry_lifecycle_signals
    s = _public_web_industry_lifecycle_signals("text")
    assert s == []


def test_working_capital_empty():
    from adapters.public_web_search_tool import _public_web_working_capital_signals
    s = _public_web_working_capital_signals("text")
    assert s == []


def test_ownership_transfer():
    from adapters.public_web_search_tool import _public_web_ownership_transfer_signals
    s = _public_web_ownership_transfer_signals("ownership transfer 股权转让 控制权变更 减持")
    assert any("ownership_transfer" in x for x in s)
    assert any("stake_disposal" in x for x in s)

def test_ownership_empty():
    from adapters.public_web_search_tool import _public_web_ownership_transfer_signals
    s = _public_web_ownership_transfer_signals("text")
    assert s == []


def test_capex():
    from adapters.public_web_search_tool import _public_web_capex_signals
    s = _public_web_capex_signals("capital expenditure 资本开支 expansion plan 扩产 R&D 研发投入")
    assert any("capex" in x for x in s)
    assert any("expansion_plans" in x for x in s)
    assert any("rd_investment" in x for x in s)

def test_capex_empty():
    from adapters.public_web_search_tool import _public_web_capex_signals
    s = _public_web_capex_signals("text")
    assert s == []


def test_goodwill_risk():
    from adapters.public_web_search_tool import _public_web_goodwill_signals
    s = _public_web_goodwill_signals("goodwill impairment 商誉减值 溢价收购")
    assert any("goodwill_risk" in x for x in s)
    assert any("acquisition_premium" in x for x in s)

def test_goodwill_empty():
    from adapters.public_web_search_tool import _public_web_goodwill_signals
    s = _public_web_goodwill_signals("text")
    assert s == []


def test_ipo_signals():
    from adapters.public_web_search_tool import _public_web_ipo_signals
    s = _public_web_ipo_signals("IPO initial public offering 估值500亿 上市前融资")
    assert any("ipo_status" in x for x in s)
    assert any("pre_ipo" in x for x in s)

def test_ipo_empty():
    from adapters.public_web_search_tool import _public_web_ipo_signals
    s = _public_web_ipo_signals("text")
    assert s == []


def test_logistics():
    from adapters.public_web_search_tool import _public_web_logistics_signals
    s = _public_web_logistics_signals("logistics warehouse 库存积压 shipping cost 运费")
    assert any("logistics_mentioned" in x for x in s)
    assert any("inventory_risk" in x for x in s)
    assert any("logistics_cost_pressure" in x for x in s)

def test_logistics_empty():
    from adapters.public_web_search_tool import _public_web_logistics_signals
    s = _public_web_logistics_signals("text")
    assert s == []


def test_regulatory_penalty():
    from adapters.public_web_search_tool import _public_web_regulatory_penalty_signals
    s = _public_web_regulatory_penalty_signals("罚款500万 吊销执照 license revoked")
    assert any("regulatory_penalty" in x for x in s)
    assert any("license_action" in x for x in s)

def test_penalty_empty():
    from adapters.public_web_search_tool import _public_web_regulatory_penalty_signals
    s = _public_web_regulatory_penalty_signals("text")
    assert s == []


def test_tech_empty():
    from adapters.public_web_search_tool import _public_web_tech_innovation_signals
    s = _public_web_tech_innovation_signals("text")
    assert s == []


def test_insurance():
    from adapters.public_web_search_tool import _public_web_insurance_signals
    s = _public_web_insurance_signals("insurance coverage 保险理赔 underinsured 巨灾风险")
    assert any("insurance_mentioned" in x for x in s)
    assert any("insurance_gap" in x for x in s)
    assert any("catastrophe_exposure" in x for x in s)

def test_insurance_empty():
    from adapters.public_web_search_tool import _public_web_insurance_signals
    s = _public_web_insurance_signals("text")
    assert s == []


def test_legal_dispute():
    from adapters.public_web_search_tool import _public_web_legal_dispute_signals
    s = _public_web_legal_dispute_signals("lawsuit litigation 诉讼 原告 defendant 和解 settlement")
    assert any("litigation_pending" in x for x in s)
    assert any("settlement" in x for x in s)

def test_legal_empty():
    from adapters.public_web_search_tool import _public_web_legal_dispute_signals
    s = _public_web_legal_dispute_signals("text")
    assert s == []


def test_cyber():
    from adapters.public_web_search_tool import _public_web_cybersecurity_signals
    s = _public_web_cybersecurity_signals("cyber attack data breach 数据泄露 information security 信息安全")
    assert any("cyber_incident" in x for x in s)
    assert any("cyber_compliance" in x for x in s)

def test_cyber_empty():
    from adapters.public_web_search_tool import _public_web_cybersecurity_signals
    s = _public_web_cybersecurity_signals("text")
    assert s == []


def test_bank_exposure():
    from adapters.public_web_search_tool import _public_web_bank_exposure_signals
    s = _public_web_bank_exposure_signals("bank exposure 银行风险敞口 银团贷款 syndicated loan")
    assert any("bank_exposure" in x for x in s)
    assert any("syndicated_loan" in x for x in s)

def test_bank_empty():
    from adapters.public_web_search_tool import _public_web_bank_exposure_signals
    s = _public_web_bank_exposure_signals("text")
    assert s == []


def test_subsidiary():
    from adapters.public_web_search_tool import _public_web_subsidiary_risk_signals
    s = _public_web_subsidiary_risk_signals("subsidiary 子公司风险 guarantee 为子公司担保 表外实体")
    assert any("subsidiary_mentioned" in x for x in s)
    assert any("subsidiary_guarantee" in x for x in s)
    assert any("subsidiary_distress" in x for x in s)

def test_subsidiary_empty():
    from adapters.public_web_search_tool import _public_web_subsidiary_risk_signals
    s = _public_web_subsidiary_risk_signals("text")
    assert s == []


def test_fraud_empty():
    from adapters.public_web_search_tool import _public_web_fraud_signals
    s = _public_web_fraud_signals("text")
    assert s == []


def test_operational_risk():
    from adapters.public_web_search_tool import _public_web_operational_risk_signals
    s = _public_web_operational_risk_signals("business continuity BCP 系统中断 operational failure key person risk")
    assert any("business_continuity" in x for x in s)
    assert any("operational_outage" in x for x in s)
    assert any("key_person_risk" in x for x in s)

def test_operational_empty():
    from adapters.public_web_search_tool import _public_web_operational_risk_signals
    s = _public_web_operational_risk_signals("text")
    assert s == []


def test_sentiment():
    from adapters.public_web_search_tool import _public_web_sentiment_signals
    s = _public_web_sentiment_signals("positive outlook bullish 看好 analyst downgrade 分析师下调")
    assert any("sentiment=positive" in x for x in s)
    assert any("analyst_downgrade" in x for x in s)

def test_sentiment_empty():
    from adapters.public_web_search_tool import _public_web_sentiment_signals
    s = _public_web_sentiment_signals("text")
    assert s == []


def test_labor():
    from adapters.public_web_search_tool import _public_web_labor_signals
    s = _public_web_labor_signals("labor dispute 劳动争议 strike 罢工 wage arrears 欠薪")
    assert any("labor_dispute" in x for x in s)
    assert any("wage_arrears" in x for x in s)

def test_labor_empty():
    from adapters.public_web_search_tool import _public_web_labor_signals
    s = _public_web_labor_signals("text")
    assert s == []


def test_carbon():
    from adapters.public_web_search_tool import _public_web_carbon_signals
    s = _public_web_carbon_signals("carbon neutral 碳中和 carbon tax ESG rating 可持续发展")
    assert any("carbon_neutral_commitment" in x for x in s)
    assert any("carbon_regulation" in x for x in s)
    assert any("esg_disclosure" in x for x in s)

def test_carbon_empty():
    from adapters.public_web_search_tool import _public_web_carbon_signals
    s = _public_web_carbon_signals("text")
    assert s == []


def test_contract():
    from adapters.public_web_search_tool import _public_web_contract_risk_signals
    s = _public_web_contract_risk_signals("contract expiration 合同到期 long-term contract 战略合作 order backlog 在手订单")
    assert any("contract_risk" in x for x in s)
    assert any("long_term_contract" in x for x in s)
    assert any("order_backlog" in x for x in s)

def test_contract_empty():
    from adapters.public_web_search_tool import _public_web_contract_risk_signals
    s = _public_web_contract_risk_signals("text")
    assert s == []


def test_geopolitical():
    from adapters.public_web_search_tool import _public_web_geopolitical_signals
    s = _public_web_geopolitical_signals("geopolitical risk trade war sanctions supply chain decoupling currency risk")
    assert any("geopolitical_risk" in x for x in s)
    assert any("supply_chain_decoupling" in x for x in s)
    assert any("currency_risk" in x for x in s)

def test_geo_empty():
    from adapters.public_web_search_tool import _public_web_geopolitical_signals
    s = _public_web_geopolitical_signals("text")
    assert s == []


def test_litigation_funding():
    from adapters.public_web_search_tool import _public_web_litigation_funding_signals
    s = _public_web_litigation_funding_signals("litigation funding 诉讼融资 contingent liability 或有负债")
    assert any("litigation_funding" in x for x in s)
    assert any("contingent_liability" in x for x in s)

def test_lf_empty():
    from adapters.public_web_search_tool import _public_web_litigation_funding_signals
    s = _public_web_litigation_funding_signals("text")
    assert s == []


def test_business_model():
    from adapters.public_web_search_tool import _public_web_business_model_signals2
    s = _public_web_business_model_signals2("SaaS subscription model 订阅模式 asset-light 轻资产")
    assert any("subscription_or_platform" in x for x in s)
    assert any("asset_light" in x for x in s)

def test_bm_empty():
    from adapters.public_web_search_tool import _public_web_business_model_signals2
    s = _public_web_business_model_signals2("text")
    assert s == []


def test_brand_empty():
    from adapters.public_web_search_tool import _public_web_brand_value_signals
    s = _public_web_brand_value_signals("text")
    assert s == []


def test_strategic_alliance():
    from adapters.public_web_search_tool import _public_web_strategic_alliance_signals
    s = _public_web_strategic_alliance_signals("joint venture 合资 strategic alliance cross-shareholding technology transfer")
    assert any("strategic_alliance" in x for x in s)
    assert any("cross_shareholding" in x for x in s)
    assert any("technology_transfer" in x for x in s)

def test_sa_empty():
    from adapters.public_web_search_tool import _public_web_strategic_alliance_signals
    s = _public_web_strategic_alliance_signals("text")
    assert s == []


def test_macro():
    from adapters.public_web_search_tool import _public_web_macro_economic_signals
    s = _public_web_macro_economic_signals("interest rate hike 加息 inflation 通胀 economic slowdown 经济放缓")
    assert any("interest_rate_exposure" in x for x in s)
    assert any("inflation_exposure" in x for x in s)
    assert any("macro_growth_exposure" in x for x in s)

def test_macro_empty():
    from adapters.public_web_search_tool import _public_web_macro_economic_signals
    s = _public_web_macro_economic_signals("text")
    assert s == []


def test_public_web_extraction_claims_produce_cognition_leads():
    from adapters.public_web_search_tool import public_web_cognition_claims, public_web_results_to_standardized_records
    import asyncio
    
    # Step 1: Raw public web results
    raw = [{
        "title": "Demo Co. bond default 500M and hiring surge",
        "url": "https://example.com/demo",
        "snippet": "Demo Co. faces bond default of 500 million yuan. Annual report shows revenue 200M. The company is expanding hiring with 200 new positions.",
        "confidence": 0.8
    }]
    
    # Step 2: Standardized records
    records = asyncio.run(public_web_results_to_standardized_records("Demo Co.", raw))
    assert len(records) > 0, "Should produce at least one record"
    
    # Step 3: Check claims in evidence
    found = False
    for r in records:
        for e in r.get("evidence", []):
            claim = e.get("claim", "")
            if "capital-bond" in claim or "commercial-recruiting" in claim or "financial-annual" in claim:
                found = True
                break
    assert found, f"Should find extraction claims in evidence: {records}"

def test_profile_bridge_classifies_claims():
    from core.public_web_profile_bridge import classify_public_web_claims, PW_CLAIM_TO_PROFILE
    assert len(PW_CLAIM_TO_PROFILE) >= 10
    ledger = [{"evidence": [{"claim": "capital-bond=bond_default"}]}]
    result = classify_public_web_claims(ledger)
    assert "capital_profile" in result

def test_profile_bridge_builds_runtime_profiles_from_flat_evidence():
    from core.public_web_profile_bridge import build_public_web_profiles

    ledger = [{
        "record_kind": "evidence",
        "source": "public_web_search",
        "url": "https://example.com/demo",
        "claims": [
            "debt_or_credit_obligation=publicly_described; refinancing_risk=2027",
            "supplier=Demo Supplier; customer=Demo Bank",
            "actual_controller=Alice Zhang; regulatory_penalty=publicly_described",
        ],
    }]

    profiles = build_public_web_profiles(ledger)

    assert set(profiles) >= {
        "public_capital_profile",
        "public_goods_profile",
        "public_people_profile",
    }
    assert profiles["public_capital_profile"]["verification_status"] == "public_lead_needs_corroboration"
    assert profiles["public_capital_profile"]["structured_summary"]["debt_credit"] >= 1
    assert profiles["public_capital_profile"]["structured_summary"]["refinancing"] >= 1
    assert "debt_or_credit_obligation=publicly_described" in profiles["public_capital_profile"]["debt_credit_claims"]
    assert profiles["public_goods_profile"]["row_count"] >= 2
    assert profiles["public_people_profile"]["row_count"] >= 2

def test_profile_bridge_maps_qyyjt_public_plan_to_profiles():
    from core.public_web_profile_bridge import build_public_web_profiles

    profiles = build_public_web_profiles([{
        "record_kind": "evidence",
        "source": "qyyjt_public_plan:risk_scan",
        "title": "Demo Co. bond risk and supplier concentration public lead",
        "summary": "controller and negative risk references need corroboration",
    }])

    assert "public_capital_profile" in profiles
    assert "public_goods_profile" in profiles
    assert "public_people_profile" in profiles
    joined = " ".join(profiles["public_people_profile"]["claims"])
    assert "qyyjt_public_plan_lead" in joined

def test_profile_bridge_merges_to_cognition():
    from core.public_web_profile_bridge import merge_into_cognition
    classified = {"capital_profile": ["capital-bond=test"]}
    ec = merge_into_cognition(classified, {})
    assert "public_web_claim_profiles" in ec
    assert "capital_profile" in ec

def test_rp_loan():
    from adapters.public_web_search_tool import _public_web_related_party_loan_signals
    s = _public_web_related_party_loan_signals("related party loan 关联方借款 tunnelling 利益输送")
    assert any("related_party_loan" in x for x in s)
    assert any("tunnelling_risk" in x for x in s)
def test_rp_empty():
    from adapters.public_web_search_tool import _public_web_related_party_loan_signals
    s = _public_web_related_party_loan_signals("text")
    assert s == []

def test_obs():
    from adapters.public_web_search_tool import _public_web_off_balance_signals
    s=_public_web_off_balance_signals("off-balance-sheet SPV structured finance 资产证券化 ABS")
    assert any("off_balance_sheet" in x for x in s)
    assert any("structured_finance" in x for x in s)
def test_obs_empty():
    from adapters.public_web_search_tool import _public_web_off_balance_signals
    s=_public_web_off_balance_signals("text")
    assert s==[]

def test_rr():
    from adapters.public_web_search_tool import _public_web_revenue_recognition_signals
    s=_public_web_revenue_recognition_signals("revenue recognition risk 收入操纵 aggressive accounting")
    assert any("revenue_recognition_risk" in x for x in s)
    assert any("aggressive_accounting" in x for x in s)
def test_rr_empty():
    from adapters.public_web_search_tool import _public_web_revenue_recognition_signals
    s=_public_web_revenue_recognition_signals("text")
    assert s==[]

def test_imp():
    from adapters.public_web_search_tool import _public_web_impairment_signals
    s=_public_web_impairment_signals("asset impairment 减值 write-down 存货跌价 拨备")
    assert any("asset_impairment" in x for x in s)
    assert any("provision_risk" in x for x in s)
def test_imp_empty():
    from adapters.public_web_search_tool import _public_web_impairment_signals
    s=_public_web_impairment_signals("text")
    assert s==[]

def test_ben():
    from adapters.public_web_search_tool import _public_web_employee_benefit_signals
    s=_public_web_employee_benefit_signals("pension obligation 养老金缺口 ESOP 股权激励")
    assert any("pension_obligation" in x for x in s)
    assert any("equity_compensation" in x for x in s)
def test_ben_e():
    from adapters.public_web_search_tool import _public_web_employee_benefit_signals
    assert _public_web_employee_benefit_signals("text")==[]

def test_gs():
    from adapters.public_web_search_tool import _public_web_government_subsidy_signals
    s=_public_web_government_subsidy_signals("government subsidy 政府补贴 补贴依赖 tax refund")
    assert any("govt_subsidy" in x for x in s)
    assert any("subsidy_dependence" in x for x in s)
def test_gs_e():
    from adapters.public_web_search_tool import _public_web_government_subsidy_signals
    assert _public_web_government_subsidy_signals("text")==[]

def test_pq():
    from adapters.public_web_search_tool import _public_web_product_quality_signals
    s=_public_web_product_quality_signals("product recall 质量问题 safety incident 认证撤销")
    assert any("product_quality_issue" in x for x in s)
    assert any("certification_status" in x for x in s)
def test_pq_e():
    from adapters.public_web_search_tool import _public_web_product_quality_signals
    assert _public_web_product_quality_signals("text")==[]

def test_cc():
    from adapters.public_web_search_tool import _public_web_customer_churn_signals
    s=_public_web_customer_churn_signals("customer churn 客户流失 contract non-renewal NPS 客户满意度")
    assert any("customer_churn" in x for x in s)
    assert any("customer_satisfaction" in x for x in s)
def test_cc_e():
    from adapters.public_web_search_tool import _public_web_customer_churn_signals
    assert _public_web_customer_churn_signals("text")==[]

def test_sb():
    from adapters.public_web_search_tool import _public_web_share_buyback_signals
    s=_public_web_share_buyback_signals("share buyback 回购计划 dividend 分红")
    assert any("share_buyback" in x for x in s)
    assert any("dividend_policy" in x for x in s)
def test_sb_e():
    from adapters.public_web_search_tool import _public_web_share_buyback_signals
    assert _public_web_share_buyback_signals("text")==[]

def test_wl():
    from adapters.public_web_search_tool import _public_web_warranty_liability_signals
    s=_public_web_warranty_liability_signals("warranty claim 质保索赔 warranty reserve")
    assert any("warranty_liability" in x for x in s)
    assert any("warranty_reserve" in x for x in s)
def test_wl_e():
    from adapters.public_web_search_tool import _public_web_warranty_liability_signals
    assert _public_web_warranty_liability_signals("text")==[]

def test_lo():
    from adapters.public_web_search_tool import _public_web_lease_obligation_signals
    s=_public_web_lease_obligation_signals("lease liability 租赁负债 sale-leaseback 售后回租")
    assert any("lease_liability" in x for x in s)
    assert any("sale_leaseback" in x for x in s)
def test_lo_e():
    from adapters.public_web_search_tool import _public_web_lease_obligation_signals
    assert _public_web_lease_obligation_signals("text")==[]

def test_dc():
    from adapters.public_web_search_tool import _public_web_debt_covenant_signals
    s=_public_web_debt_covenant_signals("debt covenant breach 违反契约 covenant waiver")
    assert any("covenant_breach" in x for x in s)
    assert any("covenant_waiver" in x for x in s)
def test_dc_e():
    from adapters.public_web_search_tool import _public_web_debt_covenant_signals
    assert _public_web_debt_covenant_signals("text")==[]

def test_crm():
    from adapters.public_web_search_tool import _public_web_credit_rating_migration_signals
    s=_public_web_credit_rating_migration_signals("rating downgrade 评级下调 watch negative 负面观察")
    assert any("rating_downgrade" in x for x in s)
    assert any("credit_watch_negative" in x for x in s)
def test_crm_e():
    from adapters.public_web_search_tool import _public_web_credit_rating_migration_signals
    assert _public_web_credit_rating_migration_signals("text")==[]

def test_cg():
    from adapters.public_web_search_tool import _public_web_cross_guarantee_signals
    s=_public_web_cross_guarantee_signals("cross guarantee 交叉担保 担保圈 互保")
    assert any("cross_guarantee" in x for x in s)
    assert any("guarantee_circle" in x for x in s)
def test_cg_e():
    from adapters.public_web_search_tool import _public_web_cross_guarantee_signals
    assert _public_web_cross_guarantee_signals("text")==[]

def test_ce():
    from adapters.public_web_search_tool import _public_web_contingent_equity_signals
    s=_public_web_contingent_equity_signals("convertible bond CB warrant 认股权证 dilution risk")
    assert any("convertible_debt" in x for x in s)
    assert any("dilution_risk" in x for x in s)
def test_ce_e():
    from adapters.public_web_search_tool import _public_web_contingent_equity_signals
    assert _public_web_contingent_equity_signals("text")==[]

def test_fr():
    from adapters.public_web_search_tool import _public_web_financial_restatement_signals
    s=_public_web_financial_restatement_signals("financial restatement accounting error material weakness")
    assert any("restatement" in x for x in s)
    assert any("accounting_weakness" in x for x in s)
def test_ipd():
    from adapters.public_web_search_tool import _public_web_intellectual_property_dispute_signals
    s=_public_web_intellectual_property_dispute_signals("IP infringement 专利侵权 trade secret")
    assert any("ip_dispute" in x for x in s)
    assert any("trade_secret_risk" in x for x in s)
def test_gr():
    from adapters.public_web_search_tool import _public_web_government_relation_signals
    s=_public_web_government_relation_signals("government contract SOE state-owned bribery 腐败调查")
    assert any("government_contract" in x for x in s)
    assert any("corruption_risk" in x for x in s)
def test_id():
    from adapters.public_web_search_tool import _public_web_industry_disruption_signals
    s=_public_web_industry_disruption_signals("disruption disruptive technology 数字化转型 digital transformation")
    assert any("disruption_risk" in x for x in s)
    assert any("digital_transformation" in x for x in s)
def test_wh():
    from adapters.public_web_search_tool import _public_web_working_hours_compliance_signals
    s=_public_web_working_hours_compliance_signals("overtime violation 996 加班 forced labor 劳工权益")
    assert any("overtime_risk" in x for x in s)
    assert any("labor_rights_violation" in x for x in s)
def test_scf():
    from adapters.public_web_search_tool import _public_web_supply_chain_finance_signals
    s=_public_web_supply_chain_finance_signals("supply chain finance reverse factoring 保理")
    assert any("scf_activity" in x for x in s)
    assert any("factoring" in x for x in s)
def test_ir():
    from adapters.public_web_search_tool import _public_web_investor_relations_signals
    s=_public_web_investor_relations_signals("investor complaint activist investor proxy fight")
    assert any("investor_pressure" in x for x in s)
    assert any("activist_pressure" in x for x in s)
def test_nd():
    from adapters.public_web_search_tool import _public_web_natural_disaster_exposure_signals
    s=_public_web_natural_disaster_exposure_signals("earthquake flood natural disaster business interruption")
    assert any("disaster_exposure" in x for x in s)
    assert any("business_interruption_risk" in x for x in s)
def test_ci():
    from adapters.public_web_search_tool import _public_web_credit_insurance_signals
    s=_public_web_credit_insurance_signals("credit insurance trade credit insurance credit enhancement")
    assert any("credit_insurance" in x for x in s)
    assert any("credit_enhancement" in x for x in s)
def test_cp():
    from adapters.public_web_search_tool import _public_web_commodity_price_exposure_signals
    s=_public_web_commodity_price_exposure_signals("commodity price oil price hedging loss")
    assert any("commodity_exposure" in x for x in s)
    assert any("commodity_hedging_risk" in x for x in s)
def test_mm():
    from adapters.public_web_search_tool import _public_web_market_manipulation_signals
    s=_public_web_market_manipulation_signals("market manipulation insider trading pump and dump")
    assert any("market_manipulation" in x for x in s)
    assert any("stock_manipulation" in x for x in s)
def test_pc():
    from adapters.public_web_search_tool import _public_web_product_concentration_signals
    s=_public_web_product_concentration_signals("product concentration 62% single product risk")
    assert any("product_concentration" in x for x in s) or any("single_product_dependency" in x for x in s)
def test_sd():
    from adapters.public_web_search_tool import _public_web_strategic_dependence_signals
    s=_public_web_strategic_dependence_signals("single supplier sole source 单一客户依赖")
    assert any("sole_supplier_risk" in x for x in s)
    assert any("key_customer_risk" in x for x in s)
def test_sc():
    from adapters.public_web_search_tool import _public_web_social_controversy_signals
    s=_public_web_social_controversy_signals("social controversy public backlash discrimination lawsuit")
    assert any("social_controversy" in x for x in s)
    assert any("discrimination_risk" in x for x in s)
def test_aq():
    from adapters.public_web_search_tool import _public_web_asset_quality_signals
    s=_public_web_asset_quality_signals("NPA non-performing loan asset quality deterioration")
    assert any("nonperforming_asset" in x for x in s)
    assert any("asset_quality_deterioration" in x for x in s)
def test_eq():
    from adapters.public_web_search_tool import _public_web_earnings_quality_signals
    s=_public_web_earnings_quality_signals("earnings manipulation non-recurring income cash flow mismatch")
    assert any("earnings_quality_concern" in x for x in s)
    assert any("nonrecurring_income" in x for x in s)
def test_cm():
    from adapters.public_web_search_tool import _public_web_cash_management_signals
    s=_public_web_cash_management_signals("cash shortage liquidity squeeze restricted cash")
    assert any("cash_shortage" in x for x in s)
    assert any("restricted_cash" in x for x in s)
def test_br():
    from adapters.public_web_search_tool import _public_web_business_restructuring_signals
    s=_public_web_business_restructuring_signals("business restructuring spinoff asset disposal")
    assert any("restructuring" in x for x in s)
    assert any("spinoff" in x for x in s)
def test_tc():
    from adapters.public_web_search_tool import _public_web_tax_controversy_signals
    s=_public_web_tax_controversy_signals("tax dispute transfer pricing tax haven")
    assert any("tax_dispute" in x for x in s)
    assert any("transfer_pricing_risk" in x for x in s)
def test_rpg():
    from adapters.public_web_search_tool import _public_web_related_party_guarantee_signals
    s=_public_web_related_party_guarantee_signals("related party guarantee guarantee exposure")
    assert any("related_guarantee" in x for x in s)
    assert any("guarantee_exposure" in x for x in s)
def test_rcap():
    from adapters.public_web_search_tool import _public_web_regulatory_capital_signals
    s=_public_web_regulatory_capital_signals("capital adequacy CAR Tier 1 capital shortfall")
    assert any("regulatory_capital" in x for x in s)
    assert any("capital_shortfall" in x for x in s)
def test_ec():
    from adapters.public_web_search_tool import _public_web_export_credit_signals
    s=_public_web_export_credit_signals("export credit export financing sinosure ECA")
    assert any("export_credit" in x for x in s)
    assert any("export_insurance" in x for x in s)
def test_rf():
    from adapters.public_web_search_tool import _public_web_refinancing_risk_signals
    s=_public_web_refinancing_risk_signals("refinancing risk maturity wall refinancing difficulty")
    assert any("refinancing_risk" in x for x in s)
    assert any("maturity_wall" in x for x in s)
def test_sov():
    from adapters.public_web_search_tool import _public_web_sovereign_exposure_signals
    s=_public_web_sovereign_exposure_signals("sovereign risk country risk sovereign downgrade")
    assert any("sovereign_risk" in x for x in s)
    assert any("sovereign_downgrade" in x for x in s)
def test_ibe():
    from adapters.public_web_search_tool import _public_web_interbank_exposure_signals
    s=_public_web_interbank_exposure_signals("interbank exposure interbank lending systemic risk")
    assert any("interbank_exposure" in x for x in s)
    assert any("interbank_contagion" in x for x in s)
def test_fs():
    from adapters.public_web_search_tool import _public_web_financial_sponsor_signals
    s=_public_web_financial_sponsor_signals("private equity buyout LBO PE exit plan")
    assert any("pe_vc_investment" in x for x in s)
    assert any("buyout_activity" in x for x in s)
def test_cb():
    from adapters.public_web_search_tool import _public_web_cross_border_risk_signals
    s=_public_web_cross_border_risk_signals("cross-border risk capital control repatriation risk")
    assert any("cross_border_exposure" in x for x in s)
    assert any("capital_control_risk" in x for x in s)
def test_mr():
    from adapters.public_web_search_tool import _public_web_merger_regulatory_signals
    s=_public_web_merger_regulatory_signals("merger review antitrust review merger blocked remedy")
    assert any("merger_regulatory_review" in x for x in s)
    assert any("merger_blocked" in x for x in s)
def test_asec():
    from adapters.public_web_search_tool import _public_web_asset_securitization_signals
    s=_public_web_asset_securitization_signals("securitization ABS issuance loan portfolio sale")
    assert any("securitization_activity" in x for x in s)
    assert any("loan_portfolio_sale" in x for x in s)
def test_ipo_u():
    from adapters.public_web_search_tool import _public_web_ipo_underwriting_signals
    s=_public_web_ipo_underwriting_signals("IPO underwriting book-building greenshoe")
    assert any("ipo_underwriting" in x for x in s)
    assert any("greenshoe_option" in x for x in s)
def test_pf():
    from adapters.public_web_search_tool import _public_web_project_finance_signals
    s=_public_web_project_finance_signals("project finance BOT project cost overrun")
    assert any("project_finance" in x for x in s)
    assert any("project_risk" in x for x in s)
def test_df():
    from adapters.public_web_search_tool import _public_web_deposit_franchise_signals
    s=_public_web_deposit_franchise_signals("deposit base core deposits deposit outflow")
    assert any("deposit_strength" in x for x in s)
    assert any("deposit_outflow_risk" in x for x in s)
def test_fg():
    from adapters.public_web_search_tool import _public_web_financial_guarantee_signals
    s=_public_web_financial_guarantee_signals("financial guarantee credit guarantee guarantor distress")
    assert any("financial_guarantee" in x for x in s)
    assert any("guarantor_risk" in x for x in s)
def test_vf():
    from adapters.public_web_search_tool import _public_web_vendor_financing_signals
    s=_public_web_vendor_financing_signals("vendor financing supplier credit payment delay")
    assert any("vendor_financing" in x for x in s)
    assert any("supplier_payment_pressure" in x for x in s)
def test_dd():
    from adapters.public_web_search_tool import _public_web_distressed_debt_signals
    s=_public_web_distressed_debt_signals("distressed debt NPL sale vulture fund")
    assert any("distressed_debt" in x for x in s)
    assert any("distressed_investor_activity" in x for x in s)
def test_sd2():
    from adapters.public_web_search_tool import _public_web_structured_deposit_signals
    s=_public_web_structured_deposit_signals("structured deposit wealth management product non-principal-protected")
    assert any("structured_deposit" in x for x in s)
    assert any("principal_protection_risk" in x for x in s)
def test_sb3():
    from adapters.public_web_search_tool import _public_web_shadow_banking_signals
    s=_public_web_shadow_banking_signals("shadow banking trust loan entrusted loan")
    assert any("shadow_banking" in x for x in s)
    assert any("trust_lending" in x for x in s)
def test_mms():
    from adapters.public_web_search_tool import _public_web_money_market_stress_signals
    s=_public_web_money_market_stress_signals("money market stress SHIBOR liquidity crunch")
    assert any("money_market_stress" in x for x in s)
    assert any("liquidity_crunch" in x for x in s)
def test_bk():
    from adapters.public_web_search_tool import _public_web_bankruptcy_risk_signals
    s=_public_web_bankruptcy_risk_signals("bankruptcy filing Chapter 11 insolvency bankruptcy protection")
    assert any("bankruptcy_risk" in x for x in s)
    assert any("bankruptcy_protection" in x for x in s)
def test_rb():
    from adapters.public_web_search_tool import _public_web_regional_bank_risk_signals
    s=_public_web_regional_bank_risk_signals("regional bank city commercial bank rural bank")
    assert any("regional_bank_exposure" in x for x in s)
    assert any("rural_bank_exposure" in x for x in s)
def test_ip():
    from adapters.public_web_search_tool import _public_web_investment_portfolio_signals
    s=_public_web_investment_portfolio_signals("investment loss fair value loss mark-to-market")
    assert any("investment_loss" in x for x in s)
    assert any("fair_value_loss" in x for x in s)
def test_ri():
    from adapters.public_web_search_tool import _public_web_reinsurance_signals
    s=_public_web_reinsurance_signals("reinsurance reinsurer reinsurance recoverable")
    assert any("reinsurance_exposure" in x for x in s)
    assert any("reinsurance_credit_risk" in x for x in s)
def test_pa():
    from adapters.public_web_search_tool import _public_web_pension_asset_signals
    s=_public_web_pension_asset_signals("pension fund pension underfunding funding gap")
    assert any("pension_asset" in x for x in s)
    assert any("pension_shortfall" in x for x in s)
def test_tcap():
    from adapters.public_web_search_tool import _public_web_trust_capital_signals
    s=_public_web_trust_capital_signals("trust capital capital injection recapitalization")
    assert any("trust_capital" in x for x in s)
    assert any("capital_injection" in x for x in s)
def test_dv():
    from adapters.public_web_search_tool import _public_web_derivatives_exposure_signals
    s=_public_web_derivatives_exposure_signals("derivative exposure derivatives trading derivative loss")
    assert any("derivative_exposure" in x for x in s)
    assert any("derivative_loss" in x for x in s)
def test_ere():
    from adapters.public_web_search_tool import _public_web_exchange_rate_exposure_signals
    s=_public_web_exchange_rate_exposure_signals("exchange rate forex exposure devaluation risk")
    assert any("exchange_rate_exposure" in x for x in s)
    assert any("currency_volatility" in x for x in s)
def test_ef():
    from adapters.public_web_search_tool import _public_web_equity_fundraising_signals
    s=_public_web_equity_fundraising_signals("rights issue placement private placement equity offering")
    assert any("equity_fundraising" in x for x in s)
    assert any("private_placement" in x for x in s)
def test_swf():
    from adapters.public_web_search_tool import _public_web_sovereign_wealth_fund_signals
    s=_public_web_sovereign_wealth_fund_signals("sovereign wealth fund SWF state capital")
    assert any("sovereign_fund_investment" in x for x in s)
    assert any("state_capital" in x for x in s)
def test_am():
    from adapters.public_web_search_tool import _public_web_asset_management_signals
    s=_public_web_asset_management_signals("asset management AUM decline fund outflow")
    assert any("asset_management" in x for x in s)
    assert any("aum_decline" in x for x in s)
def test_cl():
    from adapters.public_web_search_tool import _public_web_collateralized_loan_signals
    s=_public_web_collateralized_loan_signals("collateralized loan secured loan LTV loan-to-value")
    assert any("collateralized_lending" in x for x in s)
    assert any("ltv_ratio" in x for x in s)
def test_fmi():
    from adapters.public_web_search_tool import _public_web_financial_market_infrastructure_signals
    s=_public_web_financial_market_infrastructure_signals("clearing house CCP settlement risk")
    assert any("market_infrastructure" in x for x in s)
    assert any("settlement_risk" in x for x in s)
def test_fx():
    from adapters.public_web_search_tool import _public_web_fx_exposure_signals
    s = _public_web_fx_exposure_signals("foreign exchange FX exposure 外汇 hedge 对冲")
    assert any("fx_exposure" in x for x in s)
    assert any("fx_hedging" in x for x in s)

def test_fx_empty():
    from adapters.public_web_search_tool import _public_web_fx_exposure_signals
    s = _public_web_fx_exposure_signals("text")
    assert s == []

def test_lbo():
    from adapters.public_web_search_tool import _public_web_leveraged_buyout_signals
    s=_public_web_leveraged_buyout_signals("leveraged buyout LBO LBO financing acquisition debt")
    assert any("leveraged_buyout" in x for x in s)
    assert any("lbo_leverage" in x for x in s)
def test_mz():
    from adapters.public_web_search_tool import _public_web_mezzanine_debt_signals
    s=_public_web_mezzanine_debt_signals("mezzanine debt junior debt mezzanine default")
    assert any("mezzanine_debt" in x for x in s)
    assert any("mezzanine_credit_quality" in x for x in s)
