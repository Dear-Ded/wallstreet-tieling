#!/usr/bin/env python3
"""Tests for writable runtime state path resolution."""
from __future__ import annotations

from pathlib import Path

from core.risk_discovery_pipeline import RiskDiscoveryPipeline
from core.storage_paths import runtime_state_path, runtime_state_root


def test_runtime_state_root_honors_explicit_env(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "state"
    monkeypatch.setenv("WST_STATE_DIR", str(configured))

    root = runtime_state_root()

    assert root == configured
    assert root.exists()


def test_runtime_state_path_honors_file_env(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "stores" / "events.jsonl"
    monkeypatch.setenv("WST_RISK_EVENT_STORE", str(configured))

    path = runtime_state_path("risk-events.jsonl", filename_env_var="WST_RISK_EVENT_STORE")

    assert path == configured
    assert path.parent.exists()


def test_risk_discovery_pipeline_uses_configured_default_store(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "risk-events.jsonl"
    monkeypatch.setenv("WST_RISK_EVENT_STORE", str(configured))

    pipeline = RiskDiscoveryPipeline()

    assert Path(pipeline.risk_event_store.path) == configured
