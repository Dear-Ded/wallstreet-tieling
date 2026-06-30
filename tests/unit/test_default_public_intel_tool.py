#!/usr/bin/env python3
"""Tests for the default public intelligence fan-out tool."""
from __future__ import annotations

from adapters.default_public_intel_tool import DefaultPublicIntelTool
from adapters.public_web_search_tool import PublicWebSearchTool
from adapters.qyyjt_adapter import QYYJTModule
from adapters.qyyjt_tool import QYYJTTool
from core.investigation import build_investigation_packet
from core.risk_discovery_pipeline import RiskDiscoveryPipeline
from core.risk_graph_export import export_risk_graph


class FakeQYYJTAdapter:
    def __init__(self):
        self.cookie_manager = FakeCookieManager()
        self.queried_companies = []
        self.queried_modules = []

    def get_module_query(self, module, company):
        return {
            "module": module.value,
            "module_name": module.name,
            "company": company,
            "queries": [f"{company} {module.value}"],
        }

    async def query(self, company, modules, prefer_api):
        assert prefer_api is False
        self.queried_companies.append(company)
        self.queried_modules.append([module.value for module in modules])
        return {
            "company": company,
            "api_data": {},
            "websearch_queries": [
                {
                    "module": "risk_scan",
                    "module_name": "RISK_SCAN",
                    "query": f"site:qyyjt.cn {company} risk",
                    "note": "default public QYYJT lead",
                }
            ],
        }


class FakeCookieManager:
    async def test_cookies_valid(self):
        return False


class SlowPublicWeb:
    def health_check(self):
        return {"ok": True, "default_enabled": True}

    async def search(self, query: str, tool_type: str, **kwargs):
        import asyncio

        await asyncio.sleep(1)
        raise AssertionError("slow public web child should be timed out by default fan-out")


class FakeCreditChinaAdapter:
    source_domain = "www.creditchina.gov.cn"
    data_boundary = "fully_public"
    requires_credentials = False

    def __init__(self):
        self.audit = self
        self.queries = []

    def query(self, keyword: str, **params):
        self.queries.append((keyword, params))
        return {
            "source_domain": self.source_domain,
            "source_type": "government_public_disclosure",
            "data_boundary": self.data_boundary,
            "response_status": 200,
            "fields": {
                "penalty_count": 1,
                "disclosure_type": "government_administrative_penalty",
            },
            "field_count": 2,
            "error": "",
        }

    def get_trail(self):
        return [
            {
                "source_domain": self.source_domain,
                "data_boundary": self.data_boundary,
                "operation_type": "public_record_query",
            }
        ]


async def _http_get(url: str):
    return {
        "Heading": "Demo Default Co.",
        "AbstractText": "Public company profile.",
        "AbstractURL": "https://example.com/default-company",
    }


async def _http_get_product(url: str):
    return {
        "Heading": "Demo RiskIntel Co. risk intelligence platform",
        "AbstractText": (
            "Demo RiskIntel Co. is a technology company offering a "
            "counterparty risk intelligence platform for due diligence teams. "
            "Customers include Bank Alpha. Suppliers include Demo Cloud Ltd. "
            "Partners include Demo Integrator. Downstream markets include "
            "compliance workflow teams. Customer concentration was 62%."
        ),
        "AbstractURL": "https://example.com/demo-riskintel",
    }


def create_tool() -> DefaultPublicIntelTool:
    adapter = FakeQYYJTAdapter()
    return DefaultPublicIntelTool(
        public_web=PublicWebSearchTool(),
        qyyjt=QYYJTTool(adapter=adapter, modules=[QYYJTModule.RISK_SCAN])
    )


def test_default_public_intel_health_is_default_enabled() -> None:
    health = create_tool().health_check()

    assert health["ok"] is True
    assert health["default_enabled"] is True
    assert health["default_public_entry"] is True
    assert "public_web_search" in health["enabled_sources"]
    assert "qyyjt" in health["enabled_sources"]
    assert "telegram_bot_public_service" in health["enabled_sources"]
    assert "creditchina_public" in health["children"]
    assert "creditchina_public" not in health["enabled_sources"]


def test_default_public_intel_exposes_source_routing_health_report() -> None:
    from core.risk_discovery_pipeline import RiskDiscoveryPipeline

    adapter = FakeCreditChinaAdapter()
    tool = DefaultPublicIntelTool(
        public_web=PublicWebSearchTool(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        creditchina=adapter,
        enabled_sources=("creditchina_public",),
    )

    assert tool.list_sources() == ["creditchina_public"]
    assert tool.available_sources() == ["creditchina_public"]

    report = tool.health_report()
    assert report["creditchina_public"]["ok"] is True
    assert report["creditchina_public"]["enabled"] is True
    assert report["creditchina_public"]["data_boundary"] == "fully_public"
    assert report["creditchina_public"]["smoke_tested"] is True
    assert report["creditchina_public"]["smoke_test_file"] == "tests/unit/test_source_smoke.py"
    assert report["qyyjt"]["enabled"] is False

    snapshot = RiskDiscoveryPipeline._source_routing_snapshot(tool)
    assert snapshot["configured_sources"] == ["creditchina_public"]
    assert snapshot["available_sources"] == ["creditchina_public"]
    assert snapshot["health_reports"]["creditchina_public"]["smoke_tested"] is True


async def test_default_public_intel_can_explicitly_run_creditchina_public() -> None:
    adapter = FakeCreditChinaAdapter()
    tool = DefaultPublicIntelTool(
        public_web=PublicWebSearchTool(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        creditchina=adapter,
        enabled_sources=("creditchina_public",),
    )

    result = await tool.search(
        "Demo Admin Risk Co.",
        "default_public_intel",
        creditchina_options={"page": 2},
    )

    assert result.ok is True
    assert adapter.queries == [("Demo Admin Risk Co.", {"page": 2})]
    assert result.data["queried_sources"] == ["creditchina_public"]
    assert result.data["source_diagnostics"] == [
        {
            "source_name": "creditchina_public",
            "status": "success",
            "record_count": 1,
            "error": "",
        }
    ]
    record = result.data["standardized_records"][0]
    assert record["source_name"] == "creditchina_public"
    assert record["source_profile"]["authority"] == "official"
    assert result.data["record_quality"]["ok"] is True


async def test_default_public_intel_fans_out_public_records() -> None:
    adapter = FakeQYYJTAdapter()
    tool = create_tool()
    tool.qyyjt = QYYJTTool(adapter=adapter, modules=[QYYJTModule.RISK_SCAN])

    result = await tool.search(
        "Demo Default Co.",
        "default_public_intel",
        company="Demo Default Co.",
        public_web_options={"http_get": _http_get},
    )

    assert result.ok is True
    assert result.data["default_public_entry"] is True
    assert result.data["record_quality"]["ok"] is True
    assert result.data["queried_sources"] == [
        "public_web_search",
        "qyyjt",
        "telegram_bot_public_service",
    ]
    source_names = {record["source_name"] for record in result.data["standardized_records"]}
    assert "public_web_search" in source_names
    assert "qyyjt_websearch_plan" in source_names
    assert adapter.queried_companies == ["Demo Default Co."]


async def test_default_public_intel_limits_entity_anchor_sources_by_layer() -> None:
    adapter = FakeQYYJTAdapter()
    tool = create_tool()
    tool.qyyjt = QYYJTTool(adapter=adapter, modules=[QYYJTModule.RISK_SCAN])

    result = await tool.search(
        "Demo Anchor Co.",
        "default_public_intel",
        company="Demo Anchor Co.",
        retrieval_layer="entity_anchor",
        public_web_options={"http_get": _http_get},
    )

    assert result.ok is True
    assert result.data["retrieval_layer"] == "entity_anchor"
    assert result.data["selected_sources"] == ("public_web_search", "qyyjt")
    assert result.data["queried_sources"] == ["public_web_search", "qyyjt"]
    assert adapter.queried_companies == ["Demo Anchor Co."]
    assert adapter.queried_modules == [["search_multi", "ent_basic"]]


async def test_default_public_intel_executes_qyyjt_public_plan_queries() -> None:
    class CapturingPublicWeb:
        def __init__(self):
            self.queries = []

        def health_check(self):
            return {"ok": True, "default_enabled": True}

        async def search(self, query: str, tool_type: str, **kwargs):
            self.queries.append(query)
            return await PublicWebSearchTool().search(
                query,
                "public_web_search",
                results=[
                    {
                        "title": "QYYJT plan public result",
                        "url": "https://example.com/qyyjt-plan",
                        "snippet": "Public result from an executed QYYJT plan query.",
                    }
                ],
            )

    public_web = CapturingPublicWeb()
    tool = DefaultPublicIntelTool(
        public_web=public_web,
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("qyyjt",),
    )

    result = await tool.search(
        "Demo QYYJT Plan Co.",
        "default_public_intel",
        company="Demo QYYJT Plan Co.",
        qyyjt_public_plan_limit=1,
    )

    source_names = {record["source_name"] for record in result.data["standardized_records"]}
    assert result.ok is True
    assert public_web.queries == ["site:qyyjt.cn Demo QYYJT Plan Co. risk"]
    assert "qyyjt_websearch_plan" in source_names
    assert "qyyjt_public_plan:risk_scan" in source_names
    assert result.data["source_diagnostics"][0]["record_count"] >= 2


async def test_qyyjt_public_plan_results_reach_packet_without_fixture_bridge(tmp_path) -> None:
    class CapturingPublicWeb:
        def health_check(self):
            return {"ok": True, "default_enabled": True}

        async def search(self, query: str, tool_type: str, **kwargs):
            return await PublicWebSearchTool().search(
                query,
                "public_web_search",
                results=[
                    {
                        "title": "Demo QYYJT Plan Co. public risk result",
                        "url": "https://example.com/qyyjt-plan-risk",
                        "snippet": (
                            "Demo QYYJT Plan Co. disclosed a negative news lead "
                            "and a supplier concentration risk in public materials."
                        ),
                    }
                ],
            )

    tool = DefaultPublicIntelTool(
        public_web=CapturingPublicWeb(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("qyyjt",),
    )
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = await pipeline.run(
        "Demo QYYJT Plan Co.",
        search_engine=tool,
        retrieval_concurrency=1,
        query_timeout_seconds=8,
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo QYYJT Plan Co.",
        mode="standard",
    ).to_dict()

    evidence_sources = {item.get("source") for item in packet["evidence_ledger"]}
    top_sources = {item.get("source") for item in packet["source_provenance"]["top_sources"]}
    trace_sources = {
        item.get("source")
        for item in packet["enterprise_cognition"]["investigation_report_card"]["dd_summary"]["evidence_to_report_trace"]
    }

    assert "qyyjt_public_plan:risk_scan" in evidence_sources
    assert "qyyjt_public_plan:risk_scan" in top_sources
    assert "qyyjt_public_plan:risk_scan" in trace_sources
    assert "fixture_bridge" not in evidence_sources
    assert "fixture_bridge" not in top_sources
    assert "SEC fixture" not in trace_sources
    diagnostic = next(
        item
        for item in result.source_diagnostics
        if item.get("source_name") == "default_public_intel"
        and item.get("qyyjt_public_plan_executed") == 1
    )
    assert diagnostic["qyyjt_public_plan_executed"] == 1
    assert diagnostic["qyyjt_public_plan_failed"] == 0
    assert diagnostic["child_source_diagnostics"][0]["source_name"] == "qyyjt"
    assert diagnostic["qyyjt_public_plan_diagnostics"][0]["status"] == "success"
    public_plan_summary = result.retrieval_summary["public_plan_summary"]
    assert public_plan_summary["qyyjt_public_plan_executed"] >= 1
    assert public_plan_summary["qyyjt_public_plan_failed"] == 0
    assert public_plan_summary["triggered_attempts"] >= 1


async def test_default_public_intel_applies_layer_result_budgets_without_overriding_options() -> None:
    class BudgetPublicWeb:
        def __init__(self):
            self.max_results = []

        def health_check(self):
            return {"ok": True, "default_enabled": True}

        async def search(self, query: str, tool_type: str, **kwargs):
            self.max_results.append(kwargs.get("max_results"))
            return await PublicWebSearchTool().search(
                query,
                "public_web_search",
                http_get=_http_get,
                max_results=kwargs.get("max_results"),
            )

    adapter = FakeQYYJTAdapter()
    public_web = BudgetPublicWeb()
    tool = DefaultPublicIntelTool(
        public_web=public_web,
        qyyjt=QYYJTTool(adapter=adapter, modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("public_web_search", "qyyjt"),
    )

    result = await tool.search(
        "Demo Budget Co.",
        "default_public_intel",
        company="Demo Budget Co.",
        retrieval_layer="prioritized_drilldown",
        public_web_options={"max_results": 2},
        qyyjt_options={"modules": [QYYJTModule.NEWS_NEGATIVE]},
        execute_qyyjt_public_plan=False,
    )

    assert result.ok is True
    assert public_web.max_results == [2]
    assert adapter.queried_modules == [["news_negative"]]


async def test_default_public_intel_times_out_slow_child_without_losing_fast_records() -> None:
    adapter = FakeQYYJTAdapter()
    tool = DefaultPublicIntelTool(
        public_web=SlowPublicWeb(),
        qyyjt=QYYJTTool(adapter=adapter, modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("public_web_search", "qyyjt"),
    )

    result = await tool.search(
        "Demo Timeout Co.",
        "default_public_intel",
        company="Demo Timeout Co.",
        child_timeout_seconds=0.1,
    )

    source_names = {record["source_name"] for record in result.data["standardized_records"]}

    assert result.ok is True
    assert result.data["failed_sources"] == ["public_web_search"]
    assert "qyyjt_websearch_plan" in source_names
    assert adapter.queried_companies == ["Demo Timeout Co."]


async def test_default_public_intel_child_failure_reaches_pipeline_packet(tmp_path) -> None:
    tool = DefaultPublicIntelTool(
        public_web=SlowPublicWeb(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("public_web_search", "qyyjt"),
    )
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = await pipeline.run(
        "Demo Child Failure Co.",
        search_engine=tool,
        retrieval_concurrency=1,
        query_timeout_seconds=1,
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo Child Failure Co.",
    ).to_dict()

    child_failures = [
        item for item in result.source_diagnostics
        if item.get("diagnostic_scope") == "child_source" and item.get("status") == "failed"
    ]

    assert result.ok is True
    assert "default_public_intel" in result.queried_sources
    assert "public_web_search" in result.failed_sources
    assert child_failures
    assert child_failures[0]["parent_source_name"] == "default_public_intel"
    assert result.retrieval_summary["status_counts"]["failed"] >= 1
    assert packet["source_failure_summary"]["failure_count"] >= 1
    assert "source_failures_present" in packet["quality_gate"]["warnings"]


async def test_default_public_intel_feeds_risk_discovery_pipeline(tmp_path) -> None:
    class PipelinePublicWeb:
        def health_check(self):
            return {"ok": True, "default_enabled": True}

        async def search(self, query: str, tool_type: str, **kwargs):
            return await PublicWebSearchTool().search(
                query,
                "public_web_search",
                http_get=_http_get,
            )

    tool = DefaultPublicIntelTool(
        public_web=PipelinePublicWeb(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
    )
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = await pipeline.run(
        "Demo Default Co.",
        search_engine=tool,
        retrieval_concurrency=2,
    )

    assert result.ok is True
    assert result.evidence_count >= 1
    assert "default_public_intel" in result.queried_sources


async def test_default_public_intel_skips_unsupported_specialized_source_hints(tmp_path) -> None:
    from core.official_public_smoke import build_official_public_smoke_plan

    tool = create_tool()
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")
    plan = build_official_public_smoke_plan("Demo Specialized Source Co.")
    plan.tasks = [task for task in plan.tasks if task.source_hint == "sec_edgar_public_api"]

    result = await pipeline.run(
        "Demo Specialized Source Co.",
        search_engine=tool,
        existing_plan=plan,
        retrieval_concurrency=1,
    )

    assert result.failed_sources == []
    assert result.queried_sources == []
    assert result.source_diagnostics[0]["status"] == "skipped_unsupported_source"
    assert result.source_diagnostics[0]["source_hint"] == "sec_edgar_public_api"
    assert result.source_diagnostics[0]["source_name"] == "sec_edgar_public_api"
    assert result.retrieval_summary["execution_state"] == "no_evidence_found"
    assert result.retrieval_summary["status_counts"] == {"skipped_unsupported_source": 1}


async def test_default_public_intel_public_web_leads_reach_industry_product_packet(tmp_path) -> None:
    class PipelinePublicWeb:
        def health_check(self):
            return {"ok": True, "default_enabled": True}

        async def search(self, query: str, tool_type: str, **kwargs):
            return await PublicWebSearchTool().search(
                query,
                "public_web_search",
                http_get=_http_get_product,
            )

    tool = DefaultPublicIntelTool(
        public_web=PipelinePublicWeb(),
        qyyjt=QYYJTTool(adapter=FakeQYYJTAdapter(), modules=[QYYJTModule.RISK_SCAN]),
        enabled_sources=("public_web_search",),
    )
    pipeline = RiskDiscoveryPipeline(risk_event_store=tmp_path / "risk-events.jsonl")

    result = await pipeline.run(
        "Demo RiskIntel Co.",
        search_engine=tool,
        retrieval_concurrency=1,
    )
    packet = build_investigation_packet(
        export_risk_graph(result).to_dict(),
        input_text="Demo RiskIntel Co.",
    ).to_dict()

    assert result.evidence_count >= 1
    assert packet["enterprise_cognition"]["industry"]["industry"] == "technology"
    assert packet["enterprise_cognition"]["product"]["product_name"] == "risk intelligence platform"
    assert packet["enterprise_cognition"]["supply_chain_profile"]["customer_count"] == 1
    assert packet["enterprise_cognition"]["supply_chain_profile"]["supplier_count"] == 1
    assert "## 供应链与商业版图" in packet["report_markdown"]
    assert "Bank Alpha" in packet["report_markdown"]
