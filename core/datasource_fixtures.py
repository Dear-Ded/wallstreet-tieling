#!/usr/bin/env python3
"""Datasource fixture packs for connector contracts and demos.

These fixtures are not claims about a real company. They are executable
reference records for connector authors: every public, bot-delivered, or
licensed provider should be able to map its output into this shape before it
enters the evidence graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatasourceFixturePack:
    """Named standardized-record fixtures for one company."""

    company: str
    public_registry: list[dict[str, Any]]
    official_global: list[dict[str, Any]]
    public_web: list[dict[str, Any]]
    telegram_delivery: list[dict[str, Any]]
    licensed_api: list[dict[str, Any]]

    def all_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        records.extend(self.public_registry)
        records.extend(self.official_global)
        records.extend(self.public_web)
        records.extend(self.telegram_delivery)
        records.extend(self.licensed_api)
        return records

    def by_source_family(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "public_registry": self.public_registry,
            "official_global": self.official_global,
            "public_web": self.public_web,
            "telegram_delivery": self.telegram_delivery,
            "licensed_api": self.licensed_api,
        }


def build_datasource_fixture_pack(company: str) -> DatasourceFixturePack:
    """Return reference standardized records for the main connector families."""
    seed = " ".join(str(company).split()) or "Demo Intelligence Co., Ltd."
    return DatasourceFixturePack(
        company=seed,
        public_registry=_public_registry_records(seed),
        official_global=_official_global_records(seed),
        public_web=_public_web_records(seed),
        telegram_delivery=_telegram_delivery_records(seed),
        licensed_api=_licensed_api_records(seed),
    )


def _public_registry_records(company: str) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "public_registry",
            "source_type": "official_platform",
            "source_hint": "registry_sources",
            "entity": company,
            "title": f"{company} public registry profile",
            "summary": (
                "Public registry fixture: legal representative Alice Zhang, "
                "actual controller Bob Li, registered address No. 1 Finance Road."
            ),
            "url": "https://example.invalid/registry/profile",
            "published_at": "2026-06-20",
            "confidence": 0.86,
            "raw": {
                "legal_representative": "Alice Zhang",
                "actual_controller": {"name": "Bob Li"},
                "registered_address": "No. 1 Finance Road, Tieling",
                "website": "www.demo-intel.example",
            },
            "evidence": [
                {"claim": "Alice Zhang is listed as legal representative in the public registry fixture."},
                {"claim": "Bob Li is listed as actual-controller candidate in the public registry fixture."},
                {"claim": "No. 1 Finance Road is the registered-address lead."},
            ],
        }
    ]


def _official_global_records(company: str) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "gleif_lei_public_api",
            "source_type": "rest_api",
            "source_hint": "gleif_lei_public_api",
            "entity": company,
            "title": f"GLEIF LEI record: {company}",
            "summary": (
                "Official global fixture: LEI record links the entity to a registration authority "
                "and an ultimate parent lead that should be verified through official relationship records."
            ),
            "url": "https://search.gleif.org/#/record/5493001KJTIIGC8Y1R12",
            "published_at": "2026-06-20",
            "confidence": 0.86,
            "raw": {
                "lei": "5493001KJTIIGC8Y1R12",
                "registration_authority": "RA000001",
                "ultimate_parent": "Demo Holdings Ltd.",
            },
            "evidence": [
                {"claim": "GLEIF fixture provides an LEI identity lead for the company."},
                {"claim": "GLEIF fixture provides an ultimate-parent relationship lead."},
            ],
        },
        {
            "source_name": "sec_edgar_public_api",
            "source_type": "rest_api",
            "source_hint": "sec_edgar_public_api",
            "entity": company,
            "title": f"SEC EDGAR submissions: {company}",
            "summary": (
                "Official capital-market fixture: recent 10-K and 8-K filings indicate that "
                "public disclosure history should be reviewed for ownership, related-party, and liquidity signals."
            ),
            "url": "https://www.sec.gov/edgar/browse/?CIK=0000320193",
            "published_at": "2026-06-20",
            "confidence": 0.82,
            "raw": {
                "cik": "0000320193",
                "ticker": "DEMO",
                "recent_filings": ["10-K 2025-10-31", "8-K 2026-01-15"],
            },
            "evidence": [
                {
                    "claim": (
                        "Public industry signal: industry=enterprise risk intelligence; "
                        "industry_growth=0.09; capacity_growth=0.06; price_change=0.02; "
                        "customer_power=0.54; supplier_power=0.32; sources=SEC business overview fixture"
                    )
                },
                {
                    "claim": (
                        "Public product signal: product=counterparty risk platform; "
                        "product_revenue_growth=0.12; repeat_purchase_rate=0.81; "
                        "core_product_revenue_ratio=0.68; substitute_performance_gap=0.18; "
                        "substitute_price_advantage=0.06; customer_churn_rate=0.08; "
                        "customer_value=continuous counterparty monitoring and evidence workflow"
                    )
                },
                {"claim": "Public goods signal: supplier=Acme Components Ltd; customer=BigCo Electronics; product=SmartWidget X1; industry=consumer electronics; sources=SEC fixture"},
                {"claim": "Public goods signal: supplier=Acme Components Ltd; customer=BigCo Electronics; product=SmartWidget X1; industry=consumer electronics; sources=SEC fixture"},
                {"claim": "SEC fixture provides a public issuer disclosure lead."},
                {"claim": "Recent filing types should be reviewed for related-party and capital-market risk signals."},
                {
                    "claim": (
                        "SEC EDGAR companyfacts: cik=0000320193; revenue=1285000000; "
                        "net_income=142000000; operating_cash_flow=188000000; "
                        "net_margin=0.1105; cash_conversion=1.3239; debt_to_assets=0.418"
                    )
                },
                {
                    "claim": (
                        "Public capital pressure signal: debt_exposure=sizable; refinancing_risk=2027_maturity_wall; "
                        "credit_profile=investment_grade_watch; financing_event=2025_convertible_offering; "
                        "equity_fundraising=ATM_program_active; sources=SEC fixture"
                    )
                },
                {
                    "claim": (
                        "Public people signal: ownership=Bob_Li_54pct_indirect; controller=Bob_Li; "
                        "key_person=Alice_Zhang_CEO; administrative_penalty=late_filing_fine_2025; "
                        "related_party=Demo_Holdings_Ltd; sources=SEC fixture"
                    )
                },
            ],
        },
    ]


def _public_web_records(company: str) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "public_web_search",
            "source_type": "search_engine",
            "source_hint": "public_account_sources",
            "entity": company,
            "title": f"{company} public web footprint",
            "summary": (
                "Public web fixture: company website, recruitment page, and public account lead. "
                "A complaint keyword appears in one public page and needs verification."
            ),
            "url": "https://example.invalid/public-web/company-footprint",
            "published_at": "2026-06-20",
            "confidence": 0.64,
            "raw": {
                "domain": "www.demo-intel.example",
                "public_account": "@demo_intel_public",
                "contact_email": "contact@demo-intel.example",
            },
            "evidence": [
                {"claim": "The public web fixture links the company to www.demo-intel.example."},
                {"claim": "A public complaint lead is present and should be corroborated."},
                {"claim": "Public people signal: court_enforcement=IP_dispute_2024; dishonesty_blacklist=supplier_listed; common_address=Suite_500_Finance_Road_Tieling; sources=public web fixture"},
                {"claim": "Public people signal: common_project=Smart_Grid_Phase_2; regulatory_action=CFIUS_review_pending; license_change=export_license_revoked; sources=public web fixture"},

                {"claim": "Public competitive landscape signal: competitor_set=publicly_mentioned; competitive_position=market_challenger; competitive_dynamics=new_entrants_active; market_share=0.12; competitor_count=8; barrier_to_entry=moderate; sources=public web fixture"},
            {"claim": "Public supply chain signal: supply_chain=verified; upstream_count=3; customer_count=5; customer_concentration=0.42; supplier_concentration=0.35; upstream=Raw_Materials_Group_Ltd.; supplier=Semiconductor Components Ltd.; customer=Enterprise Risk Solutions Inc.; sources=public web fixture"},
                {"claim": "Public market position lead: market_share=0.12; competitor_count=8; barrier_to_entry=moderate; industry_growth=0.09; sources=public web fixture"},

            ],
        }
    ]


def _telegram_delivery_records(company: str) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "fixture_telegram_public_service:demo_bot",
            "source_type": "telegram_bot",
            "source_hint": "telegram_bot_public_service",
            "entity": company,
            "title": f"{company} public-service delivery lead",
            "summary": (
                "Telegram delivery fixture: public bot returned a registry aggregation lead. "
                "The delivery channel is Telegram; the underlying data must still be public and auditable."
            ),
            "published_at": "2026-06-20",
            "confidence": 0.52,
            "raw": {
                "bot_handle": "@demo_public_registry_bot",
                "source_description": "public registry aggregation fixture",
                "returned_text": f"{company}: related person Bob Li; related company Demo Holdings Ltd.",
            },
            "evidence": [
                {"claim": "Telegram public-service fixture returned Bob Li as a related-person lead."},
                {"claim": "Telegram delivery metadata includes bot handle and source description."},
            ],
        }
    ]


def _licensed_api_records(company: str) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "fixture_licensed_registry_api",
            "source_type": "licensed_api",
            "source_hint": "registry_and_commercial_sources",
            "entity": company,
            "title": f"{company} licensed risk enrichment",
            "summary": (
                "Licensed API fixture: provider reports an administrative penalty lead, "
                "a court enforcement watch item, and a controller-change risk event."
            ),
            "url": "https://example.invalid/licensed-api/risk-profile",
            "published_at": "2026-06-20",
            "confidence": 0.78,
            "raw": {
                "case_no": "fixture-2026-enforcement-001",
                "actual_controller": {"name": "Bob Li"},
                "asset": "Vehicle collateral public notice",
            },
            "risk_events": [
                {
                    "risk_category": "ownership",
                    "severity": "high",
                    "title": "Controller change signal",
                    "summary": "Fixture provider marked a controller-change risk event.",
                    "confidence": 0.8,
                }
            ],
            "evidence": [
                {"claim": "Administrative penalty lead requires source verification."},
                {"claim": "Court enforcement watch item requires docket verification."},
                {"claim": "Controller-change risk event is provider-supplied fixture metadata."},
            ],
        }
    ]
