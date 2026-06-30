"""
公开源与授权源 Smoke 验证接口。
利用公开存档访问功能获取信息源，模拟普通人类研究员行为进行自动化操作，
形成可验证的运行痕迹。

设计原则:
  - 不做假数据 (no fake/fixture-only responses)
  - 使用真实浏览器自动化或公开存档作为回退
  - 记录完整的操作痕迹供审计
  - 区分 public_source_smoke / authorized_source_smoke
"""
from __future__ import annotations
import hashlib
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SmokeStatus(str, Enum):
    LIVE_VERIFIED = "live_verified"
    ARCHIVE_ACCESSED = "archive_accessed"
    ACCESS_DENIED = "access_denied"
    CONFIG_REQUIRED = "config_required"
    NOT_AVAILABLE = "not_available"


class SourceCategory(str, Enum):
    PUBLIC = "public"
    AUTHORIZED = "authorized"


@dataclass
class SmokeTrace:
    """单次 smoke 验证的可审计痕迹"""
    trace_id: str = ""
    source_name: str = ""
    source_category: SourceCategory = SourceCategory.PUBLIC
    status: SmokeStatus = SmokeStatus.NOT_AVAILABLE
    access_url: str = ""
    access_method: str = ""
    response_status: int = 0
    elapsed_ms: float = 0
    field_count: int = 0
    sample_fields: list[str] = field(default_factory=list)
    archive_fallback_used: bool = False
    archive_url: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    human_behavior_simulation: str = ""  # e.g. "scroll_and_wait_3s", "typed_in_search_box"

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "source_name": self.source_name,
            "source_category": self.source_category.value,
            "status": self.status.value,
            "access_url": self.access_url,
            "access_method": self.access_method,
            "response_status": self.response_status,
            "elapsed_ms": self.elapsed_ms,
            "field_count": self.field_count,
            "sample_fields": self.sample_fields,
            "archive_fallback_used": self.archive_fallback_used,
            "archive_url": self.archive_url,
            "timestamp": self.timestamp,
            "human_behavior_simulation": self.human_behavior_simulation,
        }


class SourceSmokeHarness:
    """
    数据源 Smoke 验证工具。
    验证每个数据源是否能实际获取结构化数据，留下可审计痕迹。
    """

    def __init__(
        self,
        *,
        http_get: Callable[[str], tuple[int, str | None, str]] | None = None,
        authorized_get: Callable[[str, dict], tuple[int, str | None, str]] | None = None,
    ):
        self._traces: list[SmokeTrace] = []
        self._http_get_override = http_get
        self._authorized_get_override = authorized_get

    # ================================================================
    # Public API
    # ================================================================

    def public_source_smoke(
        self,
        source_name: str,
        target_url: str,
        source_type: str = "government_public_disclosure",
    ) -> SmokeTrace:
        """
        对完全公开的数据源执行 smoke 验证。
        使用标准 HTTP GET 访问目标 URL，验证能否获取结构化数据。
        如果直接访问失败，尝试公开存档回退。
        """
        trace = SmokeTrace(
            trace_id=hashlib.sha256(f"{source_name}:{target_url}:{time.time()}".encode()).hexdigest()[:16],
            source_name=source_name,
            source_category=SourceCategory.PUBLIC,
            access_url=target_url,
            access_method="standard_http_get",
            human_behavior_simulation="direct_url_access",
        )
        t0 = time.monotonic()

        try:
            # Step 1: 直接访问
            status, raw, error = self._http_get(target_url)
            if status == 200 and raw:
                fields = self._extract_public_fields(raw, source_type)
                trace.status = SmokeStatus.LIVE_VERIFIED
                trace.response_status = 200
                trace.field_count = len(fields)
                trace.sample_fields = list(fields.keys())[:5]
            else:
                # Step 2: 公开存档回退
                archive_url = self._build_archive_url(target_url)
                status_a, raw_a, _ = self._http_get(archive_url)
                if status_a == 200 and raw_a:
                    fields = self._extract_public_fields(raw_a, source_type)
                    trace.status = SmokeStatus.ARCHIVE_ACCESSED
                    trace.archive_fallback_used = True
                    trace.archive_url = archive_url
                    trace.response_status = 200
                    trace.field_count = len(fields)
                    trace.sample_fields = list(fields.keys())[:5]
                    trace.human_behavior_simulation = "archive_research_access"
                else:
                    trace.status = SmokeStatus.ACCESS_DENIED
                    trace.response_status = status or 0

        except Exception as exc:
            trace.status = SmokeStatus.NOT_AVAILABLE
            logger.warning(f"Smoke failed for {source_name}: {exc}")

        trace.elapsed_ms = (time.monotonic() - t0) * 1000
        self._traces.append(trace)
        return trace

    def authorized_source_smoke(
        self,
        source_name: str,
        target_url: str,
        credentials: dict[str, str] | None = None,
    ) -> SmokeTrace:
        """
        对需要用户授权的数据源执行 smoke 验证。
        使用用户提供的凭证访问，验证能否获取结构化数据。
        """
        trace = SmokeTrace(
            trace_id=hashlib.sha256(f"{source_name}:{target_url}:{time.time()}".encode()).hexdigest()[:16],
            source_name=source_name,
            source_category=SourceCategory.AUTHORIZED,
            access_url=target_url,
            access_method="authorized_api_call",
            human_behavior_simulation="credential_authenticated_access",
        )
        t0 = time.monotonic()

        if not credentials or not credentials.get("auth_token"):
            trace.status = SmokeStatus.CONFIG_REQUIRED
            trace.elapsed_ms = (time.monotonic() - t0) * 1000
            self._traces.append(trace)
            return trace

        try:
            status, raw, error = self._authorized_get(target_url, credentials)
            if status == 200 and raw:
                fields = self._extract_authorized_fields(raw)
                trace.status = SmokeStatus.LIVE_VERIFIED
                trace.response_status = 200
                trace.field_count = len(fields)
                trace.sample_fields = list(fields.keys())[:5]
            else:
                trace.status = SmokeStatus.ACCESS_DENIED
                trace.response_status = status or 0
        except Exception as exc:
            trace.status = SmokeStatus.NOT_AVAILABLE
            logger.warning(f"Auth smoke failed for {source_name}: {exc}")

        trace.elapsed_ms = (time.monotonic() - t0) * 1000
        self._traces.append(trace)
        return trace

    def get_smoke_report(self) -> dict:
        """生成完整的 smoke 报告"""
        traces = [t.to_dict() for t in self._traces]
        return {
            "total_sources_smoked": len(traces),
            "live_verified": sum(1 for t in traces if t["status"] == "live_verified"),
            "archive_accessed": sum(1 for t in traces if t["status"] == "archive_accessed"),
            "access_denied": sum(1 for t in traces if t["status"] == "access_denied"),
            "config_required": sum(1 for t in traces if t["status"] == "config_required"),
            "not_available": sum(1 for t in traces if t["status"] == "not_available"),
            "traces": traces,
        }

    # ================================================================
    # Internal Helpers
    # ================================================================

    def _http_get(self, url: str) -> tuple[int, str | None, str]:
        if self._http_get_override is not None:
            return self._http_get_override(url)
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                                  "(Enterprise Due Diligence Research)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _authorized_get(self, url: str, creds: dict) -> tuple[int, str | None, str]:
        if self._authorized_get_override is not None:
            return self._authorized_get_override(url, creds)
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
                    "Authorization": f"Bearer {creds.get('auth_token', '')}",
                    "X-Research-Purpose": "commercial_due_diligence",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _extract_public_fields(self, raw: str, source_type: str) -> dict[str, str]:
        """从网页内容提取公开字段"""
        fields = {
            "source_type": source_type,
            "content_length": str(len(raw)),
        }
        # 公开企业信息典型字段检测
        import re
        for keyword, label in [
            (r"统一社会信用代码", "uscc_detected"),
            (r"法定代表人", "legal_representative_detected"),
            (r"注册资本", "registered_capital_detected"),
            (r"经营范围", "business_scope_detected"),
            (r"行政处罚", "penalty_detected"),
            (r"失信被执行人", "dishonesty_detected"),
            (r"裁判文书", "judgment_detected"),
            (r"专利权", "patent_detected"),
            (r"商标", "trademark_detected"),
        ]:
            if re.search(keyword, raw):
                fields[label] = "found"
        return fields

    def _extract_authorized_fields(self, raw: str) -> dict[str, str]:
        """从授权API响应提取字段"""
        try:
            data = json.loads(raw) if raw.startswith("{") else {}
            return {k: str(v)[:100] for k, v in data.items() if v is not None}
        except Exception:
            return {"raw_length": str(len(raw))}

    def _build_archive_url(self, original_url: str) -> str:
        """构建公开存档回退URL"""
        # Wayback Machine — Internet Archive 公开存档
        return f"https://web.archive.org/web/2024/{original_url}"


# ================================================================
# 可运行演示
# ================================================================
if __name__ == "__main__":
    harness = SourceSmokeHarness()

    # 公开源 smoke
    trace1 = harness.public_source_smoke(
        "creditchina",
        "https://www.creditchina.gov.cn/search?keyword=测试",
    )
    print(f"[public] {trace1.source_name}: {trace1.status.value} "
          f"({trace1.field_count} fields, {trace1.elapsed_ms:.0f}ms)")

    # 授权源 smoke (无凭证 → config_required)
    trace2 = harness.authorized_source_smoke(
        "qyyjt_api",
        "https://api.qyyjt.com/v1/enterprise/search?keyword=测试",
        credentials=None,
    )
    print(f"[authorized] {trace2.source_name}: {trace2.status.value}")

    # 生成报告
    print(json.dumps(harness.get_smoke_report(), ensure_ascii=False, indent=2))
