"""
通用多数据源接入模块 - 标准内置组件
Universal Multi-Data Source Access Module - Standard Built-in Component

架构设计原则:
1. 高度可扩展 - 新增数据源只需继承 BaseDataSource
2. 类型安全 - 充分利用 Python 类型注解
3. asyncio 原生支持 - 全异步设计
4. 错误处理完善 - 分层错误处理与重试机制
5. 易于测试 - 依赖注入 + 抽象接口
6. 开箱即用 - 单例模式 + 全局入口 + 缓存机制

版本: 2.0.0 (标准内置组件版)
"""

from __future__ import annotations

import asyncio
import yaml
import time
import logging
import random
import hashlib
import json
import ipaddress
import csv
import re
import socket
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union, Generic, TypeVar, Callable
from pydantic import BaseModel, Field, field_validator
try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover - optional dependency fallback
    class BaseSettings(BaseModel):
        """Fallback BaseSettings when pydantic-settings is unavailable."""
        pass
try:
    from core.intelligence_retrieval import EntityResolutionScorer
except ImportError:  # pragma: no cover - optional package import fallback
    EntityResolutionScorer = None  # type: ignore[assignment]
from typing_extensions import Protocol
from functools import lru_cache, wraps
from collections import OrderedDict
import threading

_FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding"}
_MAX_QUERY_LENGTH = 2048
_MAX_RESPONSE_SIZE = 10 * 1024 * 1024
_OFAC_MAX_RESPONSE_SIZE = 2 * 1024 * 1024
_UN_SC_MAX_RESPONSE_SIZE = 8 * 1024 * 1024
_IPV4_ALIAS_RE = re.compile(r"(?:0x[0-9a-fA-F]+|\d+)(?:\.(?:0x[0-9a-fA-F]+|\d+)){0,3}")


def _parse_ip_candidate(hostname: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    if _IPV4_ALIAS_RE.fullmatch(hostname):
        try:
            return ipaddress.ip_address(socket.inet_aton(hostname))
        except OSError:
            return None

    return None


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    )


def _validate_http_url(value: str, field_name: str, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} cannot be empty")

    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")

    parsed = urlparse(value)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"{field_name} must include a hostname")

    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include credentials")

    if parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must not include query or fragment")

    ip = _parse_ip_candidate(hostname)
    if ip and _is_blocked_ip(ip):
        raise ValueError(f"{field_name} points to a blocked host")

    blocked_names = ("localhost", "metadata", "169.254.169.254")
    if any(part in hostname.lower() for part in blocked_names):
        raise ValueError(f"{field_name} points to a blocked host")

    return value.rstrip("/")


def _validate_headers(headers: Dict[str, str], field_name: str) -> Dict[str, str]:
    for key, value in headers.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} contains an invalid header name")
        if not isinstance(value, str):
            raise ValueError(f"{field_name} contains a non-string header value")
        if any(ch in key for ch in ("\r", "\n")) or any(ch in value for ch in ("\r", "\n")):
            raise ValueError(f"{field_name} must not contain newline characters")
        if key.lower() in _FORBIDDEN_HEADERS:
            raise ValueError(f"forbidden custom header: {key}")
    return headers


def _safe_url_for_diagnostics(raw: str) -> str:
    parsed = urlparse(str(raw or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _join_endpoint(base_url: str, endpoint: str) -> str:
    """Build a request URL while allowing vetted provider-specific absolute URLs."""
    endpoint = str(endpoint or "")
    if endpoint.startswith(("http://", "https://")):
        return _validate_http_url(endpoint, "endpoint")
    return f"{base_url}/{endpoint.lstrip('/')}"


def _safe_exception_metadata(exc: Exception) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"type": type(exc).__name__}
    status = getattr(exc, "status", None)
    if status is not None:
        metadata["http_status"] = int(status)
    request_info = getattr(exc, "request_info", None)
    real_url = getattr(request_info, "real_url", None)
    if real_url:
        metadata["url"] = _safe_url_for_diagnostics(str(real_url))
    message = str(exc)
    if message and len(message) <= 240:
        metadata["message"] = message
    return metadata

# =============================================================================
# 1. 核心类型定义 (Core Type Definitions)
# =============================================================================

T = TypeVar('T')
DataSourceType = TypeVar('DataSourceType', bound='BaseDataSource')

class QueryStatus(str, Enum):
    """查询状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

class ConfigError(Exception):
    """配置相关错误"""
    pass

class QueryError(Exception):
    """查询相关错误"""
    pass

class DataSourceError(Exception):
    """数据源错误"""
    pass

from .auth_handlers import (  # noqa: E402
    AuthChallengeRequired,
    AuthRequestContext,
    AuthResponseContext,
    build_auth_handler,
)

# =============================================================================
# 2. 配置模型 (Configuration Models)
# =============================================================================

class AuthConfig(BaseModel):
    """认证配置 (当前版本不需要认证，但保留扩展)"""
    type: str = Field(default="none", description="认证类型: none/basic/api_key/oauth2/bearer/session/request_signature/challenge_aware")
    username: Optional[str] = Field(None, description="Basic Auth 用户名")
    password: Optional[str] = Field(None, description="Basic Auth 密码")
    api_key: Optional[str] = Field(None, description="API Key")
    token: Optional[str] = Field(None, description="Bearer token")
    token_url: Optional[str] = Field(None, description="OAuth2 Token URL")
    expires_at: Optional[float] = Field(None, description="Token expiry unix timestamp")
    header_name: Optional[str] = Field(None, description="API key header name")
    param_name: Optional[str] = Field(None, description="API key query parameter name")
    cookies: Dict[str, str] = Field(default_factory=dict, description="Session cookies")
    session_headers: Dict[str, str] = Field(default_factory=dict, description="Session headers")
    signature_secret: Optional[str] = Field(None, description="Request signing secret")
    signature_header: str = Field(default="X-Signature", description="Signature header")
    timestamp_header: str = Field(default="X-Timestamp", description="Signature timestamp header")
    signature_algorithm: str = Field(default="sha256", description="Signature hash algorithm")
    challenge_provider: str = Field(default="disabled", description="Human-verification provider slot name")
    challenge_provider_config: Dict[str, Any] = Field(default_factory=dict, description="Provider-owned challenge configuration")

class RateLimitConfig(BaseModel):
    """限流配置"""
    requests_per_second: float = Field(default=10.0, ge=0.1, description="每秒请求数")
    burst_size: int = Field(default=10, ge=1, description="突发请求大小")
    enabled: bool = Field(default=True, description="是否启用限流")

class RateLimiter:
    """令牌桶限流器"""
    
    def __init__(self, rate: float, burst: int):
        self.rate = rate  # tokens per second
        self.burst = burst  # bucket size
        self.tokens = float(burst)
        self.last_refill = time.time()
    
    async def acquire(self):
        """获取令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return
        else:
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_refill = time.time()

class RetryConfig(BaseModel):
    """重试配置"""
    max_retries: int = Field(default=3, ge=0, description="最大重试次数")
    backoff_factor: float = Field(default=1.0, ge=0.1, description="退避因子")
    retry_on_status: Set[int] = Field(default={429, 500, 502, 503, 504}, description="需要重试的HTTP状态码")

class DataSourceConfig(BaseModel):
    """单个数据源配置"""
    name: str = Field(..., description="数据源名称，唯一标识")
    type: str = Field(..., description="数据源类型，对应 BaseDataSource 的 type_name")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=100, description="优先级，数字越小优先级越高")
    
    # 连接配置
    base_url: str = Field(..., description="基础URL")
    timeout: int = Field(default=30, ge=1, description="请求超时时间(秒)")
    
    # 可达性检测
    ping: bool = Field(default=True, description="启动时是否检测可达性")
    ping_endpoint: str = Field(default="", description="健康检查端点 (空则使用 base_url)")
    ping_timeout: int = Field(default=5, ge=1, le=30, description="可达性检测超时(秒)")
    auto_disable_on_fail: bool = Field(default=True, description="可达性检测失败时是否自动禁用")
    
    # 可选配置
    description: Optional[str] = Field(None, description="数据源描述")
    headers: Dict[str, str] = Field(default_factory=dict, description="默认请求头")
    params: Dict[str, Any] = Field(default_factory=dict, description="默认查询参数")
    auth: AuthConfig = Field(default_factory=AuthConfig, description="认证配置")
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig, description="限流配置")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="重试配置")
    
    # 缓存配置
    cache_enabled: bool = Field(default=True, description="是否启用缓存")
    cache_ttl: int = Field(default=300, ge=0, description="缓存有效期(秒)")
    
    # 连接池配置
    pool_size: int = Field(default=10, ge=1, description="连接池大小")
    pool_ttl: int = Field(default=60, ge=10, description="连接池连接存活时间(秒)")
    
    # 自定义配置 (各数据源可扩展)
    custom: Dict[str, Any] = Field(default_factory=dict, description="自定义配置项")
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        if not v:
            raise ValueError("数据源类型不能为空")
        return v.lower()
    
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        return _validate_http_url(v, 'base_url')

    @field_validator('ping_endpoint')
    @classmethod
    def validate_ping_endpoint(cls, v: str) -> str:
        return _validate_http_url(v, 'ping_endpoint', allow_empty=True)

    @field_validator('headers')
    @classmethod
    def validate_headers(cls, v: Dict[str, str]) -> Dict[str, str]:
        return _validate_headers(v, 'headers')

class MultiDataSourceConfig(BaseModel):
    """多数据源总配置"""
    version: str = Field(default="2.0", description="配置文件版本")
    sources: List[DataSourceConfig] = Field(..., description="数据源列表")
    
    @field_validator('sources')
    @classmethod
    def validate_sources(cls, v: List[DataSourceConfig]) -> List[DataSourceConfig]:
        names = [s.name for s in v]
        if len(names) != len(set(names)):
            raise ValueError("数据源名称必须唯一")
        return v

# =============================================================================
# 3. 查询结果模型 (Query Result Models)
# =============================================================================

@dataclass
class StandardizedRecord:
    """Unified evidence-friendly record emitted by every data source."""

    source_name: str
    source_type: str
    entity: str = ""
    title: str = ""
    summary: str = ""
    url: str = ""
    published_at: Optional[str] = None
    retrieved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence: float = 0.5
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    registered_address: str = ""
    headquarters_address: str = ""
    registration_authority: str = ""
    jurisdiction: str = ""
    lei: str = ""
    source_hint: str = ""
    entity_match: Dict[str, Any] = field(default_factory=dict)
    risk_events: List[Dict[str, Any]] = field(default_factory=list)
    risk_category: str = ""
    risk_level: str = ""
    severity: str = ""
    raw: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "entity": self.entity,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "entities": self.entities,
            "registered_address": self.registered_address,
            "headquarters_address": self.headquarters_address,
            "registration_authority": self.registration_authority,
            "jurisdiction": self.jurisdiction,
            "lei": self.lei,
            "source_hint": self.source_hint,
            "entity_match": self.entity_match,
            "risk_events": self.risk_events,
            "risk_category": self.risk_category,
            "risk_level": self.risk_level,
            "severity": self.severity,
            "raw": self.raw,
        }


@dataclass
class HealthReport:
    """Structured connectivity report for datasource routing and UI diagnostics."""

    source_name: str
    source_type: str
    ok: bool
    status: str
    endpoint: str
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    latency_ms: float = 0.0
    http_status: Optional[int] = None
    detail: str = ""
    error_type: str = ""
    auth_challenge: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "ok": self.ok,
            "status": self.status,
            "endpoint": self.endpoint,
            "checked_at": self.checked_at,
            "latency_ms": round(self.latency_ms, 2),
            "http_status": self.http_status,
            "detail": self.detail,
            "error_type": self.error_type,
            "auth_challenge": self.auth_challenge,
        }


def _first_text(payload: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def standardize_records(
    data: Any,
    source_name: str,
    source_type: str,
    query: str = "",
) -> List[StandardizedRecord]:
    """Map arbitrary connector output into the internal intelligence record."""
    if data is None:
        return []

    if isinstance(data, StandardizedRecord):
        return [data]

    if isinstance(data, dict):
        existing = data.get("standardized_records")
        if isinstance(existing, list):
            records: List[StandardizedRecord] = []
            for item in existing:
                if isinstance(item, StandardizedRecord):
                    records.append(item)
                elif isinstance(item, dict):
                    record_fields = {
                        key: value
                        for key, value in item.items()
                        if key in {
                            "entity", "title", "summary", "url", "published_at",
                            "retrieved_at", "confidence", "evidence", "raw",
                            "risk_events", "risk_category", "risk_level",
                            "severity", "source_hint", "entity_match",
                            "entities", "registered_address",
                            "headquarters_address", "registration_authority",
                            "jurisdiction", "lei",
                        }
                    }
                    records.append(
                        StandardizedRecord(
                            source_name=str(item.get("source_name", source_name)),
                            source_type=str(item.get("source_type", source_type)),
                            **record_fields,
                        )
                    )
            return records

        for key in ("data", "results", "items", "content", "records", "list"):
            if isinstance(data.get(key), list):
                return standardize_records(data[key], source_name, source_type, query)

    items = data if isinstance(data, list) else [data]
    records = []

    for item in items:
        if isinstance(item, StandardizedRecord):
            records.append(item)
            continue

        if isinstance(item, dict):
            title = _first_text(item, ("title", "headline", "subject", "name"))
            entity = _first_text(item, ("entity", "company", "company_name", "companyName", "name", "legal_name"))
            summary = _first_text(item, ("summary", "description", "desc", "content", "abstract", "snippet"))
            url = _first_text(item, ("url", "link", "source_url", "sourceUrl", "href"))
            published_at = _first_text(item, ("published_at", "publish_time", "publishTime", "date", "time", "created_at"))
            confidence_value = item.get("confidence", item.get("score", 0.5))
            evidence = item.get("evidence", [])
        else:
            title = str(item)
            entity = query
            summary = str(item)
            url = ""
            published_at = ""
            confidence_value = 0.3
            evidence = []

        try:
            confidence = max(0.0, min(1.0, float(confidence_value)))
        except (TypeError, ValueError):
            confidence = 0.5

        if not isinstance(evidence, list):
            evidence = [{"value": evidence}]

        records.append(
            StandardizedRecord(
                source_name=source_name,
                source_type=source_type,
                entity=entity or query,
                title=title or entity or query,
                summary=summary,
                url=url,
                published_at=published_at or None,
                confidence=confidence,
                evidence=evidence,
                raw=item,
            )
        )

    return records


@dataclass
class QueryResult(Generic[T]):
    """
    查询结果封装类
    
    泛型设计，支持不同类型的结果数据
    """
    source_name: str                           # 数据源名称
    source_type: str                           # 数据源类型
    status: QueryStatus                        # 查询状态
    
    # 结果数据
    data: Optional[T] = None                  # 成功时的数据
    error: Optional[Exception] = None          # 失败时的错误
    
    # 元数据
    query_time: float = 0.0                   # 查询耗时(秒)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_success(self) -> bool:
        return self.status == QueryStatus.SUCCESS
    
    @property
    def is_failed(self) -> bool:
        return self.status == QueryStatus.FAILED
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "status": self.status.value,
            "data": self.data,
            "error": str(self.error) if self.error else None,
            "query_time": self.query_time,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

@dataclass
class AggregatedResult(Generic[T]):
    """
    聚合查询结果
    
    包含多个数据源的查询结果
    """
    results: List[QueryResult[T]]             # 各数据源的结果
    successful_count: int = 0                  # 成功数量
    failed_count: int = 0                      # 失败数量
    total_time: float = 0.0                   # 总耗时
    
    def __post_init__(self):
        self.successful_count = sum(1 for r in self.results if r.is_success)
        self.failed_count = len(self.results) - self.successful_count
        if self.results:
            self.total_time = max(r.query_time for r in self.results)
    
    @property
    def is_all_success(self) -> bool:
        return self.failed_count == 0
    
    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.successful_count / len(self.results)
    
    def get_successful_data(self) -> List[T]:
        """获取所有成功的结果数据"""
        return [r.data for r in self.results if r.is_success and r.data is not None]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "total_time": self.total_time,
            "success_rate": self.success_rate,
            "is_all_success": self.is_all_success
        }

# =============================================================================
# 4. 查询请求模型 (Query Request Models)
# =============================================================================

@dataclass
class QueryRequest:
    """
    查询请求
    
    封装查询参数，支持灵活查询
    """
    query: str                                # 查询字符串
    params: Dict[str, Any] = field(default_factory=dict)  # 查询参数
    headers: Dict[str, str] = field(default_factory=dict) # 额外请求头
    timeout: Optional[int] = None             # 覆盖默认超时
    filters: List[Dict[str, Any]] = field(default_factory=list)  # 过滤条件
    sort: Optional[Dict[str, Any]] = None    # 排序条件
    pagination: Optional[Dict[str, Any]] = None
    def __post_init__(self):
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError('query cannot be empty')
        if len(self.query) > _MAX_QUERY_LENGTH:
            raise ValueError('query is too long')
        if (
            '..' in self.query
            or self.query.startswith('/')
            or self.query.startswith('//')
            or '://' in self.query
            or '\\' in self.query
            or '?' in self.query
            or '\r' in self.query
            or '\n' in self.query
        ):
            raise ValueError('query contains an unsafe path shape')
        self.headers = _validate_headers(self.headers, 'headers')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "params": self.params,
            "headers": self.headers,
            "timeout": self.timeout,
            "filters": self.filters,
            "sort": self.sort,
            "pagination": self.pagination
        }
    
    def cache_key(self) -> str:
        """生成缓存键"""
        content = {
            "query": self.query,
            "params": self.params,
            "filters": self.filters,
            "sort": self.sort,
            "pagination": self.pagination
        }
        return hashlib.md5(
            json.dumps(content, sort_keys=True).encode('utf-8')
        ).hexdigest()

# =============================================================================
# 5. 缓存机制 (Cache Mechanism)
# =============================================================================

class QueryCache:
    """
    查询结果缓存
    
    支持 TTL 过期、LRU 淘汰、线程安全
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认 TTL (秒)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Tuple[Any, datetime]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的数据，未命中返回 None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            data, expire_time = self._cache[key]
            
            # Check if expired
            if datetime.now() > expire_time:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return data
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存数据
            ttl: 存活时间(秒)，None 使用默认值
        """
        with self._lock:
            expire_time = datetime.now() + timedelta(seconds=ttl or self.default_ttl)
            
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # Check if need to evict
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)  # Remove LRU
            
            self._cache[key] = (value, expire_time)
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "max_size": self.max_size
            }

# =============================================================================
# 6. 核心抽象类 (Core Abstract Classes)
# =============================================================================

class BaseDataSource(ABC):
    """
    数据源抽象基类
    
    所有数据源必须继承此类并实现抽象方法
    
    设计模式:
    - Template Method: 定义查询流程骨架
    - Strategy: 允许运行时切换数据源
    - Factory Method: 子类决定具体实现
    """
    
    # 类属性: 数据源类型名称 (子类必须覆盖)
    type_name: str = "base"
    
    def __init__(self, config: DataSourceConfig):
        """
        初始化数据源
        
        Args:
            config: 数据源配置
        """
        self.config = config
        self.name = config.name
        self.logger = logging.getLogger(f"datasource.{self.name}")
        self._validate_config()
    
    def _validate_config(self) -> None:
        """
        验证配置
        
        子类可以覆盖此方法添加自定义验证
        """
        if not self.config.base_url:
            raise ConfigError(f"数据源 {self.name} 的 base_url 未配置")
    
    # =========================================================================
    # 抽象方法 (必须由子类实现)
    # =========================================================================
    
    @abstractmethod
    async def _do_query(self, request: QueryRequest) -> Any:
        """
        执行 REST API 查询

        Args:
            request: 查询请求

        Returns:
            API 响应数据
        """
        session = await self._get_session()
        url = f"{self.config.base_url}/{request.query.lstrip('/')}"
        params = {**self.config.params, **request.params}
        headers = {**self.config.headers, **request.headers}

        async with session.get(url, params=params, headers=headers) as response:
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if 'json' not in content_type and 'text/' not in content_type:
                self.logger.warning(f"未知的 Content-Type: {content_type}")

            if response.content_length and response.content_length > _MAX_RESPONSE_SIZE:
                raise QueryError(f"响应体过大: {response.content_length} bytes")

            try:
                return await response.json()
            except Exception as exc:
                self.logger.error(f"响应解析失败: {type(exc).__name__}")
                raise QueryError('响应解析失败') from exc
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            数据源是否健康
        """
        pass
    
    @abstractmethod
    def format_result(self, raw_data: Any) -> Any:
        """
        格式化结果
        
        将原始数据转换为统一格式
        
        Args:
            raw_data: 原始数据
            
        Returns:
            格式化后的数据
        """
        pass
    
    # =========================================================================
    # 模板方法 (定义查询流程)
    # =========================================================================
    
    async def query(self, request: QueryRequest) -> QueryResult[Any]:
        """
        执行查询 (模板方法)
        
        定义查询流程骨架:
        1. 前置处理
        2. 执行查询
        3. 结果格式化
        4. 后置处理
        
        Args:
            request: 查询请求
            
        Returns:
            查询结果
        """
        start_time = time.time()
        
        try:
            # 1. 前置处理 (可覆盖)
            await self._pre_query(request)
            
            # 2. 执行查询 (带重试)
            raw_data = await self._execute_with_retry(request)
            
            # 3. 结果格式化
            formatted_data = self.format_result(raw_data)
            
            # 4. 后置处理 (可覆盖)
            final_data = await self._post_query(formatted_data, request)
            
            query_time = time.time() - start_time
            
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.SUCCESS,
                data=final_data,
                query_time=query_time,
                metadata={
                    "request": request.to_dict(),
                    "standardized_records": [
                        record.to_dict()
                        for record in standardize_records(
                            final_data,
                            self.name,
                            self.type_name,
                            request.query,
                        )
                    ],
                }
            )
            
        except asyncio.TimeoutError:
            query_time = time.time() - start_time
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.TIMEOUT,
                error=QueryError(f"查询超时 ({self.config.timeout}秒)"),
                query_time=query_time
            )
            
        except AuthChallengeRequired as e:
            query_time = time.time() - start_time
            self.logger.warning("authentication challenge required: %s", e.challenge_type)
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.FAILED,
                error=QueryError("authentication challenge requires user authorization or configured provider"),
                query_time=query_time,
                metadata={
                    "auth_challenge": {
                        "type": e.challenge_type,
                        "source": e.source,
                        "details": e.details,
                    }
                },
            )
            
        except Exception as e:
            query_time = time.time() - start_time
            # SECURITY FIX F-002: Don't expose raw errors in logs
            safe_error = type(e).__name__
            self.logger.error(f"查询失败: {safe_error}")
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.FAILED,
                error=QueryError("查询执行失败"),  # Don't expose original error
                query_time=query_time
            )
    
    async def _execute_with_retry(self, request: QueryRequest) -> Any:
        """
        带重试的查询执行
        
        Args:
            request: 查询请求
            
        Returns:
            查询结果
        """
        retry_config = self.config.retry
        last_error = None
        timeout_seconds = request.timeout or self.config.timeout
        
        for attempt in range(retry_config.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._do_query(request),
                    timeout=timeout_seconds
                )
            except Exception as e:
                last_error = e
                if attempt < retry_config.max_retries:
                    # SECURITY FIX F-008: Add random jitter to prevent DoS
                    wait_time = retry_config.backoff_factor * (2 ** attempt)
                    jitter = random.uniform(0, wait_time * 0.5)
                    actual_wait = wait_time + jitter
                    # Don't expose raw error in logs
                    safe_error = type(e).__name__
                    self.logger.debug(
                        "query retry scheduled: source=%s wait_seconds=%.2f attempt=%s/%s error_type=%s",
                        self.name,
                        actual_wait,
                        attempt + 1,
                        retry_config.max_retries + 1,
                        safe_error,
                    )
                    await asyncio.sleep(actual_wait)
                else:
                    raise
        
        raise last_error  # type: ignore
    
    # =========================================================================
    # Hook 方法 (子类可选择覆盖)
    # =========================================================================
    
    async def _pre_query(self, request: QueryRequest) -> None:
        """
        查询前置处理
        
        子类可以覆盖此方法添加自定义逻辑
        """
        pass
    
    async def _post_query(self, data: Any, request: QueryRequest) -> Any:
        """
        查询后置处理
        
        子类可以覆盖此方法添加自定义逻辑
        """
        return data
    
    # =========================================================================
    # 工具方法
    # =========================================================================
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, type={self.type_name})"
    
    def __repr__(self) -> str:
        return self.__str__()

# =============================================================================
# 7. REST API 数据源实现 (REST API Data Source Implementation)
# =============================================================================

class RestApiDataSource(BaseDataSource):
    """
    RESTful API 数据源实现
    
    支持标准 REST API 查询
    """
    
    type_name: str = "rest_api"
    
    def __init__(self, config: DataSourceConfig):
        super().__init__(config)
        self._session: Optional[Any] = None  # aiohttp.ClientSession
        self._auth_handler = build_auth_handler(config.auth)
        self._current_query_hint = ""
        # SECURITY FIX F-012: Initialize rate limiter
        if config.rate_limit.enabled:
            self._rate_limiter = RateLimiter(
                rate=config.rate_limit.requests_per_second,
                burst=config.rate_limit.burst_size
            )
        else:
            self._rate_limiter = None

    def _prepare_provider_request(self, request: QueryRequest) -> Tuple[str, Dict[str, Any]]:
        """Map provider-specific public APIs from a subject query to endpoint/params."""
        provider_type = str(self.config.custom.get("provider_type", ""))
        query = request.query.strip()
        params = {**self.config.params, **request.params}

        if provider_type == "gleif_lei":
            endpoint = "lei-records"
            provider_params = {
                key: value
                for key, value in params.items()
                if key.startswith("filter[") or key.startswith("page[")
            }
            provider_params.setdefault("filter[entity.legalName]", query)
            provider_params.setdefault("page[size]", 5)
            return endpoint, provider_params

        if provider_type == "sec_edgar":
            cik = str(request.params.get("cik", "")).strip()
            if cik and str(request.params.get("sec_endpoint") or "") == "companyfacts":
                normalized_cik = cik.zfill(10)
                return f"api/xbrl/companyfacts/CIK{normalized_cik}.json", {
                    key: value
                    for key, value in params.items()
                    if key not in {"cik", "company", "domain", "objective", "sec_endpoint"}
                }
            if cik:
                normalized_cik = cik.zfill(10)
                return f"submissions/CIK{normalized_cik}.json", {
                    key: value
                    for key, value in params.items()
                    if key not in {"cik", "company", "domain", "objective"}
                }
            return "https://www.sec.gov/files/company_tickers.json", {}

        if provider_type == "opensanctions_dataset_catalog":
            return "datasets/latest/index.json", {}

        if provider_type == "idb_sanctioned_firms_dataset_catalog":
            return "dataset/dataset-of-sanctioned-firms-and-individuals", {}

        if provider_type == "world_bank_debarred_firms":
            return "en/projects-operations/procurement/debarred-firms", {}

        if provider_type == "wikidata_entity_search":
            if str(params.get("wikidata_endpoint") or "") == "entitydata":
                qid = str(params.get("wikidata_id") or params.get("qid") or "").strip()
                if not re.fullmatch(r"Q\d+", qid):
                    raise QueryError("invalid Wikidata entity id")
                return f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json", {
                    key: value
                    for key, value in params.items()
                    if key not in {"wikidata_endpoint", "wikidata_id", "qid", "company", "domain", "objective"}
                }
            return "api.php", {
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "uselang": "en",
                "limit": 10,
                "search": query,
            }

        if provider_type == "ofac_consolidated_xml":
            return "consolidated.xml", {}

        if provider_type == "un_sc_consolidated_sanctions_xml":
            return "resources/xml/en/consolidated.xml", {}

        if provider_type == "official_portal_catalog":
            return "", {}

        return query, params

    def _format_gleif_result(self, raw_data: Any) -> Dict[str, Any]:
        data = raw_data.get("data", []) if isinstance(raw_data, dict) else []
        records: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            attributes = item.get("attributes", {}) or {}
            entity = attributes.get("entity", {}) or {}
            legal_name = (entity.get("legalName", {}) or {}).get("name", "")
            registration = entity.get("registeredAt", {}) or {}
            status = attributes.get("registration", {}) or {}
            registered_address = self._format_gleif_address(entity.get("legalAddress"))
            headquarters_address = self._format_gleif_address(entity.get("headquartersAddress"))
            jurisdiction = str(entity.get("jurisdiction") or "").strip()
            registration_authority = str(registration.get("id") or "").strip()
            lei = item.get("id", "")
            relationship_entities = self._gleif_relationship_entities(item, attributes, entity)
            summary_parts = [
                f"LEI={lei}" if lei else "",
                f"status={status.get('status', '')}" if status.get("status") else "",
                f"registration_authority={registration_authority}" if registration_authority else "",
                f"jurisdiction={jurisdiction}" if jurisdiction else "",
                f"registered_address={registered_address}" if registered_address else "",
                f"headquarters_address={headquarters_address}" if headquarters_address else "",
                "relationships="
                + ", ".join(
                    f"{related['relation']}:{related['name']}"
                    for related in relationship_entities[:6]
                ) if relationship_entities else "",
            ]
            entities: List[Dict[str, Any]] = []
            if registered_address:
                entities.append({
                    "kind": "address",
                    "name": registered_address,
                    "relation": "registered_address",
                    "confidence": 0.82,
                    "source": "GLEIF",
                })
            if headquarters_address and headquarters_address != registered_address:
                entities.append({
                    "kind": "address",
                    "name": headquarters_address,
                    "relation": "headquarters_address",
                    "confidence": 0.8,
                    "source": "GLEIF",
                })
            entities.extend(relationship_entities)
            evidence = [
                {
                    "type": "official_public_api",
                    "provider": "GLEIF",
                    "lei": lei,
                    "registration_authority": registration_authority,
                    "jurisdiction": jurisdiction,
                    "registered_address": registered_address,
                    "headquarters_address": headquarters_address,
                }
            ]
            for related in relationship_entities:
                evidence.append(
                    {
                        "type": "official_public_api_relation",
                        "provider": "GLEIF",
                        "relation": related.get("relation"),
                        "name": related.get("name"),
                        "lei": related.get("lei", ""),
                    }
                )
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "entity": legal_name or lei,
                "title": f"GLEIF LEI record: {legal_name or lei}",
                "summary": "; ".join(part for part in summary_parts if part).strip(),
                "url": f"https://search.gleif.org/#/record/{lei}" if lei else "",
                "confidence": 0.86,
                "lei": lei,
                "registered_address": registered_address,
                "headquarters_address": headquarters_address,
                "registration_authority": registration_authority,
                "jurisdiction": jurisdiction,
                "entities": entities,
                "evidence": evidence,
                "raw": item,
            })
        return {"standardized_records": records, "raw": raw_data}

    @classmethod
    def _gleif_relationship_entities(
        cls,
        item: Dict[str, Any],
        attributes: Dict[str, Any],
        entity: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        related: List[Dict[str, Any]] = []

        def add(raw: Any, relation: str) -> None:
            payload = raw if isinstance(raw, dict) else {}
            name = cls._gleif_related_name(payload)
            lei = str(
                payload.get("lei")
                or payload.get("id")
                or payload.get("relatedLei")
                or payload.get("relatedEntityLei")
                or ""
            ).strip()
            if not name and lei:
                name = lei
            if not name:
                return
            related.append(
                {
                    "kind": "company",
                    "name": name,
                    "relation": relation,
                    "confidence": 0.76,
                    "source": "GLEIF",
                    "lei": lei,
                }
            )

        for container in (entity, attributes, item):
            if not isinstance(container, dict):
                continue
            add(container.get("directParent"), "direct_parent")
            add(container.get("ultimateParent"), "ultimate_parent")
            add(container.get("parent"), "parent_organization")
            relationships = container.get("relationships")
            if isinstance(relationships, dict):
                relationships = relationships.get("data") or relationships.get("relationships") or []
            if not isinstance(relationships, list):
                continue
            for relationship in relationships:
                if not isinstance(relationship, dict):
                    continue
                raw_type = str(
                    relationship.get("relationshipType")
                    or relationship.get("type")
                    or relationship.get("relation")
                    or ""
                ).lower()
                relation = "parent_organization"
                if "ultimate" in raw_type:
                    relation = "ultimate_parent"
                elif "direct" in raw_type:
                    relation = "direct_parent"
                target = (
                    relationship.get("related")
                    or relationship.get("relatedEntity")
                    or relationship.get("target")
                    or relationship
                )
                add(target, relation)

        deduped: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in related:
            key = (str(row.get("relation") or ""), str(row.get("name") or "").casefold())
            deduped.setdefault(key, row)
        return list(deduped.values())

    @staticmethod
    def _gleif_related_name(payload: Dict[str, Any]) -> str:
        legal_name = payload.get("legalName")
        if isinstance(legal_name, dict):
            value = legal_name.get("name") or legal_name.get("value")
            if value:
                return str(value).strip()
        return str(
            payload.get("name")
            or payload.get("legalName")
            or payload.get("entityName")
            or payload.get("relatedEntityName")
            or ""
        ).strip()

    @staticmethod
    def _format_gleif_address(raw_address: Any) -> str:
        if not isinstance(raw_address, dict):
            return ""
        parts: List[str] = []
        for line in raw_address.get("addressLines") or []:
            text = str(line or "").strip()
            if text:
                parts.append(text)
        for key in ("city", "region", "postalCode", "country"):
            text = str(raw_address.get(key) or "").strip()
            if text:
                parts.append(text)
        deduped: List[str] = []
        seen = set()
        for part in parts:
            marker = part.lower()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(part)
        return ", ".join(deduped)

    async def query(self, request: QueryRequest) -> QueryResult[Any]:
        """Execute a REST query with structured, sanitized diagnostics."""
        start_time = time.time()

        try:
            await self._pre_query(request)
            self._current_query_hint = request.query
            raw_data = await self._execute_with_retry(request)
            formatted_data = self.format_result(raw_data)
            final_data = await self._post_query(formatted_data, request)
            query_time = time.time() - start_time

            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.SUCCESS,
                data=final_data,
                query_time=query_time,
                metadata={
                    "request": request.to_dict(),
                    "standardized_records": [
                        record.to_dict()
                        for record in standardize_records(
                            final_data,
                            self.name,
                            self.type_name,
                            request.query,
                        )
                    ],
                },
            )

        except asyncio.TimeoutError:
            query_time = time.time() - start_time
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.TIMEOUT,
                error=QueryError("query timed out"),
                query_time=query_time,
                metadata={
                    "request": request.to_dict(),
                    "error_details": {
                        "type": "TimeoutError",
                        "timeout_seconds": self.config.timeout,
                    },
                },
            )

        except AuthChallengeRequired as exc:
            query_time = time.time() - start_time
            self.logger.warning("authentication challenge required: %s", exc.challenge_type)
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.FAILED,
                error=QueryError("authentication challenge requires user authorization or configured provider"),
                query_time=query_time,
                metadata={
                    "request": request.to_dict(),
                    "auth_challenge": {
                        "type": exc.challenge_type,
                        "source": exc.source,
                        "details": exc.details,
                    },
                    "error_details": _safe_exception_metadata(exc),
                },
            )

        except Exception as exc:
            query_time = time.time() - start_time
            self.logger.error("query failed: %s", type(exc).__name__)
            return QueryResult(
                source_name=self.name,
                source_type=self.type_name,
                status=QueryStatus.FAILED,
                error=QueryError("查询执行失败"),
                query_time=query_time,
                metadata={
                    "request": request.to_dict(),
                    "error_details": _safe_exception_metadata(exc),
                },
            )

    def _format_sec_result(self, raw_data: Any) -> Dict[str, Any]:
        if not isinstance(raw_data, dict):
            return {"standardized_records": [], "raw": raw_data}

        records: List[Dict[str, Any]] = []
        if "facts" in raw_data and ("entityName" in raw_data or "cik" in raw_data):
            return self._format_sec_companyfacts_result(raw_data)

        if "cik" in raw_data and "name" in raw_data:
            cik = str(raw_data.get("cik", "")).zfill(10)
            entity = str(raw_data.get("name", ""))
            filings = (raw_data.get("filings", {}) or {}).get("recent", {}) or {}
            forms = filings.get("form", []) or []
            filing_dates = filings.get("filingDate", []) or []
            accessions = filings.get("accessionNumber", []) or []
            key_people = self._sec_key_person_entities(raw_data)
            latest = [
                f"{form} {filing_date} {accession}".strip()
                for form, filing_date, accession in list(zip(forms, filing_dates, accessions))[:5]
            ]
            people_summary = ", ".join(
                f"{item['relation']}:{item['name']}" for item in key_people[:6]
            )
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": "sec_edgar_public_api",
                "entity": entity,
                "title": f"SEC EDGAR submissions: {entity}",
                "summary": "; ".join(
                    part for part in (
                        "; ".join(latest) or f"CIK={cik}",
                        f"key_people={people_summary}" if people_summary else "",
                    ) if part
                ),
                "url": f"https://www.sec.gov/edgar/browse/?CIK={cik}",
                "confidence": 0.84,
                "cik": cik,
                "entity_match": self._sec_entity_match(entity, cik),
                "entities": key_people,
                "evidence": [
                    {
                        "type": "official_public_api",
                        "provider": "SEC EDGAR",
                        "cik": cik,
                        "recent_filings_count": len(forms),
                        "key_people_count": len(key_people),
                    }
                ],
                "raw": raw_data,
            })
            return {"standardized_records": records, "raw": raw_data}

        query_hint = str(raw_data.get("_query", "")).lower()
        candidates = []
        for value in raw_data.values():
            if not isinstance(value, dict):
                continue
            title = str(value.get("title", ""))
            ticker = str(value.get("ticker", ""))
            if query_hint and query_hint not in title.lower() and query_hint != ticker.lower():
                continue
            candidates.append(value)

        for value in candidates[:10]:
            title = str(value.get("title", ""))
            cik = str(value.get("cik_str", "")).zfill(10)
            ticker = str(value.get("ticker", ""))
            if not title:
                continue
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": "sec_edgar_public_api",
                "entity": title,
                "title": f"SEC EDGAR company ticker match: {title}",
                "summary": f"ticker={ticker}; cik={cik}",
                "url": f"https://www.sec.gov/edgar/browse/?CIK={cik}" if cik else "",
                "confidence": 0.62,
                "evidence": [
                    {
                        "type": "official_public_api",
                        "provider": "SEC EDGAR",
                        "ticker": ticker,
                        "cik": cik,
                    }
                ],
                "raw": value,
            })
        return {"standardized_records": records, "raw": raw_data}

    @classmethod
    def _sec_key_person_entities(cls, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map structured SEC-derived person fields without inferring from filing prose."""
        if not isinstance(raw_data, dict):
            return []
        collection_relations = {
            "officers": "officer",
            "directors": "director",
            "executives": "executive",
            "insiders": "insider",
            "keyPeople": "key_person",
            "key_people": "key_person",
            "management": "management",
            "board": "director",
        }
        entities: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        cik = str(raw_data.get("cik") or "").zfill(10) if raw_data.get("cik") not in (None, "") else ""
        for field_name, fallback_relation in collection_relations.items():
            for item in cls._iter_sec_people(raw_data.get(field_name)):
                name = cls._sec_person_name(item)
                if not name:
                    continue
                title = cls._sec_person_title(item)
                relation = cls._sec_relation_from_role(fallback_relation, title)
                key = (name.casefold(), relation)
                if key in seen:
                    continue
                seen.add(key)
                payload: Dict[str, Any] = {
                    "kind": "person",
                    "name": name,
                    "relation": relation,
                    "confidence": 0.7 if title else 0.64,
                    "source": "SEC EDGAR",
                    "field": field_name,
                    "confidence_basis": "structured SEC public submission field",
                }
                if title:
                    payload["position"] = title
                if cik:
                    payload["cik"] = cik
                entities.append(payload)
        return entities

    @staticmethod
    def _iter_sec_people(raw_people: Any) -> List[Any]:
        if raw_people in (None, ""):
            return []
        if isinstance(raw_people, list):
            return raw_people
        if isinstance(raw_people, dict):
            for key in ("items", "people", "records", "data", "results"):
                nested = raw_people.get(key)
                if isinstance(nested, list):
                    return nested
            return list(raw_people.values()) if raw_people else []
        return [raw_people]

    @staticmethod
    def _sec_person_name(item: Any) -> str:
        if isinstance(item, str):
            return " ".join(item.split())
        if not isinstance(item, dict):
            return ""
        for key in (
            "name",
            "fullName",
            "personName",
            "reportingOwnerName",
            "officerName",
            "directorName",
            "individualName",
        ):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        parts = [
            str(item.get(key) or "").strip()
            for key in ("firstName", "middleName", "lastName")
            if str(item.get(key) or "").strip()
        ]
        return " ".join(parts)

    @staticmethod
    def _sec_person_title(item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        for key in ("title", "role", "officerTitle", "relationship", "position", "jobTitle"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    @staticmethod
    def _sec_relation_from_role(fallback: str, title: str) -> str:
        text = str(title or "").casefold()
        if "chief executive" in text or re.search(r"\bceo\b", text):
            return "chief_executive_officer"
        if "chief financial" in text or re.search(r"\bcfo\b", text):
            return "chief_financial_officer"
        if "chair" in text:
            return "chairperson"
        if "director" in text:
            return "director"
        if "president" in text:
            return "president"
        if "executive" in text:
            return "executive"
        if "officer" in text:
            return "officer"
        return fallback

    def _sec_entity_match(self, entity: str, cik: str = "") -> Dict[str, Any]:
        if not EntityResolutionScorer or not entity:
            return {}
        match = EntityResolutionScorer.score(self._current_query_hint, entity, {"cik": cik})
        query_norm = self._normalize_label_for_match(self._current_query_hint)
        entity_norm = self._normalize_label_for_match(entity)
        if cik and entity_norm and entity_norm in query_norm:
            upgraded = dict(match)
            upgraded["score"] = max(float(upgraded.get("score") or 0), 0.98)
            upgraded["level"] = "exact"
            reasons = list(upgraded.get("reasons") or [])
            reasons.append("SEC CIK endpoint returned a single official company record")
            upgraded["reasons"] = sorted(set(str(item) for item in reasons if item))
            return upgraded
        return match

    def _format_sec_companyfacts_result(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        entity = str(raw_data.get("entityName") or raw_data.get("name") or raw_data.get("cik") or "").strip()
        cik = str(raw_data.get("cik") or "").zfill(10) if raw_data.get("cik") is not None else ""
        facts = ((raw_data.get("facts") or {}).get("us-gaap") or {})
        metrics = {
            "revenue": self._sec_latest_fact(facts, ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")),
            "net_income": self._sec_latest_fact(facts, ("NetIncomeLoss",)),
            "operating_cash_flow": self._sec_latest_fact(facts, ("NetCashProvidedByUsedInOperatingActivities",)),
            "assets": self._sec_latest_fact(facts, ("Assets",)),
            "liabilities": self._sec_latest_fact(facts, ("Liabilities",)),
            "stockholders_equity": self._sec_latest_fact(facts, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
            "cash": self._sec_latest_fact(facts, ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")),
            "accounts_receivable": self._sec_latest_fact(facts, ("AccountsReceivableNetCurrent", "AccountsReceivableNet")),
            "inventory": self._sec_latest_fact(facts, ("InventoryNet",)),
        }
        present = {key: value for key, value in metrics.items() if value is not None}
        if not entity and not present:
            return {"standardized_records": [], "raw": raw_data}

        revenue = self._fact_value(metrics["revenue"])
        net_income = self._fact_value(metrics["net_income"])
        operating_cash_flow = self._fact_value(metrics["operating_cash_flow"])
        assets = self._fact_value(metrics["assets"])
        liabilities = self._fact_value(metrics["liabilities"])
        equity = self._fact_value(metrics["stockholders_equity"])
        net_margin = self._safe_ratio(net_income, revenue)
        cash_conversion = self._safe_ratio(operating_cash_flow, net_income)
        debt_to_assets = self._safe_ratio(liabilities, assets)
        debt_to_equity = self._safe_ratio(liabilities, equity)
        risk_events: List[Dict[str, Any]] = []
        warnings: List[str] = []
        if net_income and net_income > 0 and cash_conversion is not None and cash_conversion < 0.5:
            warnings.append("SEC companyfacts: earnings cash conversion is weak")
        if operating_cash_flow is not None and operating_cash_flow < 0:
            warnings.append("SEC companyfacts: operating cash flow is negative")
        if debt_to_assets is not None and debt_to_assets > 0.75:
            warnings.append("SEC companyfacts: liabilities/assets is elevated")
        if warnings:
            risk_events.append({
                "category": "financing_capital_markets",
                "severity": "medium",
                "title": "SEC companyfacts financial-quality signal",
                "summary": "; ".join(warnings),
                "confidence": 0.72,
                "status": "open",
            })
        summary_parts = [
            f"cik={cik}" if cik else "",
            self._sec_metric_text("revenue", metrics["revenue"]),
            self._sec_metric_text("net_income", metrics["net_income"]),
            self._sec_metric_text("operating_cash_flow", metrics["operating_cash_flow"]),
            f"net_margin={net_margin:.4f}" if net_margin is not None else "",
            f"cash_conversion={cash_conversion:.4f}" if cash_conversion is not None else "",
            f"debt_to_assets={debt_to_assets:.4f}" if debt_to_assets is not None else "",
        ]
        record = {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": "sec_edgar_public_api",
            "entity": entity,
            "title": f"SEC EDGAR company facts: {entity or cik}",
            "summary": "; ".join(part for part in summary_parts if part),
            "url": f"https://www.sec.gov/edgar/browse/?CIK={cik}" if cik else "https://data.sec.gov/api/xbrl/companyfacts/",
            "confidence": 0.78,
            "entity_match": self._sec_entity_match(entity, cik),
            "risk_events": risk_events,
            "evidence": [
                {
                    "type": "official_public_api",
                    "provider": "SEC EDGAR companyfacts",
                    "cik": cik,
                    "revenue": revenue,
                    "net_income": net_income,
                    "operating_cash_flow": operating_cash_flow,
                    "net_margin": net_margin,
                    "cash_conversion": cash_conversion,
                    "debt_to_assets": debt_to_assets,
                    "debt_to_equity": debt_to_equity,
                }
            ],
            "raw": {
                "cik": cik,
                "entityName": entity,
                "metrics": present,
                "ratios": {
                    "net_margin": net_margin,
                    "cash_conversion": cash_conversion,
                    "debt_to_assets": debt_to_assets,
                    "debt_to_equity": debt_to_equity,
                },
            },
        }
        return {"standardized_records": [record], "raw": record["raw"]}

    @staticmethod
    def _sec_latest_fact(facts: Dict[str, Any], keys: tuple[str, ...]) -> Dict[str, Any] | None:
        candidates: List[Dict[str, Any]] = []
        for key in keys:
            fact = facts.get(key)
            units = fact.get("units") if isinstance(fact, dict) else None
            if not isinstance(units, dict):
                continue
            for unit, unit_values in units.items():
                if isinstance(unit_values, list):
                    for item in unit_values:
                        if isinstance(item, dict) and item.get("val") is not None:
                            latest = dict(item)
                            latest["concept"] = key
                            latest["unit"] = str(unit)
                            candidates.append(latest)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                str(item.get("end") or ""),
                str(item.get("filed") or ""),
                str(item.get("form") or ""),
                str(item.get("concept") or ""),
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _fact_value(fact: Dict[str, Any] | None) -> float | None:
        if not fact:
            return None
        try:
            return float(fact.get("val"))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _sec_metric_text(cls, label: str, fact: Dict[str, Any] | None) -> str:
        if not fact:
            return ""
        value = cls._fact_value(fact)
        if value is None:
            return ""
        suffix = f" end={fact.get('end')}" if fact.get("end") else ""
        return f"{label}={value:g}{suffix}"

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator

    def _format_opensanctions_catalog_result(self, raw_data: Any) -> Dict[str, Any]:
        if not isinstance(raw_data, dict):
            return {"standardized_records": [], "raw": raw_data}

        datasets = raw_data.get("datasets", raw_data.get("data", raw_data))
        if isinstance(datasets, dict):
            iterable = datasets.values()
        elif isinstance(datasets, list):
            iterable = datasets
        else:
            iterable = []

        records: List[Dict[str, Any]] = []
        for item in iterable:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or "").strip()
            title = str(item.get("title") or name).strip()
            category = str(item.get("category") or item.get("type") or "").strip()
            summary = str(item.get("summary") or item.get("description") or "").strip()
            if not name and not title:
                continue
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "entity": title or name,
                "title": f"OpenSanctions dataset coverage: {title or name}",
                "summary": "; ".join(
                    part for part in (f"name={name}" if name else "", f"category={category}" if category else "", summary)
                    if part
                ),
                "url": str(item.get("url") or f"https://www.opensanctions.org/datasets/{quote(name)}/" if name else ""),
                "confidence": 0.58,
                "evidence": [
                    {
                        "type": "public_dataset_catalog",
                        "provider": "OpenSanctions",
                        "dataset": name,
                        "category": category,
                    }
                ],
                "raw": item,
            })
        return {"source_catalog_records": records[:20], "standardized_records": [], "raw": raw_data}

    def _format_idb_sanctioned_firms_catalog_result(self, raw_data: Any) -> Dict[str, Any]:
        if not isinstance(raw_data, str) or not raw_data.strip():
            return {"source_catalog_records": [], "standardized_records": [], "raw": raw_data}

        text = raw_data[:200000]
        title = self._html_meta(text, "citation_title") or "Dataset of Sanctioned firms and individuals"
        publisher = self._html_meta(text, "citation_publisher") or "IADB"
        doi = self._html_meta(text, "citation_doi")
        online_date = self._html_meta(text, "citation_online_date")
        description = self._html_meta(text, "description")
        resource_url = self._html_meta(text, "citation_public_url")
        source_url = resource_url or _join_endpoint(
            self.config.base_url,
            "dataset/dataset-of-sanctioned-firms-and-individuals",
        )
        summary_parts = [
            f"publisher={publisher}",
            f"doi={doi}" if doi else "",
            f"online_date={online_date}" if online_date else "",
            description or "",
        ]
        record = {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": self.name,
            "entity": title,
            "title": f"IDB sanctions dataset coverage: {title}",
            "summary": "; ".join(part for part in summary_parts if part),
            "url": source_url,
            "confidence": 0.6,
            "evidence": [
                {
                    "type": "public_dataset_catalog",
                    "provider": publisher,
                    "dataset": title,
                    "doi": doi,
                    "online_date": online_date,
                }
            ],
            "raw": {
                "title": title,
                "publisher": publisher,
                "doi": doi,
                "online_date": online_date,
                "description": description,
                "url": source_url,
            },
        }
        return {
            "source_catalog_records": [record],
            "standardized_records": [],
            "raw": record["raw"],
        }

    def _format_world_bank_debarred_firms_result(self, raw_data: Any, *, query: str = "") -> Dict[str, Any]:
        if not isinstance(raw_data, str) or not raw_data.strip():
            return {"source_catalog_records": [], "standardized_records": [], "raw": raw_data}

        text = raw_data[:500000]
        rows = self._html_table_rows(text)
        records: List[Dict[str, Any]] = []
        parsed_count = 0
        for row in rows:
            cells = [self._clean_html_text(cell) for cell in row]
            cells = [cell for cell in cells if cell]
            if len(cells) < 2:
                continue
            row_text = " | ".join(cells)
            if "firm name" in row_text.lower() or "address" in row_text.lower() and "country" in row_text.lower():
                continue
            parsed_count += 1
            firm_name = cells[0]
            match = EntityResolutionScorer.score(query, firm_name, {"source": "world_bank_debarred_firms"}) if EntityResolutionScorer and query else {}
            if str(match.get("level") or "") not in {"exact", "strong"}:
                continue
            address = cells[1] if len(cells) > 1 else ""
            country = cells[2] if len(cells) > 2 else ""
            from_date = cells[3] if len(cells) > 3 else ""
            to_date = cells[4] if len(cells) > 4 else ""
            grounds = cells[5] if len(cells) > 5 else ""
            summary = "; ".join(
                part
                for part in (
                    f"country={country}" if country else "",
                    f"address={address}" if address else "",
                    f"from={from_date}" if from_date else "",
                    f"to={to_date}" if to_date else "",
                    f"grounds={grounds}" if grounds else "",
                )
                if part
            )
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": self.name,
                "entity": firm_name,
                "title": f"World Bank debarred firm listing: {firm_name}",
                "summary": summary,
                "url": _join_endpoint(self.config.base_url, "en/projects-operations/procurement/debarred-firms"),
                "confidence": 0.82,
                "registered_address": address,
                "jurisdiction": country,
                "entity_match": match,
                "entities": [
                    {
                        "kind": "address",
                        "name": address,
                        "relation": "listed_address",
                        "confidence": 0.72,
                        "source": "World Bank",
                    }
                ] if address else [],
                "risk_events": [
                    {
                        "category": "administrative_risk",
                        "severity": "high",
                        "title": "World Bank procurement debarment listing",
                        "summary": summary or "The subject appears in the World Bank public debarred firms list.",
                        "confidence": 0.82,
                        "status": "open",
                    }
                ],
                "evidence": [
                    {
                        "type": "official_public_dataset",
                        "provider": "World Bank",
                        "dataset": "Debarred Firms and Individuals",
                        "country": country,
                        "from_date": from_date,
                        "to_date": to_date,
                        "grounds": grounds,
                    }
                ],
                "raw": {"cells": cells, "row_text": row_text},
            })
        return {
            "standardized_records": records[:20],
            "raw": {"parsed_count": parsed_count, "match_count": len(records)},
        }

    @staticmethod
    def _html_table_rows(html: str) -> List[List[str]]:
        rows: List[List[str]] = []
        for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
            row_html = row_match.group(1)
            cells = [
                cell_match.group(1)
                for cell_match in re.finditer(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            ]
            if cells:
                rows.append(cells)
        return rows

    @staticmethod
    def _clean_html_text(html: str) -> str:
        text = re.sub(r"<br\s*/?>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(unescape(text).split())

    def _format_wikidata_entity_search_result(self, raw_data: Any) -> Dict[str, Any]:
        if self._is_wikidata_entitydata_payload(raw_data):
            return self._format_wikidata_entitydata_result(raw_data)
        matches = raw_data.get("search", []) if isinstance(raw_data, dict) else []
        records: List[Dict[str, Any]] = []
        for item in matches:
            if not isinstance(item, dict):
                continue
            entity = str(item.get("label") or "").strip()
            if not entity:
                continue
            entity_id = str(item.get("id") or "").strip()
            description = str(item.get("description") or "").strip()
            concept_uri = str(item.get("concepturi") or "").strip()
            aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
            normalized_query = self._normalize_label_for_match(self._current_query_hint)
            normalized_entity = self._normalize_label_for_match(entity)
            exact_label = bool(normalized_query and normalized_query == normalized_entity)
            entity_match = {
                "seed_name": self._current_query_hint,
                "candidate_name": entity,
                "score": 1.0 if exact_label else 0.68,
                "level": "exact" if exact_label else "review",
                "reasons": [
                    "Wikidata label exact match" if exact_label else "Wikidata public related-topic search result"
                ],
                "identifiers": {"wikidata_id": entity_id} if entity_id else {},
            }
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": self.name,
                "entity": entity,
                "title": f"Wikidata entity graph match: {entity}",
                "summary": "; ".join(
                    part
                    for part in (
                        description,
                        f"wikidata_id={entity_id}" if entity_id else "",
                        f"aliases={', '.join(str(alias) for alias in aliases[:5])}" if aliases else "",
                    )
                    if part
                ),
                "url": concept_uri,
                "confidence": 0.56,
                "entity_match": entity_match,
                "evidence": [
                    {
                        "type": "public_knowledge_graph",
                        "provider": "Wikidata",
                        "item": concept_uri,
                        "wikidata_id": entity_id,
                    }
                ],
                "raw": item,
            })
        return {"standardized_records": records, "raw": raw_data}

    @staticmethod
    def _is_wikidata_entitydata_payload(raw_data: Any) -> bool:
        return isinstance(raw_data, dict) and isinstance(raw_data.get("entities"), dict)

    def _format_wikidata_entitydata_result(self, raw_data: Any) -> Dict[str, Any]:
        entities = raw_data.get("entities", {}) if isinstance(raw_data, dict) else {}
        records: List[Dict[str, Any]] = []
        for qid, entity_payload in entities.items():
            if not isinstance(entity_payload, dict):
                continue
            qid = str(qid or entity_payload.get("id") or "").strip()
            label = self._wikidata_label(entity_payload) or qid
            description = self._wikidata_description(entity_payload)
            relationship_entities = self._wikidata_relationship_entities(entity_payload)
            evidence = [
                {
                    "type": "public_knowledge_graph_entitydata",
                    "provider": "Wikidata",
                    "wikidata_id": qid,
                    "label": label,
                }
            ]
            for related in relationship_entities:
                evidence.append(
                    {
                        "type": "public_knowledge_graph_relation",
                        "provider": "Wikidata",
                        "relation": related["relation"],
                        "name": related["name"],
                        "wikidata_id": related.get("wikidata_id", ""),
                    }
                )

            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": self.name,
                "entity": label,
                "title": f"Wikidata entity data: {label}",
                "summary": "; ".join(
                    part
                    for part in (
                        description,
                        f"wikidata_id={qid}" if qid else "",
                        "relationships="
                        + ", ".join(
                            f"{item['relation']}:{item['name']}"
                            for item in relationship_entities[:8]
                        ) if relationship_entities else "",
                    )
                    if part
                ),
                "url": f"http://www.wikidata.org/entity/{qid}" if qid else "",
                "confidence": 0.7,
                "wikidata_id": qid,
                "wikidata_endpoint": "entitydata",
                "entity_match": EntityResolutionScorer.score(self._current_query_hint, label, {"wikidata_id": qid}) if EntityResolutionScorer and label else {},
                "entities": relationship_entities,
                "evidence": evidence,
                "raw": entity_payload,
            })
        return {"standardized_records": records, "raw": raw_data}

    @staticmethod
    def _wikidata_label(entity_payload: Dict[str, Any]) -> str:
        labels = entity_payload.get("labels") if isinstance(entity_payload, dict) else {}
        if isinstance(labels, dict):
            for language in ("en", "zh", "zh-hans"):
                value = labels.get(language)
                if isinstance(value, dict) and str(value.get("value") or "").strip():
                    return str(value["value"]).strip()
        return ""

    @staticmethod
    def _wikidata_description(entity_payload: Dict[str, Any]) -> str:
        descriptions = entity_payload.get("descriptions") if isinstance(entity_payload, dict) else {}
        if isinstance(descriptions, dict):
            for language in ("en", "zh", "zh-hans"):
                value = descriptions.get(language)
                if isinstance(value, dict) and str(value.get("value") or "").strip():
                    return str(value["value"]).strip()
        return ""

    def _wikidata_relationship_entities(self, entity_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        claims = entity_payload.get("claims") if isinstance(entity_payload, dict) else {}
        if not isinstance(claims, dict):
            return []
        property_map = {
            "P112": ("person", "founder", 0.72),
            "P169": ("person", "chief_executive_officer", 0.72),
            "P488": ("person", "chairperson", 0.7),
            "P1037": ("person", "director_or_manager", 0.66),
            "P3320": ("person", "board_member", 0.68),
            "P127": ("company", "owner", 0.68),
            "P1830": ("company", "owner_of", 0.66),
            "P355": ("company", "subsidiary", 0.66),
            "P749": ("company", "parent_organization", 0.66),
        }
        labels = self._wikidata_entity_labels_from_payload(entity_payload)
        related: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for property_id, (kind, relation, confidence) in property_map.items():
            for claim in claims.get(property_id) or []:
                qid = self._wikidata_claim_qid(claim)
                if not qid:
                    continue
                name = labels.get(qid, qid)
                key = (kind, relation, name)
                if key in seen:
                    continue
                seen.add(key)
                related.append({
                    "kind": kind,
                    "name": name,
                    "relation": relation,
                    "confidence": confidence,
                    "source": "Wikidata",
                    "wikidata_id": qid,
                })
        return related

    @staticmethod
    def _wikidata_entity_labels_from_payload(entity_payload: Dict[str, Any]) -> Dict[str, str]:
        labels: Dict[str, str] = {}
        entities = entity_payload.get("_linked_entities")
        if isinstance(entities, dict):
            for qid, linked in entities.items():
                if isinstance(linked, dict):
                    label = RestApiDataSource._wikidata_label(linked)
                    if label:
                        labels[str(qid)] = label
        return labels

    @staticmethod
    def _wikidata_claim_qid(claim: Any) -> str:
        if not isinstance(claim, dict):
            return ""
        mainsnak = claim.get("mainsnak")
        if not isinstance(mainsnak, dict):
            return ""
        datavalue = mainsnak.get("datavalue")
        if not isinstance(datavalue, dict):
            return ""
        value = datavalue.get("value")
        if not isinstance(value, dict):
            return ""
        entity_id = value.get("id")
        if entity_id:
            return str(entity_id)
        numeric_id = value.get("numeric-id")
        return f"Q{numeric_id}" if numeric_id else ""

    @staticmethod
    def _normalize_label_for_match(raw: str) -> str:
        text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", str(raw or "").lower())
        return " ".join(text.split())

    @staticmethod
    def _html_meta(html: str, name: str) -> str:
        pattern = (
            r"<meta\b(?=[^>]*\bname=[\"']"
            + re.escape(name)
            + r"[\"'])(?=[^>]*\bcontent=[\"']([^\"']*)[\"'])[^>]*>"
        )
        match = re.search(pattern, html, flags=re.IGNORECASE)
        return unescape(match.group(1)).strip() if match else ""

    def _format_official_portal_catalog_result(self, raw_data: Any, *, query: str = "") -> Dict[str, Any]:
        """Return an auditable handoff record for official portal catalog sources.

        These sources are catalog/handoff entries until a source-specific parser
        and stable health semantics are implemented. The record is intentionally
        not emitted as factual evidence; it tells the product which official
        portal should be consulted and what dimensions it covers.
        """
        parsed = self._format_official_portal_validated_snapshot(raw_data, query=query)
        if parsed is not None:
            return parsed

        domains = self.config.custom.get("coverage_domains") or []
        if not isinstance(domains, list):
            domains = []
        evidence_role = str(self.config.custom.get("evidence_role") or self.name)
        source_legitimacy = str(self.config.custom.get("source_legitimacy") or "official_public_portal")
        adapter_required = bool(self.config.custom.get("adapter_required", True))
        challenge_policy = str(getattr(self.config.auth, "challenge_provider", "") or "")
        expected_fields = self.config.custom.get("expected_fields") or []
        if not isinstance(expected_fields, list):
            expected_fields = []
        handoff_steps = self.config.custom.get("handoff_steps") or []
        if not isinstance(handoff_steps, list):
            handoff_steps = []
        parser_status = str(self.config.custom.get("parser_status") or "pending")
        health_semantics = str(self.config.custom.get("health_semantics") or "manual_catalog")
        base_url = str(self.config.base_url or "").strip()
        description = str(self.config.description or self.name).strip()
        summary_parts = [
            f"query={query}" if query else "",
            f"coverage={', '.join(str(item) for item in domains)}" if domains else "",
            f"evidence_role={evidence_role}" if evidence_role else "",
            "adapter_required=true" if adapter_required else "",
            f"handoff={challenge_policy}" if challenge_policy else "",
            f"parser_status={parser_status}" if parser_status else "",
            f"health={health_semantics}" if health_semantics else "",
        ]
        record = {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": self.name,
            "entity": query or description,
            "title": f"Official portal catalog handoff: {description}",
            "summary": "; ".join(part for part in summary_parts if part),
            "url": base_url,
            "confidence": 0.5,
            "evidence": [
                {
                    "type": "official_portal_catalog",
                    "provider": self.name,
                    "source_legitimacy": source_legitimacy,
                    "coverage_domains": [str(item) for item in domains],
                    "adapter_required": adapter_required,
                    "challenge_provider": challenge_policy,
                    "expected_fields": [str(item) for item in expected_fields],
                    "handoff_steps": [str(item) for item in handoff_steps],
                    "parser_status": parser_status,
                    "health_semantics": health_semantics,
                }
            ],
            "raw": {
                "description": description,
                "query": query,
                "base_url": base_url,
                "coverage_domains": [str(item) for item in domains],
                "adapter_required": adapter_required,
                "expected_fields": [str(item) for item in expected_fields],
                "handoff_steps": [str(item) for item in handoff_steps],
                "parser_status": parser_status,
                "health_semantics": health_semantics,
                "raw_probe": raw_data if isinstance(raw_data, (dict, list, str)) else str(type(raw_data).__name__),
            },
        }
        return {
            "source_catalog_records": [record],
            "standardized_records": [],
            "raw": record["raw"],
        }

    def _format_official_portal_validated_snapshot(self, raw_data: Any, *, query: str = "") -> Optional[Dict[str, Any]]:
        if not isinstance(raw_data, dict):
            return None

        page_status = str(raw_data.get("page_status") or raw_data.get("status") or "").strip()
        if page_status not in {"validated_result", "validated_no_result"}:
            return None

        snapshot = raw_data.get("fields") or raw_data.get("visible_fields") or raw_data.get("record")
        if snapshot is None:
            snapshot = {}
        if not isinstance(snapshot, dict):
            return None

        parser_kind = self._official_portal_parser_kind()
        if page_status == "validated_no_result":
            return self._official_portal_no_result(snapshot, raw_data, query=query, parser_kind=parser_kind)

        expected_fields = self.config.custom.get("expected_fields") or []
        if not isinstance(expected_fields, list):
            expected_fields = []
        if not self._official_portal_has_required_field(snapshot, expected_fields):
            return {
                "source_catalog_records": [
                    self._official_portal_parser_review_record(
                        raw_data,
                        query=query,
                        parser_kind=parser_kind,
                        reason="validated snapshot is missing expected fields",
                    )
                ],
                "standardized_records": [],
                "raw": {
                    "parser_kind": parser_kind,
                    "page_status": page_status,
                    "field_names": sorted(str(key) for key in snapshot.keys()),
                    "parse_status": "review_required",
                },
            }

        if parser_kind == "registry":
            record = self._official_china_registry_record(snapshot, raw_data, query=query)
        elif parser_kind == "credit":
            record = self._official_china_credit_record(snapshot, raw_data, query=query)
        elif parser_kind == "court_enforcement":
            record = self._official_china_court_record(snapshot, raw_data, query=query)
        else:
            record = self._official_portal_generic_record(snapshot, raw_data, query=query)

        return {
            "source_catalog_records": [],
            "standardized_records": [record],
            "raw": {
                "parser_kind": parser_kind,
                "page_status": page_status,
                "parse_status": "parsed_validated_snapshot",
                "field_names": sorted(str(key) for key in snapshot.keys()),
            },
        }

    def _official_portal_no_result(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
        parser_kind: str,
    ) -> Dict[str, Any]:
        evidence_role = str(self.config.custom.get("evidence_role") or self.name)
        source_url = str(raw_data.get("source_url") or raw_data.get("url") or self.config.base_url or "")
        record = {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": self.name,
            "entity": query or str(snapshot.get("legal_name") or snapshot.get("subject_name") or ""),
            "title": f"Validated official portal no-result: {self.config.description or self.name}",
            "summary": f"page_status=validated_no_result; evidence_role={evidence_role}; query={query}",
            "url": source_url,
            "published_at": str(raw_data.get("retrieved_at") or raw_data.get("checked_at") or "") or None,
            "confidence": 0.68,
            "evidence": [
                {
                    "type": "official_portal_no_result",
                    "provider": self.name,
                    "page_status": "validated_no_result",
                    "parser_kind": parser_kind,
                    "query": query,
                    "source_legitimacy": self.config.custom.get("source_legitimacy") or "official_public_portal",
                    "retrieved_at": raw_data.get("retrieved_at") or raw_data.get("checked_at"),
                    "manual_review_required": True,
                }
            ],
            "raw": {
                "visible_fields": dict(snapshot),
                "source_url": source_url,
                "page_status": "validated_no_result",
            },
            "entity_match": {
                "level": "no_result",
                "score": 1.0,
                "rationale": "validated official portal no-result page",
            },
        }
        return {
            "source_catalog_records": [],
            "standardized_records": [record],
            "raw": {
                "parser_kind": parser_kind,
                "page_status": "validated_no_result",
                "parse_status": "parsed_validated_no_result",
            },
        }

    def _official_portal_parser_review_record(
        self,
        raw_data: Dict[str, Any],
        *,
        query: str,
        parser_kind: str,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": self.name,
            "entity": query or self.name,
            "title": f"Official portal parser review required: {self.config.description or self.name}",
            "summary": f"parser_kind={parser_kind}; reason={reason}",
            "url": str(raw_data.get("source_url") or raw_data.get("url") or self.config.base_url or ""),
            "confidence": 0.35,
            "evidence": [
                {
                    "type": "official_portal_parser_review",
                    "provider": self.name,
                    "parser_kind": parser_kind,
                    "reason": reason,
                    "page_status": raw_data.get("page_status") or raw_data.get("status"),
                    "manual_review_required": True,
                }
            ],
            "raw": raw_data,
        }

    def _official_portal_parser_kind(self) -> str:
        role = str(self.config.custom.get("evidence_role") or self.name)
        name = str(self.name)
        if "court" in role or "court" in name or "enforcement" in role or "enforcement" in name:
            return "court_enforcement"
        if "credit" in role or "credit" in name:
            return "credit"
        if "registry" in role or "registry" in name:
            return "registry"
        return "generic"

    @staticmethod
    def _official_portal_has_required_field(snapshot: Dict[str, Any], expected_fields: List[Any]) -> bool:
        if not expected_fields:
            return bool(snapshot)
        lower_keys = {str(key).lower() for key in snapshot.keys()}
        return any(str(field).lower() in lower_keys for field in expected_fields)

    def _official_china_registry_record(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
    ) -> Dict[str, Any]:
        legal_name = self._official_field(snapshot, "legal_name", "entity", "company_name", "name") or query
        uscc = self._official_field(snapshot, "unified_social_credit_code", "uscc", "credit_code")
        legal_rep = self._official_field(snapshot, "legal_representative", "representative")
        address = self._official_field(snapshot, "registered_address", "address")
        business_status = self._official_field(snapshot, "business_status", "status")
        shareholders = self._official_list(snapshot.get("shareholders"))
        entities = []
        if legal_rep:
            entities.append({
                "kind": "person",
                "name": legal_rep,
                "relation": "legal_representative",
                "confidence": 0.84,
                "source": self.name,
            })
        for shareholder in shareholders[:10]:
            entities.append({
                "kind": "shareholder",
                "name": shareholder,
                "relation": "shareholder",
                "confidence": 0.76,
                "source": self.name,
            })
        if address:
            entities.append({
                "kind": "address",
                "name": address,
                "relation": "registered_address",
                "confidence": 0.82,
                "source": self.name,
            })
        summary_parts = [
            f"legal_name={legal_name}" if legal_name else "",
            f"unified_social_credit_code={uscc}" if uscc else "",
            f"legal_representative={legal_rep}" if legal_rep else "",
            f"business_status={business_status}" if business_status else "",
            f"shareholders={', '.join(shareholders[:5])}" if shareholders else "",
            f"registered_address={address}" if address else "",
        ]
        return self._official_portal_record(
            snapshot,
            raw_data,
            query=query,
            entity=legal_name,
            title=f"Official China registry snapshot: {legal_name}",
            summary="; ".join(part for part in summary_parts if part),
            confidence=0.82,
            entities=entities,
            registered_address=address,
            source_hint="official_china_registry",
            risk_category="corporate_registry",
            raw_extra={
                "unified_social_credit_code": uscc,
                "legal_representative": legal_rep,
                "shareholders": shareholders,
                "business_status": business_status,
            },
        )

    def _official_china_credit_record(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
    ) -> Dict[str, Any]:
        legal_name = self._official_field(snapshot, "legal_name", "entity", "company_name", "name") or query
        notice_title = self._official_field(snapshot, "credit_notice", "notice_title", "title")
        penalty = self._official_field(snapshot, "administrative_penalty", "penalty")
        abnormal = self._official_field(snapshot, "abnormal_operation", "abnormal")
        authority = self._official_field(snapshot, "issuing_authority", "authority")
        notice_date = self._official_field(snapshot, "notice_date", "date", "published_at")
        risk_events = []
        if penalty or abnormal:
            risk_events.append({
                "risk_category": "administrative_risk",
                "severity": "medium" if penalty else "low",
                "title": notice_title or penalty or abnormal,
                "summary": "; ".join(part for part in (penalty, abnormal, authority) if part),
                "confidence": 0.74,
            })
        summary_parts = [
            f"legal_name={legal_name}" if legal_name else "",
            f"notice={notice_title}" if notice_title else "",
            f"administrative_penalty={penalty}" if penalty else "",
            f"abnormal_operation={abnormal}" if abnormal else "",
            f"issuing_authority={authority}" if authority else "",
            f"notice_date={notice_date}" if notice_date else "",
        ]
        record = self._official_portal_record(
            snapshot,
            raw_data,
            query=query,
            entity=legal_name,
            title=f"Official China credit-publicity snapshot: {notice_title or legal_name}",
            summary="; ".join(part for part in summary_parts if part),
            confidence=0.74,
            source_hint="official_china_credit_publicity",
            risk_category="administrative_risk" if risk_events else "credit_publicity",
            severity="medium" if penalty else ("low" if abnormal else ""),
            risk_events=risk_events,
            raw_extra={
                "notice_title": notice_title,
                "administrative_penalty": penalty,
                "abnormal_operation": abnormal,
                "issuing_authority": authority,
                "notice_date": notice_date,
            },
        )
        if notice_date:
            record["published_at"] = notice_date
        return record

    def _official_china_court_record(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
    ) -> Dict[str, Any]:
        subject = self._official_field(snapshot, "subject_name", "legal_name", "entity", "name") or query
        case_number = self._official_field(snapshot, "case_number", "case_no")
        court = self._official_field(snapshot, "court", "executing_court")
        filing_date = self._official_field(snapshot, "filing_date", "date", "published_at")
        amount = self._official_field(snapshot, "execution_amount", "amount")
        case_status = self._official_field(snapshot, "case_status", "status")
        title = f"Official China court enforcement snapshot: {case_number or subject}"
        summary_parts = [
            f"subject_name={subject}" if subject else "",
            f"case_number={case_number}" if case_number else "",
            f"court={court}" if court else "",
            f"filing_date={filing_date}" if filing_date else "",
            f"execution_amount={amount}" if amount else "",
            f"case_status={case_status}" if case_status else "",
        ]
        risk_events = [
            {
                "risk_category": "court_enforcement",
                "severity": "high" if amount else "medium",
                "title": title,
                "summary": "; ".join(part for part in summary_parts if part),
                "confidence": 0.78,
            }
        ]
        record = self._official_portal_record(
            snapshot,
            raw_data,
            query=query,
            entity=subject,
            title=title,
            summary="; ".join(part for part in summary_parts if part),
            confidence=0.78,
            source_hint="official_china_court_enforcement",
            risk_category="court_enforcement",
            severity="high" if amount else "medium",
            risk_events=risk_events,
            raw_extra={
                "case_number": case_number,
                "court": court,
                "filing_date": filing_date,
                "execution_amount": amount,
                "case_status": case_status,
            },
        )
        if filing_date:
            record["published_at"] = filing_date
        return record

    def _official_portal_generic_record(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
    ) -> Dict[str, Any]:
        entity = self._official_field(snapshot, "legal_name", "subject_name", "entity", "name") or query
        return self._official_portal_record(
            snapshot,
            raw_data,
            query=query,
            entity=entity,
            title=f"Official portal validated snapshot: {entity}",
            summary="; ".join(f"{key}={value}" for key, value in snapshot.items() if str(value).strip()),
            confidence=0.65,
            source_hint=self.name,
        )

    def _official_portal_record(
        self,
        snapshot: Dict[str, Any],
        raw_data: Dict[str, Any],
        *,
        query: str,
        entity: str,
        title: str,
        summary: str,
        confidence: float,
        source_hint: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        registered_address: str = "",
        risk_category: str = "",
        severity: str = "",
        risk_events: Optional[List[Dict[str, Any]]] = None,
        raw_extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_url = str(raw_data.get("source_url") or raw_data.get("url") or self.config.base_url or "")
        retrieved_at = str(raw_data.get("retrieved_at") or raw_data.get("checked_at") or datetime.now().isoformat())
        match = EntityResolutionScorer.score(query, entity, raw_extra or snapshot) if EntityResolutionScorer and query and entity else {}
        evidence = [
            {
                "type": "official_portal_validated_snapshot",
                "provider": self.name,
                "source_legitimacy": self.config.custom.get("source_legitimacy") or "official_public_portal",
                "page_status": "validated_result",
                "parser_kind": self._official_portal_parser_kind(),
                "retrieved_at": retrieved_at,
                "source_url": source_url,
                "visible_fields": dict(snapshot),
                "manual_review_required": True,
            }
        ]
        raw = {
            "visible_fields": dict(snapshot),
            "source_url": source_url,
            "page_status": "validated_result",
            "parser_kind": self._official_portal_parser_kind(),
        }
        if raw_extra:
            raw.update(raw_extra)
        return {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": source_hint,
            "entity": entity,
            "title": title,
            "summary": summary,
            "url": source_url,
            "published_at": str(raw_data.get("published_at") or "") or None,
            "retrieved_at": retrieved_at,
            "confidence": confidence,
            "evidence": evidence,
            "entities": entities or [],
            "registered_address": registered_address,
            "entity_match": match,
            "risk_category": risk_category,
            "severity": severity,
            "risk_events": risk_events or [],
            "raw": raw,
        }

    @staticmethod
    def _official_field(snapshot: Dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = snapshot.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _official_list(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            return [item.strip() for item in re.split(r"[;,，；|]", raw) if item.strip()]
        return [str(raw).strip()] if str(raw).strip() else []

    def _format_ofac_consolidated_xml_result(self, raw_data: Any, *, query: str = "") -> Dict[str, Any]:
        if not isinstance(raw_data, str) or not raw_data.strip():
            return {"standardized_records": [], "raw": raw_data}

        try:
            root = ET.fromstring(raw_data)
        except ET.ParseError:
            return {"standardized_records": [], "raw": raw_data[:1000]}

        records: List[Dict[str, Any]] = []
        parsed_count = 0
        for entry in root.findall(".//{*}sdnEntry"):
            parsed_count += 1
            first_name = self._xml_text(entry, "firstName")
            last_name = self._xml_text(entry, "lastName")
            title = " ".join(part for part in (first_name, last_name) if part).strip()
            if not title:
                title = self._xml_text(entry, "lastName") or self._xml_text(entry, "sdnEntry")
            if not title:
                continue
            entity_match = EntityResolutionScorer.score(query, title, {"uid": self._xml_text(entry, "uid")}) if query else {}
            if query and str(entity_match.get("level")) not in {"exact", "strong"}:
                continue
            sdn_type = self._xml_text(entry, "sdnType")
            programs = [
                item.text.strip()
                for item in entry.findall(".//{*}program")
                if item.text and item.text.strip()
            ]
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": self.name,
                "entity": title,
                "title": f"OFAC consolidated sanctions entry: {title}",
                "summary": "; ".join(
                    part
                    for part in (
                        f"type={sdn_type}" if sdn_type else "",
                        f"programs={', '.join(programs[:5])}" if programs else "",
                    )
                    if part
                ),
                "url": "https://ofac.treasury.gov/specially-designated-nationals-list-data-formats-data-schemas",
                "confidence": 0.9,
                "entity_match": entity_match,
                "evidence": [
                    {
                        "type": "official_public_dataset",
                        "provider": "OFAC",
                        "sdn_type": sdn_type,
                        "programs": programs,
                    }
                ],
                "risk_events": [
                    {
                        "category": "administrative",
                        "severity": "high",
                        "title": f"OFAC consolidated sanctions match: {title}",
                        "summary": "Subject matched an official public sanctions-list entry.",
                        "confidence": 0.9,
                    }
                ],
                "raw": {
                    "uid": self._xml_text(entry, "uid"),
                    "sdn_type": sdn_type,
                    "programs": programs,
                },
            })
        return {"standardized_records": records[:20], "raw": {"match_count": len(records), "parsed_count": parsed_count}}

    def _format_un_sc_consolidated_xml_result(self, raw_data: Any, *, query: str = "") -> Dict[str, Any]:
        if not isinstance(raw_data, str) or not raw_data.strip():
            return {"standardized_records": [], "raw": {"match_count": 0, "parsed_count": 0}}
        try:
            root = ET.fromstring(raw_data[:_UN_SC_MAX_RESPONSE_SIZE])
        except ET.ParseError:
            return {"standardized_records": [], "raw": {"match_count": 0, "parsed_count": 0, "parse_error": True}}

        records: List[Dict[str, Any]] = []
        parsed_count = 0
        for entry in list(root.findall(".//INDIVIDUAL")) + list(root.findall(".//ENTITY")):
            parsed_count += 1
            entry_kind = "person" if entry.tag.endswith("INDIVIDUAL") else "company"
            name = self._un_sc_entry_name(entry)
            if not name:
                continue
            aliases = self._un_sc_entry_aliases(entry)
            candidates = [name, *aliases]
            entity_match = self._best_entity_match(
                query,
                candidates,
                {"source": "un_sc_consolidated_sanctions"},
            ) if query else {}
            if query and str(entity_match.get("level") or "") not in {"exact", "strong", "review"}:
                continue
            list_type = self._xml_text_no_ns(entry, "UN_LIST_TYPE")
            reference_number = self._xml_text_no_ns(entry, "REFERENCE_NUMBER")
            listed_on = self._xml_text_no_ns(entry, "LISTED_ON")
            comments = self._xml_text_no_ns(entry, "COMMENTS1")
            summary = "; ".join(
                part
                for part in (
                    f"list_type={list_type}" if list_type else "",
                    f"reference={reference_number}" if reference_number else "",
                    f"listed_on={listed_on}" if listed_on else "",
                    f"aliases={', '.join(aliases[:5])}" if aliases else "",
                    comments[:240] if comments else "",
                )
                if part
            )
            title = f"UN Security Council consolidated list match: {name}"
            records.append({
                "source_name": self.name,
                "source_type": self.type_name,
                "source_hint": self.name,
                "entity": name,
                "title": title,
                "summary": summary,
                "url": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
                "confidence": 0.88,
                "entity_match": entity_match,
                "entities": [
                    {
                        "kind": entry_kind,
                        "name": name,
                        "relation": "watchlist_subject",
                        "confidence": 0.88,
                        "source": "United Nations Security Council",
                    }
                ],
                "risk_events": [
                    {
                        "category": "administrative_risk",
                        "severity": "high",
                        "title": title,
                        "summary": summary or "Subject matched an official UN Security Council consolidated-list entry.",
                        "confidence": 0.88,
                        "status": "open",
                    }
                ],
                "evidence": [
                    {
                        "type": "official_public_dataset",
                        "provider": "United Nations Security Council",
                        "dataset": "Consolidated List",
                        "entry_kind": entry_kind,
                        "reference_number": reference_number,
                        "list_type": list_type,
                        "listed_on": listed_on,
                        "aliases": aliases,
                    }
                ],
                "raw": {
                    "dataid": self._xml_text_no_ns(entry, "DATAID"),
                    "reference_number": reference_number,
                    "list_type": list_type,
                    "listed_on": listed_on,
                    "aliases": aliases,
                },
            })
        return {"standardized_records": records[:20], "raw": {"match_count": len(records), "parsed_count": parsed_count}}

    @classmethod
    def _best_entity_match(
        cls,
        query: str,
        candidates: List[str],
        identifiers: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not EntityResolutionScorer:
            return {}
        best: Dict[str, Any] = {}
        for candidate in candidates:
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            match = EntityResolutionScorer.score(query, candidate, identifiers)
            if not best or float(match.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
                best = match
        return best

    @classmethod
    def _un_sc_entry_name(cls, entry: ET.Element) -> str:
        if entry.tag.endswith("ENTITY"):
            return cls._xml_text_no_ns(entry, "FIRST_NAME")
        parts = [
            cls._xml_text_no_ns(entry, "FIRST_NAME"),
            cls._xml_text_no_ns(entry, "SECOND_NAME"),
            cls._xml_text_no_ns(entry, "THIRD_NAME"),
            cls._xml_text_no_ns(entry, "FOURTH_NAME"),
        ]
        return " ".join(part for part in parts if part).strip()

    @classmethod
    def _un_sc_entry_aliases(cls, entry: ET.Element) -> List[str]:
        aliases: List[str] = []
        for alias_node in list(entry.findall(".//INDIVIDUAL_ALIAS")) + list(entry.findall(".//ENTITY_ALIAS")):
            alias = cls._xml_text_no_ns(alias_node, "ALIAS_NAME")
            if alias and alias not in aliases:
                aliases.append(alias)
        return aliases

    @staticmethod
    def _xml_text_no_ns(element: ET.Element, tag: str) -> str:
        found = element.find(tag)
        return (found.text or "").strip() if found is not None and found.text else ""

    @staticmethod
    def _xml_text(element: ET.Element, tag: str) -> str:
        found = element.find(f".//{{*}}{tag}")
        return (found.text or "").strip() if found is not None and found.text else ""
    
    async def _get_session(self):
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            # SECURITY FIX F-005: Don't set default headers here, set them per-request
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _blocking_public_text_get(
        self,
        url: str,
        *,
        params: Dict[str, Any],
        headers: Dict[str, str],
        max_size: int,
    ) -> str:
        """Fetch public text sources with urllib when an origin stalls aiohttp body reads."""
        return await asyncio.to_thread(
            self._blocking_public_text_get_sync,
            url,
            params,
            headers,
            max_size,
            self.config.timeout,
        )

    @staticmethod
    def _blocking_public_text_get_sync(
        url: str,
        params: Dict[str, Any],
        headers: Dict[str, str],
        max_size: int,
        timeout: int,
    ) -> str:
        safe_url = _validate_http_url(url, "url")
        query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
        if query:
            separator = "&" if "?" in safe_url else "?"
            safe_url = f"{safe_url}{separator}{query}"
        safe_headers = _validate_headers(headers, "headers")
        request = UrlRequest(safe_url, headers=safe_headers, method="GET")
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is validated above.
            payload = response.read(max_size + 1)
        if len(payload) > max_size:
            raise QueryError(f"response body too large: {len(payload)} bytes")
        return payload.decode("utf-8", errors="replace")

    async def _do_query(self, request: QueryRequest) -> Any:
        """
        执行 REST API 查询

        Args:
            request: 查询请求

        Returns:
            API 响应数据
        """
        session = await self._get_session()
        endpoint, params = self._prepare_provider_request(request)
        url = _join_endpoint(self.config.base_url, endpoint)
        headers = {**self.config.headers, **request.headers}
        auth_context = await self._auth_handler.prepare(
            AuthRequestContext(
                source_name=self.name,
                method="GET",
                url=url,
                params=params,
                headers=headers,
            )
        )
        auth_context.headers = _validate_headers(auth_context.headers, 'headers')
        provider_type = str(self.config.custom.get("provider_type", ""))
        if provider_type == "un_sc_consolidated_sanctions_xml":
            return await self._blocking_public_text_get(
                auth_context.url,
                params=auth_context.params,
                headers=auth_context.headers,
                max_size=_UN_SC_MAX_RESPONSE_SIZE,
            )

        async with session.get(
            auth_context.url,
            params=auth_context.params,
            headers=auth_context.headers,
        ) as response:
            response_headers = dict(getattr(response, "headers", {}) or {})
            body_preview = ""
            if int(getattr(response, "status", 0) or 0) in {403, 429}:
                try:
                    body_preview = (await response.text())[:2048]
                except Exception:
                    body_preview = ""
            await self._auth_handler.handle_response(
                auth_context,
                AuthResponseContext(
                    status=int(getattr(response, "status", 0) or 0),
                    headers=response_headers,
                    content_type=str(response_headers.get("content-type", "")),
                    body_preview=body_preview,
                ),
            )
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if 'json' not in content_type and 'text/' not in content_type:
                self.logger.warning(f"未知的 Content-Type: {content_type}")

            if response.content_length and response.content_length > _MAX_RESPONSE_SIZE:
                raise QueryError(f"响应体过大: {response.content_length} bytes")

            if provider_type in {"ofac_consolidated_xml", "un_sc_consolidated_sanctions_xml"}:
                max_size = _OFAC_MAX_RESPONSE_SIZE if provider_type == "ofac_consolidated_xml" else _UN_SC_MAX_RESPONSE_SIZE
                if response.content_length and response.content_length > max_size:
                    raise QueryError(f"响应体过大: {response.content_length} bytes")
                return await response.text()
            if provider_type in {"idb_sanctioned_firms_dataset_catalog", "world_bank_debarred_firms"}:
                return await response.text()

            try:
                payload = await response.json()
                if (
                    provider_type == "wikidata_entity_search"
                    and str(request.params.get("wikidata_endpoint") or "") == "entitydata"
                    and isinstance(payload, dict)
                ):
                    payload = await self._attach_wikidata_linked_labels(
                        session,
                        payload,
                        headers=auth_context.headers,
                    )
                return payload
            except Exception as exc:
                self.logger.error(f"响应解析失败: {type(exc).__name__}")
                raise QueryError('响应解析失败') from exc
    async def health_check(self) -> bool:
        """
        健康检查: 发送简单请求验证连接
        
        Returns:
            是否健康
        """
        try:
            session = await self._get_session()
            async with session.get(f"{self.config.base_url}/health") as response:
                return response.status < 400
        except Exception as e:
            self.logger.warning(f"健康检查失败: {e}")
            return False
    
    def format_result(self, raw_data: Any) -> Any:
        """
        格式化 REST API 结果
        
        默认返回原始 JSON 数据
        子类可以覆盖此方法自定义格式化逻辑
        
        Args:
            raw_data: 原始 API 响应
            
        Returns:
            格式化后的数据
        """
        # 默认实现: 如果数据是字典且包含常见字段，提取有效数据
        provider_type = str(self.config.custom.get("provider_type", ""))
        if provider_type == "gleif_lei":
            return self._format_gleif_result(raw_data)
        if provider_type == "sec_edgar":
            return self._format_sec_result(raw_data)
        if provider_type == "opensanctions_dataset_catalog":
            return self._format_opensanctions_catalog_result(raw_data)
        if provider_type == "idb_sanctioned_firms_dataset_catalog":
            return self._format_idb_sanctioned_firms_catalog_result(raw_data)
        if provider_type == "world_bank_debarred_firms":
            return self._format_world_bank_debarred_firms_result(raw_data, query=self._current_query_hint)
        if provider_type == "wikidata_entity_search":
            return self._format_wikidata_entity_search_result(raw_data)
        if provider_type == "ofac_consolidated_xml":
            return self._format_ofac_consolidated_xml_result(raw_data, query=self._current_query_hint)
        if provider_type == "un_sc_consolidated_sanctions_xml":
            return self._format_un_sc_consolidated_xml_result(raw_data, query=self._current_query_hint)
        if provider_type == "official_portal_catalog":
            return self._format_official_portal_catalog_result(raw_data, query=self._current_query_hint)

        if isinstance(raw_data, dict):
            # 尝试提取常见数据字段
            for key in ['data', 'results', 'items', 'content']:
                if key in raw_data:
                    return raw_data[key]
        
        # 如果没有常见字段，返回原始数据
        return raw_data

    async def _attach_wikidata_linked_labels(
        self,
        session: Any,
        payload: Dict[str, Any],
        *,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        qids = sorted(self._wikidata_referenced_qids_from_payload(payload))[:25]
        if not qids:
            return payload
        existing = self._wikidata_existing_linked_labels(payload)
        missing = [qid for qid in qids if qid not in existing]
        if not missing:
            return payload
        label_params = {
            "action": "wbgetentities",
            "format": "json",
            "props": "labels",
            "languages": "en|zh|zh-hans",
            "ids": "|".join(missing),
        }
        try:
            async with session.get(
                "https://www.wikidata.org/w/api.php",
                params=label_params,
                headers=headers,
            ) as response:
                response.raise_for_status()
                label_payload = await response.json()
        except Exception as exc:
            self.logger.warning("Wikidata linked-label enrichment failed: %s", type(exc).__name__)
            return payload

        linked = label_payload.get("entities", {}) if isinstance(label_payload, dict) else {}
        if not isinstance(linked, dict):
            return payload
        for entity_payload in (payload.get("entities") or {}).values():
            if not isinstance(entity_payload, dict):
                continue
            current = entity_payload.setdefault("_linked_entities", {})
            if isinstance(current, dict):
                current.update({str(qid): value for qid, value in linked.items() if isinstance(value, dict)})
        return payload

    @classmethod
    def _wikidata_referenced_qids_from_payload(cls, payload: Dict[str, Any]) -> set[str]:
        qids: set[str] = set()
        relationship_properties = {"P112", "P169", "P488", "P1037", "P127", "P355", "P749"}
        for entity_payload in (payload.get("entities") or {}).values():
            if not isinstance(entity_payload, dict):
                continue
            claims = entity_payload.get("claims")
            if not isinstance(claims, dict):
                continue
            for property_id in relationship_properties:
                values = claims.get(property_id)
                if not isinstance(values, list):
                    continue
                for claim in values:
                    qid = cls._wikidata_claim_qid(claim)
                    if qid:
                        qids.add(qid)
        return qids

    @staticmethod
    def _wikidata_existing_linked_labels(payload: Dict[str, Any]) -> set[str]:
        existing: set[str] = set()
        for entity_payload in (payload.get("entities") or {}).values():
            if not isinstance(entity_payload, dict):
                continue
            linked = entity_payload.get("_linked_entities")
            if isinstance(linked, dict):
                existing.update(str(key) for key in linked)
        return existing
    
    # SECURITY FIX F-012: Rate limiting integration
    async def _pre_query(self, request: QueryRequest) -> None:
        """Rate limiting check before query"""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

    async def _post_query(self, data: Any, request: QueryRequest) -> Any:
        if (
            self.config.custom.get("provider_type") == "wikidata_entity_search"
            and isinstance(data, dict)
            and isinstance(data.get("raw"), dict)
        ):
            self._current_query_hint = request.query
            return self._format_wikidata_entity_search_result(data["raw"])
        if (
            self.config.custom.get("provider_type") == "sec_edgar"
            and isinstance(data, dict)
            and isinstance(data.get("raw"), dict)
            and "cik" not in data["raw"]
        ):
            data["raw"]["_query"] = request.query
            return self._format_sec_result(data["raw"])
        return data
    
    async def close(self) -> None:
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()


class LocalIndexDataSource(BaseDataSource):
    """Read-only subject screening against a local public/authorized index file."""

    type_name: str = "local_index"

    async def _do_query(self, request: QueryRequest) -> Any:
        index_path = Path(str(self.config.custom.get("index_path") or ""))
        if not index_path:
            raise QueryError("local index path is not configured")
        if not index_path.exists() or not index_path.is_file():
            raise QueryError("local index file is not available")
        if index_path.suffix.lower() not in {".json", ".jsonl", ".ndjson", ".csv"}:
            raise QueryError("unsupported local index format")
        return {
            "query": request.query,
            "records": self._load_index_records(index_path),
            "index_path": str(index_path),
        }

    async def health_check(self) -> bool:
        index_path = Path(str(self.config.custom.get("index_path") or ""))
        return bool(index_path and index_path.exists() and index_path.is_file())

    def format_result(self, raw_data: Any) -> Any:
        if not isinstance(raw_data, dict):
            return {"standardized_records": [], "raw": raw_data}
        query = str(raw_data.get("query") or "")
        records = raw_data.get("records") if isinstance(raw_data.get("records"), list) else []
        standardized: List[Dict[str, Any]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            name = self._record_name(item)
            if not name:
                continue
            match = EntityResolutionScorer.score(query, name, item) if EntityResolutionScorer and query else {}
            if str(match.get("level") or "") not in {"exact", "strong", "review"}:
                continue
            standardized.append(self._standardized_local_record(item, name, match))
        return {
            "standardized_records": standardized[:20],
            "raw": {
                "index_path": raw_data.get("index_path"),
                "parsed_count": len(records),
                "match_count": len(standardized),
            },
        }

    @staticmethod
    def _load_index_records(index_path: Path) -> List[Dict[str, Any]]:
        suffix = index_path.suffix.lower()
        if suffix == ".json":
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for key in ("records", "data", "items", "results"):
                    if isinstance(payload.get(key), list):
                        return [item for item in payload[key] if isinstance(item, dict)]
                return [payload]
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            return []
        if suffix in {".jsonl", ".ndjson"}:
            rows: List[Dict[str, Any]] = []
            for line in index_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            return rows
        with index_path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    @classmethod
    def audit_index_file(cls, index_path: Union[str, Path]) -> Dict[str, Any]:
        path = Path(index_path)
        errors: List[str] = []
        warnings: List[str] = []
        if not path.exists() or not path.is_file():
            return {
                "ok": False,
                "status": "missing",
                "path": str(path),
                "record_count": 0,
                "matchable_count": 0,
                "provenance_count": 0,
                "errors": ["index_file_not_found"],
                "warnings": [],
            }
        if path.suffix.lower() not in {".json", ".jsonl", ".ndjson", ".csv"}:
            return {
                "ok": False,
                "status": "unsupported_format",
                "path": str(path),
                "record_count": 0,
                "matchable_count": 0,
                "provenance_count": 0,
                "errors": ["unsupported_local_index_format"],
                "warnings": [],
            }
        try:
            records = cls._load_index_records(path)
        except Exception as exc:
            return {
                "ok": False,
                "status": "parse_error",
                "path": str(path),
                "record_count": 0,
                "matchable_count": 0,
                "provenance_count": 0,
                "errors": [type(exc).__name__],
                "warnings": [],
            }

        matchable_count = 0
        provenance_count = 0
        severity_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        field_coverage: Dict[str, int] = {}
        for item in records:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if value not in (None, ""):
                    field_coverage[str(key)] = field_coverage.get(str(key), 0) + 1
            if cls._record_name(item):
                matchable_count += 1
            if any(str(item.get(key) or "").strip() for key in ("url", "source_url", "reference_url", "dataset")):
                provenance_count += 1
            severity = str(item.get("severity") or "unspecified").strip() or "unspecified"
            category = str(item.get("category") or item.get("schema") or item.get("type") or "unspecified").strip() or "unspecified"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1

        record_count = len(records)
        if record_count == 0:
            errors.append("empty_index")
        if matchable_count < record_count:
            warnings.append("some_records_missing_matchable_name")
        if provenance_count < record_count:
            warnings.append("some_records_missing_source_or_dataset")
        ok = bool(record_count and matchable_count == record_count and provenance_count == record_count)
        return {
            "ok": ok,
            "status": "ready" if ok else "needs_review",
            "path": str(path),
            "record_count": record_count,
            "matchable_count": matchable_count,
            "provenance_count": provenance_count,
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "field_coverage": field_coverage,
            "errors": errors,
            "warnings": warnings,
            "required_name_fields": ["name", "entity", "caption", "legal_name", "firm_name", "subject", "title"],
            "recommended_provenance_fields": ["url", "source_url", "reference_url", "dataset"],
        }

    @staticmethod
    def _record_name(item: Dict[str, Any]) -> str:
        for key in ("name", "entity", "caption", "legal_name", "firm_name", "subject", "title"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _standardized_local_record(
        self,
        item: Dict[str, Any],
        name: str,
        match: Dict[str, Any],
    ) -> Dict[str, Any]:
        provider = str(self.config.custom.get("provider") or self.name)
        dataset = str(self.config.custom.get("dataset") or item.get("dataset") or self.name)
        category = str(item.get("category") or item.get("schema") or item.get("type") or "public_index_match")
        url = str(item.get("url") or item.get("source_url") or self.config.base_url)
        summary_parts = [
            f"dataset={dataset}",
            f"category={category}",
            str(item.get("summary") or item.get("description") or item.get("reason") or "").strip(),
        ]
        return {
            "source_name": self.name,
            "source_type": self.type_name,
            "source_hint": self.name,
            "entity": name,
            "title": f"Local public index match: {name}",
            "summary": "; ".join(part for part in summary_parts if part),
            "url": url,
            "confidence": 0.72 if match.get("level") in {"exact", "strong"} else 0.58,
            "entity_match": match,
            "risk_events": [
                {
                    "category": "administrative_risk",
                    "severity": str(item.get("severity") or "medium"),
                    "title": f"{provider} local index match",
                    "summary": str(item.get("summary") or item.get("description") or "Subject matched a configured local public index."),
                    "confidence": 0.7,
                    "status": "open",
                }
            ],
            "evidence": [
                {
                    "type": "local_public_or_authorized_index",
                    "provider": provider,
                    "dataset": dataset,
                    "category": category,
                    "source_url": url,
                }
            ],
            "raw": item,
        }

# =============================================================================
# 8. 数据源管理器 (Data Source Manager)
# =============================================================================

class DataSourceManager:
    """
    数据源管理器
    
    负责:
    1. 数据源注册与管理
    2. 配置加载与验证
    3. 并发查询编排
    4. 结果聚合
    5. 缓存管理
    """
    
    # SECURITY FIX F-004: Add concurrency and source count limits
    MAX_CONCURRENCY = 50
    MAX_SOURCES = 100
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        初始化数据源管理器
        
        Args:
            config_path: YAML 配置文件路径
        """
        self.config_path = Path(config_path) if config_path else None
        self._sources: Dict[str, BaseDataSource] = {}
        self._source_classes: Dict[str, Type[BaseDataSource]] = {}
        self.config: Optional[MultiDataSourceConfig] = None
        self.logger = logging.getLogger("DataSourceManager")
        self._health_status: Dict[str, bool] = {}
        self._health_reports: Dict[str, HealthReport] = {}
        
        # 缓存机制
        self._cache = QueryCache(max_size=1000, default_ttl=300)
        
        # 注册默认数据源类型
        self.register_source_type(RestApiDataSource)
        self.register_source_type(LocalIndexDataSource)
    
    def register_source_type(self, source_class: Type[BaseDataSource]) -> None:
        """
        注册数据源类型
        
        Args:
            source_class: 数据源类
        """
        type_name = source_class.type_name
        if type_name in self._source_classes:
            self.logger.warning(f"覆盖已注册的数据源类型: {type_name}")
        self._source_classes[type_name] = source_class
        self.logger.info(f"注册数据源类型: {type_name}")
    
    def load_config(self, config_path: Optional[Union[str, Path]] = None) -> None:
        """
        加载配置文件
        
        Args:
            config_path: YAML 配置文件路径
        """
        path = Path(config_path) if config_path else self.config_path
        if not path:
            raise ConfigError("未指定配置文件路径")
        
        if not path.exists():
            raise ConfigError(f"配置文件不存在: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        if not config_dict:
            raise ConfigError("config file is empty")
        
        self.config = MultiDataSourceConfig(**config_dict)
        self.logger.info(f"加载配置: {len(self.config.sources)} 个数据源")
    
    def initialize_sources(self) -> None:
        """
        根据配置初始化所有数据源
        """
        if not self.config:
            raise ConfigError("请先调用 load_config() 加载配置")
        
        self._sources.clear()
        self._health_status.clear()
        self._health_reports.clear()
        
        for source_config in self.config.sources:
            if not source_config.enabled:
                self.logger.info(f"跳过禁用的数据源: {source_config.name}")
                continue
            
            # 查找对应的数据源类
            source_class = self._source_classes.get(source_config.type)
            if not source_class:
                self.logger.error(
                    f"未找到数据源类型 '{source_config.type}' "
                    f"(数据源: {source_config.name})"
                )
                continue
            
            # 创建数据源实例
            try:
                source = source_class(source_config)
                self._sources[source_config.name] = source
                self._health_status[source_config.name] = True
                self._health_reports[source_config.name] = HealthReport(
                    source_name=source_config.name,
                    source_type=source_config.type,
                    ok=True,
                    status="unknown",
                    endpoint=source_config.ping_endpoint or source_config.base_url,
                    detail="initialized; connectivity not checked yet",
                )
                self.logger.info(f"初始化数据源: {source_config.name}")  # SECURITY FIX F-003: Only log non-sensitive info
            except Exception as e:
                self.logger.error(f"初始化数据源失败 {source_config.name}: {e}")
        
        self.logger.info(f"✅ 已初始化 {len(self._sources)} 个数据源")
    
    async def initialize_and_check(self) -> None:
        """
        初始化数据源 + 可达性检测 (推荐在系统启动时调用)
        """
        self.initialize_sources()
        await self.check_connectivity()
    
    async def check_connectivity(self) -> Dict[str, bool]:
        """
        检测所有已启用的数据源可达性
        
        Returns:
            数据源名称 -> 是否可达
        """
        reports = await self.health_report_all()
        return {name: report.ok for name, report in reports.items()}

    async def health_report_all(self) -> Dict[str, HealthReport]:
        """Return structured connectivity reports for every loaded source."""
        reports: Dict[str, HealthReport] = {}
        for name, source in self._sources.items():
            started = time.time()
            endpoint = source.config.ping_endpoint or source.config.base_url

            if not source.config.ping:
                if self._is_official_portal_catalog_source(source):
                    report = self._official_portal_manual_gate_health_report(source, endpoint)
                    reports[name] = report
                    self._health_reports[name] = report
                    self._health_status[name] = True
                    continue
                report = HealthReport(
                    source_name=name,
                    source_type=source.type_name,
                    ok=True,
                    status="skipped",
                    endpoint=endpoint,
                    latency_ms=0.0,
                    detail="ping disabled by datasource configuration",
                )
                reports[name] = report
                self._health_reports[name] = report
                self._health_status[name] = True
                continue

            try:
                ok = await self._check_single_connectivity(name, source)
                report = HealthReport(
                    source_name=name,
                    source_type=source.type_name,
                    ok=ok,
                    status="up" if ok else "down",
                    endpoint=endpoint,
                    latency_ms=(time.time() - started) * 1000,
                    detail="connectivity check passed" if ok else "connectivity check failed",
                )
            except AuthChallengeRequired as exc:
                report = HealthReport(
                    source_name=name,
                    source_type=source.type_name,
                    ok=False,
                    status="challenge",
                    endpoint=endpoint,
                    latency_ms=(time.time() - started) * 1000,
                    detail="authentication challenge required",
                    error_type=type(exc).__name__,
                    auth_challenge={
                        "type": exc.challenge_type,
                        "source": exc.source,
                        "details": exc.details,
                    },
                )
            except Exception as exc:
                report = HealthReport(
                    source_name=name,
                    source_type=source.type_name,
                    ok=False,
                    status="error",
                    endpoint=endpoint,
                    latency_ms=(time.time() - started) * 1000,
                    detail="connectivity check raised an unexpected exception",
                    error_type=type(exc).__name__,
                )

            reports[name] = report
            self._health_reports[name] = report
            self._health_status[name] = report.ok
            if not report.ok and source.config.auto_disable_on_fail:
                source.config.enabled = False

        return reports

    @staticmethod
    def _is_official_portal_catalog_source(source: BaseDataSource) -> bool:
        custom = getattr(getattr(source, "config", None), "custom", {}) or {}
        return str(custom.get("provider_type") or "") == "official_portal_catalog"

    @staticmethod
    def _official_portal_manual_gate_health_report(source: BaseDataSource, endpoint: str) -> HealthReport:
        config = getattr(source, "config", None)
        custom = getattr(config, "custom", {}) or {}
        auth = getattr(config, "auth", None)
        challenge_provider = str(getattr(auth, "challenge_provider", "") or "")
        parser_status = str(custom.get("parser_status") or "pending")
        accepted_page_statuses = custom.get("accepted_page_statuses") or []
        if not isinstance(accepted_page_statuses, list):
            accepted_page_statuses = []
        health_semantics = str(custom.get("health_semantics") or "manual_catalog")
        provider = challenge_provider or "none"
        return HealthReport(
            source_name=getattr(source, "name", ""),
            source_type=getattr(source, "type_name", ""),
            ok=True,
            status="manual_gate",
            endpoint=endpoint,
            latency_ms=0.0,
            detail=(
                "official portal requires browser handoff or a validated page snapshot; "
                "live connectivity is not treated as production health"
            ),
            auth_challenge={
                "type": "official_portal_manual_gate",
                "source": getattr(source, "name", ""),
                "details": {
                    "provider": provider,
                    "parser_status": parser_status,
                    "health_semantics": health_semantics,
                    "accepted_page_statuses": [str(item) for item in accepted_page_statuses],
                    "automation_enabled": False,
                },
            },
        )

    def available_sources(
        self,
        filter_types: Optional[List[str]] = None,
    ) -> List[BaseDataSource]:
        """Return enabled and healthy sources ordered by priority."""
        sources = [
            source
            for source in self._sources.values()
            if source.config.enabled
            and (filter_types is None or source.type_name in filter_types)
            and self._health_status.get(source.name, True)
        ]
        return sorted(sources, key=lambda source: (source.config.priority, source.name))
    
    async def _check_single_connectivity(self, name: str, source: BaseDataSource) -> bool:
        """
        检测单个数据源的可达性
        
        Args:
            name: 数据源名称
            source: 数据源实例
            
        Returns:
            是否可达
        """
        ping_url = source.config.ping_endpoint or source.config.base_url
        ping_timeout = source.config.ping_timeout
        headers = getattr(source.config, "headers", {}) or {}
        
        try:
            # 使用 aiohttp 发送 HEAD 请求检测可达性
            import aiohttp
            
            timeout = aiohttp.ClientTimeout(total=ping_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    # 尝试发送 HEAD 请求
                    async with session.head(ping_url, headers=headers) as response:
                        # 2xx, 3xx 都算可达
                        if response.status < 400:
                            return True
                        raise QueryError("HEAD connectivity probe returned non-success")
                except Exception:
                    # HEAD 请求失败，尝试 GET 请求 (部分 API 不支持 HEAD)
                    async with session.get(ping_url, headers=headers) as response:
                        return response.status < 400
        except asyncio.TimeoutError:
            self.logger.debug(
                "connectivity check timed out: source=%s endpoint=%s timeout_seconds=%s",
                name,
                _safe_url_for_diagnostics(ping_url),
                ping_timeout,
            )
            return False
        except aiohttp.ClientError as e:
            self.logger.debug(
                "connectivity check client error: source=%s error_type=%s endpoint=%s",
                name,
                type(e).__name__,
                _safe_url_for_diagnostics(ping_url),
            )
            return False
        except Exception as e:
            self.logger.debug(
                "connectivity check failed: source=%s error_type=%s endpoint=%s",
                name,
                type(e).__name__,
                _safe_url_for_diagnostics(ping_url),
            )
            return False
    
    def get_source(self, name: str) -> Optional[BaseDataSource]:
        """
        获取指定数据源
        
        Args:
            name: 数据源名称
            
        Returns:
            数据源实例
        """
        return self._sources.get(name)
    
    def get_sources_by_type(self, type_name: str) -> List[BaseDataSource]:
        """
        获取指定类型的所有数据源
        
        Args:
            type_name: 数据源类型
            
        Returns:
            数据源实例列表
        """
        return [s for s in self._sources.values() if s.type_name == type_name]
    
    def list_sources(self) -> List[str]:
        """
        列出所有已加载的数据源名称
        
        Returns:
            数据源名称列表
        """
        return list(self._sources.keys())
    
    # =========================================================================
    # 查询方法 (带缓存)
    # =========================================================================
    
    async def query_single(
        self, 
        source_name: str, 
        request: QueryRequest,
        use_cache: bool = True
    ) -> QueryResult[Any]:
        """
        查询单个数据源
        
        Args:
            source_name: 数据源名称
            request: 查询请求
            use_cache: 是否使用缓存
            
        Returns:
            查询结果
        """
        source = self.get_source(source_name)
        if not source:
            return QueryResult(
                source_name=source_name,
                source_type="unknown",
                status=QueryStatus.FAILED,
                error=DataSourceError(f"数据源未找到: {source_name}")
            )
        
        # Check cache
        if use_cache and source.config.cache_enabled:
            cache_key = f"{source_name}:{request.cache_key()}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Execute query
        result = await source.query(request)
        
        # Cache result
        if use_cache and source.config.cache_enabled and result.is_success:
            cache_key = f"{source_name}:{request.cache_key()}"
            self._cache.set(cache_key, result, ttl=source.config.cache_ttl)
        
        return result
    
    async def query_multiple(
        self, 
        source_names: List[str], 
        request: QueryRequest,
        concurrency: int = 10,
        use_cache: bool = True
    ) -> AggregatedResult[Any]:
        """
        并发查询多个数据源
        
        Args:
            source_names: 数据源名称列表
            request: 查询请求
            concurrency: 并发数
            use_cache: 是否使用缓存
            
        Returns:
            聚合结果
        """
        # SECURITY FIX F-004: Add concurrency and source count limits
        if concurrency > self.MAX_CONCURRENCY:
            raise ValueError(f"并发数不能超过 {self.MAX_CONCURRENCY}")
        
        if len(source_names) > self.MAX_SOURCES:
            self.logger.warning(f"数据源数量超过限制，仅查询前 {self.MAX_SOURCES} 个")
            source_names = source_names[:self.MAX_SOURCES]
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(min(concurrency, self.MAX_CONCURRENCY))
        
        async def _query_with_semaphore(source_name: str) -> QueryResult[Any]:
            async with semaphore:
                return await self.query_single(source_name, request, use_cache)
        
        # 并发执行查询
        tasks = [_query_with_semaphore(name) for name in source_names]
        results = await asyncio.gather(*tasks)
        
        return AggregatedResult(results=list(results))
    
    async def query_all(
        self, 
        request: QueryRequest,
        filter_types: Optional[List[str]] = None,
        concurrency: int = 10,
        use_cache: bool = True
    ) -> AggregatedResult[Any]:
        """
        查询所有数据源
        
        Args:
            request: 查询请求
            filter_types: 按类型过滤数据源
            concurrency: 并发数
            use_cache: 是否使用缓存
            
        Returns:
            聚合结果
        """
        source_names = [
            name for name, source in self._sources.items()
            if filter_types is None or source.type_name in filter_types
        ]
        
        return await self.query_multiple(source_names, request, concurrency, use_cache)

    async def query_available(
        self,
        request: QueryRequest,
        filter_types: Optional[List[str]] = None,
        concurrency: int = 10,
        use_cache: bool = True
    ) -> AggregatedResult[Any]:
        """
        Query only enabled sources that passed the latest connectivity check.

        This is the production-safe default path for user-facing retrieval:
        configured endpoints are health-checked at startup, then routing avoids
        sources known to be down or auto-disabled.
        """
        source_names = [source.name for source in self.available_sources(filter_types)]
        return await self.query_multiple(source_names, request, concurrency, use_cache)
    
    async def query_by_priority(
        self, 
        request: QueryRequest,
        max_sources: int = 3,
        concurrency: int = 10,
        use_cache: bool = True
    ) -> AggregatedResult[Any]:
        """
        按优先级查询数据源 (查询最快成功的 N 个)
        
        Args:
            request: 查询请求
            max_sources: 最大查询数据源数量
            concurrency: 并发数
            use_cache: 是否使用缓存
            
        Returns:
            聚合结果
        """
        # 按优先级排序
        sorted_sources = sorted(
            self._sources.values(),
            key=lambda s: s.config.priority
        )
        
        source_names = [s.name for s in sorted_sources[:max_sources]]
        return await self.query_multiple(source_names, request, concurrency, use_cache)
    
    # =========================================================================
    # 健康检查
    # =========================================================================
    
    async def health_check_all(self) -> Dict[str, bool]:
        """
        检查所有数据源的健康状态
        
        Returns:
            数据源名称 -> 健康状态
        """
        reports = await self.health_report_all()
        return {name: report.ok for name, report in reports.items()}
    
    # =========================================================================
    # 缓存管理
    # =========================================================================
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self.logger.info("已清空缓存")
    
    def cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self._cache.stats()
    
    # =========================================================================
    # 清理资源
    # =========================================================================
    
    async def close(self) -> None:
        """
        关闭所有数据源 (清理资源)
        """
        for name, source in self._sources.items():
            if hasattr(source, 'close'):
                try:
                    await source.close()
                    self.logger.debug(f"已关闭数据源: {name}")
                except Exception as e:
                    self.logger.error(f"关闭数据源失败 {name}: {e}")

# =============================================================================
# 9. 单例模式搜索引擎 (Singleton Search Engine)
# =============================================================================

class SearchEngine:
    """
    搜索引擎 - 单例模式
    
    提供全局统一的检索入口，支持:
    - 单例模式 (全局唯一实例)
    - 同步/异步双接口
    - 自动初始化
    - 缓存机制
    - 异常处理
    
    使用示例:
        ```python
        # 初始化 (系统启动时调用一次)
        await SearchEngine.initialize("datasources.yaml")
        
        # 异步调用
        result = await SearchEngine.search("github_api", "users/octocat")
        
        # 同步调用
        result = SearchEngine.search_sync("github_api", "users/octocat")
        ```
    """
    
    _instance: Optional['SearchEngine'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        构造函数 (私有化)
        
        注意: 不要直接调用 SearchEngine()，而应该使用:
        1. await SearchEngine.initialize("datasources.yaml")  # 推荐
        2. SearchEngine.get_instance()  # 获取已初始化的实例
        
        如果直接调用 SearchEngine()，会得到一个未初始化的实例，
        调用搜索方法时会抛出 ConfigError。
        """
        if not hasattr(self, '_initialized'):
            self._manager: Optional[DataSourceManager] = None
            self._config_path: Optional[Path] = None
            self._initialized = False
            self._init_lock = asyncio.Lock()
    
    @classmethod
    async def initialize(
        cls, 
        config_path: Union[str, Path],
        auto_initialize_sources: bool = True
    ) -> 'SearchEngine':
        """
        初始化搜索引擎 (单例模式)
        
        Args:
            config_path: 配置文件路径
            auto_initialize_sources: 是否自动初始化数据源
            
        Returns:
            SearchEngine 实例
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            
            instance = cls._instance
            
            if not instance._initialized:
                instance._config_path = Path(config_path)
                instance._manager = DataSourceManager(config_path)
                instance._manager.load_config()
                
                if auto_initialize_sources:
                    # 使用 initialize_and_check() 自动检测可达性
                    await instance._manager.initialize_and_check()
                
                instance._initialized = True
                
                logging.getLogger("SearchEngine").info(
                    f"搜索引擎初始化完成: {len(instance._manager.list_sources())} 个数据源"
                )
            
            return instance
    
    @classmethod
    def get_instance(cls) -> Optional['SearchEngine']:
        """
        获取搜索引擎实例 (不自动初始化)
        
        注意: 如果搜索引擎未初始化，返回 None。
        推荐使用方式:
        1. 先初始化: await SearchEngine.initialize("datasources.yaml")
        2. 再获取: instance = SearchEngine.get_instance()
        
        Returns:
            SearchEngine 实例，未初始化返回 None
            
        Raises:
            ConfigError: 当搜索引擎未初始化时，调用搜索方法会抛出此异常
        """
        return cls._instance if cls._instance and cls._instance._initialized else None
    
    @classmethod
    async def search(
        cls,
        source_name: str,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        **kwargs
    ) -> QueryResult[Any]:
        """
        异步搜索 - 全局统一入口
        
        Args:
            source_name: 数据源名称
            query: 查询字符串
            params: 查询参数
            use_cache: 是否使用缓存
            **kwargs: 其他查询选项 (headers, filters, sort, pagination)
            
        Returns:
            查询结果
            
        使用示例:
            ```python
            result = await SearchEngine.search("github_api", "users/octocat")
            if result.is_success:
                print(result.data)
            ```
        """
        instance = cls.get_instance()
        if not instance:
            raise ConfigError("搜索引擎未初始化，请先调用 SearchEngine.initialize()")
        
        request = QueryRequest(
            query=query,
            params=params or {},
            **kwargs
        )
        
        return await instance._manager.query_single(source_name, request, use_cache)
    
    @classmethod
    def search_sync(
        cls,
        source_name: str,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        **kwargs
    ) -> QueryResult[Any]:
        """
        同步搜索 - 全局统一入口
        
        Args:
            source_name: 数据源名称
            query: 查询字符串
            params: 查询参数
            use_cache: 是否使用缓存
            **kwargs: 其他查询选项
            
        Returns:
            查询结果
            
        使用示例:
            ```python
            result = SearchEngine.search_sync("github_api", "users/octocat")
            if result.is_success:
                print(result.data)
            ```
        """
        # Run async function in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is already running, create task
            future = asyncio.ensure_future(
                cls.search(source_name, query, params, use_cache, **kwargs)
            )
            return loop.run_until_complete(future)
        else:
            return loop.run_until_complete(
                cls.search(source_name, query, params, use_cache, **kwargs)
            )
    
    @classmethod
    async def search_all(
        cls,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        filter_types: Optional[List[str]] = None,
        concurrency: int = 10,
        use_cache: bool = True,
        **kwargs
    ) -> AggregatedResult[Any]:
        """
        异步搜索 - 查询所有数据源
        
        Args:
            query: 查询字符串
            params: 查询参数
            filter_types: 按类型过滤数据源
            concurrency: 并发数
            use_cache: 是否使用缓存
            **kwargs: 其他查询选项
            
        Returns:
            聚合查询结果
        """
        instance = cls.get_instance()
        if not instance:
            raise ConfigError("搜索引擎未初始化，请先调用 SearchEngine.initialize()")
        
        request = QueryRequest(
            query=query,
            params=params or {},
            **kwargs
        )
        
        return await instance._manager.query_all(request, filter_types, concurrency, use_cache)

    @classmethod
    async def search_available(
        cls,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        filter_types: Optional[List[str]] = None,
        concurrency: int = 10,
        use_cache: bool = True,
        **kwargs
    ) -> AggregatedResult[Any]:
        """Search through the currently healthy sources only."""
        instance = cls.get_instance()
        if not instance:
            raise ConfigError("Search engine is not initialized; call SearchEngine.initialize() first")

        request = QueryRequest(
            query=query,
            params=params or {},
            **kwargs
        )

        return await instance._manager.query_available(request, filter_types, concurrency, use_cache)
    
    @classmethod
    def search_all_sync(
        cls,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        filter_types: Optional[List[str]] = None,
        concurrency: int = 10,
        use_cache: bool = True,
        **kwargs
    ) -> AggregatedResult[Any]:
        """
        同步搜索 - 查询所有数据源
        
        Args:
            query: 查询字符串
            params: 查询参数
            filter_types: 按类型过滤数据源
            concurrency: 并发数
            use_cache: 是否使用缓存
            **kwargs: 其他查询选项
            
        Returns:
            聚合查询结果
        """
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(
                cls.search_all(query, params, filter_types, concurrency, use_cache, **kwargs)
            )
            return loop.run_until_complete(future)
        else:
            return loop.run_until_complete(
                cls.search_all(query, params, filter_types, concurrency, use_cache, **kwargs)
            )
    
    @classmethod
    def list_sources(cls) -> List[str]:
        """
        列出所有已加载的数据源
        
        Returns:
            数据源名称列表
        """
        instance = cls.get_instance()
        if not instance:
            return []
        return instance._manager.list_sources()

    @classmethod
    def available_sources(cls, filter_types: Optional[List[str]] = None) -> List[str]:
        """列出当前可用且健康的数据源。"""
        instance = cls.get_instance()
        if not instance:
            return []
        return [source.name for source in instance._manager.available_sources(filter_types)]
    
    @classmethod
    def health_check(cls) -> Dict[str, bool]:
        """
        健康检查 (同步版本)
        
        Returns:
            数据源名称 -> 健康状态
        """
        instance = cls.get_instance()
        if not instance:
            return {}
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(instance._manager.health_check_all())
            return loop.run_until_complete(future)
        else:
            return loop.run_until_complete(instance._manager.health_check_all())
    
    @classmethod
    def clear_cache(cls) -> None:
        """清空缓存"""
        instance = cls.get_instance()
        if instance:
            instance._manager.clear_cache()
    
    @classmethod
    def cache_stats(cls) -> Dict[str, Any]:
        """获取缓存统计"""
        instance = cls.get_instance()
        if not instance:
            return {}
        return instance._manager.cache_stats()
    
    @classmethod
    async def close(cls) -> None:
        """关闭搜索引擎"""
        instance = cls.get_instance()
        if instance and instance._manager:
            await instance._manager.close()
            cls._instance = None
            logging.getLogger("SearchEngine").info("搜索引擎已关闭")

# =============================================================================
# 10. 结果聚合器 (Result Aggregator)
# =============================================================================

class ResultAggregator:
    """
    结果聚合器
    
    提供多种结果聚合策略
    """
    
    @staticmethod
    def merge_list(results: List[QueryResult[Any]]) -> List[Any]:
        """
        合并列表结果
        
        Args:
            results: 查询结果列表
            
        Returns:
            合并后的列表
        """
        merged = []
        for result in results:
            if result.is_success and result.data is not None:
                if isinstance(result.data, list):
                    merged.extend(result.data)
                else:
                    merged.append(result.data)
        return merged
    
    @staticmethod
    def merge_dict(results: List[QueryResult[Any]]) -> Dict[str, Any]:
        """
        合并字典结果
        
        Args:
            results: 查询结果列表
            
        Returns:
            合并后的字典
        """
        merged = {}
        for result in results:
            if result.is_success and isinstance(result.data, dict):
                merged.update(result.data)
        return merged
    
    @staticmethod
    def rank_by_source(
        aggregated: AggregatedResult[Any],
        strategy: str = "priority"
    ) -> List[QueryResult[Any]]:
        """
        按策略对结果排序
        
        Args:
            aggregated: 聚合结果
            strategy: 排序策略 (priority/time/source_name)
            
        Returns:
            排序后的结果列表
        """
        if strategy == "priority":
            # 按数据源优先级排序 (需要在 manager 中查找)
            return sorted(
                aggregated.results,
                key=lambda r: (not r.is_success, r.source_name)
            )
        elif strategy == "time":
            return sorted(
                aggregated.results,
                key=lambda r: r.query_time
            )
        elif strategy == "source_name":
            return sorted(
                aggregated.results,
                key=lambda r: r.source_name
            )
        else:
            return aggregated.results

# =============================================================================
# 11. 完整使用示例 (Complete Usage Examples)
# =============================================================================

# =============================================================================
# 示例 1: 系统启动 → 初始化 → 随时调用 (推荐用法)
# =============================================================================

async def example_1_system_startup():
    """
    示例 1: 系统启动时初始化，之后随时调用
    
    这是推荐的使用方式，适合生产环境
    """
    print("=" * 60)
    print("示例 1: 系统启动 → 初始化 → 随时调用")
    print("=" * 60)
    
    # =========================================================================
    # 步骤 1: 系统启动时初始化 (只需执行一次)
    # =========================================================================
    print("\n[步骤 1] 系统启动，初始化搜索引擎...")
    
    await SearchEngine.initialize("datasources.yaml")
    
    print("✅ 搜索引擎初始化完成")
    print(f"   已加载数据源: {SearchEngine.list_sources()}")
    
    # =========================================================================
    # 步骤 2: 随时调用检索 (系统内任何地方都可以调用)
    # =========================================================================
    print("\n[步骤 2] 随时调用检索...")
    
    # 示例 2.1: 异步调用 (推荐，性能最好)
    print("\n  [2.1] 异步调用示例:")
    result = await SearchEngine.search("jsonplaceholder", "posts/1")
    if result.is_success:
        print(f"    ✅ 查询成功: {result.data}")
    else:
        print(f"    ❌ 查询失败: {result.error}")
    
    # 示例 2.2: 同步调用 (适合不支持 async 的环境)
    print("\n  [2.2] 同步调用示例:")
    result = SearchEngine.search_sync("jsonplaceholder", "posts/2")
    if result.is_success:
        print(f"    ✅ 查询成功: {result.data}")
    else:
        print(f"    ❌ 查询失败: {result.error}")
    
    # 示例 2.3: 查询所有数据源
    print("\n  [2.3] 查询所有数据源:")
    aggregated = await SearchEngine.search_all("posts/1", concurrency=5)
    print(f"    成功: {aggregated.successful_count}")
    print(f"    失败: {aggregated.failed_count}")
    print(f"    成功率: {aggregated.success_rate:.2%}")
    
    # 示例 2.4: 使用缓存 (第二次查询会命中缓存)
    print("\n  [2.4] 缓存示例:")
    start = time.time()
    result1 = await SearchEngine.search("jsonplaceholder", "posts/1", use_cache=True)
    time1 = time.time() - start
    print(f"    第一次查询: {time1:.3f}秒")
    
    start = time.time()
    result2 = await SearchEngine.search("jsonplaceholder", "posts/1", use_cache=True)
    time2 = time.time() - start
    print(f"    第二次查询 (缓存): {time2:.3f}秒")
    print(f"    缓存加速: {time1/time2:.1f}x")
    
    # =========================================================================
    # 步骤 3: 查看系统状态
    # =========================================================================
    print("\n[步骤 3] 系统状态:")
    print(f"   缓存统计: {SearchEngine.cache_stats()}")
    print(f"   健康状态: {SearchEngine.health_check()}")
    
    # =========================================================================
    # 步骤 4: 系统关闭时清理资源 (可选)
    # =========================================================================
    print("\n[步骤 4] 系统关闭，清理资源...")
    await SearchEngine.close()
    print("✅ 搜索引擎已关闭")

# =============================================================================
# 示例 2: 一行代码调用 (极简用法)
# =============================================================================

async def example_2_one_liner():
    """
    示例 2: 一行代码调用
    
    适合快速原型开发、脚本、REPL 等场景
    """
    print("\n" + "=" * 60)
    print("示例 2: 一行代码调用")
    print("=" * 60)
    
    # 初始化 (只需一次)
    await SearchEngine.initialize("datasources.yaml")
    
    # 一行代码查询
    result = await SearchEngine.search("jsonplaceholder", "posts/1")
    
    # 一行代码处理结果
    print(f"\n查询结果: {result.data if result.is_success else result.error}")

# =============================================================================
# 示例 3: 在现有系统中集成
# =============================================================================

async def example_3_integration():
    """
    示例 3: 在现有系统中集成
    
    展示如何将搜索引擎集成到现有系统
    """
    print("\n" + "=" * 60)
    print("示例 3: 在现有系统中集成")
    print("=" * 60)
    
    # 假设这是一个现有的信息检索系统
    class InformationRetrievalSystem:
        """
        现有信息检索系统
        """
        
        def __init__(self, config_path: str):
            self.config_path = config_path
            self.initialized = False
        
        async def initialize(self):
            """系统初始化"""
            if not self.initialized:
                await SearchEngine.initialize(self.config_path)
                self.initialized = True
                print("✅ 信息检索系统初始化完成")
        
        async def search(self, query: str, sources: Optional[List[str]] = None):
            """
            系统统一的搜索接口
            
            上层调用只需关心这个接口，无需关心底层数据源差异
            """
            if not self.initialized:
                await self.initialize()
            
            if sources:
                # 查询指定的数据源
                results = []
                for source in sources:
                    result = await SearchEngine.search(source, query)
                    results.append(result)
                return results
            else:
                # 查询所有数据源
                return await SearchEngine.search_all(query)
    
    # 使用现有系统
    print("\n[集成示例] 在现有系统中使用:")
    irs = InformationRetrievalSystem("datasources.yaml")
    
    # 初始化
    await irs.initialize()
    
    # 使用系统的统一接口查询
    results = await irs.search("posts/1")
    print(f"查询结果: {len(results.get_successful_data())} 条数据")

# =============================================================================
# 12. 主程序入口 (Main Entry Point)
# =============================================================================

if __name__ == "__main__":
    """
    主程序入口
    
    使用示例:
        python -m multi_datasource
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="多数据源接入模块 - 标准内置组件")
    parser.add_argument("--config", type=str, default="datasources.yaml", help="配置文件路径")
    parser.add_argument("--example", type=int, default=1, choices=[1, 2, 3], help="运行示例编号")
    parser.add_argument("--query", type=str, help="查询字符串")
    parser.add_argument("--source", type=str, help="指定数据源名称")
    parser.add_argument("--all", action="store_true", help="查询所有数据源")
    
    args = parser.parse_args()
    
    async def main():
        # 初始化
        await SearchEngine.initialize(args.config)
        
        if args.query:
            # 命令行查询模式
            if args.source:
                result = await SearchEngine.search(args.source, args.query)
                print(f"结果: {result.to_dict()}")
            elif args.all:
                aggregated = await SearchEngine.search_all(args.query)
                print(f"聚合结果: {aggregated.to_dict()}")
            else:
                print("请指定 --source 或 --all")
        else:
            # 运行示例
            if args.example == 1:
                await example_1_system_startup()
            elif args.example == 2:
                await example_2_one_liner()
            elif args.example == 3:
                await example_3_integration()
        
        # 关闭
        await SearchEngine.close()
    
    asyncio.run(main())
