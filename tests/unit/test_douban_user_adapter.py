"""Tests for Douban public user page adapter (offline fixtures, 2026-10-21 HTML shapes)."""

from adapters.douban_user_adapter import DoubanUserLookup

# Shape distilled from 2026-10-21 live fetch of https://www.douban.com/people/ahbei/
FIXTURE_PROFILE_HTML = """<!DOCTYPE html>
<html><head><title>阿北</title></head><body>
<div id="db-usr-profile">
  <div class="pic"><a class="nbg" href="#"><img class="userface" alt="" src="https://img9.doubanio.com/view/people/l/public/p1.jpg"/></a></div>
  <div class="info">
    <h1>阿北</h1>
    <div class="user-info">
      常居: 北京
      1000001 (ahbei)<br/>
      2006-01-09加入
      IP属地：未知
    </div>
  </div>
</div>
<div id="intro_display">Less is more</div>
</body></html>"""

FIXTURE_WALLED_HTML = """<html><head><title>登录豆瓣</title></head><body>
<div class="account-body">请先登录</div>
</body></html>"""


def _adapter(status_body):
    status, body = status_body
    return DoubanUserLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_parse_profile_page_fields():
    p = DoubanUserLookup.parse_profile_page(FIXTURE_PROFILE_HTML, "ahbei")
    assert p["user_found"] is True
    assert p["nickname"] == "阿北"
    assert p["uid"] == "ahbei"
    assert p["user_id_number"] == "1000001"
    assert p["uid_alias"] == "ahbei"
    assert p["location"] == "北京"
    assert p["registered_at"] == "2006-01-09"
    assert p["ip_location"] == "未知"
    assert p["intro"] == "Less is more"
    assert p["avatar"].startswith("https://img9.doubanio.com/")


def test_parse_profile_title_suffix_stripped():
    html = FIXTURE_PROFILE_HTML.replace("<title>阿北</title>", "<title>阿北的个人主页</title>")
    p = DoubanUserLookup.parse_profile_page(html, "ahbei")
    assert p["nickname"] == "阿北"


def test_parse_profile_walled_page_not_found():
    p = DoubanUserLookup.parse_profile_page(FIXTURE_WALLED_HTML, "ahbei")
    assert p["user_found"] is False


def test_query_parses_profile():
    a = _adapter((200, FIXTURE_PROFILE_HTML))
    result = a.query("ahbei")
    assert result["status"] == "ok"
    assert result["fields"]["profile"]["nickname"] == "阿北"
    assert result["fields"]["profile"]["location"] == "北京"
    assert result["fields"]["profile_url"] == "https://www.douban.com/people/ahbei/"
    assert result["response_status"] == 200
    assert a.audit.verify_integrity()


def test_query_404_user_not_found():
    a = _adapter((404, None))
    result = a.query("no-such-user-zzz")
    assert result["status"] == "empty"
    assert result["error"] == "user_not_found"
    assert result["fields"] == {}


def test_query_invalid_uid():
    a = _adapter((200, FIXTURE_PROFILE_HTML))
    result = a.query("bad uid!!")
    assert result["error"] == "invalid_uid"


def test_data_boundary_and_rate_limit():
    a = _adapter((200, FIXTURE_PROFILE_HTML))
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.min_request_interval == 3.0


def test_parse_profile_self_claimed_kinship():
    """简介亲属自述 -> self_claimed_kinship（review 级线索）. (亲属关系 lane)"""
    html = FIXTURE_PROFILE_HTML.replace(
        '<div id="intro_display">Less is more</div>',
        '<div id="intro_display">张三的妻子，爱好摄影</div>',
    )
    profile = DoubanUserLookup.parse_profile_page(html, "lisi")
    claimed = profile.get("self_claimed_kinship") or []
    assert len(claimed) == 1
    assert claimed[0]["person_b"] == "张三"
    assert claimed[0]["relation_kind"] == "spouse"
    assert claimed[0]["evidence_level"] == "review"


def test_parse_profile_no_self_claimed_kinship():
    profile = DoubanUserLookup.parse_profile_page(FIXTURE_PROFILE_HTML, "ahbei")
    assert "self_claimed_kinship" not in profile
