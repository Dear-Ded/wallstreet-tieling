"""WhatsMyName 用户名枚举 — 用户名跨站关联适配器。数据边界: fully_public

WhatsMyName (github.com/WebBreacher/WhatsMyName) 是社区维护的用户名枚举数据集
(692 站点, CC BY-SA 4.0)。2026-10-21 合并 sherlock-project/sherlock 数据集
(481 站点, MIT, 去重后新增 289) 后共 981 站点。给一个用户名, 检查 ~980 站点
是否存在该用户。sherlock 条目带 detect=message|status_code|response_url，
见 check_site 检测语义与 adapters/_vendor/whatsmyname/merge_sherlock.py。

关联深挖价值 (per user directive):
- 用户名复用是社工学经典: 同一人在多平台用同一用户名
- Profile 元数据 (bio/位置/公司) 直接暴露关联信息
- 中文站点优先: 豆瓣/知乎/微博已验证, 抖音/快手/小红书/B站走搜索

技术说明 (verified 2026-10-21):
- wmn-data.json 捆绑在 adapters/_vendor/whatsmyname/ (CC BY-SA 4.0, 需署名)
- 检测逻辑: e_string 在响应中 = 存在; m_string 在响应中 = 不存在
- 中文站点补充: douban (people/{account}/, 404=不存在, 已验证)
- 抖音/快手/小红书/B站: 用户名不在 profile URL 中, 标记为 search_based

Philosophy: 公开 profile 就是公开信息。用户名枚举只查"是否存在",
不碰私密内容。Bio/简介是用户自己公开的。
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import json
import os
import re
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed


# 中文站点补充 (WMN 数据集缺失或需增强的)
CHINESE_SITES = [
    {
        "name": "Douban",
        "uri_check": "https://www.douban.com/people/{account}/",
        "uri_pretty": "https://www.douban.com/people/{account}/",
        "e_code": 200,
        "e_string": "个人主页",
        "m_code": 404,
        "m_string": "页面不存在",
        "cat": "social",
        "note": "中文: 豆瓣用户主页, 用户名直接在 URL 中",
    },
    {
        "name": "Zhihu",
        "uri_check": "https://www.zhihu.com/people/{account}",
        "uri_pretty": "https://www.zhihu.com/people/{account}",
        "e_code": 200,
        "e_string": "知乎",
        "m_code": 404,
        "m_string": "你似乎来到了没有知识存在的荒原",
        "cat": "social",
        "note": "中文: 知乎用户主页 (WMN 自带 API 版本, 这是网页版补充)",
    },
    {
        "name": "Bilibili_Search",
        "uri_check": "https://search.bilibili.com/all?keyword={account}&from_source=web_search",
        "uri_pretty": "https://search.bilibili.com/all?keyword={account}",
        "e_code": 200,
        "e_string": "",
        "m_code": 200,
        "m_string": "",
        "cat": "social",
        "note": "中文: B站用户名搜索 (search_based, 需人工确认, WAF 可能拦截)",
        "search_based": True,
    },
    {
        "name": "Douyin_Search",
        "uri_check": "https://www.douyin.com/search/{account}?type=user",
        "uri_pretty": "https://www.douyin.com/search/{account}?type=user",
        "e_code": 200,
        "e_string": "",
        "m_code": 200,
        "m_string": "",
        "cat": "social",
        "note": "中文: 抖音用户搜索 (search_based, 需签名/browser-assisted)",
        "search_based": True,
    },
    {
        "name": "Xiaohongshu_Search",
        "uri_check": "https://www.xiaohongshu.com/search_result?keyword={account}&type=user",
        "uri_pretty": "https://www.xiaohongshu.com/search_result?keyword={account}&type=user",
        "e_code": 200,
        "e_string": "",
        "m_code": 200,
        "m_string": "",
        "cat": "social",
        "note": "中文: 小红书用户搜索 (search_based, browser-assisted)",
        "search_based": True,
    },
    {
        "name": "Kuaishou_Search",
        "uri_check": "https://www.kuaishou.com/search/user?query={account}",
        "uri_pretty": "https://www.kuaishou.com/search/user?query={account}",
        "e_code": 200,
        "e_string": "",
        "m_code": 200,
        "m_string": "",
        "cat": "social",
        "note": "中文: 快手用户搜索 (search_based, browser-assisted)",
        "search_based": True,
    },
]


class WhatsMyNameLookup(SafeResearchAdapter):
    """WhatsMyName 用户名跨站枚举。"""

    source_domain = "github.com"  # 数据集来源
    source_type = "username_enumeration"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 1.0  # 多站点检查, 间隔短一点

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sites = None
        self._data_path = os.path.join(
            os.path.dirname(__file__), "_vendor", "whatsmyname", "wmn-data.json"
        )
        # robots.txt 缓存: host -> RobotFileParser (抓取层遵守站点规则)
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _load_sites(self) -> list[dict]:
        """加载 WMN 数据集 + 中文站点补充。"""
        if self._sites is not None:
            return self._sites
        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sites = data.get("sites", [])
        except (FileNotFoundError, json.JSONDecodeError):
            sites = []
        # 中文站点优先 (去重: 同名则中文版优先)
        existing_names = {s.get("name", "").lower() for s in sites}
        for cs in CHINESE_SITES:
            if cs["name"].lower() not in existing_names:
                sites.append(cs)
        self._sites = sites
        return sites

    def _build_url(self, keyword: str, **params) -> str:
        # query() 重写了主逻辑, 这里返回占位
        return f"whatsmyname://{keyword}"

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        return raw_data if isinstance(raw_data, dict) else {}

    @staticmethod
    def _record_redirects() -> tuple:
        """Build an opener that records the final URL after redirects."""
        import urllib.request

        class _Recorder(urllib.request.HTTPRedirectHandler):
            def __init__(self):
                self.final_url: str | None = None

            def redirect_request(self, req, fp, code, msg, headers, newurl):
                self.final_url = newurl
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        recorder = _Recorder()
        return urllib.request.build_opener(recorder), recorder

    def check_site(self, site: dict, username: str) -> dict[str, Any]:
        """检查单个站点用户名是否存在。

        返回: {"site": name, "found": bool|None, "url": str, "note": str}
        found=None 表示无法判断 (search_based、regex 不合规或请求失败)

        检测语义 (site["detect"], sherlock 数据集合并 2026-10-21 引入):
        - message:      errorMsg 任一在 body 中 => 不存在；都不在 => 存在
        - status_code:  200 => 存在；>=400 => 不存在
        - response_url: 最终 URL == error_url => 不存在；否则 => 存在
        - (缺省/WMN 原生): m_string/e_string/m_code/e_code 四段式逻辑
        """
        name = site.get("name", "unknown")
        uri_template = site.get("uri_check", "")
        url = uri_template.replace("{account}", username)

        # search_based 站点: 只返回搜索 URL, 不自动判断
        if site.get("search_based"):
            return {
                "site": name,
                "found": None,
                "url": url,
                "note": site.get("note", "search_based, 需人工确认"),
            }

        # regexCheck (sherlock): 用户名不合格式 => 该站不查, 不判
        regex_check = site.get("regex_check") or ""
        if regex_check:
            try:
                if not re.match(regex_check, username or ""):
                    return {
                        "site": name,
                        "found": None,
                        "url": site.get("uri_pretty", url).replace("{account}", username),
                        "check_url": url,
                        "category": site.get("cat", ""),
                        "note": "regex_mismatch_skipped (site requires "
                                f"{regex_check})",
                    }
            except re.error:
                pass

        detect = site.get("detect") or ""
        need_final_url = detect == "response_url"
        opener = recorder = None
        if need_final_url:
            opener, recorder = self._record_redirects()

        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self._build_headers())
            if opener is not None:
                open_ctx = opener.open(req, timeout=15)
            else:
                open_ctx = urllib.request.urlopen(req, timeout=15)
            with open_ctx as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                geturl = getattr(resp, "geturl", None)
                final_url = (recorder.final_url if recorder and recorder.final_url
                             else (geturl() if callable(geturl) else ""))
        except Exception as e:
            # HTTPError 会带 code, 其他异常则无法判断
            status = getattr(e, "code", 0)
            try:
                body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            except Exception:
                body = ""
            final_url = ""

        if detect == "message":
            msgs = site.get("m_strings") or (
                [site.get("m_string")] if site.get("m_string") else []
            )
            if status == 0:
                found = None
            else:
                found = not any(m and m in body for m in msgs)
        elif detect == "status_code":
            if status == 200:
                found = True
            elif status >= 400:
                found = False
            else:
                found = None
        elif detect == "response_url":
            error_url = (site.get("error_url") or "").rstrip("/")
            if status == 0:
                found = None
            else:
                found = (final_url or "").rstrip("/") != error_url
        else:
            e_code = site.get("e_code")
            e_string = site.get("e_string", "")
            m_code = site.get("m_code")
            m_string = site.get("m_string", "")

            # 判断逻辑: m_string (不存在) 优先, 其次 e_string, 最后状态码
            # 原因: 404 页面常包含站点名等通用字符串, e_string 易误判
            found = None
            if m_string and m_string in body:
                found = False
            elif e_string and e_string in body:
                found = True
            elif m_code and status == m_code:
                found = False
            elif e_code and status == e_code:
                found = True

        return {
            "site": name,
            "found": found,
            "url": site.get("uri_pretty", url).replace("{account}", username),
            "check_url": url,
            "category": site.get("cat", ""),
            "note": site.get("note", ""),
        }

    # -- profile 元数据深挖 (Maigret 式, 默认关闭) ----------------------------

    def _robots_allowed(self, url: str) -> bool:
        """抓 profile 页前检查 robots.txt；取不到 robots 则保守放行但已尽力。"""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower()
            if not host:
                return False
            if host not in self._robots_cache:
                rp = urllib.robotparser.RobotFileParser()
                rp.set_url(f"https://{host}/robots.txt")
                try:
                    rp.read()
                except Exception:
                    self._robots_cache[host] = None  # type: ignore
                    return True
                self._robots_cache[host] = rp
            rp = self._robots_cache[host]
            if rp is None:
                return True
            return rp.can_fetch("*", url)
        except Exception:
            return False

    def _fetch_profile_html(self, url: str, timeout: int = 15) -> bytes | None:
        import urllib.request
        try:
            req = urllib.request.Request(url, headers=self._build_headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                return resp.read()
        except Exception:
            return None

    def _enrich_profiles(
        self,
        found: list[dict[str, Any]],
        username: str,
        max_profiles: int = 20,
        profile_interval: float = 2.0,
    ) -> list[dict[str, Any]]:
        """对命中站点抓取公开 profile 页并解析元数据。

        只抓公开 profile 页，不登录；robots 不允许则跳过；
        单站失败直接降级（不中断整体流程）；串行 + 固定间隔限速。
        """
        from core.profile_metadata import extract_profile_metadata, profile_text
        from core.contact_extractor import extract_contacts

        enriched: list[dict[str, Any]] = []
        # search_based 不自动判断, 不抓取
        targets = [r for r in found if r.get("url")][:max_profiles]
        for r in targets:
            site_name = r.get("site", "")
            pretty = r.get("url") or ""
            check_url = r.get("check_url") or ""
            # 微博 ajax / API 型 check_url 直接返回结构化 JSON, 优先用它
            enrich_url = (
                check_url if ("ajax" in check_url or "/api" in check_url)
                else (pretty or check_url)
            )
            if not enrich_url or not enrich_url.startswith("http"):
                continue
            if not self._robots_allowed(enrich_url):
                continue
            html = self._fetch_profile_html(enrich_url)
            time.sleep(profile_interval)
            if not html:
                continue
            try:
                pm = extract_profile_metadata(html, enrich_url)
            except Exception:
                continue
            pm["site_name"] = site_name  # WMN 数据集里的站点名
            contacts = extract_contacts(
                profile_text(pm), source_label=f"whatsmyname:{site_name}"
            )
            pm["contacts"] = contacts
            enriched.append(pm)
        return enriched

    def query(self, username: str, **params) -> dict[str, Any]:
        """枚举用户名 across 所有站点。

        params:
            categories: 只查指定分类 (list[str])
            max_sites: 最大检查站点数 (默认 100, 防止过慢)
            chinese_first: 中文站点优先 (默认 True)
            workers: 并发数 (默认 10)
            enrich_profiles: 是否对命中站点抓 profile 元数据 (默认 False;
                显式开启才抓, 避免默认 692 次请求)
            max_profiles: 最多深挖多少个命中站点 (默认 20)
            profile_interval: profile 抓取间隔秒 (默认 2.0)
        """
        import time
        start = time.monotonic()

        if not username or not username.strip():
            return self._build_empty_result(username, "empty_username")

        username = username.strip()
        sites = self._load_sites()

        # 分类过滤
        categories = params.get("categories")
        if categories:
            cats = {c.lower() for c in categories}
            sites = [s for s in sites if s.get("cat", "").lower() in cats]

        # 中文站点优先
        chinese_first = params.get("chinese_first", True)
        if chinese_first:
            chinese_names = {cs["name"].lower() for cs in CHINESE_SITES}
            # WMN 自带的 weibo/zhihu/tiktok 也算中文相关
            chinese_names.update({"weibo", "zhihu", "tiktok"})
            sites = sorted(
                sites,
                key=lambda s: 0 if s.get("name", "").lower() in chinese_names else 1,
            )

        max_sites = params.get("max_sites", 100)
        sites = sites[:max_sites]

        workers = params.get("workers", 10)
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_site = {
                executor.submit(self.check_site, site, username): site
                for site in sites
            }
            for future in as_completed(future_to_site):
                try:
                    results.append(future.result())
                except Exception as e:
                    site = future_to_site[future]
                    results.append({
                        "site": site.get("name", "unknown"),
                        "found": None,
                        "url": "",
                        "note": f"check_error: {e}",
                    })

        found = [r for r in results if r["found"] is True]
        not_found = [r for r in results if r["found"] is False]
        unknown = [r for r in results if r["found"] is None]

        # 可选深挖：profile 元数据（默认关闭，显式开启才抓取）
        enrich_profiles = params.get("enrich_profiles", False)
        profile_metadata: list[dict[str, Any]] = []
        if enrich_profiles and found:
            max_profiles = params.get("max_profiles", 20)
            profile_interval = params.get("profile_interval", 2.0)
            profile_metadata = self._enrich_profiles(
                found, username,
                max_profiles=max_profiles,
                profile_interval=profile_interval,
            )

        # 审计 (只存 hash, 不存用户名原文)
        self._record_audit(
            keyword=username,
            url=f"whatsmyname://{len(sites)}_sites"
            + ("+profiles" if enrich_profiles else ""),
            status=200 if found else 404,
            fields=["found_count", "sites_checked"]
            + (["profile_metadata"] if profile_metadata else []),
        )

        out = {
            "query_subject_hash": self._hash_query(username),
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "username": username,  # 用户名本身就是查询输入, 非敏感
            "sites_checked": len(sites),
            "found_count": len(found),
            "not_found_count": len(not_found),
            "unknown_count": len(unknown),
            "found": sorted(found, key=lambda x: x["site"]),
            "not_found": [{"site": r["site"], "url": r["url"]} for r in not_found],
            "needs_review": sorted(unknown, key=lambda x: x["site"]),
            "duration_ms": (time.monotonic() - start) * 1000,
        }
        out["fields"] = {
            "sites_found": [{"site": r["site"], "url": r["url"]} for r in found],
        }
        if enrich_profiles:
            out["fields"]["profile_metadata"] = profile_metadata
        return out

    def _hash_query(self, keyword: str) -> str:
        import hashlib
        return hashlib.sha256(keyword.encode()).hexdigest()[:12]

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _build_empty_result(self, keyword: str, reason: str) -> dict[str, Any]:
        return {
            "query_subject_hash": self._hash_query(keyword) if keyword else "",
            "source_domain": self.source_domain,
            "error": reason,
            "found": [],
            "found_count": 0,
        }

    def _record_audit(self, keyword: str, url: str, status: int, fields: list) -> None:
        from adapters.safe_research_adapter import ResearchAuditRecord
        import hashlib
        self.audit.log(ResearchAuditRecord(
            operation_type="whatsmyname_lookup",
            source_domain=self.source_domain,
            source_type=self.source_type,
            access_method="multi_site_enumeration",
            requires_credentials=False,
            requires_interaction=False,
            robots_txt_checked=True,
            robots_txt_allowed=True,
            rate_limit_applied=f"{self.min_request_interval}s",
            query_params_hash=hashlib.sha256(keyword.encode()).hexdigest()[:12],
            response_status=status,
            fields_extracted=fields,
            data_boundary=self.data_boundary,
        ))
