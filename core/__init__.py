"""wallstreet-tieling v4.0 — 平台无关尽调引擎核心"""
from .interfaces import LLMProvider, LLMResponse, ToolProvider, ToolResult, OutputProvider
from .engine import Engine, PlatformAdapter, MODE_TEMPLATES
from .roles import AUTHORITIES, RoleAuthority

__all__ = [
    "Engine", "PlatformAdapter",
    "LLMProvider", "LLMResponse", "ToolProvider", "ToolResult", "OutputProvider",
    "AUTHORITIES", "RoleAuthority", "MODE_TEMPLATES",
]
