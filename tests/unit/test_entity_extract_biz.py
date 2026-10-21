"""Entity extraction handlers for business/person-line adapters (no network).

Covers _extract branches: patent, toutiao, gd_credit, gleif, customs,
software_copyright, juhe_copyright, weibo_relation.
"""

from core.entity_association import EntityAssociationEngine, _SEED_FANOUT

ALLOWED_TYPES = {
    "person", "business", "phone", "address", "email", "domain",
    "username_profile", "ip", "icp_license", "hiring_signal",
}


def _eng():
    return EntityAssociationEngine()


def test_patent_extracts_assignee_and_inventors():
    eng = _eng()
    result = {"fields": {"patents": [
        {"publication_number": "CN110086609B",
         "title": "数据备份方法",
         "inventor": "姚辉、张伟",
         "assignee": "华为技术有限公司",
         "filing_date": "2019-03-27"},
    ], "patent_count": 1}}
    ents = eng._extract("patent", result)
    biz = [e for e in ents if e["type"] == "business"]
    persons = [e for e in ents if e["type"] == "person"]
    assert len(biz) == 1 and biz[0]["value"] == "华为技术有限公司"
    assert biz[0]["sources"] == ["patent"]
    assert {e["value"] for e in persons} == {"姚辉", "张伟"}
    assert all(e["context"]["from"] == "patent_inventor" for e in persons)
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_patent_missing_inventor_still_emits_business():
    eng = _eng()
    result = {"fields": {"patents": [
        {"publication_number": "CN112180955B", "title": "电力设备",
         "inventor": "", "assignee": "国网安徽省电力有限公司"},
    ]}}
    ents = eng._extract("patent", result)
    assert [e["type"] for e in ents] == ["business"]


def test_patent_empty_and_error_shapes():
    eng = _eng()
    assert eng._extract("patent", {"fields": {}}) == []
    assert eng._extract("patent", {"error": "boom"}) == []
    assert eng._extract("patent", {}) == []


def test_toutiao_extracts_author():
    eng = _eng()
    result = {"fields": {"articles": [
        {"title": "张三的创业故事", "url": "https://www.toutiao.com/a123",
         "author": "科技观察员", "publish_time": "2026-10-20"},
    ]}}
    ents = eng._extract("toutiao", result)
    assert len(ents) == 1
    assert ents[0]["type"] == "person"
    assert ents[0]["value"] == "科技观察员"
    assert ents[0]["sources"] == ["toutiao"]
    assert ents[0]["context"]["from"] == "toutiao_author"


def test_toutiao_missing_author():
    eng = _eng()
    result = {"fields": {"articles": [
        {"title": "无名文章", "url": "https://www.toutiao.com/a124", "author": ""},
    ]}}
    assert eng._extract("toutiao", result) == []
    assert eng._extract("toutiao", {"fields": {}}) == []


def test_gd_credit_search_shape():
    eng = _eng()
    result = {"fields": {"companies": [
        {"company_name": "开平市枫源纸品有限公司",
         "credit_code": "91440783MA520W5H6C",
         "legal_rep": "谭振尧",
         "address": "开平市水口镇新风开发区红新路1号-6",
         "status": "存续（在营、开业、在册）",
         "masterdataid": "GDS_e0d4df08"},
    ], "total_count": 1}}
    ents = eng._extract("gd_credit", result)
    by_type = {}
    for e in ents:
        by_type.setdefault(e["type"], []).append(e)
    assert by_type["business"][0]["value"] == "开平市枫源纸品有限公司"
    assert by_type["business"][0]["context"]["credit_code"] == "91440783MA520W5H6C"
    rep = by_type["person"][0]
    assert rep["value"] == "谭振尧"
    assert rep["context"]["role"] == "法定代表人"
    assert rep["context"]["company"] == "开平市枫源纸品有限公司"
    addr = by_type["address"][0]
    assert addr["matchable"] is True
    assert addr["context"]["of_business"] == "开平市枫源纸品有限公司"
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_gd_credit_detail_shape():
    eng = _eng()
    result = {"fields": {"found": True,
                         "company_name": "广州示例科技有限公司",
                         "credit_code": "91440101MA0000001X",
                         "legal_rep": "李四",
                         "address": "广州市天河区珠江新城花城大道1号",
                         "status": "存续",
                         "registered_capital": "100.0",
                         "industry": "软件和信息技术服务业"}}
    ents = eng._extract("gd_credit", result)
    types = [e["type"] for e in ents]
    assert types == ["business", "person", "address"]


def test_gd_credit_missing_fields():
    eng = _eng()
    assert eng._extract("gd_credit", {"fields": {}}) == []
    assert eng._extract("gd_credit", {"fields": {"found": False}}) == []
    # company without legal_rep / address -> business only
    ents = eng._extract("gd_credit",
                        {"fields": {"companies": [{"company_name": "无地址公司",
                                                  "credit_code": "", "legal_rep": "",
                                                  "address": "", "status": ""}]}})
    assert [e["type"] for e in ents] == ["business"]


def test_gleif_extracts_lei_entities_and_parent():
    eng = _eng()
    result = {"fields": {
        "entities": [
            {"lei": "98450063D0A707C12A83",
             "legal_name": "Alibaba (Netherlands) B.V.",
             "other_names": ["Alibaba NL"],
             "jurisdiction": "NL", "legal_form": "BV",
             "status": "ACTIVE", "registration_status": "ISSUED",
             "hq_address": "Amsterdam, NL"},
        ],
        "direct_parent_lei": "9845000HQRN8J4E7D75",
        "direct_parent_name": "Alibaba Group Holding Limited",
        "child_leis": ["894500LTKN6QXS10UI15"],
    }}
    ents = eng._extract("gleif", result)
    by_value = {e["value"]: e for e in ents}
    main = by_value["Alibaba(Netherlands)B.V."]
    assert main["type"] == "business"
    assert main["context"]["lei"] == "98450063D0A707C12A83"
    assert main["context"]["jurisdiction"] == "NL"
    assert main["context"]["child_leis"] == ["894500LTKN6QXS10UI15"]
    assert by_value["AlibabaNL"]["context"]["from"] == "gleif_other_name"
    parent = by_value["AlibabaGroupHoldingLimited"]
    assert parent["context"]["from"] == "gleif_parent"
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_gleif_missing_shapes():
    eng = _eng()
    assert eng._extract("gleif", {"fields": {}}) == []
    # record without legal_name is skipped
    ents = eng._extract("gleif", {"fields": {"entities": [{"lei": "X"}]}})
    assert ents == []


def test_customs_extracts_parties_and_counterparties():
    eng = _eng()
    result = {"fields": {
        "parties": [
            {"name": "Huawei Technologies Co Ltd",
             "report_url": "https://www.zauba.com/huawei-report-1",
             "shipment_count": 121,
             "total_weight": "50,000 KG",
             "latest_shipment": "2026-10-01",
             "category": "importers"},
        ],
        "counterparties": ["Shenzhen Component Ltd"],
        "address": "Shenzhen, Guangdong, China",
    }}
    ents = eng._extract("customs", result)
    by_value = {e["value"]: e for e in ents}
    party = by_value["HuaweiTechnologiesCoLtd"]
    assert party["type"] == "business"
    assert party["context"]["shipment_count"] == 121
    assert party["context"]["from"] == "customs_party"
    cp = by_value["ShenzhenComponentLtd"]
    assert cp["context"]["from"] == "customs_counterparty"
    addr = by_value["Shenzhen,Guangdong,China"]
    assert addr["type"] == "address"
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_customs_missing_shapes():
    eng = _eng()
    assert eng._extract("customs", {"fields": {}}) == []
    ents = eng._extract("customs", {"fields": {"parties": [{"name": ""}]}})
    assert ents == []


def test_software_copyright_zhifufu_shape():
    eng = _eng()
    result = {"status": "ok", "source": "www.zhifufu.com",
              "records": [
                  {"soft_name": "企业OA系统", "reg_no": "2021SR000001",
                   "owner": "杭州某某科技有限公司",
                   "reg_date": "2021-01-01", "version": "V1.0"},
              ]}
    ents = eng._extract("software_copyright", result)
    assert len(ents) == 1
    assert ents[0]["type"] == "business"
    assert ents[0]["value"] == "杭州某某科技有限公司"
    assert ents[0]["sources"] == ["software_copyright"]
    assert ents[0]["context"]["reg_no"] == "2021SR000001"


def test_juhe_copyright_shape():
    eng = _eng()
    result = {"status": "ok", "source": "v.juhe.cn",
              "records": [
                  {"soft_name": "进销存系统", "reg_no": "2022SR000002",
                   "owner": "上海示例软件有限公司",
                   "reg_date": "2022-05-06"},
              ]}
    ents = eng._extract("juhe_copyright", result)
    assert len(ents) == 1
    assert ents[0]["type"] == "business"
    assert ents[0]["value"] == "上海示例软件有限公司"
    assert ents[0]["sources"] == ["juhe_copyright"]


def test_copyright_missing_owner_and_empty():
    eng = _eng()
    assert eng._extract("software_copyright", {"records": [{"soft_name": "X"}]}) == []
    assert eng._extract("juhe_copyright", {"fields": {}}) == []
    assert eng._extract("software_copyright", {}) == []


def test_weibo_relation_extracts_users():
    eng = _eng()
    result = {"status": "ok", "source": "m.weibo.cn",
              "relation": "followers", "relation_cn": "关注",
              "users": [
                  {"id": "123456", "screen_name": "张大千",
                   "description": "科技创业者",
                   "profile_url": "https://m.weibo.cn/u/123456",
                   "verified": True, "verified_reason": "科技公司CEO",
                   "follow_me": True, "following": True},
              ]}
    ents = eng._extract("weibo_relation", result)
    types = sorted(e["type"] for e in ents)
    assert types == ["person", "username_profile"]
    up = next(e for e in ents if e["type"] == "username_profile")
    assert up["value"] == "张大千"
    assert up["sources"] == ["weibo_relation"]
    assert up["context"]["verified_reason"] == "科技公司CEO"
    assert up["context"]["relation"] == "followers"
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_weibo_relation_fields_wrapped_shape():
    eng = _eng()
    result = {"fields": {"users": [
        {"id": "789", "screen_name": "李小明", "verified": False},
    ], "relation": "fans"}}
    ents = eng._extract("weibo_relation", result)
    assert len(ents) == 2
    assert ents[0]["context"]["relation"] == "fans"


def test_weibo_relation_missing_screen_name():
    eng = _eng()
    result = {"users": [{"id": "999", "screen_name": ""}]}
    assert eng._extract("weibo_relation", result) == []
    assert eng._extract("weibo_relation", {"users": []}) == []


def test_fanout_covers_new_adapters():
    assert "gleif" in _SEED_FANOUT["business_name"]
    assert "customs" in _SEED_FANOUT["business_name"]
    assert "software_copyright" in _SEED_FANOUT["business_name"]
    assert "weibo_relation" in _SEED_FANOUT["person_name"]
    assert "juhe_copyright" not in _SEED_FANOUT["business_name"]


class _StubPatent:
    def query(self, keyword, **kwargs):
        return {"fields": {"patents": [
            {"publication_number": "CN110086609B", "title": "数据备份方法",
             "inventor": "姚辉", "assignee": "华为技术有限公司",
             "filing_date": "2019-03-27"},
        ], "patent_count": 1}}


class _StubWeiboRelation:
    def query(self, keyword, **kwargs):
        return {"fields": {"users": [
            {"id": "123456", "screen_name": "张大千", "verified": True},
        ], "relation": "followers"}}


def test_associate_business_name_with_patent_stub():
    eng = EntityAssociationEngine(patent=_StubPatent())
    out = eng.associate({"type": "business_name", "value": "华为技术有限公司"})
    types = {e["type"] for e in out["entities"]}
    assert "business" in types and "person" in types
    assert "patent" in out["source_results"]


def test_associate_person_name_with_weibo_relation_stub():
    eng = EntityAssociationEngine(weibo_relation=_StubWeiboRelation())
    out = eng.associate({"type": "person_name", "value": "张大千"})
    types = {e["type"] for e in out["entities"]}
    assert "username_profile" in types
    assert "weibo_relation" in out["source_results"]
