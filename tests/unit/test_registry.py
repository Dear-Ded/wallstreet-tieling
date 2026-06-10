#!/usr/bin/env python3
"""AgentRegistry 单元测试 — wallstreet-tieling v3.1.0

覆盖：生命周期 / CRUD / 通信路由 / 状态快照 / 聊天记录 / 清理
纯 mock 测试，不依赖真实 personality / skill 文件。
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.agent_registry import AgentRegistry
from api.agent import DueDiligenceAgent, AgentMessage, AgentState, Mood, PersonalityProfile


# ══════════════════════════════════════════════════════════
#  共享 fixtures
# ══════════════════════════════════════════════════════════


def _make_profile(agent_id: str, display_name: str = "") -> PersonalityProfile:
    """快速构造 PersonalityProfile"""
    return PersonalityProfile(
        agent_id=agent_id,
        display_name=display_name or agent_id.replace("-", " ").title(),
        nickname=display_name or agent_id,
    )


@pytest.fixture
def registry():
    """空注册中心"""
    return AgentRegistry()


@pytest.fixture
def mock_profile():
    """单 profile"""
    return _make_profile("zhang-tie-zhu", "张铁柱")


@pytest.fixture
def mock_agent_ids():
    """3 个 agent ID"""
    return ["zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan"]


# ══════════════════════════════════════════════════════════
#  __init__ 初始状态
# ══════════════════════════════════════════════════════════


class TestInit:
    def test_empty_registry_has_no_agents(self, registry):
        """空注册中心 agents 为空"""
        assert registry._agents == {}
        assert registry.get_all() == []

    def test_message_queue_empty_initially(self, registry):
        """消息队列初始为空"""
        assert registry._message_queue == []

    def test_team_chat_log_empty_initially(self, registry):
        """聊天记录初始为空"""
        assert registry._team_chat_log == []


# ══════════════════════════════════════════════════════════
#  boot() 启动
# ══════════════════════════════════════════════════════════


class TestBoot:
    def test_boot_all_agents(self, registry, mock_agent_ids):
        """boot() 启动全部 agent（默认）"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=mock_agent_ids), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill content"):
            registry.boot()
        assert len(registry._agents) == 3
        assert "zhang-tie-zhu" in registry._agents
        assert "li-ming-yuan" in registry._agents
        assert "wang-si-yuan" in registry._agents

    def test_boot_specific_agents(self, registry):
        """boot() 指定 agent_ids 启动"""
        with patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot(agent_ids=["zhang-tie-zhu", "zhao-gang"])
        assert len(registry._agents) == 2
        assert "zhang-tie-zhu" in registry._agents
        assert "zhao-gang" in registry._agents
        # 不应包含未指定的 agent
        assert "li-ming-yuan" not in registry._agents

    def test_boot_empty_list_uses_all_agents(self, registry):
        """boot([]) 空列表 → fallback 到全部 agent（因为 [] 是 falsy）"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu"]), \
             patch("api.agent_registry.get_personality", return_value=_make_profile("zhang-tie-zhu")), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot(agent_ids=[])
        # [] is falsy, so boot() uses get_all_agent_ids() instead
        assert len(registry._agents) == 1

    def test_boot_uses_role_file_map(self, registry):
        """boot 使用 config.ROLE_FILE_MAP 查找 skill 文件"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhao-gang"]), \
             patch("api.agent_registry.get_personality", return_value=_make_profile("zhao-gang")), \
             patch("api.agent_registry.load_skill") as mock_load:
            registry.boot()
        mock_load.assert_called_once()
        # config.ROLE_FILE_MAP["zhao-gang"] == "zhao-gang.md"
        assert mock_load.call_args[0][0] == "zhao-gang.md"

    def test_boot_unknown_id_uses_fallback_filename(self, registry):
        """boot 未知 ID 用 fallback 文件名"""
        with patch("api.agent_registry.get_personality", return_value=_make_profile("unknown")), \
             patch("api.agent_registry.load_skill") as mock_load:
            registry.boot(agent_ids=["unknown"])
        # config.ROLE_FILE_MAP.get("unknown", "unknown.md") → "unknown.md"
        assert mock_load.call_args[0][0] == "unknown.md"


# ══════════════════════════════════════════════════════════
#  CRUD: get / get_all / get_many
# ══════════════════════════════════════════════════════════


class TestCRUD:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry, mock_agent_ids):
        """预启动 3 个 agent 的注册中心"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=mock_agent_ids), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_get_existing_agent(self, registry):
        """get() 存在 → 返回 Agent"""
        a = registry.get("zhang-tie-zhu")
        assert a is not None
        assert a.agent_id == "zhang-tie-zhu"

    def test_get_nonexistent_agent(self, registry):
        """get() 不存在 → None"""
        a = registry.get("nobody")
        assert a is None

    def test_get_all_returns_all(self, registry):
        """get_all() 返回全部 agent"""
        all_agents = registry.get_all()
        assert len(all_agents) == 3
        ids = {a.agent_id for a in all_agents}
        assert ids == {"zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan"}

    def test_get_many_existing(self, registry):
        """get_many() 批量获取"""
        agents = registry.get_many(["zhang-tie-zhu", "wang-si-yuan"])
        assert len(agents) == 2
        assert agents[0].agent_id == "zhang-tie-zhu"
        assert agents[1].agent_id == "wang-si-yuan"

    def test_get_many_skips_missing(self, registry):
        """get_many() 跳过不存在的 agent"""
        agents = registry.get_many(["zhang-tie-zhu", "nobody", "wang-si-yuan"])
        assert len(agents) == 2


# ══════════════════════════════════════════════════════════
#  状态管理
# ══════════════════════════════════════════════════════════


class TestStateManagement:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry, mock_agent_ids):
        with patch("api.agent_registry.get_all_agent_ids", return_value=mock_agent_ids), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_get_by_state_returns_matching(self, registry):
        """get_by_state() 按状态筛选"""
        # 全部初始 IDLE
        idles = registry.get_by_state(AgentState.IDLE)
        assert len(idles) == 3
        workings = registry.get_by_state(AgentState.WORKING)
        assert len(workings) == 0

    def test_set_state_changes_agent_state(self, registry):
        """set_state() 修改单个 agent 状态"""
        registry.set_state("zhang-tie-zhu", AgentState.WORKING)
        assert registry.get("zhang-tie-zhu").state == AgentState.WORKING
        # 其他 agent 不受影响
        assert registry.get("li-ming-yuan").state == AgentState.IDLE

    def test_set_state_nonexistent_noop(self, registry):
        """set_state() 不存在 agent 无操作"""
        registry.set_state("nobody", AgentState.WORKING)
        # 不应抛出异常

    def test_set_many_states(self, registry):
        """set_many_states() 批量修改"""
        registry.set_many_states(["zhang-tie-zhu", "li-ming-yuan"], AgentState.DONE)
        assert registry.get("zhang-tie-zhu").state == AgentState.DONE
        assert registry.get("li-ming-yuan").state == AgentState.DONE
        assert registry.get("wang-si-yuan").state == AgentState.IDLE


# ══════════════════════════════════════════════════════════
#  wake_agents
# ══════════════════════════════════════════════════════════


class TestWakeAgents:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry, mock_agent_ids):
        with patch("api.agent_registry.get_all_agent_ids", return_value=mock_agent_ids), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_wake_idle_agent_changes_state(self, registry):
        """wake_agents() 把 IDLE → WORKING"""
        with patch("api.agent_registry.get_receptionist_greeting", return_value="收到！"):
            registry.wake_agents(["zhang-tie-zhu"], "测试公司")
        assert registry.get("zhang-tie-zhu").state == AgentState.WORKING

    def test_wake_non_idle_agent_unchanged(self, registry):
        """wake_agents() 非 IDLE agent 状态不变"""
        registry.set_state("li-ming-yuan", AgentState.BUSY if hasattr(AgentState, 'BUSY') else AgentState.WORKING)
        with patch("api.agent_registry.get_receptionist_greeting", return_value="收到！"):
            registry.wake_agents(["li-ming-yuan"], "测试公司")
        # 不是 IDLE 就不会改变
        # 注意：wake_agents 只唤醒 IDLE 状态的 agent
        # li-ming-yuan 如果不是 IDLE 就不处理
        assert registry.get("li-ming-yuan").state != AgentState.IDLE
        assert registry.get("li-ming-yuan").state == AgentState.WORKING

    def test_wake_adds_chat_log(self, registry):
        """wake_agents() 添加聊天记录"""
        with patch("api.agent_registry.get_receptionist_greeting",
                   return_value="收到，铁柱开始干活！"):
            registry.wake_agents(["zhang-tie-zhu"], "测试公司")
        assert len(registry._team_chat_log) == 1
        assert "铁柱" in registry._team_chat_log[0]
        assert "收到" in registry._team_chat_log[0]


# ══════════════════════════════════════════════════════════
#  通信路由
# ══════════════════════════════════════════════════════════


class TestRouteMessage:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry):
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu", "li-ming-yuan"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_route_point_to_point(self, registry):
        """route_message() 点对点路由"""
        msg = AgentMessage(
            msg_id="m1", from_agent="zhang-tie-zhu", to_agent="li-ming-yuan",
            msg_type="question", content="数字对吗？",
        )
        registry.route_message(msg)
        # 目标 agent 收到消息
        target = registry.get("li-ming-yuan")
        assert len(target.inbox) == 1

    def test_route_broadcast(self, registry):
        """route_message() 广播路由"""
        msg = AgentMessage(
            msg_id="m2", from_agent="zhang-tie-zhu", to_agent="broadcast",
            msg_type="observation", content="数据已更新",
        )
        registry.route_message(msg)
        # 所有非发送者都收到
        for aid in ["li-ming-yuan"]:
            agent = registry.get(aid)
            assert len(agent.inbox) == 1

    def test_route_broadcast_excludes_sender(self, registry):
        """广播排除发送者"""
        msg = AgentMessage(
            msg_id="m3", from_agent="zhang-tie-zhu", to_agent="broadcast",
            msg_type="observation", content="test",
        )
        registry.route_message(msg)
        # 发送者自己不应收到
        sender = registry.get("zhang-tie-zhu")
        assert len(sender.inbox) == 0

    def test_route_to_invalid_target_ignored(self, registry):
        """route_message() 无效目标 → 无操作（不抛异常）"""
        msg = AgentMessage(
            msg_id="m4", from_agent="zhang-tie-zhu", to_agent="nobody",
            msg_type="question", content="test",
        )
        # 不应抛出异常
        registry.route_message(msg)
        # 消息仍然进入队列
        assert registry._message_queue[-1] == msg

    def test_route_adds_to_queue(self, registry):
        """route_message() 消息入队"""
        msg = AgentMessage(
            msg_id="m5", from_agent="a", to_agent="b",
            msg_type="observation", content="test",
        )
        registry.route_message(msg)
        assert registry._message_queue[-1] == msg


# ══════════════════════════════════════════════════════════
#  broadcast
# ══════════════════════════════════════════════════════════


class TestBroadcast:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry):
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu", "li-ming-yuan"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_broadcast_sends_to_all(self, registry):
        """broadcast() 发送给所有其他 agent"""
        registry.broadcast("zhang-tie-zhu", "大家辛苦了", msg_type="status")
        # li-ming-yuan 收到
        target = registry.get("li-ming-yuan")
        assert len(target.inbox) == 1
        assert target.inbox[0].content == "大家辛苦了"

    def test_broadcast_from_unknown_agent(self, registry):
        """broadcast() 未知发送者 → 无操作"""
        registry.broadcast("nobody", "test")
        # 不应抛异常，不应有消息进入队列（除了已有的消息）


# ══════════════════════════════════════════════════════════
#  process_all_inboxes
# ══════════════════════════════════════════════════════════


class TestProcessAllInboxes:
    @pytest.fixture(autouse=True)
    def booted_registry(self, registry):
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu", "li-ming-yuan"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        return registry

    def test_process_all_inboxes_clears_inbox(self, registry):
        """process_all_inboxes() 处理收件箱后清空"""
        # 先给 agent 发消息
        msg = AgentMessage(
            msg_id="pi-1", from_agent="li-ming-yuan", to_agent="zhang-tie-zhu",
            msg_type="question", content="问个问题",
        )
        registry.route_message(msg)
        assert len(registry.get("zhang-tie-zhu").inbox) == 1
        registry.process_all_inboxes()
        assert len(registry.get("zhang-tie-zhu").inbox) == 0


# ══════════════════════════════════════════════════════════
#  团队聊天
# ══════════════════════════════════════════════════════════


class TestTeamChat:
    def test_add_team_chat_appends(self, registry):
        """add_team_chat() 追加记录"""
        registry.add_team_chat("[张铁柱] 数据来了")
        registry.add_team_chat("[李明远] 收到")
        assert len(registry._team_chat_log) == 2

    def test_team_chat_snapshot_last_n(self, registry):
        """team_chat_snapshot() 返回最后 N 条"""
        for i in range(15):
            registry.add_team_chat(f"消息 {i}")
        snap = registry.team_chat_snapshot(max_lines=5)
        lines = snap.split("\n")
        assert len(lines) == 5
        assert "消息 14" in lines[-1]

    def test_team_chat_snapshot_empty(self, registry):
        """空聊天记录 → 空字符串"""
        assert registry.team_chat_snapshot() == ""


# ══════════════════════════════════════════════════════════
#  状态报告
# ══════════════════════════════════════════════════════════


class TestStatusReport:
    def test_status_report_contains_header(self, registry):
        """status_report() 含标题"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        report = registry.status_report()
        assert "办事处状态" in report

    def test_status_report_empty_registry(self, registry):
        """空注册中心 status_report 只含标题"""
        report = registry.status_report()
        assert "═══ 办事处状态 ═══" in report


# ══════════════════════════════════════════════════════════
#  shutdown
# ══════════════════════════════════════════════════════════


class TestShutdown:
    def test_shutdown_resets_all_agents_to_idle(self, registry):
        """shutdown() 所有 agent 重置为 IDLE"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu", "li-ming-yuan"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        # 改为 WORKING
        registry.set_many_states(["zhang-tie-zhu", "li-ming-yuan"], AgentState.WORKING)
        registry.shutdown()
        assert registry.get("zhang-tie-zhu").state == AgentState.IDLE
        assert registry.get("li-ming-yuan").state == AgentState.IDLE

    def test_shutdown_clears_message_queue(self, registry):
        """shutdown() 清空消息队列"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        msg = AgentMessage(
            msg_id="sd-1", from_agent="a", to_agent="zhang-tie-zhu",
            msg_type="observation", content="test",
        )
        registry.route_message(msg)
        assert len(registry._message_queue) > 0
        registry.shutdown()
        assert len(registry._message_queue) == 0

    def test_shutdown_clears_team_chat(self, registry):
        """shutdown() 清空聊天记录"""
        with patch("api.agent_registry.get_all_agent_ids", return_value=["zhang-tie-zhu"]), \
             patch("api.agent_registry.get_personality", side_effect=lambda aid: _make_profile(aid)), \
             patch("api.agent_registry.load_skill", return_value="# Skill"):
            registry.boot()
        registry.add_team_chat("闲聊")
        registry.shutdown()
        assert len(registry._team_chat_log) == 0
