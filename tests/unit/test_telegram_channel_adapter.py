"""Tests for Telegram public channel preview adapter (offline fixtures)."""

import pytest

from adapters.telegram_channel_adapter import TelegramChannelLookup

FIXTURE_HEADER = """
<div class="tgme_channel_info">
<div class="tgme_channel_info_header">
<div class="tgme_channel_info_header_title"><span dir="auto">Test Channel</span></div>
<div class="tgme_channel_info_counter"><span class="counter_value">12.5K</span> <span class="counter_type">subscribers</span></div>
<div class="tgme_channel_info_counter"><span class="counter_value">310</span> <span class="counter_type">photos</span></div>
<div class="tgme_channel_info_description">A channel for testing.</div>
</div>
</div>
"""

FIXTURE_POSTS = """
<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="testchan/101">
<div class="tgme_widget_message_bubble">
<div class="tgme_widget_message_text js-message_text" dir="auto">Hello world<br>second line <a href="https://example.com">link</a></div>
<div class="tgme_widget_message_footer">
<span class="tgme_widget_message_views">1.2K</span>
<a class="tgme_widget_message_date" href="https://t.me/testchan/101"><time datetime="2026-10-20T08:00:00+00:00" class="time">08:00</time></a>
</div>
</div>
</div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="testchan/100">
<div class="tgme_widget_message_bubble">
<div class="tgme_widget_message_text js-message_text" dir="auto"></div>
<div class="tgme_widget_message_photo_wrap"></div>
<div class="tgme_widget_message_footer">
<a class="tgme_widget_message_date" href="https://t.me/testchan/100"><time datetime="2026-10-19T08:00:00+00:00" class="time">08:00</time></a>
</div>
</div>
</div>
</div>
"""

FULL = FIXTURE_HEADER + FIXTURE_POSTS


def _adapter(body, final_url="https://t.me/s/testchan"):
    return TelegramChannelLookup(
        execute_query=lambda url, headers: (200, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url_uses_preview_path():
    a = _adapter(FULL)
    url = a._build_url("testchan", handle="testchan")
    assert url == "https://t.me/s/testchan"


def test_normalize_handle():
    assert TelegramChannelLookup.normalize_handle("@Test_Chan1") == "test_chan1"
    assert TelegramChannelLookup.normalize_handle("  durov ") == "durov"
    assert TelegramChannelLookup.normalize_handle("has space") is None
    assert TelegramChannelLookup.normalize_handle("ab") is None  # too short


def test_invalid_handle_returns_structured_empty():
    a = _adapter("")
    result = a.query("not a handle!!")
    assert result["fields"] == {}
    assert "handle_invalid" in result["error"]


def test_redirect_to_plain_tme_means_no_preview():
    a = _adapter("<html>whatever</html>")
    fields = a._extract_public_fields(("https://t.me/testchan", "<html>x</html>"))
    assert fields["channel_found"] is False


def test_parse_channel_header():
    header = TelegramChannelLookup.parse_channel_header(FULL)
    assert header["title"] == "Test Channel"
    assert header["description"] == "A channel for testing."
    assert header["subscribers"] == 12500
    assert header["subscribers_raw"] == "12.5K"
    assert header["photos"] == 310


def test_parse_posts_extracts_text_time_views():
    posts = TelegramChannelLookup.parse_posts(FULL)
    assert len(posts) == 2
    first = posts[0]
    assert first["handle"] == "testchan"
    assert first["post_id"] == "101"
    assert first["url"] == "https://t.me/testchan/101"
    assert first["posted_at"] == "2026-10-20T08:00:00+00:00"
    assert "Hello world" in first["text"] and "second line" in first["text"]
    assert first["views"] == 1200
    # second post: no text, photo media flag
    second = posts[1]
    assert "text" not in second
    assert second["media"] == ["photo"]
    assert second["posted_at"] == "2026-10-19T08:00:00+00:00"


def test_parse_compact_count():
    p = TelegramChannelLookup._parse_compact_count
    assert p("10.3M") == 10300000
    assert p("1.2K") == 1200
    assert p("531") == 531
    assert p("2.5B") == 2500000000
    assert p("n/a") is None


def test_query_full_result_shape():
    a = _adapter(FULL)
    result = a.query("testchan")
    assert result["source_domain"] == "t.me"
    assert result["data_boundary"] == "fully_public"
    fields = result["fields"]
    assert fields["channel_found"] is True
    assert fields["channel"]["title"] == "Test Channel"
    assert fields["post_count"] == 2
    assert result["field_count"] > 0
    # audit trail recorded
    trail = a.audit.get_trail()
    assert len(trail) == 1
    assert trail[0]["source_domain"] == "t.me"
    assert trail[0]["robots_txt_checked"] is True


def test_query_channel_explicit_api():
    a = _adapter(FULL)
    result = a.query_channel("testchan")
    assert result["fields"]["channel_found"] is True


def test_query_channel_invalid_handle():
    a = _adapter(FULL)
    result = a.query_channel("!!bad")
    assert result["fields"] == {}


def test_empty_body_marks_not_found():
    a = _adapter("")
    fields = a._extract_public_fields(("https://t.me/s/ghost", ""))
    assert fields["channel_found"] is False


@pytest.mark.parametrize("views,expected", [("5.83M", 5830000), ("999", 999)])
def test_views_variants(views, expected):
    html = FIXTURE_HEADER + (
        '<div class="tgme_widget_message_wrap js-widget_message_wrap">'
        '<div data-post="testchan/1">'
        '<div class="tgme_widget_message_text js-message_text">x</div>'
        f'<span class="tgme_widget_message_views">{views}</span>'
        "</div></div>"
    )
    posts = TelegramChannelLookup.parse_posts(html)
    assert posts[0]["views"] == expected


TGSTAT_FIXTURE = """
<html><head><meta name="description" content="Founder of Telegram."></head><body>
<h1 class="text-dark"> Pavel Durov </h1>
<a href="https://t.me/durov" role="button" class="btn btn-outline-info btn-rounded">@durov</a>
<a href="https://t.me/feed" role="button" class="btn btn-outline-info btn-rounded">@feed</a>
<a href="https://t.me/lean" role="button" class="btn btn-outline-info btn-rounded">@lean</a>
<div class="card card-body border pt-1 pb-2"><div class="row"><div class="col col-6">
<h2 class="mb-1 text-dark">10 303 163</h2>
<div class="text-uppercase font-12">subscribers</div>
</div></div></div>
</body></html>
"""


def test_parse_tgstat_channel():
    out = TelegramChannelLookup.parse_tgstat_channel(TGSTAT_FIXTURE, "durov")
    assert out["handle"] == "durov"
    assert out["description"] == "Founder of Telegram."
    assert out["subscribers_exact"] == 10303163
    assert out["related_handles"] == ["feed", "lean"]  # own handle excluded
    assert out["channel_url"] == "https://tgstat.com/channel/@durov"


def test_parse_tgstat_channel_no_related():
    body = TGSTAT_FIXTURE.replace('href="https://t.me/feed"', 'href="https://x.example/feed"')
    body = body.replace('href="https://t.me/lean"', 'href="https://x.example/lean"')
    out = TelegramChannelLookup.parse_tgstat_channel(body, "durov")
    assert "related_handles" not in out
    assert out["subscribers_exact"] == 10303163


def test_enrich_with_tgstat_uses_offline_body(monkeypatch):
    import urllib.request

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return TGSTAT_FIXTURE.encode()

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=30: _Resp()
    )
    a = TelegramChannelLookup(robots_checker=lambda d, u: True, sleeper=lambda s: None)
    out = a.enrich_with_tgstat("durov")
    assert out["subscribers_exact"] == 10303163
    assert out["related_handles"] == ["feed", "lean"]
    # audit trail records the tgstat.com hop
    domains = [r["source_domain"] for r in a.audit.get_trail()]
    assert "tgstat.com" in domains


def test_enrich_with_tgstat_failure_returns_none(monkeypatch):
    import urllib.request

    def _boom(req, timeout=30):
        raise ConnectionError("down")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    a = TelegramChannelLookup(robots_checker=lambda d, u: True, sleeper=lambda s: None)
    assert a.enrich_with_tgstat("durov") is None


def test_query_with_enrich_merges_fields(monkeypatch):
    import urllib.request

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return TGSTAT_FIXTURE.encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: _Resp())
    a = _adapter(FULL)
    result = a.query("durov", enrich=True)
    assert result["fields"]["channel_found"] is True
    assert result["fields"]["tgstat"]["related_handles"] == ["feed", "lean"]
