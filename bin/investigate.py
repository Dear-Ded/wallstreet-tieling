#!/usr/bin/env python3
"""Run one-click investigation and return a product-facing packet."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.datasource_fixtures import build_datasource_fixture_pack  # noqa: E402
from core.connector_registry import ConnectorRegistry  # noqa: E402
from core.development_requirements import build_development_requirements_board  # noqa: E402
from core.investigation import (  # noqa: E402
    _packet_queue_agent_autorun,
    _packet_source_resilience_handoff,
    build_investigation_packet,
)
from core.official_public_smoke import (  # noqa: E402
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)
from core.one_click_defaults import resolve_one_click_retrieval_async  # noqa: E402
from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture  # noqa: E402
from core.risk_graph_export import export_risk_graph  # noqa: E402
from core.report_docx import render_print_package_docx  # noqa: E402


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def force_utf8_stdio() -> None:
    """Keep CLI JSON decodable when Windows defaults stdout to a local codepage."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-click company investigation packet: verdict, report, graph, evidence, and watch seed."
    )
    parser.add_argument("company", help="Company name or unified social credit identifier.")
    parser.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"], help="Investigation mode label.")
    parser.add_argument("--store", default="", help="JSONL risk-event store path.")
    parser.add_argument("--config", default="", help="YAML datasource config path.")
    parser.add_argument("--retrieval-concurrency", type=int, default=4, help="Maximum concurrent retrieval tasks.")
    parser.add_argument("--query-timeout-seconds", type=float, default=20.0, help="Maximum seconds to wait for one retrieval task.")
    parser.add_argument("--fanout-rounds", type=int, default=1, help="Bounded entity fan-out rounds.")
    parser.add_argument("--max-fanout-tasks", type=int, default=24, help="Maximum generated fan-out tasks.")
    parser.add_argument("--offline-fixture", action="store_true", help="Use deterministic offline public-record fixture.")
    parser.add_argument("--fixture-pack", action="store_true", help="Use the multi-source datasource fixture pack.")
    parser.add_argument("--official-public-smoke", action="store_true", help="Run live official/public datasource smoke with selected public sources.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON packet explicitly. This is also the default unless --report-only is used.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print Markdown report instead of the full JSON packet.",
    )
    parser.add_argument(
        "--export-docx",
        default="",
        help="Write a Word-openable red-head DOCX report to this path while still printing the JSON packet.",
    )
    parser.add_argument(
        "--export-dir",
        default="",
        help="Write DOCX, portable HTML, Markdown, JSON, and an export manifest into this directory.",
    )
    parser.add_argument(
        "--export-html",
        default="",
        help="Write the portable printable HTML report to this path while still printing stdout.",
    )
    parser.add_argument(
        "--export-markdown",
        default="",
        help="Write the full Markdown report body to this path while still printing stdout.",
    )
    parser.add_argument(
        "--export-json",
        default="",
        help="Write the full investigation JSON packet to this path while still printing stdout.",
    )
    return parser


async def run(args: argparse.Namespace) -> dict:
    mode_count = sum(bool(item) for item in (args.config, args.offline_fixture, args.fixture_pack, args.official_public_smoke))
    if mode_count > 1:
        raise SystemExit("--config, --offline-fixture, --fixture-pack, and --official-public-smoke are mutually exclusive")

    records = None
    if args.fixture_pack:
        records = build_datasource_fixture_pack(args.company).all_records()
    elif args.offline_fixture:
        records = offline_enforcement_fixture(args.company)

    search_engine = None
    existing_plan = None
    config_path = args.config
    if args.official_public_smoke:
        config_path = str(build_official_public_smoke_config())
        existing_plan = build_official_public_smoke_plan(args.company)
    if config_path:
        from adapters.multi_datasource import SearchEngine

        await SearchEngine.initialize(config_path)
        search_engine = SearchEngine

    selected = await resolve_one_click_retrieval_async(
        company=args.company,
        records=records,
        search_engine=search_engine,
        existing_plan=existing_plan,
        fanout_rounds=clamp_int(args.fanout_rounds, 0, 3),
        default_enabled=True,
    )

    result = await RiskDiscoveryPipeline().run(
        args.company,
        records=selected.records,
        search_engine=selected.search_engine,
        store_path=args.store or None,
        existing_plan=selected.existing_plan,
        retrieval_concurrency=clamp_int(args.retrieval_concurrency, 1, 20),
        fanout_rounds=1 if args.official_public_smoke else selected.fanout_rounds,
        max_fanout_tasks=clamp_int(args.max_fanout_tasks, 0, 80),
        identifier_fanout_only=bool(args.official_public_smoke),
        query_timeout_seconds=clamp_float(args.query_timeout_seconds, 0.1, 120.0),
    )
    graph_payload = export_risk_graph(result).to_dict()
    return build_investigation_packet(
        graph_payload,
        input_text=args.company,
        mode=args.mode,
    ).to_dict()


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    if args.json and args.report_only:
        raise SystemExit("--json and --report-only are mutually exclusive")
    payload = asyncio.run(run(args))
    json_document = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.export_docx:
        output_path = Path(args.export_docx)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(render_print_package_docx(payload))
    if args.export_dir:
        _write_report_export_dir(args.export_dir, payload, json_document)
    if args.export_html:
        _write_text_export(
            args.export_html,
            str(payload.get("report_exports", {}).get("portable_html", {}).get("document") or ""),
        )
    if args.export_markdown:
        _write_text_export(args.export_markdown, str(payload.get("report_markdown") or ""))
    if args.export_json:
        _write_text_export(args.export_json, json_document)
    if args.report_only:
        print(payload["report_markdown"])
    else:
        print(json_document)
    return 0


def _write_text_export(path: str, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8", newline="\n")


def _write_report_export_dir(path: str, payload: dict, json_document: str) -> None:
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_exports = payload.get("report_exports", {})
    markdown = report_exports.get("markdown", {})
    portable_html = report_exports.get("portable_html", {})
    json_packet = report_exports.get("json_packet", {})
    print_package = report_exports.get("print_package", {})
    docx = print_package.get("docx", {}) if isinstance(print_package, dict) else {}

    files = {
        "markdown": _safe_export_name(markdown.get("filename"), "due-diligence-report.md"),
        "portable_html": _safe_export_name(portable_html.get("filename"), "due-diligence-report.html"),
        "json_packet": _safe_export_name(json_packet.get("filename"), "investigation-packet.json"),
        "docx": _safe_export_name(docx.get("filename"), "red-head-due-diligence-report.docx"),
        "agent_handoff": _safe_export_name(
            report_exports.get("directory_bundle", {}).get("agent_handoff", {}).get("filename")
            if isinstance(report_exports.get("directory_bundle"), dict)
            else "",
            "agent-handoff.json",
        ),
        "manifest": "report-export-manifest.json",
    }
    (output_dir / files["markdown"]).write_text(str(payload.get("report_markdown") or ""), encoding="utf-8", newline="\n")
    (output_dir / files["portable_html"]).write_text(
        str(portable_html.get("document") or ""),
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / files["json_packet"]).write_text(json_document, encoding="utf-8", newline="\n")
    (output_dir / files["docx"]).write_bytes(render_print_package_docx(payload))
    file_manifest = _export_file_manifest(output_dir, files, exclude={files["manifest"], files["agent_handoff"]})
    agent_handoff = _agent_handoff_export(payload, files, file_manifest=file_manifest)
    (output_dir / files["agent_handoff"]).write_text(
        json.dumps(agent_handoff, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "type": "report_export_directory_manifest",
        "company": payload.get("summary", {}).get("company") or payload.get("input"),
        "files": files,
        "file_manifest": file_manifest,
        "delivery_checklist": print_package.get("delivery_checklist", {}) if isinstance(print_package, dict) else {},
        "agent_summary": _manifest_agent_summary(agent_handoff),
        "report_exports": report_exports,
    }
    (output_dir / files["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )


def _safe_export_name(value: object, fallback: str) -> str:
    name = str(value or fallback).replace("\\", "-").replace("/", "-").strip(" .")
    return name or fallback


def _export_file_manifest(output_dir: Path, files: dict[str, str], exclude: set[str] | None = None) -> dict:
    excluded = set(exclude or set())
    rows = []
    for role, filename in sorted(files.items()):
        if not filename or filename in excluded:
            continue
        path = output_dir / filename
        if not path.exists() or not path.is_file():
            continue
        content = path.read_bytes()
        rows.append(
            {
                "role": role,
                "filename": filename,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "type": "report_export_file_manifest",
        "hash_algorithm": "sha256",
        "item_count": len(rows),
        "items": rows,
        "policy": "Hashes cover primary emitted report files except manifest and agent-handoff self-referential files to avoid recursive self-hash ambiguity.",
    }


def _agent_handoff_export(
    payload: dict,
    files: dict | None = None,
    file_manifest: dict | None = None,
) -> dict:
    one_click = payload.get("one_click_readiness", {})
    monitoring_seed = payload.get("monitoring_seed", {})
    report_exports = payload.get("report_exports", {})
    portable_html = report_exports.get("portable_html", {}) if isinstance(report_exports, dict) else {}
    print_package = report_exports.get("print_package", {}) if isinstance(report_exports, dict) else {}
    enterprise_cognition = payload.get("enterprise_cognition", {})
    control_ownership = (
        enterprise_cognition.get("control_ownership")
        if isinstance(enterprise_cognition, dict)
        else {}
    )
    if not isinstance(control_ownership, dict):
        control_ownership = {}
    reliance_limitations = one_click.get("reliance_limitations", {})
    if not isinstance(reliance_limitations, dict):
        reliance_limitations = {}
    limitation_items = [
        dict(item)
        for item in reliance_limitations.get("items", [])
        if isinstance(item, dict)
    ][:8]
    closure_steps = {
        "capital_relationship": one_click.get("capital_relationship_closure_step") or {},
        "control_path": one_click.get("control_path_closure_step") or {},
        "goods_economics": one_click.get("goods_economics_closure_step") or {},
        "people_control": one_click.get("people_control_closure_step") or {},
        "graph_capital_exposure": one_click.get("graph_capital_exposure_top_step") or {},
    }
    closure_queue = [
        {"closure_id": key, **value}
        for key, value in closure_steps.items()
        if isinstance(value, dict) and value
    ]
    acceptance_closure = one_click.get("acceptance_closure_summary")
    if not isinstance(acceptance_closure, dict):
        acceptance_closure = {}
    relationship_graph_audit = _relationship_graph_audit_handoff(one_click)
    relationship_resolution = _relationship_resolution_handoff(enterprise_cognition)
    capital_risk_panel = _capital_risk_panel(one_click, enterprise_cognition, relationship_graph_audit)
    delivery_files = _delivery_file_handoff(files or {}, report_exports)
    delivery_checklist = print_package.get("delivery_checklist") if isinstance(print_package, dict) else {}
    if not isinstance(delivery_checklist, dict):
        delivery_checklist = {}
    report_visibility = _report_visibility_handoff(print_package, portable_html)
    source_strengthening = _source_strengthening_handoff()
    source_resilience_handoff = _packet_source_resilience_handoff(
        one_click_readiness=one_click,
        monitoring_seed=monitoring_seed,
    )
    next_actions = _agent_next_actions(one_click, monitoring_seed, relationship_graph_audit)
    bundle_integrity = _bundle_integrity_handoff(file_manifest or {}, files or {})
    bundle_verification = _bundle_verification_handoff(report_exports, files or {}, bundle_integrity)
    artifact_autorun = _report_artifact_agent_autorun(
        delivery_files=delivery_files,
        report_visibility=report_visibility,
        bundle_verification=bundle_verification,
        acceptance_closure=acceptance_closure,
    )
    delivery_files["agent_autorun"] = artifact_autorun
    report_visibility["agent_autorun"] = artifact_autorun
    bundle_verification["agent_autorun"] = artifact_autorun
    trust_boundaries = _trust_boundaries(payload, one_click, monitoring_seed)
    decision_digest = _decision_digest(
        one_click=one_click,
        delivery_checklist=delivery_checklist,
        bundle_integrity=bundle_integrity,
        trust_boundaries=trust_boundaries,
        next_actions=next_actions,
        relationship_graph_audit=relationship_graph_audit,
    )
    delivery_decision = _requirements_delivery_decision()
    return {
        "type": "report_export_agent_handoff",
        "company": payload.get("summary", {}).get("company") or payload.get("input"),
        "status": one_click.get("status"),
        "delivery_decision": delivery_decision,
        "delivery_files": delivery_files,
        "bundle_integrity": bundle_integrity,
        "bundle_verification": bundle_verification,
        "delivery_checklist": delivery_checklist,
        "report_visibility": report_visibility,
        "capital_risk_panel": capital_risk_panel,
        "source_strengthening": source_strengthening,
        "relationship_resolution": relationship_resolution,
        "trust_boundaries": trust_boundaries,
        "decision_digest": decision_digest,
        "next_actions": next_actions,
        "acceptance_closure": {
            "status": one_click.get("acceptance_closure_status") or acceptance_closure.get("status") or "unknown",
            "blocking_count": one_click.get("acceptance_closure_blocking_count", acceptance_closure.get("blocking_count", 0)),
            "ready_count": one_click.get("acceptance_closure_ready_count", acceptance_closure.get("ready_count", 0)),
            "open_domains": list(acceptance_closure.get("open_domains") or [])[:8],
            "top_action": one_click.get("acceptance_closure_top_action") or acceptance_closure.get("top_action") or {},
            "next_action": acceptance_closure.get("next_action") or "",
            "done_condition": acceptance_closure.get("done_condition") or "",
            "agent_autorun": artifact_autorun,
            "policy": acceptance_closure.get("policy") or "",
        },
        "reliance_limitations": {
            "count": reliance_limitations.get("count", 0),
            "highest_severity": reliance_limitations.get("highest_severity") or "none",
            "can_make_clean_conclusion": bool(one_click.get("can_make_clean_conclusion")),
            "policy": reliance_limitations.get("policy") or "",
            "top_next_action": limitation_items[0].get("next_action") if limitation_items else "",
            "items": limitation_items,
        },
        "operator_work": {
            "count": one_click.get("operator_work_queue_count", 0),
            "p0_count": one_click.get("operator_work_p0_count", 0),
            "ready_count": one_click.get("operator_work_ready_count", 0),
            "top_action": one_click.get("operator_work_top_action") or {},
            "queue": list(one_click.get("operator_work_queue") or [])[:12],
        },
        "closure_steps": {
            "count": len(closure_queue),
            "ready_count": sum(1 for item in closure_queue if bool(item.get("ready_to_run", True))),
            "people_control_needed": bool(one_click.get("people_control_closure_needed")),
            "goods_economics_needed": bool(one_click.get("goods_economics_closure_needed")),
            "control_path_needed": bool(one_click.get("control_path_closure_needed")),
            "capital_relationship_status": one_click.get("capital_relationship_status") or "",
            "steps": closure_steps,
            "queue": closure_queue,
            "control_path_verification_queue": list(control_ownership.get("control_path_verification_queue") or [])[:8],
            "control_path_top_step": one_click.get("control_path_closure_step") or {},
            "policy": "Closure steps are task-routing hints only; use evidence ledger and provenance before upgrading leads to facts.",
        },
        "qyyjt_public_origin": {
            "handoff": payload.get("qyyjt_public_origin_handoff") or {},
            "section_execution_summary": (
                (payload.get("qyyjt_public_origin_handoff") or {}).get("section_execution_summary") or {}
            ),
            "top_ready_section_work_order": (
                (payload.get("qyyjt_public_origin_handoff") or {}).get("top_ready_section_work_order") or {}
            ),
            "report_section_batches": list(
                (payload.get("qyyjt_public_origin_handoff") or {}).get("report_section_batches") or []
            )[:8],
            "section_work_orders": list(
                (payload.get("qyyjt_public_origin_handoff") or {}).get("section_work_orders") or []
            )[:8],
            "top_section_work_order": (payload.get("qyyjt_public_origin_handoff") or {}).get("top_section_work_order") or {},
            "agent_autorun": (payload.get("qyyjt_public_origin_handoff") or {}).get("agent_autorun") or {},
            "gap_bridge": one_click.get("public_origin_gap_bridge") or {},
            "gap_bridge_top_action": one_click.get("public_origin_gap_bridge_top_action") or {},
        },
        "source_health": {
            "digest": one_click.get("source_health_trend_digest") or {},
            "snapshot": monitoring_seed.get("source_health_trend_snapshot") or {},
            "top_source": one_click.get("source_health_trend_top_source") or {},
            "policy": one_click.get("source_health_trend_policy") or "",
            "repair_queue": list(monitoring_seed.get("source_repair_priority_queue") or [])[:8],
            "recovery_execution_queue": monitoring_seed.get("recovery_execution_queue") or {},
            "recovery_summary": monitoring_seed.get("recovery_execution_summary") or {},
            "source_resilience": {
                "status": one_click.get("source_resilience_status") or "",
                "score": one_click.get("source_resilience_score"),
                "recommended_action": one_click.get("source_resilience_recommended_action") or "",
                "recommended_step": one_click.get("source_resilience_recommended_step") or {},
                "retry_policy": one_click.get("source_resilience_retry_policy") or {},
                "retryable": bool(one_click.get("source_resilience_retryable")),
                "max_attempts": one_click.get("source_resilience_retry_max_attempts", 0),
                "ready_to_run": bool(one_click.get("source_resilience_recommended_step_ready_to_run")),
                "blocked_reason": one_click.get("source_resilience_recommended_step_blocked_reason") or "",
                "agent_autorun": source_resilience_handoff.get("agent_autorun") or {},
            },
        },
        "capital_and_relationship": {
            "risk_panel": capital_risk_panel,
            "graph_capital_exposure": one_click.get("graph_capital_exposure") or {},
            "graph_capital_exposure_top_step": one_click.get("graph_capital_exposure_top_step") or {},
            "capital_verification_queue": list(one_click.get("capital_verification_queue") or [])[:8],
            "capital_verification_top_step": one_click.get("capital_verification_top_step") or {},
            "capital_relationship_closure_step": one_click.get("capital_relationship_closure_step") or {},
            "relationship_graph_audit": relationship_graph_audit,
            "relationship_graph_audit_top_step": one_click.get("relationship_graph_audit_top_step") or {},
            "relationship_resolution": relationship_resolution,
            "agent_autorun": {
                "capital_verification": capital_risk_panel.get("agent_autorun") or {},
                "relationship_graph_audit": relationship_graph_audit.get("agent_autorun") or {},
                "relationship_resolution": relationship_resolution.get("agent_autorun") or {},
            },
        },
        "report_handoff_cards": {
            "source": portable_html.get("first_screen_handoff_source")
            or "report_exports.print_package.operational_handoff.cards",
            "cards": list(portable_html.get("first_screen_handoff_cards") or []),
            "print_package_summary": (print_package.get("operational_handoff") or {}).get("summary", {}),
            "delivery_checklist_status": delivery_checklist.get("status") or "",
        },
        "policy": "Use this lightweight handoff for desktop-agent task routing; open delivery_files first, then use the full json_packet for evidence and final report content.",
    }


def _source_strengthening_handoff() -> dict:
    """Expose bounded source-hardening work orders inside export-dir handoffs."""
    try:
        catalog = ConnectorRegistry().product_catalog()
    except Exception as exc:  # pragma: no cover - defensive for CLI fallback mode
        return {
            "type": "source_strengthening_handoff",
            "status": "unavailable",
            "work_order_count": 0,
            "top_work_orders": [],
            "by_lane": {},
            "blocked_reason": f"connector_catalog_unavailable:{exc}",
            "policy": "Run connector_catalog separately before assigning source-hardening work.",
        }
    queue = [
        item for item in catalog.get("source_strengthening_queue", [])
        if isinstance(item, dict)
    ]
    top_work_orders: list[dict] = []
    by_lane: dict[str, int] = {}
    for item in queue[:8]:
        lane = str(item.get("lane") or "general_enrichment")
        by_lane[lane] = by_lane.get(lane, 0) + 1
        execution_plan = item.get("execution_plan") if isinstance(item.get("execution_plan"), dict) else {}
        implementation_pack = item.get("implementation_pack") if isinstance(item.get("implementation_pack"), dict) else {}
        runtime_companion = item.get("runtime_companion") if isinstance(item.get("runtime_companion"), dict) else {}
        top_work_orders.append({
            "connector": item.get("connector") or "",
            "priority": item.get("priority") or "",
            "lane": lane,
            "missing_contracts": list(item.get("missing_contracts") or [])[:8],
            "next_action": item.get("next_action") or "",
            "runtime_companion": runtime_companion,
            "execution_plan": {
                "type": execution_plan.get("type") or "source_strengthening_execution_plan",
                "source_hint": execution_plan.get("source_hint") or "",
                "record_type": execution_plan.get("record_type") or "",
                "first_target_file": execution_plan.get("first_target_file") or "",
                "primary_acceptance_command": execution_plan.get("primary_acceptance_command") or "",
                "runtime_companion": execution_plan.get("runtime_companion")
                if isinstance(execution_plan.get("runtime_companion"), dict)
                else runtime_companion,
                "ordered_steps": list(execution_plan.get("ordered_steps") or [])[:6],
                "report_gate": execution_plan.get("report_gate") or "",
            },
            "implementation_pack_ref": {
                "type": implementation_pack.get("type") or "source_strengthening_implementation_pack",
                "target_files": list(implementation_pack.get("target_files") or [])[:6],
                "acceptance_commands": list(implementation_pack.get("acceptance_commands") or [])[:3],
            },
        })
    status = "ready" if top_work_orders else "complete"
    completion_summary = {
        "type": "source_strengthening_completion_summary",
        "candidate_count": len(queue),
        "pending_work": bool(top_work_orders),
        "message": (
            "No pending source-strengthening work orders remain in connector_catalog; "
            "future source expansion should start from new connector admission metadata."
        ),
    }
    return {
        "type": "source_strengthening_handoff",
        "status": status,
        "catalog_tool": "connector_catalog",
        "mcp_tool": "connector_catalog",
        "cli": "npx wallstreet-tieling --connectors",
        "api": "GET /api/connectors",
        "work_order_count": len(queue),
        "top_work_orders": top_work_orders,
        "top_work_order": top_work_orders[0] if top_work_orders else {},
        "by_lane": by_lane,
        "completion_summary": completion_summary,
        "preserve_fields": [
            "connector_catalog.source_strengthening_queue",
            "connector_catalog.source_strengthening_queue[].implementation_pack",
            "connector_catalog.source_strengthening_queue[].execution_plan",
            "connector_catalog.source_strengthening_queue[].runtime_companion",
        ],
        "promotion_gate": (
            "Do not promote catalog or lead-only rows into report facts until source-specific "
            "standardized records, provenance, entity match, and admission tests pass."
        ),
        "policy": (
            "This handoff is follow-up runtime work for source hardening. It does not change the current "
            "investigation facts or imply live-source availability."
        ),
    }


def _report_visibility_handoff(print_package: dict, portable_html: dict) -> dict:
    if not isinstance(print_package, dict):
        print_package = {}
    if not isinstance(portable_html, dict):
        portable_html = {}
    image_inventory = print_package.get("image_evidence_inventory", {})
    source_appendix = print_package.get("source_provenance_appendix", {})
    section_inventory = print_package.get("section_inventory", [])
    chart_manifest = print_package.get("chart_manifest", [])
    operational_handoff = print_package.get("operational_handoff", {})
    if not isinstance(image_inventory, dict):
        image_inventory = {}
    if not isinstance(source_appendix, dict):
        source_appendix = {}
    if not isinstance(section_inventory, list):
        section_inventory = []
    if not isinstance(chart_manifest, list):
        chart_manifest = []
    if not isinstance(operational_handoff, dict):
        operational_handoff = {}
    premium_profile = portable_html.get("premium_profile", {})
    if not isinstance(premium_profile, dict):
        premium_profile = {}
    return {
        "type": "report_visibility_handoff",
        "portable_html_filename": portable_html.get("filename") or "",
        "portable_html_contains_full_body": True,
        "premium_html": {
            "profile_present": premium_profile.get("type") == "premium_html_report_profile",
            "status": premium_profile.get("status") or "",
            "filename": premium_profile.get("filename") or portable_html.get("filename") or "",
            "document_field": premium_profile.get("document_field") or "report_exports.portable_html.document",
            "acceptance_checklist": list(premium_profile.get("acceptance_checklist") or [])[:12],
            "content_guarantees": list(premium_profile.get("content_guarantees") or [])[:12],
            "forbidden_shortcuts": list(premium_profile.get("forbidden_shortcuts") or [])[:12],
            "metrics": premium_profile.get("metrics") if isinstance(premium_profile.get("metrics"), dict) else {},
            "policy": premium_profile.get("policy") or "",
        },
        "first_screen_handoff_card_count": int(portable_html.get("first_screen_handoff_card_count") or 0),
        "image_evidence": {
            "inventory_type": image_inventory.get("type") or "image_evidence_inventory",
            "inventory_source": "report_exports.print_package.image_evidence_inventory",
            "count": int(image_inventory.get("count") or 0),
            "embeddable_count": int(image_inventory.get("embeddable_count") or 0),
            "remote_reference_count": int(image_inventory.get("remote_reference_count") or 0),
            "appendix_required": bool(image_inventory.get("appendix_required")),
            "items": list(image_inventory.get("items") or [])[:8],
            "policy": image_inventory.get("delivery_policy") or "",
        },
        "source_provenance": {
            "source_count": int(source_appendix.get("source_count") or 0),
            "evidence_row_count": int(source_appendix.get("evidence_row_count") or 0),
            "appendix_required": bool(source_appendix.get("appendix_required")),
            "rows": list(source_appendix.get("rows") or [])[:12],
            "policy": source_appendix.get("policy") or "",
        },
        "section_inventory_count": len(section_inventory),
        "chart_manifest_count": len(chart_manifest),
        "operational_handoff_card_count": int(operational_handoff.get("card_count") or 0),
        "open_order": [
            "delivery_files.primary_print_file",
            "delivery_files.primary_screen_file",
            "report_visibility.premium_html",
            "report_visibility.image_evidence",
            "report_visibility.source_provenance",
            "json_packet.evidence_ledger",
        ],
        "policy": "Report visibility keeps charts, image evidence, source provenance, and full-body preservation visible to desktop agents before they summarize the report.",
    }


def _bundle_integrity_handoff(file_manifest: dict, files: dict) -> dict:
    items = file_manifest.get("items", []) if isinstance(file_manifest, dict) else []
    if not isinstance(items, list):
        items = []
    hashed_roles = [str(item.get("role") or "") for item in items if isinstance(item, dict) and item.get("role")]
    required_roles = [
        role
        for role in ("docx", "portable_html", "markdown", "json_packet")
        if files.get(role)
    ]
    missing_roles = [role for role in required_roles if role not in set(hashed_roles)]
    return {
        "type": "bundle_integrity_handoff",
        "file_manifest_field": "report-export-manifest.json.file_manifest",
        "hash_algorithm": file_manifest.get("hash_algorithm") if isinstance(file_manifest, dict) else "",
        "hashed_file_count": int(file_manifest.get("item_count") or len(items)) if isinstance(file_manifest, dict) else 0,
        "required_hashed_roles": required_roles,
        "missing_hashed_roles": missing_roles,
        "ready_to_verify": not missing_roles and bool(items),
        "manifest_self_hash_excluded": True,
        "agent_handoff_self_hash_excluded": True,
        "policy": "Verify file size and sha256 for primary report outputs from report-export-manifest.json before sharing or archiving the bundle.",
    }


def _bundle_verification_handoff(report_exports: dict, files: dict, bundle_integrity: dict) -> dict:
    directory_bundle = report_exports.get("directory_bundle", {}) if isinstance(report_exports, dict) else {}
    if not isinstance(directory_bundle, dict):
        directory_bundle = {}
    recipe = directory_bundle.get("verification_recipe", {})
    if not isinstance(recipe, dict):
        recipe = {}
    manifest_name = _safe_export_name(files.get("manifest"), "report-export-manifest.json")
    verifier = str(directory_bundle.get("integrity_verifier_entrypoint") or "bin/verify_report_bundle.py <export-dir>")
    return {
        "type": "bundle_verification_handoff",
        "recipe": recipe,
        "command": recipe.get("command") or "python bin/verify_report_bundle.py <export-dir>",
        "integrity_verifier_entrypoint": verifier,
        "manifest_file": manifest_name,
        "expected_exit_code": int(recipe.get("expected_exit_code") or 0),
        "required_output_fields": list(recipe.get("required_output_fields") or directory_bundle.get("verifier_output_fields") or []),
        "success_condition": recipe.get("success_condition")
        or "ok=true and agent_handoff.schema_valid=true and agent_handoff.bundle_ready_to_verify=true",
        "failure_routing": recipe.get("failure_routing")
        or "Repair missing files, hash mismatches, or handoff schema failures before delivery.",
        "ready_to_run": bool(bundle_integrity.get("ready_to_verify")) if isinstance(bundle_integrity, dict) else False,
        "blocked_reason": "" if isinstance(bundle_integrity, dict) and bundle_integrity.get("ready_to_verify") else "bundle_integrity_not_ready",
        "policy": "Desktop agents must run this verifier after export-dir and before claiming the bundle is deliverable.",
    }


def _report_artifact_agent_autorun(
    *,
    delivery_files: dict,
    report_visibility: dict,
    bundle_verification: dict,
    acceptance_closure: dict,
) -> dict:
    files = delivery_files.get("files", {}) if isinstance(delivery_files, dict) else {}
    if not isinstance(files, dict):
        files = {}
    open_order = list(delivery_files.get("open_order") or []) if isinstance(delivery_files, dict) else []
    command = bundle_verification.get("command") if isinstance(bundle_verification, dict) else ""
    ready_to_run = bool(bundle_verification.get("ready_to_run")) if isinstance(bundle_verification, dict) else False
    blocked_reason = bundle_verification.get("blocked_reason") if isinstance(bundle_verification, dict) else "bundle_verification_unavailable"
    route_files = {
        key: value.get("path") if isinstance(value, dict) else ""
        for key, value in files.items()
    }
    return {
        "type": "report_artifact_agent_autorun",
        "manual_intermediate_steps_required": False,
        "ready_to_run": ready_to_run,
        "blocked_reason": "" if ready_to_run else str(blocked_reason or "bundle_integrity_not_ready"),
        "routes": [
            {
                "route_id": "open-report-artifacts",
                "action": "open_delivery_artifacts",
                "open_order": open_order,
                "files": route_files,
                "required_before_summary": [
                    "docx",
                    "portable_html",
                    "json_packet",
                    "agent_handoff",
                    "manifest",
                ],
                "done_condition": "DOCX, HTML, full JSON packet, agent-handoff, and manifest are all present and addressable from the export directory.",
            },
            {
                "route_id": "verify-report-bundle",
                "action": "run_bundle_verifier",
                "cli_command": command or "python bin/verify_report_bundle.py <export-dir>",
                "ready_to_run": ready_to_run,
                "required_output_fields": list(bundle_verification.get("required_output_fields") or []),
                "success_condition": bundle_verification.get("success_condition") or "",
                "failure_routing": bundle_verification.get("failure_routing") or "",
                "done_condition": "Verifier returns ok=true and agent_handoff.bundle_ready_to_verify=true before delivery is claimed.",
            },
            {
                "route_id": "inspect-acceptance-closure",
                "action": "inspect_acceptance_closure",
                "status": acceptance_closure.get("status") if isinstance(acceptance_closure, dict) else "unknown",
                "blocking_count": int(acceptance_closure.get("blocking_count") or 0) if isinstance(acceptance_closure, dict) else 0,
                "open_domains": list(acceptance_closure.get("open_domains") or [])[:8] if isinstance(acceptance_closure, dict) else [],
                "done_condition": acceptance_closure.get("done_condition") if isinstance(acceptance_closure, dict) else "",
            },
        ],
        "preserve_packet_fields": [
            "report_exports.directory_bundle",
            "report_exports.directory_bundle.agent_handoff",
            "report_exports.directory_bundle.verification_recipe",
            "report_exports.print_package.delivery_checklist",
            "report_exports.portable_html.document",
            "one_click_readiness.acceptance_closure_summary",
        ],
        "report_visibility": {
            "portable_html_contains_full_body": bool(report_visibility.get("portable_html_contains_full_body")) if isinstance(report_visibility, dict) else False,
            "premium_html_profile_present": bool(_as_plain_dict(report_visibility.get("premium_html")).get("profile_present")) if isinstance(report_visibility, dict) else False,
            "image_evidence_count": int(_as_plain_dict(report_visibility.get("image_evidence")).get("count") or 0) if isinstance(report_visibility, dict) else 0,
            "source_count": int(_as_plain_dict(report_visibility.get("source_provenance")).get("source_count") or 0) if isinstance(report_visibility, dict) else 0,
        },
        "operator_intervention_only_when": [
            "Required files are missing from the export directory.",
            "Bundle verifier fails after repairing machine-readable handoff or manifest mismatches.",
            "Acceptance closure reports blocking domains that require new evidence collection or authorization.",
        ],
        "policy": "Open and verify report artifacts automatically; do not summarize away report sections, image evidence, charts, source provenance, or agent-handoff fields.",
    }


def _as_plain_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _decision_digest(
    *,
    one_click: dict,
    delivery_checklist: dict,
    bundle_integrity: dict,
    trust_boundaries: dict,
    next_actions: list[dict],
    relationship_graph_audit: dict,
) -> dict:
    """Compact routing summary for desktop agents that should not infer state from raw JSON."""
    first_action = next_actions[0] if next_actions else {}
    blocked_reasons = [
        str(value)
        for value in (
            one_click.get("source_resilience_recommended_step_blocked_reason"),
            first_action.get("blocked_reason") if isinstance(first_action, dict) else "",
        )
        if str(value or "").strip()
    ]
    blocking_count = int(one_click.get("acceptance_closure_blocking_count") or 0)
    source_ready = bool(one_click.get("source_resilience_recommended_step_ready_to_run"))
    return {
        "type": "agent_decision_digest",
        "delivery_status": delivery_checklist.get("status") if isinstance(delivery_checklist, dict) else "",
        "bundle_ready_to_verify": bool(bundle_integrity.get("ready_to_verify")) if isinstance(bundle_integrity, dict) else False,
        "can_make_clean_conclusion": bool(trust_boundaries.get("can_make_clean_conclusion"))
        if isinstance(trust_boundaries, dict)
        else False,
        "acceptance_closure_status": one_click.get("acceptance_closure_status") or "unknown",
        "acceptance_blocking_count": blocking_count,
        "source_resilience_status": one_click.get("source_resilience_status") or "unknown",
        "source_resilience_ready_to_run": source_ready,
        "source_resilience_retryable": bool(one_click.get("source_resilience_retryable")),
        "capital_relationship_status": one_click.get("capital_relationship_status") or "unknown",
        "relationship_audit_status": relationship_graph_audit.get("status")
        if isinstance(relationship_graph_audit, dict)
        else "unknown",
        "work_queue_counts": {
            "operator_work": int(one_click.get("operator_work_queue_count") or 0),
            "operator_work_ready": int(one_click.get("operator_work_ready_count") or 0),
            "capital_verification": int(one_click.get("capital_verification_queue_count") or 0),
            "relationship_audit": int(one_click.get("relationship_graph_audit_queue_count") or 0),
            "public_origin": int(one_click.get("public_origin_next_action_count") or 0),
            "source_repair": int(one_click.get("source_repair_priority_count") or 0),
        },
        "first_action": {
            "id": first_action.get("id") if isinstance(first_action, dict) else "",
            "priority": first_action.get("priority") if isinstance(first_action, dict) else "",
            "status": first_action.get("status") if isinstance(first_action, dict) else "",
            "ready_to_run": bool(first_action.get("ready_to_run")) if isinstance(first_action, dict) else False,
            "action": first_action.get("action") if isinstance(first_action, dict) else "",
            "done_condition": first_action.get("done_condition") if isinstance(first_action, dict) else "",
        },
        "blocked_reasons": blocked_reasons[:5],
        "requires_operator": bool(one_click.get("needs_operator_followup")) or blocking_count > 0 or not source_ready,
        "public_or_authorized_boundary": "public, licensed, or user-authorized evidence only; no lead is promoted without provenance and admission gates",
        "policy": "Use this digest for routing only; verify evidence in json_packet before final conclusions.",
    }


def _manifest_agent_summary(agent_handoff: dict) -> dict:
    delivery_checklist = agent_handoff.get("delivery_checklist", {})
    trust_boundaries = agent_handoff.get("trust_boundaries", {})
    acceptance_closure = agent_handoff.get("acceptance_closure", {})
    source_health = agent_handoff.get("source_health", {})
    source_resilience = source_health.get("source_resilience", {}) if isinstance(source_health, dict) else {}
    qyyjt_public_origin = agent_handoff.get("qyyjt_public_origin", {})
    capital_relationship = agent_handoff.get("capital_and_relationship", {})
    relationship_resolution = agent_handoff.get("relationship_resolution", {})
    relationship_audit = (
        capital_relationship.get("relationship_graph_audit", {})
        if isinstance(capital_relationship, dict)
        else {}
    )
    operator_work = agent_handoff.get("operator_work", {})
    delivery_decision = agent_handoff.get("delivery_decision", {})
    bundle_verification = agent_handoff.get("bundle_verification", {})
    report_visibility = agent_handoff.get("report_visibility", {})
    capital_risk_panel = agent_handoff.get("capital_risk_panel", {})
    source_strengthening = agent_handoff.get("source_strengthening", {})
    source_repair_queue = source_health.get("repair_queue", []) if isinstance(source_health, dict) else []
    capital_queue = (
        capital_relationship.get("capital_verification_queue", [])
        if isinstance(capital_relationship, dict)
        else []
    )
    next_actions = [
        {
            "id": item.get("id") or "",
            "priority": item.get("priority") or "",
            "status": item.get("status") or "",
            "action": item.get("action") or "",
            "ready_to_run": bool(item.get("ready_to_run")),
            "done_condition": item.get("done_condition") or "",
        }
        for item in agent_handoff.get("next_actions", [])[:5]
        if isinstance(item, dict)
    ]
    return {
        "type": "report_export_manifest_agent_summary",
        "status": agent_handoff.get("status") or "",
        "delivery_decision": delivery_decision if isinstance(delivery_decision, dict) else {},
        "decision_digest": agent_handoff.get("decision_digest", {})
        if isinstance(agent_handoff.get("decision_digest"), dict)
        else {},
        "bundle_verification": bundle_verification if isinstance(bundle_verification, dict) else {},
        "report_visibility": {
            "type": report_visibility.get("type", "report_visibility_handoff")
            if isinstance(report_visibility, dict)
            else "report_visibility_handoff",
            "image_evidence_inventory_present": isinstance(report_visibility, dict)
            and isinstance(report_visibility.get("image_evidence"), dict)
            and report_visibility.get("image_evidence", {}).get("inventory_type") == "image_evidence_inventory",
            "image_evidence_count": report_visibility.get("image_evidence", {}).get("count", 0)
            if isinstance(report_visibility, dict) and isinstance(report_visibility.get("image_evidence"), dict)
            else 0,
            "source_count": report_visibility.get("source_provenance", {}).get("source_count", 0)
            if isinstance(report_visibility, dict) and isinstance(report_visibility.get("source_provenance"), dict)
            else 0,
            "section_inventory_count": report_visibility.get("section_inventory_count", 0)
            if isinstance(report_visibility, dict)
            else 0,
            "chart_manifest_count": report_visibility.get("chart_manifest_count", 0)
            if isinstance(report_visibility, dict)
            else 0,
            "premium_html_profile_present": report_visibility.get("premium_html", {}).get("profile_present", False)
            if isinstance(report_visibility, dict) and isinstance(report_visibility.get("premium_html"), dict)
            else False,
            "premium_html_status": report_visibility.get("premium_html", {}).get("status", "")
            if isinstance(report_visibility, dict) and isinstance(report_visibility.get("premium_html"), dict)
            else "",
        },
        "capital_risk_panel": {
            "type": capital_risk_panel.get("type", "capital_risk_panel")
            if isinstance(capital_risk_panel, dict)
            else "capital_risk_panel",
            "status": capital_risk_panel.get("status", "unknown")
            if isinstance(capital_risk_panel, dict)
            else "unknown",
            "risk_level": capital_risk_panel.get("risk_level", "unknown")
            if isinstance(capital_risk_panel, dict)
            else "unknown",
            "capital_verification_queue_count": capital_risk_panel.get("capital_verification_queue_count", 0)
            if isinstance(capital_risk_panel, dict)
            else 0,
            "relationship_audit_queue_count": capital_risk_panel.get("relationship_audit_queue_count", 0)
            if isinstance(capital_risk_panel, dict)
            else 0,
            "clean_reliance_allowed": bool(capital_risk_panel.get("clean_reliance_allowed"))
            if isinstance(capital_risk_panel, dict)
            else False,
        },
        "source_strengthening": {
            "type": source_strengthening.get("type", "source_strengthening_handoff")
            if isinstance(source_strengthening, dict)
            else "source_strengthening_handoff",
            "status": source_strengthening.get("status", "unknown")
            if isinstance(source_strengthening, dict)
            else "unknown",
            "work_order_count": source_strengthening.get("work_order_count", 0)
            if isinstance(source_strengthening, dict)
            else 0,
            "top_work_order": source_strengthening.get("top_work_order", {})
            if isinstance(source_strengthening, dict)
            else {},
            "by_lane": source_strengthening.get("by_lane", {})
            if isinstance(source_strengthening, dict)
            else {},
        },
        "delivery_status": delivery_checklist.get("status") if isinstance(delivery_checklist, dict) else "",
        "can_make_clean_conclusion": bool(trust_boundaries.get("can_make_clean_conclusion"))
        if isinstance(trust_boundaries, dict)
        else False,
        "acceptance_closure_status": acceptance_closure.get("status") if isinstance(acceptance_closure, dict) else "",
        "acceptance_closure_blocking_count": acceptance_closure.get("blocking_count", 0)
        if isinstance(acceptance_closure, dict)
        else 0,
        "source_resilience_status": source_resilience.get("status") if isinstance(source_resilience, dict) else "",
        "source_resilience_retryable": bool(source_resilience.get("retryable"))
        if isinstance(source_resilience, dict)
        else False,
        "source_resilience_blocked_reason": source_resilience.get("blocked_reason")
        if isinstance(source_resilience, dict)
        else "",
        "relationship_audit_status": relationship_audit.get("status") if isinstance(relationship_audit, dict) else "",
        "relationship_resolution": {
            "type": relationship_resolution.get("type", "relationship_resolution_handoff")
            if isinstance(relationship_resolution, dict)
            else "relationship_resolution_handoff",
            "lead_count": relationship_resolution.get("lead_count", 0)
            if isinstance(relationship_resolution, dict)
            else 0,
            "typed_lead_count": relationship_resolution.get("typed_lead_count", 0)
            if isinstance(relationship_resolution, dict)
            else 0,
            "weak_lead_count": relationship_resolution.get("weak_lead_count", 0)
            if isinstance(relationship_resolution, dict)
            else 0,
            "verification_queue_count": relationship_resolution.get("verification_queue_count", 0)
            if isinstance(relationship_resolution, dict)
            else 0,
            "top_step": relationship_resolution.get("top_step", {})
            if isinstance(relationship_resolution, dict)
            else {},
        },
        "work_queue_counts": {
            "operator_work": operator_work.get("count", 0) if isinstance(operator_work, dict) else 0,
            "operator_work_ready": operator_work.get("ready_count", 0) if isinstance(operator_work, dict) else 0,
            "source_repair": len(source_repair_queue) if isinstance(source_repair_queue, list) else 0,
            "qyyjt_public_origin_sections": len(qyyjt_public_origin.get("section_work_orders", []))
            if isinstance(qyyjt_public_origin, dict)
            else 0,
            "capital_verification": len(capital_queue) if isinstance(capital_queue, list) else 0,
            "relationship_audit": relationship_audit.get("queue_count", 0)
            if isinstance(relationship_audit, dict)
            else 0,
        },
        "top_public_origin_work_order": qyyjt_public_origin.get("top_section_work_order", {})
        if isinstance(qyyjt_public_origin, dict)
        else {},
        "top_capital_step": capital_relationship.get("capital_verification_top_step", {})
        if isinstance(capital_relationship, dict)
        else {},
        "top_relationship_step": relationship_audit.get("top_step", {})
        if isinstance(relationship_audit, dict)
        else {},
        "next_action_count": len(agent_handoff.get("next_actions", []))
        if isinstance(agent_handoff.get("next_actions"), list)
        else 0,
        "top_next_actions": next_actions,
        "policy": "Manifest summary is a bounded routing preview; use agent-handoff.json and the full JSON packet for complete evidence review.",
    }


def _requirements_delivery_decision() -> dict:
    board = build_development_requirements_board()
    decision = board.get("delivery_decision", {})
    summary = board.get("summary", {})
    if not isinstance(decision, dict):
        decision = {}
    if not isinstance(summary, dict):
        summary = {}
    return {
        "type": decision.get("type") or "development_delivery_decision",
        "current_target": decision.get("current_target") or "desktop_agent_alpha",
        "status": decision.get("status") or summary.get("desktop_agent_delivery") or "unknown",
        "desktop_agent_release_candidate": bool(decision.get("desktop_agent_release_candidate")),
        "full_product_status": decision.get("full_product_status") or summary.get("release_decision") or "not_final_release_ready",
        "current_release_completion_percent": decision.get("current_release_completion_percent", board.get("completion_percent", 0)),
        "p0_open_count": decision.get("p0_open_count", summary.get("p0_open_count", 0)),
        "next_major_gate": decision.get("next_major_gate") or summary.get("next_major_gate") or "",
        "source": "development_requirements_board",
        "policy": decision.get("policy") or "",
    }


def _delivery_file_handoff(files: dict, report_exports: dict) -> dict:
    directory_bundle = report_exports.get("directory_bundle", {}) if isinstance(report_exports, dict) else {}
    if not isinstance(directory_bundle, dict):
        directory_bundle = {}
    print_package = report_exports.get("print_package", {}) if isinstance(report_exports, dict) else {}
    portable_html = report_exports.get("portable_html", {}) if isinstance(report_exports, dict) else {}
    markdown = report_exports.get("markdown", {}) if isinstance(report_exports, dict) else {}
    json_packet = report_exports.get("json_packet", {}) if isinstance(report_exports, dict) else {}
    docx = print_package.get("docx", {}) if isinstance(print_package, dict) else {}
    directory_agent_handoff = directory_bundle.get("agent_handoff", {})
    if not isinstance(directory_agent_handoff, dict):
        directory_agent_handoff = {}

    resolved = {
        "docx": _safe_export_name(files.get("docx") or docx.get("filename"), "red-head-due-diligence-report.docx"),
        "portable_html": _safe_export_name(
            files.get("portable_html") or portable_html.get("filename"),
            "due-diligence-report.html",
        ),
        "markdown": _safe_export_name(files.get("markdown") or markdown.get("filename"), "due-diligence-report.md"),
        "json_packet": _safe_export_name(
            files.get("json_packet") or json_packet.get("filename"),
            "investigation-packet.json",
        ),
        "agent_handoff": _safe_export_name(
            files.get("agent_handoff") or directory_agent_handoff.get("filename"),
            "agent-handoff.json",
        ),
        "manifest": _safe_export_name(files.get("manifest"), "report-export-manifest.json"),
    }
    return {
        "type": "delivery_file_handoff",
        "bundle_manifest": resolved["manifest"],
        "primary_print_file": resolved["docx"],
        "primary_screen_file": resolved["portable_html"],
        "full_evidence_packet": resolved["json_packet"],
        "markdown_report": resolved["markdown"],
        "agent_handoff_file": resolved["agent_handoff"],
        "open_order": [
            resolved["docx"],
            resolved["portable_html"],
            resolved["markdown"],
            resolved["json_packet"],
            resolved["agent_handoff"],
            resolved["manifest"],
        ],
        "files": {
            "docx": {
                "path": resolved["docx"],
                "role": "primary_print_report",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "required": True,
            },
            "portable_html": {
                "path": resolved["portable_html"],
                "role": "primary_screen_report",
                "mime_type": "text/html; charset=utf-8",
                "required": True,
            },
            "markdown": {
                "path": resolved["markdown"],
                "role": "plain_text_report_body",
                "mime_type": "text/markdown; charset=utf-8",
                "required": True,
            },
            "json_packet": {
                "path": resolved["json_packet"],
                "role": "full_evidence_packet",
                "mime_type": "application/json; charset=utf-8",
                "required": True,
            },
            "agent_handoff": {
                "path": resolved["agent_handoff"],
                "role": "desktop_agent_task_router",
                "mime_type": "application/json; charset=utf-8",
                "required": True,
            },
            "manifest": {
                "path": resolved["manifest"],
                "role": "bundle_file_manifest",
                "mime_type": "application/json; charset=utf-8",
                "required": True,
            },
        },
        "stdout_preserved": True,
        "policy": "File names are relative to the export directory; use json_packet for evidence replay and DOCX/HTML/Markdown for presentation.",
    }


def _agent_next_actions(one_click: dict, monitoring_seed: dict, relationship_graph_audit: dict) -> list[dict]:
    actions: list[dict] = []

    def add_action(action_id: str, source: str, item: object, default_action: str = "") -> None:
        if isinstance(item, dict) and item:
            action = item.get("action") or item.get("next_action") or item.get("done_condition") or default_action
            done_condition = item.get("done_condition") or item.get("acceptance_gate") or ""
            priority = item.get("priority") or "P1"
            status = item.get("status") or "ready"
            ready_to_run = bool(item.get("ready_to_run", True))
        else:
            action = default_action
            done_condition = ""
            priority = "P1"
            status = "ready" if default_action else "skipped"
            ready_to_run = bool(default_action)
        if not action:
            return
        actions.append(
            {
                "id": action_id,
                "source": source,
                "priority": priority,
                "status": status,
                "action": action,
                "ready_to_run": ready_to_run,
                "done_condition": done_condition,
                "packet_refs": _packet_refs_for_action(source),
            }
        )

    add_action("acceptance_closure", "acceptance_closure", one_click.get("acceptance_closure_top_action"))
    add_action("operator_work", "operator_work", one_click.get("operator_work_top_action"))
    add_action("source_resilience", "source_health", one_click.get("source_resilience_recommended_step"))
    add_action("capital_verification", "capital_and_relationship", one_click.get("capital_verification_top_step"))
    add_action("relationship_graph_audit", "capital_and_relationship", relationship_graph_audit.get("top_step"))
    add_action("public_origin_gap_bridge", "qyyjt_public_origin", one_click.get("public_origin_gap_bridge_top_action"))
    add_action("control_path", "closure_steps", one_click.get("control_path_closure_step"))
    add_action("goods_economics", "closure_steps", one_click.get("goods_economics_closure_step"))
    add_action("people_control", "closure_steps", one_click.get("people_control_closure_step"))

    recovery_queue = monitoring_seed.get("recovery_execution_queue") if isinstance(monitoring_seed, dict) else {}
    if isinstance(recovery_queue, dict):
        ready_rows = [item for item in recovery_queue.get("ready") or [] if isinstance(item, dict)]
        if ready_rows:
            add_action("source_recovery_execution", "source_health", ready_rows[0])

    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    actions.sort(key=lambda item: (priority_rank.get(str(item["priority"]), 9), 0 if item["ready_to_run"] else 1, item["id"]))
    return actions[:12]


def _packet_refs_for_action(source: str) -> list[str]:
    refs = {
        "acceptance_closure": ["one_click_readiness.acceptance_closure_summary", "report_exports.print_package.operational_handoff"],
        "operator_work": ["one_click_readiness.operator_work_queue", "report_exports.print_package.operational_handoff.cards"],
        "source_health": ["monitoring_seed.recovery_execution_queue", "one_click_readiness.source_resilience_recommended_step"],
        "capital_and_relationship": ["one_click_readiness.capital_verification_queue", "one_click_readiness.relationship_graph_audit_queue"],
        "qyyjt_public_origin": ["qyyjt_public_origin_handoff.section_work_orders", "one_click_readiness.public_origin_gap_bridge"],
        "closure_steps": ["one_click_readiness.control_path_closure_step", "one_click_readiness.goods_economics_closure_step", "one_click_readiness.people_control_closure_step"],
    }
    return refs.get(source, ["json_packet"])


def _trust_boundaries(payload: dict, one_click: dict, monitoring_seed: dict) -> dict:
    return {
        "type": "agent_handoff_trust_boundaries",
        "public_data_boundary": "public, licensed, or user-authorized evidence only",
        "can_make_clean_conclusion": bool(one_click.get("can_make_clean_conclusion")),
        "reliance_limitation_count": int(one_click.get("reliance_limitation_count") or 0),
        "lead_only_until_verified": True,
        "weak_leads_are_not_facts": True,
        "source_health_is_connector_work_not_subject_risk": True,
        "current_release_monitoring_enabled": bool(monitoring_seed.get("current_release_monitoring_enabled")) if isinstance(monitoring_seed, dict) else False,
        "continuous_monitoring_scope": (
            monitoring_seed.get("feature_scope")
            if isinstance(monitoring_seed, dict)
            else "future_version_not_current_release"
        )
        or "future_version_not_current_release",
        "final_report_content_source": "report_markdown plus full json_packet evidence ledger",
        "policy": "Do not upgrade leads, source failures, or connector repair tasks into subject-risk facts without admitted evidence and entity-resolution checks.",
    }


def _relationship_resolution_handoff(enterprise_cognition: dict) -> dict:
    """Bounded relationship-resolution routing summary for desktop agents."""
    resolution = enterprise_cognition.get("relationship_resolution_v1") if isinstance(enterprise_cognition, dict) else {}
    if not isinstance(resolution, dict):
        resolution = {}
    summary = resolution.get("resolution_summary") if isinstance(resolution.get("resolution_summary"), dict) else {}
    queue = [
        dict(item)
        for item in summary.get("verification_queue", [])
        if isinstance(item, dict)
    ][:8]
    leads = [
        dict(item)
        for item in resolution.get("phase1_candidate_leads", [])
        if isinstance(item, dict)
    ][:8]
    top_step = queue[0] if queue else {}
    agent_autorun = _packet_queue_agent_autorun(
        autorun_type="relationship_resolution_agent_autorun",
        routes=queue,
        route_prefix="REL-RESOLVE",
        required_output_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
        ],
        policy="Relationship-resolution leads stay leads until corroborated by registry, filing, announcement, licensed, or user-authorized evidence.",
    )
    return {
        "type": "relationship_resolution_handoff",
        "source": "enterprise_cognition.relationship_resolution_v1",
        "lead_count": int(resolution.get("lead_count") or len(resolution.get("phase1_candidate_leads") or [])),
        "edge_count": int(resolution.get("edge_count") or len(resolution.get("phase2_admitted_edges") or [])),
        "typed_lead_count": int(summary.get("typed_lead_count") or 0),
        "weak_lead_count": int(summary.get("weak_lead_count") or 0),
        "lead_risk_level": summary.get("lead_risk_level") or "unknown",
        "by_relation_type": summary.get("by_relation_type") if isinstance(summary.get("by_relation_type"), dict) else {},
        "by_lane": summary.get("by_lane") if isinstance(summary.get("by_lane"), dict) else {},
        "source_names": list(summary.get("source_names") or [])[:8],
        "verification_queue_count": len(queue),
        "verification_queue": queue,
        "top_step": top_step,
        "candidate_leads": leads,
        "agent_autorun": agent_autorun,
        "preserve_fields": [
            "enterprise_cognition.relationship_resolution_v1",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary",
            "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
        ],
        "policy": "Relationship resolution is a lead-routing surface. Candidate leads are not facts until corroborated by registry, filing, announcement, licensed, or user-authorized evidence.",
    }


def _relationship_graph_audit_handoff(one_click: dict) -> dict:
    edge_count = int(one_click.get("relationship_edge_count") or 0)
    evidence_backed_count = int(one_click.get("relationship_evidence_backed_edge_count") or 0)
    auditable_count = int(one_click.get("relationship_auditable_edge_count") or 0)
    missing_evidence_count = int(one_click.get("relationship_missing_evidence_edge_count") or 0)
    lead_only_count = int(one_click.get("relationship_lead_only_edge_count") or 0)
    queue_count = int(one_click.get("relationship_graph_audit_queue_count") or 0)
    queue = [
        dict(item)
        for item in one_click.get("relationship_graph_audit_queue") or []
        if isinstance(item, dict)
    ][:8]
    top_step = one_click.get("relationship_graph_audit_top_step") or {}
    if not isinstance(top_step, dict):
        top_step = {}
    agent_autorun = _packet_queue_agent_autorun(
        autorun_type="relationship_graph_audit_agent_autorun",
        routes=queue,
        route_prefix="REL-AUDIT",
        required_output_fields=[
            "one_click_readiness.relationship_graph_audit_queue",
            "one_click_readiness.relationship_graph_audit_top_step",
            "enterprise_cognition.relationship_resolution_v1",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.relationship_resolution_v1",
            "one_click_readiness.relationship_graph_audit_queue",
            "report_exports.directory_bundle.agent_handoff.relationship_resolution",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit",
        ],
        policy="Audit relationship edges as verification tasks; never promote lead-only or missing-evidence edges into facts.",
    )
    if edge_count <= 0:
        status = "no_relationship_edges"
    elif queue_count > 0 or missing_evidence_count > 0 or lead_only_count > 0:
        status = "audit_required"
    else:
        status = "evidence_backed"
    return {
        "type": "relationship_graph_audit_handoff",
        "status": status,
        "edge_count": edge_count,
        "evidence_backed_edge_count": evidence_backed_count,
        "auditable_edge_count": auditable_count,
        "missing_evidence_edge_count": missing_evidence_count,
        "lead_only_edge_count": lead_only_count,
        "queue_count": queue_count,
        "queue": queue,
        "top_step": top_step,
        "agent_autorun": agent_autorun,
        "next_action": top_step.get("done_condition")
        or "Keep relationship edges lead-only until source provenance, entity match, and evidence IDs are verified.",
        "policy": (
            "Relationship graph handoff is task routing only; clean reliance requires evidence IDs, "
            "fact/admitted evidence status, source provenance, and entity-resolution checks."
        ),
    }


def _capital_risk_panel(
    one_click: dict,
    enterprise_cognition: dict,
    relationship_graph_audit: dict,
) -> dict:
    """Compact capital/relationship decision panel for low-context agent hosts."""
    if not isinstance(one_click, dict):
        one_click = {}
    if not isinstance(enterprise_cognition, dict):
        enterprise_cognition = {}
    if not isinstance(relationship_graph_audit, dict):
        relationship_graph_audit = {}

    capital_pressure = enterprise_cognition.get("capital_pressure_profile", {})
    if not isinstance(capital_pressure, dict):
        capital_pressure = {}
    capital_relationship = enterprise_cognition.get("capital_relationship_profile", {})
    if not isinstance(capital_relationship, dict):
        capital_relationship = {}

    capital_queue = [
        dict(item)
        for item in one_click.get("capital_verification_queue") or []
        if isinstance(item, dict)
    ][:8]
    relationship_queue = [
        dict(item)
        for item in one_click.get("relationship_graph_audit_queue") or []
        if isinstance(item, dict)
    ][:8]
    capital_queue_count = int(one_click.get("capital_verification_queue_count") or len(capital_queue))
    relationship_queue_count = int(
        one_click.get("relationship_graph_audit_queue_count") or relationship_graph_audit.get("queue_count") or len(relationship_queue)
    )
    relationship_status = str(one_click.get("capital_relationship_status") or "unknown")
    pressure_level = str(one_click.get("capital_pressure_level") or capital_pressure.get("pressure_level") or "none")
    verification_status = str(
        one_click.get("capital_pressure_verification_status")
        or capital_pressure.get("verification_status")
        or "unknown"
    )
    unresolved_reason = str(one_click.get("capital_relationship_unresolved_reason") or "")
    lead_only_count = int(one_click.get("relationship_lead_only_edge_count") or 0)
    missing_evidence_count = int(one_click.get("relationship_missing_evidence_edge_count") or 0)
    relationship_match_count = int(one_click.get("capital_relationship_match_count") or capital_relationship.get("match_count") or 0)

    if relationship_status == "evidence_backed" and missing_evidence_count == 0 and lead_only_count == 0:
        status = "evidence_backed"
    elif relationship_status == "not_applicable" and pressure_level in {"none", "low"}:
        status = "not_applicable"
    elif relationship_queue_count or capital_queue_count or unresolved_reason:
        status = "verification_required"
    else:
        status = relationship_status or "unknown"

    top_action = (
        one_click.get("capital_relationship_closure_step")
        or one_click.get("graph_capital_exposure_top_step")
        or one_click.get("capital_verification_top_step")
        or relationship_graph_audit.get("top_step")
        or {}
    )
    if not isinstance(top_action, dict):
        top_action = {}
    autorun_seed = capital_queue or ([top_action] if top_action else [{
        "step_id": "CAPITAL-RECHECK-001",
        "priority": "P1",
        "kind": "capital_relationship_recheck",
        "target": "capital_risk_panel",
        "done_condition": "Re-run deep investigation and preserve capital risk panel, graph capital exposure, and relationship audit fields.",
        "ready_to_run": True,
    }])
    agent_autorun = _packet_queue_agent_autorun(
        autorun_type="capital_risk_agent_autorun",
        routes=autorun_seed,
        route_prefix="CAPITAL",
        required_output_fields=[
            "one_click_readiness.capital_verification_queue",
            "one_click_readiness.capital_risk_panel",
            "one_click_readiness.graph_capital_exposure",
            "report_exports.directory_bundle.agent_handoff.capital_risk_panel",
        ],
        preserve_packet_fields=[
            "enterprise_cognition.capital_pressure_profile",
            "enterprise_cognition.capital_relationship_profile",
            "one_click_readiness.capital_verification_queue",
            "one_click_readiness.graph_capital_exposure",
            "report_exports.directory_bundle.agent_handoff.capital_and_relationship",
        ],
        policy="Verify capital pressure rows and relationship context before relying on capital-risk conclusions.",
    )

    official_or_authorized = bool(one_click.get("capital_pressure_has_official_or_authorized_source"))
    clean_reliance_allowed = (
        status == "evidence_backed"
        and official_or_authorized
        and not bool(one_click.get("capital_pressure_lead_only_public_rows_present"))
        and missing_evidence_count == 0
        and lead_only_count == 0
    )

    return {
        "type": "capital_risk_panel",
        "status": status,
        "risk_level": capital_relationship.get("relationship_risk_level") or pressure_level or "unknown",
        "pressure_level": pressure_level,
        "capital_pressure_verification_status": verification_status,
        "capital_relationship_status": relationship_status,
        "capital_relationship_unresolved_reason": unresolved_reason,
        "capital_relationship_match_count": relationship_match_count,
        "relationship_edge_count": int(one_click.get("relationship_edge_count") or 0),
        "relationship_evidence_backed_edge_count": int(one_click.get("relationship_evidence_backed_edge_count") or 0),
        "relationship_auditable_edge_count": int(one_click.get("relationship_auditable_edge_count") or 0),
        "relationship_missing_evidence_edge_count": missing_evidence_count,
        "relationship_lead_only_edge_count": lead_only_count,
        "capital_verification_queue_count": capital_queue_count,
        "relationship_audit_queue_count": relationship_queue_count,
        "capital_verification_queue": capital_queue,
        "relationship_audit_queue": relationship_queue,
        "top_action": {
            "step_id": top_action.get("step_id") or top_action.get("id") or "",
            "priority": top_action.get("priority") or "",
            "kind": top_action.get("kind") or "",
            "target_id": top_action.get("target_id") or "",
            "target_title": top_action.get("target_title") or top_action.get("target") or "",
            "done_condition": top_action.get("done_condition") or "",
        },
        "source_posture": {
            "top_family": one_click.get("capital_pressure_source_top_family") or "",
            "family_count": int(one_click.get("capital_pressure_source_family_count") or 0),
            "has_official_or_authorized_source": official_or_authorized,
            "lead_only_public_rows_present": bool(one_click.get("capital_pressure_lead_only_public_rows_present")),
        },
        "clean_reliance_allowed": clean_reliance_allowed,
        "required_packet_refs": [
            "enterprise_cognition.capital_pressure_profile",
            "enterprise_cognition.capital_relationship_profile",
            "one_click_readiness.graph_capital_exposure",
            "one_click_readiness.capital_verification_queue",
            "one_click_readiness.relationship_graph_audit_queue",
        ],
        "agent_autorun": agent_autorun,
        "next_action": (
            top_action.get("done_condition")
            or one_click.get("capital_relationship_next_action")
            or "Verify capital pressure rows and relationship edges before relying on capital-risk conclusions."
        ),
        "policy": (
            "Capital risk panel is a routing surface. It must not upgrade public leads or unresolved relationship edges "
            "into clean conclusions without admitted source evidence, entity match, and relationship provenance."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
