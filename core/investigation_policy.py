#!/usr/bin/env python3
"""Runtime policy — loads configurable investigation behavior from config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RetrievalPolicy:
    result_limit: int = 3
    per_source_result_limit: int = 3


@dataclass
class LayerBudgets:
    entity_anchor: RetrievalPolicy = field(default_factory=lambda: RetrievalPolicy(3, 3))
    overview: RetrievalPolicy = field(default_factory=lambda: RetrievalPolicy(5, 5))
    prioritized_drilldown: RetrievalPolicy = field(default_factory=lambda: RetrievalPolicy(8, 8))
    specialist: RetrievalPolicy = field(default_factory=lambda: RetrievalPolicy(12, 12))


@dataclass
class RecursionPolicyConfig:
    default_depth: int = 3
    max_subjects: int = 80
    max_signals_per_dimension: int = 120


@dataclass
class EvidenceAdmissionPolicy:
    minimum_entity_match_level: str = "strong"
    exact_threshold: float = 0.95
    strong_threshold: float = 0.80
    review_threshold: float = 0.55
    evidence_boundary: str = "public_only"


@dataclass
class QualityGatePolicy:
    ready_for_review_score: int = 85
    usable_with_warnings_score: int = 65
    blocker_deduction: int = 30
    warning_deduction: int = 8
    evidence_substantial_min_count: int = 4
    evidence_substantial_min_dimensions: int = 4


@dataclass
class ExtractionPolicy:
    capital_signals_max: int = 10
    product_signals_max: int = 8
    industry_signals_max: int = 8
    supply_chain_signals_max: int = 12
    people_entities_max: int = 8
    people_pairs_max: int = 12
    list_values_max: int = 4
    business_model_signals_max: int = 8
    market_position_signals_max: int = 6


@dataclass
class InfrastructurePolicy:
    max_concurrency: int = 50
    max_sources: int = 100
    max_query_length: int = 2048
    cache_max_size: int = 1000
    cache_default_ttl: int = 300
    deep_graph_max_depth: int = 8
    deep_graph_max_nodes_per_layer: int = 10
    context_max_summary_chars: int = 700
    context_max_line_chars: int = 240
    context_max_evidence_lines: int = 8
    context_max_risk_lines: int = 8
    context_max_recent_lines: int = 4
    engine_concurrency_cap: int = 20
    engine_retries_cap: int = 5
    risk_event_store_alert_limit: int = 10


@dataclass
class RuntimePolicy:
    retrieval: LayerBudgets = field(default_factory=LayerBudgets)
    recursion: RecursionPolicyConfig = field(default_factory=RecursionPolicyConfig)
    evidence_admission: EvidenceAdmissionPolicy = field(default_factory=EvidenceAdmissionPolicy)
    quality_gate: QualityGatePolicy = field(default_factory=QualityGatePolicy)
    extraction: ExtractionPolicy = field(default_factory=ExtractionPolicy)
    infrastructure: InfrastructurePolicy = field(default_factory=InfrastructurePolicy)
    retrieval_concurrency: int = 4
    fanout_rounds: int = 1
    max_fanout_tasks: int = 24
    query_timeout_seconds: float = 20.0

    @classmethod
    def from_config(cls, config_path: str | Path | None = None) -> "RuntimePolicy":
        import re

        config: dict[str, Any] = {}
        if config_path:
            config = _load_simple_yaml(Path(config_path))
        else:
            default = _default_config_path()
            if default:
                config = _load_simple_yaml(default)

        p = config.get("investigation_policy", {})
        return cls(
            retrieval=_parse_layer_budgets(p.get("retrieval", {})),
            recursion=_parse_recursion(p.get("recursion", {})),
            evidence_admission=_parse_evidence(p.get("evidence_admission", {})),
            quality_gate=_parse_quality(p.get("quality_gate", {})),
            extraction=_parse_extraction(p.get("extraction", {})),
            infrastructure=_parse_infrastructure(p.get("infrastructure", {})),
            retrieval_concurrency=int(p.get("retrieval", {}).get("retrieval_concurrency", 4)),
            fanout_rounds=int(p.get("retrieval", {}).get("fanout_rounds", 1)),
            max_fanout_tasks=int(p.get("retrieval", {}).get("max_fanout_tasks", 24)),
            query_timeout_seconds=float(p.get("retrieval", {}).get("query_timeout_seconds", 20.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval": {
                "entity_anchor": {"result_limit": self.retrieval.entity_anchor.result_limit, "per_source_result_limit": self.retrieval.entity_anchor.per_source_result_limit},
                "overview": {"result_limit": self.retrieval.overview.result_limit, "per_source_result_limit": self.retrieval.overview.per_source_result_limit},
                "prioritized_drilldown": {"result_limit": self.retrieval.prioritized_drilldown.result_limit, "per_source_result_limit": self.retrieval.prioritized_drilldown.per_source_result_limit},
                "specialist": {"result_limit": self.retrieval.specialist.result_limit, "per_source_result_limit": self.retrieval.specialist.per_source_result_limit},
            },
            "recursion": {"default_depth": self.recursion.default_depth},
            "evidence_admission": {"minimum_entity_match_level": self.evidence_admission.minimum_entity_match_level},
            "quality_gate": {"ready_for_review_score": self.quality_gate.ready_for_review_score},
            "extraction": {"capital_signals_max": self.extraction.capital_signals_max},
            "infrastructure": {"max_concurrency": self.infrastructure.max_concurrency},
        }


_active_policy: RuntimePolicy = RuntimePolicy()


def get_active_policy() -> RuntimePolicy:
    return _active_policy


def set_active_policy(policy: RuntimePolicy) -> None:
    global _active_policy
    _active_policy = policy


def _default_config_path() -> Path | None:
    for candidate in [Path("config.yaml"), Path("config/config.yaml")]:
        if candidate.exists():
            return candidate
    return None


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    import re
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    result: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [result]
    indent_stack: list[int] = [-1]
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while indent_stack and indent <= indent_stack[-1]:
            stack.pop(); indent_stack.pop()
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip().strip('"').strip("'")
            value = value.strip()
            if value == "" or value in ("{}",):
                d: dict[str, Any] = {}
                stack[-1][key] = d
                stack.append(d); indent_stack.append(indent)
            elif value in ("true", "True"): stack[-1][key] = True
            elif value in ("false", "False"): stack[-1][key] = False
            elif (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                stack[-1][key] = value[1:-1]
            elif re.match(r"^-?\d+$", value): stack[-1][key] = int(value)
            elif re.match(r"^-?\d+\.\d+$", value): stack[-1][key] = float(value)
            else: stack[-1][key] = value
    return result


def _parse_layer_budgets(raw: dict[str, Any]) -> LayerBudgets:
    lbs = raw.get("layer_budgets", raw)
    return LayerBudgets(
        entity_anchor=RetrievalPolicy(int(_deep_get(lbs, "entity_anchor.result_limit", 3)), int(_deep_get(lbs, "entity_anchor.per_source_result_limit", 3))),
        overview=RetrievalPolicy(int(_deep_get(lbs, "overview.result_limit", 5)), int(_deep_get(lbs, "overview.per_source_result_limit", 5))),
        prioritized_drilldown=RetrievalPolicy(int(_deep_get(lbs, "prioritized_drilldown.result_limit", 8)), int(_deep_get(lbs, "prioritized_drilldown.per_source_result_limit", 8))),
        specialist=RetrievalPolicy(int(_deep_get(lbs, "specialist.result_limit", 12)), int(_deep_get(lbs, "specialist.per_source_result_limit", 12))),
    )

def _parse_recursion(raw: dict[str, Any]) -> RecursionPolicyConfig:
    return RecursionPolicyConfig(int(raw.get("default_depth", 3)), int(raw.get("max_subjects", 80)), int(raw.get("max_signals_per_dimension", 120)))

def _parse_evidence(raw: dict[str, Any]) -> EvidenceAdmissionPolicy:
    sr = raw.get("subject_resolution", {})
    return EvidenceAdmissionPolicy(str(raw.get("minimum_entity_match_level", "strong")), float(sr.get("exact_threshold", 0.95)), float(sr.get("strong_threshold", 0.80)), float(sr.get("review_threshold", 0.55)), str(raw.get("evidence_boundary", "public_only")))

def _parse_quality(raw: dict[str, Any]) -> QualityGatePolicy:
    return QualityGatePolicy(int(raw.get("ready_for_review_score", 85)), int(raw.get("usable_with_warnings_score", 65)), int(raw.get("blocker_deduction", 30)), int(raw.get("warning_deduction", 8)), int(raw.get("evidence_substantial_min_count", 4)), int(raw.get("evidence_substantial_min_dimensions", 4)))

def _parse_extraction(raw: dict[str, Any]) -> ExtractionPolicy:
    return ExtractionPolicy(int(raw.get("capital_signals_max", 10)), int(raw.get("product_signals_max", 8)), int(raw.get("industry_signals_max", 8)), int(raw.get("supply_chain_signals_max", 12)), int(raw.get("people_entities_max", 8)), int(raw.get("people_pairs_max", 12)), int(raw.get("list_values_max", 4)), int(raw.get("business_model_signals_max", 8)), int(raw.get("market_position_signals_max", 6)))

def _parse_infrastructure(raw: dict[str, Any]) -> InfrastructurePolicy:
    return InfrastructurePolicy(int(raw.get("max_concurrency", 50)), int(raw.get("max_sources", 100)), int(raw.get("max_query_length", 2048)), int(raw.get("cache_max_size", 1000)), int(raw.get("cache_default_ttl", 300)), int(raw.get("deep_graph_max_depth", 8)), int(raw.get("deep_graph_max_nodes_per_layer", 10)), int(raw.get("context_max_summary_chars", 700)), int(raw.get("context_max_line_chars", 240)), int(raw.get("context_max_evidence_lines", 8)), int(raw.get("context_max_risk_lines", 8)), int(raw.get("context_max_recent_lines", 4)), int(raw.get("engine_concurrency_cap", 20)), int(raw.get("engine_retries_cap", 5)), int(raw.get("risk_event_store_alert_limit", 10)))

def _deep_get(d: dict[str, Any], path: str, default: Any = 0) -> Any:
    for key in path.split("."):
        if isinstance(d, dict): d = d.get(key, default)
        else: return default
    return d


def create_default_policy() -> RuntimePolicy:
    return RuntimePolicy()
