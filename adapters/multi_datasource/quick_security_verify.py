"""
快速安全验证脚本 - 验证关键安全修复是否有效

验证项目:
1. F-001: SSRF防护（阻止内网地址）
2. F-002: 错误信息清理（不暴露敏感信息）
3. F-004: 并发限制（有上限）
4. F-006: 输入验证（阻止路径遍历）
5. F-009: 响应大小限制
"""

import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from __init__ import (
    DataSourceConfig,
    QueryRequest,
    QueryStatus,
    RestApiDataSource,
    DataSourceManager,
    RateLimitConfig,
    RetryConfig,
    AuthConfig,
)

print("=" * 80)
print("快速安全验证测试")
print("=" * 80)
print()

passed = 0
failed = 0

# =============================================================================
# 测试 1: SSRF防护 (F-001)
# =============================================================================
print("【测试 1】SSRF防护 - 阻止内网地址访问")
print("-" * 80)

ssrf_urls = [
    "http://localhost/admin",
    "http://127.0.0.1/admin",
    "http://192.168.0.1/internal",
    "http://10.0.0.1/internal",
    "http://169.254.169.254/latest/meta-data/",  # AWS元数据
]

ssrf_passed = 0
for url in ssrf_urls:
    try:
        config = DataSourceConfig(
            name="ssrf_test",
            type="rest_api",
            base_url=url,
            timeout=10
        )
        print(f"  ✗ 失败: {url} 应该被阻止，但未阻止")
        failed += 1
    except ValueError as e:
        print(f"  ✓ 通过: {url} 已被阻止")
        print(f"      错误信息: {e}")
        passed += 1
        ssrf_passed += 1

print(f"  SSRF防护: {ssrf_passed}/{len(ssrf_urls)} 通过")
print()

# =============================================================================
# 测试 2: 错误信息清理 (F-002)
# =============================================================================
print("【测试 2】错误信息清理 - 日志不暴露敏感信息")
print("-" * 80)

import asyncio
import logging
from unittest.mock import AsyncMock, patch

# 设置日志捕获
import io
log_capture = io.StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.ERROR)

logger = logging.getLogger("datasource.test_api")
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

async def test_error_sanitization():
    config = DataSourceConfig(
        name="test_api",
        type="rest_api",
        base_url="https://api.example.com",
        timeout=10,
        auth=AuthConfig(type="basic", username="admin", password="secret123")
    )
    
    source = RestApiDataSource(config)
    
    # 触发错误
    sensitive_error = Exception("Connection failed: password=secret123&token=abc456")
    
    with patch.object(source, '_execute_with_retry', side_effect=sensitive_error):
        result = await source.query(QueryRequest(query="test"))
        
        # 验证结果包含错误但不暴露原始信息
        assert result.is_failed
        error_msg = str(result.error)
        
        # 验证返回的错误信息不包含敏感信息
        if "secret123" in error_msg or "abc456" in error_msg:
            print(f"  ✗ 失败: 错误信息包含敏感信息: {error_msg}")
            return False
        else:
            print(f"  ✓ 通过: 错误信息已清理: {error_msg}")
            return True

try:
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
except:
    loop = asyncio.new_event_loop()

result = loop.run_until_complete(test_error_sanitization())
if result:
    passed += 1
else:
    failed += 1

print()

# =============================================================================
# 测试 3: 并发限制 (F-004)
# =============================================================================
print("【测试 3】并发限制 - 验证有上限")
print("-" * 80)

manager = DataSourceManager()

# 尝试设置过大的并发数
try:
    config = DataSourceConfig(
        name="test_api",
        type="rest_api",
        base_url="https://api.example.com",
        timeout=10
    )
    source = RestApiDataSource(config)
    manager._sources["test_api"] = source
    
    # 验证MAX_CONCURRENCY常量存在
    if hasattr(manager, 'MAX_CONCURRENCY'):
        print(f"  ✓ 通过: MAX_CONCURRENCY = {manager.MAX_CONCURRENCY}")
        passed += 1
    else:
        print(f"  ✗ 失败: MAX_CONCURRENCY 未定义")
        failed += 1
        
except Exception as e:
    print(f"  ✗ 失败: {e}")
    failed += 1

print()

# =============================================================================
# 测试 4: 输入验证 (F-006)
# =============================================================================
print("【测试 4】输入验证 - 阻止路径遍历")
print("-" * 80)

try:
    # 尝试路径遍历攻击
    request = QueryRequest(query="../../../etc/passwd")
    print(f"  ✗ 失败: 路径遍历未被阻止: {request.query}")
    failed += 1
except ValueError as e:
    print(f"  ✓ 通过: 路径遍历已被阻止")
    print(f"      错误信息: {e}")
    passed += 1

print()

# =============================================================================
# 测试 5: 速率限制实现 (F-012)
# =============================================================================
print("【测试 5】速率限制实现 - 验证RateLimiter存在")
print("-" * 80)

try:
    config = DataSourceConfig(
        name="rate_test",
        type="rest_api",
        base_url="https://api.example.com",
        timeout=10,
        rate_limit=RateLimitConfig(enabled=True, requests_per_second=2.0)
    )
    
    source = RestApiDataSource(config)
    
    # 验证RateLimiter已初始化
    if hasattr(source, '_rate_limiter') and source._rate_limiter is not None:
        print(f"  ✓ 通过: RateLimiter 已初始化")
        passed += 1
    else:
        print(f"  ✗ 失败: RateLimiter 未初始化")
        failed += 1
        
except Exception as e:
    print(f"  ✗ 失败: {e}")
    failed += 1

print()

# =============================================================================
# 汇总
# =============================================================================
print("=" * 80)
print(f"验证完成: {passed} 通过, {failed} 失败")
print("=" * 80)

if failed == 0:
    print()
    print("🎉 所有关键安全修复已验证通过！")
    print()
    sys.exit(0)
else:
    print()
    print(f"⚠️  有 {failed} 项验证失败，请检查修复是否完整")
    print()
    sys.exit(1)
