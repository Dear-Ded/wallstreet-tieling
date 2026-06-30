"""
多数据源工具 - 集成到 wallstreet-tieling
Multi-Data Source Tool - Integration with wallstreet-tieling

这个模块将多数据源检索能力暴露给 wallstreet-tieling 的 agents。
It wraps the SearchEngine and exposes it as a tool that agents can use.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.interfaces import ToolProvider, ToolResult

logger = logging.getLogger("wst.multi_datasource")


class SearchEngineTool(ToolProvider):
    """
    搜索引擎工具 - 包装 SearchEngine
    
    这个工具类将 SearchEngine 暴露给 wallstreet-tieling 的 agents，
    让它们在信息检索时可以调用多数据源。
    
    Usage:
        ```python
        # 在 adapter 中注册这个工具
        tools = SearchEngineTool(config_path="datasources.yaml")
        
        # Agent 调用时会触发 search() 方法
        result = await tools.search("query", "search_engine")
        ```
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化多数据源工具
        
        Args:
            config_path: YAML 配置文件路径（相对于项目根目录）
        """
        self._config_path = config_path or "adapters/multi_datasource/datasources.yaml"
        self._initialized = False
        self._available = {"multi_datasource", "mds"}  # 工具名称
        
    async def _ensure_initialized(self):
        """确保 SearchEngine 已初始化"""
        if not self._initialized:
            try:
                from adapters.multi_datasource import SearchEngine
                
                # 构建配置文件路径
                config_path = Path(self._config_path)
                if not config_path.is_absolute():
                    # 相对于项目根目录
                    project_root = Path(__file__).resolve().parent.parent
                    config_path = project_root / self._config_path
                
                if config_path.exists():
                    await SearchEngine.initialize(str(config_path))
                    self._initialized = True
                    logger.info(f"✅ 多数据源工具初始化完成: {config_path}")
                else:
                    logger.warning(f"⚠️ 配置文件不存在: {config_path}")
                    
            except Exception as e:
                logger.error(f"❌ 多数据源工具初始化失败: {e}")
    
    def available_tools(self) -> set[str]:
        """
        返回可用的工具名称
        
        Returns:
            工具名称集合
        """
        return self._available
    
    async def search(self, query: str, tool_type: str = "multi_datasource", **kwargs) -> ToolResult:
        """
        执行多数据源检索
        
        Args:
            query: 查询字符串（可以是企业名称、关键词等）
            tool_type: 工具类型（"multi_datasource" 或 "mds"）
            **kwargs: 其他参数（sources, use_cache 等）
            
        Returns:
            ToolResult 包含查询结果
        """
        await self._ensure_initialized()
        
        try:
            from adapters.multi_datasource import SearchEngine, QueryRequest
            
            # 解析参数
            sources = kwargs.get("sources")  # 指定数据源列表
            use_cache = kwargs.get("use_cache", True)
            
            # 执行查询
            if sources and isinstance(sources, list):
                # 查询指定的数据源
                results = []
                for source in sources:
                    result = await SearchEngine.search(source, query, use_cache=use_cache)
                    results.append(result.to_dict())
                
                return ToolResult(
                    ok=True,
                    data={
                        "query": query,
                        "results": results,
                        "source_count": len(results)
                    },
                    sources=[f"mds:{s}" for s in sources]
                )
            else:
                # 查询所有数据源
                aggregated = await SearchEngine.search_available(query, use_cache=use_cache)
                
                return ToolResult(
                    ok=True,
                    data={
                        "query": query,
                        "aggregated": aggregated.to_dict(),
                        "successful_count": aggregated.successful_count,
                        "failed_count": aggregated.failed_count,
                        "success_rate": aggregated.success_rate
                    },
                    sources=["mds:available"]
                )
                
        except Exception as e:
            logger.error(f"多数据源查询失败: {e}")
            return ToolResult(
                ok=False,
                error=str(e),
                data={"query": query}
            )
    
    async def search_single(self, source_name: str, query: str, **kwargs) -> ToolResult:
        """
        查询单个数据源
        
        Args:
            source_name: 数据源名称
            query: 查询字符串
            **kwargs: 其他参数
            
        Returns:
            ToolResult 包含查询结果
        """
        await self._ensure_initialized()
        
        try:
            from adapters.multi_datasource import SearchEngine
            
            result = await SearchEngine.search(source_name, query, **kwargs)
            
            return ToolResult(
                ok=result.is_success,
                data=result.to_dict(),
                error=None if result.is_success else str(result.error),
                sources=[f"mds:{source_name}"]
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error=str(e),
                data={"source": source_name, "query": query}
            )
    
    def get_tool_description(self) -> str:
        """
        返回工具描述（用于生成 agent prompt）
        
        Returns:
            工具描述文本
        """
        return """
## 多数据源检索工具 (MultiDataSource)

**工具名称**: `multi_datasource` 或 `mds`

**功能**: 从多个配置的数据源并发检索信息，支持缓存加速。

**使用场景**:
- 需要查询多个信息源时
- 需要缓存加速重复查询时
- 需要统一格式的结果时

**调用方式**:
```
# 查询所有数据源
search(query="企业名称", tool_type="multi_datasource")

# 查询指定数据源
search(query="企业名称", tool_type="multi_datasource", sources=["qyyjt", "sgkrank"])

# 查询单个数据源
tools.search_single("qyyjt", "query=企业名称")
```

**返回格式**:
```json
{
  "ok": true,
  "data": {
    "query": "企业名称",
    "aggregated": {...},
    "successful_count": 3,
    "failed_count": 1
  },
  "sources": ["mds:all"]
}
```

**注意事项**:
- 首次调用会自动初始化（加载配置文件）
- 支持缓存，重复查询会自动命中缓存
- 数据源在 `datasources.yaml` 中配置
""".strip()
    
    async def close(self):
        """关闭工具（清理资源）"""
        try:
            from adapters.multi_datasource import SearchEngine
            await SearchEngine.close()
            logger.info("✅ 多数据源工具已关闭")
        except Exception as e:
            logger.error(f"关闭多数据源工具失败: {e}")


# =============================================================================
# 工厂函数
# =============================================================================

def create_search_engine_tool(config_path: Optional[str] = None) -> SearchEngineTool:
    """
    创建搜索引擎工具实例
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        SearchEngineTool 实例
    """
    return SearchEngineTool(config_path=config_path)
