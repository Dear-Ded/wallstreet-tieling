"""Tests for PhoneMarkLookup adapter."""
import pytest
from adapters.phone_mark_adapter import PhoneMarkLookup


# Realistic chahaoba business directory page (simplified)
BIZ_PAGE_HTML = """<html><head><title>☎️宁波市羅亞帝時尚造型(鼓樓城門店)：0574-56665900 | 查號吧 📞</title></head>
<body><div id="mw-content-text">
<p>0574-56665900是哪裡的電話？宁波市羅亞帝時尚造型(鼓樓城門店)的電話是0574-56665900。</p>
<p>宁波市羅亞帝時尚造型(鼓樓城門店)位于浙江省宁波市海曙區中山西路76號。</p>
<p>如果您需要聯繫宁波市羅亞帝時尚造型(鼓樓城門店)，可以在本頁面上找到詳細的聯繫方式。</p>
</div><!-- end content --></body></html>"""

# User query page with spam reports
QUERY_PAGE_HTML = """<html><head><title>號碼13800138000 | 查號吧 📞</title></head>
<body><div id="mw-content-text">
<p>提出查詢要求</p>
<p>留言：這個號碼天天打騷擾電話，推銷貸款，煩死了</p>
<p>留言：詐騙電話，大家小心不要上當</p>
<p>下面是本站系統對13800138000進行的自動分析：</p>
<p>13800138000是一個國內手機號碼，138卡，1380013號段。</p>
<p>歸屬省份地區：北京</p>
</div><!-- end content --></body></html>"""

EMPTY_PAGE_HTML = """<html><head><title>查號吧</title></head><body></body></html>"""


class TestNormalizePhone:
    def test_strips_dashes_spaces(self):
        assert PhoneMarkLookup.normalize_phone("138-0013-8000") == "13800138000"
        assert PhoneMarkLookup.normalize_phone("0574 56665900") == "057456665900"

    def test_strips_country_code(self):
        assert PhoneMarkLookup.normalize_phone("+8613800138000") == "13800138000"
        assert PhoneMarkLookup.normalize_phone("008613800138000") == "13800138000"

    def test_strips_parentheses(self):
        assert PhoneMarkLookup.normalize_phone("(0574)56665900") == "057456665900"


class TestIsValidPhone:
    def test_valid_mobile(self):
        assert PhoneMarkLookup.is_valid_phone("13800138000")
        assert PhoneMarkLookup.is_valid_phone("138-0013-8000")
        assert PhoneMarkLookup.is_valid_phone("+8613800138000")

    def test_valid_landline(self):
        assert PhoneMarkLookup.is_valid_phone("057456665900")
        assert PhoneMarkLookup.is_valid_phone("0574-56665900")

    def test_invalid(self):
        assert not PhoneMarkLookup.is_valid_phone("12345")
        assert not PhoneMarkLookup.is_valid_phone("abc")
        assert not PhoneMarkLookup.is_valid_phone("")
        assert not PhoneMarkLookup.is_valid_phone("1380013800")  # too short


class TestParsePhonePage:
    def test_business_page(self):
        parsed = PhoneMarkLookup.parse_phone_page(BIZ_PAGE_HTML)
        assert parsed["phone_found"] is True
        assert parsed["phone"] == "0574-56665900"
        assert "羅亞帝" in parsed["business_name"]
        assert "宁波" in parsed["city"] or "寧波" in parsed["city"]

    def test_query_page_with_marks(self):
        parsed = PhoneMarkLookup.parse_phone_page(QUERY_PAGE_HTML)
        assert parsed["phone_found"] is True
        assert parsed["phone"] == "13800138000"
        signals = {s["signal"] for s in parsed["mark_signals"]}
        assert "spam" in signals or "fraud" in signals or "loan" in signals
        assert len(parsed["user_reports"]) > 0

    def test_empty_page(self):
        parsed = PhoneMarkLookup.parse_phone_page(EMPTY_PAGE_HTML)
        assert parsed["phone_found"] is False

    def test_garbage_input(self):
        parsed = PhoneMarkLookup.parse_phone_page("")
        assert parsed["phone_found"] is False
        parsed = PhoneMarkLookup.parse_phone_page("<html></html>")
        assert parsed["phone_found"] is False


class TestExtractPublicFields:
    def test_fields_structure(self):
        adapter = PhoneMarkLookup()
        fields = adapter._extract_public_fields(BIZ_PAGE_HTML)
        assert "phone_found" in fields
        assert "business_name" in fields
        assert "mark_signals" in fields
        assert fields["source"] == "tw.chahaoba.com"

    def test_empty_input(self):
        adapter = PhoneMarkLookup()
        fields = adapter._extract_public_fields("")
        assert fields["phone_found"] is False


class TestQueryValidation:
    def test_invalid_phone_rejected(self):
        adapter = PhoneMarkLookup()
        result = adapter.query("not-a-phone")
        assert result["status"] == "invalid_input"

    def test_empty_rejected(self):
        adapter = PhoneMarkLookup()
        result = adapter.query("")
        assert result["status"] == "invalid_input"


class TestAdapterMetadata:
    def test_no_credentials_required(self):
        assert PhoneMarkLookup.requires_credentials is False
        assert PhoneMarkLookup.requires_interaction is False

    def test_data_boundary(self):
        assert PhoneMarkLookup.data_boundary == "fully_public"

    def test_rate_limit(self):
        assert PhoneMarkLookup.min_request_interval >= 2.0
