#!/usr/bin/env python3
"""wallstreet-tieling v0.5.0 统一错误处理装饰器

提供统一的错误处理、重试、日志、验证功能。
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Optional, Type, Union

from .exceptions import WallStreetError, ConfigError, APIError, DataSourceError

logger = logging.getLogger("wst.decorators")


# ── 默认异常处理 ────────────────────────────────────────────────────────

def _default_exception_handler(func: Callable, e: Exception, *args, **kwargs) -> Any:
    """默认异常处理函数"""
    logger.error(f"❌ {func.__name__} 执行失败: {e}")
    if isinstance(e, WallStreetError):
        logger.error(f"  错误码: {e.error_code}")
        logger.error(f"  详情: {e.details}")
    return None


# ── 错误处理装饰器 ──────────────────────────────────────────────────────

def handle_errors(
    exceptions: Any = Exception,
    handler: Optional[Callable] = None,
    log_traceback: bool = True,
    reraise: bool = False,
    default_return: Any = None,
):
    """
    统一错误处理装饰器。
    
    用法:
        @handle_errors(exceptions=(APIError, DataSourceError), default_return=[])
        def fetch_data():
            ...
    
    Args:
        exceptions: 要捕获的异常类型（单个或元组）
        handler: 自定义异常处理函数（可选）
        log_traceback: 是否记录完整的 traceback
        reraise: 是否重新抛出异常（False 则返回 default_return）
        default_return: 发生异常时的默认返回值
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                # 使用自定义处理器或默认处理器
                if handler:
                    handler(func, e, *args, **kwargs)
                else:
                    _default_exception_handler(func, e, *args, **kwargs)
                
                # 记录 traceback
                if log_traceback:
                    logger.error("详细错误信息:", exc_info=True)
                
                # 是否重新抛出
                if reraise:
                    raise
                
                # 返回默认值
                return default_return
        
        return wrapper
    
    return decorator


# ── 重试装饰器 ─────────────────────────────────────────────────────────

def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Any = Exception,
    on_retry: Optional[Callable] = None,
):
    """
    自动重试装饰器（支持指数退避）。
    
    用法:
        @retry_on_error(max_retries=3, delay=1.0, exceptions=APIError)
        def call_api():
            ...
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 退避倍数（每次重试后延迟乘以 backoff）
        exceptions: 触发重试的异常类型
        on_retry: 重试时的回调函数（可选，用于日志或通知）
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # 调用重试回调
                        if on_retry:
                            on_retry(func, attempt + 1, max_retries, e)
                        else:
                            logger.warning(
                                f"⚠️  {func.__name__} 第 {attempt + 1} 次尝试失败: {e}，"
                                f" {current_delay}秒后重试..."
                            )
                        
                        # 等待后重试
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        # 超过最大重试次数
                        logger.error(
                            f"❌ {func.__name__} 重试 {max_retries} 次后仍然失败: {e}"
                        )
                        raise
            
            # 理论上不会到这里
            raise last_exception
        
        return wrapper
    
    return decorator


# ── 输入验证装饰器 ──────────────────────────────────────────────────────

def validate_input(
    validators: Optional[dict[str, Callable]] = None,
    raise_on_error: bool = True,
):
    """
    输入验证装饰器。
    
    用法:
        @validate_input(validators={"target": lambda x: isinstance(x, str) and len(x) > 0})
        def analyze(target: str):
            ...
    
    Args:
        validators: 参数名 → 验证函数的字典
        raise_on_error: 验证失败时是否抛出异常（False 则返回 None）
    """
    def decorator(func: Callable):
        import inspect
        
        sig = inspect.signature(func)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 绑定参数
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # 验证参数
            if validators:
                for param_name, validator in validators.items():
                    if param_name in bound_args.arguments:
                        value = bound_args.arguments[param_name]
                        try:
                            if not validator(value):
                                error_msg = f"参数验证失败: {param_name}={value}"
                                logger.error(error_msg)
                                if raise_on_error:
                                    from .exceptions import ValidationError
                                    raise ValidationError(error_msg, field=param_name)
                                else:
                                    return None
                        except Exception as e:
                            error_msg = f"验证函数执行失败: {param_name} ({e})"
                            logger.error(error_msg)
                            if raise_on_error:
                                raise
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# ── 执行日志装饰器 ──────────────────────────────────────────────────────

def log_execution(
    log_level: str = "INFO",
    log_args: bool = True,
    log_result: bool = False,
    log_execution_time: bool = True,
):
    """
    执行日志装饰器（记录函数调用、参数、返回值、执行时间）。
    
    用法:
        @log_execution(log_level="DEBUG", log_args=True, log_result=False)
        def expensive_operation():
            ...
    
    Args:
        log_level: 日志级别（DEBUG / INFO / WARNING / ERROR）
        log_args: 是否记录输入参数
        log_result: 是否记录返回值
        log_execution_time: 是否记录执行时间
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            log_func = getattr(logger, log_level.lower(), logger.info)
            
            # 记录函数调用
            msg = f"▶ 开始执行 {func.__name__}"
            if log_args:
                msg += f" (args={args[1:] if args else ()}, kwargs={kwargs})"
            log_func(msg)
            
            try:
                result = func(*args, **kwargs)
                
                # 记录执行成功
                elapsed = time.time() - start_time
                success_msg = f"✅ {func.__name__} 执行成功"
                if log_execution_time:
                    success_msg += f" (耗时: {elapsed:.2f}秒)"
                if log_result:
                    success_msg += f", 返回值: {result}"
                log_func(success_msg)
                
                return result
            except Exception as e:
                # 记录执行失败
                elapsed = time.time() - start_time
                error_msg = f"❌ {func.__name__} 执行失败: {e}"
                if log_execution_time:
                    error_msg += f" (耗时: {elapsed:.2f}秒)"
                log_func(error_msg, exc_info=True)
                raise
        
        return wrapper
    
    return decorator


# ── 组合装饰器 ─────────────────────────────────────────────────────────

def with_error_handling(
    handle: bool = True,
    retry: bool = False,
    validate: bool = False,
    log: bool = True,
    **kwargs,
):
    """
    组合装饰器（一次性应用多个装饰器）。
    
    用法:
        @with_error_handling(handle=True, retry=True, max_retries=3, log=True)
        def important_function():
            ...
    """
    def decorator(func: Callable):
        # 从内到外应用装饰器（执行时从外到内）
        result_func = func
        
        if log:
            log_kwargs = {k: v for k, v in kwargs.items() if k.startswith("log_")}
            result_func = log_execution(**log_kwargs)(result_func)
        
        if validate:
            validate_kwargs = {k: v for k, v in kwargs.items() if k == "validators" or k == "raise_on_error"}
            result_func = validate_input(**validate_kwargs)(result_func)
        
        if retry:
            retry_kwargs = {k: v for k, v in kwargs.items() if k in ("max_retries", "delay", "backoff", "exceptions", "on_retry")}
            result_func = retry_on_error(**retry_kwargs)(result_func)
        
        if handle:
            handle_kwargs = {k: v for k, v in kwargs.items() if k in ("exceptions", "handler", "log_traceback", "reraise", "default_return")}
            result_func = handle_errors(**handle_kwargs)(result_func)
        
        return result_func
    
    return decorator


# ── 导出列表 ─────────────────────────────────────────────────────────

__all__ = [
    "handle_errors",
    "retry_on_error",
    "validate_input",
    "log_execution",
    "with_error_handling",
]
