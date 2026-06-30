#!/usr/bin/env python3
"""统一监督模块 — 向后兼容聚合入口 v0.5.0

v0.5.0 重构: 质量规则引擎已拆分到 api/quality_rules.py。
本文档保留 import 聚合入口，现有代码无需修改即可继续使用。
"""
from __future__ import annotations

# 从新模块导入，保持向后兼容
from .quality_rules import QualityRules, Violation

__all__ = ["QualityRules", "Violation"]
