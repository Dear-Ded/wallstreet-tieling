"""Tests for HuggingFace public developer-profile adapter (offline fixtures)."""

import pytest

from adapters.huggingface_adapter import HuggingFaceLookup

OVERVIEW_FIXTURE = {
    "_id": "62f83661fe21cc4875221c0f",
    "avatarUrl": "https://cdn-avatars.huggingface.co/v1/production/uploads/x.jpeg",
    "isPro": True,
    "fullname": "Andrej K",
    "numModels": 7,
    "numDatasets": 6,
    "numSpaces": 0,
    "numFollowers": 2052,
    "numFollowing": 0,
    "numFollowingOrgs": 2,
    "orgs": [
        {"id": "630f7242197cd3f24e7f5cf7", "name": "compvis-community",
         "fullname": "CompVis Community",
         "avatarUrl": "https://cdn-avatars.huggingface.co/v1/production/uploads/y.png"},
        {"id": "66903087c1cdfb01d5fccd72", "name": "llmc", "fullname": "llmc",
         "avatarUrl": "https://cdn-avatars.huggingface.co/v1/production/uploads/z.png"},
    ],
    "user": "karpathy",
    "type": "user",
    "details": "ML researcher. Email me at andrej@example.com",
    "createdAt": "2022-08-13T23:40:17.000Z",
}

MODELS_FIXTURE = [
    {"_id": "68f04b9084d32f71374caa0a", "id": "karpathy/nanochat-d32",
     "likes": 96, "trendingScore": 1, "private": False, "downloads": 5749,
     "tags": ["license:mit", "region:us"], "createdAt": "2025-10-16T01:34:08.000Z",
     "modelId": "karpathy/nanochat-d32"},
    {"_id": "64c19eb0275dc8cd7f170b8f", "id": "karpathy/tinyllamas",
     "likes": 208, "private": False, "downloads": 0,
     "tags": ["license:mit"], "pipeline_tag": "text-generation",
     "library_name": "transformers",
     "createdAt": "2023-07-26T22:31:12.000Z", "modelId": "karpathy/tinyllamas"},
]


def _adapter(overview=OVERVIEW_FIXTURE, models=MODELS_FIXTURE):
    def fake_execute(url, headers):
        if "/models?" in url:
            return (200, models, "")
        return (200, overview, "")
    return HuggingFaceLookup(
        execute_query=fake_execute,
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_data_boundary_and_limits():
    a = _adapter()
    assert a.data_boundary == "fully_public"
    assert a.requires_credentials is False
    assert a.source_domain == "huggingface.co"
    assert a.min_request_interval >= 2.0


def test_normalize_username():
    n = HuggingFaceLookup.normalize_username
    assert n("@Karpathy") == "karpathy"
    assert n("  some-org ") == "some-org"
    assert n("a") == "a"
    assert n("has space") is None
    assert n("bad!chars") is None
    assert n("") is None
    assert n("x" * 40) is None  # too long


def test_build_url_is_overview_endpoint():
    a = _adapter()
    assert a._build_url("karpathy", username="karpathy") == \
        "https://huggingface.co/api/users/karpathy/overview"
    assert a._build_models_url("karpathy").startswith(
        "https://huggingface.co/api/models?author=karpathy")


def test_parse_profile():
    p = HuggingFaceLookup.parse_profile(OVERVIEW_FIXTURE, "karpathy")
    assert p["username"] == "karpathy"
    assert p["fullname"] == "Andrej K"
    assert p["type"] == "user"
    assert p["orgs"] == [
        {"name": "compvis-community", "fullname": "CompVis Community"},
        {"name": "llmc", "fullname": "llmc"},
    ]
    assert p["num_models"] == 7
    assert p["num_followers"] == 2052
    assert p["created_at"] == "2022-08-13T23:40:17.000Z"
    assert p["profile_url"] == "https://huggingface.co/karpathy"
    assert "ML researcher" in p["description"]


def test_parse_model():
    m = HuggingFaceLookup.parse_model(MODELS_FIXTURE[0])
    assert m["model_id"] == "karpathy/nanochat-d32"
    assert m["likes"] == 96
    assert m["downloads"] == 5749
    assert m["model_url"] == "https://huggingface.co/karpathy/nanochat-d32"
    m2 = HuggingFaceLookup.parse_model(MODELS_FIXTURE[1])
    assert m2["pipeline_tag"] == "text-generation"
    assert m2["library_name"] == "transformers"


def test_extract_fields_user_found():
    a = _adapter()
    fields = a._extract_public_fields(OVERVIEW_FIXTURE)
    assert fields["user_found"] is True
    assert fields["profile"]["username"] == "karpathy"


def test_extract_fields_user_not_found():
    a = _adapter()
    fields = a._extract_public_fields(None)
    assert fields["user_found"] is False
    assert fields["username"] == ""


def test_query_full_result_shape():
    a = _adapter()
    result = a.query("karpathy")
    assert result["source_domain"] == "huggingface.co"
    assert result["data_boundary"] == "fully_public"
    fields = result["fields"]
    assert fields["user_found"] is True
    assert fields["profile"]["fullname"] == "Andrej K"
    assert fields["model_count"] == 2
    assert fields["models"][0]["model_id"] == "karpathy/nanochat-d32"
    assert result["field_count"] == len(fields)
    assert not result["error"]
    # audit trail records both API calls
    assert len(a.audit.get_trail()) == 2
    assert all(r["data_boundary"] == "fully_public" for r in a.audit.get_trail())
    assert a.audit.verify_integrity()


def test_query_user_explicit():
    a = _adapter()
    result = a.query_user("karpathy")
    assert result["fields"]["user_found"] is True


def test_query_nonexistent_user_returns_structured_not_found():
    def fake_execute(url, headers):
        if "/models?" in url:
            return (200, [], "")
        return (404, None, "HTTPError: 404")
    a = HuggingFaceLookup(
        execute_query=fake_execute,
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )
    result = a.query("zzz-no-such-user-999")
    assert result["fields"]["user_found"] is False
    assert "models" not in result["fields"]  # no model fetch for missing users


def test_invalid_username_returns_structured_empty():
    a = _adapter()
    result = a.query("not a username!!")
    assert result["fields"] == {}
    assert "username_invalid" in result["error"]


def test_fetch_public_models_transport_failure_returns_none():
    a = HuggingFaceLookup(
        execute_query=lambda url, headers: (0, None, "URLError: timeout"),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )
    assert a.fetch_public_models("karpathy") is None


def test_fetch_public_models_empty_list():
    a = HuggingFaceLookup(
        execute_query=lambda url, headers: (200, [], ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )
    assert a.fetch_public_models("brand_new_user") == []


# ------------------------------------------------- entity association wiring


def _query_result():
    return _adapter().query("karpathy")


def test_huggingface_entities_person_shape():
    from core.entity_association import _huggingface_entities
    fields = _query_result()["fields"]
    ents = _huggingface_entities(fields, "huggingface")
    assert len(ents) == 1
    e = ents[0]
    assert e["type"] == "person"
    assert e["value"] == "karpathy"
    assert e["display"] == "Andrej K"
    ctx = e["context"]
    assert ctx["username"] == "karpathy"  # cross-platform identity signal
    assert ctx["orgs"] == ["compvis-community", "llmc"]
    assert ctx["num_models"] == 7
    assert "ML researcher" in ctx["description"]  # contact-pipeline text


def test_huggingface_entities_not_found_is_empty():
    from core.entity_association import _huggingface_entities
    assert _huggingface_entities({"user_found": False}, "huggingface") == []
    assert _huggingface_entities({}, "huggingface") == []


def test_engine_extract_huggingface_branch():
    from core.entity_association import EntityAssociationEngine
    engine = EntityAssociationEngine()
    ents = engine._extract("huggingface", _query_result())
    assert len(ents) == 1
    assert ents[0]["type"] == "person"
    assert ents[0]["sources"] == ["huggingface"]


def test_username_joins_cross_platform_identity_resolution():
    from core.entity_association import EntityAssociationEngine, _huggingface_entities
    engine = EntityAssociationEngine()
    hf_ent = _huggingface_entities(_query_result()["fields"], "huggingface")[0]
    gh_ent = {"type": "person", "value": "karpathy", "display": "karpathy",
              "sources": ["github_deep"],
              "context": {"from": "github_deep", "username": "karpathy"}}
    entities = {
        "person:karpathy:huggingface": hf_ent,
        "person:karpathy:github": gh_ent,
    }
    assocs = engine._resolve_person_identity(entities)
    assert any(a["pattern"] == "cross_platform_identity"
               and set(a["platforms"]) == {"github_deep", "huggingface"}
               for a in assocs)


def test_engine_has_huggingface_slot_and_fanout():
    from core.entity_association import EntityAssociationEngine, _SEED_FANOUT
    assert "huggingface" in _SEED_FANOUT["person_name"]
    assert "huggingface" in EntityAssociationEngine.__dataclass_fields__
