"""Telegram公开数据聚合适配器验证"""


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate
    return UserAuthorizationGate("test")


def test_unauthorized_blocks():
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    a = TelegramPublicAggregationAdapter(_make_gate())
    r = a.query_aggregation_service("enterprise_lookup", "test_company")
    assert r.get("error") == "source_not_authorized"


def test_authorized_no_credentials():
    """授权但未配凭证 → credentials_not_configured"""
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    a = TelegramPublicAggregationAdapter(_make_gate())
    a.enable()
    r = a.query_aggregation_service("enterprise_lookup", "test")
    assert r.get("error") == "credentials_not_configured"


def test_unknown_service_type():
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    a = TelegramPublicAggregationAdapter(_make_gate())
    a.enable()
    r = a.query_aggregation_service("nonexistent", "test")
    assert r.get("error") == "unknown_service_type"


def test_list_services():
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    a = TelegramPublicAggregationAdapter(_make_gate())
    services = a.list_available_services()
    assert "enterprise_lookup" in services["services"]
    assert "court_record_lookup" in services["services"]
    assert "cross_platform_identity" in services["services"]


def test_all_services_have_data_origin():
    """所有服务标注了数据来源(均为官方登记系统)"""
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    a = TelegramPublicAggregationAdapter(_make_gate())
    for svc, info in a.PUBLIC_AGGREGATION_SERVICES.items():
        assert info["data_origin"], f"{svc} 缺少数据来源标注"
        assert "GSXT" in info["data_origin"] or "官方" in info["data_origin"] or "公开" in info["data_origin"] or "裁判" in info["data_origin"] or "信用" in info["data_origin"] or "多个公开" in info["data_origin"]


def test_disable_revokes():
    from adapters.telegram_aggregation import TelegramPublicAggregationAdapter
    gate = _make_gate()
    a = TelegramPublicAggregationAdapter(gate)
    a.enable()
    assert a.is_available()
    gate.disable_source("telegram_public_aggregation")
    assert not a.is_available()
