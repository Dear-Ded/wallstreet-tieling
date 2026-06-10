#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 — Agent 注册中心
管理 13 个 Agent 实例的生命周期、状态查询、通信路由。
"""
from __future__ import annotations

import logging
from typing import Optional

from .agent import DueDiligenceAgent, AgentMessage, AgentState, Mood
from .personality import get_personality, get_all_agent_ids, get_receptionist_greeting
from .utils import load_skill
from . import config

logger = logging.getLogger("wst.registry")


class AgentRegistry:
    """Agent 注册中心 —— 13 个 Agent 的中央管理器"""

    def __init__(self):
        self._agents: dict[str, DueDiligenceAgent] = {}
        self._message_queue: list[AgentMessage] = []
        self._team_chat_log: list[str] = []  # 团队闲聊记录

    # ── 生命周期 ──
    def boot(self, agent_ids: list[str] | None = None):
        """启动 Agent 实例"""
        ids = agent_ids or get_all_agent_ids()
        for aid in ids:
            profile = get_personality(aid)
            filename = config.ROLE_FILE_MAP.get(aid, f"{aid}.md")
            skill_content = load_skill(filename)
            agent = DueDiligenceAgent(
                agent_id=aid,
                profile=profile,
                sub_skill_content=skill_content,
            )
            self._agents[aid] = agent
        logger.info("Booted %d agents: %s", len(self._agents),
                     ", ".join(f"{a.name}({a.agent_id})" for a in self._agents.values()))

    def wake_agents(self, agent_ids: list[str], target: str):
        """唤醒指定 Agent，生成开工问候"""
        for aid in agent_ids:
            agent = self.get(aid)
            if agent and agent.state == AgentState.IDLE:
                agent.state = AgentState.WORKING
                greeting = get_receptionist_greeting(aid, target)
                self._team_chat_log.append(f"[{agent.name}] {greeting}")

    # ── CRUD ──
    def get(self, agent_id: str) -> Optional[DueDiligenceAgent]:
        return self._agents.get(agent_id)

    def get_all(self) -> list[DueDiligenceAgent]:
        return list(self._agents.values())

    def get_many(self, agent_ids: list[str]) -> list[DueDiligenceAgent]:
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_by_state(self, state: AgentState) -> list[DueDiligenceAgent]:
        return [a for a in self._agents.values() if a.state == state]

    def set_state(self, agent_id: str, state: AgentState):
        agent = self.get(agent_id)
        if agent:
            agent.state = state

    def set_many_states(self, agent_ids: list[str], state: AgentState):
        for aid in agent_ids:
            self.set_state(aid, state)

    # ── 通信 ──
    def route_message(self, msg: AgentMessage):
        """路由消息到目标 Agent"""
        self._message_queue.append(msg)
        if msg.to_agent == "broadcast":
            for agent in self._agents.values():
                if agent.agent_id != msg.from_agent:
                    agent.receive_message(msg)
        elif msg.to_agent in self._agents:
            self._agents[msg.to_agent].receive_message(msg)

    def broadcast(self, from_agent: str, content: str, msg_type: str = "observation",
                  priority: int = 0):
        """广播消息给所有 Agent"""
        agent = self.get(from_agent)
        if agent:
            msg = agent.send_message("broadcast", msg_type, content, priority=priority)
            self.route_message(msg)

    def process_all_inboxes(self):
        """处理所有 Agent 的收件箱"""
        for agent in self._agents.values():
            replies = agent.process_inbox()
            for reply in replies:
                self.route_message(reply)

    # ── 团队动态 ──
    def team_chat_snapshot(self, max_lines: int = 10) -> str:
        """获取团队闲聊记录"""
        recent = self._team_chat_log[-max_lines:]
        return "\n".join(recent)

    def add_team_chat(self, line: str):
        self._team_chat_log.append(line)

    # ── 状态快照 ──
    def status_report(self) -> str:
        """生成团队状态报告"""
        lines = ["═══ 办事处状态 ═══"]
        for agent in self._agents.values():
            mood_icon = {
                Mood.CONFIDENT: "😤", Mood.FRUSTRATED: "😤",
                Mood.ALERT: "🔍", Mood.CURIOUS: "🤔",
                Mood.TIRED: "😮‍💨", Mood.EXCITED: "🔥",
                Mood.NEUTRAL: "👌",
            }.get(agent.emotion.mood, "❓")
            state_icon = {
                AgentState.IDLE: "💤", AgentState.WORKING: "🔄",
                AgentState.WAITING: "⏳", AgentState.REVIEWING: "🔎",
                AgentState.DEGRADED: "⚠️", AgentState.DONE: "✅",
            }.get(agent.state, "❓")
            key_findings = len(agent.memory.key_findings)
            lines.append(
                f"  {state_icon}{mood_icon} {agent.name}({agent.nickname})"
                f" | 信心:{agent.emotion.confidence:.0%}"
                f" | 发现:{key_findings}条"
                f" | {agent.emotion.mood.value}"
            )
        lines.append("═" * 25)
        return "\n".join(lines)

    # ── 内存清理 ──
    def shutdown(self):
        """关停所有 Agent，清理状态"""
        for agent in self._agents.values():
            agent.state = AgentState.IDLE
            agent.memory = type(agent.memory)()
            agent.emotion = type(agent.emotion)()
        self._message_queue.clear()
        self._team_chat_log.clear()
