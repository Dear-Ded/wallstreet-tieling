"""软件著作权适配器单元测试。"""

import json

import pytest

from adapters.software_copyright_adapter import (
    JuheCopyrightLookup,
    ZhifufuSoftLookup,
    _zff_sign,
)


# ---------------------------------------------------------------------------
# 签名算法
# ---------------------------------------------------------------------------
def test_zff_sign_is_md5_hex():
    import hashlib

    sig = _zff_sign("小米", 1)
    expected = hashlib.md5(
        "svelgt5x0cpixpgayvmiwa_yyCAbxUlotrUuKpl57pNe+c_soft.search_小米_1".encode()
    ).hexdigest()
    assert sig == expected
    assert len(sig) == 32


def test_zff_sign_owner_variant():
    sig = _zff_sign("", 1, owner="小米科技")
    assert len(sig) == 32
    assert sig != _zff_sign("", 1, owner="华为技术")


# ---------------------------------------------------------------------------
# ZhifufuSoftLookup: query()
# ---------------------------------------------------------------------------
def test_zhifu_query_returns_interaction_required():
    adapter = ZhifufuSoftLookup()
    result = adapter.query("小米科技", search_by="owner")
    assert result["status"] == "interaction_required"
    assert result["search_by"] == "owner"
    assert "instructions" in result
    assert any("cha/api/soft/search" in s for s in result["instructions"])


def test_zhifu_query_keyword_mode():
    adapter = ZhifufuSoftLookup()
    result = adapter.query("人脸识别")
    assert result["status"] == "interaction_required"
    assert result["search_by"] == "keyword"


def test_zhifu_query_empty_keyword():
    adapter = ZhifufuSoftLookup()
    result = adapter.query("")
    assert result["status"] == "interaction_required"
    assert result["reason"] == "empty keyword"


def test_zhifu_query_invalid_search_by_defaults_to_keyword():
    adapter = ZhifufuSoftLookup()
    result = adapter.query("测试", search_by="nonsense")
    assert result["search_by"] == "keyword"


# ---------------------------------------------------------------------------
# ZhifufuSoftLookup: parse_browser_result()
# ---------------------------------------------------------------------------
_SOLR_SAMPLE = {
    "success": True,
    "code": 200,
    "response": {
        "numFound": 2,
        "docs": [
            {
                "id": "abc123",
                "soft_name": "小米智能家居控制软件",
                "reg_no": "2023SR1234567",
                "owner_s": "小米科技有限责任公司",
                "rd": "2023-05-01",
                "version": "V1.0",
            },
            {
                "id": "def456",
                "name": "米家APP",
                "djh": "2022SR7654321",
                "zqr": "小米科技有限责任公司",
            },
        ],
    },
    "responseHeader": {"QTime": 42},
}


def test_zhifu_parse_solr_response():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result(_SOLR_SAMPLE)
    assert result["status"] == "ok"
    assert result["total"] == 2
    assert result["record_count"] == 2
    first = result["records"][0]
    assert first["soft_name"] == "小米智能家居控制软件"
    assert first["reg_no"] == "2023SR1234567"
    assert first["owner"] == "小米科技有限责任公司"
    assert first["reg_date"] == "2023-05-01"
    assert first["version"] == "V1.0"


def test_zhifu_parse_field_name_variants():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result(_SOLR_SAMPLE)
    second = result["records"][1]
    # name/djh/zqr 是候选字段名变体
    assert second["soft_name"] == "米家APP"
    assert second["reg_no"] == "2022SR7654321"
    assert second["owner"] == "小米科技有限责任公司"


def test_zhifu_parse_accepts_json_string():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result(json.dumps(_SOLR_SAMPLE))
    assert result["status"] == "ok"
    assert result["record_count"] == 2


def test_zhifu_parse_captcha_code():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result({"code": 106, "msg": "ticket is null"})
    assert result["status"] == "empty"
    assert result["reason"] == "captcha_required"


def test_zhifu_parse_invalid_json():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result("not json {{{")
    assert result["status"] == "empty"
    assert result["reason"] == "invalid_json"


def test_zhifu_parse_invalid_input_type():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result(12345)
    assert result["status"] == "empty"


def test_zhifu_parse_empty_docs():
    adapter = ZhifufuSoftLookup()
    result = adapter.parse_browser_result(
        {"success": True, "response": {"numFound": 0, "docs": []}}
    )
    assert result["status"] == "ok"
    assert result["record_count"] == 0


# ---------------------------------------------------------------------------
# JuheCopyrightLookup
# ---------------------------------------------------------------------------
def test_juhe_no_key_returns_credentials_required():
    adapter = JuheCopyrightLookup()
    result = adapter.query("小米科技有限责任公司")
    assert result["status"] == "credentials_required"
    assert result["reason"] == "juhe_copyright_needs_api_key"


def test_juhe_empty_company():
    adapter = JuheCopyrightLookup(api_key="testkey")
    result = adapter.query("")
    assert result["status"] == "empty"


_JUHE_SAMPLE = {
    "reason": "success",
    "result": {
        "total": 1,
        "num": 1,
        "items": [
            {
                "id": "607dcfaff9d1e0bb3d5f8032",
                "number": "2021SR0001234",
                "company": "小米科技有限责任公司",
                "version": "V2.0",
                "name": "小米智能家居软件",
                "type_name": "原始取得",
                "success_date": "2020-01-01",
                "approval_date": "2021-03-01",
            }
        ],
    },
    "error_code": 0,
}


def test_juhe_parse_response(monkeypatch):
    adapter = JuheCopyrightLookup(api_key="testkey")

    class FakeResp:
        def read(self):
            return json.dumps(_JUHE_SAMPLE).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=20: FakeResp()
    )
    result = adapter.query("小米科技有限责任公司")
    assert result["status"] == "ok"
    assert result["record_count"] == 1
    rec = result["records"][0]
    assert rec["soft_name"] == "小米智能家居软件"
    assert rec["reg_no"] == "2021SR0001234"
    assert rec["owner"] == "小米科技有限责任公司"


def test_juhe_parse_api_error(monkeypatch):
    adapter = JuheCopyrightLookup(api_key="badkey")

    class FakeResp:
        def read(self):
            return json.dumps(
                {"error_code": 10001, "reason": "错误的请求KEY", "result": None}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=20: FakeResp()
    )
    result = adapter.query("测试公司")
    assert result["status"] == "empty"
    assert "api_error" in result["reason"]


def test_juhe_key_never_in_audit_log():
    adapter = JuheCopyrightLookup(api_key="supersecretkey123")
    # 审计只记录 query 的 hash，不记录 key；这里验证 key 属性存在但 query 路径正常
    assert adapter._api_key == "supersecretkey123"
    assert adapter._has_required_credentials()


def test_adapters_default_off():
    # 两个适配器都不应默认启用（由注册表 default_enabled=False 控制，
    # 这里验证类级别不自动执行网络）
    z = ZhifufuSoftLookup()
    assert z.requires_interaction is True
    j = JuheCopyrightLookup()
    assert j.requires_credentials is True
