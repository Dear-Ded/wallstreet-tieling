"""Tests for core.entity_association (Entity Association Engine)."""

from core.entity_association import (
    EntityAssociationEngine,
    normalize_phone,
    split_phones,
    normalize_address,
    normalize_name,
    extract_phones_from_text,
    extract_emails_from_text,
    entity_id,
)


def test_normalize_phone_mobile_variants():
    assert normalize_phone("13800138000") == "13800138000"
    assert normalize_phone("138-0013-8000") == "13800138000"
    assert normalize_phone("138 0013 8000") == "13800138000"
    assert normalize_phone("+86 13800138000") == "13800138000"
    assert normalize_phone("+8613800138000") == "13800138000"
    assert normalize_phone("8613800138000") == "13800138000"
    assert normalize_phone("008613800138000") == "13800138000"
    assert normalize_phone("(138)00138000") == "13800138000"


def test_normalize_phone_landline():
    assert normalize_phone("010-12345678") == "01012345678"
    assert normalize_phone("02012345678") == "02012345678"
    assert normalize_phone("0755-1234567") == "07551234567"
    assert normalize_phone("010-12345678转801") == "01012345678"


def test_normalize_phone_invalid():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
    assert normalize_phone("12345") == ""
    assert normalize_phone("not-a-phone") == ""
    assert normalize_phone("1380013800") == ""


def test_split_phones_multi():
    assert split_phones("13800138000;13900139000") == ["13800138000", "13900139000"]
    assert split_phones("13800138000、13900139000") == ["13800138000", "13900139000"]
    assert split_phones("13800138000 / 13900139000") == ["13800138000", "13900139000"]
    assert split_phones("13800138000，13800138000") == ["13800138000"]
    assert split_phones("") == []
    assert split_phones(None) == []


def test_normalize_address_strips_floor_room():
    key, display = normalize_address("广州市天河区中山大道123号101室")
    assert key == "广州市天河区中山大道123号"
    assert display == "广州市天河区中山大道123号101室"
    key2, _ = normalize_address("广州市天河区中山大道123号")
    assert key == key2
    key3, _ = normalize_address("北京市朝阳区建国路88号3层")
    assert "建国路88号" in key3


def test_normalize_address_masked_not_matchable():
    key, display = normalize_address("广州大道北******")
    assert key == ""
    assert display == "广州大道北******"


def test_normalize_address_too_short():
    key, _ = normalize_address("北京")
    assert key == ""


def test_normalize_name():
    assert normalize_name("  张三  ") == "张三"
    assert normalize_name("海底捞火锅店") == "海底捞火锅店"
    assert normalize_name("") == ""
    assert normalize_name(None) == ""


def test_extract_phones_from_text():
    text = "本店电话13800138000，座机010-12345678，欢迎光临"
    phones = extract_phones_from_text(text)
    assert "13800138000" in phones
    assert "01012345678" in phones


def test_extract_phones_from_text_no_phones():
    assert extract_phones_from_text("欢迎光临本店") == []
    assert extract_phones_from_text("") == []
    assert extract_phones_from_text(None) == []


def test_extract_emails_from_text():
    text = "联系邮箱 contact@example.com 或 info@test.org"
    emails = extract_emails_from_text(text)
    assert "contact@example.com" in emails
    assert "info@test.org" in emails


def test_entity_id_deterministic():
    assert entity_id("phone", "13800138000") == entity_id("phone", "13800138000")
    assert entity_id("phone", "13800138000") != entity_id("address", "13800138000")
    assert len(entity_id("phone", "13800138000")) == 16


class _StubAmap:
    def __init__(self, pois):
        self._pois = pois

    def query(self, keyword, **kwargs):
        return {
            "source_domain": "restapi.amap.com",
            "fields": {"poi_count": len(self._pois), "pois": self._pois},
            "error": "",
        }


class _StubSogou:
    def __init__(self, articles):
        self._articles = articles

    def query(self, keyword, **kwargs):
        return {
            "source_domain": "weixin.sogou.com",
            "fields": {"article_count": len(self._articles),
                       "articles": self._articles},
            "error": "",
        }


class _StubFailing:
    def query(self, keyword, **kwargs):
        raise RuntimeError("network down")


class _StubInteraction:
    def query(self, keyword, **kwargs):
        return {"interaction_required": True,
                "interaction_guide": ["do it manually"]}


AMAP_POIS = [
    {
        "name": "沙县小吃（中山路店）",
        "tel": "13800138000",
        "address": "郑州市金水区中山路88号101室",
        "province": "河南省", "city": "郑州市", "district": "金水区",
    },
    {
        "name": "沙县小吃（文化路店）",
        "tel": "13800138000",
        "address": "郑州市金水区文化路66号",
        "province": "河南省", "city": "郑州市", "district": "金水区",
    },
    {
        "name": "兰州拉面",
        "tel": "13900139000",
        "address": "郑州市金水区文化路66号203室",
        "province": "河南省", "city": "郑州市", "district": "金水区",
    },
]


def test_associate_business_name_fanout():
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    assert out["seed"] == {"type": "business_name", "value": "沙县小吃"}
    types = {e["type"] for e in out["entities"]}
    assert "business" in types
    assert "phone" in types
    assert "address" in types
    phones = [e["value"] for e in out["entities"] if e["type"] == "phone"]
    assert "13800138000" in phones


def test_shared_phone_pattern_detected():
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "shared_phone_across_businesses" in pats
    pat = next(p for p in out["interesting_patterns"]
               if p["pattern"] == "shared_phone_across_businesses")
    assert "2" in pat["description"]


def test_shared_address_pattern_detected():
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "shared_address_across_businesses" in pats


def test_same_phone_association_strength():
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    rels = {(a["relation"], a["strength"]) for a in out["associations"]}
    assert ("same_phone", "strong") in rels
    assert ("same_address", "strong") in rels
    assert ("located_at", "exact") in rels
    assert ("contact_of", "strong") in rels


def test_failing_adapter_does_not_break_run():
    eng = EntityAssociationEngine(amap=_StubFailing(), sogou_wx=_StubSogou([]))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    assert out["source_results"]["amap"]["status"] == "error"
    assert out["source_results"]["sogou_wx"]["status"] == "ok"


def test_interaction_required_adapter_skipped():
    eng = EntityAssociationEngine(douyin=_StubInteraction())
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    assert out["source_results"]["douyin"]["status"] == "interaction_required"
    assert out["entities"] == []


def test_no_adapters_enabled():
    eng = EntityAssociationEngine()
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    assert out["entities"] == []
    assert out["associations"] == []


def test_unsupported_seed_type():
    eng = EntityAssociationEngine()
    out = eng.associate({"type": "wechat_id", "value": "xxx"})
    assert "error" in out
    assert "unsupported seed type" in out["error"]


def test_phone_seed_fanout_to_sogou():
    arts = [{"title": "本店开业", "summary": "电话 13800138000",
             "account": "小店君", "published_date": "2024-01-01",
             "sogou_link": "/link?url=x"}]
    eng = EntityAssociationEngine(sogou_wx=_StubSogou(arts))
    out = eng.associate({"type": "phone", "value": "138-0013-8000"})
    phones = [e["value"] for e in out["entities"] if e["type"] == "phone"]
    assert "13800138000" in phones


def test_shell_signal_pattern():
    pois = [
        {"name": "有电话的店", "tel": "13800138000",
         "address": "郑州市金水区中山路1号"},
        {"name": "神秘店铺", "tel": "", "address": ""},
    ]
    eng = EntityAssociationEngine(amap=_StubAmap(pois))
    out = eng.associate({"type": "business_name", "value": "店"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "business_no_contact_footprint" in pats


def test_dedupe_associations():
    eng = EntityAssociationEngine()
    assocs = [
        {"from": "a", "to": "b", "relation": "same_phone",
         "strength": "strong", "sources": ["amap"], "note": ""},
        {"from": "b", "to": "a", "relation": "same_phone",
         "strength": "strong", "sources": ["amap"], "note": ""},
        {"from": "a", "to": "b", "relation": "same_address",
         "strength": "strong", "sources": ["amap"], "note": ""},
    ]
    out = eng._dedupe_associations(assocs)
    assert len(out) == 2


def test_disclaimer_present():
    eng = EntityAssociationEngine()
    out = eng.associate({"type": "business_name", "value": "x"})
    assert "leads, not identity assertions" in out["disclaimer"]
    assert out["data_boundary"] == "fully_public"


def test_source_results_no_raw_pii():
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"})
    blob = str(out["source_results"])
    assert "13800138000" not in blob
    assert "中山路88号" not in blob


def test_depth2_followup_bounded():
    # sogou_wx enabled -> depth2 fires phone follow-ups, bounded at 6
    arts = [{"title": "t", "summary": "电话 13800138000",
             "account": "a", "published_date": "2024-01-01",
             "sogou_link": "/link?url=x"}]
    eng = EntityAssociationEngine(amap=_StubAmap(AMAP_POIS),
                                  sogou_wx=_StubSogou(arts))
    out = eng.associate({"type": "business_name", "value": "沙县小吃"},
                        max_depth=2)
    depth2_keys = [k for k in out["source_results"] if "depth2" in k]
    assert len(depth2_keys) <= 6
    assert len(depth2_keys) >= 1


# ---------------------------------------------------------------------------
# family / beneficial-owner inference
# ---------------------------------------------------------------------------

from core.entity_association import extract_surname  # noqa: E402


def test_extract_surname_simple():
    assert extract_surname("张伟") == "张"
    assert extract_surname("李娜") == "李"


def test_extract_surname_compound():
    assert extract_surname("欧阳锋") == "欧阳"
    assert extract_surname("诸葛亮") == "诸葛"


def test_extract_surname_empty():
    assert extract_surname("") == ""
    assert extract_surname(None) == ""


class _StubCorporate:
    """Mimics a corporate role adapter."""
    def __init__(self, records):
        self._records = records

    def query(self, keyword, **kwargs):
        recs = self._records
        if isinstance(recs, dict):
            recs = [recs]
        return {
            "source_domain": "corporate.example",
            "fields": {"corporate_records": recs},
            "error": "",
        }


FAMILY_CO = {
    "company_name": "杭州云栖科技有限公司",
    "legal_rep": {"name": "张伟", "age_hint": "young"},
    "shareholders": [
        {"name": "张伟", "kind": "person", "share_pct": 20, "age_hint": "young"},
        {"name": "张建国", "kind": "person", "share_pct": 70, "age_hint": "old"},
        {"name": "李娜", "kind": "person", "share_pct": 10, "age_hint": "middle"},
    ],
    "personnel": [
        {"name": "张建国", "role": "监事"},
        {"name": "李娜", "role": "董事"},
    ],
}


def test_family_business_signal():
    eng = EntityAssociationEngine(corporate=_StubCorporate(FAMILY_CO))
    out = eng.associate({"type": "business_name", "value": "杭州云栖科技有限公司"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "family_business_signal" in pats
    pat = next(p for p in out["interesting_patterns"]
               if p["pattern"] == "family_business_signal")
    # lead language, not assertion
    assert "疑似" in pat["description"]


def test_figurehead_risk_young_rep_old_shareholder():
    eng = EntityAssociationEngine(corporate=_StubCorporate(FAMILY_CO))
    out = eng.associate({"type": "business_name", "value": "杭州云栖科技有限公司"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "figurehead_risk" in pats
    assert "possible_beneficial_owner" in pats
    # the suspected controller is NOT the legal rep
    bop = next(p for p in out["interesting_patterns"]
               if p["pattern"] == "possible_beneficial_owner")
    assert "张建国" in bop["description"]


def test_possible_family_with_association():
    eng = EntityAssociationEngine(corporate=_StubCorporate(FAMILY_CO))
    out = eng.associate({"type": "business_name", "value": "杭州云栖科技有限公司"})
    rels = {a["relation"] for a in out["associations"]}
    assert "possible_family_with" in rels
    assert "legal_rep_of" in rels
    assert "shareholder_of" in rels
    assert "supervisor_of" in rels
    # confidence levels present
    strengths = {a["strength"] for a in out["associations"]
                 if a["relation"] == "possible_family_with"}
    assert strengths == {"weak"}


def test_couple_business_pattern():
    co = {
        "company_name": "夫妻小吃店",
        "legal_rep": {"name": "王强", "age_hint": "middle"},
        "shareholders": [
            {"name": "王强", "kind": "person", "share_pct": 50},
            {"name": "刘芳", "kind": "person", "share_pct": 50},
        ],
        "personnel": [],
    }
    eng = EntityAssociationEngine(corporate=_StubCorporate(co))
    out = eng.associate({"type": "business_name", "value": "夫妻小吃店"})
    rels = {a["relation"] for a in out["associations"]}
    assert "possible_couple_business" in rels
    cpl = next(a for a in out["associations"]
               if a["relation"] == "possible_couple_business")
    assert cpl["strength"] == "weak"
    assert "疑似" in cpl["note"]


def test_through_shareholding_beneficial_owner():
    recs = [
        {
            "company_name": "目标公司",
            "legal_rep": {"name": "赵六", "age_hint": "middle"},
            "shareholders": [
                {"name": "控股集团有限公司", "kind": "company", "share_pct": 100},
            ],
            "personnel": [],
        },
        {
            "company_name": "控股集团有限公司",
            "legal_rep": {"name": "钱大", "age_hint": "old"},
            "shareholders": [
                {"name": "钱大", "kind": "person", "share_pct": 100},
            ],
            "personnel": [],
        },
    ]
    eng = EntityAssociationEngine(corporate=_StubCorporate(recs))
    out = eng.associate({"type": "business_name", "value": "目标公司"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "possible_beneficial_owner" in pats
    bop = next(p for p in out["interesting_patterns"]
               if p["pattern"] == "possible_beneficial_owner")
    assert "钱大" in bop["description"]
    assert "穿透" in bop["description"]


def test_one_person_multiple_companies():
    recs = [
        {
            "company_name": "甲公司",
            "legal_rep": {"name": "孙七", "age_hint": "middle"},
            "shareholders": [{"name": "孙七", "kind": "person", "share_pct": 100}],
            "personnel": [],
        },
        {
            "company_name": "乙公司",
            "legal_rep": {"name": "孙七", "age_hint": "middle"},
            "shareholders": [{"name": "孙七", "kind": "person", "share_pct": 80}],
            "personnel": [],
        },
    ]
    eng = EntityAssociationEngine(corporate=_StubCorporate(recs))
    out = eng.associate({"type": "business_name", "value": "甲公司"})
    rels = [a for a in out["associations"]
            if a["relation"] == "multi_company_role"]
    assert len(rels) >= 2
    assert all(a["strength"] == "weak" for a in rels)


def test_no_family_signal_single_person():
    co = {
        "company_name": "一人公司",
        "legal_rep": {"name": "周八", "age_hint": "middle"},
        "shareholders": [{"name": "周八", "kind": "person", "share_pct": 100}],
        "personnel": [],
    }
    eng = EntityAssociationEngine(corporate=_StubCorporate(co))
    out = eng.associate({"type": "business_name", "value": "一人公司"})
    pats = [p["pattern"] for p in out["interesting_patterns"]]
    assert "family_business_signal" not in pats
    assert "figurehead_risk" not in pats
