"""
source_smoke.py — DD 1.0 Smoke Interfaces
Each source returns: source_name, status, structure_verified,
fields_enter_pipeline, credential_required, live_verified, reason.
"""
from typing import Any

def public_source_smoke() -> dict[str, dict[str, Any]]:
    return {
        "public_web_search": {"source_name": "public_web_search", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "reason": "Fixture-backed; no live verification performed in this environment."},
        "public_registry": {"source_name": "public_registry", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "reason": "Fixture-backed; live registry queries need API endpoints."},
        "sec_edgar_public_api": {"source_name": "sec_edgar_public_api", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "reason": "Fixture-backed; live SEC EDGAR rate-limited."},
        "gleif_lei_public_api": {"source_name": "gleif_lei_public_api", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "reason": "Fixture-backed; live GLEIF limited to LEI queries."},
        "default_public_intel": {"source_name": "default_public_intel", "status": "live_unverified", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "live_smoke_capable": True, "reason": "Default public intelligence can execute public web and QYYJT public-plan searches, but this smoke report has not verified live results."},
    }

def authorized_source_smoke() -> dict[str, dict[str, Any]]:
    return {
        "qyyjt_api": {"source_name": "qyyjt_api", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": True, "live_verified": False, "reason": "QYYJT requires account credentials; not configured in this environment."},
        "fixture_licensed_registry_api": {"source_name": "fixture_licensed_registry_api", "status": "fixture_only", "structure_verified": True, "fields_enter_pipeline": True, "credential_required": False, "live_verified": False, "reason": "Simulated licensed registry; live access needs API key."},
    }
