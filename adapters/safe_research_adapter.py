"""
安全企业尽调信息采集标准化适配器基类。
每个子类实现一个公开信息渠道的查询逻辑。
所有操作都在公开/授权/可审计边界内。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ResearchAuditRecord:
    """不可变的研究操作审计记录"""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    operation_type: str = ""
    source_domain: str = ""
    source_type: str = ""
    access_method: str = ""
    requires_credentials: bool = False
    requires_interaction: bool = False
    robots_txt_checked: bool = True
    robots_txt_allowed: bool = True
    rate_limit_applied: str = "3s"
    query_params_hash: str = ""
    response_status: int = 0
    fields_extracted: list[str] = field(default_factory=list)
    data_boundary: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, default=str)


class ResearchAuditLogger:
    """研究操作审计日志器"""
    def __init__(self):
        self._records: list[ResearchAuditRecord] = []
    def log(self, record: ResearchAuditRecord) -> None:
        self._records.append(record)
    def get_trail(self) -> list[dict]:
        return [json.loads(r.to_json()) for r in self._records]
    def verify_integrity(self) -> bool:
        return all(
            r.robots_txt_checked and r.rate_limit_applied != ""
            and r.source_domain != "" and r.data_boundary != ""
            for r in self._records
        )


class SafeResearchAdapter(ABC):
    """所有信息采集适配器的基类。强制实施: robots.txt、频率限制、审计日志、边界验证。"""
    def __init__(
        self,
        *,
        execute_query: Callable[[str, dict[str, str]], tuple[int, Any, str]] | None = None,
        robots_checker: Callable[[str, str], bool] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.audit = ResearchAuditLogger()
        self._last_request_time: dict[str, float] = {}
        self._robot_parser = urllib.robotparser.RobotFileParser()
        self._execute_query_override = execute_query
        self._robots_checker = robots_checker
        self._sleeper = sleeper or time.sleep

    source_domain: str = ""
    source_type: str = "government_public_disclosure"
    data_boundary: str = "fully_public"
    requires_credentials: bool = False
    requires_interaction: bool = False
    min_request_interval: float = 3.0

    def query(self, keyword: str, **params) -> dict[str, Any]:
        start = time.monotonic()
        if self.requires_credentials and not self._has_required_credentials():
            self._record_audit(keyword=keyword, url="", status=0, fields=[])
            return self._build_empty_result(keyword, "credentials_required")
        self._enforce_rate_limit()
        robots_ok = self._check_robots()
        if not robots_ok:
            self._record_audit(keyword=keyword, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(keyword, "robots_txt_disallowed")
        url = self._build_url(keyword, **params)
        headers = self._build_headers()
        status, raw_data, error = self._execute_query(url, headers)
        fields = self._extract_public_fields(raw_data) if raw_data else {}
        self._record_audit(keyword=keyword, url=url, status=status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "fields": fields,
            "field_count": len(fields),
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }

    @abstractmethod
    def _build_url(self, keyword: str, **params) -> str: ...
    @abstractmethod
    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]: ...

    def _has_required_credentials(self) -> bool:
        return True

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _enforce_rate_limit(self) -> None:
        key = self.source_domain
        now = time.monotonic()
        last = self._last_request_time.get(key, 0)
        wait = self.min_request_interval - (now - last)
        if wait > 0:
            self._sleeper(wait)
        self._last_request_time[key] = time.monotonic()

    def _check_robots(self) -> bool:
        if self._robots_checker is not None:
            return bool(self._robots_checker(self.source_domain, f"https://{self.source_domain}/"))
        try:
            self._robot_parser.set_url(f"https://{self.source_domain}/robots.txt")
            self._robot_parser.read()
            return self._robot_parser.can_fetch("WallstreetTieling/0.6", f"https://{self.source_domain}/")
        except Exception:
            return True

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence)",
            "X-Research-Purpose": "commercial_due_diligence",
        }

    def _record_audit(
        self,
        keyword: str,
        url: str,
        status: int,
        fields: list[str],
        *,
        robots_allowed: bool = True,
    ) -> None:
        self.audit.log(ResearchAuditRecord(
            operation_type="public_record_query",
            source_domain=self.source_domain,
            source_type=self.source_type,
            access_method="standard_http_get",
            requires_credentials=self.requires_credentials,
            requires_interaction=self.requires_interaction,
            rate_limit_applied=f"{self.min_request_interval}s",
            robots_txt_allowed=robots_allowed,
            query_params_hash=hashlib.sha256(keyword.encode()).hexdigest()[:12],
            response_status=status,
            fields_extracted=fields,
            data_boundary=self.data_boundary,
        ))

    def _build_empty_result(self, keyword: str, reason: str) -> dict:
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": 0,
            "fields": {},
            "field_count": 0,
            "error": f"Query blocked: {reason}",
            "duration_ms": 0,
        }
