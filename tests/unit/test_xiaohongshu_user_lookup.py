"""Tests for Xiaohongshu user-dimension parsing (browser-assisted, offline)."""

from adapters.xiaohongshu_adapter import XiaohongshuNoteLookup

# Shape 1: {"data": {"basic_info": {...}}}
FIXTURE_BASIC_INFO = {
    "data": {
        "basic_info": {
            "user_id": "5f4c3b2a0000000001001234",
            "nickname": "测试达人",
            "red_id": "xiaohongshu123",
            "desc": "美妆分享 | 合作vx: beautyvx",
            "location": "上海",
            "gender": 1,
            "fans": 88000,
            "follows": 500,
            "notes": 320,
            "images": "https://sns-avatar-qc.xhscdn.com/avatar/abc.jpg",
        }
    }
}

# Shape 4: flat profile
FIXTURE_FLAT = {
    "nickname": "扁平用户",
    "nick_name": "",
    "redId": "flat999",
    "introduction": "简介文本",
    "follower_count": 12,
    "follow_count": 34,
    "note_count": 5,
    "user_id": "abc123",
}


def _adapter():
    return XiaohongshuNoteLookup(sleeper=lambda s: None)


def test_parse_user_api_shape():
    a = _adapter()
    out = a.parse_browser_user_result(FIXTURE_BASIC_INFO)
    assert out["response_status"] == 200
    fields = out["fields"]
    assert fields["user_found"] is True
    p = fields["profile"]
    assert p["nickname"] == "测试达人"
    assert p["red_id"] == "xiaohongshu123"
    assert "vx" in p["bio"]
    assert p["location"] == "上海"
    assert p["fans_count"] == 88000
    assert p["follows_count"] == 500
    assert p["notes_count"] == 320
    assert p["profile_url"] == "https://www.xiaohongshu.com/user/profile/5f4c3b2a0000000001001234"
    assert a.audit.verify_integrity()


def test_parse_flat_shape_with_aliases():
    a = _adapter()
    out = a.parse_browser_user_result(FIXTURE_FLAT)
    p = out["fields"]["profile"]
    assert p["nickname"] == "扁平用户"
    assert p["red_id"] == "flat999"
    assert p["bio"] == "简介文本"
    assert p["fans_count"] == 12


def test_parse_user_invalid_json():
    a = _adapter()
    out = a.parse_browser_user_result("{not json")
    assert out["error"] == "invalid_json"


def test_parse_user_no_profile():
    a = _adapter()
    out = a.parse_browser_user_result({"data": {}})
    assert out["error"] == "profile_not_found"


def test_query_user_is_browser_assisted():
    a = _adapter()
    out = a.query_user("测试达人")
    assert out["error"] == "interaction_required"
    assert "user/profile" in out["interaction_instructions"]
    assert out["source_type"] == "social_user_xiaohongshu"
