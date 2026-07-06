#!/usr/bin/env python3
"""Deep-mode source preflight for desktop-agent hosts."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .connector_registry import ConnectorCapability, ConnectorRegistry
from .intelligence_retrieval import SourceAccess


CONFIG_KEYS_BY_FLAG = {
    "api_key_required": ("api_key_env", "api_key"),
    "requires_user_agent_contact": ("user_agent_contact_env", "user_agent_contact"),
    "user_session_required": ("session_env", "session_path", "cookie_env"),
    "requires_configured_local_index": ("index_path", "index_env"),
    "local_index_required": ("index_path", "index_env"),
    "dataset_refresh_policy_required": ("refresh_policy",),
}


def build_source_preflight(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return a no-secret readiness profile for deep-mode source automation."""
    registry = ConnectorRegistry()
    config = _load_config(config_path)
    rows = [_preflight_row(connector, config) for connector in registry.list()]
    ready_rows = [row for row in rows if row["ready_to_run"]]
    default_public = [row for row in rows if row["category"] == "default_public_ready"]
    configured_authorized = [row for row in rows if row["category"] == "configured_authorized_ready"]
    fallback_rows = [row for row in rows if row["fallback_available"] and not row["ready_to_run"]]
    blocked_rows = [
        row
        for row in rows
        if row["status"] in {"blocked_missing_configuration", "configured_but_admission_pending"}
    ]
    prompt_rows = [row for row in rows if row["operator_prompt_required_during_run"]]
    lanes = _lane_summary(rows)
    deep_ready = bool(default_public) and not prompt_rows
    configured_depth = bool(configured_authorized)
    return {
        "type": "source_preflight",
        "version": "0.5.0",
        "config_path": str(config_path) if config_path else "",
        "config_loaded": bool(config),
        "status": "pass" if deep_ready else "fail",
        "deep_mode_status": (
            "configured_depth_ready"
            if configured_depth
            else "ready_with_public_fallbacks"
            if deep_ready
            else "blocked"
        ),
        "no_prompt_contract": {
            "subject_name_only_after_preconfiguration": True,
            "operator_prompt_required_during_run": bool(prompt_rows),
            "prompt_required_source_count": len(prompt_rows),
            "missing_source_policy": "continue_with_public_origin_fallback_and_record_gap",
            "stop_on_missing_advanced_source": False,
            "secret_policy": "secret values are never emitted; only env/config presence is reported",
        },
        "summary": {
            "total_connectors": len(rows),
            "ready_to_run": len(ready_rows),
            "default_public_ready": len(default_public),
            "configured_authorized_ready": len(configured_authorized),
            "fallback_only": len(fallback_rows),
            "blocked_or_pending": len(blocked_rows),
            "lane_count": len(lanes),
        },
        "lanes": lanes,
        "rows": rows,
        "next_actions": _next_actions(rows, configured_depth),
        "agent_rules": [
            "Run source_preflight before deep investigate when a workspace may contain configured sources.",
            "Do not ask the end user to select sources after subject submission.",
            "Do not stop deep mode because an advanced source is missing; downgrade to public-origin fallback and record the gap.",
            "Do not promote fallback or lead-only rows into report facts without provenance and admission gates.",
        ],
    }


def _preflight_row(connector: ConnectorCapability, config: dict[str, Any]) -> dict[str, Any]:
    payload = connector.to_dict()
    source_config = _source_config(config, connector.name)
    required = _required_configuration(connector)
    configured = _is_configured(source_config, required)
    public_no_secret = connector.access is SourceAccess.PUBLIC
    ready_public = public_no_secret and connector.production_ready
    ready_authorized = configured and connector.production_ready
    ready_to_run = bool(ready_public or ready_authorized)
    fallback_available = not ready_to_run
    status = _status(connector, configured, ready_to_run)
    category = _category(connector, ready_to_run, configured)
    return {
        "name": connector.name,
        "status": status,
        "category": category,
        "ready_to_run": ready_to_run,
        "fallback_available": fallback_available,
        "fallback": "public_origin_reconstruction" if fallback_available else "",
        "access": payload["access"],
        "authority": payload["authority"],
        "domains": payload["domains"],
        "production_ready": payload["production_ready"],
        "default_enabled": payload["default_enabled"],
        "standardized_records": payload["standardized_records"],
        "health_check": payload["health_check"],
        "admission_mode": payload["data_effectiveness"]["admission_mode"],
        "can_feed_report_facts": payload["data_effectiveness"]["can_feed_report_facts"] and ready_to_run,
        "can_feed_report_leads": payload["data_effectiveness"]["can_feed_report_leads"],
        "required_configuration": required,
        "configured": configured,
        "configured_by": _configured_by(source_config, required),
        "operator_prompt_required_during_run": False,
        "stop_on_failure": False,
        "downgrade_policy": (
            "continue_with_fallback_and_evidence_gap"
            if fallback_available
            else "record_source_health_and_continue"
        ),
    }


def _status(connector: ConnectorCapability, configured: bool, ready_to_run: bool) -> str:
    if ready_to_run:
        return "ready"
    if connector.access is SourceAccess.PUBLIC:
        return "available_as_fallback_or_lead"
    if configured:
        return "configured_but_admission_pending"
    return "blocked_missing_configuration"


def _category(connector: ConnectorCapability, ready_to_run: bool, configured: bool) -> str:
    if ready_to_run and connector.default_enabled and connector.access is SourceAccess.PUBLIC:
        return "default_public_ready"
    if ready_to_run and connector.access is SourceAccess.PUBLIC:
        return "optional_public_ready"
    if ready_to_run and configured:
        return "configured_authorized_ready"
    if connector.access is SourceAccess.PUBLIC:
        return "public_fallback_or_catalog"
    return "authorized_fallback_only"


def _required_configuration(connector: ConnectorCapability) -> list[dict[str, Any]]:
    keys: list[str] = []
    for flag in connector.risk_flags:
        keys.extend(CONFIG_KEYS_BY_FLAG.get(flag, ()))
    if connector.access is SourceAccess.USER_AUTHORIZED and not keys:
        keys.append("authorization_evidence")
    result = []
    for key in sorted(dict.fromkeys(keys)):
        env_name = _env_name(connector.name, key)
        result.append(
            {
                "key": key,
                "env": env_name,
                "present": bool(os.environ.get(env_name)),
            }
        )
    return result


def _is_configured(source_config: dict[str, Any], required: list[dict[str, Any]]) -> bool:
    if not required:
        return bool(source_config.get("enabled"))
    if source_config.get("enabled") is True:
        return True
    for item in required:
        key = item["key"]
        if item["present"] or source_config.get(key):
            return True
    return False


def _configured_by(source_config: dict[str, Any], required: list[dict[str, Any]]) -> list[str]:
    configured_by = []
    if source_config.get("enabled") is True:
        configured_by.append("config.enabled")
    for item in required:
        key = item["key"]
        if item["present"]:
            configured_by.append(f"env.{item['env']}")
        if source_config.get(key):
            configured_by.append(f"config.{key}")
    return sorted(dict.fromkeys(configured_by))


def _source_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    sources = config.get("sources") if isinstance(config.get("sources"), dict) else {}
    if name in sources and isinstance(sources[name], dict):
        return sources[name]
    if name in config and isinstance(config[name], dict):
        return config[name]
    enabled = config.get("enabled_sources")
    if isinstance(enabled, list) and name in {str(item) for item in enabled}:
        return {"enabled": True}
    return {}


def _load_config(config_path: str | Path | None) -> dict[str, Any]:
    if not config_path:
        return {}
    target = Path(config_path)
    if not target.exists():
        return {"_missing_config_path": str(target)}
    loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _env_name(source_name: str, key: str) -> str:
    clean_source = "".join(ch if ch.isalnum() else "_" for ch in source_name).upper()
    clean_key = "".join(ch if ch.isalnum() else "_" for ch in key).upper()
    return f"WST_{clean_source}_{clean_key}"


def _lane_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for row in rows:
        for domain in row["domains"]:
            lane = lanes.setdefault(
                domain,
                {
                    "lane": domain,
                    "source_count": 0,
                    "ready_to_run": 0,
                    "fact_capable_ready": 0,
                    "fallback_only": 0,
                    "top_sources": [],
                },
            )
            lane["source_count"] += 1
            if row["ready_to_run"]:
                lane["ready_to_run"] += 1
            if row["can_feed_report_facts"]:
                lane["fact_capable_ready"] += 1
            if row["fallback_available"] and not row["ready_to_run"]:
                lane["fallback_only"] += 1
            if len(lane["top_sources"]) < 5:
                lane["top_sources"].append(row["name"])
    return sorted(lanes.values(), key=lambda item: item["lane"])


def _next_actions(rows: list[dict[str, Any]], configured_depth: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    missing_authorized = [row for row in rows if row["category"] == "authorized_fallback_only"][:8]
    pending = [row for row in rows if row["status"] == "configured_but_admission_pending"][:8]
    if missing_authorized:
        actions.append(
            {
                "id": "configure_authorized_depth_sources",
                "priority": "P0" if not configured_depth else "P1",
                "status": "ready",
                "action": "Configure authorized source credentials, sessions, or local indexes once at workspace level; deep runs must not ask for them after subject submission.",
                "source_names": [row["name"] for row in missing_authorized],
            }
        )
    if pending:
        actions.append(
            {
                "id": "finish_admission_for_configured_sources",
                "priority": "P0",
                "status": "ready",
                "action": "Complete standardized-record, health, and admission checks before configured sources can feed report facts.",
                "source_names": [row["name"] for row in pending],
            }
        )
    actions.append(
        {
            "id": "run_deep_mode_without_midrun_prompt",
            "priority": "P0",
            "status": "ready",
            "action": 'Run npx wallstreet-tieling --source-preflight, then npx wallstreet-tieling --investigate "<subject>" --mode deep; unresolved sources must enter fallback/gap queues.',
            "source_names": [],
        }
    )
    return actions
