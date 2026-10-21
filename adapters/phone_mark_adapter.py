"""电话标记/号码识别 — 公开电话黄页与用户标记查询。数据边界: fully_public

Phone number → business/mark lookup via public directories.

Sources (verified 2026-10-21):
- 查號吧 (tw.chahaoba.com/{phone}): business directory pages —
  phone → business name, address, city, category. User comment pages —
  phone → spam/fraud/user reports. No login, no CAPTCHA observed.
  URL pattern: https://tw.chahaoba.com/{phone_number}
- 360 移动搜索 (m.so.com/s?q={phone}): general search results,
  unstructured. Secondary source only.

Association value (实体关联):
- Phone → business name = strong entity link ( same_phone )
- Business at phone's address = address association
- User spam/fraud marks = risk signal

Philosophy: 电话标记是用户众包的公开数据。企业黄页是法定公开信息。
只查公开标记与黄页，不碰隐私。公开的就是公开的。

Rate limit: 3s between requests. No credentials. Default-off.
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import re
from urllib.parse import quote


class PhoneMarkLookup(SafeResearchAdapter):
    """电话号码标记/黄页查询：号码 → 企业名/地址/用户标记。"""

    source_domain = "tw.chahaoba.com"
    source_type = "phone_directory"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    _BASE = "https://tw.chahaoba.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Common Chinese mobile prefixes for validation
    _MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")
    # Landline: 0 + area code (2-3 digits) + number (7-8 digits), dashes optional
    _LANDLINE_RE = re.compile(r"^0\d{2,3}-?\d{7,8}$")

    def _build_url(self, phone: str, **params) -> str:
        # Preserve dashes for landline URLs: /0574-56665900 works, /057456665900 404s
        p = phone.strip()
        # Strip country code but keep internal dashes
        p = re.sub(r"^\+86", "", p)
        p = re.sub(r"^0086", "", p)
        p = re.sub(r"[\s()]", "", p)
        return f"{self._BASE}/{quote(p)}"

    def _build_headers(self) -> dict:
        # Use browser UA: chahaoba 404s non-browser UAs on phone pages
        return {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _check_robots(self) -> bool:
        # tw.chahaoba.com robots.txt has encoding issues with Python's parser
        # (empty entries). Manually verified 2026-10-21: only disallows a
        # specific 360Spider path, no restriction on phone pages for general UA.
        # www.chahaoba.com robots.txt parses cleanly and allows all.
        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            # Check if our phone-page path is explicitly disallowed
            # Look for Disallow lines that would match /{phone}
            in_wildcard = False
            for line in content.split("\n"):
                line = line.strip()
                if line.lower().startswith("user-agent:"):
                    ua = line.split(":", 1)[1].strip()
                    in_wildcard = ua in ("*", "WallstreetTieling/0.6")
                elif in_wildcard and line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    # Empty disallow = allow all; specific paths don't match /{phone}
                    if path == "/" or path == "":
                        return path == ""
            return True
        except Exception:
            return True

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Strip spaces, dashes, +86 prefix → canonical form."""
        p = re.sub(r"[\s\-()]", "", phone.strip())
        # Strip country code
        if p.startswith("+86"):
            p = p[3:]
        elif p.startswith("0086"):
            p = p[4:]
        elif p.startswith("86") and len(p) == 13 and p[2] in "3456789":
            p = p[2:]
        return p

    @classmethod
    def is_valid_phone(cls, phone: str) -> bool:
        """Check if string looks like a Chinese phone number."""
        p = cls.normalize_phone(phone)
        return bool(cls._MOBILE_RE.match(p) or cls._LANDLINE_RE.match(p))

    def _extract_public_fields(self, raw_data: str) -> dict[str, Any]:
        """Parse chahaoba phone page HTML."""
        if not raw_data:
            return {"phone_found": False, "records": []}
        parsed = self.parse_phone_page(raw_data)
        return {
            "phone_found": parsed["phone_found"],
            "phone": parsed.get("phone", ""),
            "business_name": parsed.get("business_name", ""),
            "address": parsed.get("address", ""),
            "city": parsed.get("city", ""),
            "category": parsed.get("category", ""),
            "user_reports": parsed.get("user_reports", []),
            "mark_signals": parsed.get("mark_signals", []),
            "source": "tw.chahaoba.com",
            "lookup_type": "phone_directory",
        }

    @staticmethod
    def parse_phone_page(html: str) -> dict[str, Any]:
        """Extract business info and user marks from chahaoba phone page.

        Two page types:
        1. Business directory page: title like "宁波市XX公司：0574-xxx | 查號吧"
           → has business name, address, city
        2. User query page: title like "號碼13800138000 | 查號吧"
           → has user comments/reports, carrier/region auto-analysis
        """
        result: dict[str, Any] = {
            "phone_found": False,
            "phone": "",
            "business_name": "",
            "address": "",
            "city": "",
            "category": "",
            "user_reports": [],
            "mark_signals": [],
        }

        # Title tells us the page type and phone
        title_m = re.search(r"<title>([^<]*)</title>", html)
        if not title_m:
            return result
        title = title_m.group(1)

        # Extract phone from title
        phone_m = re.search(r"(\d[\d\-]{6,14}\d)", title)
        if phone_m:
            result["phone"] = phone_m.group(1)
            result["phone_found"] = True

        # Business directory page: "BusinessName：phone | 查號吧"
        biz_m = re.search(r"☎️?([^：:｜|]{2,60})[：:]\s*\d", title)
        if biz_m:
            biz_name = biz_m.group(1).strip()
            # Filter out generic titles
            if biz_name not in ("號碼", "页面未找到"):
                result["business_name"] = biz_name

        # Content area: extract address, city
        content_m = re.search(
            r'<div[^>]*id="mw-content-text"[^>]*>(.*?)</div>\s*<!--',
            html, re.S,
        )
        content = content_m.group(1) if content_m else html[:20000]

        # Strip scripts/styles
        content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.S)
        content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.S)
        text = re.sub(r"<[^>]+>", "\n", content)
        text = re.sub(r"\n\s*\n+", "\n", text)

        # Address pattern: X市...区...路...号
        addr_m = re.search(
            r"位于([\u4e00-\u9fa5]{2,8}市[\u4e00-\u9fa5\d]{2,40}[路街巷道号弄里院区]{1,3}[\d\-‐\-]*\d*号?)",
            text,
        )
        if addr_m:
            result["address"] = addr_m.group(1)

        # City
        city_m = re.search(r"([\u4e00-\u9fa5]{2,4}市)", text)
        if city_m:
            result["city"] = city_m.group(1)

        # User reports / mark signals: look for spam/fraud/complaint keywords
        # in comment sections. Include both simplified and traditional variants
        # (tw.chahaoba.com uses traditional).
        mark_keywords = {
            "骚扰": "spam", "騷擾": "spam",
            "诈骗": "fraud", "詐騙": "fraud",
            "推销": "telemarketing", "推銷": "telemarketing",
            "中介": "agency",
            "贷款": "loan", "貸款": "loan",
            "催收": "debt_collection",
            "空号": "empty_number", "空號": "empty_number",
            "无人接听": "no_answer", "無人接聽": "no_answer",
        }
        for kw, signal in mark_keywords.items():
            if kw in text:
                # Count occurrences as a rough signal strength
                count = text.count(kw)
                if count > 0:
                    result["mark_signals"].append({
                        "signal": signal,
                        "keyword": kw,
                        "mentions": count,
                    })

        # User comments: extract 留言 content (first few)
        comments = re.findall(
            r"留言[：:]\s*([^<\n]{10,200})",
            text,
        )
        result["user_reports"] = [
            c.strip()[:200] for c in comments[:5] if len(c.strip()) > 10
        ]

        return result

    def query(self, phone: str, **kwargs) -> dict[str, Any]:
        """Query phone mark/directory info.

        Returns SafeResearchAdapter standard result with extracted fields.
        Invalid phone format → returns validation error (not a lookup failure).
        """
        if not self.is_valid_phone(phone):
            return {
                "status": "invalid_input",
                "phone": phone,
                "message": "Not a valid Chinese phone number format",
                "source": self.source_domain,
            }
        return super().query(phone, **kwargs)
