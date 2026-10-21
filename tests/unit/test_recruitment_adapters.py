"""Tests for lagou_adapter, zhaopin_adapter, zhipin_adapter."""
import json
import pytest

from adapters.lagou_adapter import LagouCompanyLookup
from adapters.zhaopin_adapter import ZhaopinCompanyLookup
from adapters.zhipin_adapter import ZhipinCompanyLookup


def _no_sleep(_s):
    pass


def _robots_ok(domain, url):
    return True


# ---------------- Lagou ----------------

LAGOU_SEARCH_JSON = json.dumps({
    "pageSize": 16,
    "result": [
        {
            "companyId": 62,
            "companyFullName": "抖音视界（北京）有限公司",
            "companyShortName": "字节跳动",
            "city": "北京",
            "industryField": "内容资讯,短视频",
            "financeStage": "D轮及以上",
            "companySize": "2000人以上",
            "positionNum": 620,
            "interviewRemarkNum": 185,
            "updateTime": "2026-10-21 09:53:26",
            "otherLabel": "弹性工作,年度体检",
        }
    ],
})

LAGOU_DETAIL_HTML = (
    '<html>"city":"北京","district":"海淀区",'
    '"detailAddress":"北三环西路甲18号","lat":"39.965724","lng":"116.340725",'
    '"companySize":"2000人以上","financeStage":"D轮及以上",'
    '"industryField":"内容资讯,短视频","companyFullName":"抖音视界（北京）有限公司",'
    '"positionName":"大数据开发工程师","positionName":"技术支持客服-飞书",'
    '"positionName":"大数据开发工程师"</html>'
)


def test_lagou_search_parses_companies():
    a = LagouCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                           execute_query=lambda u, h: (200, LAGOU_SEARCH_JSON, ""))
    r = a.query("字节跳动")
    f = r["fields"]
    assert f["company_found"] is True
    assert f["company_count"] == 1
    c = f["companies"][0]
    assert c["company_full_name"] == "抖音视界（北京）有限公司"
    assert c["company_short_name"] == "字节跳动"
    assert c["company_size"] == "2000人以上"
    assert c["finance_stage"] == "D轮及以上"
    assert c["position_count"] == 620
    assert c["detail_url"] == "https://www.lagou.com/gongsi/62.html"


def test_lagou_search_empty():
    a = LagouCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                           execute_query=lambda u, h: (200, '{"result":[]}', ""))
    r = a.query("不存在的公司xyz123")
    assert r["fields"]["company_found"] is False


def test_lagou_search_bad_json():
    a = LagouCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                           execute_query=lambda u, h: (200, "not json", ""))
    r = a.query("test")
    assert r["fields"]["company_found"] is False


def test_lagou_detail_parses_address():
    a = LagouCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                           execute_query=lambda u, h: (200, LAGOU_DETAIL_HTML, ""))
    r = a.query_company_detail(62)
    f = r["fields"]
    assert f["city"] == "北京"
    assert f["district"] == "海淀区"
    assert "北三环西路甲18号" in f["detail_address"]
    assert f["lat"] == "39.965724"
    assert f["full_address"] == "北京海淀区北三环西路甲18号"
    # positions deduped
    assert f["positions"] == ["大数据开发工程师", "技术支持客服-飞书"]


def test_lagou_audit_no_raw_pii():
    a = LagouCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                           execute_query=lambda u, h: (200, LAGOU_SEARCH_JSON, ""))
    a.query("字节跳动")
    trail = a.audit.get_trail()
    assert len(trail) == 1
    # audit stores hash, not raw keyword
    assert "字节跳动" not in json.dumps(trail[0], ensure_ascii=False)


def test_lagou_default_off():
    # Registered default-off check happens at registry level;
    # adapter itself must not require credentials
    a = LagouCompanyLookup()
    assert a.requires_credentials is False
    assert a.data_boundary == "fully_public"


# ---------------- Zhaopin ----------------

ZHAOPIN_HTML = (
    '<html>{"companyName":"测试科技有限公司","companyNumber":"CZL123456",'
    '"companySize":"100-499人","companyUrl":"http://company.zhaopin.com/CZL123456.htm",'
    '"financingStage":"B轮","industryName":"互联网","firstPublishTime":"2026-10-20",'
    '"displayPhoneNumber":"010-12345678","jobName":"Python工程师",'
    '"salary":"15K-25K","workCity":"北京"}'
    '{"companyName":"测试科技有限公司","companyNumber":"CZL123456",'
    '"jobName":"前端工程师","salary":"12K-20K"}'
    '{"companyName":"另一家公司","companyNumber":"CZL999999",'
    '"companySize":"50-99人","jobName":"产品经理"}</html>'
)


def test_zhaopin_parses_records():
    a = ZhaopinCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                             execute_query=lambda u, h: (200, ZHAOPIN_HTML, ""))
    r = a.query("测试科技")
    f = r["fields"]
    assert f["company_found"] is True
    assert f["record_count"] == 3
    assert f["company_count"] == 2
    # company dedup keeps first-seen fields
    comp = {c["company_name"]: c for c in f["companies"]}
    assert comp["测试科技有限公司"]["company_number"] == "CZL123456"
    assert comp["测试科技有限公司"]["financing_stage"] == "B轮"
    assert comp["测试科技有限公司"]["display_phone"] == "010-12345678"
    assert comp["另一家公司"]["company_size"] == "50-99人"


def test_zhaopin_empty():
    a = ZhaopinCompanyLookup(sleeper=_no_sleep, robots_checker=_robots_ok,
                             execute_query=lambda u, h: (200, "<html>no jobs</html>", ""))
    r = a.query("xyz不存在")
    assert r["fields"]["company_found"] is False


def test_zhaopin_url_encoding():
    a = ZhaopinCompanyLookup()
    url = a._build_url("字节跳动")
    assert "zhaopin.com/sou/" in url
    assert "query=" not in url  # uses q= param
    assert "%E5%AD%97%E8%8A%82" in url  # url-encoded


# ---------------- Zhipin (browser-assisted) ----------------

ZHIPIN_JSON = json.dumps({
    "code": 0,
    "zpData": {
        "jobList": [
            {
                "jobName": "Python后端工程师",
                "salaryDesc": "20-35K",
                "cityName": "北京",
                "areaDistrict": "海淀区",
                "jobExperience": "3-5年",
                "jobDegree": "本科",
                "skills": ["Python", "Django"],
                "brandName": "测试科技",
                "brandIndustry": "互联网",
                "brandScaleName": "100-499人",
                "brandStageName": "B轮",
                "bossInfo": {"name": "张经理", "title": "技术招聘"},
            },
            {
                "jobName": "前端工程师",
                "salaryDesc": "15-25K",
                "cityName": "北京",
                "brandName": "测试科技",
                "brandIndustry": "互联网",
                "brandScaleName": "100-499人",
                "brandStageName": "B轮",
            },
        ]
    },
})


def test_zhipin_query_requires_interaction():
    a = ZhipinCompanyLookup(sleeper=_no_sleep)
    r = a.query("测试科技")
    assert r["status"] == "interaction_required"
    assert r["requires_interaction"] is True
    assert len(r["instructions"]) == 6
    assert any("zhipin.com" in s for s in r["instructions"])


def test_zhipin_parse_browser_result():
    a = ZhipinCompanyLookup()
    r = a.parse_browser_result(ZHIPIN_JSON)
    assert r["parsed"] is True
    assert r["job_count"] == 2
    assert r["company_count"] == 1
    comp = r["companies"][0]
    assert comp["company_name"] == "测试科技"
    assert comp["company_size"] == "100-499人"
    assert comp["stage"] == "B轮"
    assert comp["job_count_in_page"] == 2
    job = r["jobs"][0]
    assert job["job_name"] == "Python后端工程师"
    assert job["recruiter"] == "张经理"
    assert job["recruiter_title"] == "技术招聘"


def test_zhipin_parse_bot_check():
    a = ZhipinCompanyLookup()
    r = a.parse_browser_result(json.dumps({"code": 37, "message": "您的环境存在异常"}))
    assert r["parsed"] is False
    assert r["error"] == "bot_check_not_passed"


def test_zhipin_parse_invalid():
    a = ZhipinCompanyLookup()
    assert a.parse_browser_result("")["parsed"] is False
    assert a.parse_browser_result("not json")["parsed"] is False
    assert a.parse_browser_result([1, 2])["parsed"] is False


def test_zhipin_dict_input():
    a = ZhipinCompanyLookup()
    r = a.parse_browser_result(json.loads(ZHIPIN_JSON))
    assert r["parsed"] is True
    assert r["job_count"] == 2
