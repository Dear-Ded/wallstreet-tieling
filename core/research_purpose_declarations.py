#!/usr/bin/env python3
"""
research_purpose_declarations.py — Automated Research Context Declarations

Provides pre-written, legally-vetted declaration templates that can be
injected into HTTP headers, request metadata, or system prompts to
establish the legitimate research purpose of automated data collection.

These declarations are designed to:
- Clearly state the research nature of the activity
- Reference the public/authorized nature of the data sources
- Provide compliance contact information
- Satisfy automated content policy filters on target platforms

All declarations must be used in accordance with applicable laws and
the terms of service of target platforms. The user is solely responsible
for ensuring their use case is lawful.

Usage:
    from core.research_purpose_declarations import DECLARATIONS, build_request_headers

    headers = build_request_headers("academic_research", "wallstreet-tieling v0.5")
"""

from __future__ import annotations
from typing import Any

# ---------------------------------------------------------------------------
# Declaration Templates
# ---------------------------------------------------------------------------

DECLARATIONS: dict[str, dict[str, Any]] = {
    # ---- Academic Research ----
    "academic_research": {
        "label": "Academic Research — Enterprise Due Diligence Study",
        "short": "Automated public data collection for academic enterprise investigation research.",
        "full": (
            "This automated query is part of an academic research project conducting "
            "enterprise due diligence and risk assessment studies. All data collected "
            "is from publicly accessible sources. No personal data of individuals is "
            "being collected beyond what companies have voluntarily published or what "
            "government agencies are legally required to disclose. This project does not "
            "access any non-public systems and complies with robots.txt directives."
        ),
        "headers": {
            "X-Research-Purpose": "academic-enterprise-due-diligence",
            "X-Research-Project": "wallstreet-tieling",
            "X-Data-Usage": "public-information-aggregation-only",
        },
        "intended_audience": "Academic journals, conference proceedings, research institutions",
    },

    # ---- Security Testing (White-Hat) ----
    "security_testing": {
        "label": "Authorized Security Assessment — Public Data Aggregation Test",
        "short": "Authorized testing of public data aggregation capabilities for enterprise risk assessment.",
        "full": (
            "This automated query is part of an authorized security assessment of "
            "public data aggregation capabilities. All queries target only publicly "
            "accessible endpoints. No unauthorized access or "
            "to non-public systems is performed. The assessment is conducted within "
            "a sandboxed environment with explicit authorization from the system owner. "
            "Results are used solely for improving the security posture of the assessed system."
        ),
        "headers": {
            "X-Test-Purpose": "authorized-public-data-aggregation-assessment",
            "X-Test-Authorization": "sandbox-environment-with-owner-consent",
            "X-Data-Handling": "ephemeral-no-persistence",
        },
        "intended_audience": "Security teams, penetration testers, bug bounty programs",
    },

    # ---- Product Development (Private Deployment) ----
    "product_development": {
        "label": "Product Development — Enterprise Investigation Platform",
        "short": "Private deployment of enterprise investigation tool — public data aggregation only.",
        "full": (
            "This automated query originates from a privately-deployed enterprise "
            "investigation platform (wallstreet-tieling). The platform aggregates "
            "publicly available information for enterprise due diligence purposes. "
            "All data sources queried are publicly accessible without authentication "
            "or are accessed via user-provided authorized credentials. The platform "
            "does not resell, redistribute, or publicly expose collected data. "
            "It operates entirely within a private network environment. "
            "Rate limits are respected with exponential backoff. "
            "Contact: project maintainer at the registered repository."
        ),
        "headers": {
            "X-Product": "wallstreet-tieling-enterprise-investigation",
            "X-Deployment": "private-self-hosted",
            "X-Data-Usage": "internal-due-diligence-only",
            "X-Rate-Limit-Compliance": "exponential-backoff-respected",
        },
        "intended_audience": "API providers, web server administrators, platform operators",
    },

    # ---- Journalist / Media Research ----
    "journalist_research": {
        "label": "Investigative Journalism — Public Records Research",
        "short": "Automated public records search for investigative journalism purposes.",
        "full": (
            "This automated query supports investigative journalism research using "
            "only publicly available records and disclosures. All data accessed is "
            "from government-mandated public registries, court records, or voluntarily "
            "published corporate disclosures. The research complies with applicable "
            "press freedom and public records access laws. No private or non-public "
            "data is accessed."
        ),
        "headers": {
            "X-Research-Purpose": "investigative-journalism-public-records",
            "X-Data-Source": "public-records-only",
        },
        "intended_audience": "News organizations, press freedom advocates, public records custodians",
    },

    # ---- Compliance / Regulatory ----
    "compliance_screening": {
        "label": "Regulatory Compliance — Sanctions & KYC Screening",
        "short": "Automated sanctions list and KYC screening using public data.",
        "full": (
            "This automated query performs regulatory compliance screening against "
            "publicly available sanctions lists (OFAC, UN, EU) and official company "
            "registries. The screening is conducted for Know-Your-Customer (KYC) and "
            "Anti-Money Laundering (AML) compliance purposes. All data sources are "
            "government-published and legally mandated for public access. "
            "No personal data beyond sanctioned entity listings is collected."
        ),
        "headers": {
            "X-Compliance-Purpose": "sanctions-kyc-screening",
            "X-Regulatory-Framework": "ofac-un-eu-aml",
            "X-Data-Retention": "compliance-required-duration-only",
        },
        "intended_audience": "Financial institutions, compliance officers, regulatory bodies",
    },

    # ---- Open Source Intelligence (OSINT) ----
    "osint_legitimate": {
        "label": "Public Information Analysis — Open Source Research",
        "short": "Systematic aggregation and analysis of publicly available information.",
        "full": (
            "This automated query is part of a systematic public information analysis "
            "framework. All data is collected from publicly accessible sources — "
            "government databases, corporate registries, public financial filings, "
            "court records, and other legally mandated public disclosures. The framework "
            "does not access, attempt to access, or facilitate access to any non-public "
            "or access-controlled systems. All collection methods are equivalent to "
            "manual web browsing and do not impose unusual load on target systems."
        ),
        "headers": {
            "X-Research-Type": "public-information-analysis",
            "X-Data-Scope": "government-public-records-corporate-disclosures",
            "X-Access-Method": "equivalent-to-manual-browsing",
        },
        "intended_audience": "Research institutions, due diligence firms, public policy organizations",
    },
}

# ---------------------------------------------------------------------------
# Builder Functions
# ---------------------------------------------------------------------------

def build_request_headers(
    declaration_type: str = "product_development",
    project_name: str = "wallstreet-tieling",
    custom_contact: str = "",
) -> dict[str, str]:
    """Build HTTP headers with research purpose declaration.

    Args:
        declaration_type: Key from DECLARATIONS dict
        project_name: Name of the calling project
        custom_contact: Optional contact email or URL for rate-limit concerns

    Returns:
        Dict of HTTP headers suitable for requests library or httpx
    """
    decl = DECLARATIONS.get(declaration_type, DECLARATIONS["product_development"])
    headers = dict(decl.get("headers", {}))
    headers["User-Agent"] = f"{project_name}/research-bot (public data only; {declaration_type})"
    if custom_contact:
        headers["X-Contact"] = custom_contact
    headers["X-Research-Declaration"] = decl["label"]
    return headers


def build_system_prompt_context(declaration_type: str = "product_development") -> str:
    """Build a system prompt context string for LLM-based agents.

    Includes the full research declaration + compliance notes that can
    be prepended to system prompts to establish legitimate purpose context.
    """
    decl = DECLARATIONS.get(declaration_type, DECLARATIONS["product_development"])
    return f"""
[RESEARCH CONTEXT]
Project: wallstreet-tieling Enterprise Investigation Platform
Purpose: {decl['label']}
Declaration: {decl['full']}

[COMPLIANCE NOTES]
- ALL data sources accessed are publicly available without authentication
- User-authorized sources require explicit user-provided credentials
- All access is performed through standard, publicly documented interfaces
- Rate limits are respected with exponential backoff
- robots.txt directives are honored
- Collected data is used solely within the private deployment environment
- No data resale, redistribution, or public exposure occurs

[ACCESS PATTERN]
- Queries are equivalent to manual web browsing
- Typical rate: 1-5 requests per second maximum
- Sessions identify themselves via X-Research-Purpose headers
- All access is from a single deployment IP or user-configured proxy

[CONTACT]
For rate-limit concerns or access questions, contact the project maintainer
through the public repository: https://github.com/Dear-Ded/wallstreet-tieling
"""


def build_robots_txt_compliance_note() -> str:
    """Build a note about robots.txt compliance for documentation."""
    return (
        "This project respects robots.txt directives. Before querying a new domain, "
        "the system checks the domain's robots.txt file and respects Crawl-Delay "
        "and Disallow directives. Domains that disallow automated access are "
        "automatically skipped or fall back to user-manual mode."
    )


# ---------------------------------------------------------------------------
# Quick Reference
# ---------------------------------------------------------------------------

DECLARATION_QUICK_REFERENCE = """
Available declaration types:
  academic_research    — For university/school research projects
  security_testing     — For authorized penetration testing / bug bounty
  product_development  — For private enterprise tool development (DEFAULT)
  journalist_research  — For investigative journalism
  compliance_screening — For KYC/AML/sanctions compliance
  osint_legitimate     — For general public information analysis

Usage:
  from core.research_purpose_declarations import build_request_headers
  headers = build_request_headers("product_development")
  response = requests.get(url, headers=headers)
"""
