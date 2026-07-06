#!/usr/bin/env python3
"""Encoding guardrails for public Chinese product and retrieval copy."""
from __future__ import annotations

from pathlib import Path

from core.intelligence_retrieval import InvestigativeRetrievalPlanner, RetrievalDomain
from core.subject_profile import SubjectProfileBuilder, SubjectProfileDimension


def test_public_copy_and_core_sources_do_not_contain_replacement_characters() -> None:
    paths = [
        Path("README.md"),
        Path("index.html"),
        Path("package.json"),
        Path("deploy/mcp-server.json"),
        Path("bin/cli.js"),
        Path("bin/investigate.py"),
        Path("lib/mcp-server.js"),
        Path("tools/codex-mcp-smoke.js"),
        Path("tools/agent-host-smoke.js"),
        Path("CLAUDE.md"),
        Path("docs/CLAUDE_CODE_ADAPTER.md"),
        Path("docs/DESKTOP_AGENT_HOSTS.md"),
        Path("core/investigation.py"),
        Path("core/intelligence_retrieval.py"),
        Path("core/subject_profile.py"),
        Path("core/development_requirements.py"),
        Path("tests/unit/test_intelligence_retrieval.py"),
        Path("tests/unit/test_subject_profile.py"),
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "\ufffd" not in text
        assert "????" not in text


def test_retrieval_plan_keeps_real_chinese_search_terms() -> None:
    plan = InvestigativeRetrievalPlanner().build_company_plan("测试科技有限公司")
    queries = "\n".join(task.query for task in plan.tasks)

    assert "实际控制人" in queries
    assert "裁判文书" in queries
    assert "行政处罚" in queries
    assert "不动产抵押" in queries
    assert "软件著作权" in queries
    assert any(
        "微信公众号" in task.query and task.domain is RetrievalDomain.SOCIAL_WEB
        for task in plan.tasks
    )


def test_subject_profile_keyword_catalog_keeps_real_chinese_dimensions() -> None:
    keyword_catalog = {
        dimension.value: set(keywords)
        for dimension, keywords in SubjectProfileBuilder.TEXT_DIMENSIONS
    }

    assert "不动产" in keyword_catalog[SubjectProfileDimension.ASSET_SOLVENCY.value]
    assert "违章" in keyword_catalog[SubjectProfileDimension.BEHAVIORAL_RISK.value]
    assert "收货" in keyword_catalog[SubjectProfileDimension.LOCATION_ACTIVITY.value]
    assert "评价" in keyword_catalog[SubjectProfileDimension.CONSUMPTION_PREFERENCE.value]
    assert "公众号" in keyword_catalog[SubjectProfileDimension.PUBLIC_STATEMENTS.value]


def test_mcp_server_exposes_executable_investigation_tool() -> None:
    text = Path("lib/mcp-server.js").read_text(encoding="utf-8")

    assert "investigate_company" in text
    assert "connector_catalog" in text
    assert "release_readiness" in text
    assert "development_requirements" in text
    assert "retrieval_plan" in text
    assert "aggregate_subject" in text
    assert "investigate.py" in text
    assert "retrieval_plan.py" in text
    assert "export_dir" in text
    assert "source-resilience recovery step" in text
    assert "qyyjt_public_origin_handoff" in text
    assert "capital verification queue" in text
    assert "relationship graph audit queue" in text
    assert "acceptance_status_counts" in text


def test_static_workbench_exposes_report_exports() -> None:
    text = Path("index.html").read_text(encoding="utf-8")

    assert 'id="exportMarkdown"' in text
    assert 'id="exportJson"' in text
    assert 'id="exportHtml"' in text
    assert "function exportCurrent(format)" in text
    assert "function downloadText(filename, mimeType, content)" in text
    assert "text/markdown" in text
    assert "application/json" in text
    assert "text/html" in text
    assert "persona_surface" in text
    assert "13-role anthropomorphic shell" in text
    assert "function personaBriefItems(persona)" in text
    assert "function personaMarkdown(persona)" in text
    assert "专家团外壳" in text
    assert "本次激活角色" in text
    assert "case_investigation_lens" in text
    assert "function caseLensBriefItems(cognition)" in text
    assert "function caseLensMarkdown(cognition)" in text
    assert "扒光查案式调查" in text


def test_cli_help_mentions_catalog_and_release_commands() -> None:
    text = Path("bin/cli.js").read_text(encoding="utf-8")

    assert "--connectors" in text
    assert "--release" in text
    assert "--delivery-closure" in text
    assert "--requirements" in text
    assert "--aggregate-subject" in text
    assert "WST_PYTHON" in text
    assert "printPythonJson" in text


def test_claude_code_docs_reference_executable_mcp_and_catalogs() -> None:
    handoff = Path("CLAUDE.md").read_text(encoding="utf-8")
    root_skill = Path("SKILL.md").read_text(encoding="utf-8")
    codex_skill = Path("skills/wallstreet-tieling/SKILL.md").read_text(encoding="utf-8")
    adapter = Path("docs/CLAUDE_CODE_ADAPTER.md").read_text(encoding="utf-8")
    knowledge_pack = Path("docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md").read_text(encoding="utf-8")
    desktop_hosts = Path("docs/DESKTOP_AGENT_HOSTS.md").read_text(encoding="utf-8")
    mcp_config = Path("deploy/mcp-server.json").read_text(encoding="utf-8")

    for text in (handoff, adapter, knowledge_pack):
        assert "--connectors" in text
        assert "--release" in text
    for text in (handoff, root_skill, codex_skill, knowledge_pack):
        assert "--agent-tools" in text
        assert "agent_tool_adapters" in text
        assert "release_readiness" in text
        assert "connector_catalog" in text
        assert "development_requirements" in text
        assert "investigate_company" in text
    for text in (handoff, adapter):
        assert "--mcp" in text
    for text in (adapter, desktop_hosts):
        assert "qyyjt_public_origin_handoff" in text
        assert "source_resilience_recommended_step" in text
        assert "capital_verification_queue_count" in text
        assert "relationship_graph_audit_queue_count" in text
        assert "print_package" in text
    assert "docs/CLAUDE_PROJECT_KNOWLEDGE_PACK.md" in adapter
    assert "enterprise_cognition.control_ownership.controller_conflict_summary" in knowledge_pack
    assert "tools/api-smoke.py" in knowledge_pack
    assert "--export-docx" in adapter
    assert "--export-html" in adapter
    assert "--export-dir" in adapter
    assert "wallstreet-tieling" in mcp_config
    assert "connector_catalog" in mcp_config
    assert "release_readiness" in mcp_config
    assert "development_requirements" in mcp_config
    assert "retrieval_plan" in mcp_config
    assert "aggregate_subject" in mcp_config


def test_codex_market_readiness_mentions_runtime_tools() -> None:
    text = Path("docs/PLUGIN_MARKET_READINESS.md").read_text(encoding="utf-8")
    plugin = Path(".codex-plugin/plugin.json").read_text(encoding="utf-8")

    assert "connector_catalog" in text
    assert "release_readiness" in text
    assert "development_requirements" in Path("tools/codex-mcp-smoke.js").read_text(encoding="utf-8")
    smoke_text = Path("tools/codex-mcp-smoke.js").read_text(encoding="utf-8")
    assert "client.listTools" in smoke_text
    assert "client.callTool" in smoke_text
    assert "mcp_request_response_contract" in smoke_text
    assert "mcp_report_output_paths" in smoke_text
    assert "relationship_evidence_backed_edge_count" in smoke_text
    assert "qyyjt_public_origin_handoff" in smoke_text
    assert "capital_verification_queue_count" in smoke_text
    assert "relationship_graph_audit_queue_count" in smoke_text
    assert "acceptance_status_counts" in smoke_text
    host_smoke_text = Path("tools/agent-host-smoke.js").read_text(encoding="utf-8")
    assert "open_claude_agents" in host_smoke_text
    assert "qyyjt_public_origin_handoff" in host_smoke_text
    assert "capital_verification_queue_count" in host_smoke_text
    assert "relationship_graph_audit_queue_count" in host_smoke_text
    assert "runtime_cli_renderer_available_via_export_docx" in host_smoke_text
    assert "operational_handoff_tables" in host_smoke_text
    assert "investigate_company" in text
    assert "Plugin validator: passed" in text
    assert "Packaged Codex MCP backing smoke" in text
    assert "REST API smoke" in text
    assert "baseline re-check" in plugin
    assert "continuous monitoring is later-version scope" in plugin


def test_api_contracts_match_runtime_handoff_surfaces() -> None:
    text = Path("docs/API_CONTRACTS.md").read_text(encoding="utf-8")
    hermes = Path("docs/HERMES_AGENT_SETUP.md").read_text(encoding="utf-8")
    office = Path("docs/OFFICE_TASK_MODE_HANDOFF.md").read_text(encoding="utf-8")
    open_agents = Path("docs/OPEN_AGENT_COMPATIBILITY.md").read_text(encoding="utf-8")

    assert "qyyjt_public_origin_handoff" in text
    assert "source_resilience_recommended_step" in text
    assert "capital_verification_queue_count" in text
    assert "relationship_graph_audit_queue_count" in text
    assert "print_package" in text
    assert "directory_bundle" in text
    assert "delivery_decision.remaining_variant_blocker_count" in text
    assert "delivery_decision.variant_next_gate_count" in text
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in text
    assert "qyyjt_public_origin_handoff.agent_autorun" in text
    assert "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun" in text
    assert "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun" in text
    assert "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun" in text
    assert "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun" in text
    assert "report_exports.directory_bundle.agent_handoff.report_artifact_autorun" in text
    assert "runtime_cli_renderer_available_via_export_docx" in text
    assert "native_word_tables" in text
    assert "operational_handoff_tables" in text
    assert "first-screen handoff cards" in text
    assert "bin/investigate.py" in text
    assert "--export-docx" in text
    assert "--export-html" in text
    assert "--export-dir" in text
    assert "p2_template_required_not_current_release_blocker" not in text
    assert "WST_MCP_TIMEOUT_MS" in hermes
    assert "WST_QUERY_TIMEOUT_SECONDS" in hermes
    assert "--agent-tools" in office
    assert "办公任务模式 Agent" in office
    assert "领导摘要" in office
    assert "证据与缺口" in office
    assert "交付文件" in office
    assert "鍏" not in office
    assert "浣" not in office
    assert "one_click_readiness.source_resilience_recommended_step" in office
    assert "report_exports.print_package.docx.renderer_capabilities" in office
    assert "WST_ACCEPTANCE_STATE_DIR" in open_agents
    assert "npx wallstreet-tieling --mcp" in open_agents
    assert "report_exports.directory_bundle.agent_handoff.delivery_decision" in open_agents
