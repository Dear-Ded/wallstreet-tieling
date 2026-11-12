"""Regressions found by the v0.6.0 availability / data-accuracy audit (2026-11-12).

Each test pins a defect that was reproduced against live public sources:

* Wikidata answered HTTP 403 to the bare ``wallstreet-tieling/0.6.0`` UA.
* SEC companyfacts mixed 9-month YTD / quarter figures into "revenue".
* GLEIF branch records (e.g. lapsed ICBC 分行/支行) were admitted as facts
  about the head office.
* Missing cash flow / ROE = 0 still produced an "优秀" financial grade.
* A packet with no evidence in any lane printed "Overall: LOW RISK".
* Eastmoney F10 lost the company survey when the holders endpoint failed.
* Beijing Stock Exchange 920xxx codes were routed to Shanghai.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

from adapters.eastmoney_f10_adapter import EastmoneyF10Lookup, normalize_stock_code
from adapters.multi_datasource import (
    DataSourceConfig,
    QueryRequest,
    RestApiDataSource,
    _wikimedia_compliant_headers,
)
from core.crawl_presets import xueqiu_symbol
from core.financial_analyzer_v2 import EnhancedFinancialAnalyzer, FinancialHealthGrade
from core.intelligence_retrieval import EntityResolutionScorer
from core.investigation import _build_subject_due_diligence_profile

ROOT = Path(__file__).resolve().parents[2]
SEC_SAMPLE = ROOT / "tests" / "fixtures" / "live_samples" / "sec_companyfacts_aapl_asof_20260731.json"


# --- Wikidata User-Agent -----------------------------------------------------

def test_wikidata_template_user_agent_carries_contact_information() -> None:
    payload = yaml.safe_load((ROOT / "adapters" / "multi_datasource" / "datasources.yaml").read_text(encoding="utf-8"))
    source = next(item for item in payload["sources"] if item["name"] == "wikidata_public_entity_graph")
    ua = source["headers"]["User-Agent"]
    assert "(" in ua and "https://" in ua


def test_wikimedia_headers_upgrade_bare_user_agent_only() -> None:
    assert "(+https://" in _wikimedia_compliant_headers({"User-Agent": "wallstreet-tieling/0.6.0"})["User-Agent"]
    assert "(+https://" in _wikimedia_compliant_headers({})["User-Agent"]
    custom = {"user-agent": "acme-dd/1.0 (ops@acme.example)"}
    assert _wikimedia_compliant_headers(custom) == custom


def test_wikidata_request_is_sent_with_contact_user_agent() -> None:
    class _Response:
        status = 200
        headers = {"content-type": "application/json"}
        content_length = None

        def raise_for_status(self) -> None:
            return None

        async def json(self):
            return {"search": []}

        async def text(self):
            return json.dumps({"search": []})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Session:
        closed = False

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def get(self, url, params=None, headers=None, **kwargs):
            self.calls.append({"url": url, "params": params, "headers": headers})
            return _Response()

        async def close(self):
            self.closed = True

    source = RestApiDataSource(
        DataSourceConfig(
            name="wikidata_public_entity_graph",
            type="rest_api",
            base_url="https://www.wikidata.org/w",
            headers={"Accept": "application/json", "User-Agent": "wallstreet-tieling/0.6.0"},
            custom={"provider_type": "wikidata_entity_search"},
            rate_limit={"enabled": False},
        )
    )
    session = _Session()

    async def _get_session():
        return session

    source._get_session = _get_session  # type: ignore[method-assign]
    asyncio.run(source.query(QueryRequest(query="Kweichow Moutai")))
    assert session.calls, "wikidata request was not issued"
    sent_ua = session.calls[0]["headers"]["User-Agent"]
    assert sent_ua.startswith("wallstreet-tieling/0.6.0 (")


# --- SEC companyfacts reporting period ----------------------------------------

def _sec_source() -> RestApiDataSource:
    return RestApiDataSource(
        DataSourceConfig(
            name="sec_edgar_public_api",
            type="rest_api",
            base_url="https://data.sec.gov",
            custom={"provider_type": "sec_edgar"},
            rate_limit={"enabled": False},
        )
    )


def test_sec_companyfacts_prefers_fiscal_year_over_ytd_interim_live_sample() -> None:
    raw = json.loads(SEC_SAMPLE.read_text(encoding="utf-8"))
    record = _sec_source()._format_sec_companyfacts_result(raw)["standardized_records"][0]
    metrics = record["raw"]["metrics"]

    # Live sample as of 2026-07-31: the latest end date (2026-06-27) only has
    # the 9-month YTD (364,357M) and the 3-month quarter (109,417M). The
    # fiscal-year total is FY2025 (ended 2025-09-27) = 416,161M per the 10-K.
    assert metrics["revenue"]["val"] == 416161000000
    assert metrics["revenue"]["period_type"] == "fiscal_year"
    assert metrics["revenue"]["start"] == "2024-09-29"
    assert metrics["net_income"]["val"] == 112010000000
    assert metrics["operating_cash_flow"]["val"] == 111482000000
    assert "period=fiscal_year" in record["summary"]
    assert "3.64357e+11" not in record["summary"]
    assert record["raw"]["period_mismatches"] == []
    assert abs(record["raw"]["ratios"]["net_margin"] - 112010 / 416161) < 1e-9


def test_sec_companyfacts_does_not_mix_periods_in_ratios() -> None:
    raw = {
        "cik": "1",
        "entityName": "Interim Only Co.",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    {"start": "2026-01-01", "end": "2026-06-30", "val": 600, "fp": "Q2", "form": "10-Q", "filed": "2026-08-01"},
                ]}},
                "NetIncomeLoss": {"units": {"USD": [
                    {"start": "2026-04-01", "end": "2026-06-30", "val": 50, "fp": "Q2", "form": "10-Q", "filed": "2026-08-01"},
                ]}},
            }
        },
    }
    record = _sec_source()._format_sec_companyfacts_result(raw)["standardized_records"][0]
    assert record["raw"]["metrics"]["revenue"]["period_type"] == "year_to_date"
    assert record["raw"]["metrics"]["net_income"]["period_type"] == "quarter"
    assert record["raw"]["ratios"]["net_margin"] is None
    assert any(item.startswith("net_margin:") for item in record["raw"]["period_mismatches"])


# --- Entity resolution: branches are not the head office ---------------------

def test_branch_record_is_not_a_strong_match_for_head_office() -> None:
    for branch in ("中国工商银行股份有限公司汕头分行", "中国工商银行股份有限公司乡宁支行", "中国工商银行股份有限公司重庆市分行"):
        match = EntityResolutionScorer.score("中国工商银行股份有限公司", branch)
        assert match["level"] == "review", (branch, match)
        assert any("branch or sub-unit" in reason for reason in match["reasons"])
    exact = EntityResolutionScorer.score("中国工商银行股份有限公司", "中国工商银行股份有限公司")
    assert exact["level"] == "exact"


def test_single_token_containment_stays_review_level() -> None:
    match = EntityResolutionScorer.score("贵州茅台酒股份有限公司", "贵州茅台酒股份有限公司销售")
    assert match["level"] in {"review", "weak"}
    assert match["score"] < 0.82


# --- Financial grade: missing data is not health ------------------------------

def test_missing_operating_cash_flow_does_not_grade_as_healthy() -> None:
    analyzer = EnhancedFinancialAnalyzer()
    result = asyncio.run(analyzer.analyze_financial_health({"revenue": 1000, "net_profit": 100, "roe": 0.2}))
    assert result["cash_flow_analysis"]["health_status"] == "未知"
    assert result["health_grade"] not in {FinancialHealthGrade.EXCELLENT.value, FinancialHealthGrade.GOOD.value}


def test_zero_roe_is_never_graded_excellent() -> None:
    analyzer = EnhancedFinancialAnalyzer()
    result = asyncio.run(analyzer.analyze_financial_health({"roe": 0.0, "operating_cash_flow": 5, "debt_to_equity": 0.2}))
    assert "净资产收益率过低" in result["financial_risk"]["warning_flags"]
    assert result["health_grade"] != FinancialHealthGrade.EXCELLENT.value


def test_complete_healthy_input_can_still_grade_excellent() -> None:
    analyzer = EnhancedFinancialAnalyzer()
    result = asyncio.run(
        analyzer.analyze_financial_health(
            {"roe": 0.3, "debt_to_equity": 0.2, "operating_cash_flow": 120, "investing_cash_flow": -20, "net_profit": 100, "revenue": 400}
        )
    )
    assert result["health_grade"] == FinancialHealthGrade.EXCELLENT.value


# --- DD executive summary ------------------------------------------------------

def test_dd_overall_risk_is_unknown_when_no_lane_has_evidence() -> None:
    profile = _build_subject_due_diligence_profile(
        company="贵州茅台酒股份有限公司",
        financial=None,
        fund_flow_profile=None,
        goods_flow_profile=None,
        people_flow_profile=None,
        cross_lane_insights=[],
        supply_chain_profile=None,
        legal_administrative_profile=None,
        public_capital_profile=None,
        public_goods_profile=None,
        public_people_profile=None,
        risk_events=[],
        next_questions=[],
        evidence_gaps=[],
    )
    summary = profile["executive_summary"]
    assert {summary["capital_risk"], summary["goods_risk"], summary["people_risk"]} == {"unknown"}
    assert summary["overall_risk"] == "unknown"


# --- Eastmoney F10 -------------------------------------------------------------

def test_eastmoney_holders_failure_keeps_company_survey() -> None:
    survey = {"jbzl": {"gsmc": "贵州茅台酒股份有限公司", "agdm": "600519", "gsdj": "9152000071430580XT"}, "SecuCode": "600519.SH"}

    class _Lookup(EastmoneyF10Lookup):
        @staticmethod
        def _http_get_json(url: str, headers: dict):
            if "datacenter-web" in url:
                raise ValueError("Expecting value: line 1 column 1 (char 0)")
            return survey

    lookup = _Lookup(robots_checker=lambda domain, url: True, sleeper=lambda s: None)
    result = lookup.query("600519")
    assert result["error"] == ""
    assert result["fields"]["company_name"] == "贵州茅台酒股份有限公司"
    assert result["fields"]["credit_code"] == "9152000071430580XT"
    assert "top_holders" not in result["fields"]
    assert result["fields"]["top_holders_gap"]["reason"] == "holders_fetch_failed"


# --- Ticker mapping -------------------------------------------------------------

def test_beijing_920_codes_and_shanghai_funds_map_to_the_right_exchange() -> None:
    assert xueqiu_symbol("920185") == "BJ920185"
    assert xueqiu_symbol("830799") == "BJ830799"
    assert xueqiu_symbol("510300") == "SH510300"
    assert xueqiu_symbol("600519") == "SH600519"
    assert xueqiu_symbol("900901") == "SH900901"
    assert xueqiu_symbol("000001") == "SZ000001"
    assert normalize_stock_code("920185") == "BJ920185"
    assert normalize_stock_code("600519") == "SH600519"


# --- Identifier extraction: generic keys must not cross-file identifiers --------

def test_gleif_lei_in_generic_id_is_not_filed_as_wikidata_qid() -> None:
    from core.intelligence_retrieval import EvidenceIngestor

    extract = EvidenceIngestor._record_identifier_attributes
    gleif = extract({"raw": {"id": "HWUPKR0MPOU8FGXBT394", "lei": "HWUPKR0MPOU8FGXBT394"}})
    assert "wikidata_id" not in gleif
    assert gleif["lei"] == "HWUPKR0MPOU8FGXBT394"
    wikidata = extract({"raw": {"id": "Q312"}})
    assert wikidata["wikidata_id"] == "Q312"


def test_stock_code_in_generic_code_is_not_filed_as_uscc() -> None:
    from core.intelligence_retrieval import EvidenceIngestor

    extract = EvidenceIngestor._record_identifier_attributes
    assert "unified_social_credit_code" not in extract({"raw": {"code": "600519"}})
    assert extract({"raw": {"code": "9152000071430580XT"}})["unified_social_credit_code"] == "9152000071430580XT"
    assert "unified_social_credit_code" not in EntityResolutionScorer.score("贵州茅台", "贵州茅台", {"code": "600519"})["identifiers"]


# --- Lane ratings: leads are not a low-risk clearance --------------------------------

def test_lane_with_only_public_leads_is_unknown_not_low() -> None:
    profile = _build_subject_due_diligence_profile(
        company="Demo Lead Only Co.",
        financial=None,
        fund_flow_profile=None,
        goods_flow_profile=None,
        people_flow_profile=None,
        cross_lane_insights=[],
        supply_chain_profile=None,
        legal_administrative_profile=None,
        public_capital_profile={"row_count": 2, "claims": ["financing lead"]},
        public_goods_profile={"row_count": 1, "claims": ["market lead"]},
        public_people_profile={"row_count": 0, "claims": []},
        risk_events=[],
        next_questions=[],
        evidence_gaps=["people lane has no facts"],
    )
    summary = profile["executive_summary"]
    assert summary["capital_risk"] == "unknown"
    assert summary["goods_risk"] == "unknown"
    assert summary["people_risk"] == "unknown"
    assert summary["overall_risk"] == "unknown"
    from core.investigation import _build_human_readable_dd_summary

    rendered = _build_human_readable_dd_summary(profile)
    assert "People: INSUFFICIENT DATA" in rendered
    assert "People: LOW RISK (0 signals)" not in rendered


def test_people_lane_with_public_lead_key_persons_is_unknown_not_low() -> None:
    profile = _build_subject_due_diligence_profile(
        company="贵州茅台酒股份有限公司",
        financial=None,
        fund_flow_profile=None,
        goods_flow_profile=None,
        people_flow_profile={
            "controller_signals": ["陈华"],
            "key_person_signals": ["legal_rep=陈华"],
            "verification_status": "public_lead",
            "fact_count": 0,
            "lead_count": 4,
        },
        cross_lane_insights=[],
        supply_chain_profile=None,
        legal_administrative_profile=None,
        public_capital_profile=None,
        public_goods_profile=None,
        public_people_profile={
            "row_count": 1,
            "claims": ["legal_rep=陈华"],
            "verification_status": "public_lead_needs_corroboration",
        },
        risk_events=[],
        next_questions=[],
        evidence_gaps=["people lane has no official facts"],
    )
    summary = profile["executive_summary"]
    assert summary["people_risk"] == "unknown"
    assert summary["overall_risk"] == "unknown"
    from core.investigation import _build_human_readable_dd_summary

    rendered = _build_human_readable_dd_summary(profile)
    assert "People: INSUFFICIENT DATA" in rendered
    assert "People: LOW RISK" not in rendered


def test_people_lane_relationship_only_profile_is_unknown() -> None:
    profile = _build_subject_due_diligence_profile(
        company="Apple Inc.",
        financial={"revenue": 478834000000, "net_income": 132175000000},
        fund_flow_profile=None,
        goods_flow_profile=None,
        people_flow_profile={
            "controller_signals": [],
            "key_person_signals": ["relationship_network_subjects=7;relations=7"],
            "relationship_signals": [
                "relation_types=mentioned_with,registered_address,headquarters_address",
                "Apple Inc.->C/O C T Corporation System;relation=registered_address;confidence=0.82",
            ],
            "verification_status": "relationship_or_legal_only_needs_controller_corroboration",
        },
        cross_lane_insights=[],
        supply_chain_profile=None,
        legal_administrative_profile=None,
        public_capital_profile=None,
        public_goods_profile=None,
        public_people_profile=None,
        risk_events=[],
        next_questions=[],
        evidence_gaps=["people lane has no controller facts"],
    )
    summary = profile["executive_summary"]
    assert summary["people_risk"] == "unknown"
    assert summary["capital_risk"] == "low"
    assert summary["overall_risk"] == "unknown"
    from core.investigation import _build_human_readable_dd_summary

    rendered = _build_human_readable_dd_summary(profile)
    assert "People: INSUFFICIENT DATA" in rendered
    assert "People: LOW RISK (0 signals)" not in rendered
