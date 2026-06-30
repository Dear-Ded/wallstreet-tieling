#!/usr/bin/env python3
"""
evidence_chain.py — Multi-Source Evidence Corroboration & Confidence Tiering

Advances evidence from single-source leads to multi-source corroborated facts.
Implements the wallstreet-tieling evidence grading pipeline:

    raw_data → single_source_record → cross_source_match → fact_or_lead

Key features:
- Cross-source entity matching (company name, registration ID, domain)
- Evidence confidence scoring (source authority × data freshness × cross-source count)
- Automatic lead→fact promotion when 2+ independent sources agree
- Contradiction detection (source A says X, source B says Y → flag for investigation)
- Evidence chain audit trail (which sources corroborated which claims)

Usage:
    from core.evidence_chain import EvidenceChain

    chain = EvidenceChain()
    chain.ingest(sec_response)  # from SEC EDGAR adapter
    chain.ingest(gleif_response)  # from GLEIF adapter
    facts, leads, conflicts = chain.evaluate()
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Evidence Item
# ---------------------------------------------------------------------------

class EvidenceGrade(str, Enum):
    FACT = "fact"
    LEAD = "lead"
    WEAK_LEAD = "weak_lead"
    REJECTED = "rejected"
    CONFLICT = "conflict"  # Two sources disagree


@dataclass
class EvidenceItem:
    """Single piece of evidence from one data source."""
    evidence_id: str
    source_name: str
    source_authority: float  # 0-1: how authoritative is this source?
    claim_type: str  # "revenue", "legal_rep", "address", "supplier", etc.
    claim_value: Any
    confidence: float = 0.5
    freshness_days: float = 0  # days since data was published/updated
    admission: EvidenceGrade = EvidenceGrade.LEAD
    raw_context: dict[str, Any] = field(default_factory=dict)
    corroborated_by: list[str] = field(default_factory=list)
    contradicted_by: list[str] = field(default_factory=list)

    @property
    def claim_key(self) -> str:
        """Normalized key for cross-source matching."""
        val = str(self.claim_value).strip().lower()
        # Remove common noise
        val = re.sub(r"[^\w\u4e00-\u9fff]", "", val)
        return f"{self.claim_type}:{val}"


# ---------------------------------------------------------------------------
# Source Authority Weights
# ---------------------------------------------------------------------------

SOURCE_AUTHORITY = {
    "sec_edgar_api": 0.95,           # US SEC — audited financials
    "gleif_lei_api": 0.90,           # GLEIF — verified LEI records
    "gsxt_gov_cn": 0.85,             # 中国工商注册 — government registry
    "ofac_sanctions_xml": 0.95,      # US Treasury — sanctions data
    "courts_gov_cn": 0.85,           # 中国裁判文书 — court judgments
    "qyyjt_api": 0.75,               # 企业预警通 — commercial aggregator
    "wikidata_graph": 0.55,          # Wikidata — crowd-sourced
    "opencorporates_api": 0.80,      # OpenCorporates — official registry aggregator
    "public_web_search": 0.35,       # Public web — unverified snippets
    "user_upload": 0.60,             # User-provided — self-attested
    "im_bot_query": 0.50,            # IM platform bot — automated aggregation
    "default": 0.40,
}


def get_source_authority(source_name: str) -> float:
    for key, weight in SOURCE_AUTHORITY.items():
        if key in source_name.lower():
            return weight
    return SOURCE_AUTHORITY["default"]


# ---------------------------------------------------------------------------
# Claim Normalizer
# ---------------------------------------------------------------------------

class ClaimNormalizer:
    """Normalize claim values for cross-source comparison."""

    @staticmethod
    def normalize_money(value: Any) -> float | None:
        """Normalize monetary values to float (CNY or USD)."""
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().lower().replace(",", "").replace(" ", "")
        # Remove currency symbols
        s = s.replace("¥", "").replace("$", "").replace("€", "").replace("元", "")
        s = s.replace("万", "e4").replace("亿", "e8").replace("亿", "e8")
        s = s.replace("b", "e9").replace("m", "e6").replace("k", "e3")
        try:
            return float(re.sub(r"[^\d.e]", "", s))
        except ValueError:
            return None

    @staticmethod
    def normalize_name(value: str) -> str:
        """Normalize company/person names for fuzzy matching."""
        s = str(value).strip().lower()
        # Remove corporate suffixes
        for suffix in ["有限公司", "股份有限公司", "有限责任公司", "ltd", "limited",
                       "inc", "incorporated", "corp", "corporation", "co.", "llc", "llp"]:
            s = s.replace(suffix, "")
        return re.sub(r"[^\w\u4e00-\u9fff]", "", s)

    @staticmethod
    def normalize_address(value: str) -> str:
        s = str(value).strip().lower()
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
        return s

    @staticmethod
    def normalize_identifier(value: str) -> str:
        """USCC / LEI / CIK — exact match only."""
        return str(value).strip().upper().replace(" ", "")


# ---------------------------------------------------------------------------
# Evidence Chain
# ---------------------------------------------------------------------------

@dataclass
class EvidenceChainResult:
    """Output of evidence chain evaluation."""
    facts: list[EvidenceItem] = field(default_factory=list)
    leads: list[EvidenceItem] = field(default_factory=list)
    weak_leads: list[EvidenceItem] = field(default_factory=list)
    rejected: list[EvidenceItem] = field(default_factory=list)
    conflicts: list[tuple[EvidenceItem, EvidenceItem]] = field(default_factory=list)
    corroboration_graph: dict[str, list[str]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def fact_count(self) -> int: return len(self.facts)
    @property
    def lead_count(self) -> int: return len(self.leads)
    @property
    def conflict_count(self) -> int: return len(self.conflicts)


class EvidenceChain:
    """Multi-source evidence corroboration engine.

    Ingests evidence from multiple adapters, cross-references claims,
    promotes leads to facts when corroborated, and flags contradictions.
    """

    def __init__(self):
        self._items: list[EvidenceItem] = []
        self._normalizer = ClaimNormalizer()
        self.corroboration_threshold = 2  # number of sources needed for fact promotion
        self.confidence_threshold = 0.6   # minimum confidence for fact

    def ingest(self, item: EvidenceItem | dict) -> None:
        """Ingest a single evidence item."""
        if isinstance(item, dict):
            item = EvidenceItem(
                evidence_id=item.get("evidence_id", hashlib.sha256(
                    json.dumps(item, sort_keys=True, default=str).encode()
                ).hexdigest()[:12]),
                source_name=item.get("source_name", "unknown"),
                source_authority=item.get("source_authority",
                    get_source_authority(item.get("source_name", ""))),
                claim_type=item.get("claim_type", "unknown"),
                claim_value=item.get("claim_value", item.get("fields", {})),
                confidence=item.get("confidence", 0.5),
                freshness_days=item.get("freshness_days", 0),
                admission=EvidenceGrade(item.get("admission", "lead")),
                raw_context=item.get("raw_context", {}),
            )
        self._items.append(item)

    def ingest_batch(self, items: list[EvidenceItem | dict]) -> None:
        for item in items:
            self.ingest(item)

    def evaluate(self) -> EvidenceChainResult:
        """Run the full evidence chain: classify, corroborate, detect conflicts."""
        result = EvidenceChainResult()

        # Step 1: Classify by admission grade
        for item in self._items:
            if item.admission == EvidenceGrade.REJECTED:
                result.rejected.append(item)
            elif item.admission == EvidenceGrade.FACT:
                result.facts.append(item)
            elif item.admission == EvidenceGrade.WEAK_LEAD:
                result.weak_leads.append(item)
            else:
                result.leads.append(item)

        # Step 2: Cross-source corroboration — promote leads to facts
        claim_groups: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in result.leads + result.facts:
            key = item.claim_key
            claim_groups[key].append(item)

        promoted = []
        for key, items in claim_groups.items():
            if len(items) >= self.corroboration_threshold:
                # Multiple sources agree on the same claim
                sources = list({i.source_name for i in items})
                if len(sources) >= 2:  # At least 2 different sources
                    best = max(items, key=lambda i: i.source_authority * (1.0 / (1.0 + i.freshness_days)))
                    best.admission = EvidenceGrade.FACT
                    best.confidence = min(0.95, best.confidence + 0.15 * len(items))
                    best.corroborated_by = sources
                    if best in result.leads:
                        result.leads.remove(best)
                        result.facts.append(best)
                        promoted.append(best)

        # Step 3: Contradiction detection
        for key, items in claim_groups.items():
            if len(items) >= 2:
                values = list({str(i.claim_value).strip().lower() for i in items})
                if len(values) >= 2:  # Same claim type, different values
                    # Check if values are significantly different (not just formatting)
                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            v1 = str(items[i].claim_value).strip().lower()
                            v2 = str(items[j].claim_value).strip().lower()
                            if v1 != v2 and items[i].source_name != items[j].source_name:
                                items[i].contradicted_by.append(items[j].source_name)
                                items[j].contradicted_by.append(items[i].source_name)
                                result.conflicts.append((items[i], items[j]))

        # Step 4: Build corroboration graph
        for item in self._items:
            if item.corroborated_by:
                result.corroboration_graph[item.evidence_id] = item.corroborated_by

        # Step 5: Summary
        result.summary = {
            "total_items": len(self._items),
            "facts": result.fact_count,
            "leads": result.lead_count,
            "weak_leads": len(result.weak_leads),
            "rejected": len(result.rejected),
            "conflicts": result.conflict_count,
            "promoted": len(promoted),
            "sources": list({i.source_name for i in self._items}),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        return result

    def to_ledger_rows(self) -> list[dict[str, Any]]:
        """Export all evidence as ledger-compatible rows."""
        result = self.evaluate()
        rows = []
        for item in (result.facts + result.leads + result.weak_leads + result.rejected):
            rows.append({
                "evidence_id": item.evidence_id,
                "source_name": item.source_name,
                "source_authority": item.source_authority,
                "claim_type": item.claim_type,
                "claim_value": item.claim_value,
                "confidence": item.confidence,
                "admission": item.admission.value,
                "corroborated_by": item.corroborated_by,
                "contradicted_by": item.contradicted_by,
                "freshness_days": item.freshness_days,
            })
        return rows

    def clear(self):
        self._items.clear()
