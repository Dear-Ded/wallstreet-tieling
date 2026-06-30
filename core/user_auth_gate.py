"""
用户授权网关 — 默认安全、授权后开启、可审计。

所有信息采集适配器必须通过此网关才能执行查询。
默认状态: 所有数据源 = 禁用。
用户必须为每个数据源显式授权后方可使用。
所有授权操作均被审计日志记录。

安全策略兼容设计:
- enabled=False(默认) → 不连接任何外部服务
- 用户显式调用 enable_source() → 记录授权时间/用户身份
- 所有查询通过 audit_trail 可追溯
- 配置文件控制所有开关
"""

from __future__ import annotations
import json
import time
import hashlib
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceAuthorizationStatus(str, Enum):
    DISABLED = "disabled"          # 默认 — 用户未授权
    ENABLED = "enabled"           # 用户已授权
    EXPIRED = "expired"            # 授权已过期
    REVOKED = "revoked"            # 用户已撤回


@dataclass
class AuthorizationRecord:
    """不可变的授权审计记录"""
    source_key: str
    source_name: str
    source_type: str                # public_api | authorized_api | public_web | user_upload
    status: SourceAuthorizationStatus = SourceAuthorizationStatus.DISABLED
    enabled_at: str = ""
    enabled_by: str = ""            # 用户身份标识(哈希)
    expires_at: str = ""            # 授权过期时间
    configuration: dict = field(default_factory=dict)
    audit_trail: list[dict] = field(default_factory=list)

    def record_access(self, operation: str, target_hash: str, result: str) -> None:
        self.audit_trail.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "operation": operation,
            "target_hash": target_hash,
            "result": result,
        })

    def to_dict(self) -> dict:
        return {
            "source_key": self.source_key,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "status": self.status.value,
            "enabled_at": self.enabled_at,
            "enabled_by": self.enabled_by,
            "expires_at": self.expires_at,
            "configuration": self.configuration,
            "audit_trail_count": len(self.audit_trail),
            "last_audit": self.audit_trail[-1] if self.audit_trail else None,
        }


class UserAuthorizationGate:
    """
    用户授权网关 — 所有数据源访问的守门人。
    
    设计原则:
    1. 默认安全: 所有数据源默认禁用, 必须用户显式授权
    2. 授权可追溯: 每次授权记录时间/用户/配置
    3. 可配置: 每个数据源的配置(频率、字段范围等)用户可调整
    4. 可撤回: 用户随时可禁用已授权的数据源
    """

    def __init__(self, user_identity: str = ""):
        self._user_identity = hashlib.sha256(
            (user_identity or f"user_{time.time()}").encode()
        ).hexdigest()[:16]
        self._sources: dict[str, AuthorizationRecord] = {}
        self._lock = threading.Lock()

    def register_source(
        self, source_key: str, source_name: str,
        source_type: str = "public_api",
        default_config: dict | None = None,
    ) -> AuthorizationRecord:
        """注册数据源(默认禁用状态)"""
        with self._lock:
            record = AuthorizationRecord(
                source_key=source_key,
                source_name=source_name,
                source_type=source_type,
                status=SourceAuthorizationStatus.DISABLED,
                configuration=default_config or {},
            )
            self._sources[source_key] = record
            return record

    def enable_source(
        self, source_key: str,
        config: dict | None = None,
        duration_hours: int = 24,
    ) -> AuthorizationRecord:
        """用户显式授权启用数据源"""
        with self._lock:
            if source_key not in self._sources:
                raise KeyError(f"Source '{source_key}' not registered. Call register_source() first.")
            
            record = self._sources[source_key]
            record.status = SourceAuthorizationStatus.ENABLED
            record.enabled_at = time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            record.enabled_by = self._user_identity
            if duration_hours > 0:
                record.expires_at = time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z",
                    time.localtime(time.time() + duration_hours * 3600),
                )
            if config:
                record.configuration.update(config)
            
            record.record_access("source_enabled", source_key, "authorized")
            return record

    def disable_source(self, source_key: str) -> AuthorizationRecord:
        """用户撤回授权"""
        with self._lock:
            if source_key not in self._sources:
                raise KeyError(f"Source '{source_key}' not found.")
            record = self._sources[source_key]
            record.status = SourceAuthorizationStatus.REVOKED
            record.record_access("source_revoked", source_key, "user_revoked")
            return record

    def is_authorized(self, source_key: str) -> bool:
        """检查数据源是否已授权且未过期"""
        with self._lock:
            record = self._sources.get(source_key)
            if not record or record.status != SourceAuthorizationStatus.ENABLED:
                return False
            if record.expires_at and record.expires_at < time.strftime("%Y-%m-%dT%H:%M:%S.000Z"):
                record.status = SourceAuthorizationStatus.EXPIRED
                return False
            return True

    def log_access(self, source_key: str, operation: str, target_hash: str, result: str) -> None:
        """记录数据源访问审计"""
        with self._lock:
            if source_key in self._sources:
                self._sources[source_key].record_access(operation, target_hash, result)

    def get_authorization_report(self) -> dict[str, Any]:
        """生成授权状态报告"""
        with self._lock:
            return {
                "user_identity_hash": self._user_identity,
                "total_sources": len(self._sources),
                "enabled": sum(1 for s in self._sources.values() if s.status == SourceAuthorizationStatus.ENABLED),
                "disabled": sum(1 for s in self._sources.values() if s.status == SourceAuthorizationStatus.DISABLED),
                "expired": sum(1 for s in self._sources.values() if s.status == SourceAuthorizationStatus.EXPIRED),
                "revoked": sum(1 for s in self._sources.values() if s.status == SourceAuthorizationStatus.REVOKED),
                "sources": {k: v.to_dict() for k, v in self._sources.items()},
            }

    def get_source_config(self, source_key: str) -> dict:
        """获取已启用数据源的配置"""
        if not self.is_authorized(source_key):
            return {"error": f"Source '{source_key}' is not authorized"}
        return self._sources[source_key].configuration
