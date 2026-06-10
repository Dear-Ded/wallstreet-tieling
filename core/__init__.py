"""wallstreet-tieling v4.0 — 平台无关尽调引擎核心"""
from .interfaces import LLMProvider, LLMResponse, ToolProvider, ToolResult, OutputProvider, PlatformAdapter
from .engine import Engine
from .rules import MODE_TEMPLATES, NO_FABRICATION_RULE, NO_FABRICATION_TAGLINE
from .roles import AUTHORITIES, RoleAuthority

__all__ = [
    "Engine", "PlatformAdapter",
    "LLMProvider", "LLMResponse", "ToolProvider", "ToolResult", "OutputProvider",
    "AUTHORITIES", "RoleAuthority", "MODE_TEMPLATES",
    "NO_FABRICATION_RULE", "NO_FABRICATION_TAGLINE",
]
