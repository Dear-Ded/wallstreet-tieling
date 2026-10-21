"""hibp_breach_catalog _extract 分支 + 引擎接线（fixture 离线）。"""
from core.entity_association import (
    EntityAssociationEngine,
    create_engine_with_all_adapters,
    _SEED_FANOUT,
)


def _fake_result():
    return {
        "fields": {
            "query_name": "adobe",
            "match_count": 1,
            "catalog_size": 1047,
            "breaches": [
                {
                    "id": "Adobe",
                    "title": "Adobe",
                    "pwn_count": 152445165,
                    "pwn_count_display": "152.4M",
                    "added_date": "4 Dec 2013",
                    "breach_date": "Oct 2013",
                    "breach_url": "https://haveibeenpwned.com/Breach/Adobe",
                }
            ],
        }
    }


def test_hibp_extract_breach_signal():
    e = EntityAssociationEngine(hibp_breach_catalog=None)
    ents = e._extract("hibp_breach_catalog", _fake_result())
    assert len(ents) == 1
    ent = ents[0]
    assert ent["type"] == "breach_signal"
    assert ent["value"] == "Adobe"
    assert ent["sources"] == ["hibp_breach_catalog"]
    assert ent["context"]["pwn_count"] == 152445165
    assert ent["context"]["breach_url"] == "https://haveibeenpwned.com/Breach/Adobe"
    assert "lead" in ent["context"]["note"]


def test_hibp_extract_no_matches():
    e = EntityAssociationEngine(hibp_breach_catalog=None)
    assert e._extract("hibp_breach_catalog", {"fields": {"breaches": []}}) == []
    assert e._extract("hibp_breach_catalog", {"fields": {}}) == []


def test_hibp_wired_in_fanout_and_factory():
    assert "hibp_breach_catalog" in _SEED_FANOUT["business_name"]
    eng = create_engine_with_all_adapters()
    assert eng.hibp_breach_catalog is not None
    assert type(eng.hibp_breach_catalog).__name__ == "HIBPBreachCatalog"
