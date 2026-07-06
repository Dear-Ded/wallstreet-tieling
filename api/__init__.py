#!/usr/bin/env python3
"""wallstreet-tieling API package."""

__all__ = [
    "AgentRegistry",
    "DueDiligenceAgent",
    "Orchestrator",
    "QualityRules",
]


def __getattr__(name: str):
    """Load public API classes lazily so CLI JSON output stays clean."""
    if name == "AgentRegistry":
        from .agent_registry import AgentRegistry

        return AgentRegistry
    if name == "DueDiligenceAgent":
        from .agent import DueDiligenceAgent

        return DueDiligenceAgent
    if name == "Orchestrator":
        from .orchestrator import Orchestrator

        return Orchestrator
    if name == "QualityRules":
        from .quality_rules import QualityRules

        return QualityRules
    raise AttributeError(f"module 'api' has no attribute {name!r}")
