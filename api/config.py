#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 统一配置中心
所有模块共享的配置入口，支持环境变量覆盖和热更新。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import logging

_logger = logging.getLogger("wst.config")


def _safe_int(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, str(default)))
    except (ValueError, TypeError):
        _logger.warning("Invalid int for %s, using default %d", env, default)
        return default


def _safe_float(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, str(default)))
    except (ValueError, TypeError):
        _logger.warning("Invalid float for %s, using default %.1f", env, default)
        return default

# ── 路径 ──
SKILL_DIR = Path(__file__).resolve().parent.parent
SUB_SKILLS_DIR = SKILL_DIR / "sub-skills"
OUTPUT_DIR = SKILL_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def ensure_output_dir() -> Path:
    """创建输出目录（延迟创建，避免 import 副作用）"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR

# ── API 配置 ──
API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
API_BASE = os.environ.get(
    "DEEPSEEK_BASE_URL",
    os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
)
DEFAULT_MODEL = os.environ.get("WALLSTREET_MODEL", "deepseek-chat")
DEFAULT_CONCURRENCY = _safe_int("WALLSTREET_CONCURRENCY", 5)
MAX_TOKENS = _safe_int("WALLSTREET_MAX_TOKENS", 8192)
TEMPERATURE = _safe_float("WALLSTREET_TEMPERATURE", 0.3)
API_TIMEOUT_SECONDS = _safe_int("WALLSTREET_TIMEOUT", 300)

# ── Agent 预算 ──
AGENT_BUDGET_TOKENS = 8000
SURVEY_BUDGET_TOKENS = 60000
CONTEXT_WINDOW = {
    "phase1_to_phase2": 2000,
    "phase_to_phase3": 3000,
    "summary_brief": 1500,
    "risk_brief": 1000,
}

# ── 角色配置 ──
ROLE_FILE_MAP: dict[str, str] = {
    "zhang-tie-zhu": "zhang-tie-zhu.md",
    "li-ming-yuan": "li-ming-yuan.md",
    "wang-si-yuan": "wang-si-yuan.md",
    "zhao-gang": "zhao-gang.md",
    "ma-li-quan": "ma-li-quan.md",
    "zhou-tong": "zhou-tong.md",
    "zheng-shen-zhi": "zheng-shen-zhi.md",
    "wu-de-hou": "wu-de-hou.md",
    "liu-wen-hua": "liu-wen-hua.md",
    "yan-hao-kan": "yan-hao-kan.md",
    "chen-zhi-yuan": "chen-zhi-yuan.md",
    "qian-shou-zheng": "qian-shou-zheng.md",
    "an-shao": "an-shao.md",
}

# 角色中文名映射（供 CLI 帮助文本和日志显示使用）
ROLE_NAME_MAP: dict[str, str] = {
    "zhang-tie-zhu": "张铁柱",
    "li-ming-yuan": "李明远",
    "wang-si-yuan": "王思远",
    "zhao-gang": "赵刚",
    "ma-li-quan": "马力全",
    "zhou-tong": "周通",
    "zheng-shen-zhi": "郑慎之",
    "wu-de-hou": "吴德厚",
    "liu-wen-hua": "刘文华",
    "yan-hao-kan": "颜好看",
    "chen-zhi-yuan": "陈志远",
    "qian-shou-zheng": "钱守正",
    "an-shao": "暗哨",
}

# ── 模式模板 ──
MODE_TEMPLATES: dict[str, dict[str, Any]] = {
    "simple": {
        "phase1": ["zhang-tie-zhu"],
        "phase2": [],
        "phase3": [],
        "desc": "简单查询：企业工商信息",
    },
    "standard": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua"],
        "desc": "标准尽调：工商+财务+行业+风险+人员",
    },
    "deep": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang", "ma-li-quan"],
        "phase2": ["zheng-shen-zhi", "wu-de-hou"],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "conditional_branches": True,
        "desc": "深度尽调：全角色 + 条件分支",
    },
    "sme": {
        "phase1": ["zhang-tie-zhu", "li-ming-yuan", "zhao-gang"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": ["liu-wen-hua"],
        "desc": "中小企业：基础工商+替代数据+基础风险",
    },
    "people": {
        "phase1": ["ma-li-quan", "zhou-tong"],
        "phase2": ["zheng-shen-zhi"],
        "phase3": [],
        "desc": "人员背调：OSINT+交叉验证",
    },
    "report": {
        "phase1": [],
        "phase2": [],
        "phase3": ["liu-wen-hua", "yan-hao-kan"],
        "desc": "报告生成：仅格式化输出",
    },
}

# ── 模型价格 ──
PRICING: dict[str, dict[str, float]] = {
    "deepseek": {"input": 1.0, "output": 2.0},
    "deepseek-v3": {"input": 1.0, "output": 2.0},
    "deepseek-v4": {"input": 1.0, "output": 2.0},
    "deepseek-r1": {"input": 4.0, "output": 16.0},
    "gpt-4o": {"input": 17.5, "output": 70.0},
    "gpt-4o-mini": {"input": 1.05, "output": 4.2},
    "mimo-v2.5-pro": {"input": 2.0, "output": 8.0},
    "mimo-v2.5-flash": {"input": 0.5, "output": 2.0},
}
DEFAULT_PRICE = {"input": 1.0, "output": 2.0}


def get_api_key() -> str:
    """获取 API Key，DEEPSEEK > OPENAI 回退"""
    return API_KEY


def get_api_base() -> str:
    return API_BASE


def reload_config():
    """重新加载环境变量（支持热更新）"""
    global API_KEY, API_BASE, DEFAULT_MODEL, DEFAULT_CONCURRENCY
    global MAX_TOKENS, TEMPERATURE, API_TIMEOUT_SECONDS
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    API_BASE = os.environ.get(
        "DEEPSEEK_BASE_URL",
        os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
    )
    DEFAULT_MODEL = os.environ.get("WALLSTREET_MODEL", "deepseek-chat")
    DEFAULT_CONCURRENCY = _safe_int("WALLSTREET_CONCURRENCY", 5)
    MAX_TOKENS = _safe_int("WALLSTREET_MAX_TOKENS", 8192)
    TEMPERATURE = _safe_float("WALLSTREET_TEMPERATURE", 0.3)
    API_TIMEOUT_SECONDS = _safe_int("WALLSTREET_TIMEOUT", 300)
