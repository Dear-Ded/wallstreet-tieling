#!/usr/bin/env python3
"""Orchestrator 单元测试 — wallstreet-tieling v3.2.0

覆盖：_commissar_check / _generate_pua_feedback / _extract_signals /
       _build_context / _check_consistency / 初始化 / 模式选择
零 LLM 调用，纯函数 + Mock。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.agent import (
    DueDiligenceAgent,
    PersonalityProfile,
    AgentState,
    Mood,
)
from api.orchestrator import (
    Orchestrator,
    CONDITIONAL_BRANCH_RULES,
    NO_FABRICATION_RULE,
    NO_FABRICATION_TAGLINE,
    PHASE1_USER_TEMPLATES,
    PHASE2_USER_TEMPLATES,
    PHASE3_USER_TEMPLATES,
    ALL_USER_TEMPLATES,
)
from api.quality_rules import Violation


# ══════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════


@pytest.fixture
def sample_profile():
    return PersonalityProfile(
        agent_id="zhang-tie-zhu",
        display_name="张铁柱",
        nickname="铁柱",
    )


@pytest.fixture
def sample_agent(sample_profile):
    return DueDiligenceAgent(
        agent_id="zhang-tie-zhu",
        profile=sample_profile,
        sub_skill_content="# 工商查询\n铁柱负责工商信息查询。",
    )


@pytest.fixture
def base_orch():
    """基础编排器，无 API 调用"""
    return Orchestrator(
        target="测试科技",
        mode="standard",
        concurrency=2,
        max_retries=2,
    )


# ══════════════════════════════════════════════════════════
#  初始化测试
# ══════════════════════════════════════════════════════════


class TestOrchestratorInit:
    def test_default_initialization(self):
        """默认参数正确"""
        orch = Orchestrator("测试科技")
        assert orch.target == "测试科技"
        assert orch.mode == "standard"
        assert orch.concurrency == 5
        assert orch.max_retries == 3
        assert orch.roles is None

    def test_custom_concurrency_and_retries(self):
        """自定义并发数和重试次数"""
        orch = Orchestrator("测试", concurrency=3, max_retries=5)
        assert orch.concurrency == 3
        assert orch.max_retries == 5

    def test_custom_mode_deep(self):
        """深度模式"""
        orch = Orchestrator("测试", mode="deep")
        assert orch.mode == "deep"
        template = orch.template
        assert "conditional_branches" in template
        assert template["conditional_branches"] is True

    def test_custom_mode_simple(self):
        """简单模式"""
        orch = Orchestrator("测试", mode="simple")
        assert orch.mode == "simple"
        assert len(orch.template["phase1"]) == 1
        assert orch.template["phase2"] == []
        assert orch.template["phase3"] == []

    def test_custom_mode_sme(self):
        """中小企业模式"""
        orch = Orchestrator("测试", mode="sme")
        assert orch.mode == "sme"

    def test_roles_parameter(self):
        """指定角色列表"""
        orch = Orchestrator("测试", roles=["zhang-tie-zhu", "zhao-gang"])
        assert orch.roles == ["zhang-tie-zhu", "zhao-gang"]

    def test_registry_created(self, base_orch):
        """registry 已创建"""
        assert base_orch.registry is not None

    def test_branches_triggered_empty(self, base_orch):
        """初始无分支触发"""
        assert base_orch.branches_triggered == []

    def test_session_start_set(self, base_orch):
        """session_start 已记录"""
        assert base_orch._session_start > 0


# ══════════════════════════════════════════════════════════
#  _commissar_check 测试
# ══════════════════════════════════════════════════════════


class TestCommissarCheck:
    def test_happy_path_l1_l2_pass(self, base_orch, sample_agent):
        """L1 通过 + L2 通过 → (True, [])"""
        text = (
            "注册资本1000万元[来源: tyc-mcp, 参数: company_name='测试科技', "
            "时间: 2026-06-10]。公司经营正常，财务稳健。"
            "营收500亿[来源: Bloomberg, 2026]。"
        ) * 7  # >500 chars for truncation check
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        assert passed is True
        assert violations == []

    def test_l1_fail_credit_word(self, base_orch, sample_agent):
        """L1 失败：信贷决策词"""
        text = "建议通过授信，额度500万。" * 20
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        assert passed is False
        assert len(violations) > 0
        credit = [v for v in violations if v.rule == "credit_word"]
        assert len(credit) >= 1

    def test_l1_fail_vague_word(self, base_orch, sample_agent):
        """L1 失败：模糊词"""
        text = "大概营收5亿，可能利润1亿。" * 10
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        assert passed is False
        vague = [v for v in violations if v.rule == "vague_word"]
        assert len(vague) >= 1

    def test_l1_fail_no_source(self, base_orch, sample_agent):
        """L1 失败：无来源标注"""
        text = "注册资本500万，公司经营正常，营收10亿。" * 10
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        # Should fail because >100 chars without source
        assert passed is False
        no_src = [v for v in violations if v.rule == "no_source"]
        assert len(no_src) >= 1

    def test_l1_pass_l2_fabrication_detected(self, base_orch, sample_agent):
        """L1 通过但 L2 发现编造信号 → (False, violations)"""
        # Text that passes L1: long enough, has source annotations, no credit/vague words
        # But contains anonymous source indicators ("据悉", "知情人士") for L2 fabrication detection
        text = (
            "该公司营收规模位居行业前列[来源: 行业报告, 2026]。"
            "据悉该领域增长潜力巨大。"
            "知情人士透露公司正筹备新一轮融资[来源: 行业报告, 2026]。"
            "业内人士认为公司有望取得更大发展[来源: 行业报告, 2026]。"
        ) * 6
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        assert passed is False
        fab_violations = [v for v in violations if v.rule == "fabrication_risk"]
        assert len(fab_violations) >= 1

    def test_commissar_stats_recorded_on_pass(self, base_orch, sample_agent):
        """政委通过时记录 stats"""
        text = (
            "注册资本1000万元[来源: tyc-mcp, 参数: company_name='测试科技', "
            "时间: 2026-06-10]。营收500亿[来源: Bloomberg, 2026]。"
        ) * 3
        passed, _ = base_orch._commissar_check(sample_agent, text, 0)
        if passed:
            stats = base_orch._commissar_stats.get("zhang-tie-zhu")
            assert stats is not None
            assert stats["pass"] is True
            assert stats["degraded"] is False

    def test_commissar_stats_on_fabrication(self, base_orch, sample_agent):
        """编造信号检测 — L1 通过但 L2 发现匿名源"""
        # Must be ≥500 chars to avoid short_output L1 violation
        # Must have source annotations to avoid no_source L1 violation
        # Must NOT have credit words or vague words
        # But MUST have anonymous source indicators for L2 fabrication detection
        text = (
            "据悉该公司经营状况良好。"   # anonymous source indicator
            "市场分析显示行业前景广阔[来源: 行业报告, 2026]。"
            "业内人士认为公司有望取得更大发展[来源: 行业报告, 2026]。"
            "据悉该领域增长潜力巨大。"
        ) * 8  # Make it long enough (>500 chars)
        passed, violations = base_orch._commissar_check(sample_agent, text, 0)
        assert passed is False
        fab_violations = [v for v in violations if v.rule == "fabrication_risk"]
        assert len(fab_violations) >= 1


# ══════════════════════════════════════════════════════════
#  _generate_pua_feedback 测试
# ══════════════════════════════════════════════════════════


class TestPuaFeedback:
    @pytest.fixture
    def sample_violations(self):
        return [
            Violation(rule="credit_word", field="full_text",
                      detail="检测到信贷决策词: 建议通过", severity="ERROR"),
            Violation(rule="no_source", field="full_text",
                      detail="输出未标注任何数据来源", severity="ERROR"),
        ]

    def test_attempt_0_level_1(self, base_orch, sample_agent, sample_violations):
        """attempt=0 → level 1（第一次违规）"""
        feedback = base_orch._generate_pua_feedback(
            sample_agent, sample_violations, 1
        )
        assert "张铁柱" in feedback
        assert "政委退回第1次" in feedback
        assert "修正" in feedback

    def test_attempt_1_level_2(self, base_orch, sample_agent, sample_violations):
        """attempt=1 → level 2（第二次警告）"""
        feedback = base_orch._generate_pua_feedback(
            sample_agent, sample_violations, 2
        )
        assert "政委退回第2次" in feedback
        assert "第二次" in feedback
        # Level 2 mentions colleague comparison
        assert "王思远" in feedback or "最后" in feedback

    def test_attempt_2_level_3(self, base_orch, sample_agent, sample_violations):
        """attempt=2 → level 3（降级）"""
        feedback = base_orch._generate_pua_feedback(
            sample_agent, sample_violations, 3
        )
        assert "政委退回第3次" in feedback
        assert "降级" in feedback

    def test_attempt_3_capped_at_level_3(self, base_orch, sample_agent, sample_violations):
        """attempt=3 → cap at level 3"""
        feedback = base_orch._generate_pua_feedback(
            sample_agent, sample_violations, 4
        )
        assert "政委退回第4次" in feedback
        # Still uses level 3 template
        assert "降级" in feedback

    def test_feedback_contains_issues(self, base_orch, sample_agent, sample_violations):
        """feedback 包含具体违规详情"""
        feedback = base_orch._generate_pua_feedback(
            sample_agent, sample_violations, 1
        )
        assert "credit_word" in feedback
        assert "no_source" in feedback
        assert "建议通过" in feedback

    def test_feedback_with_single_violation(self, base_orch, sample_agent):
        """单个违规的反馈"""
        violations = [
            Violation(rule="short_output", field="full_text",
                      detail="疑似输出截断，仅 50 字符", severity="WARN"),
        ]
        feedback = base_orch._generate_pua_feedback(sample_agent, violations, 1)
        assert "1 处违规" in feedback


# ══════════════════════════════════════════════════════════
#  _extract_signals 测试
# ══════════════════════════════════════════════════════════


class TestExtractSignals:
    def test_controller_anomaly_detected(self, base_orch):
        """实控人不一致 → controller_anomaly 信号"""
        results = [
            {"ok": True, "text": "经查，该公司实际控制人不明，存在股权代持嫌疑。", "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        controller = [s for s in signals if s["signal"] == "controller_anomaly"]
        assert len(controller) >= 1
        assert controller[0]["append_role"] == "ma-li-quan"

    def test_large_deposit_loan_detected(self, base_orch):
        """大存大贷 → 追加赵刚"""
        results = [
            {"ok": True, "text": "该公司存在大存大贷现象，存贷双高。", "rid": "li-ming-yuan"},
        ]
        signals = base_orch._extract_signals(results)
        matched = [s for s in signals if s["signal"] == "large_deposit_loan"]
        assert len(matched) >= 1
        assert matched[0]["append_role"] == "zhao-gang"

    def test_dishonest_record_detected(self, base_orch):
        """失信被执行人 → 追加张铁柱"""
        results = [
            {"ok": True, "text": "发现失信被执行人记录3条。", "rid": "zhao-gang"},
        ]
        signals = base_orch._extract_signals(results)
        matched = [s for s in signals if s["signal"] == "dishonest_record"]
        assert len(matched) >= 1
        assert matched[0]["append_role"] == "zhang-tie-zhu"

    def test_many_related_detected(self, base_orch):
        """关联企业超过10家 → 追加赵刚"""
        results = [
            {"ok": True, "text": "该公司关联企业超过10家，关联交易频繁。", "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        matched = [s for s in signals if s["signal"] == "many_related"]
        assert len(matched) >= 1

    def test_cashflow_quality_detected(self, base_orch):
        """现金流质量差 → 追加郑慎之"""
        results = [
            {"ok": True, "text": "经营现金流为负，现金流覆盖不足。", "rid": "li-ming-yuan"},
        ]
        signals = base_orch._extract_signals(results)
        matched = [s for s in signals if s["signal"] == "cashflow_quality"]
        assert len(matched) >= 1
        assert matched[0]["append_role"] == "zheng-shen-zhi"

    def test_registration_mismatch_detected(self, base_orch):
        """注册资本异常 → 追加郑慎之"""
        results = [
            {"ok": True, "text": "发现注册资本异常，注册资金与经营不匹配。", "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        matched = [s for s in signals if s["signal"] == "registration_mismatch"]
        assert len(matched) >= 1

    def test_no_signals_in_clean_text(self, base_orch):
        """干净文本无信号"""
        results = [
            {"ok": True, "text": "公司经营正常，财务稳健。", "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        assert signals == []

    def test_max_2_signals_returned(self, base_orch):
        """最多返回 2 个信号（按优先级）"""
        # Text with multiple signals
        results = [
            {"ok": True, "text": (
                "实控人不一致，存在代持。"
                "大存大贷现象明显。"
                "失信被执行人记录。"
                "关联企业超过10家。"
            ), "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        assert len(signals) <= 2

    def test_failed_results_excluded(self, base_orch):
        """失败的结果不计入信号检测"""
        results = [
            {"ok": False, "text": "实控人不一致", "rid": "zhang-tie-zhu"},
        ]
        signals = base_orch._extract_signals(results)
        assert signals == []


# ══════════════════════════════════════════════════════════
#  _build_context 测试
# ══════════════════════════════════════════════════════════


class TestBuildContext:
    def test_builds_from_results(self, base_orch):
        results = [
            {"ok": True, "name": "张铁柱", "text": "工商信息查询结果。"},
            {"ok": True, "name": "李明远", "text": "财务分析结果。"},
        ]
        ctx = base_orch._build_context(results)
        assert "张铁柱" in ctx
        assert "李明远" in ctx
        assert "工商信息查询结果" in ctx
        assert "财务分析结果" in ctx

    def test_max_chars_truncation(self, base_orch):
        """超过 max_chars 时截断"""
        results = [
            {"ok": True, "name": "测试", "text": "A" * 5000},
        ]
        ctx = base_orch._build_context(results, max_chars=500)
        assert len(ctx) < 2000  # header + truncated text, well under 5000

    def test_failed_results_excluded(self, base_orch):
        """失败结果被排除"""
        results = [
            {"ok": True, "name": "正常", "text": "正常数据。"},
            {"ok": False, "name": "失败", "text": "失败数据。"},
        ]
        ctx = base_orch._build_context(results)
        assert "正常" in ctx
        assert "失败" not in ctx

    def test_empty_results(self, base_orch):
        assert base_orch._build_context([]) == ""

    def test_result_without_name_uses_rid(self, base_orch):
        results = [
            {"ok": True, "rid": "agent-x", "text": "数据。"},
        ]
        ctx = base_orch._build_context(results)
        assert "agent-x" in ctx


# ══════════════════════════════════════════════════════════
#  _check_consistency 测试
# ══════════════════════════════════════════════════════════


class TestCheckConsistency:
    def test_finds_conflicts_from_zheng_shen_zhi(self, base_orch):
        """郑慎之输出中的 [冲突:xxx] 被提取"""
        p2_results = [
            {"ok": True, "rid": "zheng-shen-zhi",
             "text": "数据验证结果。[冲突: 注册资本不一致，天眼查1000万 vs 企查查1500万]"},
        ]
        conflicts = base_orch._check_consistency([], p2_results)
        assert len(conflicts) >= 1
        assert "冲突" in conflicts[0]

    def test_empty_when_no_zheng_shen_zhi(self, base_orch):
        p2_results = [
            {"ok": True, "rid": "wu-de-hou", "text": "质检通过。"},
        ]
        conflicts = base_orch._check_consistency([], p2_results)
        assert conflicts == []

    def test_empty_when_no_conflicts_in_text(self, base_orch):
        p2_results = [
            {"ok": True, "rid": "zheng-shen-zhi", "text": "数据一致，无不一致项。"},
        ]
        conflicts = base_orch._check_consistency([], p2_results)
        assert conflicts == []


# ══════════════════════════════════════════════════════════
#  No Fabrication Rule 常量测试
# ══════════════════════════════════════════════════════════


class TestNoFabricationRule:
    def test_nfr_contains_key_sections(self):
        """NFR 包含关键章节"""
        assert "第1层" in NO_FABRICATION_RULE
        assert "第2层" in NO_FABRICATION_RULE
        assert "第6层" in NO_FABRICATION_RULE
        assert "绝对不能编造" in NO_FABRICATION_RULE

    def test_tagline_contains_key_rules(self):
        """Tagline 包含关键提醒"""
        assert "[来源:" in NO_FABRICATION_TAGLINE
        assert "[未获取]" in NO_FABRICATION_TAGLINE
        assert "[待核实]" in NO_FABRICATION_TAGLINE
        assert "[数据不一致]" in NO_FABRICATION_TAGLINE


# ══════════════════════════════════════════════════════════
#  模板测试
# ══════════════════════════════════════════════════════════


class TestTemplates:
    def test_phase1_templates_for_all_roles(self):
        """Phase 1 模板覆盖所有角色"""
        expected_roles = [
            "zhang-tie-zhu", "li-ming-yuan", "wang-si-yuan",
            "zhao-gang", "ma-li-quan", "zhou-tong",
        ]
        for role in expected_roles:
            assert role in PHASE1_USER_TEMPLATES, f"{role} missing from PHASE1"

    def test_phase2_templates_for_all_roles(self):
        """Phase 2 模板覆盖所有角色"""
        expected_roles = ["zheng-shen-zhi", "wu-de-hou"]
        for role in expected_roles:
            assert role in PHASE2_USER_TEMPLATES

    def test_phase3_templates_for_all_roles(self):
        """Phase 3 模板覆盖所有角色"""
        expected_roles = ["liu-wen-hua", "yan-hao-kan"]
        for role in expected_roles:
            assert role in PHASE3_USER_TEMPLATES

    def test_all_templates_combined_correctly(self):
        """ALL_USER_TEMPLATES 包含所有模板"""
        expected = set(PHASE1_USER_TEMPLATES) | set(PHASE2_USER_TEMPLATES) | set(PHASE3_USER_TEMPLATES)
        assert set(ALL_USER_TEMPLATES) == expected

    def test_template_returns_string(self):
        """模板函数返回字符串"""
        for role_id, fn in ALL_USER_TEMPLATES.items():
            result = fn("测试公司")
            assert isinstance(result, str)
            assert len(result) > 10
            assert "测试公司" in result


# ══════════════════════════════════════════════════════════
#  条件分支规则测试
# ══════════════════════════════════════════════════════════


class TestConditionalBranchRules:
    def test_all_signals_have_required_fields(self):
        """所有信号规则包含必要字段"""
        for sig_id, rule in CONDITIONAL_BRANCH_RULES.items():
            assert "signal_keywords" in rule, f"{sig_id} missing keywords"
            assert "append_role" in rule, f"{sig_id} missing append_role"
            assert "desc" in rule, f"{sig_id} missing desc"
            assert len(rule["signal_keywords"]) > 0

    def test_all_append_roles_are_valid(self):
        """所有追加角色在 ROLE_FILE_MAP 中"""
        from api.config import ROLE_FILE_MAP
        for rule in CONDITIONAL_BRANCH_RULES.values():
            role = rule["append_role"]
            assert role in ROLE_FILE_MAP, f"Unknown role: {role}"


# ══════════════════════════════════════════════════════════
#  _make_agent_config 测试
# ══════════════════════════════════════════════════════════


class TestMakeAgentConfig:
    def test_config_for_known_role(self, base_orch, sample_agent):
        """已知角色的 config 正确生成"""
        # Boot registry with test agent
        base_orch.registry._agents["zhang-tie-zhu"] = sample_agent
        cfg = base_orch._make_agent_config(sample_agent)
        assert cfg["agent_id"] == "zhang-tie-zhu"
        assert cfg["agent_name"] == "张铁柱"
        assert "user_prompt" in cfg
        assert "inner_monologue" in cfg
        assert "测试科技" in cfg["user_prompt"]

    def test_config_includes_tagline(self, base_orch, sample_agent):
        """config 包含铁律提醒"""
        base_orch.registry._agents["zhang-tie-zhu"] = sample_agent
        cfg = base_orch._make_agent_config(sample_agent)
        assert "【铁律提醒】" in cfg["user_prompt"]

    def test_config_unknown_role(self, base_orch):
        """未知角色使用通用 prompt"""
        p = PersonalityProfile(agent_id="unknown", display_name="未知")
        agent = DueDiligenceAgent("unknown", p, "")
        cfg = base_orch._make_agent_config(agent)
        assert "user_prompt" in cfg
        assert "尽调分析" in cfg["user_prompt"]

    def test_config_includes_key_findings(self, base_orch, sample_agent):
        """有 key_findings 时附带此前发现"""
        base_orch.registry._agents["zhang-tie-zhu"] = sample_agent
        sample_agent.memory.key_findings.append("发现1: 注册资本异常")
        cfg = base_orch._make_agent_config(sample_agent)
        assert "此前发现" in cfg["user_prompt"]
        assert "发现1" in cfg["user_prompt"]
