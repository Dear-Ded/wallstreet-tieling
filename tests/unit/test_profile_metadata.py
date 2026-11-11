"""Maigret 式 profile 元数据解析测试（离线 fixture，不联网）。

覆盖：通用 fallback、GitHub/微博/豆瓣/知乎/Gitee 专用解析、
contact_extractor 联动、whatsmyname 引擎分支。
"""

from core.profile_metadata import extract_profile_metadata, profile_text
from core.contact_extractor import extract_contacts
from core.entity_association import EntityAssociationEngine, _wmn_profile_entities

ALLOWED_TYPES = {
    "person", "business", "phone", "address", "email", "domain",
    "username_profile", "ip", "icp_license", "hiring_signal",
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GENERIC_HTML = """<!DOCTYPE html><html><head>
<title>someuser 的个人主页</title>
<meta name="description" content="热爱开源，联系：test@example.com">
<meta property="og:title" content="someuser · Example">
<meta property="og:description" content="全栈工程师，base 杭州">
</head><body>hi</body></html>"""

_GITHUB_HTML = """<html><head>
<title>zhangsan (张三) · GitHub</title>
<meta property="og:description" content="张三 has 42 repositories available.">
</head><body>
<script type="application/json">{"payload":{"profile":{"bio":"安全研究员，QQ：123456789",
"company":"Acme 安全","location":"北京","name":"张三"}}}</script>
</body></html>"""

_WEIBO_JSON = (
    '{"data":{"user":{"screen_name":"李四","description":"摄影爱好者，'
    '微信：lisi_photo，邮箱 lisi@example.org","location":"上海","company":""}}'
    ',"ok":1}'
)

_DOUBAN_HTML = """<html><head>
<title>王五的豆瓣</title>
<meta name="description" content="豆瓣用户王五">
</head><body>
<div class="signature">读书写字，手机 13912345678，豆瓣 id: wangwu</div>
</body></html>"""

_ZHIHU_HTML = """<html><head>
<title>赵六 - 知乎</title>
<meta name="description" content="知乎用户">
</head><body>
<script>window.__INITIAL_STATE__={"user":{"name":"赵六",
"description":"数据分析师","headline":"某大厂 P7"}};</script>
</body></html>"""

_GITEE_HTML = """<html><head>
<title>钱七 - Gitee.com</title>
<meta property="og:description" content="Java 开发者">
</head><body>
<script>{"description":"后端工程师，邮箱 qianqi@example.com","name":"钱七"}</script>
</body></html>"""

# ---------------------------------------------------------------------------
# 通用 fallback
# ---------------------------------------------------------------------------


def test_generic_fallback_meta_and_title():
    pm = extract_profile_metadata(_GENERIC_HTML, "https://example.com/someuser")
    assert pm["parser"] == "generic"
    # og:description 优先于 meta description
    assert pm["bio"] == "全栈工程师，base 杭州"
    # og:title 优先于 <title>
    assert pm["display_name"] == "someuser · Example"
    assert pm["site"] == "example.com"


def test_generic_handles_bytes_and_empty():
    pm = extract_profile_metadata(_GENERIC_HTML.encode("utf-8"),
                                  "https://example.com/x")
    assert pm["bio"] == "全栈工程师，base 杭州"
    pm2 = extract_profile_metadata("", "https://example.com/x")
    assert pm2["display_name"] is None and pm2["bio"] is None


# ---------------------------------------------------------------------------
# 专用解析
# ---------------------------------------------------------------------------


def test_github_parser_embedded_json():
    pm = extract_profile_metadata(_GITHUB_HTML, "https://github.com/zhangsan")
    assert pm["parser"] == "github"
    assert pm["display_name"] == "张三"
    assert "安全研究员" in pm["bio"]
    assert pm["company"] == "Acme 安全"
    assert pm["location"] == "北京"


def test_weibo_parser_ajax_json():
    pm = extract_profile_metadata(
        _WEIBO_JSON, "https://weibo.com/ajax/profile/info?custom=lisi")
    assert pm["parser"] == "weibo"
    assert pm["display_name"] == "李四"
    assert "摄影爱好者" in pm["bio"]
    assert pm["location"] == "上海"


def test_douban_parser_signature():
    pm = extract_profile_metadata(_DOUBAN_HTML,
                                  "https://www.douban.com/people/wangwu/")
    assert pm["parser"] == "douban"
    assert "王五" in (pm["display_name"] or "")
    assert "13912345678" in (pm["bio"] or "")


def test_zhihu_parser_embedded_json():
    pm = extract_profile_metadata(_ZHIHU_HTML,
                                  "https://www.zhihu.com/people/zhaoliu")
    assert pm["parser"] == "zhihu"
    assert pm["display_name"] == "赵六"
    assert pm["bio"] == "数据分析师"
    assert pm["company"] == "某大厂 P7"


def test_gitee_parser():
    pm = extract_profile_metadata(_GITEE_HTML, "https://gitee.com/qianqi")
    assert pm["parser"] == "gitee"
    assert pm["display_name"] == "钱七"
    assert "后端工程师" in (pm["bio"] or "")


# ---------------------------------------------------------------------------
# contact_extractor 联动
# ---------------------------------------------------------------------------


def test_profile_text_feeds_contact_extractor_github():
    pm = extract_profile_metadata(_GITHUB_HTML, "https://github.com/zhangsan")
    contacts = extract_contacts(profile_text(pm), source_label="whatsmyname:test")
    by_type = {c["type"]: c for c in contacts}
    assert by_type["qq"]["value"] == "123456789"
    assert by_type["qq"]["confidence"] == "strong"  # "QQ：" 上下文


def test_profile_text_feeds_contact_extractor_weibo():
    pm = extract_profile_metadata(
        _WEIBO_JSON, "https://weibo.com/ajax/profile/info?custom=lisi")
    contacts = extract_contacts(profile_text(pm), source_label="whatsmyname:test")
    by_type = {c["type"]: c for c in contacts}
    assert by_type["wechat"]["value"] == "lisi_photo"
    assert by_type["email"]["value"] == "lisi@example.org"


def test_profile_text_feeds_contact_extractor_douban():
    pm = extract_profile_metadata(_DOUBAN_HTML,
                                  "https://www.douban.com/people/wangwu/")
    contacts = extract_contacts(profile_text(pm), source_label="whatsmyname:test")
    by_type = {c["type"]: c for c in contacts}
    assert by_type["mobile"]["value"] == "13912345678"
    assert by_type["mobile"]["confidence"] == "exact"


def test_profile_text_feeds_contact_extractor_gitee():
    pm = extract_profile_metadata(_GITEE_HTML, "https://gitee.com/qianqi")
    contacts = extract_contacts(profile_text(pm), source_label="whatsmyname:test")
    by_type = {c["type"]: c for c in contacts}
    assert by_type["email"]["value"] == "qianqi@example.com"


# ---------------------------------------------------------------------------
# whatsmyname 引擎分支
# ---------------------------------------------------------------------------


def _enriched_pm():
    pm = extract_profile_metadata(_GITHUB_HTML, "https://github.com/zhangsan")
    pm["site_name"] = "GitHub (User)"
    pm["contacts"] = extract_contacts(
        profile_text(pm), source_label="whatsmyname:GitHub (User)")
    return pm


def test_wmn_profile_entities_person_and_contacts():
    ents = _wmn_profile_entities(_enriched_pm())
    by_type: dict[str, list] = {}
    for e in ents:
        by_type.setdefault(e["type"], []).append(e)
    assert by_type["person"][0]["value"] == "张三"
    assert by_type["person"][0]["context"]["site"] == "GitHub (User)"
    assert by_type["person"][0]["context"]["company"] == "Acme 安全"
    assert {e["value"] for e in by_type["username_profile"]} == {"123456789"}
    assert by_type["username_profile"][0]["context"]["contact_type"] == "qq"
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_engine_extract_whatsmyname_with_profile_metadata():
    eng = EntityAssociationEngine()
    result = {
        "fields": {
            "sites_found": [
                {"site": "GitHub (User)", "url": "https://github.com/zhangsan"},
            ],
            "profile_metadata": [_enriched_pm()],
        }
    }
    ents = eng._extract("whatsmyname", result)
    # 原有行为保留：username_reuse 实体
    reuse = [e for e in ents
             if e["context"].get("from") == "username_reuse"]
    assert len(reuse) == 1 and reuse[0]["value"] == "GitHub (User)"
    # 新增：profile person + 联系方式实体
    persons = [e for e in ents
               if e["type"] == "person" and e["context"].get("from") == "wmn_profile"]
    assert len(persons) == 1 and persons[0]["value"] == "张三"
    assert any(e["type"] == "username_profile"
               and e["context"].get("contact_type") == "qq" for e in ents)
    assert all(e["type"] in ALLOWED_TYPES for e in ents)


def test_engine_extract_whatsmyname_without_enrichment_unchanged():
    eng = EntityAssociationEngine()
    result = {"fields": {
        "sites_found": [{"site": "Gitee", "url": "https://gitee.com/foo"}],
    }}
    ents = eng._extract("whatsmyname", result)
    assert len(ents) == 1
    assert ents[0]["type"] == "username_profile"
    assert ents[0]["context"]["from"] == "username_reuse"


def test_wmn_profile_entities_empty_safe():
    assert _wmn_profile_entities({}) == []
    assert _wmn_profile_entities(None) == []  # type: ignore
    assert _wmn_profile_entities({"contacts": [{"type": "bogus", "value": "x"}]}) == []
