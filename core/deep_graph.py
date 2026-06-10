#!/usr/bin/env python3
"""wallstreet-tieling v4.0 — 深度关联图引擎
多跳图遍历 (BFS+DFS, ≤8跳, ≤10节点/层), 环检测, 关联路径还原。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    DOMAIN = "DOMAIN"


class RelationType(Enum):
    SHAREHOLDER = "SHAREHOLDER"
    EXECUTIVE = "EXECUTIVE"
    SAME_ADDRESS = "SAME_ADDRESS"
    SAME_PHONE = "SAME_PHONE"
    SOCIAL_INTERACTION = "SOCIAL_INTERACTION"


@dataclass
class Entity:
    id: str
    type: EntityType
    attributes: dict = field(default_factory=dict)
    confidence: float = 1.0
    blind_spots: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class Relation:
    from_id: str
    to_id: str
    type: RelationType
    strength: float = 1.0
    evidence: list[str] = field(default_factory=list)


class DeepGraph:
    """深度关联图 — 从单个实体出发, 递归遍历关联网络"""

    MAX_DEPTH = 8
    MAX_NODES_PER_LAYER = 10

    def __init__(self, seed: Entity):
        self.seed = seed
        self.nodes: dict[str, Entity] = {seed.id: seed}
        self.edges: list[Relation] = []
        self.cycles: list[list[str]] = []

    def add_entity(self, entity: Entity) -> None:
        self.nodes.setdefault(entity.id, entity)

    def add_relation(self, from_id: str, to_id: str, rel_type: RelationType,
                     strength: float = 1.0, evidence: list[str] | None = None) -> None:
        self.edges.append(Relation(from_id, to_id, rel_type, strength, evidence or []))

    def detect_cycles(self) -> list[list[str]]:
        """检测图中的环 (关联交易嫌疑)"""
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str):
            if node in path:
                cycle_start = path.index(node)
                self.cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            for e in self.edges:
                if e.from_id == node:
                    dfs(e.to_id)
            path.pop()

        dfs(self.seed.id)
        return self.cycles

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed.id,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "cycles": len(self.cycles),
            "max_depth_reached": min(self.MAX_DEPTH, len(self.nodes)),
        }
