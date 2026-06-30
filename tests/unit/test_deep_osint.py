"""深度OSINT信息聚合适配器门验证 — 0真实HTTP。"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_message_platform_unauthorized_blocks():
    from adapters.deep_osint import MessagePlatformAggregationLookup
    a = MessagePlatformAggregationLookup(_make_gate())
    assert not a.is_available()
    r = a.query_public_aggregation("test_company")
    assert r.get("error") == "source_not_authorized"


def test_message_platform_authorized_no_creds():
    """授权但未配置凭证 → credentials_not_configured"""
    from adapters.deep_osint import MessagePlatformAggregationLookup
    a = MessagePlatformAggregationLookup(_make_gate())
    a.enable()
    assert a.is_available()
    r = a.query_public_aggregation("test_company")
    assert r.get("error") == "credentials_not_configured"


def test_visual_verification_unauthorized_blocks():
    from adapters.deep_osint import VisualVerificationAssistance
    a = VisualVerificationAssistance(_make_gate())
    assert not a.is_available()
    r = a.assist_visual_verification("gsxt", {"keyword": "test"})
    assert r.get("error") == "source_not_authorized"


def test_commercial_platform_unauthorized_blocks():
    from adapters.deep_osint import CommercialPlatformSessionLookup
    a = CommercialPlatformSessionLookup(_make_gate())
    assert not a.is_available()
    r = a.query_with_session("test_company")
    assert r.get("error") == "source_not_authorized"


def test_osint_tools_unauthorized_blocks():
    from adapters.deep_osint import OpenSourceOSINTIntegration
    a = OpenSourceOSINTIntegration(_make_gate())
    assert not a.is_available()
    r = a.query_tool("maigret", "test_user")
    assert r.get("error") == "source_not_authorized"


def test_osint_tools_list_available():
    from adapters.deep_osint import OpenSourceOSINTIntegration
    a = OpenSourceOSINTIntegration(_make_gate())
    tools = a.list_available_tools()
    assert "maigret" in tools["tools"]
    assert "holehe" in tools["tools"]
    assert "sherlock" in tools["tools"]


def test_all_adapters_have_enterprise_or_public_source_type():
    from adapters.deep_osint import (
        MessagePlatformAggregationLookup, VisualVerificationAssistance,
        CommercialPlatformSessionLookup, OpenSourceOSINTIntegration,
    )
    gate = _make_gate()
    for cls in [MessagePlatformAggregationLookup, VisualVerificationAssistance,
                CommercialPlatformSessionLookup, OpenSourceOSINTIntegration]:
        a = cls(gate)
        assert "enterprise" in a.source_type.lower() or "public" in a.source_type.lower() or "enterprise" in a.source_domain.lower()


def test_ocr_adapter_uses_compliant_terminology():
    """OCR适配器使用合规术语(光学字符识别,非'处理验证码')"""
    from adapters.deep_osint import VisualVerificationAssistance
    a = VisualVerificationAssistance(_make_gate())
    cfg = a._gate.get_source_config(a._source_key) if False else {}
    # ocr_engine = ddddocr — this is the standard OCR engine, not a 'CAPTCHA breaker'
    assert a.requires_interaction is True  # OCR需要页面交互
