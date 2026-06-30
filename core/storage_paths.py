#!/usr/bin/env python3
"""Writable runtime storage paths for local product state."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


APP_DIR_NAME = "wallstreet-tieling"


def runtime_state_root(*, env_var: str = "WST_STATE_DIR") -> Path:
    """Return a writable root for local state, with temp fallback."""
    candidates: list[Path] = []
    configured = os.environ.get(env_var) or os.environ.get("WORKBUDDY_STATE_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path.home() / ".workbuddy" / APP_DIR_NAME)
    candidates.append(Path(tempfile.gettempdir()) / APP_DIR_NAME)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue

    fallback = Path(tempfile.gettempdir()) / APP_DIR_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def runtime_state_path(
    *parts: str,
    env_var: str = "WST_STATE_DIR",
    filename_env_var: str | None = None,
) -> Path:
    """Return a writable file or directory path under the runtime state root."""
    if filename_env_var:
        configured = os.environ.get(filename_env_var)
        if configured:
            path = Path(configured).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    return runtime_state_root(env_var=env_var).joinpath(*parts)
