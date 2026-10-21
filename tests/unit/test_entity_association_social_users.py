"""Entity extraction for social user lanes (B站/豆瓣/抖音/小红书 -> person)."""

from core.entity_association import EntityAssociationEngine


def _engine():
    return EntityAssociationEngine()


def test_bilibili_user_extract_person():
    e = _engine()
    result = {"fields": {"users": [{
        "mid": 1131457022, "uname": "人民日报", "bio": "参与、沟通、记录时代。",
        "fans": 19082142, "level": 6, "official_desc": "人民日报官方账号",
        "profile_url": "https://space.bilibili.com/1131457022",
    }]}}
    ents = e._extract("bilibili_user", result)  # noqa: SLF001
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "person"
    assert ent["display"] == "人民日报"
    assert ent["sources"] == ["bilibili_user"]
    ctx = ent["context"]
    assert ctx["username"] == "人民日报"
    assert ctx["description"] == "参与、沟通、记录时代。"
    assert ctx["verified"] == "人民日报官方账号"
    assert ctx["fans"] == 19082142


def test_douban_user_extract_person():
    e = _engine()
    result = {"fields": {
        "profile": {
            "user_found": True, "uid": "ahbei", "uid_alias": "ahbei",
            "user_id_number": "1000001", "nickname": "阿北",
            "intro": "Less is more", "location": "北京",
            "registered_at": "2006-01-09",
        },
        "profile_url": "https://www.douban.com/people/ahbei/",
    }}
    ents = e._extract("douban_user", result)  # noqa: SLF001
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "person"
    assert ent["display"] == "阿北"
    ctx = ent["context"]
    assert ctx["username"] == "ahbei"
    assert ctx["location"] == "北京"
    assert ctx["description"] == "Less is more"
    assert ctx["registered_at"] == "2006-01-09"


def test_douban_user_not_found_yields_nothing():
    e = _engine()
    ents = e._extract("douban_user", {"fields": {}})  # noqa: SLF001
    assert ents == []


def test_douyin_user_extract_person():
    e = _engine()
    result = {"fields": {
        "user_found": True,
        "profile": {
            "username": "test.douyin", "nickname": "测试博主",
            "bio": "合作请私信 微信: testwx123",
            "follower_count": 120000, "location": "IP属地：北京",
            "verified": "优质创作者",
        },
        "profile_url": "https://www.douyin.com/user/abc",
    }}
    ents = e._extract("douyin_user", result)  # noqa: SLF001
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "person"
    assert ent["display"] == "测试博主"
    ctx = ent["context"]
    assert ctx["username"] == "test.douyin"
    assert ctx["location"] == "IP属地：北京"
    assert "微信" in ctx["description"]


def test_xiaohongshu_user_extract_person():
    e = _engine()
    result = {"fields": {
        "user_found": True,
        "profile": {
            "user_id": "abc123", "nickname": "测试达人",
            "red_id": "xiaohongshu123", "bio": "美妆分享",
            "location": "上海", "fans_count": 88000,
            "profile_url": "https://www.xiaohongshu.com/user/profile/abc123",
        },
    }}
    ents = e._extract("xiaohongshu_user", result)  # noqa: SLF001
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "person"
    assert ent["display"] == "测试达人"
    ctx = ent["context"]
    assert ctx["username"] == "xiaohongshu123"
    assert ctx["location"] == "上海"
    assert ctx["description"] == "美妆分享"


def test_cross_platform_identity_merge_uses_context_username():
    e = _engine()
    douban_ents = e._extract("douban_user", {"fields": {  # noqa: SLF001
        "profile": {"user_found": True, "uid": "zhangsan",
                    "uid_alias": "zhangsan", "nickname": "张三",
                    "location": "北京", "intro": "hi"},
        "profile_url": "https://www.douban.com/people/zhangsan/",
    }})
    xhs_ents = e._extract("xiaohongshu_user", {"fields": {  # noqa: SLF001
        "user_found": True,
        "profile": {"user_id": "u1", "nickname": "张三在上海",
                    "red_id": "zhangsan", "location": "北京", "bio": "hello"},
    }})
    entities = {}
    for ent in douban_ents + xhs_ents:
        entities[f"{ent['sources'][0]}:{ent['display']}"] = ent
    assocs = e._resolve_person_identity(entities)  # noqa: SLF001
    assert any(a["pattern"] == "cross_platform_identity" and
               a["confidence"] == "exact" for a in assocs), (
        "same username + same location across platforms should merge as exact"
    )


def test_person_name_fanout_includes_new_lanes():
    from core.entity_association import _SEED_FANOUT
    for lane in ("bilibili_user", "douban_user", "douyin_user", "xiaohongshu_user"):
        assert lane in _SEED_FANOUT["person_name"]
