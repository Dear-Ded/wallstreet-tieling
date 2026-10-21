"""DouyinBusinessLookup adapter tests (stubbed, no network)."""
import json

from adapters.douyin_adapter import (
    DouyinBusinessLookup,
    _gen_ms_token,
)


def _profile_fixture():
    return {
        "user": {
            "sec_uid": "MS4wLjABAAAA" + "x" * 40,
            "unique_id": "shaxianxiaochi001",
            "nickname": "沙县小吃总店",
            "signature": "郑州市金水区花园路123号 电话13800138000",
            "follower_count": 12500,
            "following_count": 32,
            "aweme_count": 156,
            "total_favorited": 89000,
            "enterprise_verify_reason": "沙县小吃（郑州）餐饮有限公司",
            "ip_location": "河南",
        }
    }


def _posts_fixture():
    return {
        "aweme_list": [
            {
                "aweme_id": "7481234567890123456",
                "desc": "今日特价拌面",
                "create_time": 1729000000,
                "statistics": {"digg_count": 120, "comment_count": 15,
                               "share_count": 8},
                "poi_info": {
                    "poi_name": "沙县小吃（花园路店）",
                    "address": "郑州市金水区花园路123号",
                    "latitude": 34.78,
                    "longitude": 113.65,
                },
            },
            {
                "aweme_id": "7481234567890123457",
                "desc": "后厨日常",
                "create_time": 1728900000,
                "statistics": {"digg_count": 45, "comment_count": 3,
                               "share_count": 1},
            },
        ]
    }


def test_profile_parsing():
    a = DouyinBusinessLookup()
    p = a._parse_profile(_profile_fixture())
    assert p["nickname"] == "沙县小吃总店"
    assert p["douyin_id"] == "shaxianxiaochi001"
    assert p["follower_count"] == 12500
    assert p["enterprise_verify"] is True
    assert "花园路123号" in p["signature"]


def test_posts_parsing_and_poi_collect():
    a = DouyinBusinessLookup()
    posts = a._parse_posts(_posts_fixture())
    assert len(posts) == 2
    assert posts[0]["poi_name"] == "沙县小吃（花园路店）"
    assert posts[0]["poi_latitude"] == 34.78
    assert posts[1]["poi_name"] == ""
    pois = a._collect_pois(posts)
    assert len(pois) == 1
    assert pois[0]["poi_address"] == "郑州市金水区花园路123号"


def test_parse_browser_search_general_shape():
    a = DouyinBusinessLookup()
    raw = json.dumps({
        "data": [{"user_list": [
            {"user_info": {"sec_uid": "SEC123", "nickname": "测试店",
                           "follower_count": 100}}]}]
    })
    out = a.parse_browser_search(raw)
    assert out["user_count"] == 1
    assert out["users"][0]["nickname"] == "测试店"


def test_parse_browser_search_invalid():
    out = DouyinBusinessLookup.parse_browser_search("not json{{{")
    assert "parse_error" in out
    assert out["users"] == []


def test_query_returns_interaction_required():
    a = DouyinBusinessLookup()
    r = a.query("沙县小吃")
    assert r["interaction_required"] is True
    assert "interaction_guide" in r
    assert r["source_domain"] == "www.douyin.com"


def test_ms_token_shape():
    t = _gen_ms_token()
    assert t.endswith("==")
    assert len(t) == 109


def test_resolve_share_url_garbage():
    assert DouyinBusinessLookup._resolve_share_url(
        "https://example.com/nope") is None
