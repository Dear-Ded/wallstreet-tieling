#!/usr/bin/env python3
"""Runtime release contract for portal, plugins, and marketplace checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from api.personality import build_persona_surface_brief


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VARIANTS_PATH = PROJECT_ROOT / "release" / "variants.yaml"


def load_release_contract(path: str | Path | None = None) -> dict[str, Any]:
    """Load and normalize the release/variant matrix for API consumers."""
    target = Path(path) if path else DEFAULT_VARIANTS_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    product = _dict(data.get("product"))
    variants = _dict(data.get("variants"))
    gates = _dict(data.get("release_gates"))
    normalized_variants = {
        name: _variant_payload(name, _dict(variant))
        for name, variant in sorted(variants.items())
    }
    readiness_counts: dict[str, int] = {}
    for variant in normalized_variants.values():
        readiness = str(variant.get("readiness") or "unknown")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1

    return {
        "type": "release_contract",
        "version": "0.5.0",
        "product": {
            "name": product.get("name", "wallstreet-tieling"),
            "display_name": product.get("display_name", "Wallstreet Tieling"),
            "positioning": product.get("positioning", "Enterprise Intelligence & Risk Discovery System"),
            "public_portal_repo": product.get("public_portal_repo"),
            "shared_core": _string_list(product.get("shared_core")),
        },
        "persona_surface": build_persona_surface_brief(),
        "variants": normalized_variants,
        "summary": {
            "variant_count": len(normalized_variants),
            "readiness_counts": readiness_counts,
            "stable_or_beta_count": sum(
                1
                for variant in normalized_variants.values()
                if variant.get("readiness") in {"stable", "beta"}
            ),
            "alpha_count": readiness_counts.get("alpha", 0),
            "planned_count": readiness_counts.get("planned", 0),
        },
        "release_gates": {
            name: _string_list(rules)
            for name, rules in sorted(gates.items())
        },
    }


def release_readiness_brief(path: str | Path | None = None) -> dict[str, Any]:
    """Return a plain product brief without forcing callers to parse YAML."""
    contract = load_release_contract(path)
    blockers: list[dict[str, Any]] = []
    readyish: list[str] = []
    for name, variant in contract["variants"].items():
        readiness = variant.get("readiness")
        if readiness in {"stable", "beta"}:
            readyish.append(name)
        else:
            blockers.append(
                {
                    "variant": name,
                    "readiness": readiness,
                    "next_gate": variant.get("next_gate", []),
                }
            )
    return {
        "type": "release_readiness_brief",
        "version": contract["version"],
        "positioning": contract["product"]["positioning"],
        "persona_surface": contract["persona_surface"],
        "readyish_variants": readyish,
        "blockers": blockers,
        "next_focus": _next_focus(blockers),
        "contract": contract,
    }


def _variant_payload(name: str, variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": variant.get("display_name", name),
        "audience": variant.get("audience", ""),
        "entrypoints": _string_list(variant.get("entrypoints")),
        "packaging": _string_list(variant.get("packaging")),
        "required_capabilities": _string_list(variant.get("required_capabilities")),
        "readiness": str(variant.get("readiness") or "planned"),
        "next_gate": _string_list(variant.get("next_gate")),
    }


def _next_focus(blockers: list[dict[str, Any]]) -> list[str]:
    focus: list[str] = []
    for blocker in blockers:
        for gate in blocker.get("next_gate", [])[:2]:
            item = f"{blocker['variant']}: {gate}"
            if item not in focus:
                focus.append(item)
    return focus[:8]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []
