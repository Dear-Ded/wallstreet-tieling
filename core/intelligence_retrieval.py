#!/usr/bin/env python3
"""Investigative retrieval planning for company due diligence.

This module turns a company name into a broad, evidence-first OSINT plan. It is
deliberately source-agnostic: connectors can execute the produced search tasks,
while this layer owns coverage, fan-out logic, provenance, and confidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RetrievalDomain(str, Enum):
    CORPORATE_REGISTRY = "corporate_registry"
    OWNERSHIP_CONTROL = "ownership_control"
    PEOPLE = "people"
    RELATED_ENTITIES = "related_entities"
    COURT_ENFORCEMENT = "court_enforcement"
    ADMINISTRATIVE_RISK = "administrative_risk"
    NEWS_PUBLIC_OPINION = "news_public_opinion"
    SOCIAL_WEB = "social_web"
    LOCATION_ASSETS = "location_assets"
    FINANCING_CAPITAL_MARKETS = "financing_capital_markets"
    PROCUREMENT_PROJECTS = "procurement_projects"
    IP_TECH = "ip_tech"


class RetrievalLayer(str, Enum):
    ENTITY_ANCHOR = "entity_anchor"
    OVERVIEW = "overview"
    PRIORITIZED_DRILLDOWN = "prioritized_drilldown"
    SPECIALIST = "specialist"


class EvidenceType(str, Enum):
    REGISTRY_RECORD = "registry_record"
    PUBLIC_NOTICE = "public_notice"
    COURT_RECORD = "court_record"
    ADMINISTRATIVE_RECORD = "administrative_record"
    NEWS_ARTICLE = "news_article"
    SOCIAL_POST = "social_post"
    WEBPAGE = "webpage"
    DATABASE_RESULT = "database_result"
    DERIVED_CLUE = "derived_clue"


class EntityKind(str, Enum):
    COMPANY = "company"
    PERSON = "person"
    ADDRESS = "address"
    PHONE = "phone"
    EMAIL = "email"
    DOMAIN = "domain"
    ACCOUNT = "account"
    ASSET = "asset"
    CASE = "case"
    PROJECT = "project"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConnectorShape(str, Enum):
    REST_API = "rest_api"
    WEB_PAGE = "web_page"
    SEARCH_ENGINE = "search_engine"
    OFFICIAL_PLATFORM = "official_platform"
    TELEGRAM_BOT = "telegram_bot"
    LOCAL_FILE = "local_file"
    UNKNOWN = "unknown"


class SourceAccess(str, Enum):
    PUBLIC = "public"
    USER_AUTHORIZED = "user_authorized"
    LICENSED = "licensed"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class SourceAuthority(str, Enum):
    OFFICIAL = "official"
    COMMERCIAL = "commercial"
    PUBLIC_WEB = "public_web"
    COMMUNITY = "community"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceProfile:
    name: str
    shape: ConnectorShape
    access: SourceAccess
    authority: SourceAuthority
    provenance_required: bool = True
    allowed: bool = True
    business_relevance_required: bool = True
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "shape": self.shape.value,
            "access": self.access.value,
            "authority": self.authority.value,
            "provenance_required": self.provenance_required,
            "allowed": self.allowed,
            "business_relevance_required": self.business_relevance_required,
            "notes": list(self.notes),
        }


class SourceCatalog:
    """Classifies source hints by delivery shape and legitimacy expectations."""

    _PROFILES: dict[str, SourceProfile] = {
        "registry_sources": SourceProfile(
            "registry_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use official or licensed business-registration records.",),
        ),
        "registry_and_commercial_sources": SourceProfile(
            "registry_and_commercial_sources",
            ConnectorShape.REST_API,
            SourceAccess.LICENSED,
            SourceAuthority.COMMERCIAL,
            notes=("Commercial registry enrichment must be licensed or user-authorized.",),
        ),
        "registry_and_web_search": SourceProfile(
            "registry_and_web_search",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public pages to corroborate registry people and roles.",),
        ),
        "registry_and_disclosure_sources": SourceProfile(
            "registry_and_disclosure_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Prioritize official filings and public disclosures.",),
        ),
        "gleif_lei_public_api": SourceProfile(
            "gleif_lei_public_api",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use GLEIF public LEI records for legal-entity identity and relationship leads.",),
        ),
        "sec_edgar_public_api": SourceProfile(
            "sec_edgar_public_api",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use SEC EDGAR public company submissions for issuer disclosure and capital-market leads.",),
        ),
        "opensanctions_public_dataset_catalog": SourceProfile(
            "opensanctions_public_dataset_catalog",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public OpenSanctions dataset metadata to understand watchlist, PEP, and sanctions coverage.",),
        ),
        "ofac_consolidated_sanctions_xml": SourceProfile(
            "ofac_consolidated_sanctions_xml",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use the official public OFAC consolidated sanctions XML for watchlist screening.",),
        ),
        "un_sc_consolidated_sanctions_xml": SourceProfile(
            "un_sc_consolidated_sanctions_xml",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use the official public UN Security Council consolidated sanctions XML for watchlist screening.",),
        ),
        "idb_sanctioned_firms_dataset_catalog": SourceProfile(
            "idb_sanctioned_firms_dataset_catalog",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use the IDB public sanctions dataset catalog for procurement debarment coverage discovery.",),
        ),
        "world_bank_debarred_firms_public_list": SourceProfile(
            "world_bank_debarred_firms_public_list",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use the World Bank public debarred firms list for procurement and counterparty exclusion screening.",),
        ),
        "wikidata_public_entity_graph": SourceProfile(
            "wikidata_public_entity_graph",
            ConnectorShape.REST_API,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use Wikidata as a public knowledge-graph corroboration layer for entities, people, identifiers, and websites.",),
        ),
        "court_and_credit_sources": SourceProfile(
            "court_and_credit_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use public court, enforcement, and credit-publicity portals.",),
        ),
        "government_credit_sources": SourceProfile(
            "government_credit_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use government credit and administrative-publicity sources.",),
        ),
        "news_and_web_search": SourceProfile(
            "news_and_web_search",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Treat media and public-opinion items as leads until corroborated.",),
        ),
        "web_search": SourceProfile(
            "web_search",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Only index public pages and keep URL-level provenance.",),
        ),
        "asset_and_location_sources": SourceProfile(
            "asset_and_location_sources",
            ConnectorShape.WEB_PAGE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public asset, auction, procurement, and address disclosures.",),
        ),
        "public_contact_sources": SourceProfile(
            "public_contact_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public recruitment, cooperation, website, and filing pages for contact leads.",),
        ),
        "public_account_sources": SourceProfile(
            "public_account_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public account pages and public social/search results as corroboration leads.",),
        ),
        "location_activity_sources": SourceProfile(
            "location_activity_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public address, procurement, recruitment, logistics, and activity-location disclosures.",),
        ),
        "public_asset_sources": SourceProfile(
            "public_asset_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Prefer official public asset, collateral, auction, vehicle, and property notices.",),
        ),
        "public_behavior_sources": SourceProfile(
            "public_behavior_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use public administrative, court, traffic, and regulatory records when lawfully available.",),
        ),
        "relationship_network_sources": SourceProfile(
            "relationship_network_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public co-occurrence, investment, appointment, project, and counterparty relationships.",),
        ),
        "capital_market_sources": SourceProfile(
            "capital_market_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Prefer exchange, regulator, and issuer disclosures.",),
        ),
        "procurement_sources": SourceProfile(
            "procurement_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use public procurement and tender award notices.",),
        ),
        "supply_chain_sources": SourceProfile(
            "supply_chain_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public procurement, disclosure, recruitment, customer-case, supplier, dealer, and partner pages for supply-chain leads.",),
        ),
        "industry_research_sources": SourceProfile(
            "industry_research_sources",
            ConnectorShape.SEARCH_ENGINE,
            SourceAccess.PUBLIC,
            SourceAuthority.PUBLIC_WEB,
            notes=("Use public research, filings, product pages, customer cases, and credible news for industry and business-model analysis leads.",),
        ),
        "ip_and_tech_sources": SourceProfile(
            "ip_and_tech_sources",
            ConnectorShape.OFFICIAL_PLATFORM,
            SourceAccess.PUBLIC,
            SourceAuthority.OFFICIAL,
            notes=("Use public IP, domain, app, and filing records.",),
        ),
        "telegram_bot_public_service": SourceProfile(
            "telegram_bot_public_service",
            ConnectorShape.TELEGRAM_BOT,
            SourceAccess.PUBLIC,
            SourceAuthority.COMMUNITY,
            notes=(
                "Public bot delivery is acceptable when the underlying data is public and auditable.",
            ),
        ),
    }

    @classmethod
    def profile_for(cls, source_hint: str) -> SourceProfile:
        key = str(source_hint or "").strip()
        if key in cls._PROFILES:
            return cls._PROFILES[key]
        return SourceProfile(
            name=key or "unknown",
            shape=ConnectorShape.UNKNOWN,
            access=SourceAccess.UNKNOWN,
            authority=SourceAuthority.UNKNOWN,
            allowed=False,
            notes=("Unknown source: require manual legitimacy and provenance review before production use.",),
        )


@dataclass(frozen=True)
class SearchTask:
    domain: RetrievalDomain
    query: str
    source_hint: str
    objective: str
    priority: int = 50
    expected_evidence: tuple[EvidenceType, ...] = ()
    fanout_entities: tuple[EntityKind, ...] = ()
    source_profile: SourceProfile | None = None
    params: dict[str, Any] = field(default_factory=dict)
    retrieval_layer: RetrievalLayer | None = None

    def resolved_source_profile(self) -> SourceProfile:
        return self.source_profile or SourceCatalog.profile_for(self.source_hint)

    def effective_retrieval_layer(self) -> RetrievalLayer:
        if self.retrieval_layer is not None:
            return RetrievalLayer(self.retrieval_layer)
        if str(self.params.get("retrieval_layer") or ""):
            try:
                return RetrievalLayer(str(self.params["retrieval_layer"]))
            except ValueError:
                pass
        if self.source_hint == "registry_sources":
            return RetrievalLayer.ENTITY_ANCHOR
        if self.priority <= 30:
            return RetrievalLayer.OVERVIEW
        if self.priority <= 45:
            return RetrievalLayer.PRIORITIZED_DRILLDOWN
        return RetrievalLayer.SPECIALIST



@dataclass(frozen=True)
class EvidenceItem:
    id: str
    evidence_type: EvidenceType
    source: str
    title: str
    url: str | None = None
    observed_at: str | None = None
    confidence: float = 0.5
    claims: tuple[str, ...] = ()
    source_profile: SourceProfile | None = None
    entity_match: dict[str, Any] | None = None


@dataclass
class InvestigationEntity:
    id: str
    kind: EntityKind
    name: str
    confidence: float = 0.5
    evidence_ids: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvestigationRelation:
    from_id: str
    to_id: str
    relation_type: str
    confidence: float = 0.5
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskEvent:
    id: str
    category: RetrievalDomain
    title: str
    severity: RiskSeverity
    entity_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float = 0.5
    rationale: str = ""
    status: str = "open"


@dataclass
class EvidenceGraph:
    entities: dict[str, InvestigationEntity] = field(default_factory=dict)
    evidence: dict[str, EvidenceItem] = field(default_factory=dict)
    relations: list[InvestigationRelation] = field(default_factory=list)
    risk_events: list[RiskEvent] = field(default_factory=list)

    def add_entity(self, entity: InvestigationEntity) -> None:
        current = self.entities.get(entity.id)
        if current is None:
            self.entities[entity.id] = entity
            return

        for evidence_id in entity.evidence_ids:
            if evidence_id not in current.evidence_ids:
                current.evidence_ids.append(evidence_id)
        current.attributes.update(
            {
                key: value
                for key, value in entity.attributes.items()
                if value not in (None, "")
            }
        )
        if entity.confidence > current.confidence:
            current.name = entity.name
            current.confidence = entity.confidence

    def add_evidence(self, evidence: EvidenceItem) -> None:
        self.evidence[evidence.id] = evidence

    def add_relation(self, relation: InvestigationRelation) -> None:
        self.relations.append(relation)

    def add_risk_event(self, event: RiskEvent) -> None:
        if all(current.id != event.id for current in self.risk_events):
            self.risk_events.append(event)

    def attach_evidence_to_entity(self, entity_id: str, evidence_id: str) -> None:
        entity = self.entities.get(entity_id)
        if entity and evidence_id not in entity.evidence_ids:
            entity.evidence_ids.append(evidence_id)


class EntityResolutionScorer:
    """Scores whether a provider record refers to the requested subject."""

    COMPANY_SUFFIXES = (
        "company limited",
        "co., ltd.",
        "co ltd",
        "limited",
        "ltd.",
        "ltd",
        "inc.",
        "inc",
        "corp.",
        "corp",
        "corporation",
        "group",
        "holdings",
        "holding",
        "公司",
        "有限责任公司",
        "有限公司",
        "股份有限公司",
        "集团",
    )

    @classmethod
    def score(cls, seed_name: str, candidate_name: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a compact, explainable entity-resolution assessment."""
        seed_display = " ".join(str(seed_name or "").split())
        candidate_display = " ".join(str(candidate_name or "").split())
        seed = cls._normalize(seed_display)
        candidate = cls._normalize(candidate_display)
        reasons: list[str] = []
        identifiers = cls._identifiers(raw or {})

        if not seed or not candidate:
            score = 0.0
            reasons.append("missing seed or candidate name")
        elif seed == candidate:
            score = 1.0
            reasons.append("normalized legal name exact match")
        else:
            ratio = SequenceMatcher(None, seed, candidate).ratio()
            contains = seed in candidate or candidate in seed
            score = ratio
            reasons.append(f"name similarity {ratio:.2f}")
            if contains:
                shorter_token_count = min(len(seed.split()), len(candidate.split()))
                if shorter_token_count <= 1 and seed != candidate:
                    score = max(score, 0.7)
                    reasons.append("single-token name containment requires review")
                else:
                    score = max(score, 0.9)
                    reasons.append("one normalized name contains the other")
            token_overlap = cls._token_overlap(seed, candidate)
            if token_overlap:
                score = max(score, 0.55 + 0.35 * token_overlap)
                reasons.append(f"token overlap {token_overlap:.2f}")

        if identifiers and score >= 0.62:
            score = max(score, 0.75)
            reasons.append("official identifier present: " + ", ".join(sorted(identifiers)))
        elif identifiers:
            reasons.append("official identifier present on a low-similarity candidate: " + ", ".join(sorted(identifiers)))

        score = max(0.0, min(1.0, score))
        return {
            "seed_name": seed_display,
            "candidate_name": candidate_display,
            "score": round(score, 4),
            "level": cls._level(score),
            "reasons": reasons,
            "identifiers": identifiers,
        }

    @classmethod
    def _normalize(cls, raw: str) -> str:
        text = str(raw or "").strip().lower()
        text = re.sub(r"[（）()【】\[\],，.。:：;；\-_/\\]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        changed = True
        while changed:
            changed = False
            for suffix in cls.COMPANY_SUFFIXES:
                suffix_norm = re.sub(r"\s+", " ", suffix.lower()).strip()
                if text.endswith(" " + suffix_norm):
                    text = text[: -len(suffix_norm)].strip()
                    changed = True
                elif text == suffix_norm:
                    text = ""
                    changed = True
        return text

    @staticmethod
    def _token_overlap(left: str, right: str) -> float:
        left_tokens = {token for token in left.split() if token}
        right_tokens = {token for token in right.split() if token}
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    @staticmethod
    def _identifiers(raw: dict[str, Any]) -> dict[str, str]:
        identifiers: dict[str, str] = {}
        for target, keys in {
            "lei": ("lei",),
            "cik": ("cik", "cik_str"),
            "ticker": ("ticker", "symbol"),
            "unified_social_credit_code": (
                "unified_social_credit_code",
                "unifiedSocialCreditCode",
                "creditCode",
                "uscc",
                "code",
            ),
            "registration_number": ("registration_number", "registrationNo", "regNo"),
        }.items():
            for key in keys:
                value = raw.get(key)
                if value:
                    identifiers[target] = str(value)
                    break
        return identifiers

    @staticmethod
    def _level(score: float) -> str:
        if score >= 0.95:
            return "exact"
        if score >= 0.82:
            return "strong"
        if score >= 0.62:
            return "review"
        return "weak"


class RiskSignalDetector:
    """Derives monitorable risk events from normalized evidence."""

    RULES: tuple[dict[str, Any], ...] = (
        {
            "category": RetrievalDomain.COURT_ENFORCEMENT,
            "severity": RiskSeverity.HIGH,
            "title": "Court or enforcement risk signal",
            "keywords": ("失信", "被执行", "限制高消费", "终本案件", "查封", "冻结"),
        },
        {
            "category": RetrievalDomain.ADMINISTRATIVE_RISK,
            "severity": RiskSeverity.HIGH,
            "title": "Administrative penalty or abnormal operation signal",
            "keywords": ("行政处罚", "经营异常", "严重违法", "税务处罚", "环保处罚"),
        },
        {
            "category": RetrievalDomain.OWNERSHIP_CONTROL,
            "severity": RiskSeverity.MEDIUM,
            "title": "Ownership or controller anomaly signal",
            "keywords": ("疑似实际控制人", "实际控制人变更", "股权穿透", "代持", "隐名股东"),
        },
        {
            "category": RetrievalDomain.LOCATION_ASSETS,
            "severity": RiskSeverity.MEDIUM,
            "title": "Asset encumbrance or auction signal",
            "keywords": ("不动产抵押", "动产抵押", "司法拍卖", "资产冻结", "轮候查封"),
        },
        {
            "category": RetrievalDomain.NEWS_PUBLIC_OPINION,
            "severity": RiskSeverity.MEDIUM,
            "title": "Negative public-opinion or dispute signal",
            "keywords": ("投诉", "纠纷", "维权", "事故", "负面新闻"),
        },
        {
            "category": RetrievalDomain.SOCIAL_WEB,
            "severity": RiskSeverity.LOW,
            "title": "Social-web identity or activity lead",
            "keywords": ("公开账号", "微博", "微信公众号", "抖音", "小红书", "LinkedIn", "GitHub"),
        },
    )

    @classmethod
    def derive_events(
        cls,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        task: SearchTask,
        evidence: EvidenceItem,
        related_entity_ids: tuple[str, ...] = (),
    ) -> list[RiskEvent]:
        if not cls._evidence_can_raise_risk_event(evidence):
            return []
        haystack = " ".join((evidence.title, *evidence.claims))
        events: list[RiskEvent] = []
        for rule in cls.RULES:
            matched = [keyword for keyword in rule["keywords"] if keyword in haystack]
            if not matched:
                continue

            entity_ids = cls._dedupe((seed_entity_id, *related_entity_ids))
            event = RiskEvent(
                id=cls._stable_event_id(rule["category"], entity_ids, evidence.id, matched),
                category=rule["category"],
                title=rule["title"],
                severity=rule["severity"],
                entity_ids=entity_ids,
                evidence_ids=(evidence.id,),
                confidence=evidence.confidence,
                rationale=f"Matched keywords: {', '.join(matched)}",
            )
            graph.add_risk_event(event)
            events.append(event)
        return events

    @staticmethod
    def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _stable_event_id(
        category: RetrievalDomain,
        entity_ids: tuple[str, ...],
        evidence_id: str,
        matched: list[str],
    ) -> str:
        payload = {
            "category": category.value,
            "entity_ids": entity_ids,
            "evidence_id": evidence_id,
            "matched": sorted(matched),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return f"risk:{digest}"

    @staticmethod
    def _evidence_can_raise_risk_event(evidence: EvidenceItem) -> bool:
        """Return whether a record can be treated as factual risk evidence."""
        source_type = ""
        if isinstance(evidence.entity_match, dict):
            source_type = str(evidence.entity_match.get("record_source_type") or "")
        if source_type.strip().lower() in {"query_plan", "rich_query_plan"}:
            return False
        return True


class EvidenceIngestor:
    """Normalizes connector results into the evidence graph."""

    FIELD_ENTITY_MAP: tuple[tuple[EntityKind, tuple[str, ...], str], ...] = (
        (
            EntityKind.PERSON,
            (
                "legal_representative",
                "legalRep",
                "legalRepName",
                "legalPerson",
                "frName",
                "actual_controller",
                "actualController",
                "actualControllerName",
                "controller",
                "controllerName",
                "control_person",
                "controlPerson",
                "beneficial_owner",
                "beneficialOwner",
                "beneficialOwnerName",
                "ultimate_beneficial_owner",
                "ultimateBeneficialOwner",
                "ubo",
                "chairman",
                "director",
                "directorName",
                "supervisor",
                "supervisorName",
                "manager",
                "managerName",
                "shareholder",
                "shareholders",
                "shareholderName",
                "investorName",
                "controlling_shareholder",
                "controllingShareholder",
                "executive",
                "executives",
            ),
            "public_role_or_control_lead",
        ),
        (EntityKind.ADDRESS, ("address", "registered_address", "registration_address", "office_address", "business_address"), "public_address_lead"),
        (EntityKind.PHONE, ("phone", "telephone", "contact_phone", "mobile", "hotline"), "public_contact_lead"),
        (EntityKind.EMAIL, ("email", "contact_email"), "public_contact_lead"),
        (EntityKind.DOMAIN, ("domain", "website", "website_url", "homepage"), "public_web_footprint"),
        (EntityKind.ACCOUNT, ("account", "social_account", "public_account", "handle"), "public_account_lead"),
        (EntityKind.CASE, ("case", "case_no", "case_number", "docket", "docket_no"), "public_case_lead"),
        (EntityKind.PROJECT, ("project", "project_name", "tender_project", "contract"), "public_project_lead"),
        (EntityKind.ASSET, ("asset", "asset_name", "property", "collateral"), "public_asset_lead"),
    )
    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    DOMAIN_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+(?:com|cn|net|org|io|ai|co|gov|edu)\b", re.I)
    PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\- ()]{6,}\d)(?!\d)")

    @classmethod
    def ingest_standardized_records(
        cls,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        task: SearchTask,
        records: list[dict[str, Any]],
    ) -> list[EvidenceItem]:
        """Ingest normalized connector records into evidence and risk graph.

        Multi-source adapters emit a provider-neutral record shape. This bridge
        lets retrieval providers plug into the graph without each provider
        knowing about risk events, entities, or graph storage.
        """
        evidence_items: list[EvidenceItem] = []
        for record in records:
            normalized = cls._search_result_from_standardized_record(record, task)
            evidence_items.append(
                cls.ingest_search_result(
                    graph,
                    seed_entity_id=seed_entity_id,
                    task=task,
                    result=normalized,
                )
            )
        return evidence_items

    @classmethod
    def ingest_query_result(
        cls,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        task: SearchTask,
        query_result: Any,
    ) -> list[EvidenceItem]:
        """Ingest a QueryResult-like object carrying standardized_records metadata."""
        metadata = getattr(query_result, "metadata", {}) or {}
        records = metadata.get("standardized_records", [])
        if not isinstance(records, list):
            return []
        return cls.ingest_standardized_records(
            graph,
            seed_entity_id=seed_entity_id,
            task=task,
            records=[item for item in records if isinstance(item, dict)],
        )

    @classmethod
    def ingest_search_result(
        cls,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        task: SearchTask,
        result: dict[str, Any],
    ) -> EvidenceItem:
        source = str(result.get("source") or task.source_hint)
        title = str(result.get("title") or task.objective)
        url = result.get("url")
        observed_at = result.get("observed_at")
        confidence = cls._clamp_confidence(result.get("confidence", 0.5))
        claims = tuple(str(item) for item in result.get("claims", []) if str(item).strip())
        seed_entity = graph.entities.get(seed_entity_id)
        seed_name = seed_entity.name if seed_entity else task.query
        entity_match = cls._entity_match(seed_name, result)

        evidence = EvidenceItem(
            id=cls._stable_id(
                "evidence",
                {
                    "source": source,
                    "title": title,
                    "url": url,
                    "claims": claims,
                    "query": task.query,
                },
            ),
            evidence_type=cls._evidence_type(result.get("evidence_type"), task),
            source=source,
            title=title,
            url=str(url) if url else None,
            observed_at=str(observed_at) if observed_at else None,
            confidence=confidence,
            claims=claims,
            source_profile=cls._source_profile(result, task),
            entity_match=entity_match,
        )
        graph.add_evidence(evidence)
        graph.attach_evidence_to_entity(seed_entity_id, evidence.id)

        related_entity_ids: list[str] = []
        for raw_entity in result.get("entities", []):
            entity = cls._entity_from_raw(raw_entity, evidence.id)
            if entity is None:
                continue
            related_entity_ids.append(entity.id)
            graph.add_entity(entity)
            relation_type = str(raw_entity.get("relation") or "mentioned_with")
            graph.add_relation(
                InvestigationRelation(
                    from_id=seed_entity_id,
                    to_id=entity.id,
                    relation_type=relation_type,
                    confidence=min(confidence, entity.confidence),
                    evidence_ids=(evidence.id,),
                )
            )

        for raw_relation in result.get("relations", []):
            relation, endpoint_ids = cls._relation_from_raw(
                raw_relation,
                graph,
                seed_entity_id=seed_entity_id,
                evidence_id=evidence.id,
            )
            if relation is None:
                continue
            for entity_id in endpoint_ids:
                if entity_id not in related_entity_ids and entity_id != seed_entity_id:
                    related_entity_ids.append(entity_id)
            graph.add_relation(relation)

        RiskSignalDetector.derive_events(
            graph,
            seed_entity_id=seed_entity_id,
            task=task,
            evidence=evidence,
            related_entity_ids=tuple(related_entity_ids),
        )
        cls._ingest_structured_risk_events(
            graph,
            seed_entity_id=seed_entity_id,
            task=task,
            evidence=evidence,
            result=result,
            related_entity_ids=tuple(related_entity_ids),
        )

        return evidence

    @classmethod
    def _search_result_from_standardized_record(
        cls,
        record: dict[str, Any],
        task: SearchTask,
    ) -> dict[str, Any]:
        source = str(record.get("source_name") or task.source_hint)
        source_type = str(record.get("source_type") or "")
        title = str(record.get("title") or record.get("entity") or task.objective)
        summary = str(record.get("summary") or "").strip()
        evidence_lines = record.get("evidence") if isinstance(record.get("evidence"), list) else []
        claims = [
            cls._claim_text_from_evidence_line(item)
            for item in evidence_lines
            if cls._claim_text_from_evidence_line(item)
        ]
        if summary:
            claims.insert(0, summary)

        entity_name = str(record.get("entity") or "").strip()
        query_plan_lead = cls._record_is_query_plan_lead(record)
        promote_record_entity = bool(
            entity_name
            and not query_plan_lead
            and cls._record_entity_is_subject_entity(record, task)
        )
        attach_record_entities = (
            not query_plan_lead
            and (promote_record_entity or not cls._record_entity_requires_subject_match(record, task))
        )
        entities = []
        if promote_record_entity:
            entities.append(
                {
                    "kind": "company",
                    "name": entity_name,
                    "relation": "mentioned_with",
                    "confidence": record.get("confidence", 0.5),
                    "source": source,
                    **cls._record_identifier_attributes(record),
                    **cls._record_profile_attributes(record),
                }
            )
        if attach_record_entities:
            entities.extend(cls._entities_from_standardized_record(record, claims))

        return {
            "source": source,
            "source_hint": record.get("source_hint") or source,
            "title": title,
            "url": record.get("url"),
            "observed_at": record.get("published_at") or record.get("retrieved_at"),
            "confidence": record.get("confidence", 0.5),
            "claims": claims,
            "entities": entities,
            "relations": [] if query_plan_lead else cls._structured_relations_from_record(record),
            "candidate_entity": "" if query_plan_lead else entity_name if promote_record_entity or source != "wikidata_public_entity_graph" else "",
            "raw": record.get("raw"),
            "source_type": source_type,
            "evidence_type": cls._infer_evidence_type_from_record(record, task).value,
            "structured_risk_events": [] if query_plan_lead else cls._structured_risk_events_from_record(record),
            "entity_match": record.get("entity_match"),
            "record_source_type": source_type,
            "field_contract": record.get("field_contract"),
            "qyyjt_module": record.get("qyyjt_module"),
        }

    @staticmethod
    def _record_is_query_plan_lead(record: dict[str, Any]) -> bool:
        source_type = str(record.get("source_type") or "").strip().lower()
        if source_type in {"query_plan", "rich_query_plan"}:
            return True
        entity_match = record.get("entity_match")
        if (
            isinstance(entity_match, dict)
            and str(entity_match.get("record_source_type") or "").strip().lower()
            in {"query_plan", "rich_query_plan"}
        ):
            return True
        source_hint = str(record.get("source_hint") or record.get("source_name") or "").strip().lower()
        return source_hint == "qyyjt_websearch_plan"

    @staticmethod
    def _record_identifier_attributes(record: dict[str, Any]) -> dict[str, Any]:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        identifiers: dict[str, Any] = {}
        for target, keys in {
            "cik": ("cik", "cik_str"),
            "lei": ("lei",),
            "ticker": ("ticker", "symbol"),
            "wikidata_id": ("wikidata_id", "id"),
            "unified_social_credit_code": ("unified_social_credit_code", "unifiedSocialCreditCode", "creditCode", "uscc", "code"),
            "registration_number": ("registration_number", "registrationNo", "regNo"),
        }.items():
            for key in keys:
                value = record.get(key)
                if value in (None, ""):
                    value = raw.get(key)
                if value not in (None, ""):
                    identifiers[target] = str(value)
                    break
        if raw:
            identifiers["raw"] = raw
        return identifiers

    @staticmethod
    def _record_profile_attributes(record: dict[str, Any]) -> dict[str, Any]:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        extracted = record.get("extracted_fields") if isinstance(record.get("extracted_fields"), dict) else {}
        attributes: dict[str, Any] = {}
        for target, keys in {
            "legal_name": ("legal_name", "name", "entName", "companyName", "enterpriseName"),
            "registry_status": ("status", "regStatus", "businessStatus", "state"),
            "legal_representative": ("legal_representative", "legalRep", "legalPerson", "frName"),
            "registered_address": ("registered_address", "address", "regAddress"),
            "registered_capital": ("registered_capital", "regCapital", "registeredCapital", "capital", "regCap"),
            "establishment_date": ("establishment_date", "estiblishTime", "establishTime", "establishedDate", "setupDate", "startDate"),
            "operating_period": ("operating_period", "operatingPeriod", "businessTerm", "term"),
            "registration_authority": ("registration_authority", "regInstitute", "registrationAuthority", "authority", "regOrg"),
            "business_scope": ("business_scope", "businessScope", "scope", "opscope"),
            "company_type": ("company_type", "companyType", "entType", "enterpriseType", "type"),
        }.items():
            for source in (record, extracted, raw):
                value = next(
                    (source.get(key) for key in keys if source.get(key) not in (None, "")),
                    None,
                )
                if value not in (None, ""):
                    attributes[target] = str(value)
                    break
            if target in attributes:
                continue
        return attributes

    @classmethod
    def _record_entity_is_subject_entity(cls, record: dict[str, Any], task: SearchTask) -> bool:
        """Return true when record.entity should be promoted to a graph company."""
        source_hint = str(record.get("source_hint") or record.get("source_name") or "")
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        entity_name = str(record.get("entity") or "").strip()
        evidence_type = cls._infer_evidence_type_from_record(record, task)
        raw_match = record.get("entity_match")
        if isinstance(raw_match, dict) and raw_match:
            level = str(raw_match.get("level") or "").strip()
            if level in {"exact", "strong"}:
                return True
            if level and level not in {"exact", "strong"}:
                return False
        if source_hint == "wikidata_public_entity_graph":
            identifiers = cls._record_identifier_attributes(record)
            match = EntityResolutionScorer.score(task.query, entity_name, identifiers)
            return bool(identifiers.get("wikidata_id") and match["score"] >= 0.95)
        if evidence_type in {
            EvidenceType.REGISTRY_RECORD,
            EvidenceType.PUBLIC_NOTICE,
            EvidenceType.DATABASE_RESULT,
        }:
            if not entity_name or not task.query:
                return True
            match = EntityResolutionScorer.score(task.query, entity_name, raw)
            return str(match.get("level") or "") in {"exact", "strong"}
        return False

    @classmethod
    def _record_entity_requires_subject_match(cls, record: dict[str, Any], task: SearchTask) -> bool:
        if not str(record.get("entity") or "").strip() or not task.query:
            return False
        source_hint = str(record.get("source_hint") or record.get("source_name") or "")
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        if source_hint == "wikidata_public_entity_graph" and (
            record.get("wikidata_endpoint") == "entitydata"
            or raw.get("claims")
            or any(str(item.get("source") or "") == "Wikidata" for item in record.get("entities", []) if isinstance(item, dict))
        ):
            return False
        if source_hint in {"wikidata_public_entity_graph", "gleif_lei_public_api"}:
            return True
        return cls._infer_evidence_type_from_record(record, task) in {
            EvidenceType.REGISTRY_RECORD,
            EvidenceType.PUBLIC_NOTICE,
            EvidenceType.DATABASE_RESULT,
        }

    @staticmethod
    def _claim_text_from_evidence_line(item: Any) -> str:
        if not isinstance(item, dict):
            return str(item).strip()
        direct = item.get("claim") or item.get("text") or item.get("value")
        if direct:
            return str(direct).strip()
        provider = str(item.get("provider") or item.get("source") or "").strip()
        parts: list[str] = []
        for key in (
            "lei",
            "cik",
            "ticker",
            "registration_authority",
            "jurisdiction",
            "registered_address",
            "headquarters_address",
            "recent_filings_count",
            "revenue",
            "net_income",
            "operating_cash_flow",
            "net_margin",
            "cash_conversion",
            "debt_to_assets",
            "debt_to_equity",
        ):
            value = item.get(key)
            if value not in (None, ""):
                parts.append(f"{key}={value}")
        if provider and parts:
            return f"{provider}: " + "; ".join(parts)
        if parts:
            return "; ".join(parts)
        return ""

    @classmethod
    def _ingest_structured_risk_events(
        cls,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        task: SearchTask,
        evidence: EvidenceItem,
        result: dict[str, Any],
        related_entity_ids: tuple[str, ...] = (),
    ) -> list[RiskEvent]:
        events = cls._coerce_structured_risk_events(result)
        ingested: list[RiskEvent] = []
        entity_ids = tuple(dict.fromkeys((seed_entity_id, *related_entity_ids)))
        for event_payload in events:
            category = cls._risk_category(event_payload.get("category") or event_payload.get("risk_category"), task)
            severity = cls._risk_severity(event_payload.get("severity") or event_payload.get("risk_level"))
            title = str(
                event_payload.get("title")
                or event_payload.get("name")
                or event_payload.get("event")
                or "Structured risk signal"
            ).strip()
            rationale = str(
                event_payload.get("rationale")
                or event_payload.get("summary")
                or event_payload.get("description")
                or "Connector returned a structured risk event."
            ).strip()
            status = str(event_payload.get("status") or "open").strip() or "open"
            confidence = cls._clamp_confidence(event_payload.get("confidence", evidence.confidence))
            event = RiskEvent(
                id=cls._structured_event_id(category, entity_ids, evidence.id, title, severity),
                category=category,
                title=title,
                severity=severity,
                entity_ids=entity_ids,
                evidence_ids=(evidence.id,),
                confidence=confidence,
                rationale=rationale,
                status=status,
            )
            graph.add_risk_event(event)
            ingested.append(event)
        return ingested

    @classmethod
    def _coerce_structured_risk_events(cls, result: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = result.get("structured_risk_events")
        if candidates is None:
            candidates = result.get("risk_events")
        if candidates is None and any(key in result for key in ("risk_category", "risk_level", "severity")):
            candidates = [result]
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []
        return [item for item in candidates if isinstance(item, dict)]

    @classmethod
    def _structured_risk_events_from_record(cls, record: dict[str, Any]) -> list[dict[str, Any]]:
        events = record.get("risk_events")
        if isinstance(events, dict):
            events = [events]
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
        if any(key in record for key in ("risk_category", "risk_level", "severity")):
            return [
                {
                    "category": record.get("risk_category") or record.get("category"),
                    "severity": record.get("severity") or record.get("risk_level"),
                    "title": record.get("risk_title") or record.get("title"),
                    "summary": record.get("risk_summary") or record.get("summary"),
                    "confidence": record.get("confidence"),
                    "status": record.get("status"),
                }
            ]
        return []

    @classmethod
    def _structured_relations_from_record(cls, record: dict[str, Any]) -> list[dict[str, Any]]:
        relations = record.get("relations")
        if isinstance(relations, dict):
            relations = [relations]
        if not isinstance(relations, list):
            return []
        return [item for item in relations if isinstance(item, dict)]

    @staticmethod
    def _risk_category(raw: Any, task: SearchTask) -> RetrievalDomain:
        if raw:
            normalized = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
            aliases = {
                "court": RetrievalDomain.COURT_ENFORCEMENT,
                "litigation": RetrievalDomain.COURT_ENFORCEMENT,
                "enforcement": RetrievalDomain.COURT_ENFORCEMENT,
                "administrative": RetrievalDomain.ADMINISTRATIVE_RISK,
                "regulatory": RetrievalDomain.ADMINISTRATIVE_RISK,
                "ownership": RetrievalDomain.OWNERSHIP_CONTROL,
                "controller": RetrievalDomain.OWNERSHIP_CONTROL,
                "public_opinion": RetrievalDomain.NEWS_PUBLIC_OPINION,
                "negative_news": RetrievalDomain.NEWS_PUBLIC_OPINION,
                "asset": RetrievalDomain.LOCATION_ASSETS,
                "capital_market": RetrievalDomain.FINANCING_CAPITAL_MARKETS,
            }
            if normalized in aliases:
                return aliases[normalized]
            try:
                return RetrievalDomain(normalized)
            except ValueError:
                pass
        return task.domain

    @staticmethod
    def _risk_severity(raw: Any) -> RiskSeverity:
        normalized = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "severe": RiskSeverity.HIGH,
            "major": RiskSeverity.HIGH,
            "warning": RiskSeverity.MEDIUM,
            "medium_risk": RiskSeverity.MEDIUM,
            "high_risk": RiskSeverity.HIGH,
            "critical_risk": RiskSeverity.CRITICAL,
            "low_risk": RiskSeverity.LOW,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return RiskSeverity(normalized)
        except ValueError:
            return RiskSeverity.MEDIUM

    @staticmethod
    def _structured_event_id(
        category: RetrievalDomain,
        entity_ids: tuple[str, ...],
        evidence_id: str,
        title: str,
        severity: RiskSeverity,
    ) -> str:
        payload = {
            "category": category.value,
            "entity_ids": entity_ids,
            "evidence_id": evidence_id,
            "title": title,
            "severity": severity.value,
            "kind": "structured",
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return f"risk:{digest}"

    @classmethod
    def _entities_from_standardized_record(
        cls,
        record: dict[str, Any],
        claims: list[str],
    ) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        entities.extend(cls._explicit_entities(record.get("entities")))
        raw = record.get("raw")
        if isinstance(raw, dict):
            entities.extend(cls._explicit_entities(raw.get("entities")))
            entities.extend(cls._field_entities(raw))
        entities.extend(cls._field_entities(record))

        evidence_lines = record.get("evidence")
        if isinstance(evidence_lines, list):
            for item in evidence_lines:
                if isinstance(item, dict):
                    entities.extend(cls._explicit_entities([item]))

        text = " ".join(
            str(item)
            for item in [
                record.get("title"),
                record.get("summary"),
                *claims,
            ]
            if item
        )
        entities.extend(cls._pattern_entities(text))
        return cls._dedupe_entity_dicts(entities)

    @classmethod
    def _field_entities(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for kind, keys, relation in cls.FIELD_ENTITY_MAP:
            for key in keys:
                if key not in payload:
                    continue
                for value in cls._coerce_entity_values(payload.get(key)):
                    name = cls._normalize_entity_name(value)
                    if not name:
                        continue
                    entities.append(
                        {
                            "kind": kind.value,
                            "name": name,
                            "relation": cls._field_relation(key, relation),
                            "confidence": 0.68,
                            "field": key,
                            **cls._field_entity_attributes(value),
                        }
                    )
        return entities

    @staticmethod
    def _field_relation(key: str, fallback: str) -> str:
        normalized = str(key or "").strip().lower()
        relation_by_key = {
            "legal_representative": "legal_representative",
            "legalrep": "legal_representative",
            "legalrepname": "legal_representative",
            "legalperson": "legal_representative",
            "frname": "legal_representative",
            "actual_controller": "actual_controller",
            "actualcontroller": "actual_controller",
            "actualcontrollername": "actual_controller",
            "controller": "controller",
            "controllername": "controller",
            "control_person": "controller",
            "controlperson": "controller",
            "beneficial_owner": "beneficial_owner",
            "beneficialowner": "beneficial_owner",
            "beneficialownername": "beneficial_owner",
            "ultimate_beneficial_owner": "beneficial_owner",
            "ultimatebeneficialowner": "beneficial_owner",
            "ubo": "beneficial_owner",
            "shareholder": "shareholder",
            "shareholders": "shareholder",
            "shareholdername": "shareholder",
            "investorname": "shareholder",
            "controlling_shareholder": "controlling_shareholder",
            "controllingshareholder": "controlling_shareholder",
            "chairman": "chairman",
            "director": "director",
            "directorname": "director",
            "supervisor": "supervisor",
            "supervisorname": "supervisor",
            "manager": "manager",
            "managername": "manager",
            "executive": "executive",
            "executives": "executive",
            "registered_address": "registered_address",
            "registration_address": "registered_address",
            "office_address": "office_address",
            "business_address": "business_address",
        }
        return relation_by_key.get(normalized, fallback)

    @staticmethod
    def _field_entity_attributes(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        aliases = {
            "ownership_ratio": ("ownership_ratio", "shareRatio", "ratio", "percent", "holdingRatio"),
            "layer_depth": ("layer_depth", "depth", "level", "layer"),
            "control_path": ("control_path", "controlPath", "path"),
            "path_nodes": ("path_nodes", "pathNodes", "nodes"),
            "confidence_basis": ("confidence_basis", "basis", "reason", "confidenceBasis"),
            "position": ("position", "title", "roleName", "post"),
        }
        attributes: dict[str, Any] = {}
        lowered = {str(key).lower(): value for key, value in raw.items()}
        for target, keys in aliases.items():
            for key in keys:
                value = raw.get(key)
                if value in (None, ""):
                    value = lowered.get(key.lower())
                if value not in (None, ""):
                    attributes[target] = value
                    break
        return attributes

    @classmethod
    def _explicit_entities(cls, raw_entities: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_entities, list):
            return []
        entities: list[dict[str, Any]] = []
        for item in raw_entities:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind") or item.get("entity_kind") or item.get("type")
            name = item.get("name") or item.get("entity") or item.get("entity_name") or item.get("value")
            if not kind or not name:
                continue
            entities.append(
                {
                    **item,
                    "kind": str(kind),
                    "name": cls._normalize_entity_name(name),
                    "relation": str(item.get("relation") or item.get("relation_type") or "mentioned_with"),
                    "confidence": item.get("confidence", 0.7),
                }
            )
        return entities

    @classmethod
    def _pattern_entities(cls, text: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for email in cls.EMAIL_RE.findall(text):
            entities.append(
                {
                    "kind": EntityKind.EMAIL.value,
                    "name": email,
                    "relation": "public_contact_lead",
                    "confidence": 0.62,
                    "extraction": "pattern",
                }
            )
        for domain in cls.DOMAIN_RE.findall(text):
            normalized = domain.lower().strip(".")
            if normalized.startswith("www."):
                normalized = normalized[4:]
            entities.append(
                {
                    "kind": EntityKind.DOMAIN.value,
                    "name": normalized,
                    "relation": "public_web_footprint",
                    "confidence": 0.6,
                    "extraction": "pattern",
                }
            )
        for phone in cls.PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", phone)
            if 7 <= len(digits) <= 16 and cls._looks_like_public_contact(text, phone):
                entities.append(
                    {
                        "kind": EntityKind.PHONE.value,
                        "name": phone.strip(),
                        "relation": "public_contact_lead",
                        "confidence": 0.58,
                        "extraction": "pattern",
                    }
                )
        return entities

    @classmethod
    def _looks_like_public_contact(cls, text: str, value: str) -> bool:
        """Reject obvious filing identifiers that look like phone numbers."""
        start = text.find(value)
        lowered = text.lower()
        contact_markers = (
            "phone",
            "tel",
            "telephone",
            "mobile",
            "hotline",
            "contact",
            "call",
            "电话",
            "手机",
            "热线",
            "联系方式",
            "联系电话",
        )
        if not any(marker in lowered for marker in contact_markers):
            return False
        if start < 0:
            return True
        window = text[max(0, start - 32): start + len(value) + 16].lower()
        identifier_markers = (
            "cik",
            "lei",
            "accession",
            "filing",
            "docket",
            "case",
            "wikidata_id",
            "id=",
        )
        return not any(marker in window for marker in identifier_markers)

    @staticmethod
    def _coerce_entity_values(raw: Any) -> list[Any]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, tuple):
            return list(raw)
        return [raw]

    @staticmethod
    def _normalize_entity_name(raw: Any) -> str:
        if isinstance(raw, dict):
            raw = (
                raw.get("name")
                or raw.get("person_name")
                or raw.get("personName")
                or raw.get("entity")
                or raw.get("entity_name")
                or raw.get("entityName")
                or raw.get("shareholderName")
                or raw.get("investorName")
                or raw.get("actualControllerName")
                or raw.get("actualController")
                or raw.get("controllerName")
                or raw.get("beneficialOwnerName")
                or raw.get("beneficialOwner")
                or raw.get("ultimateBeneficialOwner")
                or raw.get("legalRepName")
                or raw.get("legalRep")
                or raw.get("legalPerson")
                or raw.get("frName")
                or raw.get("value")
                or raw.get("title")
            )
        return " ".join(str(raw or "").split())

    @staticmethod
    def _dedupe_entity_dicts(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for entity in entities:
            kind = str(entity.get("kind") or "").strip()
            name = " ".join(str(entity.get("name") or "").split())
            relation = str(entity.get("relation") or "mentioned_with")
            if not kind or not name:
                continue
            key = (kind.lower(), name.lower(), relation)
            current = deduped.get(key)
            if current is None or float(entity.get("confidence", 0.5) or 0.5) > float(current.get("confidence", 0.5) or 0.5):
                deduped[key] = {**entity, "kind": kind, "name": name, "relation": relation}
        return list(deduped.values())

    @classmethod
    def _entity_from_raw(cls, raw: Any, evidence_id: str) -> InvestigationEntity | None:
        if not isinstance(raw, dict):
            return None
        try:
            kind = EntityKind(str(raw.get("kind")))
        except ValueError:
            return None
        name = str(raw.get("name") or "").strip()
        if not name:
            return None
        return InvestigationEntity(
            id=cls._entity_id(kind, name),
            kind=kind,
            name=name,
            confidence=cls._clamp_confidence(raw.get("confidence", 0.5)),
            evidence_ids=[evidence_id],
            attributes={
                key: value
                for key, value in raw.items()
                if key not in {"kind", "name", "confidence", "relation"}
            },
        )

    @classmethod
    def _relation_from_raw(
        cls,
        raw: Any,
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        evidence_id: str,
    ) -> tuple[InvestigationRelation | None, tuple[str, ...]]:
        if not isinstance(raw, dict):
            return None, ()
        from_id = cls._relation_endpoint_id(
            raw,
            graph,
            seed_entity_id=seed_entity_id,
            evidence_id=evidence_id,
            side="from",
        )
        to_id = cls._relation_endpoint_id(
            raw,
            graph,
            seed_entity_id=seed_entity_id,
            evidence_id=evidence_id,
            side="to",
        )
        if not from_id or not to_id or from_id == to_id:
            return None, tuple(item for item in (from_id, to_id) if item)
        relation_type = str(raw.get("relation_type") or raw.get("relation") or "related").strip()
        relation = InvestigationRelation(
            from_id=from_id,
            to_id=to_id,
            relation_type=relation_type or "related",
            confidence=cls._clamp_confidence(raw.get("confidence", 0.7)),
            evidence_ids=(evidence_id,),
        )
        return relation, tuple(dict.fromkeys((from_id, to_id)))

    @classmethod
    def _relation_endpoint_id(
        cls,
        raw: dict[str, Any],
        graph: EvidenceGraph,
        *,
        seed_entity_id: str,
        evidence_id: str,
        side: str,
    ) -> str | None:
        id_key = f"{side}_id"
        if raw.get(id_key) in graph.entities:
            return str(raw[id_key])

        name = (
            raw.get(f"{side}_name")
            or raw.get(f"{side}_entity")
            or raw.get(side)
            or raw.get("source" if side == "from" else "target")
        )
        name_text = cls._normalize_entity_name(name)
        seed = graph.entities.get(seed_entity_id)
        if not name_text:
            return seed_entity_id if side == "from" else None
        if name_text == seed_entity_id or (seed and cls._same_entity_name(name_text, seed.name)):
            graph.attach_evidence_to_entity(seed_entity_id, evidence_id)
            return seed_entity_id

        kind_text = str(raw.get(f"{side}_kind") or raw.get(f"{side}_type") or "company").strip()
        try:
            kind = EntityKind(kind_text)
        except ValueError:
            kind = EntityKind.PERSON if kind_text.lower() == "person" else EntityKind.COMPANY
        entity = InvestigationEntity(
            id=cls._entity_id(kind, name_text),
            kind=kind,
            name=name_text,
            confidence=cls._clamp_confidence(raw.get("confidence", 0.7)),
            evidence_ids=[evidence_id],
            attributes={
                key: value
                for key, value in raw.items()
                if key
                not in {
                    "from",
                    "from_id",
                    "from_name",
                    "from_entity",
                    "from_kind",
                    "from_type",
                    "to",
                    "to_id",
                    "to_name",
                    "to_entity",
                    "to_kind",
                    "to_type",
                    "relation",
                    "relation_type",
                    "confidence",
                }
            },
        )
        graph.add_entity(entity)
        return entity.id

    @staticmethod
    def _same_entity_name(left: str, right: str) -> bool:
        return " ".join(str(left or "").casefold().split()) == " ".join(str(right or "").casefold().split())

    @staticmethod
    def _evidence_type(raw_type: Any, task: SearchTask) -> EvidenceType:
        if raw_type:
            try:
                return EvidenceType(str(raw_type))
            except ValueError:
                pass
        if task.expected_evidence:
            return task.expected_evidence[0]
        return EvidenceType.DERIVED_CLUE

    @staticmethod
    def _infer_evidence_type_from_record(record: dict[str, Any], task: SearchTask) -> EvidenceType:
        if EvidenceIngestor._record_is_query_plan_lead(record):
            return EvidenceType.DERIVED_CLUE
        contract = record.get("field_contract")
        record_type = str(contract.get("record_type") or "") if isinstance(contract, dict) else ""
        if record_type in {
            "registry_identity",
            "controller_candidate",
            "related_party_edge",
            "ubo_path",
            "group_network_edge",
            "financial_statement_metric",
            "financial_indicator",
            "credit_profile",
        }:
            return EvidenceType.DATABASE_RESULT
        if record_type in {
            "court_case",
            "dishonesty_record",
            "limit_high_consumption",
            "enforcement_record",
        }:
            return EvidenceType.COURT_RECORD
        if record_type in {"administrative_penalty", "risk_overview", "risk_signal"}:
            return EvidenceType.ADMINISTRATIVE_RECORD
        text = " ".join(
            str(record.get(key) or "")
            for key in ("title", "summary", "source_name", "source_type")
        )
        if any(keyword in text.lower() for keyword in ("court", "法院", "执行", "失信", "诉讼")):
            return EvidenceType.COURT_RECORD
        if any(keyword in text.lower() for keyword in ("notice", "公告", "披露", "公示")):
            return EvidenceType.PUBLIC_NOTICE
        if any(keyword in text.lower() for keyword in ("news", "新闻", "舆情", "媒体")):
            return EvidenceType.NEWS_ARTICLE
        if any(keyword in text.lower() for keyword in ("social", "微博", "微信", "linkedin", "github")):
            return EvidenceType.SOCIAL_POST
        if task.expected_evidence:
            return task.expected_evidence[0]
        return EvidenceType.DATABASE_RESULT

    @classmethod
    def _entity_match(cls, seed_name: str, result: dict[str, Any]) -> dict[str, Any] | None:
        def with_record_metadata(match: dict[str, Any] | None) -> dict[str, Any] | None:
            source_type = str(result.get("record_source_type") or result.get("source_type") or "").strip()
            if not source_type:
                return match
            enriched = dict(match or {})
            enriched["record_source_type"] = source_type
            return enriched

        raw_match = result.get("entity_match")
        if isinstance(raw_match, dict) and raw_match:
            return with_record_metadata(raw_match)
        candidate = str(
            result.get("entity")
            or result.get("candidate_entity")
            or result.get("company")
            or ""
        ).strip()
        if not candidate:
            for raw_entity in result.get("entities", []):
                if not isinstance(raw_entity, dict):
                    continue
                if str(raw_entity.get("kind") or "") == EntityKind.COMPANY.value:
                    candidate = str(raw_entity.get("name") or "").strip()
                    if candidate:
                        break
        if not candidate:
            return with_record_metadata(None)
        raw_payload = result.get("raw") if isinstance(result.get("raw"), dict) else {}
        return with_record_metadata(EntityResolutionScorer.score(seed_name, candidate, raw_payload))

    @staticmethod
    def _clamp_confidence(raw: Any) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.5
        return max(0.0, min(1.0, value))

    @staticmethod
    def _source_profile(result: dict[str, Any], task: SearchTask) -> SourceProfile:
        raw_profile = result.get("source_profile")
        if isinstance(raw_profile, SourceProfile):
            return raw_profile
        source_hint = result.get("source_hint") or task.source_hint
        return SourceCatalog.profile_for(str(source_hint))

    @staticmethod
    def _entity_id(kind: EntityKind, name: str) -> str:
        normalized = "_".join(name.lower().split())
        return f"{kind.value}:{normalized}"

    @staticmethod
    def _stable_id(prefix: str, payload: Any) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{digest}"


@dataclass
class RetrievalPlan:
    seed_company: str
    tasks: list[SearchTask]
    graph: EvidenceGraph
    compliance_notes: list[str]
    coverage_domains: set[RetrievalDomain]

    def by_domain(self, domain: RetrievalDomain) -> list[SearchTask]:
        return [task for task in self.tasks if task.domain == domain]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_company": self.seed_company,
            "coverage_domains": sorted(domain.value for domain in self.coverage_domains),
            "tasks": [
                {
                    "domain": task.domain.value,
                    "query": task.query,
                    "source_hint": task.source_hint,
                    "objective": task.objective,
                    "priority": task.priority,
                    "retrieval_layer": task.effective_retrieval_layer().value,
                    "expected_evidence": [item.value for item in task.expected_evidence],
                    "fanout_entities": [item.value for item in task.fanout_entities],
                    "source_profile": task.resolved_source_profile().to_dict(),
                    "params": task.params,
                }
                for task in self.tasks
            ],
            "graph": {
                "entities": {
                    key: {
                        "kind": entity.kind.value,
                        "name": entity.name,
                        "confidence": entity.confidence,
                        "evidence_ids": entity.evidence_ids,
                        "attributes": entity.attributes,
                    }
                    for key, entity in self.graph.entities.items()
                },
                "evidence": {
                    key: {
                        "type": item.evidence_type.value,
                        "source": item.source,
                        "title": item.title,
                        "url": item.url,
                        "observed_at": item.observed_at,
                        "confidence": item.confidence,
                        "claims": list(item.claims),
                        "source_profile": (
                            item.source_profile.to_dict()
                            if item.source_profile
                            else SourceCatalog.profile_for(item.source).to_dict()
                        ),
                        "entity_match": item.entity_match,
                    }
                    for key, item in self.graph.evidence.items()
                },
                "relations": [
                    {
                        "from_id": relation.from_id,
                        "to_id": relation.to_id,
                        "relation_type": relation.relation_type,
                        "confidence": relation.confidence,
                        "evidence_ids": list(relation.evidence_ids),
                    }
                    for relation in self.graph.relations
                ],
                "risk_events": [
                    {
                        "id": event.id,
                        "category": event.category.value,
                        "title": event.title,
                        "severity": event.severity.value,
                        "entity_ids": list(event.entity_ids),
                        "evidence_ids": list(event.evidence_ids),
                        "confidence": event.confidence,
                        "rationale": event.rationale,
                        "status": event.status,
                    }
                    for event in self.graph.risk_events
                ],
            },
            "compliance_notes": self.compliance_notes,
        }


class InvestigativeRetrievalPlanner:
    """Builds broad, associative retrieval plans from a company seed."""

    REQUIRED_DOMAINS = {
        RetrievalDomain.CORPORATE_REGISTRY,
        RetrievalDomain.OWNERSHIP_CONTROL,
        RetrievalDomain.PEOPLE,
        RetrievalDomain.RELATED_ENTITIES,
        RetrievalDomain.COURT_ENFORCEMENT,
        RetrievalDomain.ADMINISTRATIVE_RISK,
        RetrievalDomain.NEWS_PUBLIC_OPINION,
        RetrievalDomain.SOCIAL_WEB,
        RetrievalDomain.LOCATION_ASSETS,
    }

    def build_company_plan(self, company_name: str) -> RetrievalPlan:
        seed = self._normalize_seed(company_name)
        seed_id = self._entity_id(EntityKind.COMPANY, seed)
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

        tasks = self._seed_tasks(seed)
        coverage = {task.domain for task in tasks}

        return RetrievalPlan(
            seed_company=seed,
            tasks=sorted(tasks, key=lambda item: (item.priority, item.domain.value, item.query)),
            graph=graph,
            compliance_notes=[
                "Use public, licensed, or user-authorized sources only.",
                "Store source, query, timestamp, and confidence with every claim.",
                "Treat social-web clues as leads until corroborated by higher-authority evidence.",
                "Do not infer private spending or personal activity without public evidence.",
                "Connector shape is neutral: REST APIs, public webpages, official platforms, and bots are allowed only when the data is public or authorized and provenance is retained.",
            ],
            coverage_domains=coverage,
        )

    def expand_from_entity(self, entity: InvestigationEntity) -> list[SearchTask]:
        name = entity.name
        if entity.kind is EntityKind.PERSON:
            return [
                SearchTask(
                    RetrievalDomain.PEOPLE,
                    f'"{name}" 履历 任职 股东 高管',
                    "web_search",
                    "Map public career history and company affiliations.",
                    20,
                    (EvidenceType.WEBPAGE, EvidenceType.NEWS_ARTICLE),
                    (EntityKind.COMPANY, EntityKind.PERSON),
                ),
                SearchTask(
                    RetrievalDomain.SOCIAL_WEB,
                    f'"{name}" 微博 微信公众号 抖音 LinkedIn GitHub',
                    "web_search",
                    "Find public social/account traces for corroborated identity leads.",
                    45,
                    (EvidenceType.SOCIAL_POST, EvidenceType.WEBPAGE),
                    (EntityKind.ACCOUNT, EntityKind.COMPANY, EntityKind.PERSON),
                ),
                SearchTask(
                    RetrievalDomain.COURT_ENFORCEMENT,
                    f'"{name}" 失信 被执行人 限制高消费 裁判文书',
                    "court_and_credit_sources",
                    "Check public court and enforcement traces for the person.",
                    25,
                    (EvidenceType.COURT_RECORD, EvidenceType.ADMINISTRATIVE_RECORD),
                    (EntityKind.CASE, EntityKind.COMPANY),
                ),
                SearchTask(
                    RetrievalDomain.OWNERSHIP_CONTROL,
                    f'"{name}" actual controller beneficial owner shareholder holding company',
                    "registry_and_web_search",
                    "Corroborate whether this person is a controller, UBO, shareholder, or nominee lead.",
                    22,
                    (EvidenceType.REGISTRY_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
                    (EntityKind.COMPANY, EntityKind.PERSON),
                ),
                SearchTask(
                    RetrievalDomain.ADMINISTRATIVE_RISK,
                    f'"{name}" public administrative penalty traffic violation regulatory notice',
                    "public_behavior_sources",
                    "Collect public behavior-risk records relevant to credit and compliance review.",
                    32,
                    (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
                    (EntityKind.CASE, EntityKind.COMPANY),
                ),
                SearchTask(
                    RetrievalDomain.LOCATION_ASSETS,
                    f'"{name}" public property vehicle collateral auction address activity city',
                    "public_asset_sources",
                    "Collect public asset, solvency, address, and activity-location leads.",
                    34,
                    (EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
                    (EntityKind.ASSET, EntityKind.ADDRESS, EntityKind.COMPANY),
                ),
                SearchTask(
                    RetrievalDomain.RELATED_ENTITIES,
                    f'"{name}" related company investment appointment project counterparty',
                    "relationship_network_sources",
                    "Expand multi-hop public relationship network around the controller candidate.",
                    36,
                    (EvidenceType.REGISTRY_RECORD, EvidenceType.WEBPAGE, EvidenceType.PUBLIC_NOTICE),
                    (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.PROJECT),
                ),
            ]

        if entity.kind is EntityKind.ADDRESS:
            return [
                SearchTask(
                    RetrievalDomain.RELATED_ENTITIES,
                    f'"{name}" 公司 注册地址 联系地址',
                    "registry_or_web_search",
                    "Find companies sharing the same address.",
                    30,
                    (EvidenceType.REGISTRY_RECORD, EvidenceType.WEBPAGE),
                    (EntityKind.COMPANY, EntityKind.PERSON),
                )
            ]

        if entity.kind is EntityKind.ACCOUNT:
            return [
                SearchTask(
                    RetrievalDomain.SOCIAL_WEB,
                    f'"{name}" 公司 项目 投资 任职',
                    "web_search",
                    "Correlate public account activity with entities, projects, and people.",
                    40,
                    (EvidenceType.SOCIAL_POST, EvidenceType.WEBPAGE),
                    (EntityKind.PERSON, EntityKind.COMPANY, EntityKind.PROJECT),
                )
            ]

        return []

    @staticmethod
    def _case_params(track: str, *questions: str) -> dict[str, Any]:
        return {
            "investigation_lens": "扒光查案式调查",
            "investigation_track": track,
            "case_questions": [question for question in questions if question],
        }

    def _seed_tasks(self, company: str) -> list[SearchTask]:
        return [
            SearchTask(
                RetrievalDomain.CORPORATE_REGISTRY,
                f"{company} 工商信息 注册资本 法定代表人 成立时间",
                "registry_sources",
                "Establish legal identity and authoritative base facts.",
                10,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.DATABASE_RESULT),
                (EntityKind.PERSON, EntityKind.ADDRESS, EntityKind.PHONE, EntityKind.EMAIL),
                params=self._case_params("people", "主体是谁？法定代表人、地址、联系方式是否能锁定同一主体？"),
            ),
            SearchTask(
                RetrievalDomain.OWNERSHIP_CONTROL,
                f"{company} 实际控制人 最终受益人 股权穿透 控股股东",
                "registry_and_commercial_sources",
                "Identify UBO/controller and control chain.",
                10,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.PERSON, EntityKind.COMPANY),
                params=self._case_params("people", "谁实际控制这家公司？股权链、受益人和代持线索是否一致？"),
            ),
            SearchTask(
                RetrievalDomain.PEOPLE,
                f"{company} 法定代表人 董监高 股东 高管 履历",
                "registry_and_web_search",
                "Build the people roster for person-level fan-out.",
                15,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.WEBPAGE),
                (EntityKind.PERSON, EntityKind.COMPANY),
                params=self._case_params("people", "关键人都是谁？各自任职、履历、关联公司和风险记录是什么？"),
            ),
            SearchTask(
                RetrievalDomain.RELATED_ENTITIES,
                f"{company} 关联企业 子公司 分公司 对外投资 关联交易",
                "registry_and_disclosure_sources",
                "Discover related companies and transaction paths.",
                20,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.ADDRESS),
                params=self._case_params("people", "关联主体如何连接？是否存在共同地址、共同任职、投资和关联交易路径？"),
            ),
            SearchTask(
                RetrievalDomain.RELATED_ENTITIES,
                company,
                "wikidata_public_entity_graph",
                "Corroborate public entity graph identifiers, official website, executives, subsidiaries, and owner leads.",
                21,
                (EvidenceType.DATABASE_RESULT, EvidenceType.WEBPAGE),
                (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.DOMAIN),
            ),
            SearchTask(
                RetrievalDomain.COURT_ENFORCEMENT,
                f"{company} 裁判文书 被执行人 失信 限制高消费 开庭公告",
                "court_and_credit_sources",
                "Collect litigation and enforcement risk signals.",
                20,
                (EvidenceType.COURT_RECORD, EvidenceType.DATABASE_RESULT),
                (EntityKind.CASE, EntityKind.PERSON, EntityKind.COMPANY),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                f"{company} 行政处罚 经营异常 严重违法 税务处罚 环保处罚",
                "government_credit_sources",
                "Collect administrative and regulatory risk signals.",
                25,
                (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.DATABASE_RESULT),
                (EntityKind.COMPANY, EntityKind.PERSON),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                company,
                "opensanctions_public_dataset_catalog",
                "Check public dataset coverage for sanctions, PEP, debarment, enforcement, and related-person screening.",
                26,
                (EvidenceType.DATABASE_RESULT, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.COMPANY, EntityKind.PERSON),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                company,
                "ofac_consolidated_sanctions_xml",
                "Screen the subject against official public OFAC consolidated sanctions data.",
                27,
                (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.COMPANY, EntityKind.PERSON),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                company,
                "un_sc_consolidated_sanctions_xml",
                "Screen the subject against official public UN Security Council consolidated sanctions data.",
                28,
                (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.COMPANY, EntityKind.PERSON),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                company,
                "idb_sanctioned_firms_dataset_catalog",
                "Check public IDB sanctions dataset coverage for procurement and debarment screening.",
                29,
                (EvidenceType.DATABASE_RESULT, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.COMPANY, EntityKind.PERSON),
            ),
            SearchTask(
                RetrievalDomain.NEWS_PUBLIC_OPINION,
                f"{company} 负面新闻 舆情 投诉 维权 事故 纠纷",
                "news_and_web_search",
                "Find public-opinion, complaint, and event leads.",
                30,
                (EvidenceType.NEWS_ARTICLE, EvidenceType.WEBPAGE),
                (EntityKind.PERSON, EntityKind.PROJECT, EntityKind.ADDRESS),
            ),
            SearchTask(
                RetrievalDomain.SOCIAL_WEB,
                f'"{company}" 微博 微信公众号 抖音 小红书 LinkedIn GitHub 招聘',
                "public_account_sources",
                "Find public account, recruiting, social, and technical traces.",
                35,
                (EvidenceType.SOCIAL_POST, EvidenceType.WEBPAGE),
                (EntityKind.ACCOUNT, EntityKind.PERSON, EntityKind.DOMAIN),
                params=self._case_params("people", "公开账号、招聘和技术痕迹是否能补充关键人、项目和经营活动线索？"),
            ),
            SearchTask(
                RetrievalDomain.PEOPLE,
                f"{company} legal representative actual controller public identity verification profile",
                "public_contact_sources",
                "Extract and verify public identity, contact, and role leads for key persons.",
                18,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.WEBPAGE, EvidenceType.PUBLIC_NOTICE),
                (EntityKind.PERSON, EntityKind.PHONE, EntityKind.EMAIL, EntityKind.ACCOUNT),
                params=self._case_params("people", "关键人身份、联系方式和角色是否能交叉核验？"),
            ),
            SearchTask(
                RetrievalDomain.RELATED_ENTITIES,
                f"{company} controller related person related company shared address shared phone shared project",
                "relationship_network_sources",
                "Build multi-hop associated subjects for recursive public-intelligence expansion.",
                22,
                (EvidenceType.REGISTRY_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
                (EntityKind.COMPANY, EntityKind.PERSON, EntityKind.ADDRESS, EntityKind.PROJECT),
                params=self._case_params("people", "控制人、关联人、关联公司、共同地址和项目对手能否形成关系网络？"),
            ),
            SearchTask(
                RetrievalDomain.LOCATION_ASSETS,
                f"{company} public property vehicle collateral auction repayment capacity solvency",
                "public_asset_sources",
                "Collect public asset and solvency signals for credit assessment.",
                38,
                (EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
                (EntityKind.ASSET, EntityKind.ADDRESS, EntityKind.PERSON),
                params=self._case_params("money", "资产、质押、冻结、拍卖和偿付能力是否解释资金压力？"),
            ),
            SearchTask(
                RetrievalDomain.ADMINISTRATIVE_RISK,
                f"{company} actual controller public traffic violation administrative penalty behavior risk",
                "public_behavior_sources",
                "Collect public behavior-risk leads for the enterprise and controller candidates.",
                39,
                (EvidenceType.ADMINISTRATIVE_RECORD, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
                (EntityKind.PERSON, EntityKind.CASE, EntityKind.COMPANY),
            ),
            SearchTask(
                RetrievalDomain.LOCATION_ASSETS,
                f"{company} 地址 物业 招拍挂 不动产抵押 司法拍卖 车辆 采购",
                "asset_and_location_sources",
                "Trace public location, asset, mortgage, auction, and spending clues.",
                40,
                (EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
                (EntityKind.ADDRESS, EntityKind.ASSET, EntityKind.PROJECT),
                params=self._case_params("money", "资产、地址、抵押、拍卖和采购支出是否能解释钱往哪里去？"),
            ),
            SearchTask(
                RetrievalDomain.FINANCING_CAPITAL_MARKETS,
                f"{company} 融资 债券 担保 评级 募集说明书 受托管理报告",
                "capital_market_sources",
                "Find capital-market disclosures and debt/guarantee obligations.",
                45,
                (EvidenceType.PUBLIC_NOTICE, EvidenceType.DATABASE_RESULT),
                (EntityKind.COMPANY, EntityKind.PERSON),
                params=self._case_params("money", "钱从哪里来？融资、债券、担保、评级和偿债压力是否互相印证？"),
            ),
            SearchTask(
                RetrievalDomain.PROCUREMENT_PROJECTS,
                f"{company} 中标 招投标 项目 合同 客户 供应商",
                "procurement_sources",
                "Discover projects, counterparties, and public spending traces.",
                50,
                (EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
                (EntityKind.PROJECT, EntityKind.COMPANY, EntityKind.ADDRESS),
                params=self._case_params("goods", "货往哪里去？项目、合同、客户和供应商是否能形成交易链？"),
            ),
            SearchTask(
                RetrievalDomain.PROCUREMENT_PROJECTS,
                f"{company} 上游 下游 供应商 客户 经销商 采购 销售 合作伙伴",
                "supply_chain_sources",
                "Deep-dive upstream, downstream, customers, suppliers, dealers, and cooperation relationships.",
                52,
                (EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE, EvidenceType.DATABASE_RESULT),
                (EntityKind.COMPANY, EntityKind.PROJECT, EntityKind.PERSON),
                params=self._case_params("goods", "货从哪里来、往哪里去？上下游、客户、供应商、经销商和伙伴是否集中或关联？"),
            ),
            SearchTask(
                RetrievalDomain.NEWS_PUBLIC_OPINION,
                f"{company} 行业 赛道 商业模式 竞争格局 市场份额 产品 客户价值 盈利模式",
                "industry_research_sources",
                "Build industry, business-model, competitive-position, product, and customer-value analysis leads.",
                53,
                (EvidenceType.NEWS_ARTICLE, EvidenceType.PUBLIC_NOTICE, EvidenceType.WEBPAGE),
                (EntityKind.COMPANY, EntityKind.PROJECT, EntityKind.DOMAIN),
                params=self._case_params("goods", "公司卖什么、靠什么赚钱？行业位置、竞品、客户价值和利润池是否清楚？"),
            ),
            SearchTask(
                RetrievalDomain.IP_TECH,
                f"{company} 专利 商标 软件著作权 域名 App 备案",
                "ip_and_tech_sources",
                "Find IP, domain, app, and technical footprint.",
                55,
                (EvidenceType.DATABASE_RESULT, EvidenceType.WEBPAGE),
                (EntityKind.DOMAIN, EntityKind.COMPANY, EntityKind.PERSON),
            ),
        ]

    @staticmethod
    def _normalize_seed(company_name: str) -> str:
        seed = " ".join(company_name.split())
        if not seed:
            raise ValueError("company_name cannot be empty")
        return seed

    @staticmethod
    def _entity_id(kind: EntityKind, name: str) -> str:
        normalized = "_".join(name.lower().split())
        return f"{kind.value}:{normalized}"
