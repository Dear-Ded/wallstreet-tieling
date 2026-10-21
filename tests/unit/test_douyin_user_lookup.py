"""Tests for Douyin user-dimension lookup (DouyinUserLookup, offline)."""

from adapters.douyin_adapter import DouyinBusinessLookup, DouyinUserLookup

FIXTURE_PROFILE_JSON = {
    "status_code": 0,
    "user": {
        "sec_uid": "MS4wLjABAAAAxTestSecUid",
        "unique_id": "test.douyin",
        "nickname": "测试博主",
        "signature": "合作请私信 微信: testwx123",
        "follower_count": 120000,
        "following_count": 300,
        "aweme_count": 88,
        "total_favorited": 500000,
        "ip_location": "IP属地：北京",
        "enterprise_verify_reason": "",
        "verify_reason": "优质创作者",
    },
}

FIXTURE_POSTS_JSON = {
    "status_code": 0,
    "aweme_list": [
        {
            "aweme_id": "1",
            "desc": "探店视频",
            "create_time": 1760000000,
            "statistics": {"digg_count": 100, "comment_count": 5, "share_count": 2},
        }
    ],
}


def _autonomous_adapter():
    a = DouyinUserLookup(sleeper=lambda s: None)
    a._ttwid = "ttwid-test"
    a._ms_token = "ms-test"

    def fake_signed_get(base_url, params, timeout=20):
        if "profile/other" in base_url:
            return (200, FIXTURE_PROFILE_JSON, "")
        return (200, FIXTURE_POSTS_JSON, "")

    a._signed_get = fake_signed_get  # noqa: SLF001
    return a


def test_query_user_shapes_person_fields():
    a = _autonomous_adapter()
    out = a.query_user(sec_uid="MS4wLjABAAAAxTestSecUid")
    assert out["status"] == "ok"
    fields = out["fields"]
    assert fields["user_found"] is True
    p = fields["profile"]
    assert p["username"] == "test.douyin"
    assert p["nickname"] == "测试博主"
    assert "微信" in p["bio"]
    assert p["follower_count"] == 120000
    assert p["location"] == "IP属地：北京"
    assert p["verified"] == "优质创作者"
    assert len(fields["recent_posts"]) == 1
    assert fields["recent_posts"][0]["desc"] == "探店视频"
    assert fields["profile_url"].endswith("MS4wLjABAAAAxTestSecUid")


def test_query_routes_sec_uid_to_autonomous():
    a = _autonomous_adapter()
    out = a.query("测试博主", sec_uid="MS4wLjABAAAAxTestSecUid")
    assert out["status"] == "ok"
    assert out["fields"]["profile"]["nickname"] == "测试博主"


def test_query_without_uid_is_browser_assisted():
    a = DouyinUserLookup(sleeper=lambda s: None)
    out = a.query("测试博主")
    assert out.get("interaction_required") is True
    guide = out.get("interaction_guide") or []
    assert any("sec_user_id" in g for g in guide)
    assert out["error"] == ""


def test_query_user_no_uid_invalid():
    a = DouyinUserLookup(sleeper=lambda s: None)
    out = a.query_user()
    assert out["status"] == "invalid_input"


def test_browser_search_parser_reused_for_user_discovery():
    raw = {
        "data": [
            {"user_list": [
                {"user_info": {
                    "sec_uid": "MS4wLjABAAAAxTestSecUid",
                    "unique_id": "test.douyin",
                    "nickname": "测试博主",
                    "signature": "合作请私信",
                    "follower_count": 120000,
                }}
            ]}
        ]
    }
    parsed = DouyinUserLookup.parse_browser_search(raw)
    assert parsed["user_count"] == 1
    assert parsed["users"][0]["sec_user_id"] == "MS4wLjABAAAAxTestSecUid"
    assert parsed["users"][0]["nickname"] == "测试博主"


def test_subclass_shares_signing_stack():
    assert issubclass(DouyinUserLookup, DouyinBusinessLookup)
    a = DouyinUserLookup(sleeper=lambda s: None)
    assert a.data_boundary == "fully_public"
    assert a.source_type == "social_user_douyin"
    assert a.min_request_interval == 3.0
