"""安全边界验证测试 — 证明所有操作在公开/授权/可审计边界内"""
import json
import sys
import os

# Ensure project path is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _fake_execute(url, headers):
    return 200, "处罚决定书文号 Demo", ""


def _allow_robots(domain, url):
    return True


def test_creditchina_adapter_stays_within_public_boundary():
    """验证: 信用中国查询仅使用公开HTTP GET"""
    from adapters.creditchina_adapter import CreditchinaAdapter
    adapter = CreditchinaAdapter(execute_query=_fake_execute, robots_checker=_allow_robots)
    assert adapter.data_boundary == "fully_public"
    assert adapter.requires_credentials == False
    assert adapter.requires_interaction == False
    assert adapter.source_type == "government_public_disclosure"

    result = adapter.query("测试企业")
    assert result["data_boundary"] == "fully_public"
    assert result["source_type"] == "government_public_disclosure"
    assert "测试企业" not in result["query_subject_hash"]

    trail = adapter.audit.get_trail()
    assert len(trail) >= 1
    record = trail[0]
    assert record["data_boundary"] == "fully_public"
    assert record["requires_credentials"] == False
    assert record["robots_txt_checked"] == True
    assert record["rate_limit_applied"] != ""


def test_audit_logger_verify_integrity():
    """验证: 审计日志完整性检查通过"""
    from adapters.safe_research_adapter import ResearchAuditLogger, ResearchAuditRecord
    logger_inst = ResearchAuditLogger()
    logger_inst.log(ResearchAuditRecord(
        operation_type="public_record_query",
        source_domain="www.creditchina.gov.cn",
        source_type="government_public_disclosure",
        data_boundary="fully_public",
    ))
    assert logger_inst.verify_integrity() == True


def test_message_platform_adapter_requires_user_auth():
    """验证: 消息平台查询需要用户凭证"""
    from adapters.message_platform_query_adapter import MessagePlatformQueryAdapter
    adapter = MessagePlatformQueryAdapter(robots_checker=_allow_robots)
    assert adapter.data_boundary == "user_authorized"
    assert adapter.requires_credentials == True
    result = adapter.query("测试企业")
    assert result["error"] != ""


def test_rate_limit_enforcement():
    """验证: 频率限制生效"""
    from adapters.creditchina_adapter import CreditchinaAdapter
    sleeps = []
    adapter = CreditchinaAdapter(execute_query=_fake_execute, robots_checker=_allow_robots, sleeper=sleeps.append)
    adapter.min_request_interval = 0.5
    adapter.query("企业A")
    adapter.query("企业B")
    assert sleeps and sleeps[0] > 0


def test_query_params_are_hashed():
    """验证: 查询参数被哈希,审计日志不存明文"""
    from adapters.creditchina_adapter import CreditchinaAdapter
    adapter = CreditchinaAdapter(execute_query=_fake_execute, robots_checker=_allow_robots)
    adapter.query("某企业名称")
    trail = adapter.audit.get_trail()
    record = trail[0]
    audit_json = json.dumps(record, ensure_ascii=False)
    assert "某企业名称" not in audit_json
    assert len(record["query_params_hash"]) > 0
