#!/usr/bin/env python3
"""Personality 单元测试 — wallstreet-tieling v3.2.0

覆盖：get_personality / get_all_agent_ids / get_receptionist_greeting / PERSONALITIES 结构完整性
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.personality import (
    get_personality,
    get_all_agent_ids,
    get_receptionist_greeting,
    PERSONALITIES,
)
from api.agent import PersonalityProfile


# ══════════════════════════════════════════════════════════
#  get_personality
# ══════════════════════════════════════════════════════════


ALL_13_IDS = [
    "zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan", "zhao-gang",
    "ma-li-quan", "zhou-tong", "zheng-shen-zhi", "wu-de-hou",
    "liu-wen-hua", "yan-hao-kan", "chen-zhi-yuan", "qian-shou-zheng",
    "an-shao",
]


class TestGetPersonality:
    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_get_personality_returns_profile_for_all_13(self, agent_id):
        """get_personality 为 13 个角色都返回 PersonalityProfile"""
        profile = get_personality(agent_id)
        assert isinstance(profile, PersonalityProfile)
        assert profile.agent_id == agent_id

    def test_unknown_agent_id_raises_keyerror(self):
        """未知 agent_id → KeyError"""
        with pytest.raises(KeyError, match="Unknown agent_id"):
            get_personality("iron-man")

    def test_keyerror_includes_available_ids(self):
        """KeyError 信息包含可用 ID 列表"""
        with pytest.raises(KeyError) as exc_info:
            get_personality("batman")
        assert "Available" in str(exc_info.value)
        assert "zhang-tie-zhu" in str(exc_info.value)


# ══════════════════════════════════════════════════════════
#  get_all_agent_ids
# ══════════════════════════════════════════════════════════


class TestGetAllAgentIds:
    def test_returns_13_ids(self):
        """get_all_agent_ids() 返回 13 个 ID"""
        ids = get_all_agent_ids()
        assert len(ids) == 13

    def test_all_known_ids_present(self):
        """返回的 ID 包含所有已知角色"""
        ids = get_all_agent_ids()
        for expected_id in ALL_13_IDS:
            assert expected_id in ids

    def test_returns_list(self):
        """返回类型是 list"""
        ids = get_all_agent_ids()
        assert isinstance(ids, list)
        assert all(isinstance(i, str) for i in ids)


# ══════════════════════════════════════════════════════════
#  get_receptionist_greeting
# ══════════════════════════════════════════════════════════


class TestGetReceptionistGreeting:
    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_every_agent_has_greeting(self, agent_id):
        """每个角色都有问候语"""
        greeting = get_receptionist_greeting(agent_id, "测试公司")
        assert isinstance(greeting, str)
        assert len(greeting) > 3

    def test_greeting_contains_target(self):
        """问候语包含目标名称"""
        greeting = get_receptionist_greeting("zhang-tie-zhu", "字节跳动")
        assert "字节跳动" in greeting

    def test_qian_shou_zheng_greeting(self):
        """钱守正的问候语特征"""
        greeting = get_receptionist_greeting("qian-shou-zheng", "测试公司")
        # 应该提到铁柱
        assert "铁柱" in greeting

    def test_an_shao_greeting(self):
        """暗哨的问候语短而精准"""
        greeting = get_receptionist_greeting("an-shao", "测试公司")
        assert "监控" in greeting

    def test_unknown_agent_raises_keyerror(self):
        """未知 agent → KeyError（由 get_personality 抛出）"""
        with pytest.raises(KeyError):
            get_receptionist_greeting("unknown", "test")


# ══════════════════════════════════════════════════════════
#  PERSONALITIES 结构完整性
# ══════════════════════════════════════════════════════════


class TestPersonalitiesDict:
    def test_has_13_entries(self):
        """PERSONALITIES 恰好 13 个条目"""
        assert len(PERSONALITIES) == 13

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_all_13_ids_in_dict(self, agent_id):
        """所有 13 个 agent_id 都在 PERSONALITIES 中"""
        assert agent_id in PERSONALITIES

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_profile_has_required_fields(self, agent_id):
        """每个 profile 必填字段非空"""
        p = PERSONALITIES[agent_id]
        assert p.agent_id == agent_id
        assert isinstance(p.display_name, str) and len(p.display_name) > 0
        assert isinstance(p.background, str) and len(p.background) > 20
        assert isinstance(p.traits, list) and len(p.traits) >= 1

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_profile_has_pet_phrases(self, agent_id):
        """每个角色至少一条口头禅"""
        p = PERSONALITIES[agent_id]
        assert isinstance(p.pet_phrases, list)
        assert len(p.pet_phrases) >= 1

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_profile_has_hates(self, agent_id):
        """每个角色有讨厌的东西（除 an-shao 可能为空）"""
        p = PERSONALITIES[agent_id]
        assert isinstance(p.hates, list)

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_emotional_volatility_in_range(self, agent_id):
        """emotional_volatility 在 0~1 范围内"""
        p = PERSONALITIES[agent_id]
        assert 0.0 <= p.emotional_volatility <= 1.0

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_humor_style_valid(self, agent_id):
        """humor_style 是有效值"""
        p = PERSONALITIES[agent_id]
        valid_styles = {"dry", "deadpan", "sarcastic", "warm", "none"}
        assert p.humor_style in valid_styles, \
            f"{agent_id} humor_style={p.humor_style} 不在 {valid_styles}"

    @pytest.mark.parametrize("agent_id", ALL_13_IDS)
    def test_colleague_opinions_is_dict(self, agent_id):
        """colleague_opinions 是 dict"""
        p = PERSONALITIES[agent_id]
        assert isinstance(p.colleague_opinions, dict)

    def test_an_shao_has_unique_traits(self):
        """暗哨有独特特征"""
        p = PERSONALITIES["an-shao"]
        assert p.age == "unknown"
        assert p.emotional_volatility == 0.0
        assert p.colleague_opinions == {}

    def test_yan_hao_kan_high_volatility(self):
        """颜好看情绪波动最大"""
        p = PERSONALITIES["yan-hao-kan"]
        assert p.emotional_volatility >= 0.4
