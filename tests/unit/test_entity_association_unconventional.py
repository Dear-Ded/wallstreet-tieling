"""Tests for the unconventional association lane (2026-10-21): 非常规关联人发现.

Covers new relation kinds in core/entity_association.py:
  co_inventor / co_party_in_case (person-person) / co_author /
  co_mentioned_in / mutual_follow / co_contributor /
  onchain_counterparty / consortium_member_of
plus new extractors, the consortium parser, and seed fanout wiring
for github_contributors / blockscout (EXPERIMENTAL adapters).
All fixtures offline.
"""

from core.entity_association import (
    EntityAssociationEngine,
    _blockscout_entities,
    _consortium_entities,
    _github_contributors_entities,
    _news_cooccurrence_entities,
    parse_consortium_members,
)

NEW_RELATIONS = {
    "co_inventor", "co_author", "co_mentioned_in", "mutual_follow",
    "co_contributor", "onchain_counterparty", "consortium_member_of",
}
# co_party_in_case pre-existed (person->business); extended to person-person.


def _eng(**kw):
    return EntityAssociationEngine(**kw)


def _merged(eng, ents):
    merged: dict = {}
    eng._merge_entities(merged, ents)
    return merged


def _rels(eng, merged):
    return eng._build_associations(merged)


def _by_rel(rels, relation):
    return [a for a in rels if a["relation"] == relation]


# ---------------------------------------------------------------- co_inventor

def test_co_inventor_pairs_share_patent():
    eng = _eng()
    ents = []
    for inv in ("冷烨", "李顼"):
        ents.append({
            "type": "person", "value": inv, "display": inv,
            "sources": ["patent"],
            "context": {"from": "patent_inventor",
                        "publication_number": "CN114697527B",
                        "patent_title": "Shooting method"},
        })
    # 不同专利的发明人不应配对
    ents.append({
        "type": "person", "value": "薛竹飙", "display": "薛竹飙",
        "sources": ["patent"],
        "context": {"from": "patent_inventor",
                    "publication_number": "CN107409091B",
                    "patent_title": "Traffic Engineered"},
    })
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "co_inventor")
    assert len(rels) == 1
    r = rels[0]
    assert r["strength"] == "strong"
    assert "CN114697527B" in r["note"]
    assert "patents.google.com/patent/CN114697527B/en" in r["note"]
    assert r["sources"] == ["patent"]


# ------------------------------------------------- co_party_in_case (person)

def test_co_party_in_case_person_person():
    eng = _eng()
    ents = [{
        "type": "person", "value": nm, "display": nm, "sources": ["wenshu"],
        "context": {"from": "court_case_party", "case_number": "(2024)京01民初1号"},
    } for nm in ("张三", "李四")]
    ents.append({
        "type": "person", "value": "王五", "display": "王五", "sources": ["wenshu"],
        "context": {"from": "court_case_party", "case_number": "(2024)京01民初2号"},
    })
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "co_party_in_case")
    pp = [r for r in rels if r["note"].startswith("same case")]
    assert len(pp) == 1
    assert pp[0]["strength"] == "weak"
    assert "(2024)京01民初1号" in pp[0]["note"]


# ------------------------------------------------------------------ co_author

def test_co_author_links_main_author():
    eng = _eng()
    ents = [{
        "type": "person", "value": "Y Bengio", "display": "Y. Bengio",
        "sources": ["semanticscholar"],
        "context": {"from": "semanticscholar_author"},
    }, {
        "type": "person", "value": "Y LeCun", "display": "Y. LeCun",
        "sources": ["semanticscholar"],
        "context": {"from": "semanticscholar_coauthor",
                    "relation": "co_author",
                    "with_author": "Y. Bengio",
                    "shared_papers": 3,
                    "paper_titles": ["Deep Learning", "Nature 2015"]},
    }]
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "co_author")
    assert len(rels) == 1
    assert rels[0]["strength"] == "strong"
    assert "Deep Learning" in rels[0]["note"]


# ------------------------------------------------------------- co_mentioned_in

def test_co_mentioned_in_needs_shared_url():
    eng = _eng()
    recs = [
        {"title": "2024 创新大会嘉宾名单", "url": "https://example.com/a",
         "persons": ["张三", "李四", "张三"]},
        {"title": "另一篇报道", "url": "https://example.com/b",
         "persons": ["王五"]},
        {"title": "无链接", "url": "", "persons": ["赵六"]},
    ]
    ents = _news_cooccurrence_entities(recs, "news_x")
    assert len(ents) == 3  # 去重张三；无 url 的赵六跳过
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "co_mentioned_in")
    assert len(rels) == 1
    assert rels[0]["strength"] == "review"
    assert "https://example.com/a" in rels[0]["note"]
    assert "2024 创新大会嘉宾名单" in rels[0]["note"]


# --------------------------------------------------------------- mutual_follow

def _weibo_result():
    return {
        "fields": {
            "users": [
                {"id": "111", "screen_name": "互关甲", "follow_me": True,
                 "following": True, "profile_url": "https://m.weibo.cn/u/111"},
                {"id": "222", "screen_name": "单向乙", "follow_me": False,
                 "following": True, "profile_url": "https://m.weibo.cn/u/222"},
            ],
            "relation": "followers",
            "pagination": {"containerid": "231051_-_followers_-_999"},
        }
    }


def test_mutual_follow_only_when_both_flags():
    eng = _eng()
    ents = eng._extract("weibo_relation", _weibo_result())
    # seed 实体被创建
    seeds = [e for e in ents
             if (e.get("context") or {}).get("from") == "weibo_relation_seed"]
    assert len(seeds) == 1 and seeds[0]["context"]["weibo_uid"] == "999"
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "mutual_follow")
    assert len(rels) == 1
    assert rels[0]["strength"] == "review"
    assert "https://m.weibo.cn/u/111" in rels[0]["note"]


def test_mutual_follow_absent_without_containerid():
    eng = _eng()
    ents = eng._extract("weibo_relation", {"fields": {"users": [
        {"id": "111", "screen_name": "互关甲",
         "follow_me": True, "following": True}], "relation": "followers"}})
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "mutual_follow")
    assert rels == []


# -------------------------------------------------------------- co_contributor

def test_co_contributor_same_repo_excludes_bots():
    eng = _eng()
    fields = {
        "repo": "octocat/Hello-World",
        "repo_url": "https://github.com/octocat/Hello-World",
        "contributors": [
            {"login": "alice", "contributions": 10, "type": "User",
             "is_bot": False, "profile_url": "https://github.com/alice"},
            {"login": "bob", "contributions": 5, "type": "User",
             "is_bot": False, "profile_url": "https://github.com/bob"},
            {"login": "dependabot[bot]", "contributions": 99, "type": "Bot",
             "is_bot": True, "profile_url": "https://github.com/apps/dependabot"},
        ],
    }
    ents = _github_contributors_entities(fields)
    assert len(ents) == 3
    assert all(e["type"] == "username_profile" for e in ents)
    assert ents[0]["context"]["repo"] == "octocat/Hello-World"
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "co_contributor")
    assert len(rels) == 1  # 仅 alice<->bob；bot 不参与配对
    assert rels[0]["strength"] == "review"
    assert "octocat/Hello-World" in rels[0]["note"]
    assert "https://github.com/octocat/Hello-World" in rels[0]["note"]


# ---------------------------------------------------------- onchain_counterparty

SEED = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
CP = "0x1111111111111111111111111111111111111111"


def test_onchain_counterparty_weak_with_tx_note():
    eng = _eng()
    fields = {
        "address": SEED,
        "explorer_url": f"https://eth.blockscout.com/address/{SEED}",
        "transactions_scanned": 50,
        "counterparties": [
            {"address": CP, "tx_count": 7, "sent": 5, "received": 2,
             "first_seen": "2026-10-01T00:00:00Z",
             "last_seen": "2026-10-20T00:00:00Z",
             "explorer_url": f"https://eth.blockscout.com/address/{CP}"},
        ],
    }
    ents = _blockscout_entities(fields)
    assert {e["type"] for e in ents} == {"evm_address"}
    assert len(ents) == 2  # seed + 对手方
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "onchain_counterparty")
    assert len(rels) == 1
    assert rels[0]["strength"] == "weak"
    assert "7" in rels[0]["note"] and "弱关联" in rels[0]["note"]


def test_blockscout_entities_empty_without_counterparties():
    assert _blockscout_entities({"counterparties": []}) == []
    assert _blockscout_entities({}) == []


# -------------------------------------------------------- consortium_member_of

def test_parse_consortium_members_leader_format():
    text = ("三、中标（成交）信息：供应商名称：联合体：北京建工集团有限责任公司"
            "（牵头人）、中铁建设集团有限公司，评审报价 1200 万元。")
    members = parse_consortium_members(text)
    assert len(members) == 2
    by_name = {m["name"]: m["role"] for m in members}
    assert by_name["北京建工集团有限责任公司"] == "leader"
    assert by_name["中铁建设集团有限公司"] == "member"


def test_parse_consortium_members_member_keyword():
    text = "本项目采用联合体投标，联合体成员：华为技术有限公司、腾讯科技（深圳）有限公司。"
    members = parse_consortium_members(text)
    assert {m["name"] for m in members} == {"华为技术有限公司", "腾讯科技（深圳）有限公司"}


def test_parse_consortium_members_rejects_noise():
    assert parse_consortium_members("本项目不接受联合体投标。") == []
    assert parse_consortium_members("") == []
    # 只有一家不算联合体
    assert parse_consortium_members("联合体：北京建工集团有限责任公司。") == []


def test_consortium_member_of_relation():
    eng = _eng()
    ann = {
        "members": [{"name": "北京建工集团有限责任公司", "role": "leader"},
                    {"name": "中铁建设集团有限公司", "role": "member"}],
        "url": "https://www.ccgp.gov.cn/detail/xyz",
        "title": "XX 项目中标公告",
    }
    ents = _consortium_entities(ann)
    assert len(ents) == 2
    assert all(e["type"] == "business" for e in ents)
    assert ents[0]["context"]["announcement_url"] == ann["url"]
    rels = _by_rel(_rels(eng, _merged(eng, ents)), "consortium_member_of")
    assert len(rels) == 1
    assert rels[0]["strength"] == "strong"
    assert "XX 项目中标公告" in rels[0]["note"]
    assert "https://www.ccgp.gov.cn/detail/xyz" in rels[0]["note"]


# ------------------------------------------------------------------ fanout

class _StubGithub:
    def query(self, keyword, **kwargs):
        assert keyword == "octocat/Hello-World"
        return {"fields": {
            "repo": "octocat/Hello-World",
            "repo_url": "https://github.com/octocat/Hello-World",
            "contributors": [
                {"login": "alice", "contributions": 3, "type": "User",
                 "is_bot": False},
            ]}}


class _StubBlockscout:
    def query(self, keyword, **kwargs):
        return {"fields": {
            "address": keyword.lower(),
            "explorer_url": "https://eth.blockscout.com/address/" + keyword.lower(),
            "transactions_scanned": 50,
            "counterparties": [
                {"address": CP, "tx_count": 2, "sent": 2, "received": 0,
                 "first_seen": "", "last_seen": ""},
            ]}}


def test_fanout_github_repo_seed():
    eng = _eng(github_contributors=_StubGithub())
    out = eng.associate({"type": "github_repo", "value": "octocat/Hello-World"})
    assert "error" not in out or not out.get("error")
    types = {e["type"] for e in out["entities"]}
    assert "username_profile" in types
    rels = _by_rel(out["associations"], "seed_hit_contributor")
    assert len(rels) == 1


def test_fanout_evm_address_seed():
    eng = _eng(blockscout=_StubBlockscout())
    out = eng.associate({"type": "evm_address", "value": SEED})
    assert "error" not in out or not out.get("error")
    types = {e["type"] for e in out["entities"]}
    assert "evm_address" in types
    rels = _by_rel(out["associations"], "onchain_counterparty")
    assert len(rels) == 1 and rels[0]["strength"] == "weak"


def test_new_relation_names_do_not_collide():
    preexisting = {
        "same_phone", "same_address", "located_at", "contact_of",
        "same_qq", "same_wechat", "co_party_in_case", "seed_hit_phone",
        "seed_hit_address", "seed_hit_business", "seed_hit_person",
        "seed_hit_contributor", "legal_rep_of", "shareholder_of",
        "supervisor_of", "executive_of", "possible_family_with",
        "suspected_controls", "possible_couple_business",
        "multi_company_role",
    }
    assert NEW_RELATIONS.isdisjoint(preexisting)


def test_factory_injects_new_adapters():
    from core.entity_association import create_engine_with_all_adapters
    eng = create_engine_with_all_adapters()
    assert eng.github_contributors is not None
    assert eng.blockscout is not None
    assert type(eng.github_contributors).__name__ == "GithubContributorsLookup"
    assert type(eng.blockscout).__name__ == "BlockscoutAddressLookup"
