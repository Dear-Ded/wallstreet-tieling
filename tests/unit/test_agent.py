#!/usr/bin/env python3
"""Agent 单元测试 — wallstreet-tieling v3.2.0

覆盖：Agent 创建 / inner_monologue / AgentMessage / EmotionalState / 消息系统 / casual_remark
零 LLM 依赖，纯函数测试。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.agent import (
    DueDiligenceAgent,
    AgentMessage,
    EmotionalState,
    AgentMemory,
    AgentState,
    Mood,
    PersonalityProfile,
)


# ══════════════════════════════════════════════════════════
#  PersonalityProfile 测试
# ══════════════════════════════════════════════════════════


class TestPersonalityProfile:
    def test_default_values(self):
        """profile 默认字段正确"""
        p = PersonalityProfile(
            agent_id="test-agent",
            display_name="测试员",
        )
        assert p.agent_id == "test-agent"
        assert p.display_name == "测试员"
        assert p.nickname == ""
        assert p.traits == []
        assert p.pet_phrases == []
        assert p.humor_style == "dry"
        assert p.emotional_volatility == 0.3
        assert p.colleague_opinions == {}

    def test_full_profile_construction(self):
        """完整 profile 构造"""
        p = PersonalityProfile(
            agent_id="zhang-tie-zhu",
            display_name="张铁柱",
            nickname="铁柱",
            age="45",
            background="铁岭本地人",
            traits=["老实巴交", "细节控"],
            pet_phrases=["这个注册号我查了一下……"],
            hates=["虚假地址"],
            humor_style="deadpan",
            emotional_volatility=0.2,
            colleague_opinions={"qian-shou-zheng": "钱总是好人"},
        )
        assert p.agent_id == "zhang-tie-zhu"
        assert p.nickname == "铁柱"
        assert len(p.traits) == 2
        assert p.humor_style == "deadpan"
        assert p.emotional_volatility == 0.2


# ══════════════════════════════════════════════════════════
#  EmotionalState 测试
# ══════════════════════════════════════════════════════════


class TestEmotionalState:
    def test_initial_state(self):
        """初始情绪为 NEUTRAL"""
        e = EmotionalState()
        assert e.mood == Mood.NEUTRAL
        assert e.confidence == 0.8
        assert e.frustration == 0.0
        assert e.excitement == 0.0
        assert e.retry_count == 0
        assert e.mood_history == []

    def test_success_boosts_confidence(self):
        """成功 → 信心 +0.05, 挫败 -0.1"""
        e = EmotionalState()
        e.update(success=True)
        assert e.confidence == pytest.approx(0.85)
        assert e.frustration == pytest.approx(0.0)

    def test_failure_lowers_confidence(self):
        """失败 → 信心 -0.1, 挫败 +0.15, 再衰减"""
        e = EmotionalState()
        e.update(success=False)
        # confidence: 0.8 - 0.1 = 0.7
        # frustration: 0.0 + 0.15 - 0.03 (decay) = 0.12
        assert e.confidence == pytest.approx(0.7)
        assert e.frustration == pytest.approx(0.12)

    def test_retry_increments_counter_and_frustration(self):
        """重试 → retry_count +1, 挫败 +0.2, 再衰减 -0.03"""
        e = EmotionalState()
        e.update(retry=True)
        assert e.retry_count == 1
        # frustration: 0.0 + 0.2 - 0.03 (decay) = 0.17
        assert e.frustration == pytest.approx(0.17)

    def test_discovery_boosts_excitement(self):
        """发现 → 兴奋 +0.2, 再衰减 -0.05"""
        e = EmotionalState()
        e.update(success=True, discovery=True)
        # excitement: 0.0 + 0.2 - 0.05 (decay) = 0.15
        assert e.excitement == pytest.approx(0.15)

    def test_excitement_decays(self):
        """兴奋自然衰减 -0.05"""
        e = EmotionalState(excitement=0.5)
        e.update()
        assert e.excitement == 0.45

    def test_frustration_decays(self):
        """挫败自然衰减 -0.03"""
        e = EmotionalState(frustration=0.5)
        e.update()
        assert e.frustration == 0.47

    def test_mood_frustrated_on_high_frustration(self):
        """挫败 >0.6 → FRUSTRATED (after decay)"""
        # frustration: 0.64 - 0.03 (decay) = 0.61 > 0.6 → FRUSTRATED
        e = EmotionalState(frustration=0.64)
        e.update()
        assert e.mood == Mood.FRUSTRATED

    def test_mood_excited_on_high_excitement(self):
        """兴奋 >0.5 → EXCITED (priority over confidence, mood based on pre-decay values)"""
        e = EmotionalState(excitement=0.51, confidence=0.9)
        e.update()
        # mood is calculated BEFORE decay: excitement 0.51 > 0.5 → EXCITED
        # decay then applies (excitement → 0.46), but mood already set
        assert e.mood == Mood.EXCITED

    def test_mood_confident_on_high_confidence(self):
        """信心 >0.85 → CONFIDENT"""
        e = EmotionalState(confidence=0.86, excitement=0.0, frustration=0.0)
        e.update()
        assert e.mood == Mood.CONFIDENT

    def test_mood_tired_on_moderate_frustration(self):
        """挫败 >0.3 → TIRED (mood based on pre-decay values)"""
        e = EmotionalState(frustration=0.31, confidence=0.7, excitement=0.0)
        e.update()
        # mood calculated before decay: frustration 0.31 > 0.3 → TIRED
        assert e.mood == Mood.TIRED

    def test_mood_history_recorded(self):
        """每次 update 都记录 mood_history"""
        e = EmotionalState()
        e.update(success=True)
        assert len(e.mood_history) == 1
        entry = e.mood_history[0]
        assert "time" in entry
        assert "mood" in entry
        assert "confidence" in entry
        assert "frustration" in entry

    def test_multiple_updates_accumulate_history(self):
        """多次 update 多次记录"""
        e = EmotionalState()
        e.update(success=True)
        e.update(success=False)
        e.update(retry=True)
        assert len(e.mood_history) == 3

    def test_confidence_clamped_to_1(self):
        """信心值不超过 1.0"""
        e = EmotionalState(confidence=0.99)
        e.update(success=True)
        assert e.confidence == 1.0

    def test_frustration_never_negative(self):
        """挫败不低于 0"""
        e = EmotionalState(frustration=0.0)
        e.update(success=True)  # frustration - 0.1
        assert e.frustration == 0.0


# ══════════════════════════════════════════════════════════
#  AgentMessage 测试
# ══════════════════════════════════════════════════════════


class TestAgentMessage:
    def test_full_message_creation(self):
        """完整消息构造"""
        msg = AgentMessage(
            msg_id="test-001",
            from_agent="zhang-tie-zhu",
            to_agent="li-ming-yuan",
            msg_type="question",
            content="这个数字对得上吗？",
            priority=1,
            thread_id="thread-42",
        )
        assert msg.msg_id == "test-001"
        assert msg.from_agent == "zhang-tie-zhu"
        assert msg.to_agent == "li-ming-yuan"
        assert msg.msg_type == "question"
        assert msg.content == "这个数字对得上吗？"
        assert msg.priority == 1
        assert msg.thread_id == "thread-42"

    def test_default_priority(self):
        """默认优先级为 0"""
        msg = AgentMessage(
            msg_id="m1", from_agent="a", to_agent="b",
            msg_type="observation", content="test",
        )
        assert msg.priority == 0

    def test_timestamp_auto_generated(self):
        """timestamp 自动生成"""
        msg = AgentMessage(
            msg_id="m2", from_agent="a", to_agent="b",
            msg_type="response", content="test",
        )
        assert msg.timestamp != ""
        assert ":" in msg.timestamp  # HH:MM:SS format

    def test_default_thread_id(self):
        """thread_id 默认为空"""
        msg = AgentMessage(
            msg_id="m3", from_agent="a", to_agent="b",
            msg_type="gossip", content="八卦",
        )
        assert msg.thread_id == ""


# ══════════════════════════════════════════════════════════
#  AgentMemory 测试
# ══════════════════════════════════════════════════════════


class TestAgentMemory:
    def test_default_empty(self):
        m = AgentMemory()
        assert m.conversation_history == []
        assert m.key_findings == []
        assert m.questions_raised == []
        assert m.notes_to_self == []

    def test_can_append_to_lists(self):
        m = AgentMemory()
        m.key_findings.append("发现1")
        m.notes_to_self.append("备忘")
        assert len(m.key_findings) == 1
        assert m.key_findings[0] == "发现1"


# ══════════════════════════════════════════════════════════
#  DueDiligenceAgent 测试
# ══════════════════════════════════════════════════════════


@pytest.fixture
def sample_profile():
    return PersonalityProfile(
        agent_id="test-agent",
        display_name="测试员",
        nickname="测试",
        age="30",
        background="测试背景",
        traits=["严谨", "细心"],
        pet_phrases=["数据说话。"],
        hates=["造假"],
        humor_style="dry",
        emotional_volatility=0.2,
        colleague_opinions={"other-agent": "挺靠谱"},
    )


@pytest.fixture
def sample_agent(sample_profile):
    return DueDiligenceAgent(
        agent_id="test-agent",
        profile=sample_profile,
        sub_skill_content="# 测试子技能\n测试用。",
    )


class TestAgentCreation:
    def test_create_with_profile(self, sample_agent, sample_profile):
        """Agent 正确创建"""
        assert sample_agent.agent_id == "test-agent"
        assert sample_agent.profile == sample_profile
        assert sample_agent.sub_skill == "# 测试子技能\n测试用。"
        assert sample_agent.state == AgentState.IDLE

    def test_name_property(self, sample_agent):
        """name 返回 display_name"""
        assert sample_agent.name == "测试员"

    def test_nickname_property(self, sample_agent):
        """nickname 返回 nickname"""
        assert sample_agent.nickname == "测试"

    def test_nickname_fallback_to_name(self, sample_profile):
        """无 nickname 时 fallback 到 display_name"""
        p = PersonalityProfile(agent_id="x", display_name="无名")
        agent = DueDiligenceAgent("x", p, "")
        assert agent.nickname == "无名"

    def test_initial_state_is_idle(self, sample_agent):
        assert sample_agent.state == AgentState.IDLE

    def test_initial_emotion_is_neutral(self, sample_agent):
        assert sample_agent.emotion.mood == Mood.NEUTRAL

    def test_initial_memory_empty(self, sample_agent):
        assert sample_agent.memory.key_findings == []
        assert sample_agent.memory.conversation_history == []
        assert sample_agent.memory.notes_to_self == []

    def test_inbox_outbox_empty(self, sample_agent):
        assert sample_agent.inbox == []
        assert sample_agent.outbox == []


class TestInnerMonologue:
    def test_neutral_mood_monologue(self, sample_agent):
        """NEUTRAL → 产生独白"""
        sample_agent.emotion.mood = Mood.NEUTRAL
        mono = sample_agent.inner_monologue()
        assert mono.startswith("[内心: ")
        assert mono.endswith("]")

    def test_confident_mood_monologue(self, sample_agent):
        """CONFIDENT → 自信独白"""
        sample_agent.emotion.mood = Mood.CONFIDENT
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_frustrated_mood_monologue(self, sample_agent):
        """FRUSTRATED → 烦躁独白"""
        sample_agent.emotion.mood = Mood.FRUSTRATED
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_alert_mood_monologue(self, sample_agent):
        """ALERT → 警觉独白"""
        sample_agent.emotion.mood = Mood.ALERT
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_curious_mood_monologue(self, sample_agent):
        """CURIOUS → 好奇独白"""
        sample_agent.emotion.mood = Mood.CURIOUS
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_tired_mood_monologue(self, sample_agent):
        """TIRED → 疲惫独白"""
        sample_agent.emotion.mood = Mood.TIRED
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_excited_mood_monologue(self, sample_agent):
        """EXCITED → 兴奋独白"""
        sample_agent.emotion.mood = Mood.EXCITED
        mono = sample_agent.inner_monologue()
        assert "[内心:" in mono

    def test_monologue_with_context(self, sample_agent):
        """带上下文的独白"""
        sample_agent.emotion.mood = Mood.NEUTRAL
        mono = sample_agent.inner_monologue("Phase 1")
        assert "[内心:" in mono
        assert "Phase 1" in mono

    def test_frustrated_includes_retry_count(self, sample_agent):
        """FRUSTRATED 独白可能包含重试次数"""
        sample_agent.emotion.mood = Mood.FRUSTRATED
        sample_agent.emotion.retry_count = 3
        # Just verify it runs without error and returns a string
        mono = sample_agent.inner_monologue()
        assert isinstance(mono, str)
        assert len(mono) > 5


class TestOpinionOf:
    def test_degraded_opinion(self, sample_agent):
        """降级 → 负面评价"""
        opinion = sample_agent.opinion_of(
            "other", "别人", their_result={"degraded": True}
        )
        assert "降级" in opinion

    def test_good_long_result_opinion(self, sample_agent):
        """长结果 → 正面评价"""
        opinion = sample_agent.opinion_of(
            "other", "别人",
            their_result={"ok": True, "text": "x" * 1500}
        )
        assert "不错" in opinion

    def test_short_result_opinion(self, sample_agent):
        """短结果 → neutral"""
        opinion = sample_agent.opinion_of(
            "other", "别人",
            their_result={"ok": True, "text": "short"}
        )
        assert "还行" in opinion

    def test_no_result_uses_colleague_opinion(self, sample_agent):
        """无结果 → 用预存看法"""
        opinion = sample_agent.opinion_of("other-agent", "别人")
        assert "挺靠谱" in opinion

    def test_no_opinion_fallback(self, sample_agent):
        """无预存看法 → 默认评价"""
        opinion = sample_agent.opinion_of("stranger", "陌生人")
        assert "共事" in opinion


class TestSendReceiveMessage:
    def test_send_message_creates_correct_message(self, sample_agent):
        """send_message 正确创建 AgentMessage"""
        msg = sample_agent.send_message("target", "question", "测试一下")
        assert msg.from_agent == "test-agent"
        assert msg.to_agent == "target"
        assert msg.msg_type == "question"
        assert msg.content == "测试一下"
        assert msg.priority == 0  # default

    def test_send_message_with_priority(self, sample_agent):
        msg = sample_agent.send_message(
            "target", "observation", "紧急!", priority=2, thread_id="t1"
        )
        assert msg.priority == 2
        assert msg.thread_id == "t1"

    def test_send_adds_to_outbox(self, sample_agent):
        assert len(sample_agent.outbox) == 0
        sample_agent.send_message("target", "observation", "test")
        assert len(sample_agent.outbox) == 1

    def test_msg_id_increments(self, sample_agent):
        """消息ID递增"""
        m1 = sample_agent.send_message("a", "test", "1")
        m2 = sample_agent.send_message("b", "test", "2")
        m3 = sample_agent.send_message("c", "test", "3")
        assert m1.msg_id == "test-agent-001"
        assert m2.msg_id == "test-agent-002"
        assert m3.msg_id == "test-agent-003"

    def test_receive_message_adds_to_inbox(self, sample_agent):
        """receive_message 添加到 inbox"""
        msg = AgentMessage(
            msg_id="ext-001", from_agent="other", to_agent="test-agent",
            msg_type="response", content="回执",
        )
        sample_agent.receive_message(msg)
        assert len(sample_agent.inbox) == 1
        assert sample_agent.inbox[0].msg_id == "ext-001"

    def test_high_priority_message_triggers_alert(self, sample_agent):
        """紧急消息 → ALERT 情绪"""
        msg = AgentMessage(
            msg_id="urgent", from_agent="boss", to_agent="test-agent",
            msg_type="request", content="紧急!", priority=2,
        )
        sample_agent.receive_message(msg)
        assert sample_agent.emotion.mood == Mood.ALERT


class TestProcessInbox:
    def test_question_gets_response(self, sample_agent):
        """问题 → 回复"""
        msg = AgentMessage(
            msg_id="q1", from_agent="other", to_agent="test-agent",
            msg_type="question", content="这个数据对吗？需要确认",
        )
        sample_agent.receive_message(msg)
        replies = sample_agent.process_inbox()
        assert len(replies) == 1
        assert replies[0].msg_type == "response"
        assert replies[0].to_agent == "other"

    def test_inbox_cleared_after_processing(self, sample_agent):
        """处理后 inbox 清空"""
        msg = AgentMessage(
            msg_id="q2", from_agent="other", to_agent="test-agent",
            msg_type="question", content="问题",
        )
        sample_agent.receive_message(msg)
        sample_agent.process_inbox()
        assert len(sample_agent.inbox) == 0

    def test_message_not_for_this_agent_ignored(self, sample_agent):
        """不是发给自己的消息 → 忽略"""
        msg = AgentMessage(
            msg_id="m-other", from_agent="a", to_agent="someone-else",
            msg_type="question", content="问题",
        )
        sample_agent.receive_message(msg)
        replies = sample_agent.process_inbox()
        assert len(replies) == 0


class TestCasualRemark:
    def test_neutral_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.NEUTRAL
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)
        assert len(remark) > 3

    def test_confident_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.CONFIDENT
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_frustrated_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.FRUSTRATED
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_excited_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.EXCITED
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_curious_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.CURIOUS
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_alert_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.ALERT
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_tired_remark(self, sample_agent):
        sample_agent.emotion.mood = Mood.TIRED
        remark = sample_agent.casual_remark("测试")
        assert isinstance(remark, str)

    def test_default_about(self, sample_agent):
        """无 about → 默认'今天的工作'"""
        remark = sample_agent.casual_remark()
        assert isinstance(remark, str)
        assert len(remark) > 3


class TestSnapshot:
    def test_snapshot_contains_all_fields(self, sample_agent):
        snap = sample_agent.snapshot()
        assert snap["agent_id"] == "test-agent"
        assert snap["name"] == "测试员"
        assert snap["state"] == "idle"
        assert snap["mood"] == "neutral"
        assert snap["confidence"] == 0.8
        assert snap["frustration"] == 0.0
        assert snap["retry_count"] == 0
        assert snap["key_findings"] == []
        assert snap["messages_sent"] == 0
        assert snap["messages_received"] == 0

    def test_snapshot_reflects_changes(self, sample_agent):
        """snapshot 反映最新状态"""
        sample_agent.emotion.update(success=True)
        sample_agent.memory.key_findings.append("重要发现")
        sample_agent.send_message("someone", "observation", "test")

        snap = sample_agent.snapshot()
        assert snap["confidence"] > 0.8
        assert snap["key_findings"] == ["重要发现"]
        assert snap["messages_sent"] == 1
