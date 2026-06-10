#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 工具函数"""
from __future__ import annotations

import re
import logging
from pathlib import Path

from . import config

logger = logging.getLogger("wst.utils")


def slug(s: str, max_len: int = 40) -> str:
    """中英文混合 safe slug"""
    s = re.sub(r'[^\w\u4e00-\u9fff]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:max_len] if s else "unknown"


def load_skill(filename: str) -> str:
    """加载 sub-skill markdown 文件"""
    # 防止路径穿越攻击
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        logger.warning("Blocked path traversal attempt: %s", filename)
        return f"# {filename.replace('.md', '')}\n角色定义加载被阻止（路径穿越检测）。"
    path = config.SUB_SKILLS_DIR / safe_name
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("sub-skill not found: %s, using fallback", filename)
    return f"# {filename.replace('.md', '')}\n角色定义缺失，按通用尽调模式执行。"


def load_system_prompt() -> str:
    """加载 SKILL.md 作为系统提示词"""
    path = config.SKILL_DIR / "SKILL.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "你是华尔街驻铁岭办事处的尽调专家。只摆事实，不给建议。"


def extract_numbers_with_unit(text: str) -> list[str]:
    """提取带单位的数字（含个位数如'5亿'）"""
    return re.findall(r'(?<!\d)(\d+(?:\.\d+)?)\s*(?:亿|万|千|百|元|%|％)', text)


def extract_company_ids(text: str) -> list[dict]:
    """从文本中提取 company_id"""
    ids = []
    id_matches = re.findall(
        r'(?:tyc-mcp|qcc-company).*?cid[=:]["\']?(\w+)', text,
        re.IGNORECASE,
    )
    for cid in id_matches:
        ids.append({"source": "extracted", "id": cid})
    return ids
