#!/usr/bin/env python3
"""Project pytest fixtures that avoid host-specific temp directory failures."""
from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Iterator

import pytest


def _safe_tmp_parent() -> Path | None:
    local_temp = Path.home() / "AppData" / "Local" / "Temp"
    return local_temp if local_temp.exists() else None


def _safe_prefix(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return (cleaned or "test")[:48] + "-"


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    """Return a normal tempfile.mkdtemp path instead of pytest's numbered root.

    Some locked-down Windows sessions create pytest's default
    ``pytest-of-<user>`` directory with an ACL that the same process cannot
    list during setup or session cleanup. This fixture keeps tests isolated
    while bypassing that host-specific TempPathFactory failure mode.
    """
    parent = _safe_tmp_parent() or Path(tempfile.gettempdir())
    path = parent / f"{_safe_prefix(request.node.name)}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolated_runtime_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Keep risk-event / monitor / memory stores out of the real home directory.

    Without this, every test run (and every xdist worker) appends to
    ~/.workbuddy/wallstreet-tieling/*.jsonl; concurrent runs corrupt the shared
    JSONL and later runs fail with JSONDecodeError.
    """
    state = Path(tempfile.mkdtemp(prefix="wst-state-"))
    monkeypatch.setenv("WST_STATE_DIR", str(state))
    monkeypatch.delenv("WORKBUDDY_STATE_DIR", raising=False)
    try:
        yield state
    finally:
        shutil.rmtree(state, ignore_errors=True)


@pytest.fixture
def sample_agent_id():
    """Standard due-diligence role id."""
    return "zhang-tie-zhu"


@pytest.fixture
def sample_target():
    """Default due-diligence target."""
    return "测试科技有限公司"


pytest_plugins = []
