"""telegram_channel _extract 分支 + 引擎接线（fixture 离线）。"""
from core.entity_association import (
    EntityAssociationEngine,
    create_engine_with_all_adapters,
    _SEED_FANOUT,
)


def _fake_result():
    return {
        "fields": {
            "channel_found": True,
            "preview_url": "https://t.me/s/durov",
            "channel": {
                "title": "Pavel Durov",
                "description": "Contact: test@example.com",
                "subscribers": "10.3M",
            },
            "posts": [
                {"text": "Hello world", "post_id": "1"},
                {"text": "My QQ is 12345678", "post_id": "2"},
            ],
            "post_count": 2,
        }
    }


def test_telegram_channel_extract_person():
    e = EntityAssociationEngine(telegram_channel=None)
    ents = e._extract("telegram_channel", _fake_result())
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "person"
    assert "telegram_channel" in ent["sources"]
    assert ent["context"]["url"] == "https://t.me/s/durov"
    # description/about 进 context，供联系方式管道挖掘
    assert "description" in ent["context"]
    assert "12345678" in ent["context"]["about"]


def test_telegram_channel_not_found():
    e = EntityAssociationEngine(telegram_channel=None)
    assert e._extract("telegram_channel", {"fields": {"channel_found": False}}) == []
    assert e._extract("telegram_channel", {"fields": {}}) == []


def _fake_result_with_tgstat():
    r = _fake_result()
    r["fields"]["tgstat"] = {
        "source": "tgstat.com",
        "handle": "durov",
        "description": "Founder of Telegram.",
        "subscribers_exact": 10303163,
        "related_handles": ["feed", "lean", "durov"],  # own handle must be skipped
        "channel_url": "https://tgstat.com/channel/@durov",
    }
    return r


def test_telegram_channel_extract_related_handles():
    e = EntityAssociationEngine(telegram_channel=None)
    ents = e._extract("telegram_channel", _fake_result_with_tgstat())
    profiles = [x for x in ents if x["type"] == "username_profile"]
    handles = {x["value"] for x in profiles}
    assert handles == {"feed", "lean"}, f"own handle not skipped: {handles}"
    for p in profiles:
        assert p["display"] == f"@{p['value']}"
        assert p["context"]["from"] == "tgstat_related_handle"
        assert p["context"]["owner_handle"] == "durov"
        assert p["context"]["subscribers_exact"] == 10303163
        assert "telegram_channel" in p["sources"]
    # person 实体仍在
    assert any(x["type"] == "person" for x in ents)


def test_telegram_channel_extract_no_tgstat_no_profiles():
    e = EntityAssociationEngine(telegram_channel=None)
    ents = e._extract("telegram_channel", _fake_result())
    assert not [x for x in ents if x["type"] == "username_profile"]


def test_telegram_channel_wired_in_fanout_and_factory():
    assert "telegram_channel" in _SEED_FANOUT["person_name"]
    eng = create_engine_with_all_adapters()
    assert eng.telegram_channel is not None
    assert type(eng.telegram_channel).__name__ == "TelegramChannelLookup"
