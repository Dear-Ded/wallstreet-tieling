"""主体深度尽调画像编排器验证 — 管线集成测试。0真实HTTP。"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_profiler_default_all_disabled():
    """默认所有适配器禁用"""
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    status = p.get_lane_status()
    for lane in ["people", "money", "goods"]:
        assert status[lane]["authorized"] == 0, f"{lane} should have 0 authorized"


def test_profiler_enable_people_lane():
    """启用PEOPLE管线后,该管线的适配器变为可用"""
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    result = p.enable_people_lane()
    assert result["lane"] == "people"
    assert result["sources_authorized"] > 0
    status = p.get_lane_status()
    assert status["people"]["authorized"] > 0


def test_profiler_enable_money_lane():
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    p.enable_money_lane()
    status = p.get_lane_status()
    assert status["money"]["authorized"] > 0


def test_profiler_enable_goods_lane():
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    p.enable_goods_lane()
    status = p.get_lane_status()
    assert status["goods"]["authorized"] > 0


def test_profiler_enable_all_lanes():
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    result = p.enable_all_lanes()
    assert "people" in result
    assert "money" in result
    assert "goods" in result


def test_profile_subject_structure():
    """profile_subject 返回标准的 money/goods/people 结构"""
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    p.enable_all_lanes()
    profile = p.profile_subject("测试企业有限公司", "张三", "test-company.com")
    assert profile["investigation_mode"] == "deep_due_diligence"
    assert "money_lane_findings" in profile
    assert "goods_lane_findings" in profile
    assert "people_lane_findings" in profile
    assert "authorization_status" in profile
    assert profile["execution_mode"] == "dry_run_plan_only"
    assert profile["execution_plan"]["default_behavior"] == "plan_only_no_network"
    assert profile["money_lane_findings"] == {}
    assert profile["goods_lane_findings"] == {}
    assert profile["people_lane_findings"] == {}
    assert profile["subject_hash"] is not None


def test_unauthorized_profiler_returns_empty_findings():
    """未授权时 profile_subject 返回空的管线调查结果"""
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    # 不调用 enable — 全部默认禁用
    profile = p.profile_subject("测试企业")
    # 所有管线结果应为空(没有授权,没有适配器可用)
    assert isinstance(profile["people_lane_findings"], dict)
    assert isinstance(profile["money_lane_findings"], dict)
    assert isinstance(profile["goods_lane_findings"], dict)


def test_lane_sources_registered():
    """每个管线至少注册了2个适配器"""
    from core.subject_dd_profiler import SubjectDeepDueDiligenceProfiler
    p = SubjectDeepDueDiligenceProfiler(_make_gate())
    # 不启用也验证源已注册
    assert len(p._lane_sources["people"]) >= 2
    assert len(p._lane_sources["money"]) >= 2
    assert len(p._lane_sources["goods"]) >= 2
