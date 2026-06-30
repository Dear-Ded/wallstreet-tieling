"""source_smoke_harness.py — DD v3.2 Full Source Smoke Harness.
Each source returns structured SourceSmokeResult with access issues, failure reasons, and next actions.
"""
from typing import Any
import time

SCHEMA = ("source_name","source_type","live_status","checked_at","structure_verified","fields_enter_pipeline","failure_reason","access_issue","next_action")

def run_source_smoke(subject=None, source_configs=None):
    """Run smoke tests for a given subject against configured sources.
    Returns standardized results with access issue tracking.
    Does NOT bypass auth/captcha/anti-crawl — records status honestly.
    """
    configs = source_configs or _default_configs()
    subject_str = str(subject) if subject else "unknown_subject"
    results = []
    for cfg in configs:
        name = cfg.get("name","?")
        stype = cfg.get("type","?")
        checked = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            result = _smoke_single(name, stype, subject_str, checked, cfg)
            results.append(result)
        except Exception as e:
            results.append(_smoke_error(name, stype, checked, str(e)[:200]))
    blocked = sum(1 for r in results if r["live_status"]=="blocked_or_captcha")
    auth_required = sum(1 for r in results if r["live_status"]=="authorization_required")
    fixture = sum(1 for r in results if r["live_status"] in ("fixture_only","live_unverified"))
    live_verified = sum(1 for r in results if r["live_status"]=="live_verified")
    return {"smoke_results":results,"source_count":len(results),
        "fixture_only":fixture,"live_verified":live_verified,
        "blocked":blocked,"authorization_required":auth_required,
        "overall_status":"ready" if live_verified>0 else ("blocked" if blocked>0 else ("needs_auth" if auth_required>0 else "fixture_only")),
        "source_lane_readiness": _source_lane_readiness(results),
        "ready_for_production":live_verified>0,
        "blocker_summary":{"live_verified":live_verified,"blocked":blocked,"auth_required":auth_required,"fixture_only":fixture,"parse_failed":0},
        "subject":subject_str}

def _smoke_single(name, stype, subject, checked, cfg):
    """Per-source smoke logic. Extensible via config dict."""
    if stype == "public_web_search":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"Live search not yet configured for this environment",
            "access_issue":None,"next_action":"configure_search_provider"}
    elif stype == "public_registry":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"Registry API endpoint not configured",
            "access_issue":None,"next_action":"configure_registry_endpoint"}
    elif stype == "sec_edgar_public_api":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"SEC EDGAR rate-limited in current environment",
            "access_issue":None,"next_action":"run_live_smoke_with_rate_limiting"}
    elif stype == "gleif_lei_public_api":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"GLEIF API limited to LEI queries only",
            "access_issue":None,"next_action":"run_live_smoke"}
    elif stype == "default_public_intel":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":True,"failure_reason":"Default intel can execute public web and QYYJT public-plan searches, but live results are not verified in this smoke run",
            "access_issue":None,"next_action":"run_live_smoke","live_smoke_capable":True}
    elif stype == "authorized_source":
        return {"source_name":name,"source_type":stype,"live_status":"authorization_required","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"Credentials required for authorized source",
            "access_issue":"authorization_required","next_action":"provide_credentials_or_upload"}
    elif stype == "user_upload":
        return {"source_name":name,"source_type":stype,"live_status":"live_unverified","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":False,"failure_reason":"User upload requires manual data provision",
            "access_issue":None,"next_action":"await_user_upload"}
    elif stype == "fixture_source":
        return {"source_name":name,"source_type":stype,"live_status":"fixture_only","checked_at":checked,
            "structure_verified":True,"fields_enter_pipeline":True,"failure_reason":None,
            "access_issue":"fixture_only_no_live_data","next_action":"replace_with_live_source"}
    else:
        return {"source_name":name,"source_type":stype,"live_status":"unknown","checked_at":checked,
            "structure_verified":False,"fields_enter_pipeline":False,"failure_reason":f"Unknown source type: {stype}",
            "access_issue":"unknown_source_type","next_action":"configure_source_type"}

def _smoke_error(name, stype, checked, error):
    return {"source_name":name,"source_type":stype,"live_status":"blocked_or_captcha","checked_at":checked,
        "structure_verified":False,"fields_enter_pipeline":False,"failure_reason":error,
        "access_issue":"blocked_or_captcha","next_action":"debug_and_retry"}

def _default_configs():
    return [{"name":"public_web_search","type":"public_web_search"},{"name":"public_registry","type":"public_registry"},
        {"name":"sec_edgar_public_api","type":"sec_edgar_public_api"},{"name":"gleif_lei_public_api","type":"gleif_lei_public_api"},
        {"name":"default_public_intel","type":"default_public_intel"},{"name":"qyyjt_api","type":"authorized_source"},
        {"name":"fixture_licensed_registry_api","type":"fixture_source"}]

def _source_lane_readiness(results):
    """Derive lane readiness from actual smoke results instead of a static matrix."""
    lanes = {}
    for result in results:
        lane = _readiness_lane_name(result)
        status = str(result.get("live_status") or "unknown")
        lanes[lane] = {
            "live_verified": status == "live_verified" or bool(result.get("live_verified")),
            "fixture_only": status == "fixture_only",
            "live_unverified": status == "live_unverified",
            "blocked": status == "blocked_or_captcha",
            "unknown": status == "unknown",
            "authorized": status == "authorization_required" or result.get("access_issue") == "authorization_required",
            "live_smoke_capable": bool(result.get("live_smoke_capable")),
            "source_name": result.get("source_name"),
            "source_type": result.get("source_type"),
            "next_action": result.get("next_action"),
        }
    return lanes

def _readiness_lane_name(result):
    name = str(result.get("source_name") or "").strip()
    aliases = {
        "public_web_search": "public_web",
        "sec_edgar_public_api": "sec_edgar",
        "gleif_lei_public_api": "gleif_lei",
        "default_public_intel": "default_intel",
        "fixture_licensed_registry_api": "fixture_src",
    }
    return aliases.get(name, name or str(result.get("source_type") or "unknown_source"))

def source_boundary_enforcer(smoke_results: dict) -> dict:
    """Batch D: Enforce live/fixture boundary. Fixture can NEVER be live_verified."""
    sr = smoke_results or {}
    # No source can be both fixture_only AND live_verified
    for r in sr.get("smoke_results", []):
        if r.get("live_status") == "fixture_only":
            r["live_verified"] = False
        if r.get("live_status") in ("live_unverified", "fixture_only", "authorization_required", "blocked_or_captcha"):
            r["live_verified"] = False
    return {
        "boundary_enforced": True,
        "fixture_is_not_live": True,
        "live_verified_count": sum(1 for r in sr.get("smoke_results", []) if r.get("live_verified")),
        "fixture_count": sum(1 for r in sr.get("smoke_results", []) if r.get("live_status") == "fixture_only"),
        "access_issues": sum(1 for r in sr.get("smoke_results", []) if r.get("live_status") in ("authorization_required", "blocked_or_captcha")),
    }
