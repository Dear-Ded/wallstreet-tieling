#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 统一配置中心
所有模块共享的配置入口，支持环境变量覆盖和热更新。

配置加载顺序（优先级从低到高）:
  1. 默认值（本文件中的常量）
  2. 配置文件（config.yaml，可选）
  3. 环境变量（最高优先级）

使用方法:
  from api.config import print_config, validate_config
  
  # 打印当前配置
  print_config()
  
  # 验证配置
  errors = validate_config()
  
  # 重新加载
  reload_config()
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from typing import Any
import logging

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_logger = logging.getLogger("wst.config")


def _safe_print(message: Any = "") -> None:
    """Print Unicode status text without crashing on legacy Windows codepages."""
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)


# ── 配置文件路径 ───────────────────────────────────────────────────────
_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"
_CONFIG_LOADED = False
_CONFIG_CACHE: dict[str, Any] = {}


def _load_config_file() -> dict[str, Any]:
    """加载配置文件（config.yaml）"""
    global _CONFIG_LOADED, _CONFIG_CACHE
    
    if _CONFIG_LOADED:
        return _CONFIG_CACHE
    
    _CONFIG_CACHE = {}
    
    if not _HAS_YAML:
        _logger.warning("PyYAML 未安装，无法加载 config.yaml。请运行: pip install pyyaml")
        _CONFIG_LOADED = True
        return _CONFIG_CACHE
    
    if not _CONFIG_FILE.exists():
        _logger.info(f"配置文件不存在: {_CONFIG_FILE}")
        _CONFIG_LOADED = True
        return _CONFIG_CACHE
    
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f) or {}
        _logger.info(f"✅ 已加载配置文件: {_CONFIG_FILE}")
    except Exception as e:
        _logger.error(f"加载配置文件失败: {e}")
    
    _CONFIG_LOADED = True
    return _CONFIG_CACHE


def _get_config_value(key: str, default: Any) -> Any:
    """获取配置值（加载顺序: 配置文件 → 环境变量 → 默认值）"""
    # 1. 从配置文件读取
    config = _load_config_file()
    file_value = config.get(key)
    if file_value is not None:
        return file_value
    
    # 2. 从环境变量读取（自动转换类型）
    env_key = key.upper()
    env_value = os.environ.get(env_key)
    if env_value is not None:
        # 自动类型转换
        if isinstance(default, bool):
            return env_value.lower() in ("true", "1", "yes", "on")
        elif isinstance(default, int):
            try:
                return int(env_value)
            except ValueError:
                _logger.warning(f"环境变量 {env_key} 不是有效的整数，使用默认值: {default}")
                return default
        elif isinstance(default, float):
            try:
                return float(env_value)
            except ValueError:
                _logger.warning(f"环境变量 {env_key} 不是有效的浮点数，使用默认值: {default}")
                return default
        else:
            return env_value
    
    # 3. 使用默认值
    return default


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


def ensure_output_dir() -> Path:
    """创建输出目录（延迟创建，避免 import 副作用）"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR


# ── API 配置 ──
def _get_api_key() -> str:
    """获取 API Key（支持配置文件 + 环境变量）"""
    # 从配置文件读取
    config = _load_config_file()
    api_key = config.get("api_key") or config.get("API_KEY")
    if api_key:
        return api_key
    
    # 从环境变量读取
    return os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))


def _get_api_base() -> str:
    """获取 API Base URL"""
    config = _load_config_file()
    api_base = config.get("api_base") or config.get("API_BASE")
    if api_base:
        return api_base
    
    return os.environ.get(
        "DEEPSEEK_BASE_URL",
        os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
    )


API_KEY = _get_api_key()
API_BASE = _get_api_base()
DEFAULT_MODEL = _get_config_value("DEFAULT_MODEL", "deepseek-chat")
DEFAULT_CONCURRENCY = _get_config_value("DEFAULT_CONCURRENCY", 5)
MAX_TOKENS = _get_config_value("MAX_TOKENS", 8192)
TEMPERATURE = _get_config_value("TEMPERATURE", 0.3)
API_TIMEOUT_SECONDS = _get_config_value("API_TIMEOUT_SECONDS", 300)

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
    global _CONFIG_LOADED, _CONFIG_CACHE
    
    # 清除配置文件缓存
    _CONFIG_LOADED = False
    _CONFIG_CACHE = {}
    
    # 重新加载
    API_KEY = _get_api_key()
    API_BASE = _get_api_base()
    DEFAULT_MODEL = _get_config_value("DEFAULT_MODEL", "deepseek-chat")
    DEFAULT_CONCURRENCY = _get_config_value("DEFAULT_CONCURRENCY", 5)
    MAX_TOKENS = _get_config_value("MAX_TOKENS", 8192)
    TEMPERATURE = _get_config_value("TEMPERATURE", 0.3)
    API_TIMEOUT_SECONDS = _get_config_value("API_TIMEOUT_SECONDS", 300)
    
    _logger.info("✅ 配置已重新加载")


def print_config(show_sensitive: bool = False) -> None:
    """打印当前生效的配置（用于调试）
    
    Args:
        show_sensitive: 是否显示敏感信息（API Key 等）
    """
    config = {
        "API": {
            "API_KEY": "***" + API_KEY[-4:] if API_KEY and not show_sensitive else API_KEY or "(未设置)",
            "API_BASE": API_BASE,
            "DEFAULT_MODEL": DEFAULT_MODEL,
            "DEFAULT_CONCURRENCY": DEFAULT_CONCURRENCY,
            "MAX_TOKENS": MAX_TOKENS,
            "TEMPERATURE": TEMPERATURE,
            "API_TIMEOUT_SECONDS": API_TIMEOUT_SECONDS,
        },
        "PATHS": {
            "SKILL_DIR": str(SKILL_DIR),
            "SUB_SKILLS_DIR": str(SUB_SKILLS_DIR),
            "OUTPUT_DIR": str(OUTPUT_DIR),
        },
        "AGENT": {
            "AGENT_BUDGET_TOKENS": AGENT_BUDGET_TOKENS,
            "SURVEY_BUDGET_TOKENS": SURVEY_BUDGET_TOKENS,
        },
    }
    
    _safe_print("=" * 80)
    _safe_print("📋 wallstreet-tieling 当前配置")
    _safe_print("=" * 80)
    _safe_print(json.dumps(config, indent=2, ensure_ascii=False))
    _safe_print("=" * 80)
    _safe_print(f"📁 配置文件: {_CONFIG_FILE} ({'存在' if _CONFIG_FILE.exists() else '不存在'})")
    _safe_print(f"🔧 环境变量前缀: DEEPSEEK_ / OPENAI_ / WALLSTREET_")
    _safe_print("=" * 80)


def validate_config() -> list[str]:
    """验证配置（启动时调用）
    
    Returns:
        错误消息列表（空列表表示验证通过）
    """
    errors = []
    warnings = []
    
    # 检查 API Key
    if not API_KEY:
        errors.append("❌ API_KEY 未设置！请设置环境变量 DEEPSEEK_API_KEY 或在 config.yaml 中配置")
    
    # 检查 API Base URL
    if not API_BASE:
        errors.append("❌ API_BASE 未设置！")
    
    # 检查输出目录
    if not OUTPUT_DIR.exists():
        warnings.append(f"⚠️  输出目录不存在: {OUTPUT_DIR}（将自动创建）")
        try:
            ensure_output_dir()
            warnings[-1] = f"✅ 已创建输出目录: {OUTPUT_DIR}"
        except Exception as e:
            errors.append(f"❌ 无法创建输出目录: {e}")
    
    # 检查 sub-skills 目录
    if not SUB_SKILLS_DIR.exists():
        warnings.append(f"⚠️  sub-skills 目录不存在: {SUB_SKILLS_DIR}")
    
    # 检查配置文件（可选）
    if _CONFIG_FILE.exists():
        try:
            if _HAS_YAML:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    yaml.safe_load(f)
                warnings.append(f"✅ 配置文件格式正确: {_CONFIG_FILE}")
            else:
                warnings.append("⚠️  PyYAML 未安装，无法验证配置文件格式")
        except Exception as e:
            errors.append(f"❌ 配置文件格式错误: {e}")
    
    # 打印验证结果
    _safe_print("=" * 80)
    _safe_print("🔍 配置验证结果")
    _safe_print("=" * 80)
    
    if warnings:
        _safe_print("\n📢 警告:")
        for w in warnings:
            _safe_print(f"  {w}")
    
    if errors:
        _safe_print("\n❌ 错误:")
        for e in errors:
            _safe_print(f"  {e}")
        _safe_print("\n⚠️  配置验证失败，请修复上述错误后再启动。")
    else:
        _safe_print("\n✅ 配置验证通过！")
    
    _safe_print("=" * 80)
    
    return errors


# ── 启动时自动验证 ───────────────────────────────────────────────────────
if __name__ != "__main__":
    # 模块导入时自动验证
    _validation_errors = validate_config()
    if _validation_errors:
        _logger.warning(f"配置验证失败: {len(_validation_errors)} 个错误")
