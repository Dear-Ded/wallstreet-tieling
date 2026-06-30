#!/usr/bin/env python3
"""Shared defaults for zero-config one-click investigations."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from adapters.default_public_intel_tool import DefaultPublicIntelTool
from adapters.qyyjt_adapter import QYYJTModule

from .intelligence_retrieval import (
    ConnectorShape,
    EvidenceGraph,
    EvidenceType,
    EntityKind,
    InvestigationEntity,
    InvestigativeRetrievalPlanner,
    RetrievalDomain,
    RetrievalPlan,
    SearchTask,
    SourceAccess,
    SourceAuthority,
    SourceProfile,
)


DEFAULT_ONE_CLICK_SOURCE = "default_public_intel"
DEFAULT_OFFICIAL_SOURCE_NAMES = (
    "gleif_lei_public_api",
    "sec_edgar_public_api",
    "ofac_consolidated_sanctions_xml",
    "un_sc_consolidated_sanctions_xml",
    "wikidata_public_entity_graph",
)


class DefaultOneClickSearchEngine:
    """Default public fan-out plus selected high-authority public connectors."""

    def __init__(self, *, public_tool: Any, official_engine: Any | None = None):
        self.public_tool = public_tool
        self.official_engine = official_engine

    def available_tools(self) -> set[str]:
        available = set()
        method = getattr(self.public_tool, "available_tools", None)
        if callable(method):
            available.update(method())
        available.add(DEFAULT_ONE_CLICK_SOURCE)
        return available

    def list_sources(self) -> list[str]:
        if self.official_engine is None:
            return [DEFAULT_ONE_CLICK_SOURCE]
        return [DEFAULT_ONE_CLICK_SOURCE, *DEFAULT_OFFICIAL_SOURCE_NAMES]

    def available_sources(self) -> list[str]:
        available = [DEFAULT_ONE_CLICK_SOURCE]
        if self.official_engine is not None:
            method = getattr(self.official_engine, "available_sources", None)
            if callable(method):
                try:
                    official = [str(item) for item in method()]
                    available.extend(source for source in DEFAULT_OFFICIAL_SOURCE_NAMES if source in official)
                except Exception:
                    pass
        return sorted(dict.fromkeys(available))

    def can_handle_source_hint(self, source_hint: str) -> bool:
        """Return whether this one-click router can execute the planned source directly."""
        hint = str(source_hint or "").strip()
        if not hint:
            return False
        can_handle_public = getattr(self.public_tool, "can_handle_source_hint", None)
        if callable(can_handle_public) and can_handle_public(hint):
            return True
        if hint == DEFAULT_ONE_CLICK_SOURCE:
            return True
        return self.official_engine is not None and hint in set(self.list_sources())

    def health_check(self) -> dict[str, Any]:
        public_health = _call_optional(self.public_tool, "health_check", {})
        official_health = _call_optional(self.official_engine, "health_check", {}) if self.official_engine else {}
        return {
            DEFAULT_ONE_CLICK_SOURCE: bool(public_health.get("ok", False)) if isinstance(public_health, dict) else False,
            **{
                name: bool(official_health.get(name, False))
                for name in DEFAULT_OFFICIAL_SOURCE_NAMES
                if self.official_engine is not None
            },
        }

    async def search(
        self,
        source_or_query: str,
        query_or_tool_type: str = DEFAULT_ONE_CLICK_SOURCE,
        **kwargs: Any,
    ) -> Any:
        """Support both SearchEngine.search(source, query) and ToolProvider.search(query, tool_type)."""
        configured = set(self.list_sources())
        if source_or_query in configured:
            source_name = source_or_query
            query = query_or_tool_type
        else:
            source_name = query_or_tool_type
            query = source_or_query

        params = dict(kwargs.get("params", {}) or {})
        if source_name in DEFAULT_OFFICIAL_SOURCE_NAMES and self.official_engine is not None:
            return await self.official_engine.search(
                source_name,
                query,
                params=params,
                timeout=_query_timeout_for_child(kwargs, params),
            )

        public_kwargs = dict(kwargs)
        if params.get("company") and not public_kwargs.get("company"):
            public_kwargs["company"] = params["company"]
        for option_key in (
            "qyyjt_options",
            "qyyjt_public_plan_limit",
            "execute_qyyjt_public_plan",
            "public_web_options",
            "telegram_options",
        ):
            if option_key in params and option_key not in public_kwargs:
                public_kwargs[option_key] = params[option_key]
        timeout_seconds = _query_timeout_for_child(kwargs, params)
        if timeout_seconds is not None:
            public_kwargs["query_timeout_seconds"] = timeout_seconds
            public_kwargs.setdefault("child_timeout_seconds", _bounded_child_timeout(timeout_seconds))
            public_web_options = dict(public_kwargs.get("public_web_options", {}) or {})
            public_web_options.setdefault(
                "request_timeout_seconds",
                _bounded_child_timeout(timeout_seconds),
            )
            public_kwargs["public_web_options"] = public_web_options

        tool_result = await self.public_tool.search(query, DEFAULT_ONE_CLICK_SOURCE, **public_kwargs)
        data = getattr(tool_result, "data", {}) or {}
        records = []
        if isinstance(data, dict):
            records = data.get("standardized_records") or []
        return SimpleNamespace(
            source_name=DEFAULT_ONE_CLICK_SOURCE,
            source_type="public_intel_fanout",
            is_success=bool(getattr(tool_result, "ok", False)),
            error=getattr(tool_result, "error", None),
            data=data,
            metadata={"standardized_records": records if isinstance(records, list) else []},
        )


@dataclass(frozen=True)
class RetrievalModeSelection:
    """Resolved retrieval inputs for CLI/API one-click runs."""

    records: list[dict[str, Any]] | None
    search_engine: Any | None
    existing_plan: RetrievalPlan | None
    fanout_rounds: int
    mode_name: str


def build_default_one_click_plan(company: str) -> RetrievalPlan:
    """Build a bounded starter plan for users who run the product with no setup.

    The full planner remains available for configured deployments. The default
    product path intentionally starts with public/no-credential sources so a new
    user gets real evidence, source coverage, and gaps without learning flags.
    """
    seed = InvestigativeRetrievalPlanner._normalize_seed(company)
    seed_id = InvestigativeRetrievalPlanner._entity_id(EntityKind.COMPANY, seed)
    graph = EvidenceGraph()
    graph.add_entity(
        InvestigationEntity(
            id=seed_id,
            kind=EntityKind.COMPANY,
            name=seed,
            confidence=1.0,
            attributes={"seed": True},
        )
    )
    source_profile = SourceProfile(
        DEFAULT_ONE_CLICK_SOURCE,
        ConnectorShape.SEARCH_ENGINE,
        SourceAccess.PUBLIC,
        SourceAuthority.PUBLIC_WEB,
        notes=(
            "Zero-config starter route: public web, public query-plan leads, and user-configurable public-service delivery.",
            "Results are evidence leads with source provenance, not final risk clearance.",
        ),
    )
    tasks = [
        SearchTask(
            RetrievalDomain.CORPORATE_REGISTRY,
            f"{seed} legal entity registry official website company profile",
            DEFAULT_ONE_CLICK_SOURCE,
            "Establish basic identity and official/public profile leads.",
            10,
            (EvidenceType.REGISTRY_RECORD, EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
            (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.ADDRESS, EntityKind.DOMAIN),
            source_profile,
        ),
        SearchTask(
            RetrievalDomain.CORPORATE_REGISTRY,
            seed,
            "gleif_lei_public_api",
            "Verify public legal-entity identity through GLEIF when available.",
            11,
            (EvidenceType.REGISTRY_RECORD, EvidenceType.DATABASE_RESULT),
            (EntityKind.COMPANY, EntityKind.ADDRESS),
            SourceProfile(
                "gleif_lei_public_api",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Default one-click high-authority public identity lookup.",),
            ),
        ),
        SearchTask(
            RetrievalDomain.OWNERSHIP_CONTROL,
            f"{seed} legal representative shareholder actual controller beneficial owner",
            DEFAULT_ONE_CLICK_SOURCE,
            "Find public controller, shareholder, and key-person leads.",
            15,
            (EvidenceType.REGISTRY_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
            (EntityKind.PERSON, EntityKind.COMPANY),
            source_profile,
        ),
        SearchTask(
            RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            seed,
            "sec_edgar_public_api",
            "Verify SEC EDGAR public issuer disclosures when available.",
            18,
            (EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
            (EntityKind.COMPANY, EntityKind.PERSON),
            SourceProfile(
                "sec_edgar_public_api",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Default one-click high-authority public disclosure lookup.",),
            ),
        ),
        SearchTask(
            RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            f"{seed} financing debt bond pledge financial indicators",
            DEFAULT_ONE_CLICK_SOURCE,
            "Collect public capital, financing, debt, and pledge leads.",
            19,
            (EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
            (EntityKind.COMPANY, EntityKind.PROJECT),
            source_profile,
            params={
                "qyyjt_options": {
                    "modules": [
                        QYYJTModule.ENTERPRISE_FINANCING,
                        QYYJTModule.FINANCIAL_STATEMENT,
                        QYYJTModule.FINANCIAL_INDICATORS,
                        QYYJTModule.BOND_PROFILE,
                    ]
                },
                "qyyjt_public_plan_limit": 3,
                "execute_qyyjt_public_plan": True,
            },
        ),
        SearchTask(
            RetrievalDomain.RELATED_ENTITIES,
            f"{seed} subsidiaries affiliates investments related companies counterparties",
            DEFAULT_ONE_CLICK_SOURCE,
            "Expand public relationship and associated-entity leads.",
            20,
            (EvidenceType.WEBPAGE, EvidenceType.PUBLIC_NOTICE, EvidenceType.REGISTRY_RECORD),
            (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.PROJECT),
            source_profile,
        ),
        SearchTask(
            RetrievalDomain.RELATED_ENTITIES,
            f"{seed} supplier customer product import export patent trademark recruitment",
            DEFAULT_ONE_CLICK_SOURCE,
            "Collect public goods, market, IP, hiring, and trade-operation leads.",
            24,
            (EvidenceType.WEBPAGE, EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
            (EntityKind.COMPANY, EntityKind.PROJECT, EntityKind.DOMAIN),
            source_profile,
            params={
                "qyyjt_options": {
                    "modules": [
                        QYYJTModule.IMPORT_EXPORT,
                        QYYJTModule.PATENT,
                        QYYJTModule.TRADEMARK,
                        QYYJTModule.RECRUIT,
                    ]
                },
                "qyyjt_public_plan_limit": 3,
                "execute_qyyjt_public_plan": True,
            },
        ),
        SearchTask(
            RetrievalDomain.RELATED_ENTITIES,
            seed,
            "wikidata_public_entity_graph",
            "Corroborate public entity graph identifiers, websites, people, and related entities.",
            21,
            (EvidenceType.DATABASE_RESULT, EvidenceType.WEBPAGE),
            (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.DOMAIN),
            SourceProfile(
                "wikidata_public_entity_graph",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.PUBLIC_WEB,
                notes=("Default one-click public knowledge-graph lookup.",),
            ),
        ),
        SearchTask(
            RetrievalDomain.COURT_ENFORCEMENT,
            f"{seed} litigation enforcement court judgment credit risk",
            DEFAULT_ONE_CLICK_SOURCE,
            "Collect public legal and enforcement-risk leads.",
            25,
            (EvidenceType.COURT_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
            (EntityKind.CASE, EntityKind.COMPANY, EntityKind.PERSON),
            source_profile,
        ),
        SearchTask(
            RetrievalDomain.ADMINISTRATIVE_RISK,
            f"{seed} administrative penalty regulatory notice sanctions debarment",
            DEFAULT_ONE_CLICK_SOURCE,
            "Collect public administrative, regulatory, and integrity-risk leads.",
            30,
            (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
            (EntityKind.CASE, EntityKind.COMPANY, EntityKind.PERSON),
            source_profile,
        ),
        SearchTask(
            RetrievalDomain.ADMINISTRATIVE_RISK,
            seed,
            "ofac_consolidated_sanctions_xml",
            "Screen the subject against OFAC official public consolidated list data when enabled.",
            31,
            (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
            (EntityKind.COMPANY, EntityKind.PERSON),
            SourceProfile(
                "ofac_consolidated_sanctions_xml",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Default one-click high-authority public screening lookup.",),
            ),
        ),
        SearchTask(
            RetrievalDomain.ADMINISTRATIVE_RISK,
            seed,
            "un_sc_consolidated_sanctions_xml",
            "Screen the subject against UN Security Council official public consolidated list data when enabled.",
            32,
            (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
            (EntityKind.COMPANY, EntityKind.PERSON),
            SourceProfile(
                "un_sc_consolidated_sanctions_xml",
                ConnectorShape.REST_API,
                SourceAccess.PUBLIC,
                SourceAuthority.OFFICIAL,
                notes=("Default one-click high-authority public screening lookup.",),
            ),
        ),
        SearchTask(
            RetrievalDomain.NEWS_PUBLIC_OPINION,
            f"{seed} news complaint incident dispute public opinion",
            DEFAULT_ONE_CLICK_SOURCE,
            "Find public event, complaint, and media leads.",
            35,
            (EvidenceType.NEWS_ARTICLE, EvidenceType.WEBPAGE, EvidenceType.SOCIAL_POST),
            (EntityKind.PERSON, EntityKind.PROJECT, EntityKind.ACCOUNT),
            source_profile,
        ),
    ]
    return RetrievalPlan(
        seed_company=seed,
        tasks=tasks,
        graph=graph,
        compliance_notes=[
            "Default one-click mode uses public/no-credential routes only.",
            "Every item is retained with source provenance and confidence.",
            "Empty results are coverage gaps, not low-risk conclusions.",
            "Configure licensed or user-authorized connectors for production-grade depth.",
        ],
        coverage_domains={task.domain for task in tasks},
    )


def build_default_public_search_engine() -> DefaultPublicIntelTool:
    """Return the default zero-config public intelligence tool."""
    return DefaultPublicIntelTool()


async def build_default_one_click_search_engine(
    *,
    include_official_public: bool = False,
) -> DefaultOneClickSearchEngine:
    """Return the default product search engine with optional official sources."""
    official_engine = None
    if include_official_public:
        try:
            from adapters.multi_datasource import SearchEngine
            from .official_public_smoke import build_official_public_smoke_config

            await SearchEngine.initialize(str(build_official_public_smoke_config()))
            official_engine = SearchEngine
        except Exception:
            official_engine = None
    return DefaultOneClickSearchEngine(
        public_tool=build_default_public_search_engine(),
        official_engine=official_engine,
    )


def resolve_one_click_retrieval(
    *,
    company: str,
    records: list[dict[str, Any]] | None = None,
    search_engine: Any | None = None,
    existing_plan: RetrievalPlan | None = None,
    fanout_rounds: int = 1,
    default_enabled: bool = True,
) -> RetrievalModeSelection:
    """Fill retrieval inputs with a usable public default when none is supplied."""
    if records is not None:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "records")
    if search_engine is not None or existing_plan is not None:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "configured")
    if not default_enabled:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "none")
    raise RuntimeError("resolve_one_click_retrieval_async must be used when default_enabled=True")


async def resolve_one_click_retrieval_async(
    *,
    company: str,
    records: list[dict[str, Any]] | None = None,
    search_engine: Any | None = None,
    existing_plan: RetrievalPlan | None = None,
    fanout_rounds: int = 1,
    default_enabled: bool = True,
) -> RetrievalModeSelection:
    """Async variant that can initialize selected public official connectors."""
    if records is not None:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "records")
    if search_engine is not None or existing_plan is not None:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "configured")
    if not default_enabled:
        return RetrievalModeSelection(records, search_engine, existing_plan, fanout_rounds, "none")
    return RetrievalModeSelection(
        records=None,
        search_engine=await build_default_one_click_search_engine(),
        existing_plan=build_default_one_click_plan(company),
        fanout_rounds=0,
        mode_name="default_public_one_click",
    )


def _call_optional(target: Any, name: str, default: Any) -> Any:
    if target is None:
        return default
    method = getattr(target, name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception:
        return default


def _query_timeout_for_child(kwargs: dict[str, Any], params: dict[str, Any]) -> float | None:
    raw = kwargs.get("query_timeout_seconds", params.get("query_timeout_seconds"))
    try:
        return max(0.1, float(raw))
    except (TypeError, ValueError):
        return None


def _bounded_child_timeout(timeout_seconds: float) -> float:
    return max(0.1, min(float(timeout_seconds) * 0.5, 3.0))
