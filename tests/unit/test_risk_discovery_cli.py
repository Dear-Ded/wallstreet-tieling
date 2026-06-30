#!/usr/bin/env python3
"""Smoke tests for the risk-discovery CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent


def test_risk_discovery_cli_offline_fixture_is_executable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_discovery.py"),
            "Demo CLI Co., Ltd.",
            "--offline-fixture",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["company"] == "Demo CLI Co., Ltd."
    assert payload["retrieval_summary"]["ingested_count"] == 1
    assert payload["risk_event_summary"]["alert_count"] == 1


def test_risk_discovery_cli_fixture_pack_is_executable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_discovery.py"),
            "Demo Fixture CLI Co., Ltd.",
            "--fixture-pack",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["evidence_count"] == 6
    assert payload["retrieval_summary"]["ingested_count"] == 6
    assert payload["risk_event_count"] >= 1
    assert "person:bob_li" in payload["subject_profile"]["subjects"]


def test_risk_discovery_cli_summary_is_human_readable(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "bin" / "risk_discovery.py"),
            "Demo Summary CLI Co., Ltd.",
            "--offline-fixture",
            "--store",
            str(tmp_path / "risk-events.jsonl"),
            "--summary",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "Investigation Summary" in result.stdout
    assert "Demo Summary CLI Co., Ltd." in result.stdout
    assert "Evidence:" in result.stdout
    assert "offline_records" in result.stdout


class FakeCliSearchEngine:
    initialized_with: str | None = None

    @classmethod
    async def initialize(cls, config_path: str):
        cls.initialized_with = config_path
        return cls


@pytest.mark.asyncio
async def test_risk_discovery_cli_config_initializes_search_engine(monkeypatch, tmp_path) -> None:
    import bin.risk_discovery as risk_discovery

    calls = {}

    async def fake_pipeline_run(self, company, **kwargs):
        calls["company"] = company
        calls["kwargs"] = kwargs
        return SimpleNamespace(
            to_dict=lambda include_plan=False: {
                "ok": True,
                "company": company,
                "include_plan": include_plan,
                "configured_source": kwargs["search_engine"].initialized_with,
                "retrieval_concurrency": kwargs["retrieval_concurrency"],
            }
        )

    monkeypatch.setattr(risk_discovery.RiskDiscoveryPipeline, "run", fake_pipeline_run)
    monkeypatch.setattr(
        "adapters.multi_datasource.SearchEngine",
        FakeCliSearchEngine,
    )

    args = risk_discovery.build_parser().parse_args(
        [
            "Demo Config Co., Ltd.",
            "--config",
            str(tmp_path / "datasources.yaml"),
            "--store",
            str(tmp_path / "risk-events.jsonl"),
            "--retrieval-concurrency",
            "7",
            "--include-plan",
        ]
    )

    payload = await risk_discovery.run(args)

    assert payload["ok"] is True
    assert payload["configured_source"] == str(tmp_path / "datasources.yaml")
    assert payload["retrieval_concurrency"] == 7
    assert payload["include_plan"] is True
    assert calls["kwargs"]["records"] is None
    assert calls["kwargs"]["store_path"] == str(tmp_path / "risk-events.jsonl")


@pytest.mark.asyncio
async def test_risk_discovery_cli_official_public_smoke_builds_temp_config(monkeypatch, tmp_path) -> None:
    import bin.risk_discovery as risk_discovery

    calls = {}
    smoke_config = tmp_path / "official-public-smoke.yaml"
    smoke_config.write_text("version: '2.0'\nsources: []\n", encoding="utf-8")

    async def fake_pipeline_run(self, company, **kwargs):
        calls["company"] = company
        calls["kwargs"] = kwargs
        return SimpleNamespace(
            to_dict=lambda include_plan=False: {
                "ok": True,
                "company": company,
                "configured_source": kwargs["search_engine"].initialized_with,
            }
        )

    monkeypatch.setattr(risk_discovery.RiskDiscoveryPipeline, "run", fake_pipeline_run)
    monkeypatch.setattr(
        "adapters.multi_datasource.SearchEngine",
        FakeCliSearchEngine,
    )
    monkeypatch.setattr(
        risk_discovery,
        "build_official_public_smoke_config",
        lambda: smoke_config,
    )

    args = risk_discovery.build_parser().parse_args(
        [
            "Demo Official Public Co., Ltd.",
            "--official-public-smoke",
        ]
    )

    payload = await risk_discovery.run(args)

    assert payload["ok"] is True
    assert payload["configured_source"] == str(smoke_config)
    assert calls["kwargs"]["records"] is None
    assert calls["kwargs"]["existing_plan"].tasks[0].source_hint == "gleif_lei_public_api"
    assert calls["kwargs"]["fanout_rounds"] == 1
    assert calls["kwargs"]["identifier_fanout_only"] is True


@pytest.mark.asyncio
async def test_risk_discovery_cli_rejects_config_with_offline_fixture(tmp_path) -> None:
    import bin.risk_discovery as risk_discovery

    args = risk_discovery.build_parser().parse_args(
        [
            "Demo Invalid Co., Ltd.",
            "--config",
            str(tmp_path / "datasources.yaml"),
            "--offline-fixture",
        ]
    )

    with pytest.raises(SystemExit, match="mutually exclusive"):
        await risk_discovery.run(args)


@pytest.mark.asyncio
async def test_risk_discovery_cli_rejects_official_smoke_with_fixture() -> None:
    import bin.risk_discovery as risk_discovery

    args = risk_discovery.build_parser().parse_args(
        [
            "Demo Invalid Co., Ltd.",
            "--official-public-smoke",
            "--fixture-pack",
        ]
    )

    with pytest.raises(SystemExit, match="mutually exclusive"):
        await risk_discovery.run(args)


@pytest.mark.asyncio
async def test_risk_discovery_cli_rejects_fixture_mode_conflict() -> None:
    import bin.risk_discovery as risk_discovery

    args = risk_discovery.build_parser().parse_args(
        [
            "Demo Invalid Co., Ltd.",
            "--offline-fixture",
            "--fixture-pack",
        ]
    )

    with pytest.raises(SystemExit, match="mutually exclusive"):
        await risk_discovery.run(args)
