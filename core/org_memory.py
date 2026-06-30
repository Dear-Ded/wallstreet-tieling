#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .storage_paths import runtime_state_path


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

import re

def secure_filename(filename: str) -> str:
    """
    生成安全的文件名（防止路径遍历攻击）
    
    Args:
        filename: 原始文件名
        
    Returns:
        安全的文件名（只保留字母、数字、下划线、横线）
    """
    # 替换路径遍历字符
    filename = filename.replace("..", "_")
    filename = filename.replace("/", "_")
    filename = filename.replace("\\", "_")
    filename = filename.replace("~", "_")
    
    # 只保留安全字符
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    
    # 限制长度
    return filename[:50]


# ═══════════════════════════════════════════════════════════
#  存储路径
# ═══════════════════════════════════════════════════════════

def _memory_root() -> Path:
    home = runtime_state_path("memory", filename_env_var="WST_MEMORY_DIR")
    home.mkdir(parents=True, exist_ok=True)
    return home


def _ensure_dirs():
    root = _memory_root()
    for d in ["investigations", "patterns", "agents", "chemistry", "tools"]:
        (root / d).mkdir(exist_ok=True)
    return root


# ═══════════════════════════════════════════════════════════
#  OrgMemory
# ═══════════════════════════════════════════════════════════

class OrgMemory:
    """组织记忆 — 每次尽调完成后调用 record()"""

    def __init__(self):
        self.root = _ensure_dirs()

    # ── 记录 ──

    def record(self, result: dict) -> dict:
        """记录一次尽调结果到五层存储"""
        ts = time.strftime("%Y%m%d-%H%M%S")
        slug = secure_filename(result.get("target", "unknown"))[:50]

        # 1. investigations/
        inv = {
            "id": f"inv-{ts}",
            "target": result.get("target", ""),
            "mode": result.get("mode", "standard"),
            "date": time.strftime("%Y-%m-%d"),
            "bus_summary": result.get("bus_summary", {}),
            "branches_triggered": len(result.get("branches_triggered", [])),
            "roles_activated": result.get("roles_activated", []),
            "commissar_stats": result.get("commissar_stats", {}),
            "metrics_count": len(result.get("metrics", [])),
        }
        inv_path = self.root / "investigations" / f"{ts}-{slug}.json"
        inv_path.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")

        # 2-5: patterns/agents/chemistry/tools — 增量更新
        self._update_agents(result)
        self._update_chemistry(result)

        return inv

    # ── 查询 ──

    def get_recent(self, n: int = 10) -> list[dict]:
        """最近 N 次调查"""
        inv_dir = self.root / "investigations"
        files = sorted(inv_dir.glob("*.json"), reverse=True)[:n]
        return [json.loads(f.read_text(encoding="utf-8")) for f in files]

    def get_agent_stats(self, agent_id: str) -> dict | None:
        """获取单个角色的表现档案"""
        path = self.root / "agents" / f"{agent_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def get_sector_patterns(self, sector: str, min_samples: int = 5) -> dict | None:
        """获取行业风险模式 (需要 ≥5 样本才生效)"""
        path = self.root / "patterns" / f"sector-{sector}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("sample_size", 0) >= min_samples:
                return data
        return None

    def build_injection(self) -> str:
        """构建下次尽调的 prompt 注入文本"""
        parts = []
        recent = self.get_recent(3)
        if recent:
            targets = ", ".join(r.get("target", "") for r in recent[:3])
            parts.append(f"(组织记忆: 最近调查过 {targets})")

        # Agent tips
        for aid in ["zhang-tie-zhu", "li-ming-yuan", "zhao-gang", "ma-li-quan"]:
            stats = self.get_agent_stats(aid)
            if stats and stats.get("total_tasks", 0) >= 5:
                sr = stats.get("success_rate", 0)
                strengths = stats.get("strengths", [])
                if strengths:
                    parts.append(f"[{aid}] 成功率 {sr:.0%}, 擅长 {', '.join(strengths[:2])}")

        return "\n".join(parts) if parts else ""

    def reset(self) -> None:
        """清除全部记忆"""
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        self.root = _ensure_dirs()

    # ── 内部更新 ──

    def _update_agents(self, result: dict) -> None:
        stats = result.get("commissar_stats", {})
        metrics = result.get("metrics", [])
        if not stats and not metrics:
            return

        # 聚合每个 agent 的表现
        agent_data: dict[str, dict] = defaultdict(lambda: {
            "total_tasks": 0, "successes": 0, "total_violations": 0, "total_tokens": 0,
        })

        for m in metrics:
            aid = m.get("agent", "")
            agent_data[aid]["total_tasks"] += 1
            if m.get("ok"):
                agent_data[aid]["successes"] += 1
            agent_data[aid]["total_tokens"] += m.get("tok", 0)

        for aid, dd in agent_data.items():
            path = self.root / "agents" / f"{aid}.json"
            existing = {}
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))

            existing["agent_id"] = aid
            existing["total_tasks"] = existing.get("total_tasks", 0) + dd["total_tasks"]
            existing["success_rate"] = (
                (existing.get("successes", 0) + dd["successes"]) /
                max(existing["total_tasks"], 1)
            )
            existing["successes"] = existing.get("successes", 0) + dd["successes"]
            existing["avg_tokens"] = (
                existing.get("total_tokens", 0) + dd["total_tokens"]
            ) / max(existing["total_tasks"], 1)
            existing["total_tokens"] = existing.get("total_tokens", 0) + dd["total_tokens"]
            existing["strengths"] = existing.get("strengths", [])
            existing["evolution"] = existing.get("evolution", [])
            existing["evolution"].append({
                "date": time.strftime("%Y-%m"),
                "success_rate": existing["success_rate"],
            })

            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_chemistry(self, result: dict) -> None:
        """更新角色协作关系 — pair-scores"""
        branches = result.get("branches_triggered", [])
        if not branches:
            return

        path = self.root / "chemistry" / "pair-scores.json"
        scores: dict[str, dict] = {}
        if path.exists():
            scores = json.loads(path.read_text(encoding="utf-8"))

        for b in branches:
            signal = b.get("signal", "")
            role = b.get("append_role", "")
            pair_key = f"{signal}::{role}"
            pair_data = scores.get(pair_key, {"cooperation_count": 0, "signal": signal, "role": role})
            pair_data["cooperation_count"] += 1
            scores[pair_key] = pair_data

        path.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
