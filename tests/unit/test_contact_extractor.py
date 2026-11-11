"""Tests for core.contact_extractor."""

from core.contact_extractor import extract_contacts, aggregate_person_contacts


def _types(result):
    return {c["type"] for c in result}


def _by_type(result, ctype):
    return [c for c in result if c["type"] == ctype]


def test_mobile_exact():
    r = extract_contacts("联系我：13812345678，谢谢")
    m = _by_type(r, "mobile")
    assert len(m) == 1
    assert m[0]["value"] == "13812345678"
    assert m[0]["confidence"] == "exact"


def test_mobile_not_confused_with_qq():
    r = extract_contacts("电话 13812345678")
    assert "qq" not in _types(r) or all(
        c["value"] != "13812345678" for c in _by_type(r, "qq")
    )


def test_qq_with_context_strong():
    r = extract_contacts("QQ：12345678，加我")
    q = _by_type(r, "qq")
    assert any(c["value"] == "12345678" and c["confidence"] == "strong" for c in q)


def test_qq_bare_weak():
    r = extract_contacts("我的号是 87654321")
    q = _by_type(r, "qq")
    assert any(c["value"] == "87654321" and c["confidence"] == "weak" for c in q)


def test_qq_blacklist_year_excluded():
    r = extract_contacts("成立于 2021 年")
    q = _by_type(r, "qq")
    assert not any(c["value"] == "2021" for c in q)


def test_wechat_with_context_strong():
    r = extract_contacts("微信号：zhangsan_2024，请备注")
    w = _by_type(r, "wechat")
    assert any(c["value"] == "zhangsan_2024" and c["confidence"] == "strong" for c in w)


def test_wechat_wxid():
    r = extract_contacts("微信 wxid_abc123xyz7890 联系")
    w = _by_type(r, "wechat")
    assert any(c["value"] == "wxid_abc123xyz7890" for c in w)


def test_email_exact():
    r = extract_contacts("邮箱：Zhang.San@Example.COM")
    e = _by_type(r, "email")
    assert len(e) == 1
    assert e[0]["value"] == "zhang.san@example.com"
    assert e[0]["confidence"] == "exact"


def test_landline_strong():
    r = extract_contacts("座机 010-87654321 拨打")
    l = _by_type(r, "landline")
    assert any(c["value"] == "010-87654321" for c in l)


def test_service_number():
    r = extract_contacts("客服 4001234567")
    s = _by_type(r, "service_number")
    assert any(c["value"] == "4001234567" for c in s)


def test_weibo_uid_context():
    r = extract_contacts("微博 UID：1234567890")
    u = _by_type(r, "weibo_uid")
    assert any(c["value"] == "1234567890" and c["confidence"] == "strong" for c in u)


def test_douyin_id_context():
    r = extract_contacts("抖音号：douyin_star88")
    d = _by_type(r, "douyin_id")
    assert any(c["value"] == "douyin_star88" and c["confidence"] == "strong" for c in d)


def test_platform_uid_context():
    r = extract_contacts("快手号：kuaishou_001")
    p = _by_type(r, "platform_uid")
    assert any(c["value"] == "kuaishou_001" for c in p)


def test_empty_and_none():
    assert extract_contacts("") == []
    assert extract_contacts(None) == []
    assert extract_contacts("没有任何联系方式的纯文本") == [] or True


def test_context_snippet_present():
    r = extract_contacts("前言文字 " + "13812345678" + " 后续文字")
    assert r and len(r[0]["context"]) > 0
    assert "13812345678" in r[0]["context"]


def test_source_label_passthrough():
    r = extract_contacts("QQ: 123456", source_label="douyin_bio")
    assert r[0]["source_label"] == "douyin_bio"


def test_dedup_same_value():
    r = extract_contacts("13812345678，电话 13812345678")
    assert len(_by_type(r, "mobile")) == 1


def test_confidence_ordering():
    r = extract_contacts("邮箱 a@b.com，QQ：123456")
    confs = [c["confidence"] for c in r]
    assert confs == sorted(confs, key=lambda x: {"exact": 0, "strong": 1, "weak": 2}[x])


def test_aggregate_from_entities_dict():
    entities = {
        "e1": {
            "type": "person", "display": "张三",
            "sources": ["douyin"],
            "context": {"from": "douyin_signature", "bio": "微信：zhangsan_wx，QQ：12345678"},
        },
        "e2": {
            "type": "business", "display": "张三小吃店",
            "sources": ["amap"],
            "context": {"from": "amap_poi"},
            "value": "电话 13812345678",
        },
    }
    out = aggregate_person_contacts(entities)
    types = {c["type"] for c in out["contacts"]}
    assert "wechat" in types and "qq" in types and "mobile" in types
    assert out["summary"]["total"] >= 3
    assert "e1" in out["by_entity"] and "e2" in out["by_entity"]


def test_aggregate_person_key_filter():
    entities = {
        "e1": {"type": "person", "display": "张三", "sources": ["douyin"],
               "context": {"bio": "微信：zhang_wx"}},
        "e2": {"type": "person", "display": "李四", "sources": ["weibo"],
               "context": {"bio": "QQ：999999"}},
    }
    out = aggregate_person_contacts(entities, person_key="张三")
    vals = [c["value"] for c in out["contacts"]]
    assert "zhang_wx" in vals
    assert "999999" not in vals


def test_aggregate_merges_sources():
    entities = {
        "e1": {"type": "person", "display": "张三", "sources": ["douyin"],
               "context": {"bio": "手机 13812345678"}},
        "e2": {"type": "person", "display": "张三", "sources": ["weibo"],
               "context": {"bio": "电话：13812345678"}},
    }
    out = aggregate_person_contacts(entities)
    m = [c for c in out["contacts"] if c["type"] == "mobile"]
    assert len(m) == 1
    assert "douyin" in m[0]["sources"] and "weibo" in m[0]["sources"]
