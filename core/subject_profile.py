#!/usr/bin/env python3
"""Deep subject profile built from public or authorized evidence graphs."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .intelligence_retrieval import (
    EntityKind,
    EvidenceGraph,
    EvidenceItem,
    InvestigationEntity,
    InvestigationRelation,
    RetrievalDomain,
    SourceAccess,
)


class SubjectProfileDimension(str, Enum):
    """Public-intelligence dimensions used by due-diligence profiles."""

    IDENTITY = "identity"
    CONTROL_OWNERSHIP = "control_ownership"
    CONTACT_ACCOUNTS = "contact_accounts"
    LOCATION_ACTIVITY = "location_activity"
    ASSET_SOLVENCY = "asset_solvency"
    BEHAVIORAL_RISK = "behavioral_risk"
    CONSUMPTION_PREFERENCE = "consumption_preference"
    RELATION_NETWORK = "relation_network"
    PUBLIC_STATEMENTS = "public_statements"
    RISK_EVENTS = "risk_events"


class SignalSensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    CORROBORATED = "corroborated"
    PUBLIC_LEAD = "public_lead"
    INFERRED = "inferred"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class SubjectProfileSignal:
    """One visible, provenance-rich profile signal."""

    id: str
    dimension: SubjectProfileDimension
    subject_id: str
    subject_name: str
    subject_kind: str
    title: str
    value: str
    relation_type: str | None = None
    confidence: float = 0.5
    sensitivity: SignalSensitivity = SignalSensitivity.LOW
    verification_status: VerificationStatus = VerificationStatus.PUBLIC_LEAD
    evidence_ids: tuple[str, ...] = ()
    source_names: tuple[str, ...] = ()
    business_relevance: str = ""
    public_data_basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension.value,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "subject_kind": self.subject_kind,
            "title": self.title,
            "value": self.value,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity.value,
            "verification_status": self.verification_status.value,
            "evidence_ids": list(self.evidence_ids),
            "source_names": list(self.source_names),
            "business_relevance": self.business_relevance,
            "public_data_basis": self.public_data_basis,
        }


@dataclass(frozen=True)
class RecursionPolicy:
    """Controls associative expansion without letting graph growth run wild."""

    default_depth: int = 3
    max_subjects: int = 80
    max_signals_per_dimension: int = 120
    include_high_sensitivity_leads: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_depth": self.default_depth,
            "max_subjects": self.max_subjects,
            "max_signals_per_dimension": self.max_signals_per_dimension,
            "include_high_sensitivity_leads": self.include_high_sensitivity_leads,
        }


@dataclass(frozen=True)
class SubjectProfile:
    """Machine-readable profile for one company plus discovered related subjects."""

    seed_subject_id: str
    seed_subject_name: str
    recursion_policy: RecursionPolicy
    subjects: dict[str, dict[str, Any]]
    signals_by_dimension: dict[str, list[dict[str, Any]]]
    controller_candidates: list[dict[str, Any]]
    relationship_graph: dict[str, list[dict[str, Any]]]
    evidence_gaps: list[str]
    compliance_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_subject_id": self.seed_subject_id,
            "seed_subject_name": self.seed_subject_name,
            "recursion_policy": self.recursion_policy.to_dict(),
            "subjects": self.subjects,
            "signals_by_dimension": self.signals_by_dimension,
            "controller_candidates": self.controller_candidates,
            "relationship_graph": self.relationship_graph,
            "evidence_gaps": self.evidence_gaps,
            "compliance_notes": self.compliance_notes,
        }


def _extract_company_brand(name: str) -> str:
    s = re.sub(r"[（(][^()（）]+[）)]", "", str(name or "")).strip()
    m = re.match(r"^(.+?)(?:集团|控股|股份|有限|责任|合伙)*(?:公司|工厂|企业|中心|行|社|部|局|院|处)(?:有限|责任|合伙)?[公司]?$", s)
    return m.group(1).strip() if m else s[:10]


class SubjectProfileBuilder:
    """Builds subject profiles from graph entities, relations, and evidence."""

    DEFAULT_POLICY = RecursionPolicy()
    CONTROL_RELATION_KEYWORDS = (
        "control",
        "controller",
        "owner",
        "shareholder",
        "beneficial",
        "role",
        "executive",
        "chief",
        "representative",
        "legal_representative",
        "founder",
        "chair",
        "director",
        "board",
        "manager",
        "parent",
        "holding",
    )
    DIMENSION_ORDER = tuple(item.value for item in SubjectProfileDimension)
    RELATION_DIMENSIONS: tuple[tuple[SubjectProfileDimension, tuple[str, ...]], ...] = (
        (
            SubjectProfileDimension.CONTROL_OWNERSHIP,
            ("control", "controller", "owner", "shareholder", "beneficial", "role", "representative"),
        ),
        (SubjectProfileDimension.CONTACT_ACCOUNTS, ("contact", "account", "web_footprint")),
        (SubjectProfileDimension.LOCATION_ACTIVITY, ("address", "location", "activity")),
        (SubjectProfileDimension.ASSET_SOLVENCY, ("asset", "property", "vehicle", "collateral")),
        (SubjectProfileDimension.BEHAVIORAL_RISK, ("case", "penalty", "violation", "risk")),
        (SubjectProfileDimension.RELATION_NETWORK, ("mentioned", "related", "project")),
    )
    TEXT_DIMENSIONS: tuple[tuple[SubjectProfileDimension, tuple[str, ...]], ...] = (
        (
            SubjectProfileDimension.ASSET_SOLVENCY,
            (
                "property",
                "real estate",
                "vehicle",
                "collateral",
                "auction",
                "mortgage",
                "asset",
                "solvency",
                "不动产",
                "车辆",
                "资产",
                "偿付",
                "抵押",
                "拍卖",
            ),
        ),
        (
            SubjectProfileDimension.BEHAVIORAL_RISK,
            (
                "penalty",
                "violation",
                "traffic",
                "administrative",
                "enforcement",
                "dishonest",
                "处罚",
                "违章",
                "违法",
                "执行",
                "失信",
            ),
        ),
        (
            SubjectProfileDimension.LOCATION_ACTIVITY,
            (
                "address",
                "location",
                "delivery",
                "shipping",
                "travel",
                "activity",
                "地址",
                "收货",
                "快递",
                "公开活动范围",
                "活动",
            ),
        ),
        (
            SubjectProfileDimension.CONSUMPTION_PREFERENCE,
            (
                "consumption",
                "purchase",
                "review",
                "preference",
                "hotel",
                "restaurant",
                "消费",
                "购买",
                "评价",
                "偏好",
                "公开场景评价",
            ),
        ),
        (
            SubjectProfileDimension.PUBLIC_STATEMENTS,
            (
                "post",
                "statement",
                "social",
                "weibo",
                "linkedin",
                "github",
                "言论",
                "发文",
                "微博",
                "公众号",
                "社交",
            ),
        ),
    )

    def __init__(self, policy: RecursionPolicy | None = None):
        self.policy = policy or self.DEFAULT_POLICY

    def build(self, graph: EvidenceGraph, *, seed_subject_id: str) -> SubjectProfile:
        if seed_subject_id not in graph.entities:
            raise ValueError(f"seed subject not found in graph: {seed_subject_id}")

        reachable = self._reachable_subjects(graph, seed_subject_id)
        subjects = {
            entity_id: self._subject_payload(entity_id, graph.entities[entity_id], graph)
            for entity_id in reachable
            if entity_id in graph.entities
        }
        signals = self._signals(graph, reachable)
        signals_by_dimension = self._group_signals(signals)
        controller_candidates = self._controller_candidates(graph, reachable)
        seed = graph.entities[seed_subject_id]

        return SubjectProfile(
            seed_subject_id=seed_subject_id,
            seed_subject_name=seed.name,
            recursion_policy=self.policy,
            subjects=subjects,
            signals_by_dimension=signals_by_dimension,
            controller_candidates=controller_candidates,
            relationship_graph=self._relationship_graph(graph, reachable),
            evidence_gaps=self._evidence_gaps(signals_by_dimension, graph, controller_candidates),
            compliance_notes=[
                "Only public, licensed, or user-authorized evidence should feed this profile.",
                "High-sensitivity leads are visible by default but remain leads unless corroborated.",
                "Reasonable inferences are marked as inferred and must not be presented as verified facts.",
                "Recursive expansion defaults to three layers and is capped by subject and signal limits.",
            ],
        )

    def _reachable_subjects(self, graph: EvidenceGraph, seed_subject_id: str) -> list[str]:
        adjacency: dict[str, set[str]] = {}
        for relation in graph.relations:
            adjacency.setdefault(relation.from_id, set()).add(relation.to_id)
            adjacency.setdefault(relation.to_id, set()).add(relation.from_id)

        visited: dict[str, int] = {seed_subject_id: 0}
        queue: list[tuple[str, int]] = [(seed_subject_id, 0)]
        while queue and len(visited) < self.policy.max_subjects:
            entity_id, depth = queue.pop(0)
            if depth > self.policy.default_depth:
                continue
            for neighbor in sorted(adjacency.get(entity_id, set())):
                if neighbor in visited or neighbor not in graph.entities:
                    continue
                next_depth = depth + 1
                if next_depth > self.policy.default_depth:
                    continue
                visited[neighbor] = next_depth
                queue.append((neighbor, next_depth))
                if len(visited) >= self.policy.max_subjects:
                    break
        return list(visited.keys())

    def _subject_payload(
        self,
        entity_id: str,
        entity: InvestigationEntity,
        graph: EvidenceGraph,
    ) -> dict[str, Any]:
        sources = self._sources_for_evidence(graph, tuple(entity.evidence_ids))
        return {
            "id": entity_id,
            "kind": entity.kind.value,
            "name": entity.name,
            "confidence": entity.confidence,
            "evidence_ids": list(entity.evidence_ids),
            "source_names": list(sources),
            "attributes": entity.attributes,
        }

    def _signals(self, graph: EvidenceGraph, reachable: list[str]) -> list[SubjectProfileSignal]:
        reachable_set = set(reachable)
        signals: list[SubjectProfileSignal] = []
        for entity_id in reachable:
            entity = graph.entities.get(entity_id)
            if entity is None:
                continue
            if not self._entity_can_feed_profile(entity, graph):
                continue
            signals.extend(self._entity_signals(entity_id, entity, graph))

        for relation in graph.relations:
            if relation.from_id not in reachable_set or relation.to_id not in reachable_set:
                continue
            if not self._evidence_ids_can_feed_profile(graph, relation.evidence_ids):
                continue
            signal = self._relation_signal(relation, graph)
            if signal:
                signals.append(signal)

        for evidence_id, evidence in graph.evidence.items():
            if not self._evidence_can_feed_profile(evidence):
                continue
            attached = [
                entity_id
                for entity_id in reachable
                if evidence_id in graph.entities[entity_id].evidence_ids
            ]
            if not attached:
                continue
            subject_id = attached[0]
            subject = graph.entities[subject_id]
            signals.extend(self._evidence_signals(subject_id, subject, evidence))

        for event in graph.risk_events:
            subject_ids = [entity_id for entity_id in event.entity_ids if entity_id in reachable_set]
            for subject_id in subject_ids:
                subject = graph.entities[subject_id]
                evidence_ids = tuple(event.evidence_ids)
                signals.append(
                    SubjectProfileSignal(
                        id=self._stable_signal_id("risk", subject_id, event.id),
                        dimension=SubjectProfileDimension.RISK_EVENTS,
                        subject_id=subject_id,
                        subject_name=subject.name,
                        subject_kind=subject.kind.value,
                        title=event.title,
                        value=event.rationale or event.title,
                        relation_type="has_risk_event",
                        confidence=event.confidence,
                        sensitivity=SignalSensitivity.HIGH if event.severity.value in {"high", "critical"} else SignalSensitivity.MEDIUM,
                        verification_status=self._verification_status(graph, evidence_ids),
                        evidence_ids=evidence_ids,
                        source_names=self._sources_for_evidence(graph, evidence_ids),
                        business_relevance="Direct risk event for credit, compliance, or operating-risk judgment.",
                        public_data_basis="Derived from retained public or authorized evidence in the risk graph.",
                    )
                )

        return self._dedupe_signals(signals)

    def _entity_signals(
        self,
        entity_id: str,
        entity: InvestigationEntity,
        graph: EvidenceGraph,
    ) -> list[SubjectProfileSignal]:
        dimension = {
            EntityKind.COMPANY: SubjectProfileDimension.IDENTITY,
            EntityKind.PERSON: SubjectProfileDimension.IDENTITY,
            EntityKind.PHONE: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.EMAIL: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.DOMAIN: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.ACCOUNT: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.ADDRESS: SubjectProfileDimension.LOCATION_ACTIVITY,
            EntityKind.ASSET: SubjectProfileDimension.ASSET_SOLVENCY,
            EntityKind.CASE: SubjectProfileDimension.BEHAVIORAL_RISK,
            EntityKind.PROJECT: SubjectProfileDimension.RELATION_NETWORK,
        }.get(entity.kind, SubjectProfileDimension.RELATION_NETWORK)
        evidence_ids = tuple(entity.evidence_ids)
        return [
            SubjectProfileSignal(
                id=self._stable_signal_id("entity", entity_id, dimension.value),
                dimension=dimension,
                subject_id=entity_id,
                subject_name=entity.name,
                subject_kind=entity.kind.value,
                title=f"{entity.kind.value} public identity lead",
                value=entity.name,
                confidence=entity.confidence,
                sensitivity=self._entity_sensitivity(entity.kind),
                verification_status=self._verification_status(graph, evidence_ids),
                evidence_ids=evidence_ids,
                source_names=self._sources_for_evidence(graph, evidence_ids),
                business_relevance=self._entity_relevance(entity.kind),
                public_data_basis="Extracted from public or authorized evidence fields.",
            )
        ] + self._entity_attribute_signals(entity_id, entity, graph)

    def _entity_attribute_signals(
        self,
        entity_id: str,
        entity: InvestigationEntity,
        graph: EvidenceGraph,
    ) -> list[SubjectProfileSignal]:
        if entity.kind is not EntityKind.COMPANY:
            return []
        evidence_ids = tuple(entity.evidence_ids)
        brand = _extract_company_brand(entity.name)
        fields = (
            ("company_brand", "Company brand", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("legal_name", "Legal name", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("unified_social_credit_code", "Unified social credit code", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("registry_status", "Registry status", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("company_type", "Company type", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("registered_capital", "Registered capital", SubjectProfileDimension.ASSET_SOLVENCY, SignalSensitivity.LOW),
            ("establishment_date", "Establishment date", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("operating_period", "Operating period", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("registration_authority", "Registration authority", SubjectProfileDimension.IDENTITY, SignalSensitivity.LOW),
            ("business_scope", "Business scope", SubjectProfileDimension.LOCATION_ACTIVITY, SignalSensitivity.MEDIUM),
        )
        signals: list[SubjectProfileSignal] = []
        for field, title, dimension, sensitivity in fields:
            value = brand if field == "company_brand" else entity.attributes.get(field)
            if value in (None, ""):
                continue
            signals.append(
                SubjectProfileSignal(
                    id=self._stable_signal_id("entity-attribute", entity_id, field),
                    dimension=dimension,
                    subject_id=entity_id,
                    subject_name=entity.name,
                    subject_kind=entity.kind.value,
                    title=title,
                    value=str(value),
                    relation_type=field,
                    confidence=entity.confidence,
                    sensitivity=sensitivity,
                    verification_status=self._verification_status(graph, evidence_ids),
                    evidence_ids=evidence_ids,
                    source_names=self._sources_for_evidence(graph, evidence_ids),
                    business_relevance=self._attribute_relevance(field),
                    public_data_basis="Structured registry field from public, licensed, or user-authorized evidence.",
                )
            )
        return signals

    def _relation_signal(
        self,
        relation: InvestigationRelation,
        graph: EvidenceGraph,
    ) -> SubjectProfileSignal | None:
        target = graph.entities.get(relation.to_id)
        source = graph.entities.get(relation.from_id)
        if target is None or source is None:
            return None
        dimension = self._dimension_from_relation(relation.relation_type, target.kind)
        return SubjectProfileSignal(
            id=self._stable_signal_id("relation", relation.from_id, relation.to_id, relation.relation_type),
            dimension=dimension,
            subject_id=relation.from_id,
            subject_name=source.name,
            subject_kind=source.kind.value,
            title=f"{source.name} -> {target.name}",
            value=target.name,
            relation_type=relation.relation_type,
            confidence=relation.confidence,
            sensitivity=self._relation_sensitivity(dimension, target.kind),
            verification_status=self._verification_status(graph, relation.evidence_ids),
            evidence_ids=relation.evidence_ids,
            source_names=self._sources_for_evidence(graph, relation.evidence_ids),
            business_relevance=self._dimension_relevance(dimension),
            public_data_basis="Relationship extracted from public or authorized evidence; inference status reflects source strength.",
        )

    def _evidence_signals(
        self,
        subject_id: str,
        subject: InvestigationEntity,
        evidence: EvidenceItem,
    ) -> list[SubjectProfileSignal]:
        text = " ".join((evidence.title, *evidence.claims)).lower()
        dimensions = [
            dimension
            for dimension, keywords in self.TEXT_DIMENSIONS
            if any(keyword.lower() in text for keyword in keywords)
        ]
        if evidence.evidence_type.value == "social_post":
            dimensions.append(SubjectProfileDimension.PUBLIC_STATEMENTS)
        if not dimensions:
            return []
        signals: list[SubjectProfileSignal] = []
        for dimension in dict.fromkeys(dimensions):
            signals.append(
                SubjectProfileSignal(
                    id=self._stable_signal_id("evidence", subject_id, evidence.id, dimension.value),
                    dimension=dimension,
                    subject_id=subject_id,
                    subject_name=subject.name,
                    subject_kind=subject.kind.value,
                    title=evidence.title,
                    value="; ".join(evidence.claims[:3]) or evidence.title,
                    confidence=evidence.confidence,
                    sensitivity=self._dimension_sensitivity(dimension),
                    verification_status=self._verification_status_from_evidence(evidence),
                    evidence_ids=(evidence.id,),
                    source_names=(evidence.source,),
                    business_relevance=self._dimension_relevance(dimension),
                    public_data_basis="Keyword-classified public lead from retained evidence claims.",
                )
            )
        return signals

    @staticmethod
    def _evidence_can_feed_profile(evidence: EvidenceItem) -> bool:
        match = evidence.entity_match if isinstance(evidence.entity_match, dict) else {}
        if str(match.get("record_source_type") or "").strip().lower() in {"query_plan", "rich_query_plan"}:
            return False
        if str(match.get("level") or "") in {"review", "weak"}:
            return False
        return True

    def _entity_can_feed_profile(self, entity: InvestigationEntity, graph: EvidenceGraph) -> bool:
        return self._evidence_ids_can_feed_profile(graph, tuple(entity.evidence_ids))

    def _evidence_ids_can_feed_profile(
        self,
        graph: EvidenceGraph,
        evidence_ids: tuple[str, ...],
    ) -> bool:
        evidence = [graph.evidence[evidence_id] for evidence_id in evidence_ids if evidence_id in graph.evidence]
        if not evidence:
            return True
        return any(self._evidence_can_feed_profile(item) for item in evidence)

    def _group_signals(self, signals: list[SubjectProfileSignal]) -> dict[str, list[dict[str, Any]]]:
        grouped = {dimension: [] for dimension in self.DIMENSION_ORDER}
        for signal in sorted(signals, key=lambda item: (-item.confidence, item.dimension.value, item.title)):
            if signal.sensitivity is SignalSensitivity.HIGH and not self.policy.include_high_sensitivity_leads:
                continue
            bucket = grouped[signal.dimension.value]
            if len(bucket) >= self.policy.max_signals_per_dimension:
                continue
            bucket.append(signal.to_dict())
        return grouped

    def _controller_candidates(
        self,
        graph: EvidenceGraph,
        reachable: list[str],
    ) -> list[dict[str, Any]]:
        reachable_set = set(reachable)
        seed_subject_id = reachable[0] if reachable else ""
        candidates_by_key: dict[str, dict[str, Any]] = {}
        for relation in graph.relations:
            if relation.to_id not in reachable_set:
                continue
            if not self._evidence_ids_can_feed_profile(graph, relation.evidence_ids):
                continue
            target = graph.entities.get(relation.to_id)
            if target is None or target.kind is not EntityKind.PERSON:
                continue
            rel = relation.relation_type.lower()
            if not self._is_controller_relation(rel):
                continue
            key = self._controller_candidate_key(target)
            evidence_ids = list(relation.evidence_ids)
            source_names = list(self._sources_for_evidence(graph, relation.evidence_ids))
            verification_status = self._verification_status(graph, relation.evidence_ids).value
            confidence_tier = self._controller_confidence_tier(graph, relation, target)
            confidence_basis = self._controller_confidence_basis(graph, relation, target)
            control_paths = self._controller_control_paths(graph, seed_subject_id, relation, target)
            control_path_summaries = self._controller_control_path_summaries(
                graph,
                seed_subject_id,
                relation,
                target,
            )
            source_names = sorted(
                set(source_names)
                | {
                    str(source_name)
                    for summary in control_path_summaries
                    for source_name in summary.get("source_names", [])
                    if str(source_name).strip()
                }
            )
            source_family_summary = self._source_family_summary_from_names(source_names)
            source_strength = self._controller_source_strength(graph, relation.evidence_ids)
            match_score = self._controller_match_score(graph, relation.evidence_ids)
            existing = candidates_by_key.get(key)
            if existing is None:
                candidates_by_key[key] = {
                    "person_id": relation.to_id,
                    "name": target.name,
                    "relation_type": relation.relation_type,
                    "relation_types": [relation.relation_type],
                    "confidence": relation.confidence,
                    "confidence_tier": confidence_tier,
                    "confidence_basis": confidence_basis,
                    "control_paths": control_paths,
                    "control_path_summaries": control_path_summaries,
                    "source_strength": source_strength,
                    "match_score": match_score,
                    "evidence_ids": evidence_ids,
                    "source_names": source_names,
                    "source_families": [item["family"] for item in source_family_summary["families"]],
                    "source_family_summary": source_family_summary,
                    "verification_status": verification_status,
                }
                continue
            existing["confidence"] = max(float(existing["confidence"]), float(relation.confidence))
            existing["confidence_tier"] = self._strongest_controller_tier(
                str(existing.get("confidence_tier") or ""),
                confidence_tier,
            )
            existing["confidence_basis"] = sorted(
                set(existing.get("confidence_basis") or []) | set(confidence_basis)
            )
            existing["control_paths"] = sorted(
                set(existing.get("control_paths") or []) | set(control_paths)
            )
            existing["control_path_summaries"] = self._merge_control_path_summaries(
                list(existing.get("control_path_summaries") or []),
                control_path_summaries,
            )
            existing["source_strength"] = max(int(existing.get("source_strength") or 0), source_strength)
            existing["match_score"] = max(
                float(existing.get("match_score") or 0),
                float(match_score or 0),
            )
            existing["evidence_ids"] = sorted(set(existing["evidence_ids"]) | set(evidence_ids))
            existing["source_names"] = sorted(set(existing["source_names"]) | set(source_names))
            merged_family_summary = self._source_family_summary_from_names(list(existing["source_names"]))
            existing["source_families"] = [item["family"] for item in merged_family_summary["families"]]
            existing["source_family_summary"] = merged_family_summary
            relation_types = list(existing.get("relation_types") or [existing["relation_type"]])
            if relation.relation_type not in relation_types:
                relation_types.append(relation.relation_type)
            existing["relation_types"] = sorted(
                relation_types,
                key=lambda item: (self._controller_relation_rank(str(item)), str(item)),
            )
            existing["relation_type"] = existing["relation_types"][0]
            existing["verification_status"] = self._strongest_verification_status(
                str(existing.get("verification_status") or ""),
                verification_status,
            )
        return sorted(
            candidates_by_key.values(),
            key=lambda item: (
                self._controller_tier_rank(str(item.get("confidence_tier") or "")),
                -int(item.get("source_strength") or 0),
                self._controller_relation_rank(str(item["relation_type"])),
                -float(item["confidence"]),
                -float(item.get("match_score") or 0),
                -len(item["source_names"]),
                str(item["name"]),
            ),
        )

    @staticmethod
    def _controller_candidate_key(entity: InvestigationEntity) -> str:
        return entity.name.strip().casefold() or entity.id

    @classmethod
    def _is_controller_relation(cls, relation_type: str) -> bool:
        rel = relation_type.lower()
        return any(keyword in rel for keyword in cls.CONTROL_RELATION_KEYWORDS)

    @staticmethod
    def _controller_relation_rank(relation_type: str) -> int:
        rel = relation_type.lower()
        if any(keyword in rel for keyword in ("controller", "control", "beneficial", "owner", "shareholder")):
            return 0
        if any(keyword in rel for keyword in ("chief", "executive", "chair", "director", "board", "manager", "representative")):
            return 1
        if "founder" in rel:
            return 2
        return 3

    def _controller_confidence_tier(
        self,
        graph: EvidenceGraph,
        relation: InvestigationRelation,
        target: InvestigationEntity,
    ) -> str:
        evidence = [
            graph.evidence[evidence_id]
            for evidence_id in relation.evidence_ids
            if evidence_id in graph.evidence
        ]
        if not evidence:
            return "inferred_relation"
        if len({item.source for item in evidence}) >= 2:
            return "corroborated_fact"
        best_strength = self._controller_source_strength(graph, relation.evidence_ids)
        match_score = self._controller_match_score(graph, relation.evidence_ids)
        relation_rank = self._controller_relation_rank(relation.relation_type)
        confidence = max(relation.confidence, target.confidence)
        if best_strength >= 4 and confidence >= 0.7 and (match_score == 0 or match_score >= 0.8):
            return "verified_fact"
        if best_strength >= 3 and confidence >= 0.65 and relation_rank <= 1:
            return "strong_public_lead"
        if confidence >= 0.55:
            return "weak_public_lead"
        return "review_lead"

    def _controller_confidence_basis(
        self,
        graph: EvidenceGraph,
        relation: InvestigationRelation,
        target: InvestigationEntity,
    ) -> list[str]:
        basis: list[str] = [f"relation_type:{relation.relation_type}"]
        if target.attributes.get("confidence_basis"):
            basis.append(str(target.attributes["confidence_basis"]))
        if target.attributes.get("ownership_ratio"):
            basis.append(f"ownership_ratio:{target.attributes['ownership_ratio']}")
        if target.attributes.get("layer_depth"):
            basis.append(f"layer_depth:{target.attributes['layer_depth']}")
        for evidence_id in relation.evidence_ids:
            evidence = graph.evidence.get(evidence_id)
            if evidence is None:
                continue
            profile = evidence.source_profile
            if profile:
                basis.append(f"{profile.authority.value}:{profile.access.value}")
            match = evidence.entity_match if isinstance(evidence.entity_match, dict) else {}
            level = str(match.get("level") or "").strip()
            score = match.get("score")
            if level:
                basis.append(f"entity_match:{level}")
            if score not in (None, ""):
                basis.append(f"match_score:{score}")
        return sorted(set(item for item in basis if item))

    @staticmethod
    def _controller_control_paths(
        graph: EvidenceGraph,
        seed_subject_id: str,
        relation: InvestigationRelation,
        target: InvestigationEntity,
    ) -> list[str]:
        paths: list[str] = []
        for key in ("control_path", "path_nodes"):
            value = target.attributes.get(key)
            if value not in (None, ""):
                paths.append(SubjectProfileBuilder._control_path_text(value))
        if not paths:
            graph_path = SubjectProfileBuilder._entity_path_text(
                graph,
                seed_subject_id,
                relation.to_id,
            )
            paths.append(graph_path or f"{relation.from_id} -> {target.name}")
        return sorted(set(paths))

    def _controller_control_path_summaries(
        self,
        graph: EvidenceGraph,
        seed_subject_id: str,
        relation: InvestigationRelation,
        target: InvestigationEntity,
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        explicit_path = None
        for key in ("control_path", "path_nodes"):
            value = target.attributes.get(key)
            if value not in (None, ""):
                explicit_path = self._control_path_text(value)
                if explicit_path:
                    source_names = list(self._sources_for_evidence(graph, relation.evidence_ids))
                    source_family_summary = self._source_family_summary_from_names(source_names)
                    summaries.append(
                        {
                            "path_text": explicit_path,
                            "path_nodes": [
                                item.strip()
                                for item in explicit_path.split(" -> ")
                                if item.strip()
                            ],
                            "hop_count": max(len(explicit_path.split(" -> ")) - 1, 1),
                            "relation_types": [relation.relation_type],
                            "terminal_name": target.name,
                            "terminal_kind": target.kind.value,
                            "min_confidence": round(min(relation.confidence, target.confidence), 4),
                            "confidence": round(max(relation.confidence, target.confidence), 4),
                            "source_strength": self._controller_source_strength(graph, relation.evidence_ids),
                            "source_names": source_names,
                            "source_families": [item["family"] for item in source_family_summary["families"]],
                            "source_family_summary": source_family_summary,
                            "evidence_ids": list(relation.evidence_ids),
                            "admission": self._relation_admission(graph, relation),
                            "verification_status": self._verification_status(graph, relation.evidence_ids).value,
                            "basis": "explicit_source_control_path",
                        }
                    )
                    break

        directed_relations = self._shortest_relation_path(
            graph,
            seed_subject_id,
            relation.to_id,
            directed=True,
        )
        relation_path = directed_relations or self._shortest_relation_path(
            graph,
            seed_subject_id,
            relation.to_id,
            directed=False,
        )
        if relation_path:
            summaries.append(
                self._relation_path_summary(
                    graph,
                    seed_subject_id,
                    relation.to_id,
                    relation_path,
                    directed=bool(directed_relations),
                )
            )
        if not summaries and explicit_path:
            return summaries
        if not summaries:
            source_names = list(self._sources_for_evidence(graph, relation.evidence_ids))
            source_family_summary = self._source_family_summary_from_names(source_names)
            summaries.append(
                {
                    "path_text": f"{relation.from_id} -> {target.name}",
                    "path_nodes": [relation.from_id, target.name],
                    "hop_count": 1,
                    "relation_types": [relation.relation_type],
                    "terminal_name": target.name,
                    "terminal_kind": target.kind.value,
                    "min_confidence": round(min(relation.confidence, target.confidence), 4),
                    "confidence": round(max(relation.confidence, target.confidence), 4),
                    "source_strength": self._controller_source_strength(graph, relation.evidence_ids),
                    "source_names": source_names,
                    "source_families": [item["family"] for item in source_family_summary["families"]],
                    "source_family_summary": source_family_summary,
                    "evidence_ids": list(relation.evidence_ids),
                    "admission": self._relation_admission(graph, relation),
                    "verification_status": self._verification_status(graph, relation.evidence_ids).value,
                    "basis": "direct_relation_fallback",
                }
            )
        return self._merge_control_path_summaries([], summaries)

    def _relation_path_summary(
        self,
        graph: EvidenceGraph,
        start_id: str,
        target_id: str,
        relation_path: list[InvestigationRelation],
        *,
        directed: bool,
    ) -> dict[str, Any]:
        node_ids = self._node_ids_from_relation_path(start_id, target_id, relation_path)
        path_nodes = [
            graph.entities[entity_id].name
            for entity_id in node_ids
            if entity_id in graph.entities and str(graph.entities[entity_id].name).strip()
        ]
        evidence_ids = sorted(
            {
                evidence_id
                for relation in relation_path
                for evidence_id in relation.evidence_ids
                if str(evidence_id).strip()
            }
        )
        source_names = list(self._sources_for_evidence(graph, tuple(evidence_ids)))
        source_family_summary = self._source_family_summary_from_names(source_names)
        relation_types = [relation.relation_type for relation in relation_path]
        admissions = [self._relation_admission(graph, relation) for relation in relation_path]
        min_confidence = min([relation.confidence for relation in relation_path] or [0.0])
        terminal = graph.entities.get(target_id)
        return {
            "path_text": " -> ".join(path_nodes),
            "path_nodes": path_nodes,
            "hop_count": max(len(path_nodes) - 1, 0),
            "relation_types": relation_types,
            "terminal_name": terminal.name if terminal else target_id,
            "terminal_kind": terminal.kind.value if terminal else "unknown",
            "min_confidence": round(min_confidence, 4),
            "confidence": round(max([relation.confidence for relation in relation_path] or [0.0]), 4),
            "source_strength": max(
                [self._controller_source_strength(graph, relation.evidence_ids) for relation in relation_path]
                or [0]
            ),
            "source_names": source_names,
            "source_families": [item["family"] for item in source_family_summary["families"]],
            "source_family_summary": source_family_summary,
            "evidence_ids": evidence_ids,
            "admission": "fact" if admissions and all(item == "fact" for item in admissions) else "lead",
            "verification_status": self._verification_status(graph, tuple(evidence_ids)).value,
            "basis": "directed_control_graph_path" if directed else "undirected_control_graph_path",
        }

    @staticmethod
    def _node_ids_from_relation_path(
        start_id: str,
        target_id: str,
        relation_path: list[InvestigationRelation],
    ) -> list[str]:
        if not relation_path:
            return []
        node_ids = [start_id]
        current = start_id
        for relation in relation_path:
            if relation.from_id == current:
                current = relation.to_id
            elif relation.to_id == current:
                current = relation.from_id
            elif relation.to_id == target_id:
                current = relation.to_id
            else:
                current = relation.from_id
            node_ids.append(current)
        return node_ids

    def _shortest_relation_path(
        self,
        graph: EvidenceGraph,
        start_id: str,
        target_id: str,
        *,
        directed: bool,
    ) -> list[InvestigationRelation]:
        if not start_id or not target_id or start_id not in graph.entities or target_id not in graph.entities:
            return []
        adjacency: dict[str, list[tuple[str, InvestigationRelation]]] = {}
        for relation in graph.relations:
            if not self._is_controller_relation(relation.relation_type):
                continue
            if not self._evidence_ids_can_feed_profile(graph, relation.evidence_ids):
                continue
            adjacency.setdefault(relation.from_id, []).append((relation.to_id, relation))
            if not directed:
                adjacency.setdefault(relation.to_id, []).append((relation.from_id, relation))
        queue: list[tuple[str, list[InvestigationRelation]]] = [(start_id, [])]
        visited = {start_id}
        max_hops = max(self.policy.default_depth + 2, 4)
        while queue:
            current, path = queue.pop(0)
            if current == target_id:
                return path
            if len(path) >= max_hops:
                continue
            for neighbor, relation in sorted(
                adjacency.get(current, []),
                key=lambda item: (
                    self._controller_relation_rank(item[1].relation_type),
                    -item[1].confidence,
                    item[0],
                ),
            ):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, [*path, relation]))
        return []

    @staticmethod
    def _merge_control_path_summaries(
        current: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in [*current, *incoming]:
            if not isinstance(item, dict):
                continue
            path_text = " ".join(str(item.get("path_text") or "").split())
            if not path_text:
                continue
            key = path_text.casefold()
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(item, path_text=path_text)
                continue
            existing["source_names"] = sorted(
                set(existing.get("source_names") or []) | set(item.get("source_names") or [])
            )
            merged_family_summary = SubjectProfileBuilder._source_family_summary_from_names(
                list(existing.get("source_names") or [])
            )
            existing["source_families"] = [entry["family"] for entry in merged_family_summary["families"]]
            existing["source_family_summary"] = merged_family_summary
            existing["evidence_ids"] = sorted(
                set(existing.get("evidence_ids") or []) | set(item.get("evidence_ids") or [])
            )
            existing["relation_types"] = sorted(
                set(existing.get("relation_types") or []) | set(item.get("relation_types") or [])
            )
            existing["source_strength"] = max(
                int(existing.get("source_strength") or 0),
                int(item.get("source_strength") or 0),
            )
            try:
                existing["min_confidence"] = round(
                    max(float(existing.get("min_confidence") or 0), float(item.get("min_confidence") or 0)),
                    4,
                )
                existing["confidence"] = round(
                    max(float(existing.get("confidence") or 0), float(item.get("confidence") or 0)),
                    4,
                )
            except (TypeError, ValueError):
                pass
            if str(item.get("admission") or "").lower() == "fact":
                existing["admission"] = item.get("admission")
        return sorted(
            merged.values(),
            key=lambda item: (
                -int(item.get("source_strength") or 0),
                -float(item.get("min_confidence") or 0),
                int(item.get("hop_count") or 0),
                str(item.get("path_text") or ""),
            ),
        )

    @staticmethod
    def _entity_path_text(
        graph: EvidenceGraph,
        start_id: str,
        target_id: str,
    ) -> str:
        if not start_id or not target_id or start_id not in graph.entities or target_id not in graph.entities:
            return ""
        directed = SubjectProfileBuilder._shortest_entity_path(graph, start_id, target_id, directed=True)
        path = directed or SubjectProfileBuilder._shortest_entity_path(graph, start_id, target_id, directed=False)
        if not path:
            return ""
        names = [
            graph.entities[entity_id].name
            for entity_id in path
            if entity_id in graph.entities and str(graph.entities[entity_id].name).strip()
        ]
        return " -> ".join(names)

    @staticmethod
    def _shortest_entity_path(
        graph: EvidenceGraph,
        start_id: str,
        target_id: str,
        *,
        directed: bool,
    ) -> list[str]:
        adjacency: dict[str, set[str]] = {}
        for relation in graph.relations:
            adjacency.setdefault(relation.from_id, set()).add(relation.to_id)
            if not directed:
                adjacency.setdefault(relation.to_id, set()).add(relation.from_id)
        queue: list[list[str]] = [[start_id]]
        visited = {start_id}
        while queue:
            path = queue.pop(0)
            current = path[-1]
            if current == target_id:
                return path
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append([*path, neighbor])
        return []

    @staticmethod
    def _control_path_text(raw: Any) -> str:
        if isinstance(raw, (list, tuple)):
            nodes: list[str] = []
            for item in raw:
                if isinstance(item, dict):
                    value = item.get("name") or item.get("entity") or item.get("value") or item.get("title")
                else:
                    value = item
                text = " ".join(str(value or "").split())
                if text:
                    nodes.append(text)
            if nodes:
                return " -> ".join(nodes)
        return " ".join(str(raw or "").split())

    def _controller_source_strength(
        self,
        graph: EvidenceGraph,
        evidence_ids: tuple[str, ...],
    ) -> int:
        strength = 0
        for evidence_id in evidence_ids:
            evidence = graph.evidence.get(evidence_id)
            if evidence is None or evidence.source_profile is None:
                continue
            profile = evidence.source_profile
            if profile.authority.value == "official" and profile.access in {SourceAccess.PUBLIC, SourceAccess.LICENSED, SourceAccess.USER_AUTHORIZED}:
                strength = max(strength, 5)
            elif profile.access in {SourceAccess.LICENSED, SourceAccess.USER_AUTHORIZED}:
                strength = max(strength, 4)
            elif profile.authority.value == "public_web":
                strength = max(strength, 2)
            else:
                strength = max(strength, 1)
        if len(self._sources_for_evidence(graph, evidence_ids)) >= 2:
            strength += 1
        return strength

    @staticmethod
    def _controller_match_score(
        graph: EvidenceGraph,
        evidence_ids: tuple[str, ...],
    ) -> float:
        scores: list[float] = []
        for evidence_id in evidence_ids:
            evidence = graph.evidence.get(evidence_id)
            match = evidence.entity_match if evidence and isinstance(evidence.entity_match, dict) else {}
            try:
                scores.append(float(match.get("score")))
            except (TypeError, ValueError):
                continue
        return round(max(scores), 4) if scores else 0.0

    @staticmethod
    def _controller_tier_rank(tier: str) -> int:
        order = {
            "verified_fact": 0,
            "corroborated_fact": 1,
            "strong_public_lead": 2,
            "weak_public_lead": 3,
            "review_lead": 4,
            "inferred_relation": 5,
        }
        return order.get(tier, 9)

    def _strongest_controller_tier(self, current: str, incoming: str) -> str:
        return min(
            (current or "inferred_relation", incoming or "inferred_relation"),
            key=self._controller_tier_rank,
        )

    @staticmethod
    def _strongest_verification_status(current: str, incoming: str) -> str:
        order = {
            "verified": 0,
            "corroborated": 1,
            "official": 2,
            "public_lead": 3,
            "unverified": 4,
            "unknown": 5,
        }
        return min((current or "unknown", incoming or "unknown"), key=lambda item: order.get(item, 9))

    def _relationship_graph(
        self,
        graph: EvidenceGraph,
        reachable: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        reachable_set = set(reachable)
        nodes = [
            self._subject_payload(entity_id, graph.entities[entity_id], graph)
            for entity_id in reachable
            if entity_id in graph.entities
        ]
        edges = []
        for relation in graph.relations:
            if relation.from_id not in reachable_set or relation.to_id not in reachable_set:
                continue
            evidence_ids = tuple(relation.evidence_ids)
            source_names = list(self._sources_for_evidence(graph, evidence_ids))
            source_family_summary = self._source_family_summary_from_names(source_names)
            edges.append(
                {
                    "from_id": relation.from_id,
                    "to_id": relation.to_id,
                    "relation_type": relation.relation_type,
                    "confidence": relation.confidence,
                    "evidence_ids": list(evidence_ids),
                    "source_names": source_names,
                    "source_families": [item["family"] for item in source_family_summary["families"]],
                    "source_family_summary": source_family_summary,
                    "source_strength": self._controller_source_strength(graph, evidence_ids),
                    "admission": self._relation_admission(graph, relation),
                }
            )
        return {"nodes": nodes, "edges": edges}

    def _relation_admission(
        self,
        graph: EvidenceGraph,
        relation: InvestigationRelation,
    ) -> str:
        if relation.confidence < 0.6:
            return "lead"
        evidence = [
            graph.evidence[evidence_id]
            for evidence_id in relation.evidence_ids
            if evidence_id in graph.evidence
        ]
        for item in evidence:
            profile = item.source_profile
            if profile is None:
                continue
            if not self._evidence_can_feed_profile(item):
                continue
            authority = str(profile.authority.value)
            access = str(profile.access.value)
            if authority == "official" or access in {"licensed", "user_authorized"}:
                return "fact"
        return "lead"

    def _evidence_gaps(
        self,
        grouped: dict[str, list[dict[str, Any]]],
        graph: EvidenceGraph,
        controller_candidates: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        labels = {
            SubjectProfileDimension.IDENTITY.value: "identity/base facts",
            SubjectProfileDimension.CONTROL_OWNERSHIP.value: "controller and beneficial-owner evidence",
            SubjectProfileDimension.ASSET_SOLVENCY.value: "public asset and solvency evidence",
            SubjectProfileDimension.BEHAVIORAL_RISK.value: "behavioral, administrative, and court-risk evidence",
            SubjectProfileDimension.RELATION_NETWORK.value: "relationship-network evidence",
        }
        has_relationship_graph = any(True for relation in graph.relations)
        return [
            f"Missing or weak {label}; expand public/authorized sources before making a final risk judgment."
            for dimension, label in labels.items()
            if not grouped.get(dimension)
            and not (
                dimension == SubjectProfileDimension.CONTROL_OWNERSHIP.value
                and controller_candidates
            )
            and not (dimension == SubjectProfileDimension.RELATION_NETWORK.value and has_relationship_graph)
        ]

    def _dimension_from_relation(
        self,
        relation_type: str,
        target_kind: EntityKind,
    ) -> SubjectProfileDimension:
        relation = relation_type.lower()
        for dimension, keywords in self.RELATION_DIMENSIONS:
            if any(keyword in relation for keyword in keywords):
                return dimension
        return {
            EntityKind.ADDRESS: SubjectProfileDimension.LOCATION_ACTIVITY,
            EntityKind.ASSET: SubjectProfileDimension.ASSET_SOLVENCY,
            EntityKind.CASE: SubjectProfileDimension.BEHAVIORAL_RISK,
            EntityKind.PHONE: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.EMAIL: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.DOMAIN: SubjectProfileDimension.CONTACT_ACCOUNTS,
            EntityKind.ACCOUNT: SubjectProfileDimension.CONTACT_ACCOUNTS,
        }.get(target_kind, SubjectProfileDimension.RELATION_NETWORK)

    def _verification_status(
        self,
        graph: EvidenceGraph,
        evidence_ids: tuple[str, ...],
    ) -> VerificationStatus:
        evidence = [graph.evidence[evidence_id] for evidence_id in evidence_ids if evidence_id in graph.evidence]
        if not evidence:
            return VerificationStatus.INFERRED
        if len({item.source for item in evidence}) >= 2:
            return VerificationStatus.CORROBORATED
        return self._verification_status_from_evidence(evidence[0])

    @staticmethod
    def _verification_status_from_evidence(evidence: EvidenceItem) -> VerificationStatus:
        profile = evidence.source_profile
        if profile and profile.access in {SourceAccess.PUBLIC, SourceAccess.LICENSED, SourceAccess.USER_AUTHORIZED}:
            if profile.authority.value == "official" and evidence.confidence >= 0.75:
                return VerificationStatus.VERIFIED
            if profile.access in {SourceAccess.LICENSED, SourceAccess.USER_AUTHORIZED} and evidence.confidence >= 0.7:
                return VerificationStatus.VERIFIED
            return VerificationStatus.PUBLIC_LEAD
        return VerificationStatus.NEEDS_REVIEW

    @staticmethod
    def _sources_for_evidence(
        graph: EvidenceGraph,
        evidence_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    graph.evidence[evidence_id].source
                    for evidence_id in evidence_ids
                    if evidence_id in graph.evidence
                }
            )
        )

    @staticmethod
    def _source_family(source_name: str) -> str:
        source = source_name.strip().lower()
        if not source:
            return "unknown"
        if "qyyjt" in source or "licensed" in source or "commercial" in source:
            return "licensed_commercial"
        if "gleif" in source:
            return "official_public_gleif"
        if "sec" in source or "edgar" in source:
            return "official_public_sec"
        if "wikidata" in source:
            return "public_knowledge_graph"
        if "registry" in source or "gsxt" in source or "official" in source:
            return "official_registry"
        if "web" in source or "search" in source:
            return "public_web"
        return "other_public_or_authorized"

    @staticmethod
    def _source_family_summary_from_names(source_names: list[str]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for source_name in source_names:
            family = SubjectProfileBuilder._source_family(str(source_name))
            if family == "unknown":
                continue
            counts[family] = counts.get(family, 0) + 1
        families = [
            {"family": family, "count": count}
            for family, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {
            "family_count": len(families),
            "top_family": families[0]["family"] if families else "",
            "families": families,
            "has_official_or_authorized": any(
                str(item["family"]).startswith("official_public_")
                or str(item["family"]) in {"official_registry", "licensed_commercial"}
                for item in families
            ),
            "policy": "Source families explain controller/UBO provenance breadth only; they do not upgrade weak leads into facts.",
        }

    @staticmethod
    def _entity_sensitivity(kind: EntityKind) -> SignalSensitivity:
        if kind in {EntityKind.ADDRESS, EntityKind.PHONE, EntityKind.EMAIL, EntityKind.ACCOUNT, EntityKind.ASSET}:
            return SignalSensitivity.HIGH
        if kind is EntityKind.PERSON:
            return SignalSensitivity.MEDIUM
        return SignalSensitivity.LOW

    @staticmethod
    def _dimension_sensitivity(dimension: SubjectProfileDimension) -> SignalSensitivity:
        if dimension in {
            SubjectProfileDimension.LOCATION_ACTIVITY,
            SubjectProfileDimension.ASSET_SOLVENCY,
            SubjectProfileDimension.BEHAVIORAL_RISK,
            SubjectProfileDimension.CONSUMPTION_PREFERENCE,
            SubjectProfileDimension.PUBLIC_STATEMENTS,
        }:
            return SignalSensitivity.HIGH
        if dimension in {SubjectProfileDimension.CONTROL_OWNERSHIP, SubjectProfileDimension.CONTACT_ACCOUNTS}:
            return SignalSensitivity.MEDIUM
        return SignalSensitivity.LOW

    def _relation_sensitivity(
        self,
        dimension: SubjectProfileDimension,
        target_kind: EntityKind,
    ) -> SignalSensitivity:
        if target_kind in {EntityKind.ADDRESS, EntityKind.ASSET, EntityKind.ACCOUNT}:
            return SignalSensitivity.HIGH
        return self._dimension_sensitivity(dimension)

    @staticmethod
    def _entity_relevance(kind: EntityKind) -> str:
        return {
            EntityKind.COMPANY: "Identifies the investigated business subject.",
            EntityKind.PERSON: "Supports controller, management, shareholder, or relationship risk review.",
            EntityKind.ADDRESS: "Supports operating footprint, shared-address, and location-risk review.",
            EntityKind.PHONE: "Supports public contact and identity-corroboration review.",
            EntityKind.EMAIL: "Supports public contact and account-correlation review.",
            EntityKind.DOMAIN: "Supports public web footprint and technical identity review.",
            EntityKind.ACCOUNT: "Supports public account and statement/activity review.",
            EntityKind.ASSET: "Supports solvency, collateral, and credit-capacity review.",
            EntityKind.CASE: "Supports litigation, enforcement, and behavioral-risk review.",
            EntityKind.PROJECT: "Supports customer, supplier, procurement, and operating activity review.",
        }.get(kind, "Supports relationship-network review.")

    @staticmethod
    def _attribute_relevance(field: str) -> str:
        return {
            "legal_name": "Locks the legal subject used for downstream matching and deduplication.",
            "unified_social_credit_code": "Provides a stable registry identifier for entity resolution.",
            "registry_status": "Shows whether the registered subject appears active, abnormal, cancelled, or otherwise constrained.",
            "company_type": "Helps interpret shareholder, liability, and operating-form context.",
            "registered_capital": "Supports capital-strength and solvency context, subject to paid-in verification.",
            "establishment_date": "Supports operating history and shell-company age checks.",
            "operating_period": "Supports continuity and expiration-risk checks.",
            "registration_authority": "Identifies the authority or registry source behind the company record.",
            "business_scope": "Anchors industry, product, and operating-activity interpretation.",
        }.get(field, "Structured registry attribute for subject-profile review.")

    @staticmethod
    def _dimension_relevance(dimension: SubjectProfileDimension) -> str:
        return {
            SubjectProfileDimension.IDENTITY: "Base identity for deduplication and legal-subject matching.",
            SubjectProfileDimension.CONTROL_OWNERSHIP: "Core due-diligence signal for controller, UBO, and related-party risk.",
            SubjectProfileDimension.CONTACT_ACCOUNTS: "Corroborates public footprint and reachable business channels.",
            SubjectProfileDimension.LOCATION_ACTIVITY: "Helps assess operating footprint, address reuse, and activity range.",
            SubjectProfileDimension.ASSET_SOLVENCY: "Helps assess asset strength, collateral, and repayment capacity.",
            SubjectProfileDimension.BEHAVIORAL_RISK: "Helps assess compliance habits, default behavior, and risk appetite.",
            SubjectProfileDimension.CONSUMPTION_PREFERENCE: "Public lead for business-relevant behavior and spending pattern review.",
            SubjectProfileDimension.RELATION_NETWORK: "Expands affiliates, counterparties, and multi-hop relationship risk.",
            SubjectProfileDimension.PUBLIC_STATEMENTS: "Captures public statements and account behavior relevant to reputation or operations.",
            SubjectProfileDimension.RISK_EVENTS: "Direct monitorable risk signal.",
        }[dimension]

    @staticmethod
    def _dedupe_signals(signals: list[SubjectProfileSignal]) -> list[SubjectProfileSignal]:
        deduped: dict[str, SubjectProfileSignal] = {}
        for signal in signals:
            key = "|".join(
                (
                    signal.dimension.value,
                    signal.subject_id,
                    signal.relation_type or "",
                    signal.value.lower(),
                )
            )
            current = deduped.get(key)
            if current is None:
                deduped[key] = signal
                continue
            evidence_ids = tuple(sorted(set(current.evidence_ids) | set(signal.evidence_ids)))
            source_names = tuple(sorted(set(current.source_names) | set(signal.source_names)))
            best = signal if signal.confidence > current.confidence else current
            deduped[key] = SubjectProfileSignal(
                id=best.id,
                dimension=best.dimension,
                subject_id=best.subject_id,
                subject_name=best.subject_name,
                subject_kind=best.subject_kind,
                title=best.title,
                value=best.value,
                relation_type=best.relation_type,
                confidence=max(current.confidence, signal.confidence),
                sensitivity=best.sensitivity,
                verification_status=best.verification_status,
                evidence_ids=evidence_ids,
                source_names=source_names,
                business_relevance=best.business_relevance,
                public_data_basis=best.public_data_basis,
            )
        return list(deduped.values())

    @staticmethod
    def _stable_signal_id(*parts: str) -> str:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
        return f"profile_signal:{digest}"
    def _explain_relationship_edges(self, graph, profile):
        edges = []
        for rel in graph.relations[:20]:
            edge = {
                "from": getattr(rel,"from_name","") or getattr(rel,"from_id",""),
                "to": getattr(rel,"to_name","") or getattr(rel,"to_id",""),
                "relation_type": getattr(rel,"relation_type","unknown"),
                "confidence": getattr(rel,"confidence",0.5),
                "source_name": getattr(rel,"source_name",""),
                "evidence_ids": list(getattr(rel,"evidence_ids",[]) or []),
                "basis": getattr(rel,"basis","") or getattr(rel,"description",""),
            }
            # Dedup weak same edges
            dedup_key = (edge["from"], edge["to"], edge["relation_type"])
            edges.append(edge)
        # Dedup: keep highest confidence per key
        deduped = {}
        for e in edges:
            k = (e["from"], e["to"], e["relation_type"])
            if k not in deduped or e["confidence"] > deduped[k]["confidence"]:
                deduped[k] = e
        profile["relationship_edges"] = sorted(deduped.values(), key=lambda x: x["confidence"], reverse=True)[:15]
        return profile


def _explain_relationship_edges(graph, profile):
    """Expose relationship edges with source, evidence refs, confidence, and dedup."""
    edges = []
    for rel in getattr(graph, "relations", [])[:20]:
        edge = {
            "from": getattr(rel, "from_name", "") or getattr(rel, "from_id", ""),
            "to": getattr(rel, "to_name", "") or getattr(rel, "to_id", ""),
            "relation_type": getattr(rel, "relation_type", "unknown"),
            "confidence": getattr(rel, "confidence", 0.5),
            "source_name": getattr(rel, "source_name", ""),
            "evidence_ids": list(getattr(rel, "evidence_ids", []) or []),
            "basis": getattr(rel, "basis", "") or getattr(rel, "description", ""),
        }
        edges.append(edge)
    # Dedup: keep highest confidence per (from, to, type) key
    deduped = {}
    for e in edges:
        k = (e["from"], e["to"], e["relation_type"])
        if k not in deduped or e["confidence"] > deduped[k]["confidence"]:
            deduped[k] = e
    profile["relationship_edges"] = sorted(deduped.values(), key=lambda x: x.get("confidence", 0), reverse=True)[:15]
    return profile

def _check_entity_conflict(existing, candidate):
    """Return conflict dict if entities have same name but different identifiers."""
    e_id = str(existing.get("registration_number") or existing.get("identifier") or "")
    c_id = str(candidate.get("registration_number") or candidate.get("identifier") or "")
    e_addr = str(existing.get("address") or "")
    c_addr = str(candidate.get("address") or "")
    name = str(candidate.get("name", ""))
    conflicts = []
    if e_id and c_id and e_id != c_id:
        conflicts.append(f"identifier_mismatch:{e_id[:20]}!={c_id[:20]}")
    if e_addr and c_addr and e_addr != c_addr:
        conflicts.append("address_mismatch")
    return {"conflicts": conflicts, "name": name} if conflicts else None
