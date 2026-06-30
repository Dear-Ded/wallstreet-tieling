#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 统一异常类

定义项目所有异常类型，支持结构化错误信息和错误码。
"""
from __future__ import annotations

from typing import Any, Optional


class WallStreetError(Exception):
    """所有 wallstreet-tieling 异常的基类"""
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN",
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        super().__init__(message)
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self) -> dict:
        """转换为字典（用于 API 响应或日志）"""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ── 配置错误 ────────────────────────────────────────────────────────────

class ConfigError(WallStreetError):
    """配置错误（缺失、格式错误、验证失败）"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="CONFIG_ERROR",
            **kwargs,
        )


class MissingConfigError(ConfigError):
    """缺少必需配置"""
    
    def __init__(self, config_key: str, **kwargs):
        super().__init__(
            message=f"缺少必需配置: {config_key}",
            details={"config_key": config_key},
            **kwargs,
        )
        self.error_code = "MISSING_CONFIG"


class InvalidConfigError(ConfigError):
    """配置值无效"""
    
    def __init__(self, config_key: str, value: Any, reason: str, **kwargs):
        super().__init__(
            message=f"配置值无效: {config_key}={value} ({reason})",
            details={"config_key": config_key, "value": str(value), "reason": reason},
            **kwargs,
        )
        self.error_code = "INVALID_CONFIG"


# ── API 错误 ─────────────────────────────────────────────────────────────

class APIError(WallStreetError):
    """API 调用错误（所有 LLM API 错误的基类）"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="API_ERROR",
            **kwargs,
        )


class APIKeyError(APIError):
    """API Key 无效或缺失"""
    
    def __init__(self, **kwargs):
        super().__init__(
            message="API Key 无效或缺失",
            **kwargs,
        )
        self.error_code = "API_KEY_ERROR"


class APIRateLimitError(APIError):
    """API 速率限制"""
    
    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        message = "API 速率限制"
        if retry_after:
            message += f"，建议 {retry_after} 秒后重试"
        super().__init__(
            message=message,
            details={"retry_after": retry_after},
            **kwargs,
        )
        self.error_code = "API_RATE_LIMIT"


class APITimeoutError(APIError):
    """API 调用超时"""
    
    def __init__(self, timeout: int, **kwargs):
        super().__init__(
            message=f"API 调用超时 ({timeout}秒)",
            details={"timeout": timeout},
            **kwargs,
        )
        self.error_code = "API_TIMEOUT"


class APIResponseError(APIError):
    """API 响应格式错误"""
    
    def __init__(self, response: Any, **kwargs):
        super().__init__(
            message=f"API 响应格式错误: {type(response).__name__}",
            details={"response": str(response)[:200]},
            **kwargs,
        )
        self.error_code = "API_RESPONSE_ERROR"


# ── 数据源错误 ─────────────────────────────────────────────────────────

class DataSourceError(WallStreetError):
    """数据源错误（所有数据源异常的基类）"""
    
    def __init__(self, message: str, source_name: Optional[str] = None, **kwargs):
        details = kwargs.get("details", {})
        details["source_name"] = source_name
        kwargs["details"] = details
        super().__init__(
            message=message,
            error_code="DATASOURCE_ERROR",
            **kwargs,
        )
        self.source_name = source_name


class DataSourceConnectionError(DataSourceError):
    """数据源连接失败"""
    
    def __init__(self, source_name: str, url: str, **kwargs):
        super().__init__(
            message=f"数据源连接失败: {source_name} ({url})",
            source_name=source_name,
            details={"url": url},
            **kwargs,
        )
        self.error_code = "DATASOURCE_CONNECTION_ERROR"


class DataSourceTimeoutError(DataSourceError):
    """数据源请求超时"""
    
    def __init__(self, source_name: str, timeout: int, **kwargs):
        super().__init__(
            message=f"数据源请求超时: {source_name} ({timeout}秒)",
            source_name=source_name,
            details={"timeout": timeout},
            **kwargs,
        )
        self.error_code = "DATASOURCE_TIMEOUT"


class DataSourceParseError(DataSourceError):
    """数据源响应解析失败"""
    
    def __init__(self, source_name: str, response: Any, **kwargs):
        super().__init__(
            message=f"数据源响应解析失败: {source_name}",
            source_name=source_name,
            details={"response": str(response)[:200]},
            **kwargs,
        )
        self.error_code = "DATASOURCE_PARSE_ERROR"


# ── Agent 错误 ──────────────────────────────────────────────────────────

class AgentError(WallStreetError):
    """Agent 执行错误（所有 Agent 异常的基类）"""
    
    def __init__(self, message: str, agent_id: Optional[str] = None, **kwargs):
        details = kwargs.get("details", {})
        details["agent_id"] = agent_id
        kwargs["details"] = details
        super().__init__(
            message=message,
            error_code="AGENT_ERROR",
            **kwargs,
        )
        self.agent_id = agent_id


class AgentTimeoutError(AgentError):
    """Agent 执行超时"""
    
    def __init__(self, agent_id: str, timeout: int, **kwargs):
        super().__init__(
            message=f"Agent 执行超时: {agent_id} ({timeout}秒)",
            agent_id=agent_id,
            details={"timeout": timeout},
            **kwargs,
        )
        self.error_code = "AGENT_TIMEOUT"


class AgentBudgetExceededError(AgentError):
    """Agent Token 预算超限"""
    
    def __init__(self, agent_id: str, budget: int, used: int, **kwargs):
        super().__init__(
            message=f"Agent Token 预算超限: {agent_id} (预算={budget}, 已用={used})",
            agent_id=agent_id,
            details={"budget": budget, "used": used},
            **kwargs,
        )
        self.error_code = "AGENT_BUDGET_EXCEEDED"


class AgentQualityError(AgentError):
    """Agent 输出质量不达标"""
    
    def __init__(self, agent_id: str, violations: list[str], **kwargs):
        super().__init__(
            message=f"Agent 输出质量不达标: {agent_id} ({len(violations)} 项违规)",
            agent_id=agent_id,
            details={"violations": violations},
            **kwargs,
        )
        self.error_code = "AGENT_QUALITY_ERROR"


# ── 报告生成错误 ────────────────────────────────────────────────────────

class ReportError(WallStreetError):
    """报告生成错误"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="REPORT_ERROR",
            **kwargs,
        )


class ReportFormatError(ReportError):
    """报告格式错误"""
    
    def __init__(self, format: str, **kwargs):
        super().__init__(
            message=f"报告格式不支持: {format}",
            details={"format": format},
            **kwargs,
        )
        self.error_code = "REPORT_FORMAT_ERROR"


class ReportEmptyError(ReportError):
    """报告内容为空"""
    
    def __init__(self, target: str, **kwargs):
        super().__init__(
            message=f"报告内容为空: {target}",
            details={"target": target},
            **kwargs,
        )
        self.error_code = "REPORT_EMPTY"


# ── 工具错误 ────────────────────────────────────────────────────────────

class ToolError(WallStreetError):
    """工具调用错误"""
    
    def __init__(self, message: str, tool_name: Optional[str] = None, **kwargs):
        details = kwargs.get("details", {})
        details["tool_name"] = tool_name
        kwargs["details"] = details
        super().__init__(
            message=message,
            error_code="TOOL_ERROR",
            **kwargs,
        )
        self.tool_name = tool_name


class ToolNotFoundError(ToolError):
    """工具不存在"""
    
    def __init__(self, tool_name: str, **kwargs):
        super().__init__(
            message=f"工具不存在: {tool_name}",
            tool_name=tool_name,
            **kwargs,
        )
        self.error_code = "TOOL_NOT_FOUND"


class ToolExecutionError(ToolError):
    """工具执行失败"""
    
    def __init__(self, tool_name: str, reason: str, **kwargs):
        super().__init__(
            message=f"工具执行失败: {tool_name} ({reason})",
            tool_name=tool_name,
            details={"reason": reason},
            **kwargs,
        )
        self.error_code = "TOOL_EXECUTION_ERROR"


# ── 验证错误 ────────────────────────────────────────────────────────────

class ValidationError(WallStreetError):
    """数据验证错误"""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        details = kwargs.get("details", {})
        details["field"] = field
        kwargs["details"] = details
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            **kwargs,
        )
        self.field = field


# ── 导出列表 ────────────────────────────────────────────────────────────

__all__ = [
    # 基类
    "WallStreetError",
    
    # 配置错误
    "ConfigError",
    "MissingConfigError",
    "InvalidConfigError",
    
    # API 错误
    "APIError",
    "APIKeyError",
    "APIRateLimitError",
    "APITimeoutError",
    "APIResponseError",
    
    # 数据源错误
    "DataSourceError",
    "DataSourceConnectionError",
    "DataSourceTimeoutError",
    "DataSourceParseError",
    
    # Agent 错误
    "AgentError",
    "AgentTimeoutError",
    "AgentBudgetExceededError",
    "AgentQualityError",
    
    # 报告错误
    "ReportError",
    "ReportFormatError",
    "ReportEmptyError",
    
    # 工具错误
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    
    # 验证错误
    "ValidationError",
]
