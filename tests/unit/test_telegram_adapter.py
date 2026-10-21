"""Unit tests for TelegramChannelLookup (t.me/s/ public preview)."""
import pytest
from adapters.telegram_adapter import TelegramChannelLookup


SAMPLE_PAGE = """
<div class="tgme_channel_info_header_title"><span dir="auto">测试频道</span></div>
<div class="tgme_channel_info_counter"><span class="counter_value">12.5K</span>&nbsp;<span class="counter_type">subscribers</span></div>
<div class="tgme_channel_info_description">这是一个测试频道的简介</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap" data-post="testchan/100">
  <div class="tgme_widget_message text_not_supported_wrap js-widget_message">
    <div class="tgme_widget_message_text js-message_text" dir="auto">找<b>XX公司</b>老板，电话 13800138000<br>有偿提供线索</div>
    <div class="tgme_widget_message_footer compact js-message_footer">
      <div class="tgme_widget_message_info short js-message_info">
        <span class="tgme_widget_message_views">1.2K</span><span class="copyonly"> views</span><span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/testchan/100"><time datetime="2026-10-20T08:00:00+00:00" class="time">08:00</time></a></span>
      </div>
    </div>
  </div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap" data-post="testchan/99">
  <div class="tgme_widget_message text_not_supported_wrap js-widget_message">
    <div class="tgme_widget_message_text js-message_text" dir="auto">纯图片消息</div>
    <div class="tgme_widget_message_footer compact js-message_footer">
      <div class="tgme_widget_message_info short js-message_info">
        <span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/testchan/99"><time datetime="2026-10-19T08:00:00+00:00" class="time">08:00</time></a></span>
      </div>
    </div>
  </div>
</div>
"""

EMPTY_PAGE = '<html><head><title>Telegram Messenger</title></head><body>no channel here</body></html>'


def _adapter():
    a = TelegramChannelLookup()
    a._robots_checker = lambda *args: True
    return a


def test_parse_channel_page_extracts_all_fields():
    ch = TelegramChannelLookup.parse_channel_page(SAMPLE_PAGE)
    assert ch["channel_found"] is True
    assert ch["channel_title"] == "测试频道"
    assert ch["subscribers"] == "12.5K subscribers"
    assert "测试频道" in ch["description"]
    assert ch["message_count"] == 2


def test_parse_messages_extracts_text_views_date():
    msgs = TelegramChannelLookup.parse_messages(SAMPLE_PAGE)
    assert len(msgs) == 2
    m0 = msgs[0]
    assert m0["post_id"] == "testchan/100"
    assert "XX公司" in m0["text"]
    assert "13800138000" in m0["text"]  # public contact info preserved, not masked
    assert "<b>" not in m0["text"]  # tags stripped
    assert m0["published_at"] == "2026-10-20T08:00:00+00:00"
    assert m0["views"] == "1.2K"
    assert m0["link"] == "https://t.me/testchan/100"


def test_parse_messages_missing_views_tolerated():
    msgs = TelegramChannelLookup.parse_messages(SAMPLE_PAGE)
    m1 = msgs[1]
    assert m1["post_id"] == "testchan/99"
    assert m1["views"] == ""  # no views span -> empty, no crash


def test_empty_page_channel_not_found():
    ch = TelegramChannelLookup.parse_channel_page(EMPTY_PAGE)
    assert ch["channel_found"] is False
    assert ch["message_count"] == 0
    assert ch["messages"] == []


def test_build_url_sanitizes_username():
    a = _adapter()
    assert a._build_url("@durov") == "https://t.me/s/durov"
    assert a._build_url("https://t.me/durov") == "https://t.me/s/durov"
    assert a._build_url("durov", before="durov/531") == "https://t.me/s/durov?before=durov%2F531"


def test_query_returns_structured_fields():
    a = _adapter()
    a._execute_query_override = lambda url, headers: (200, SAMPLE_PAGE, "")
    result = a.query("testchan")
    assert result["response_status"] == 200
    fields = result["fields"]
    assert fields["channel_found"] is True
    assert fields["message_count"] == 2
    assert result["source_domain"] == "t.me"


def test_audit_does_not_log_raw_keyword():
    # Base class hashes the keyword (query_params_hash), never stores raw.
    # Verify via the real _record_audit path with a capturing audit log.
    import hashlib

    records = []

    class FakeAudit:
        def log(self, rec):
            records.append(rec)

    a = _adapter()
    a.audit = FakeAudit()
    a._execute_query_override = lambda url, headers: (200, SAMPLE_PAGE, "")
    result = a.query("sensitive_channel_name")
    assert records, "audit record should exist"
    rec = records[0]
    assert "sensitive_channel_name" not in str(rec)
    expected_hash = hashlib.sha256(b"sensitive_channel_name").hexdigest()[:12]
    assert rec.query_params_hash == expected_hash
    assert result["query_subject_hash"] == expected_hash
