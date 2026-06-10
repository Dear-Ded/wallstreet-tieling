"""wallstreet-tieling v3.2.0 — pytest 共享 fixtures 和配置

提供跨测试模块的共用 fixtures、mock 基础设施和 pytest-asyncio 配置。
"""
import pytest


@pytest.fixture
def sample_agent_id():
    """标准尽调角色 ID"""
    return "zhang-tie-zhu"


@pytest.fixture
def sample_target():
    """默认尽调目标"""
    return "测试科技有限公司"


# pytest-asyncio 配置：允许 async 测试使用标准 asyncio 模式
# 启用 async def 测试函数的自动检测
def pytest_configure(config):
    config.option.asyncio_mode = "auto"


pytest_plugins = []
