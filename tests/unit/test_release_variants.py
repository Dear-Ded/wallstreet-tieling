#!/usr/bin/env python3
"""Release-portal contract tests for product variants."""
from __future__ import annotations

from pathlib import Path
import json
import re

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VARIANTS_PATH = PROJECT_ROOT / "release" / "variants.yaml"
PACKAGE_PATH = PROJECT_ROOT / "package.json"
MCP_MANIFEST_PATH = PROJECT_ROOT / "deploy" / "mcp-server.json"


def _load_variants() -> dict:
    return yaml.safe_load(VARIANTS_PATH.read_text(encoding="utf-8"))


def test_release_matrix_defines_desktop_agent_target_variants():
    data = _load_variants()

    assert set(data["variants"]) == {
        "universal",
        "codex",
        "claude_code",
        "hermes",
        "doubao_office_task_mode",
        "open_claude_agents",
        "workbuddy_expert_team",
    }


def test_release_variant_entrypoints_exist():
    data = _load_variants()

    for variant_name, variant in data["variants"].items():
        for entrypoint in variant["entrypoints"]:
            target = PROJECT_ROOT / entrypoint
            assert target.exists(), f"{variant_name} entrypoint missing: {entrypoint}"


def test_release_matrix_keeps_product_claims_tied_to_core_capabilities():
    data = _load_variants()

    shared_core = set(data["product"]["shared_core"])
    assert "core.enterprise_cognition.EnterpriseCognitionEngine" in shared_core
    assert "core.intelligence_retrieval.InvestigativeRetrievalPlanner" in shared_core
    assert "core.risk_event_store.RiskEventStore" in shared_core

    for variant in data["variants"].values():
        assert variant["readiness"] in {"planned", "alpha", "beta", "stable"}
        assert variant["required_capabilities"]
        assert variant["next_gate"]


def test_release_gates_cover_claims_security_and_quality():
    data = _load_variants()

    gates = data["release_gates"]
    assert {"public_claims", "security", "quality"} <= set(gates)
    assert any("No API keys" in rule for rule in gates["security"])
    assert any("feature claim" in rule for rule in gates["public_claims"])
    assert any("evidence gaps" in rule for rule in gates["quality"])


def test_release_contract_can_be_loaded_by_runtime_api():
    from core.release_contract import load_release_contract, release_readiness_brief

    contract = load_release_contract()
    brief = release_readiness_brief()

    assert contract["type"] == "release_contract"
    assert contract["version"] == "0.5.0"
    assert contract["summary"]["variant_count"] == 7
    assert contract["persona_surface"]["type"] == "persona_surface_brief"
    assert contract["persona_surface"]["role_count"] == 13
    assert contract["variants"]["codex"]["entrypoints"]
    assert brief["type"] == "release_readiness_brief"
    assert brief["persona_surface"]["role_count"] == 13
    assert brief["blockers"]
    assert brief["contract"]["product"]["name"] == "wallstreet-tieling"


def test_claude_code_variant_is_alpha_with_adapter_doc():
    data = _load_variants()
    variant = data["variants"]["claude_code"]

    assert variant["readiness"] == "alpha"
    assert "CLAUDE.md" in variant["entrypoints"]
    assert "docs/CLAUDE_CODE_ADAPTER.md" in variant["entrypoints"]
    assert "deploy/mcp-server.json" in variant["entrypoints"]
    assert any("host smoke" in item for item in variant["next_gate"])


def test_codex_variant_tracks_packaged_mcp_smoke_after_validator_pass():
    data = _load_variants()
    variant = data["variants"]["codex"]

    assert variant["readiness"] == "alpha"
    assert ".codex-plugin/plugin.json" in variant["entrypoints"]
    assert any("Codex CI workflow" in item for item in variant["next_gate"])
    assert not any(item == "Run official plugin validator" for item in variant["next_gate"])


def test_desktop_agent_variants_are_alpha_and_do_not_require_html_ui():
    data = _load_variants()

    for name in {"hermes", "doubao_office_task_mode", "open_claude_agents"}:
        variant = data["variants"][name]
        entrypoints = set(variant["entrypoints"])
        packaging = set(variant["packaging"])
        capabilities = " ".join(variant["required_capabilities"])

        assert variant["readiness"] == "alpha"
        assert "SKILL.md" in entrypoints
        assert {"bin/cli.js", "deploy/mcp-server.json", "docs/API_CONTRACTS.md"} & entrypoints
        assert {"CLI tool", "MCP server", "MCP deployment manifest", "REST API"} & packaging
        assert "HTML" not in capabilities or "No dependency on polished HTML UI" in capabilities


def test_current_release_contract_is_agent_first_not_polished_html():
    data = _load_variants()
    universal = data["variants"]["universal"]

    assert "index.html" not in universal["entrypoints"]
    assert not any("static web workbench" in item for item in universal["packaging"])
    assert any("Desktop-agent first" in item for item in data["product"]["signature_features"])
    assert any("polished HTML" in item for item in data["product"]["signature_features"])
    assert any("Desktop-agent entrypoints" in item for item in data["release_gates"]["quality"])


def test_package_scripts_and_mcp_manifest_stay_aligned():
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MCP_MANIFEST_PATH.read_text(encoding="utf-8"))

    scripts = package["scripts"]
    assert scripts["mcp"] == "node lib/mcp-server.js"
    assert scripts["codex:mcp-smoke"] == "node tools/codex-mcp-smoke.js"
    assert scripts["agent:host-smoke"] == "node tools/agent-host-smoke.js"
    assert scripts["acceptance"] == "powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-acceptance.ps1"
    assert "tools/codex-mcp-smoke.js" in package["files"]
    assert "tools/agent-host-smoke.js" in package["files"]
    assert "tools/run-acceptance.ps1" in package["files"]
    assert "tools/run-focused-tests.ps1" in package["files"]
    assert "tools/run-terminology-check.ps1" in package["files"]
    assert "CLAUDE.md" in package["files"]
    assert "docs/API_CONTRACTS.md" in package["files"]
    assert "docs/CLAUDE_CODE_ADAPTER.md" in package["files"]
    assert "docs/DESKTOP_AGENT_HOSTS.md" in package["files"]

    server = manifest["mcpServers"]["wallstreet-tieling"]
    assert server["command"] == "npx"
    assert server["args"] == ["-y", package["name"], "--mcp"]
    assert package["bin"]["wallstreet-tieling"] == "./bin/cli.js"

    referenced_tools = {
        match.group(1).replace("\\", "/")
        for command in scripts.values()
        for match in re.finditer(r"(tools[/\\][^\s|&;]+)", str(command))
    }
    for tool in referenced_tools:
        assert (PROJECT_ROOT / tool).is_file(), tool
        assert tool in package["files"], tool

    manifest_tools = {tool["name"] for tool in manifest["tools"]}
    assert {
        "investigate_company",
        "connector_catalog",
        "release_readiness",
        "development_requirements",
        "aggregate_subject",
    } <= manifest_tools
    investigate_tool = next(tool for tool in manifest["tools"] if tool["name"] == "investigate_company")
    aggregate_tool = next(tool for tool in manifest["tools"] if tool["name"] == "aggregate_subject")
    connector_tool = next(tool for tool in manifest["tools"] if tool["name"] == "connector_catalog")
    assert "quality gate" in investigate_tool["description"]
    assert "one_click_readiness" in investigate_tool["description"]
    assert "report_exports" in investigate_tool["description"]
    assert "relationship graph auditability" in investigate_tool["description"]
    assert aggregate_tool["inputSchema"]["required"] == ["subject_id"]
    assert "max_depth" in aggregate_tool["inputSchema"]["properties"]
    assert "admission" in connector_tool["description"]
    assert "query_timeout_seconds" in investigate_tool["inputSchema"]["properties"]
    assert investigate_tool["inputSchema"]["properties"]["retrieval_concurrency"]["maximum"] == 20
    assert investigate_tool["inputSchema"]["properties"]["fanout_rounds"]["maximum"] == 3
    assert investigate_tool["inputSchema"]["properties"]["max_fanout_tasks"]["maximum"] == 80
    assert investigate_tool["inputSchema"]["properties"]["query_timeout_seconds"]["maximum"] == 120

    server_text = (PROJECT_ROOT / "lib" / "mcp-server.js").read_text(encoding="utf-8")
    server_tool_names = set(re.findall(r"name: '([^']+)'", server_text))
    assert manifest_tools <= server_tool_names
