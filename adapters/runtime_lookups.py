"""Optional runtime lookup adapters for explicit due-diligence enrichment.

These adapters are intentionally not part of the default one-click public
intelligence fan-out. They are for deployment owners who configure credentials
and explicitly enable deeper vendor/security/identity review workflows.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from adapters.safe_research_adapter import SafeResearchAdapter


QueryExecutor = Callable[[str, dict[str, str]], tuple[int, Any, str]]
RobotsChecker = Callable[[str, str], bool]
Sleeper = Callable[[float], None]


class EnterpriseAssetLookup(SafeResearchAdapter):
    """Query public internet asset indexes for an organization's visible assets."""

    source_domain = "internet_asset_index"
    source_type = "public_internet_infrastructure_index"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(
        self,
        api_credentials: dict | None = None,
        *,
        execute_query: QueryExecutor | None = None,
        robots_checker: RobotsChecker | None = None,
        sleeper: Sleeper | None = None,
    ):
        super().__init__(
            execute_query=execute_query,
            robots_checker=robots_checker,
            sleeper=sleeper,
        )
        self._credentials = api_credentials or {}

    def _has_required_credentials(self) -> bool:
        return bool(self._credentials.get("asset_index_key"))

    def query_organization_assets(self, org_name: str) -> dict[str, Any]:
        return self.query(keyword=org_name)

    def _build_url(self, keyword: str, **params) -> str:
        api_key = self._credentials.get("asset_index_key", "")
        return (
            "https://api.internet-asset-index.org/shodan/host/search"
            f"?key={api_key}&query=org:{keyword}"
        )

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {}
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            matches = data.get("matches", [])
            return {
                "asset_count": len(matches),
                "source": "public_internet_infrastructure_index",
                "disclosure_type": "publicly_visible_network_metadata",
                "access_level": "fully_public_indexed_data",
                "data_note": (
                    "Contains only publicly visible network metadata such as "
                    "service type, software version, and certificate details."
                ),
                "sample_orgs": sorted(
                    {m.get("org", "") for m in matches[:10] if m.get("org")}
                ),
            }
        except Exception:
            return {"error": "response_parse_failed", "raw_length": len(str(raw_data))}


class DomainReputationLookup(SafeResearchAdapter):
    """Query configured public domain-reputation APIs."""

    source_domain = "public_security_information_registry"
    source_type = "public_domain_reputation_database"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(
        self,
        api_credentials: dict | None = None,
        *,
        execute_query: QueryExecutor | None = None,
        robots_checker: RobotsChecker | None = None,
        sleeper: Sleeper | None = None,
    ):
        super().__init__(
            execute_query=execute_query,
            robots_checker=robots_checker,
            sleeper=sleeper,
        )
        self._credentials = api_credentials or {}

    def _has_required_credentials(self) -> bool:
        return bool(self._credentials.get("domain_reputation_key"))

    def check_domain(self, domain: str) -> dict[str, Any]:
        return self.query(keyword=domain)

    def _build_url(self, keyword: str, **params) -> str:
        return f"https://otx.alienvault.com/api/v1/indicators/domain/{keyword}/general"

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        api_key = self._credentials.get("domain_reputation_key", "")
        if api_key:
            headers["X-OTX-API-KEY"] = api_key
        return headers

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {}
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            pulse_count = len(data.get("pulse_info", {}).get("pulses", []))
            return {
                "source": "public_security_information_registry",
                "disclosure_type": "publicly_reported_security_observations",
                "access_level": "fully_public_open_database",
                "public_report_count": pulse_count,
                "data_note": "Count of publicly reported domain security observations.",
            }
        except Exception:
            return {"error": "response_parse_failed"}


class PublicRecordSecurityLookup(SafeResearchAdapter):
    """Query configured public security-event notification APIs."""

    source_domain = "public_security_event_registry"
    source_type = "public_information_security_event_database"
    data_boundary = "fully_public"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 3.0

    def __init__(
        self,
        api_credentials: dict | None = None,
        *,
        execute_query: QueryExecutor | None = None,
        robots_checker: RobotsChecker | None = None,
        sleeper: Sleeper | None = None,
    ):
        super().__init__(
            execute_query=execute_query,
            robots_checker=robots_checker,
            sleeper=sleeper,
        )
        self._credentials = api_credentials or {}

    def _has_required_credentials(self) -> bool:
        return bool(self._credentials.get("security_event_api_key"))

    def check_domain_events(self, domain: str) -> dict[str, Any]:
        return self.query(keyword=domain)

    def _build_url(self, keyword: str, **params) -> str:
        return f"https://haveibeenpwned.com/api/v3/breaches?domain={keyword}"

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        api_key = self._credentials.get("security_event_api_key", "")
        if api_key:
            headers["hibp-api-key"] = api_key
        return headers

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {}
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            events = data if isinstance(data, list) else []
            return {
                "source": "public_security_event_registry",
                "disclosure_type": "publicly_disclosed_information_security_events",
                "access_level": "fully_public_notification_database",
                "event_count": len(events),
                "event_names": [e.get("Name", "") for e in events[:5]],
                "data_note": "Publicly disclosed information-security event notices.",
                "compliance_framework": "GDPR Art.33-34, SOC 2 Type II, ISO 27001",
            }
        except Exception:
            return {"error": "response_parse_failed", "note": "domain may not have public events"}


class PublicIdentityVerification(SafeResearchAdapter):
    """Explicit-only public image-source consistency lookup."""

    source_domain = "public_search_engine"
    source_type = "public_identity_consistency_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 5.0

    def __init__(
        self,
        *,
        execute_query: QueryExecutor | None = None,
        robots_checker: RobotsChecker | None = None,
        sleeper: Sleeper | None = None,
    ):
        super().__init__(
            execute_query=execute_query,
            robots_checker=robots_checker,
            sleeper=sleeper,
        )

    def verify_public_image(self, image_url: str) -> dict[str, Any]:
        return self.query(keyword=image_url)

    def _build_url(self, keyword: str, **params) -> str:
        return f"https://www.google.com/searchbyimage?image_url={keyword}&safe=active"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {}
        return {
            "source": "public_search_engine",
            "disclosure_type": "publicly_indexed_image_search_results",
            "access_level": "fully_public_search_engine",
            "data_note": "Search results come from publicly indexed web pages.",
            "compliance_framework": "FATF CDD Recommendations, KYC Standards",
        }
