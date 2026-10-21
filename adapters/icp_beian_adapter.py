"""ICP备案查询 — 工信部政务服务平台公开数据适配器。数据边界: fully_public

ICP备案是法律强制公开信息 (《互联网信息服务管理办法》)。
本适配器直调工信部 hlwicpfwc.miit.gov.cn 公开查询接口：
domain/企业名 → 主办单位名称 → 备案号 → 省份 → 审核时间

技术路线 (参考 HG-ha/ICP_Query 开源项目思路，自研实现)：
1. POST /api/auth 拿 token (authKey=md5("testtest"+timestamp)，无验证码)
2. POST /api/image/getCheckImagePoint 拿滑块验证码
3. 模板匹配解滑块 → POST /api/image/checkImage 拿 sign
4. POST /api/icpAbbreviateInfo/queryByCondition/ 查备案

Philosophy: ICP备案是强制公开信息，提取一切可见字段，不做掩码。
"""

from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import hashlib
import time
import json
import base64
import io


class IcpBeianLookup(SafeResearchAdapter):
    """工信部 ICP 备案查询。输入域名/企业名/备案号，返回备案主体信息。"""

    source_domain = "hlwicpfwc.miit.gov.cn"
    source_type = "government_mandatory_disclosure"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 3.0

    AUTH_URL = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/auth"
    CAPTCHA_URL = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/image/getCheckImagePoint"
    CHECK_URL = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/image/checkImage"
    QUERY_URL = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/icpAbbreviateInfo/queryByCondition/"

    # serviceType: 1=网站, 6=APP, 7=小程序, 8=快应用
    SERVICE_TYPES = {"web": 1, "app": 6, "miniapp": 7, "quickapp": 8}

    def _build_url(self, keyword: str, **params) -> str:
        return self.QUERY_URL

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        records = self._extract_records(raw_data if isinstance(raw_data, dict) else {})
        return {"record_count": len(records), "records": records}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._token = ""
        self._token_expire = 0
        self._sign = ""

    def _base_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/101.0",
            "Origin": "https://beian.miit.gov.cn",
            "Referer": "https://beian.miit.gov.cn/",
            "Accept": "application/json, text/plain, */*",
        }

    def _get_token(self) -> tuple[bool, str]:
        """获取 API token，无需验证码。"""
        if self._token and self._token_expire > int(time.time() * 1000):
            return True, self._token
        ts = round(time.time() * 1000)
        auth_key = hashlib.md5(f"testtest{ts}".encode()).hexdigest()
        try:
            import urllib.request
            data = f"authKey={auth_key}&timeStamp={ts}".encode()
            req = urllib.request.Request(self.AUTH_URL, data=data, headers=self._base_headers())
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success"):
                self._token = result["params"]["bussiness"]
                self._token_expire = int(time.time() * 1000) + result["params"]["expire"]
                return True, self._token
        except Exception:
            pass
        return False, ""

    def _solve_slider(self, small_b64: str, big_b64: str) -> int:
        """模板匹配解滑块验证码，返回 x 偏移。"""
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            return -1
        try:
            small = Image.open(io.BytesIO(base64.b64decode(small_b64))).convert("RGBA")
            big = Image.open(io.BytesIO(base64.b64decode(big_b64))).convert("RGB")
            s = __import__("numpy").array(small)
            b = __import__("numpy").array(big).astype(__import__("numpy").float32)
            mask = (s[:, :, 3] > 128).astype(__import__("numpy").float32)
            srgb = s[:, :, :3].astype(__import__("numpy").float32)
            sh, sw = srgb.shape[:2]
            bw = b.shape[1]
            best_x, best_score = 0, float("inf")
            np = __import__("numpy")
            for x in range(0, bw - sw):
                patch = b[0:sh, x:x + sw]
                diff = np.sum(((patch - srgb) ** 2) * mask[:, :, None]) / (np.sum(mask) + 1)
                if diff < best_score:
                    best_score, best_x = diff, x
            return best_x
        except Exception:
            return -1

    def _get_sign(self) -> tuple[bool, str]:
        """走滑块验证码拿 sign。失败返回 False。"""
        ok, token = self._get_token()
        if not ok:
            return False, ""
        try:
            import urllib.request
            headers = self._base_headers()
            headers.update({"token": token, "Content-Type": "application/json"})
            # 1. 拿验证码图
            req = urllib.request.Request(self.CAPTCHA_URL, data=b"{}", headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                cap = json.loads(resp.read().decode())
            if not cap.get("success"):
                return False, ""
            params = cap["params"]
            uuid = params["uuid"]
            # 2. 解滑块
            offset = self._solve_slider(params["smallImage"], params["bigImage"])
            if offset < 0:
                return False, ""
            # 3. 校验拿 sign
            check_data = json.dumps({"key": uuid, "value": str(offset)}).encode()
            req = urllib.request.Request(self.CHECK_URL, data=check_data, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("success") and result.get("params"):
                # sign 在返回的 params 中
                sign = result["params"].get("sign", "")
                if sign:
                    return True, sign
        except Exception:
            pass
        return False, ""

    def _query_api(self, keyword: str, service_type: int = 1,
                   page_num: int = 1, page_size: int = 10) -> dict:
        """直调查询接口。返回原始 JSON。"""
        ok, token = self._get_token()
        if not ok:
            return {"error": "token_failed"}
        if not self._sign:
            ok, sign = self._get_sign()
            if not ok:
                return {"error": "captcha_failed", "need_interaction": True}
            self._sign = sign
        try:
            import urllib.request
            headers = self._base_headers()
            headers.update({
                "token": token,
                "sign": self._sign,
                "Content-Type": "application/json",
            })
            body = json.dumps({
                "pageNum": page_num,
                "pageSize": page_size,
                "unitName": keyword,
                "serviceType": service_type,
            }).encode()
            req = urllib.request.Request(self.QUERY_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def _extract_records(self, raw: dict) -> list[dict]:
        """提取备案记录。字段全量保留，不做掩码。"""
        records = []
        params = raw.get("params", {}) if isinstance(raw, dict) else {}
        for item in params.get("list", []):
            records.append({
                "domain": item.get("domain", ""),
                "unit_name": item.get("unitName", ""),  # 主办单位名称
                "unit_nature": item.get("natureName", ""),  # 主办单位性质
                "main_licence": item.get("mainLicence", ""),  # 主体备案号
                "service_licence": item.get("serviceLicence", ""),  # 网站备案号
                "service_name": item.get("serviceName", ""),  # 网站名称
                "home_url": item.get("homeUrl", ""),
                "update_time": item.get("updateRecordTime", ""),  # 审核时间
                "unit_address": item.get("mainUnitAddress", ""),  # 主体地址
            })
        return records

    def query(self, keyword: str, service_type: str = "web",
              page_num: int = 1, page_size: int = 10, **kwargs) -> dict:
        """查询 ICP 备案。keyword: 域名/企业名/备案号。"""
        self._check_robots()
        st = self.SERVICE_TYPES.get(service_type, 1)
        raw = self._query_api(keyword, st, page_num, page_size)

        if raw.get("need_interaction"):
            return {
                "status": "interaction_required",
                "message": "滑块验证码自动识别失败，请在浏览器访问 https://beian.miit.gov.cn/ 手动查询一次",
                "keyword": keyword,
            }
        if raw.get("error"):
            return {"status": "lookup_failed", "error": raw["error"], "keyword": keyword}

        records = self._extract_records(raw)
        total = raw.get("params", {}).get("total", len(records))
        result = {
            "status": "ok",
            "keyword": keyword,
            "total": total,
            "record_count": len(records),
            "records": records,
            "source": "hlwicpfwc.miit.gov.cn",
            "disclosure": "mandatory_public_icp_filing",
        }
        self._record_audit(
            keyword=keyword,
            url=self.QUERY_URL,
            status=0,
            fields=["records"],
        )
        return result
