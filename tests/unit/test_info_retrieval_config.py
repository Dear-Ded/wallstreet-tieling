#!/usr/bin/env python3
"""Reality checks for information retrieval configuration."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_qyyjt_api_config_marks_placeholder_endpoints_incomplete():
    config_path = PROJECT_ROOT / "config" / "api_endpoints.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    endpoints = data["endpoints"]
    incomplete = {
        name
        for name, spec in endpoints.items()
        if spec.get("path") == "/TODO" or spec.get("method") == "TODO"
    }

    assert incomplete == {
        "risk_scan",
        "court_cases",
        "news_negative",
        "actual_controller",
        "related_parties",
    }


def test_qyyjt_api_config_has_only_two_verified_rest_endpoints():
    config_path = PROJECT_ROOT / "config" / "api_endpoints.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    verified_api_endpoints = {
        name
        for name, spec in data["endpoints"].items()
        if spec.get("path") not in {None, "/TODO"}
        and spec.get("method") not in {None, "TODO"}
        and spec.get("auth_required") is True
    }

    assert verified_api_endpoints == {"search", "notices"}
