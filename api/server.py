#!/usr/bin/env python3
"""华尔街驻铁岭办事处 API Server v0.5.0
一键启动: python api/server.py
Docker: docker run -p 8080:8080 wallstreet-tieling

v0.5.0 变更: 路由到 wst 编排引擎（统一质量门禁），移除独立 LLM 路径。
"""
import importlib
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("wst.server")

# ── 依赖检查 ──
MISSING_DEPS = []
for mod_name in ["flask", "flask_cors"]:
    try:
        importlib.import_module(mod_name)
    except ImportError:
        MISSING_DEPS.append(mod_name)

if MISSING_DEPS:
    print("=" * 60)
    print("  缺少依赖，请手动安装：")
    print(f"  pip install {' '.join(MISSING_DEPS)}")
    print("=" * 60)
    sys.exit(1)

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    __package__ = "api"

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ── 配置 ──
from . import config
from .orchestrator import Orchestrator
from core.datasource_fixtures import build_datasource_fixture_pack
from core.connector_registry import ConnectorRegistry
from core.agent_tool_adapters import build_agent_tool_adapter_manifest
from core.development_requirements import build_development_requirements_board
from core.investigation import build_investigation_packet
from core.release_contract import (
    delivery_audit_brief,
    objective_completion_audit_brief,
    release_preflight_brief,
    release_readiness_brief,
)
from api.personality import build_persona_surface_brief
from core.official_public_smoke import (
    build_official_public_smoke_config,
    build_official_public_smoke_plan,
)
from core.one_click_defaults import resolve_one_click_retrieval_async
from core.risk_discovery_pipeline import RiskDiscoveryPipeline, offline_enforcement_fixture
from core.risk_graph_export import export_risk_graph
from core.risk_monitor import RiskMonitor, RiskMonitorRunStore, default_monitor_run_store_path

config.reload_config()

app = Flask(__name__)
CORS_ORIGINS = os.environ.get("WALLSTREET_CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
CORS(app, origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()])
PORT = int(os.environ.get("PORT", 8080))

# ── API 认证 (P0 修复) ──
# 安全策略: 未配置 token → 强制 127.0.0.1; 已配置 → 0.0.0.0 + Bearer auth
AUTH_TOKEN = os.environ.get("WALLSTREET_AUTH_TOKEN", "")
BIND_HOST = "0.0.0.0" if AUTH_TOKEN else "127.0.0.1"

# 无需认证的公开端点
_PUBLIC_PATHS = {
    "/",
    "/api/docs",
    "/api/health",
    "/api/release",
    "/api/delivery-audit",
    "/api/objective-audit",
    "/api/connectors",
    "/api/requirements",
    "/api/agent-tools",
    "/api/office_chat",
}


@app.before_request
def check_auth():
    # 公开端点放行
    if request.path in _PUBLIC_PATHS or request.path.startswith("/api/health"):
        return
    # 未配置 token → 不拦截（此时已强制绑定 127.0.0.1）
    if not AUTH_TOKEN:
        return
    # Bearer token 校验
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        return jsonify({"error": "unauthorized", "hint": "设置 Authorization: Bearer <token>"}), 401


# ── 请求体大小限制 (P1) ──
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB


# ── 请求日志中间件 ──
@app.before_request
def log_request():
    logger.info("%s %s from %s", request.method, request.path,
                request.remote_addr)


@app.after_request
def log_response(response):
    logger.info("%s %s → %d", request.method, request.path,
                response.status_code)
    return response


# ── API 路由 ──

@app.route("/")
def index():
    return jsonify({
        "name": "华尔街驻铁岭办事处",
        "version": "v0.5.0",
        "description": "银行信贷情报专家团 API · 真并发Agent架构",
        "persona_surface": build_persona_surface_brief(),
        "endpoints": {
            "POST /api/analyze": "执行尽调分析 (通过编排引擎)",
            "POST /api/investigate": "一键调查包",
            "POST /api/aggregate": "主体聚合 follow-up，用于调查包识别出的关联主体、控制人或关系节点扩展",
            "POST /api/risk-graph": "执行风险发现并返回结构化图谱",
            "POST /api/monitor/run": "执行一次企业基线复查；连续监控属于后续版本",
            "GET /api/monitor/runs": "基线复查运行历史",
            "GET /api/monitor/source-health": "数据源健康趋势（基于显式复查运行）",
            "GET /api/connectors": "数据源目录与开箱能力",
            "GET /api/release": "发布版本与适配形态契约",
            "GET /api/delivery-audit": "桌面 agent alpha 交付总审计",
            "GET /api/objective-audit": "当前目标逐项完成度审计",
            "GET /api/requirements": "开发需求等级、当前完成度、P0/P1/P2/Future范围",
            "GET /api/agent-tools": "各桌面Agent工具适配清单",
            "GET /api/health": "健康检查",
            "GET /api/skill": "获取完整SKILL.md",
            "GET /api/docs": "API文档",
        },
        "setup": "设置 DEEPSEEK_API_KEY 环境变量后启动",
    })


@app.route("/api/health")
def health():
    has_key = bool(config.get_api_key())
    release = release_readiness_brief()
    contract_summary = release.get("contract", {}).get("summary", {})
    stable_or_beta_count = contract_summary.get("stable_or_beta_count", 0)
    blocker_count = len(release.get("blockers", []))
    readiness_status = "ready" if stable_or_beta_count and blocker_count == 0 else "not_release_ready"
    delivery_decision = release.get("delivery_decision", {})
    return jsonify({
        "status": "ok" if has_key else "missing_api_key",
        "model": config.DEFAULT_MODEL,
        "version": release.get("version", "0.5.0"),
        "time": time.time(),
        "checks": {
            "server": "running",
            "dd_version": release.get("version", "0.5.0"),
            "release_readiness": readiness_status,
            "desktop_agent_delivery": delivery_decision.get("status", "unknown"),
            "desktop_agent_release_candidate": bool(delivery_decision.get("desktop_agent_release_candidate")),
            "full_product_status": delivery_decision.get("full_product_status", "not_final_release_ready"),
            "readyish_variant_count": stable_or_beta_count,
            "blocker_count": blocker_count,
            "evidence_pipeline": "runtime_gated",
            "smoke_status": {
                "public_sources": "fixture_only",
                "authorized_sources": "fixture_only",
                "note": "Health does not certify live data. Use /api/release and source smoke checks for readiness.",
            },
        },
    })


@app.route("/api/skill")
def get_skill():
    skill_path = config.SKILL_DIR / "SKILL.md"
    if not skill_path.exists():
        return jsonify({"error": "SKILL.md not found"}), 404
    fmt = request.args.get("format", "text")
    content = skill_path.read_text(encoding="utf-8")
    if fmt == "json":
        return jsonify({"skill": content, "length": len(content)})
    return Response(content, mimetype="text/markdown; charset=utf-8")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """v0.5.0: 路由到 wst 编排引擎（完整 3-Phase + 质量门禁）"""
    data = request.get_json() or {}
    target = data.get("company", data.get("message", data.get("name", "")))
    if not target:
        return jsonify({"error": "缺少 company/message/name 参数"}), 400

    mode = data.get("depth", data.get("mode", "standard"))
    if mode not in config.MODE_TEMPLATES:
        mode = "standard"

    # 异步调用编排引擎
    try:
        concurrency = min(int(data.get("concurrency", 5)), 20)   # P0 硬上限
        max_retries = min(int(data.get("max_retries", 3)), 5)    # P0 硬上限
    except (ValueError, TypeError):
        concurrency = 5
        max_retries = 3

    try:
        orch = Orchestrator(
            target=target,
            model=data.get("model"),
            mode=mode,
            concurrency=concurrency,
            max_retries=max_retries,
        )
        # 使用 new_event_loop 避免 "Event loop is already running" 在 WSGI 多线程环境下的冲突
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orch.orchestrate())
        finally:
            loop.close()
        return jsonify({
            "task_type": "due_diligence",
            "report": result["report"],
            "model": orch.model,
            "mode": mode,
            "roles_activated": result["roles_activated"],
            "branches_triggered": result["branches_triggered"],
        })
    except RuntimeError as e:
        logger.exception("Orchestration failed: %s", e)
        return jsonify({"error": "编排失败，请检查日志获取详情"}), 500
    except Exception as e:
        logger.exception("Orchestration failed")
        return jsonify({"error": "编排失败，请检查日志获取详情"}), 500


def _clamped_int(data: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(data.get(key, default)), high))
    except (ValueError, TypeError):
        return default


def _clamped_float(data: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(float(data.get(key, default)), high))
    except (ValueError, TypeError):
        return default


def _risk_graph_target(data: dict[str, Any], *, allow_message: bool = False) -> str:
    target = data.get("company", data.get("name", ""))
    if not target and allow_message:
        target = data.get("message", "")
    return str(target or "").strip()


async def _build_risk_graph_payload(data: dict[str, Any], *, allow_message: bool = False) -> dict[str, Any]:
    target = _risk_graph_target(data, allow_message=allow_message)
    offline_fixture = bool(data.get("offline_fixture", False))
    fixture_pack = bool(data.get("fixture_pack", False))
    official_public_smoke = bool(data.get("official_public_smoke", False))
    datasource_config = str(data.get("config", "") or "")
    mode_count = sum(bool(item) for item in (datasource_config, offline_fixture, fixture_pack, official_public_smoke))
    if mode_count > 1:
        raise ValueError("config, offline_fixture, fixture_pack, official_public_smoke are mutually exclusive")
    retrieval_concurrency = _clamped_int(data, "retrieval_concurrency", 4, 1, 20)
    query_timeout_seconds = _clamped_float(data, "query_timeout_seconds", 20.0, 0.1, 120.0)
    fanout_rounds = _clamped_int(data, "fanout_rounds", 1, 0, 3)
    max_fanout_tasks = _clamped_int(data, "max_fanout_tasks", 24, 0, 80)

    records = None
    if fixture_pack:
        records = build_datasource_fixture_pack(target).all_records()
    elif offline_fixture:
        records = offline_enforcement_fixture(target)
    search_engine = None
    existing_plan = None
    if official_public_smoke:
        datasource_config = str(build_official_public_smoke_config())
        existing_plan = build_official_public_smoke_plan(target)
    if datasource_config:
        from adapters.multi_datasource import SearchEngine

        await SearchEngine.initialize(datasource_config)
        search_engine = SearchEngine
    selected = await resolve_one_click_retrieval_async(
        company=target,
        records=records,
        search_engine=search_engine,
        existing_plan=existing_plan,
        fanout_rounds=1 if official_public_smoke else fanout_rounds,
        default_enabled=bool(data.get("default_public_one_click", True)),
    )
    result = await RiskDiscoveryPipeline().run(
        target,
        records=selected.records,
        search_engine=selected.search_engine,
        store_path=data.get("store") or None,
        existing_plan=selected.existing_plan,
        retrieval_concurrency=retrieval_concurrency,
        fanout_rounds=selected.fanout_rounds,
        max_fanout_tasks=max_fanout_tasks,
        identifier_fanout_only=official_public_smoke,
        query_timeout_seconds=query_timeout_seconds,
    )
    return export_risk_graph(result).to_dict()


def _run_async_payload(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _monitor_run_store_from_request() -> RiskMonitorRunStore:
    raw_path = request.args.get("run_store") or request.args.get("store") or ""
    path = Path(raw_path) if raw_path else default_monitor_run_store_path()
    return RiskMonitorRunStore(path)


def _request_limit(default: int = 20, high: int = 200) -> int:
    try:
        return max(1, min(int(request.args.get("limit", default)), high))
    except (ValueError, TypeError):
        return default


def _monitor_companies_from_payload(data: dict[str, Any]) -> list[str]:
    raw_companies = data.get("companies")
    values: list[Any] = []
    if isinstance(raw_companies, list):
        values.extend(raw_companies)
    elif raw_companies:
        values.append(raw_companies)
    for key in ("company", "name", "message"):
        if data.get(key):
            values.append(data[key])

    seen: set[str] = set()
    companies: list[str] = []
    for item in values:
        value = " ".join(str(item or "").split())
        if not value or value in seen:
            continue
        seen.add(value)
        companies.append(value)
    return companies


async def _run_monitor_payload(data: dict[str, Any]) -> dict[str, Any]:
    companies = _monitor_companies_from_payload(data)
    if not companies:
        raise ValueError("missing companies")

    offline_fixture = bool(data.get("offline_fixture", False))
    fixture_pack = bool(data.get("fixture_pack", False))
    datasource_config = str(data.get("config", "") or "")
    mode_count = sum(bool(item) for item in (datasource_config, offline_fixture, fixture_pack))
    if mode_count > 1:
        raise ValueError("config, offline_fixture, and fixture_pack are mutually exclusive")

    search_engine = None
    if datasource_config:
        from adapters.multi_datasource import SearchEngine

        await SearchEngine.initialize(datasource_config)
        search_engine = SearchEngine
    elif not offline_fixture and not fixture_pack and bool(data.get("default_public_one_click", True)):
        from core.one_click_defaults import build_default_one_click_search_engine

        search_engine = await build_default_one_click_search_engine()

    records_by_company = None
    if offline_fixture:
        records_by_company = {
            company: offline_enforcement_fixture(company)
            for company in companies
        }
    elif fixture_pack:
        records_by_company = {
            company: build_datasource_fixture_pack(company).all_records()
            for company in companies
        }

    monitor = RiskMonitor(
        risk_event_store=data.get("store") or None,
        monitor_run_store=data.get("run_store") or default_monitor_run_store_path(),
    )
    run = await monitor.run_once(
        companies,
        search_engine=search_engine,
        records_by_company=records_by_company,
        retrieval_concurrency=_clamped_int(data, "retrieval_concurrency", 4, 1, 20),
        query_timeout_seconds=_clamped_float(data, "query_timeout_seconds", 20.0, 0.1, 120.0),
    )
    return run.to_dict()


@app.route("/api/risk-graph", methods=["POST"])
def risk_graph():
    """Return graph/timeline output for plugin and UI consumers."""
    data = request.get_json() or {}
    target = _risk_graph_target(data)
    if not target:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "缺少 company/name 参数",
            }
        }), 400

    offline_fixture = bool(data.get("offline_fixture", False))
    fixture_pack = bool(data.get("fixture_pack", False))
    official_public_smoke = bool(data.get("official_public_smoke", False))
    datasource_config = str(data.get("config", "") or "")
    mode_count = sum(bool(item) for item in (datasource_config, offline_fixture, fixture_pack, official_public_smoke))
    if mode_count > 1:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "config, offline_fixture, fixture_pack, official_public_smoke 不能同时使用",
            }
        }), 422

    try:
        payload = _run_async_payload(_build_risk_graph_payload(data))
        return jsonify({"data": payload})
    except Exception:
        logger.exception("Risk graph export failed")
        return jsonify({
            "error": {
                "code": "risk_graph_failed",
                "message": "风险图谱生成失败，请检查日志获取详情",
            }
        }), 500


@app.route("/api/investigate", methods=["POST"])
def investigate():
    """One-click investigation packet for non-technical users and Codex plugins."""
    data = request.get_json() or {}
    target = _risk_graph_target(data, allow_message=True)
    if not target:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "缺少 company/name/message 参数",
            }
        }), 400

    offline_fixture = bool(data.get("offline_fixture", False))
    fixture_pack = bool(data.get("fixture_pack", False))
    official_public_smoke = bool(data.get("official_public_smoke", False))
    datasource_config = str(data.get("config", "") or "")
    mode_count = sum(bool(item) for item in (datasource_config, offline_fixture, fixture_pack, official_public_smoke))
    if mode_count > 1:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "config, offline_fixture, fixture_pack, official_public_smoke 不能同时使用",
            }
        }), 422

    try:
        graph_payload = _run_async_payload(
            _build_risk_graph_payload(data, allow_message=True)
        )
        packet = build_investigation_packet(
            graph_payload,
            input_text=target,
            mode=data.get("mode", data.get("depth", "standard")),
        )
        return jsonify({"data": packet.to_dict()})
    except Exception:
        logger.exception("One-click investigation failed")
        return jsonify({
            "error": {
                "code": "investigation_failed",
                "message": "一键调查失败，请检查日志获取详情",
            }
        }), 500




@app.route("/api/aggregate", methods=["POST"])
def api_aggregate():
    """SubjectProfileAggregator endpoint — aggregate subject profile from 6 data sources."""
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    subject_id = str(data.get("subject_id") or data.get("company") or "").strip()
    subject_name = str(data.get("subject_name") or data.get("company_name") or subject_id).strip()
    max_depth = min(int(data.get("max_depth", 3)), 5)

    if not subject_id:
        return jsonify({"error": "subject_id is required"}), 400

    try:
        import asyncio
        from core.investigation import run_subject_profile_aggregation
        report = asyncio.run(run_subject_profile_aggregation(subject_id, subject_name, max_depth=max_depth))
        return jsonify(report), 200
    except Exception as exc:
        return jsonify({"error": str(exc), "subject_id": subject_id}), 500

@app.route("/api/monitor/run", methods=["POST"])
def monitor_run():
    """Run one monitoring pass and persist the monitor-run ledger."""
    data = request.get_json() or {}
    companies = _monitor_companies_from_payload(data)
    if not companies:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "缺少 company/name/message/companies 参数",
            }
        }), 400

    offline_fixture = bool(data.get("offline_fixture", False))
    fixture_pack = bool(data.get("fixture_pack", False))
    datasource_config = str(data.get("config", "") or "")
    mode_count = sum(bool(item) for item in (datasource_config, offline_fixture, fixture_pack))
    if mode_count > 1:
        return jsonify({
            "error": {
                "code": "validation_error",
                "message": "config, offline_fixture, fixture_pack 不能同时使用",
            }
        }), 422

    try:
        payload = _run_async_payload(_run_monitor_payload(data))
        return jsonify({"data": payload})
    except Exception:
        logger.exception("Monitor run failed")
        return jsonify({
            "error": {
                "code": "monitor_run_failed",
                "message": "监控扫描失败，请检查日志获取详情",
            }
        }), 500


@app.route("/api/monitor/runs")
def monitor_runs():
    """Return persisted monitoring run history for UI and plugin surfaces."""
    store = _monitor_run_store_from_request()
    company = request.args.get("company") or None
    rows = store.list_runs(company=company)
    limit = _request_limit()
    return jsonify({
        "data": {
            "run_store": str(store.path),
            "company_filter": company,
            "run_count": len(rows),
            "runs": rows[-limit:][::-1],
        }
    })


@app.route("/api/monitor/source-health")
def monitor_source_health():
    """Return datasource health trends from persisted monitoring runs."""
    store = _monitor_run_store_from_request()
    company = request.args.get("company") or None
    return jsonify({
        "data": {
            "run_store": str(store.path),
            "company_filter": company,
            "source_health": store.source_health_trends(company=company),
        }
    })


@app.route("/api/connectors")
def connectors():
    """Return datasource catalog and readiness metadata for UI/plugin consumers."""
    registry = ConnectorRegistry()
    return jsonify({"data": registry.product_catalog()})


@app.route("/api/release")
def release_contract():
    """Return release variants and marketplace gates as runtime metadata."""
    return jsonify({"data": release_readiness_brief()})


@app.route("/api/release-preflight")
def release_preflight():
    """Return desktop-agent alpha local packaging go/no-go preflight."""
    return jsonify({"data": release_preflight_brief()})


@app.route("/api/delivery-audit")
def delivery_audit():
    """Return the single desktop-agent alpha delivery audit."""
    return jsonify({"data": delivery_audit_brief()})


@app.route("/api/objective-audit")
def objective_audit():
    """Return requirement-by-requirement completion for the active objective."""
    return jsonify({"data": objective_completion_audit_brief()})


@app.route("/api/office_chat")
def office_chat_api():
    from core.office_chat import build_office_chat_packet
    from dataclasses import asdict
    company = request.args.get("company", "Demo Company")
    try:
        ec = {}; pb = {}
        packet = build_office_chat_packet(company, ec, pb)
        msgs = [{"role_id": m.role_id, "text": m.text, "msg_type": m.msg_type, "evidence_refs": m.evidence_refs, "timestamp": m.timestamp} for m in packet.messages]
        return jsonify({"data": {"type": "office_chat", "messages": msgs}})
    except Exception as e:
        return jsonify({"data": {"type": "office_chat", "error": str(e)}})


@app.route("/api/requirements")
def requirements_board():
    """Return executable development priority levels and current release scope."""
    return jsonify({"data": build_development_requirements_board()})


@app.route("/api/agent-tools")
def agent_tool_adapters():
    """Return host-specific desktop-agent tool sequences and fallbacks."""
    return jsonify({"data": build_agent_tool_adapter_manifest()})


@app.route("/api/docs")
def docs():
    return jsonify({
        "quickstart": {
            "curl": """curl -X POST http://localhost:8080/api/analyze \\
  -H "Content-Type: application/json" \\
  -d '{"company":"ABC公司","depth":"standard"}'""",
        },
        "types": ["due_diligence"],
        "modes": list(config.MODE_TEMPLATES.keys()),
        "formats": ["json"],
        "endpoints": {
            "POST /api/analyze": "report-oriented due diligence orchestration",
            "POST /api/investigate": "one-click investigation packet for non-technical users and plugins",
            "POST /api/aggregate": "bounded subject aggregation follow-up for related companies, controllers, or relationship nodes identified by an investigation packet",
            "POST /api/risk-graph": "structured graph/timeline risk discovery output",
            "POST /api/monitor/run": "run one explicit baseline re-check and persist run history; continuous monitoring is later-version scope",
            "GET /api/monitor/runs": "persisted baseline re-check history for UI and plugins",
            "GET /api/monitor/source-health": "datasource health trend summary from explicit baseline re-check history",
            "GET /api/connectors": "datasource catalog, default-enabled sources, production readiness, and policy",
            "GET /api/release": "desktop-agent release variant contract for Universal, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude/open-source agents, and WorkBuddy",
            "GET /api/release-preflight": "desktop-agent alpha package go/no-go preflight, final submission blockers, and package privacy review checklist",
            "GET /api/delivery-audit": "single machine-readable desktop-agent alpha delivery audit with checks, coverage, blockers, and safe claim",
            "GET /api/requirements": "P0/P1/P2/Future development requirement board and current-release completion",
            "GET /api/agent-tools": "machine-readable per-host desktop-agent tool adapter manifest, baseline tool sequence, fallbacks, smoke commands, and packet fields",
        },
        "catalog_contract": {
            "persona_surface": "data.persona_surface: 13-role anthropomorphic shell contract with groupings, roster, signature features, and routing principles",
            "data.persona_surface": "13-role anthropomorphic shell contract shared by release, API, CLI, MCP, and UI surfaces",
            "connectors": {
                "response": {
                    "data.summary.zero_config_ready": "public production-ready connectors enabled for default one-click runs",
                    "data.groups.default_enabled": "connectors enabled out of the box",
                    "data.groups.needs_admission": "connectors that require implementation, validation, or admission work",
                    "data.summary.data_effectiveness": "source counts by fact-capable, lead-capable, default fact-capable, admission mode, and analysis-output coverage",
                    "data.summary.admission_gate_summary": "default-on fact/lead source admission gates, gate counts, and reliance policy",
                    "data.data_effectiveness[]": "per-connector matrix showing whether the source can feed report facts, report leads, what analysis outputs it supports, and which limitations remain",
                    "data.qyyjt_benchmark.summary.surface_profile": "QYYJT module counts split into concrete API, rich query-plan, and generic fallback lanes, with the current matrix showing 4 API/legacy, 41 query-plan, and 0 generic fallback modules",
                    "data.qyyjt_benchmark.summary.surface_profile.concrete_api_or_legacy_module_names": "the four concrete API/legacy module names: search_multi, bond_profile, region_code, and region_economy",
                    "data.qyyjt_benchmark.summary.surface_profile.rich_query_plan_module_names": "the 41 module names that currently resolve to rich query-plan leads",
                    "data.qyyjt_benchmark.summary.surface_profile.generic_fallback_module_names": "modules that still fall back to generic fallback; currently empty",
                    "data.qyyjt_benchmark.summary.authorization_profile": "QYYJT authorization boundary split into auth-required legacy/API modules and public-search-only modules",
                    "data.qyyjt_benchmark.summary.unsupported_profile": "QYYJT unsupported or unknown semantics split; currently empty because every module has an explicit lane",
                    "data.qyyjt_benchmark.summary.surface_lanes": "QYYJT module delivery lanes visible to users and operators",
                    "data.qyyjt_benchmark.summary.p0_queue": "operator-facing current-version P0 work queue sorted by subject-resolution and report-critical priority",
                    "data.qyyjt_benchmark.summary.work_items": "all 45 QYYJT modules as actionable work items with done_when and next_action fields",
                    "data.qyyjt_benchmark.summary.field_contracts": "all 45 QYYJT module field contracts with required fields, report section, and report admission gate",
                    "data.qyyjt_benchmark.summary.public_origin_plans": "lawful public-origin fallback channels and query families to use when authorized aggregator access is unavailable",
                    "data.qyyjt_benchmark.summary.public_origin_execution_queue": "agent-ready public-origin actions combining module, priority, origin channels, query families, required fields, record type, admission gate, and done condition",
                    "data.qyyjt_benchmark.summary.public_origin_execution_summary": "agent-ready public-origin execution summary with queue count, P0 count, target lane counts, origin channel counts, top action, next batch, and field-contract gaps",
                    "data.qyyjt_benchmark.summary.public_origin_execution_summary.report_section_batches": "agent-ready public-origin batches grouped by report section with queue count, P0 count, record types, top actions, and section-level done condition",
                    "data.qyyjt_benchmark.rows[]": "Per-module QYYJT coverage rows with user-visible status, evidence role, report admissibility, admission gate, parity priority, acceptance gate, authorization mode, next action, field contract, and operator work item",
                    "data.policy": "plain-language public-release source policy",
                }
            },
            "investigate": {
                "response": {
                "data.monitoring_seed.recovery_execution_queue": "ready recovery work orders plus blocked preview rows derived from coverage gaps",
                "data.monitoring_seed.recovery_execution_summary": "small JSON summary of recovery readiness with queued count, blocked count, top blocker, and handoff policy",
                "data.monitoring_seed.relationship_candidate_execution_plan": "relationship-candidate verification and expansion work orders",
                "data.monitoring_seed.source_repair_priority_queue": "operator-ready source repair priorities derived from recurring source/category/domain failures",
            }
            },
            "release": {
                "response": {
                    "data.contract.product": "product positioning and shared core modules",
                    "data.contract.variants": "Universal/Codex/Claude Code/Hermes/Doubao Office Task Mode/OpenClaude/open-source agents/WorkBuddy packaging contract",
                    "data.runtime_delivery": "current executable delivery surfaces with entrypoints and focused proof tests for investigation packet, QYYJT public-origin queue, capital graph, DOCX, Markdown/JSON/HTML exports, and Node offline export-dir fallback",
                    "data.latest_acceptance_evidence": "latest full local npm run acceptance evidence with timestamp, passed/skipped Python test counts, smoke status, default one-click result, and covered runtime surfaces",
                    "data.delivery_decision": "desktop-agent alpha delivery decision separated from final-product readiness, so agents can distinguish current host delivery from later polished HTML/app targets",
                    "data.delivery_decision.desktop_agent_release_candidate": "true when current runtime delivery surfaces have no blocking proof gaps for desktop-agent alpha delivery",
                    "data.delivery_decision.full_product_status": "final product launch readiness remains separate from desktop-agent alpha delivery",
                    "data.delivery_decision.remaining_variant_blocker_count": "runtime blocking variant count for desktop-agent alpha delivery; zero when next_gate rows are follow-up tasks only",
                    "data.delivery_decision.variant_next_gate_count": "count of variant follow-up gates such as screenshots, host approval, or stronger-claim tasks that do not block alpha delivery",
                    "data.release_preflight": "desktop-agent alpha local packaging go/no-go preflight with final submission blockers and package privacy review checklist",
                    "data.blockers": "variant gates still required before stronger release claims",
                }
            },
            "release_preflight": {
                "response": {
                    "data.status": "ready_for_local_packaging when local alpha package gates are satisfied, otherwise blocked",
                    "data.package_candidate_ready": "true when current release decision, acceptance evidence, preserved fields, and dry-run gate are aligned",
                    "data.final_submission_ready": "false until screenshots, clean branch publishing, and external approval items are done",
                    "data.final_submission_blockers": "operator-facing remaining submission artifacts such as screenshots and clean reviewed branch publication",
                    "data.packaging_review": "dry-run and privacy-review commands plus do-not-package rules for secrets and runtime artifacts",
                    "data.agent_handoff.safe_claim": "safe public claim for desktop-agent alpha hosts",
                }
            },
            "requirements": {
                "response": {
                    "data.completion_percent": "weighted current-release completion across P0/P1/P2 items",
                    "data.delivery_decision": "desktop-agent alpha delivery decision for the executable requirements board, separate from final-product launch readiness",
                    "data.delivery_decision.desktop_agent_release_candidate": "true when the current requirements board is strong enough for desktop-agent alpha delivery",
                    "data.delivery_decision.full_product_status": "full product launch readiness remains not-final until later report/UI/hosted-operation targets close",
                    "data.level_policy": "P0/P1/P2/Future priority definitions",
                    "data.scope_rules.continuous_monitoring": "future-version boundary for continuous monitoring",
                    "data.qyyjt_current_version": "QYYJT module parity snapshot tied to current-release requirement id",
                    "data.next_focus": "ordered executable next actions, excluding future-version parked items",
                }
            },
            "agent_tools": {
                "response": {
                    "data.type": "agent_tool_adapter_manifest",
                    "data.host_ids": "all current desktop-agent host ids from release/variants.yaml",
                    "data.shared_tools": "baseline tool contracts for release_readiness, connector_catalog, development_requirements, investigate_company, and aggregate_subject",
                    "data.execution_matrix": "phase-by-phase desktop-agent run matrix with tool, done_condition, required_fields, failure_routing, and optional follow-up markers",
                    "data.first_run_recipe": "compact first-run sequence, preservation fields, verification commands, and do-not rules for hosts that only consume one manifest field",
                    "data.adapter_lookup": "compact host_id keyed lookup for low-context hosts that need fallback_order, smoke_command, tool_sequence, execution_matrix_ref, and required_packet_field_count without iterating adapters[]",
                    "data.default_host_id": "universal fallback host id for unknown desktop-agent shells",
                    "data.adapters[]": "per-host primary mode, fallback order, required packet fields, smoke command, and operator prompt",
                    "data.minimum_pass_gates": "release-facing gates every desktop-agent host must preserve before formatting output",
                    "data.policy": "desktop-agent alpha scope boundary; polished HTML and app surfaces remain later-version targets",
                }
            },
            "aggregate": {
                "request": {
                    "subject_id": "required subject identifier from an investigation packet, such as company:demo-related",
                    "subject_name": "optional display name for report labels; defaults to subject_id",
                    "max_depth": "optional bounded association depth, clamped to 1..5",
                },
                "response": {
                    "subject": "stable Agent-facing subject object with id, name, and identity",
                    "relationship_graph": "stable Agent-facing relationship graph alias; legacy relation_graph may also be present",
                    "profile": "stable Agent-facing profile alias containing identity, contacts, addresses, related_entities, social_relations, travel_records, and consumption_records",
                    "adapter_summary": "source count, failed sources, empty sources, and cache-hit count for coverage diagnostics",
                    "policy": "Use as a follow-up expansion tool only after the main investigation packet identifies a target; empty output is a coverage gap, not a clean finding.",
                },
            },
        },
        "monitor_run_contract": {
            "request": {
                "company/name/message": "single company string",
                "companies": "optional array for batch monitoring",
                "store": "optional risk-event JSONL ledger path",
                "run_store": "optional monitor-run JSONL ledger path",
                "config": "optional datasource YAML path",
                "offline_fixture": "optional deterministic local records",
                "fixture_pack": "optional multi-source fixture records",
                "retrieval_concurrency": "optional int, clamped to 1..20",
                "query_timeout_seconds": "optional float, clamped to 0.1..120.0 per retrieval task",
            },
            "response": {
                "data.run_id": "monitor run id",
                "data.results": "one row per monitored company with delta and retrieval summary",
                "data.alerts": "latest high-priority open alerts from the risk-event store",
            },
        },
        "monitor_contract": {
            "request": {
                "run_store": "optional JSONL monitor-run ledger path",
                "company": "optional company filter",
                "limit": "optional history row limit, clamped to 1..200",
            },
            "response": {
                "runs": "newest persisted monitor runs first",
                "source_health": "per-source observed_count, ok_count, down_count, availability ratio, latest status",
                "source_health.connector_recovery_queue": "ranked recovery queue derived from persisted source-health trends, with priority, status, failure category, availability ratio, operator action, and done condition",
                "source_health.release_readiness_warnings": "release-facing warnings generated from degraded or blocked source-health trends",
            },
        },
        "investigate_contract": {
            "request": {
                "company/name/message": "required string, accepts natural one-line input",
                "config": "optional datasource YAML path for live routing",
                "offline_fixture": "optional bool for deterministic local smoke tests",
                "fixture_pack": "optional bool for multi-source connector demo records",
                "query_timeout_seconds": "optional float, clamped to 0.1..120.0 per retrieval task",
                "mode/depth": "optional product mode label",
            },
            "response": {
                "data.type": "investigation_packet",
                "data.risk_brief": "plain-language verdict, score, severity counts, key findings",
                "data.profile_brief": "controller candidates, profile coverage, evidence gaps",
                "data.graph.diagnostics.subject_profile.controller_candidates.source_family_summary": "subject-profile controller/UBO candidate source-family provenance across official, licensed, knowledge-graph, and public source families; provenance only, not fact promotion",
                "data.graph.diagnostics.subject_profile.controller_candidates.control_path_summaries.source_family_summary": "multi-hop controller/UBO control-path source-family provenance, including upstream ownership layers as well as terminal person evidence",
                "data.graph.diagnostics.subject_profile.relationship_graph.edges.source_family_summary": "relationship-edge source-family provenance for subject-profile graph edges before report-level aggregation",
                "data.enterprise_cognition.control_ownership.controller_candidates.source_family_summary": "report-facing controller/UBO candidate source-family provenance when subject-profile candidates are promoted into enterprise cognition",
                "data.enterprise_cognition.control_ownership.control_paths.source_family_summary": "report-facing control-path source-family provenance for indirect controller or UBO paths",
                "data.enterprise_cognition": "strategy-level risk hypotheses, watchlist, next questions, and evidence gaps",
                "data.quality_gate": "machine-readable delivery status, blockers, warnings, strengths, and next actions",
                "data.evidence_ledger": "compact source ledger with verification hints",
                "data.report_exports": "desktop-agent export bundle for Markdown, full JSON packet, portable printable HTML, print_package manifest, and CLI/runtime DOCX export; premium HTML remains P2",
                "data.report_exports.agent_decision_digest": "packet-level desktop-agent routing digest returned directly by REST/MCP investigation calls, with delivery status, clean-conclusion boundary, acceptance blockers, source resilience, queue counts, first action, and export-dir verification reminder",
                "data.report_exports.directory_bundle": "machine-readable report directory export contract with --export-dir entrypoint, manifest filename, expected written files including agent-handoff.json, stdout preservation, and Node CLI passthrough",
                "data.report_exports.directory_bundle.integrity_verifier_entrypoint": "local verifier command for report-export-manifest.json file_manifest size/sha256 rows plus agent-handoff decision-digest schema before sharing or archiving an export directory",
                "data.report_exports.directory_bundle.verifier_output_fields": "machine-readable report-bundle verifier output fields desktop agents must inspect, including ok, agent_handoff schema booleans, delivery_checklist_present, bundle_integrity_present, bundle_ready_to_verify, image_evidence_inventory_present, verification_recipe_present, and verifier_output_fields_present",
                "data.report_exports.directory_bundle.verification_recipe": "machine-readable report-bundle verification recipe with command, expected exit code, success condition, failure routing, and required verifier output fields",
                "data.report_exports.directory_bundle.manifest_fields": "report-export-manifest.json top-level fields including files, file_manifest sha256 rows, delivery_checklist, bounded agent_summary, and report_exports",
                "data.report_exports.directory_bundle.agent_handoff": "lightweight desktop-agent handoff export containing delivery file routing, decision digest, report visibility with image evidence inventory, capital risk panel, relationship resolution verification queue, operator work, QYYJT section batches, source-health snapshot, source resilience retry policy, graph capital exposure, relationship graph audit summary, capital/relationship top steps, reliance limitations, and print handoff cards",
                "data.report_exports.directory_bundle.agent_handoff.delivery_files": "directory-relative file routing for DOCX, portable HTML, Markdown, JSON packet, agent-handoff, manifest, and recommended open order",
                "data.report_exports.directory_bundle.agent_handoff.bundle_integrity": "directory-export integrity handoff pointing to report-export-manifest.json file_manifest sha256 rows for primary report outputs, with self-referential manifest and agent-handoff exclusions",
                "data.report_exports.directory_bundle.agent_handoff.bundle_verification": "directory-export verifier handoff mirrored from verification_recipe with ready_to_run, manifest file, required output fields, success condition, and failure routing",
                "data.report_exports.directory_bundle.agent_handoff.delivery_checklist": "directory-export print and agent delivery checklist mirrored from report_exports.print_package.delivery_checklist, with required files, open order, print binding, and quality checks",
                "data.report_exports.directory_bundle.agent_handoff.trust_boundaries": "machine-readable boundary fields for clean conclusion, lead-only handling, connector-health separation, monitoring scope, and evidence reliance",
                "data.report_exports.directory_bundle.agent_handoff.decision_digest": "compact desktop-agent routing digest for delivery status, bundle verification readiness, conclusion boundary, acceptance blockers, source resilience, queue counts, first action, and public/user-authorized evidence boundary",
                "data.report_exports.directory_bundle.agent_handoff.next_actions": "single ranked desktop-agent queue merged from acceptance closure, operator work, source recovery, QYYJT public-origin, control-path, goods, people, capital, and relationship audit handoffs",
                "data.report_exports.directory_bundle.agent_handoff.acceptance_closure": "directory-export handoff content includes the acceptance closure digest so desktop agents can decide whether to deliver, continue follow-up, or keep caveats",
                "data.report_exports.directory_bundle.agent_handoff.reliance_limitations": "directory-export handoff summary of non-reliance caveats with count, highest severity, clean-conclusion flag, policy, top next action, and bounded limitation items",
                "data.report_exports.directory_bundle.agent_handoff.closure_steps.control_path_verification_queue": "directory-export control-path verification queue mirrored from enterprise_cognition.control_ownership for desktop-agent UBO/control-chain review",
                "data.report_exports.directory_bundle.agent_handoff.source_health.recovery_execution_queue": "directory-export source recovery execution queue mirrored from monitoring_seed with ready rows, blocked preview rows, retry policy, replay_route, done condition, and non-reliance caveat metadata",
                "data.report_exports.directory_bundle.agent_handoff.capital_and_relationship.relationship_graph_audit": "directory-export relationship graph audit summary with edge counts, evidence-backed/auditable/missing/lead-only split, queue count, top step, and non-reliance policy",
                "data.report_exports.directory_bundle.agent_handoff.relationship_resolution": "directory-export relationship-resolution handoff mirrored from enterprise_cognition.relationship_resolution_v1 with bounded candidate leads, relation-type/lane summary, and verification queue",
                "data.report_exports.directory_bundle.agent_handoff.relationship_resolution.verification_queue": "bounded relationship candidate verification queue; rows stay lead-only until corroborated by registry, filing, announcement, licensed, public, or user-authorized evidence",
                "data.report_exports.portable_html.first_screen_handoff_cards": "machine-readable first-screen cards synchronized from print_package operational handoff, so desktop agents can route source recovery, control-path verification, capital verification, relationship audit, public-origin, and coverage work without scraping HTML",
                "data.report_exports.portable_html.first_screen_handoff_card_count": "count of synchronized first-screen handoff cards embedded beside the portable HTML document",
                "data.report_exports.portable_html.first_screen_handoff_source": "stable packet path proving portable HTML cards are mirrored from report_exports.print_package.operational_handoff.cards",
                "data.report_exports.portable_html.delivery_checklist_source": "stable packet path proving portable HTML delivery checklist is rendered from report_exports.print_package.delivery_checklist",
                "data.report_exports.print_package.operational_handoff": "print-package operational handoff appendix with source recovery, source repair, control-path verification, goods economics, non-reliance limitations, capital verification, relationship audit, public-origin, and coverage-gap cards",
                "data.report_exports.print_package.operational_handoff.cards.acceptance_closure_summary": "first operational handoff card summarizing acceptance status, blocker count, open domains, next action, and done condition",
                "data.report_exports.print_package.operational_handoff.cards.reliance_limitation_top_action": "top non-reliance limitation card mirrored to portable HTML first-screen cards and directory agent handoff routing",
                "data.report_exports.print_package.relationship_capital_appendix": "print-package appendix summarizing capital exposure, relationship edge evidence status, capital verification queue, relationship graph audit queue, and non-reliance policy for DOCX/print review",
                "data.report_exports.print_package.delivery_checklist": "machine-readable delivery checklist for desktop agents and print operators, including required output files, open order, print binding requirements, and quality checks",
                "data.report_exports.print_package.docx.renderer_capabilities": "DOCX renderer capabilities including official document metadata, red-head separator rule, chart rows, native chart summary panels, image inventory, operational handoff tables, native Word tables, TOC, and PAGE footer",
                "data.monitoring_seed": "baseline dimensions for later continuous enterprise watch",
                "data.monitoring_seed.recurring_failure_patterns": "repeated source/category/domain failures with operator actions for source repair",
                "data.monitoring_seed.source_repair_priority_queue": "ranked source repair work queue with source, category, domain, priority, status, action, and related recovery step ids",
                "data.monitoring_seed.source_health_trend_snapshot": "bounded per-packet source-health trend snapshot for on-demand operator repair; does not enable background monitoring",
                "data.source_failure_summary.recurring_failure_patterns": "per-packet recurring retrieval failure patterns; retrieval health only, not a subject risk verdict",
                "data.one_click_readiness.source_resilience_status": "source resilience status for the first-screen desktop-agent handoff",
                "data.one_click_readiness.source_resilience_recommended_action": "operator recovery action for blocked or degraded source coverage",
                "data.one_click_readiness.source_resilience_recommended_step": "first recovery step with source, domain, priority, status, query family, and required fields",
                "data.one_click_readiness.source_resilience_retry_policy": "bounded retry guidance for the recommended recovery step, including retryable, attempts, backoff, timeout, concurrency, authorization boundary, stop conditions, and safe fallback rule",
                "data.one_click_readiness.source_resilience_retryable": "whether the recommended recovery step can be retried immediately with currently available public or user-authorized connectors",
                "data.one_click_readiness.source_resilience_retry_max_attempts": "maximum bounded attempts for the recommended recovery step; zero means blocked until the connector or authorization boundary is resolved",
                "data.one_click_readiness.source_resilience_recommended_step_ready_to_run": "whether the recommended source-resilience step can run with currently available connectors",
                "data.one_click_readiness.source_resilience_recommended_step_blocked_reason": "connector or authorization blocker for the recommended recovery step",
                "data.monitoring_seed.recovery_execution_queue.queue.replay_route": "desktop-agent source recovery replay route with investigate_company tool arguments, CLI command, retry limit, done condition, and non-reliance caveat",
                "data.monitoring_seed.recovery_execution_queue.blocked_preview.replay_route": "blocked source recovery replay route with zero retry limit until connector, authorization, or source availability is resolved",
                "data.one_click_readiness.operator_work_queue_count": "merged first-screen operator work count across source repair, recovery, public-origin fallback, control-path verification, goods economics, people/control corroboration, capital verification, relationship audit, and coverage gaps",
                "data.one_click_readiness.operator_work_p0_count": "P0 operator work rows that should be handled before relying on degraded coverage or unresolved capital/relationship findings",
                "data.one_click_readiness.operator_work_ready_count": "operator work rows that can run without additional connector or authorization work",
                "data.one_click_readiness.operator_work_top_action": "first ranked operator work row with lane, priority, status, source, target, action, readiness, blocker, done condition, and packet references",
                "data.one_click_readiness.operator_work_queue": "ranked desktop-agent work queue derived from existing runtime follow-up surfaces, not a separate evidence source",
                "data.one_click_readiness.reliance_limitations": "machine-readable missing-data and reliance caveats explaining what not to over-read and what action closes each limitation",
                "data.one_click_readiness.reliance_limitation_count": "count of current limitations that prevent clean reliance or require caveated reading",
                "data.one_click_readiness.can_make_clean_conclusion": "false when quality, coverage, source, capital, or relationship gaps mean absence of evidence must not be read as absence of risk",
                "data.one_click_readiness.acceptance_closure_summary": "compact acceptance-readiness digest combining quality, source recovery, coverage, public-origin, capital, graph, relationship, closure-step, operator-work, and reliance limitations into one delivery decision surface",
                "data.one_click_readiness.acceptance_closure_status": "blocked, needs_operator_followup, needs_review, or ready_for_human_review status for desktop-agent delivery routing",
                "data.one_click_readiness.acceptance_closure_blocking_count": "count of blockers, blocked work, reliance limitations, and unresolved capital relationship items that prevent clean acceptance closure",
                "data.one_click_readiness.acceptance_closure_top_action": "first ranked action from the acceptance closure digest for agent continuation",
                "data.one_click_readiness.source_repair_priority_count": "count of recurring source repair priorities exposed to desktop-agent hosts",
                "data.one_click_readiness.source_repair_p0_count": "P0 source repair priorities that should be handled before relying on degraded coverage",
                "data.one_click_readiness.source_repair_top_action": "first source repair action with source, failure category, domain, priority, status, and operator action",
                "data.one_click_readiness.source_health_trend_source_count": "count of sources in the bounded per-packet source-health trend snapshot",
                "data.one_click_readiness.source_health_trend_blocked_source_count": "count of blocked sources in the bounded per-packet source-health trend snapshot",
                "data.one_click_readiness.source_health_trend_top_source": "first ranked source-health trend source with priority, status, failure count, and repair queue link",
                "data.one_click_readiness.source_health_trend_digest": "compact first-screen source-health digest with top source, actionability, blocked reason, next action, packet refs, evidence boundary, repair queue id, policy, and monitoring-disabled flag",
                "data.one_click_readiness.source_health_trend_digest.actionability": "agent routing status such as blocked_connector_repair or ready_recovery_available; it describes source repair work, not subject facts",
                "data.one_click_readiness.source_health_trend_digest.subject_risk_verdict_allowed": "always false because source-health degradation cannot be promoted to a company risk verdict",
                "data.one_click_readiness.source_health_trend_policy": "policy explaining that source-health digest is bounded to this packet and does not enable background monitoring",
                "data.qyyjt_public_origin_handoff": "investigation-packet public-origin QYYJT handoff with P0/top actions, origin channels, query families, required fields, admission gate, done condition, and compliance policy",
                "data.qyyjt_public_origin_handoff.report_section_batches": "QYYJT public-origin action batches grouped by report section so agents can reconstruct evidence by report chapter from the investigation packet",
                "data.qyyjt_public_origin_handoff.section_work_orders": "agent-executable QYYJT public-origin work orders grouped by report section with query families, required fields, origin channels, top actions, done condition, and admission policy",
                "data.one_click_readiness.attempted_source_count": "source diagnostics attempted count visible without opening diagnostics",
                "data.one_click_readiness.coverage_status_counts": "coverage-only status counts such as empty, no_results, not_searched, and skipped_unsupported_source",
                "data.one_click_readiness.coverage_not_searched_count": "coverage domains that were not attempted and must not be interpreted as clean results",
                "data.one_click_readiness.coverage_no_evidence_count": "attempted domains that returned no usable evidence and remain coverage gaps",
                "data.one_click_readiness.coverage_gap_count": "deduped coverage gap domain count across not-searched and no-evidence domains",
                "data.one_click_readiness.coverage_gap_severity": "none, low, medium, or high severity label for first-screen coverage triage",
                "data.one_click_readiness.coverage_attempt_ratio": "attempted source ratio compared with not-searched coverage work",
                "data.one_click_readiness.coverage_next_action": "operator action for closing the most important coverage gap before final reliance",
                "data.one_click_readiness.coverage_missing_domains": "not-searched coverage domains visible in the one-click handoff",
                "data.one_click_readiness.coverage_domains_without_evidence": "attempted domains with no usable evidence visible in the one-click handoff",
                "data.one_click_readiness.coverage_policy": "machine-readable policy distinguishing not_searched from no_evidence",
                "data.one_click_readiness.public_origin_fallback_count": "QYYJT/public-origin fallback routes available from source diagnostics",
                "data.one_click_readiness.public_origin_next_action_count": "operator-ready public-origin fallback actions visible in the one-click handoff",
                "data.one_click_readiness.public_origin_modules": "QYYJT module names selected for public-origin reconstruction",
                "data.one_click_readiness.public_origin_top_action": "first executable public-origin action with module, origin channel, required fields, and admission gate",
                "data.one_click_readiness.public_origin_gap_bridge": "machine-readable bridge from coverage gap domains to public-origin reconstruction actions with domains, modules, fields, admission gates, and done conditions",
                "data.one_click_readiness.public_origin_gap_bridge_top_action": "first public-origin bridge action for a coverage gap, mirrored into report handoff cards and agent-handoff exports",
                "data.one_click_readiness.control_path_closure_needed": "true when multi-layer controller or UBO paths need an explicit verification/review step before final reliance",
                "data.one_click_readiness.control_path_signal_count": "number of indirect control-path rows routed into the closure step",
                "data.one_click_readiness.control_path_highest_hop_count": "maximum hop depth observed across multi-layer control paths",
                "data.one_click_readiness.control_path_source_family_summary": "source-family provenance summary for indirect controller or UBO paths; explains official/licensed/public breadth without upgrading weak leads",
                "data.one_click_readiness.control_path_closure_step": "machine-readable CONTROL-PATH step with priority, path text, admission state, evidence ids, action, and done condition",
                "data.one_click_readiness.goods_economics_closure_needed": "true when public goods economics, bargaining-power, or competitive-landscape leads need corroboration before reliance",
                "data.one_click_readiness.goods_economics_signal_count": "number of explicit public goods-economics signals routed into the closure step",
                "data.one_click_readiness.goods_economics_closure_step": "machine-readable GOODS-ECON closure step with priority, sample signals, action, and done condition for source-backed corroboration",
                "data.one_click_readiness.people_control_closure_needed": "true when public controller, UBO, key-person, legal-pressure, ownership-change, or related-party leads need corroboration before reliance",
                "data.one_click_readiness.people_control_signal_count": "number of explicit public people/control signals routed into the closure step",
                "data.one_click_readiness.people_control_closure_step": "machine-readable PEOPLE-CONTROL closure step with priority, sample signals, action, and done condition for source-backed corroboration",
                "data.one_click_readiness.relationship_candidate_watch_count": "relationship candidate leads that remain corroboration watch items",
                "data.one_click_readiness.relationship_candidate_execution_step_count": "operator execution steps for corroborating relationship candidates",
                "data.one_click_readiness.relationship_candidate_p0_count": "P0 relationship candidate leads requiring high-priority corroboration",
                "data.one_click_readiness.relationship_candidate_top_step": "first relationship corroboration step with target, relation type, and verification sources",
                "data.one_click_readiness.capital_relationship_status": "evidence_backed, unresolved, or not_applicable state for capital-pressure closure",
                "data.one_click_readiness.capital_relationship_unresolved_reason": "why admitted capital pressure is not closed by an admitted relationship edge",
                "data.one_click_readiness.capital_relationship_next_action": "operator action to close unresolved capital-pressure relationship evidence",
                "data.one_click_readiness.capital_relationship_closure_step": "machine-readable CAP-REL closure step with priority, target, source, and done condition when capital pressure is unresolved",
                "data.one_click_readiness.graph_capital_exposure": "risk-graph summary.capital_exposure mirrored into the one-click handoff with pressure level, relationship status, queues, ids, next action, and alignment state",
                "data.one_click_readiness.graph_capital_exposure_top_step": "first graph-capital exposure verification or relationship-mapping step for desktop-agent routing",
                "data.one_click_readiness.graph_capital_exposure_alignment_status": "whether graph summary capital exposure agrees with enterprise capital pressure profile or needs review",
                "data.one_click_readiness.graph_capital_exposure_source_family_summary": "source-family provenance summary for risk-graph capital exposure routing; explains official/licensed/public breadth without upgrading weak leads",
                "data.one_click_readiness.capital_pressure_source_family_summary": "source-family provenance summary for enterprise capital-pressure rows and verification steps",
                "data.one_click_readiness.capital_verification_queue_count": "number of capital pressure verification steps available for desktop-agent handoff",
                "data.one_click_readiness.capital_verification_queue": "bounded capital pressure verification steps with priority, kind, target, source, and done condition for desktop-agent routing",
                "data.one_click_readiness.capital_verification_top_step": "first executable capital verification step with priority, kind, target, and done condition",
                "data.one_click_readiness.relationship_edge_count": "relationship graph top-edge count visible in the one-click loop",
                "data.one_click_readiness.relationship_evidence_backed_edge_count": "relationship edges with evidence ids, separated from fact-admitted/auditable edges",
                "data.one_click_readiness.relationship_auditable_edge_count": "fact/admitted/evidence relationship edges with evidence ids",
                "data.one_click_readiness.relationship_missing_evidence_edge_count": "relationship edges that should not be relied on until evidence ids are attached",
                "data.one_click_readiness.relationship_lead_only_edge_count": "relationship edges that remain lead-only and need corroboration before clean reliance",
                "data.one_click_readiness.relationship_graph_audit_queue_count": "number of relationship-edge audit steps for desktop-agent handoff",
                "data.one_click_readiness.relationship_graph_audit_queue": "bounded relationship-edge audit steps with priority, kind, target, evidence ids, source names, and done condition for desktop-agent routing",
                "data.one_click_readiness.relationship_graph_audit_top_step": "first relationship-edge audit step with priority, relation type, evidence ids, and done condition",
                "data.report_markdown": "human-readable due-diligence brief for UI/export",
                "data.graph": "same structured payload as /api/risk-graph",
                "data.summary": "top-level graph summary for UI/plugin quick rendering",
                "data.next_actions": "actionable coverage and verification guidance",
                "data.persona_surface": "13-role anthropomorphic shell contract shared with release and UI surfaces",
            },
        },
        "risk_graph_contract": {
            "request": {
                "company": "required string",
                "config": "optional datasource YAML path",
                "offline_fixture": "optional bool for deterministic local smoke tests",
                "fixture_pack": "optional bool for multi-source connector demo records",
                "retrieval_concurrency": "optional int, clamped to 1..20",
                "query_timeout_seconds": "optional float, clamped to 0.1..120.0 per retrieval task",
                "fanout_rounds": "optional int, clamped to 0..3",
                "max_fanout_tasks": "optional int, clamped to 0..80",
            },
            "response": {
                "data.summary": "execution state, coverage, next actions, counts, highest severity, source success/failure summary",
                "data.summary.capital_exposure": "capital pressure level, signal counts, evidence ids, explicit capital relationship edge status, relationship audit queue, and next action",
                "data.nodes": "company/person/address/contact/domain/account/asset/case/project nodes",
                "data.edges": "evidence-backed relations and has_risk_event links",
                "data.evidence": "source, URL, trimmed claims, omitted claim count, confidence, source profile",
                "data.risk_events": "category, severity, entity names, evidence refs, rationale, evidence ids",
                "data.timeline": "merged evidence and risk-event timeline",
                "data.diagnostics.context_capsule": "bounded downstream context summary for plugins and agents",
                "data.diagnostics.source_routing": "configured/available/unavailable datasource routing snapshot",
                "data.diagnostics.monitoring_delta": "new, recurring, and not-reproduced risk events",
            },
        },
    })




@app.route("/api/dd_health", methods=["GET"])
def api_dd_health():
    try:
        company = str(request.args.get("company") or "Apple Inc.").strip()
        data = {
            "company": company,
            "default_public_one_click": True,
            "query_timeout_seconds": _clamped_float(request.args, "query_timeout_seconds", 8.0, 0.1, 120.0),
        }
        graph_payload = _run_async_payload(_build_risk_graph_payload(data))
        packet = build_investigation_packet(graph_payload, input_text=company, mode="dd_health").to_dict()
        cognition = packet.get("enterprise_cognition", {})
        report_card = cognition.get("investigation_report_card", {})
        audit = cognition.get("capability_audit", {})
        release = cognition.get("release_decision", {})
        blocker_gate = cognition.get("blocker_gate", {})
        realness = cognition.get("realness_score", {})
        return jsonify({
        "status": "ok",
        "dd_version": "5.0",
        "company": company,
        "capability_audit": {
            "total": audit.get("total", 0),
            "implemented": audit.get("implemented", 0),
            "wired": audit.get("wired", 0),
            "tested": audit.get("tested", 0),
            "fixture_only_count": audit.get("fixture_only_count", 0),
        },
        "release_decision": release,
        "blocker_gate": {
            "blocker_count": blocker_gate.get("blocker_count", 0),
            "is_clear": blocker_gate.get("is_clear", False),
        },
        "realness_score": realness,
        "investigation_report_card": {
            "api_visible_release_decision": report_card.get("api_visible_release_decision"),
            "api_visible_release_score": report_card.get("api_visible_release_score"),
            "dd_summary": report_card.get("dd_summary", {}),
        },
        "validation_status": {
            "focused_required": True,
            "acceptance_required": True,
            "source": "runtime_validation_required",
        },
    }), 200
    except Exception as e:
        return jsonify({"error":str(e)}), 500

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    print(f"""
🏛️  华尔街驻铁岭办事处 API Server v0.5.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━
端口: {PORT}
绑定: {BIND_HOST}
模型: {config.DEFAULT_MODEL}
API Key: {'已配置 ✅' if config.get_api_key() else '未配置 ⚠️'}
认证: {'Bearer Token ✅' if AUTH_TOKEN else '仅本机 (127.0.0.1) 🔒'}

测试:
  curl http://localhost:{PORT}/api/health""")
    if AUTH_TOKEN:
        print(f'  curl -H "Authorization: Bearer $WALLSTREET_AUTH_TOKEN" ...')
    print()
    app.run(host=BIND_HOST, port=PORT, debug=False)
