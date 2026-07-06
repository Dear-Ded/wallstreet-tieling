#!/usr/bin/env python3
"""Machine-readable report output targets for agent and final-product delivery."""
from __future__ import annotations

from typing import Any

from .release_contract import release_readiness_brief


def build_report_delivery_targets() -> dict[str, Any]:
    """Return the report-output contract desktop agents must preserve."""
    release = release_readiness_brief()
    surfaces = {item.get("surface"): item for item in release.get("runtime_delivery", {}).get("surfaces", [])}
    docx_surface = surfaces.get("printable_docx_export", {})
    html_surface = surfaces.get("portable_html_and_markdown_exports", {})
    persona = release.get("persona_surface", {})
    return {
        "type": "report_delivery_targets",
        "version": release.get("version", "0.5.0"),
        "current_delivery": "desktop_agent_alpha",
        "full_product_status": release.get("delivery_decision", {}).get("full_product_status", "not_final_release_ready"),
        "status": "alpha_report_contract_ready",
        "current_release_outputs": [
            {
                "id": "json_packet",
                "required": True,
                "current_status": "ready",
                "agent_field": "investigation_packet",
                "must_preserve": ["quality_gate", "evidence_ledger", "one_click_readiness", "report_exports"],
            },
            {
                "id": "markdown_report",
                "required": True,
                "current_status": "ready",
                "agent_field": "report_markdown",
                "must_preserve": ["risk_brief", "profile_brief", "enterprise_cognition", "source limitations"],
            },
            {
                "id": "portable_html",
                "required": True,
                "current_status": "runtime_available_final_visual_polish_remaining",
                "agent_field": "report_exports.portable_html",
                "entrypoints": _entrypoints(html_surface),
                "must_preserve": [
                    "all investigation findings",
                    "first_screen_handoff_cards",
                    "delivery_checklist_source",
                    "agent_decision_digest",
                ],
            },
            {
                "id": "docx_red_head",
                "required": True,
                "current_status": "runtime_available_print_polish_iterating",
                "agent_field": "report_exports.print_package",
                "entrypoints": _entrypoints(docx_surface),
                "must_preserve": [
                    "official_document_metadata",
                    "red_head_separator_rule",
                    "native_chart_summary_panels",
                    "source_provenance_appendix",
                    "relationship_capital_appendix",
                    "embedded_local_image_evidence",
                ],
            },
            {
                "id": "directory_bundle",
                "required": True,
                "current_status": "ready",
                "agent_field": "report_exports.directory_bundle",
                "must_preserve": ["file_manifest", "delivery_checklist", "agent_summary", "agent_handoff"],
            },
        ],
        "persona_interaction_contract": {
            "required": True,
            "role_count": persona.get("role_count", 0),
            "surface": "persona_surface",
            "must_preserve": [
                "13-role anthropomorphic shell",
                "runtime_lane_bindings",
                "data_sources lane",
                "verification lane",
                "finance lane",
                "people lane",
            ],
        },
        "final_product_targets": [
            {
                "id": "functional_completeness",
                "status": "open_until_final_release",
                "done_when": "No report-critical due-diligence dimension is omitted from the investigation packet, report, or agent handoff.",
            },
            {
                "id": "print_ready_official_docx",
                "status": "open_until_final_release",
                "done_when": "DOCX renders as a printable official-style red-head document with tables, charts, image evidence, appendices, and source provenance.",
            },
            {
                "id": "immersive_html_report",
                "status": "open_until_final_release",
                "done_when": "HTML report is visually polished and interactive without reducing any findings, tables, images, or evidence details from the investigation packet.",
            },
            {
                "id": "persona_not_shrunk",
                "status": "open_until_final_release",
                "done_when": "All supported agent hosts preserve persona routing and role-flavored interaction instead of returning a generic prose-only report.",
            },
        ],
        "agent_rules": [
            "Do not collapse report_exports, evidence_ledger, quality_gate, or agent_handoff into prose only.",
            "Do not treat desktop-agent alpha as final-product completion.",
            "Do not remove DOCX/HTML/persona requirements because the first delivery target is a desktop-agent package.",
            "If a host cannot render DOCX or HTML directly, preserve the runtime entrypoints and report_exports fields for a capable host.",
        ],
    }


def _entrypoints(surface: dict[str, Any]) -> list[str]:
    return [str(item) for item in surface.get("entrypoints", []) if str(item).strip()]
