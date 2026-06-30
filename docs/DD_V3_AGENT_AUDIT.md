# DD v3.0 Agent Audit Report

## Agent A: Code Audit (surface vs real implementations)

### Findings

| File | Function | Surface? | Real? | Issue |
|------|----------|----------|-------|-------|
| core/due_diligence_audit.py | build_capability_audit | NO | YES | Derived from dd_profile, readiness, graph state |
| core/evidence_ledger_v2.py | normalize_evidence_v2 | NO | YES | Lane classification from claim text |
| core/entity_resolution.py | build_entity_resolution | NO | YES | Resolves from subject_profile identifiers + graph nodes |
| core/relationship_resolution.py | build_relationship_resolution | NO | YES | Phase1 from evidence_v2 lanes, Phase2 from graph edges |
| core/investigation_strategy.py | build_strategy_v2 | NO | YES | Actions bound to gap statuses + source readiness |
| core/investigation.py | _build_strategy_quality_gate | PARTIAL | PARTIAL | Still returns 75-100 range; needs more variance |
| core/investigation.py | _build_graph_sanity_check | NO | YES | 5 checks all data-driven |
| core/investigation.py | _build_live_readiness_gate | NO | YES | Reacts to source states |

### Orphan Functions Found
- `_fast_empty_detect` — orphan, never called in pipeline
- `_pre_search_cache_check` — result assigned but never consumed (skip_request ignored)

### Hardcoded True Removed
- Old CapabilityAudit had 12 hardcoded True values
- New build_capability_audit derives every field from state checks

## Agent B: High-Star Project Research

### Projects Studied
1. **dedupe (dedupeio/dedupe)** — Probabilistic entity resolution library
   - Pattern: Trainable entity matching with active learning
   - Adopted: Normalized name keys + ambiguity flags in entity_resolution.py
   - Not adopted: Training-based matching (too heavy for current pipeline)

2. **OSINT-Framework (lockfale/osint-framework)** — OSINT source taxonomy
   - Pattern: Categorized data sources by type
   - Adopted: source_type classification in evidence_ledger_v2 (public/authorized/fixture)
   
3. **SpiderFoot (smicallef/spiderfoot)** — Automated OSINT collection
   - Pattern: Module-based source collection with event-driven pipeline
   - Adopted: Module separation pattern (5 new modules)
   - Not adopted: Event-driven architecture (current pipeline is linear)

4. **Neo4j Graph Data Science** — Relationship graph quality
   - Pattern: Graph quality metrics (density, connectivity)
   - Adopted: graph_sanity_check with 5 quality flags

## Agent C: Test Gap Analysis

### Current Coverage
- 7 tests in test_dd_v3_audit.py covering capability_audit, entity_resolution, relationship_resolution, strategy_v2

### Missing Tests (Priority):
1. [ ] report_only implementation should not count as capability
2. [ ] audit log must not contain cookie/token/browser profile
3. [ ] entity_resolution same-name-different-ID prevents fact merge
4. [ ] evidence_ledger_v2 rejected must have admission_reason
5. [ ] CapabilityAudit tested count reflects reality (not all caps tested)

### Adopted: 2 tests from C's list added below.
