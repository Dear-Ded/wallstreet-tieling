"""BOSS直聘企业信息 — 浏览器辅助模式。数据边界: fully_public

Zhipin (zhipin.com) has strong bot detection:
- /gongsi/ and /wapi/zpgeek/search/joblist.json return HTTP 302 to a
  security-check page (or {"code":37,"message":"您的环境存在异常"}) for
  programmatic requests (verified 2026-10-21).
- A real browser passes the check automatically (user's daily use proves it).

Mode: browser-assisted (same as wenshu/xiaohongshu/weibo adapters).
- query(keyword) → interaction_required + 6-step browser instructions
- parse_browser_result(raw) → structures captured JSON:
  jobList records → company info (brandName, companyFullName),
  job info (jobName, salaryDesc, cityName, skills), recruiter info.

Association value (实体关联):
- Company → recruiter names/titles = personnel links
- Company → job locations = address signals
- Job posting volume = expansion/contraction signal

Philosophy: 招聘信息是企业主动公开的。浏览器里能看到的就是公开的。
只取公开可见的，不碰登录后私密内容。

No credentials. Default-off.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import json
import re


class ZhipinCompanyLookup(SafeResearchAdapter):
    """BOSS直聘企业搜索（浏览器辅助）：公司名 → 规模/在招职位/招聘者。"""

    source_domain = "www.zhipin.com"
    source_type = "recruitment_platform"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = True
    min_request_interval = 3.0

    _SEARCH_API = (
        "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
    )

    def _build_url(self, keyword: str, **params) -> str:
        from urllib.parse import quote
        return f"{self._SEARCH_API}?query={quote(keyword)}&city=101010100"

    def _build_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.zhipin.com/",
        }

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """Browser-assisted: return interaction instructions, no direct fetch."""
        self._record_audit(
            keyword=keyword, url=self._build_url(keyword),
            status=0, fields=[],
        )
        return {
            "query_subject_hash": self._hash(keyword),
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "status": "interaction_required",
            "requires_interaction": True,
            "instructions": self._browser_instructions(keyword),
            "error": "",
        }

    @staticmethod
    def _hash(keyword: str) -> str:
        import hashlib
        return hashlib.sha256(keyword.encode()).hexdigest()[:12]

    def _browser_instructions(self, keyword: str) -> list[str]:
        from urllib.parse import quote
        api_url = f"{self._SEARCH_API}?query={quote(keyword)}&city=101010100"
        return [
            "1. 在浏览器中打开 https://www.zhipin.com/（如遇安全验证，按页面提示完成）",
            f"2. 在同一浏览器标签页打开搜索 API：{api_url}",
            "3. 页面会显示 JSON（code 应为 0；若为 37 请先在 zhipin.com 首页完成验证后重试）",
            "4. 全选复制整个 JSON 文本",
            "5. 将 JSON 粘贴回本工具进行解析",
            "6. 只复制搜索结果 JSON，不登录、不提供任何账号信息",
        ]

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        """Not used in browser-assisted mode; see parse_browser_result."""
        return {"browser_assisted": True}

    def parse_browser_result(self, raw: str) -> dict[str, Any]:
        """Parse browser-captured zhipin joblist JSON.

        Accepts: raw JSON string (or dict) from /wapi/zpgeek/search/joblist.json
        Returns: structured companies + jobs.
        """
        if not raw:
            return {"parsed": False, "companies": [], "jobs": [], "error": "empty input"}
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return {"parsed": False, "companies": [], "jobs": [], "error": "invalid json"}
        if not isinstance(data, dict):
            return {"parsed": False, "companies": [], "jobs": [], "error": "unexpected shape"}
        if data.get("code") == 37:
            return {
                "parsed": False, "companies": [], "jobs": [],
                "error": "bot_check_not_passed",
                "hint": "API returned code 37 (环境存在异常); complete the browser check first",
            }
        zp_data = data.get("zpData") or {}
        job_list = zp_data.get("jobList") or []
        jobs = []
        companies: dict[str, dict] = {}
        for j in job_list:
            if not isinstance(j, dict):
                continue
            brand = j.get("brandName") or ""
            job = {
                "job_name": j.get("jobName"),
                "salary": j.get("salaryDesc"),
                "city": j.get("cityName"),
                "area": j.get("areaDistrict"),
                "experience": j.get("jobExperience"),
                "degree": j.get("jobDegree"),
                "skills": j.get("skills") or [],
                "company": brand,
                "recruiter": (j.get("bossInfo") or {}).get("name") if isinstance(j.get("bossInfo"), dict) else None,
                "recruiter_title": (j.get("bossInfo") or {}).get("title") if isinstance(j.get("bossInfo"), dict) else None,
            }
            jobs.append(job)
            if brand and brand not in companies:
                companies[brand] = {
                    "company_name": brand,
                    "company_full_name": j.get("brandName"),
                    "industry": j.get("brandIndustry"),
                    "company_size": j.get("brandScaleName"),
                    "stage": j.get("brandStageName"),
                    "job_count_in_page": 0,
                }
            if brand in companies:
                companies[brand]["job_count_in_page"] += 1
        return {
            "parsed": True,
            "job_count": len(jobs),
            "jobs": jobs[:50],
            "company_count": len(companies),
            "companies": list(companies.values())[:20],
        }
