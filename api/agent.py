#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 — Agent 基类与状态管理
真并发 Agent 架构：每个 Agent 拥有独立状态、对话历史、情感追踪、内部独白能力。
"""
from __future__ import annotations

import time
import enum
import random
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("wst.agent")


class Mood(enum.Enum):
    """Agent 情绪状态"""
    CONFIDENT = "confident"       # 自信满满
    FRUSTRATED = "frustrated"     # 烦躁（多次退回）
    ALERT = "alert"               # 警觉（发现风险信号）
    CURIOUS = "curious"           # 好奇（深入调查中）
    TIRED = "tired"               # 疲惫（重复劳动）
    EXCITED = "excited"           # 兴奋（重大发现）
    NEUTRAL = "neutral"           # 平静


class AgentState(enum.Enum):
    """Agent 工作状态"""
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"           # 等待其他 Agent 结果
    REVIEWING = "reviewing"       # 核验中
    DEGRADED = "degraded"         # 已降级
    DONE = "done"


@dataclass
class PersonalityProfile:
    """角色性格档案 — 赋予每个角色"活人感"的核心配置"""
    agent_id: str
    display_name: str
    nickname: str = ""            # 同事间称呼（老王、铁柱）
    age: str = ""                 # 大概年龄段
    background: str = ""          # 背景故事
    traits: list[str] = field(default_factory=list)     # 性格特征
    pet_phrases: list[str] = field(default_factory=list) # 口头禅
    hates: list[str] = field(default_factory=list)      # 讨厌的事
    humor_style: str = "dry"     # 幽默风格: dry/sarcastic/warm/deadpan/none
    emotional_volatility: float = 0.3  # 情绪波动系数 0-1
    colleague_opinions: dict[str, str] = field(default_factory=dict)  # 对其他同事的看法


@dataclass
class AgentMemory:
    """Agent 记忆 — 独立上下文窗口
    key_findings 有硬性上限防止长时间编排 OOM（H1 修复）
    """
    conversation_history: list[dict] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    questions_raised: list[str] = field(default_factory=list)
    notes_to_self: list[str] = field(default_factory=list)  # 内部备忘
    _max_findings: int = 20  # 硬上限，自动裁剪旧记录

    def add_finding(self, finding: str) -> None:
        """添加发现，自动裁剪超出 max_findings 的旧记录"""
        self.key_findings.append(finding)
        if len(self.key_findings) > self._max_findings:
            self.key_findings = self.key_findings[-self._max_findings:]


@dataclass
class EmotionalState:
    """情感状态追踪"""
    mood: Mood = Mood.NEUTRAL
    confidence: float = 0.8       # 信心值 0-1
    frustration: float = 0.0       # 挫败值 0-1（累积→烦躁）
    excitement: float = 0.0        # 兴奋值 0-1
    retry_count: int = 0
    mood_history: list[dict] = field(default_factory=list)

    def update(self,
               success: Optional[bool] = None,
               retry: bool = False,
               discovery: bool = False):
        if success is True:
            self.confidence = min(1.0, self.confidence + 0.05)
            self.frustration = max(0.0, self.frustration - 0.1)
            if discovery:
                self.excitement = min(1.0, self.excitement + 0.2)
        elif success is False:
            self.confidence = max(0.1, self.confidence - 0.1)
            self.frustration = min(1.0, self.frustration + 0.15)

        if retry:
            self.retry_count += 1
            self.frustration = min(1.0, self.frustration + 0.2)

        # 计算主导情绪（基于衰减前的原始值，确保单次 update 的效果完整反映）
        if self.frustration > 0.6:
            self.mood = Mood.FRUSTRATED
        elif self.excitement > 0.5:
            self.mood = Mood.EXCITED
        elif self.confidence > 0.85:
            self.mood = Mood.CONFIDENT
        elif self.frustration > 0.3:
            self.mood = Mood.TIRED
        else:
            self.mood = Mood.NEUTRAL

        # 情绪衰减（随时间自然回落）
        self.excitement = max(0.0, self.excitement - 0.05)
        self.frustration = max(0.0, self.frustration - 0.03)

        # 浮点精度归一化（避免 0.8500000000000001 等累积误差）
        self.confidence = round(self.confidence, 10)
        self.frustration = round(self.frustration, 10)
        self.excitement = round(self.excitement, 10)

        self.mood_history.append({
            "time": time.strftime("%H:%M:%S"),
            "mood": self.mood.value,
            "confidence": round(self.confidence, 2),
            "frustration": round(self.frustration, 2),
        })


@dataclass
class AgentMessage:
    """Agent 间结构化消息"""
    msg_id: str
    from_agent: str             # agent_id
    to_agent: str               # agent_id 或 "broadcast" 或 "self"
    msg_type: str               # request / response / observation / question / gossip / frustration
    content: str                # 自然语言内容
    priority: int = 0           # 0=普通 1=重要 2=紧急
    timestamp: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    thread_id: str = ""         # 关联的消息线程


class DueDiligenceAgent:
    """真并发 Agent 基类 — 每个角色一个独立实例"""

    def __init__(self,
                 agent_id: str,
                 profile: PersonalityProfile,
                 sub_skill_content: str):
        self.agent_id = agent_id
        self.profile = profile
        self.sub_skill = sub_skill_content
        self.state = AgentState.IDLE
        self.emotion = EmotionalState()
        self.memory = AgentMemory()
        self.inbox: list[AgentMessage] = []
        self.outbox: list[AgentMessage] = []
        self._msg_counter = 0

    # ── 身份 ──
    @property
    def name(self) -> str:
        return self.profile.display_name

    @property
    def nickname(self) -> str:
        return self.profile.nickname or self.profile.display_name

    # ── 内部独白 ──
    def inner_monologue(self, context: str = "") -> str:
        """基于当前情绪生成内部独白——让角色有'活人感'的关键"""
        mood = self.emotion.mood
        phrases = []

        if mood == Mood.CONFIDENT:
            phrases = [
                "这事儿我门儿清。",
                "数据摆在这儿，还用说吗？",
                "呵，小菜一碟。",
            ]
        elif mood == Mood.FRUSTRATED:
            phrases = [
                "又来？这破系统能不能行了。",
                f"这是第{self.emotion.retry_count}次了，吴政委你饶了我吧。",
                "老子在华尔街都没受过这气。",
            ]
        elif mood == Mood.ALERT:
            phrases = [
                "嘶……这个得仔细看看。",
                "有问题，绝对有问题。",
                "等会儿，这数字不对劲。",
            ]
        elif mood == Mood.CURIOUS:
            phrases = [
                "有意思，让我再挖一挖。",
                "这事儿背后肯定还有故事。",
                "这么大的体量，钱从哪儿来的？",
            ]
        elif mood == Mood.TIRED:
            phrases = [
                "唉，又得对着屏幕看一整天。",
                "行吧行吧，再来一遍。",
                "暖气片又凉了……",
            ]
        elif mood == Mood.EXCITED:
            phrases = [
                "卧槽，这个发现有意思！",
                "我就说嘛，一眼就看出来有猫腻！",
                "得赶紧告诉钱总！",
            ]
        else:
            phrases = ["嗯，正常推进。", "数据还行。", "继续往下看。"]

        phrase = random.choice(phrases)

        if context:
            phrase = f"[内心: {phrase}（{context}）]"
        else:
            phrase = f"[内心: {phrase}]"
        return phrase

    # ── 对其他 Agent 的看法 ──
    def opinion_of(self, other_agent_id: str, other_name: str,
                   their_result: Optional[dict] = None) -> str:
        """生成对另一个 Agent 的看法/评价"""
        base = self.profile.colleague_opinions.get(other_agent_id, "")

        if their_result and their_result.get("degraded"):
            return f"{other_name}今天状态不太行啊，降级了。下次得让他少喝点酒。"

        if their_result and their_result.get("ok") and their_result.get("text"):
            text_len = len(their_result.get("text", ""))
            if text_len > 1000:
                return f"{other_name}这次干得不错，数据很扎实。"
            return f"{other_name}的输出我看了，还行。"

        return base or f"{other_name}？还行吧，一起共事挺久了。"

    # ── 消息系统 ──
    def _next_msg_id(self) -> str:
        self._msg_counter += 1
        return f"{self.agent_id}-{self._msg_counter:03d}"

    def send_message(self, to: str, msg_type: str, content: str,
                     priority: int = 0, thread_id: str = "") -> AgentMessage:
        """发送消息给另一个 Agent"""
        msg = AgentMessage(
            msg_id=self._next_msg_id(),
            from_agent=self.agent_id,
            to_agent=to,
            msg_type=msg_type,
            content=content,
            priority=priority,
            thread_id=thread_id,
        )
        self.outbox.append(msg)
        return msg

    def receive_message(self, msg: AgentMessage):
        """接收消息"""
        self.inbox.append(msg)
        # 情绪反应：收到紧急消息 → 警觉
        if msg.priority >= 2:
            self.emotion.update(discovery=True)
            self.emotion.mood = Mood.ALERT

    def process_inbox(self) -> list[AgentMessage]:
        """处理收件箱，返回回复消息列表"""
        replies = []
        messages = self.inbox.copy()
        self.inbox.clear()
        for msg in messages:
            if msg.to_agent == self.agent_id:
                reply = self._handle_message(msg)
                if reply:
                    replies.append(reply)
        return replies

    def _handle_message(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理单条消息，子类可覆盖"""
        if msg.msg_type == "question":
            return self.send_message(
                msg.from_agent, "response",
                f"收到，让我看看——{msg.content[:50]}...",
                thread_id=msg.msg_id,
            )
        if msg.msg_type == "gossip":
            # 八卦消息，随机回复
            if random.random() < 0.6:
                return self.send_message(
                    msg.from_agent, "gossip",
                    f"哈哈，{self.nickname}表示关注。",
                    thread_id=msg.msg_id,
                )
        return None

    # ── 闲聊/同事互动 ──
    def casual_remark(self, about: str = "") -> str:
        """生成一句随意的同事间闲话——增强活人感"""
        if not about:
            about = "今天的工作"

        remarks = {
            Mood.CONFIDENT: [
                f"{self.nickname}看了一眼{about}，觉得问题不大。",
                f"呵，{about}这数据，{self.nickname}心里有数。",
            ],
            Mood.FRUSTRATED: [
                f"{self.nickname}揉了揉眼睛，{about}这活儿真是没完没了。",
                f"唉，{self.nickname}端起搪瓷杯喝了口茶，{about}搞得人头大。",
            ],
            Mood.EXCITED: [
                f"{self.nickname}一拍大腿，{about}有重大发现！",
                f"诶我跟你说，{about}绝对不简单。",
            ],
            Mood.TIRED: [
                f"{self.nickname}打了个哈欠，{about}再看看。",
                f"暖气片又凉了，{self.nickname}搓了搓手。",
            ],
            Mood.NEUTRAL: [
                f"{self.nickname}瞥了一眼{about}的进度，OK。",
                f"{self.nickname}瞄了瞄手表，{about}还行。",
            ],
            Mood.CURIOUS: [
                f"{self.nickname}凑近了看{about}，越看越觉得有意思。",
                f"等一下，{about}这块儿我再好好瞅瞅。",
            ],
            Mood.ALERT: [
                f"{self.nickname}眉头一皱，{about}不太对劲。",
                f"{self.nickname}感觉{about}有坑。",
            ],
        }

        pool = remarks.get(self.emotion.mood, remarks[Mood.NEUTRAL])
        return random.choice(pool)

    # ── 序列化 ──
    def snapshot(self) -> dict:
        """导出 Agent 当前状态快照"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.value,
            "mood": self.emotion.mood.value,
            "confidence": self.emotion.confidence,
            "frustration": self.emotion.frustration,
            "retry_count": self.emotion.retry_count,
            "key_findings": self.memory.key_findings,
            "messages_sent": len(self.outbox),
            "messages_received": len(self.inbox),
        }
