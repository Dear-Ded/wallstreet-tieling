# 通用多数据源接入模块 - 架构设计文档

## 目录
1. [概述](#概述)
2. [架构设计原则](#架构设计原则)
3. [系统架构](#系统架构)
4. [核心组件](#核心组件)
5. [设计模式](#设计模式)
6. [类型系统设计](#类型系统设计)
7. [错误处理策略](#错误处理策略)
8. [并发模型](#并发模型)
9. [扩展性设计](#扩展性设计)
10. [测试策略](#测试策略)
11. [性能优化](#性能优化)
12. [部署与集成](#部署与集成)

---

## 概述

### 目标
设计一个高度可扩展、类型安全、 asyncio 原生的通用多数据源接入模块，支持：
- 统一查询接口
- YAML 配置管理
- 结果格式化与聚合
- 并发查询
- 无需认证的数据源

### 技术栈
- **语言**: Python 3.8+
- **异步框架**: asyncio + aiohttp
- **类型检查**: typing + mypy
- **配置验证**: Pydantic v2
- **配置格式**: YAML

---

## 架构设计原则

### 1. 开闭原则 (Open-Closed Principle)
对扩展开放，对修改封闭。新增数据源只需继承 `BaseDataSource`，无需修改现有代码。

### 2. 依赖倒置原则 (Dependency Inversion)
高层模块不依赖低层模块，二者都依赖抽象。`DataSourceManager` 依赖 `BaseDataSource` 抽象，不依赖具体实现。

### 3. 单一职责原则 (Single Responsibility)
每个类只负责一个功能：
- `BaseDataSource`: 定义数据源抽象
- `DataSourceManager`: 管理数据源生命周期
- `QueryResult`: 封装查询结果
- `ResultAggregator`: 聚合结果

### 4. 接口隔离原则 (Interface Segregation)
数据源接口按功能拆分：
- 查询接口 (`query`)
- 健康检查接口 (`health_check`)
- 格式化接口 (`format_result`)

---

## 系统架构

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                  应用层 (Application Layer)              │
│  - 业务逻辑                                            │
│  - 查询编排                                            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│               数据源管理器层 (Manager Layer)              │
│  - DataSourceManager                                   │
│  - 数据源注册、发现、路由                              │
│  - 并发查询编排                                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              抽象接口层 (Abstraction Layer)             │
│  - BaseDataSource (抽象基类)                          │
│  - QueryRequest / QueryResult                         │
│  - 定义标准接口                                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              具体实现层 (Implementation Layer)           │
│  - RestApiDataSource                                   │
│  - GraphQlDataSource (可扩展)                         │
│  - SoapDataSource (可扩展)                            │
│  - CustomDataSource (可扩展)                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              配置层 (Configuration Layer)               │
│  - YAML 配置加载                                       │
│  - Pydantic 配置验证                                   │
│  - 运行时配置热更新 (可扩展)                           │
└─────────────────────────────────────────────────────────┘
```

### 数据流向

```
用户请求
    ↓
DataSourceManager.query_all()
    ↓
并发查询编排 (asyncio.gather)
    ↓
┌─────────┬─────────┬─────────┐
│ Source1 │ Source2 │ Source3 │
└────┬────┴────┬────┴────┬────┘
     ↓         ↓         ↓
BaseDataSource.query() (模板方法)
     ↓
┌─────────────────────────────┐
│ 1. _pre_query (前置处理)    │
│ 2. _do_query (实际查询)    │
│ 3. format_result (格式化)   │
│ 4. _post_query (后置处理)   │
└─────────────────────────────┘
     ↓
QueryResult (结果封装)
     ↓
AggregatedResult (结果聚合)
     ↓
返回给用户
```

---

## 核心组件

### 1. BaseDataSource (抽象基类)

**职责**: 定义所有数据源的通用接口和行为

**核心方法**:
- `query(request: QueryRequest) -> QueryResult[T]`: 模板方法，定义查询流程
- `_do_query(request: QueryRequest) -> T`: 抽象方法，子类实现具体查询逻辑
- `health_check() -> bool`: 抽象方法，健康检查
- `format_result(raw_data: Any) -> T`: 抽象方法，结果格式化

**设计亮点**:
- **模板方法模式**: `query()` 定义算法骨架，`_do_query()` 实现具体步骤
- **Hook 方法**: `_pre_query()` 和 `_post_query()` 允许子类自定义流程
- **重试机制**: `_execute_with_retry()` 内置指数退避重试

**类型参数**:
- `T`: 查询结果的数据类型，支持泛型

### 2. DataSourceManager (管理器)

**职责**: 管理数据源的生命周期和查询编排

**核心功能**:
- **注册**: `register_source_type()` 注册数据源类型
- **配置加载**: `load_config()` 从 YAML 加载配置
- **初始化**: `initialize_sources()` 根据配置创建数据源实例
- **查询**:
  - `query_single()`: 查询单个数据源
  - `query_multiple()`: 并发查询多个数据源
  - `query_all()`: 查询所有数据源
  - `query_by_priority()`: 按优先级查询
- **健康检查**: `health_check_all()`

**并发控制**:
- 使用 `asyncio.Semaphore` 限制并发数
- 默认并发数: 10

### 3. QueryResult (结果封装)

**职责**: 封装单次查询结果

**核心字段**:
- `source_name`: 数据源名称
- `status`: 查询状态 (SUCCESS/FAILED/TIMEOUT/CANCELLED)
- `data`: 成功时的数据
- `error`: 失败时的错误
- `query_time`: 查询耗时
- `metadata`: 元数据

**设计亮点**:
- 泛型支持: `QueryResult[T]`
- 状态判断属性: `is_success`, `is_failed`
- 序列化: `to_dict()` 转换为字典

### 4. AggregatedResult (聚合结果)

**职责**: 封装多个数据源的查询结果

**核心字段**:
- `results`: 各数据源的结果列表
- `successful_count`: 成功数量
- `failed_count`: 失败数量
- `total_time`: 总耗时
- `success_rate`: 成功率

**核心方法**:
- `get_successful_data()`: 获取所有成功的结果数据
- `to_dict()`: 序列化为字典

### 5. ResultAggregator (结果聚合器)

**职责**: 提供多种结果聚合策略

**聚合策略**:
- `merge_list()`: 合并列表结果
- `merge_dict()`: 合并字典结果
- `rank_by_source()`: 按策略排序结果

---

## 设计模式

### 1. 模板方法模式 (Template Method)

**应用场景**: `BaseDataSource.query()`

```python
async def query(self, request: QueryRequest) -> QueryResult[Any]:
    # 1. 前置处理 (Hook 方法)
    await self._pre_query(request)
    
    # 2. 执行查询 (抽象方法)
    raw_data = await self._do_query(request)
    
    # 3. 结果格式化 (抽象方法)
    formatted_data = self.format_result(raw_data)
    
    # 4. 后置处理 (Hook 方法)
    final_data = await self._post_query(formatted_data, request)
    
    return QueryResult(...)
```

**优势**:
- 保证查询流程一致性
- 子类只需实现核心逻辑
- 易于添加通用逻辑 (日志、监控)

### 2. 策略模式 (Strategy)

**应用场景**: 结果聚合策略

```python
# 不同的聚合策略
data = ResultAggregator.merge_list(results)  # 列表合并
data = ResultAggregator.merge_dict(results)  # 字典合并
results = ResultAggregator.rank_by_source(aggregated, "time")  # 按时间排序
```

**优势**:
- 算法可替换
- 避免条件语句
- 易于扩展新策略

### 3. 注册表模式 (Registry)

**应用场景**: 数据源类型注册

```python
manager = DataSourceManager()
manager.register_source_type(RestApiDataSource)
manager.register_source_type(GraphQlDataSource)
```

**优势**:
- 动态注册新类型
- 配置驱动实例化
- 解耦类型定义和使用

### 4. 异步上下文管理器 (Async Context Manager)

**可扩展**: 支持 `async with` 语法

```python
class DataSourceManager:
    async def __aenter__(self):
        self.initialize_sources()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# 使用
async with DataSourceManager(config_path="config.yaml") as manager:
    result = await manager.query_all(request)
```

---

## 类型系统设计

### 泛型设计

```python
T = TypeVar('T')
DataSourceType = TypeVar('DataSourceType', bound='BaseDataSource')

@dataclass
class QueryResult(Generic[T]):
    data: Optional[T]

@dataclass  
class AggregatedResult(Generic[T]):
    results: List[QueryResult[T]]
```

**优势**:
- 类型安全
- IDE 自动补全
- mypy 静态检查

### 协议类型 (Protocol)

**可扩展**: 定义鸭子类型接口

```python
from typing_extensions import Protocol

class DataSourceProtocol(Protocol):
    """数据源协议 (结构化类型)"""
    name: str
    type_name: str
    
    async def query(self, request: QueryRequest) -> QueryResult[Any]: ...
    
    async def health_check(self) -> bool: ...
```

**优势**:
- 无需继承即可实现接口
- 更适合动态语言特性

### 枚举类型

```python
class QueryStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
```

**优势**:
- 类型安全
- 自动补全
- 防止魔法字符串

---

## 错误处理策略

### 分层错误处理

```
┌─────────────────────────────────┐
│ 应用层: 业务错误处理            │
│ - 结果验证                      │
│ - 降级策略                      │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ 管理器层: 编排错误处理          │
│ - 部分失败处理                  │
│ - 超时控制                      │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ 数据源层: 查询错误处理          │
│ - 重试机制                      │
│ - 异常捕获                      │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│ 网络层: 底层错误处理            │
│ - 连接错误                      │
│ - HTTP 错误                     │
└─────────────────────────────────┘
```

### 错误类型

```python
class ConfigError(Exception):
    """配置相关错误"""
    pass

class QueryError(Exception):
    """查询相关错误"""
    pass

class DataSourceError(Exception):
    """数据源错误"""
    pass
```

### 重试策略

**指数退避**:

```python
async def _execute_with_retry(self, request: QueryRequest) -> Any:
    retry_config = self.config.retry
    
    for attempt in range(retry_config.max_retries + 1):
        try:
            return await asyncio.wait_for(...)
        except Exception as e:
            if attempt < retry_config.max_retries:
                wait_time = retry_config.backoff_factor * (2 ** attempt)
                await asyncio.sleep(wait_time)
            else:
                raise
```

**配置项**:
- `max_retries`: 最大重试次数
- `backoff_factor`: 退避因子
- `retry_on_status`: 需要重试的 HTTP 状态码

### 部分失败处理

**设计**: 多数据源查询时，部分失败不影响整体

```python
aggregated = await manager.query_all(request)
print(f"成功: {aggregated.successful_count}")
print(f"失败: {aggregated.failed_count}")

# 即使部分失败，仍可获取成功的数据
if aggregated.successful_count > 0:
    data = aggregated.get_successful_data()
```

---

## 并发模型

### asyncio 原生支持

**设计原则**:
- 所有 I/O 操作都是异步的
- 使用 `async/await` 语法
- 避免阻塞调用

### 并发查询

**实现**: `asyncio.gather()`

```python
async def query_multiple(self, source_names: List[str], ...) -> AggregatedResult:
    tasks = [self.query_single(name, request) for name in source_names]
    results = await asyncio.gather(*tasks)
    return AggregatedResult(results=list(results))
```

**优势**:
- 真正并发 (非线程切换)
- 高效 I/O 多路复用
- 自动异常处理

### 并发控制

**实现**: `asyncio.Semaphore`

```python
semaphore = asyncio.Semaphore(concurrency)

async def _query_with_semaphore(source_name: str) -> QueryResult[Any]:
    async with semaphore:
        return await self.query_single(source_name, request)
```

**优势**:
- 防止资源耗尽
- 保护下游服务
- 可配置并发数

### 超时控制

**实现**: `asyncio.wait_for()`

```python
await asyncio.wait_for(
    self._do_query(request),
    timeout=self.config.timeout
)
```

**优势**:
- 防止单个查询阻塞
- 快速失败
- 提升用户体验

---

## 扩展性设计

### 1. 新增数据源类型

**步骤**:

```python
# 1. 继承 BaseDataSource
class GraphQlDataSource(BaseDataSource):
    type_name = "graphql"
    
    async def _do_query(self, request: QueryRequest) -> Any:
        # 实现 GraphQL 查询
        ...
    
    async def health_check(self) -> bool:
        # 实现健康检查
        ...
    
    def format_result(self, raw_data: Any) -> Any:
        # 实现结果格式化
        ...

# 2. 注册数据源类型
manager.register_source_type(GraphQlDataSource)

# 3. 在 YAML 配置中添加
"""
- name: "my_graphql_api"
  type: "graphql"
  base_url: "https://api.example.com/graphql"
  ...
"""
```

**所需改动**:
- ✅ 新增文件: `graphql_datasource.py`
- ✅ 注册类型: `manager.register_source_type()`
- ✅ 添加配置: YAML 文件
- ❌ 无需修改现有代码

### 2. 自定义结果格式化

**方法 1: 覆盖 `format_result()`**

```python
class CustomRestApiDataSource(RestApiDataSource):
    def format_result(self, raw_data: Any) -> Any:
        # 自定义格式化逻辑
        return {
            "items": raw_data.get("data", []),
            "total": raw_data.get("meta", {}).get("total", 0)
        }
```

**方法 2: 后处理 Hook**

```python
class CustomDataSource(BaseDataSource):
    async def _post_query(self, data: Any, request: QueryRequest) -> Any:
        # 后处理: 过滤、排序、分页等
        filtered = [item for item in data if item["status"] == "active"]
        return filtered
```

### 3. 自定义查询流程

**覆盖模板方法**:

```python
class CachedDataSource(BaseDataSource):
    async def query(self, request: QueryRequest) -> QueryResult[Any]:
        # 1. 先查缓存
        cache_key = self._build_cache_key(request)
        cached = await self._get_from_cache(cache_key)
        if cached:
            return QueryResult(data=cached, status=QueryStatus.SUCCESS)
        
        # 2. 缓存未命中，执行查询
        result = await super().query(request)
        
        # 3. 写入缓存
        if result.is_success:
            await self._save_to_cache(cache_key, result.data)
        
        return result
```

### 4. 插件系统 (可扩展)

**设计**: 数据源发现机制

```python
# 自动发现并注册数据源
import pkgutil
import importlib

def discover_data_sources(package_name: str):
    """自动发现包中的所有数据源"""
    package = importlib.import_module(package_name)
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package_name}.{modname}")
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BaseDataSource) and attr != BaseDataSource:
                manager.register_source_type(attr)

# 使用
discover_data_sources("myapp.datasources")
```

---

## 测试策略

### 单元测试

**测试目标**:
- 单个组件的功能正确性
- 边界条件处理
- 错误处理

**示例**:

```python
class TestRestApiDataSource:
    @pytest.mark.asyncio
    async def test_query_success(self, source):
        # Mock aiohttp 响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": "test"})
        
        with patch.object(source, '_get_session', return_value=mock_session):
            result = await source.query(request)
            assert result.is_success
    
    @pytest.mark.asyncio
    async def test_query_timeout(self, source):
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
            result = await source.query(request)
            assert result.status == QueryStatus.TIMEOUT
```

### 集成测试

**测试目标**:
- 组件之间的交互
- 真实 I/O 操作
- 配置文件加载

**示例**:

```python
@pytest.mark.integration
class TestDataSourceManager:
    @pytest.mark.asyncio
    async def test_load_config_and_query(self):
        manager = DataSourceManager(config_path="test_config.yaml")
        manager.initialize_sources()
        
        assert len(manager.list_sources()) > 0
        
        request = QueryRequest(query="test")
        result = await manager.query_all(request)
        assert result.successful_count > 0
```

### Mock 策略

**外部依赖**:
- `aiohttp.ClientSession`: Mock HTTP 响应
- `yaml.safe_load`: Mock 配置加载
- 数据库连接: Mock 游标和连接

**工具**:
- `unittest.mock.AsyncMock`: 异步 Mock
- `pytest-mock`: pytest Mock 插件
- `respx`: HTTP 请求 Mock

### 测试覆盖率

**目标**:
- 单元测试覆盖率: ≥ 80%
- 核心路径覆盖率: 100%

**工具**:
- `pytest-cov`: 覆盖率报告
- `coverage.py`: 覆盖率分析

---

## 性能优化

### 1. 连接池复用

**问题**: 每次查询创建新连接开销大

**解决**: 复用 aiohttp ClientSession

```python
class RestApiDataSource(BaseDataSource):
    def __init__(self, config: DataSourceConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(...)
        return self._session
```

### 2. 结果缓存

**可扩展**: 添加查询结果缓存

```python
from functools import lru_cache
import pickle

class CachedDataSourceManager(DataSourceManager):
    def __init__(self, *args, cache_size: int = 128, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache: Dict[str, Any] = {}
        self._cache_size = cache_size
    
    async def query_single(self, source_name: str, request: QueryRequest):
        cache_key = f"{source_name}:{pickle.dumps(request)}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = await super().query_single(source_name, request)
        
        if result.is_success:
            self._cache[cache_key] = result
            if len(self._cache) > self._cache_size:
                # LRU 淘汰
                ...
        
        return result
```

### 3. 限流保护

**实现**: 令牌桶算法

```python
class RateLimiter:
    """令牌桶限流器"""
    def __init__(self, rate: float, burst: int):
        self.rate = rate  # 每秒生成的令牌数
        self.burst = burst  # 桶容量
        self.tokens = burst
        self.last_refill = time.time()
    
    async def acquire(self):
        """获取令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        else:
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_refill = time.time()
            return True
```

**集成**: 在 `_pre_query()` 中调用

```python
class RestApiDataSource(BaseDataSource):
    def __init__(self, config: DataSourceConfig):
        super().__init__(config)
        self._rate_limiter = RateLimiter(
            rate=self.config.rate_limit.requests_per_second,
            burst=self.config.rate_limit.burst_size
        )
    
    async def _pre_query(self, request: QueryRequest):
        if self.config.rate_limit.enabled:
            await self._rate_limiter.acquire()
```

### 4. 结果流式处理

**可扩展**: 支持大数据集流式返回

```python
async def query_stream(self, request: QueryRequest):
    """流式查询 (生成器)"""
    offset = 0
    limit = 100
    
    while True:
        request.pagination = {"offset": offset, "limit": limit}
        result = await self.query(request)
        
        if not result.is_success or not result.data:
            break
        
        for item in result.data:
            yield item
        
        if len(result.data) < limit:
            break
        
        offset += limit
```

---

## 部署与集成

### 1. 作为独立模块使用

**安装**:

```bash
pip install multi-datasource
```

**使用**:

```python
from multi_datasource import DataSourceManager, QueryRequest

async def main():
    manager = DataSourceManager(config_path="datasources.yaml")
    manager.initialize_sources()
    
    request = QueryRequest(query="search", params={"q": "python"})
    result = await manager.query_all(request)
    
    print(result.to_dict())

asyncio.run(main())
```

### 2. 集成到现有系统

**场景**: 分层信息检索架构

```
现有系统架构:
┌─────────────────────┐
│  API 层 (FastAPI)   │
├─────────────────────┤
│ 业务逻辑层           │
├─────────────────────┤
│ 数据访问层           │  ← 插入多数据源模块
├─────────────────────┤
│ 存储层 (DB/Cache)   │
└─────────────────────┘
```

**集成代码**:

```python
# 在现有系统的数据访问层使用
from multi_datasource import DataSourceManager

class DataAccessLayer:
    def __init__(self):
        self.manager = DataSourceManager(config_path="datasources.yaml")
        self.manager.initialize_sources()
    
    async def search(self, query: str) -> List[Dict]:
        request = QueryRequest(query=query)
        aggregated = await self.manager.query_all(request)
        
        # 转换为现有系统格式
        results = []
        for result in aggregated.results:
            if result.is_success:
                results.extend(result.data)
        
        return results
```

### 3. Docker 部署

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY multi_datasource_framework.py /app/
COPY datasources.yaml /app/

CMD ["python", "multi_datasource_framework.py", "--config", "datasources.yaml"]
```

### 4. 配置管理

**环境变量覆盖**:

```python
class DataSourceConfig(BaseModel):
    base_url: str = Field(...)
    
    @validator('base_url', pre=True)
    def validate_base_url(cls, v: str) -> str:
        # 支持环境变量覆盖
        return os.getenv(f"DATASOURCE_{v.upper()}_URL", v)
```

**配置热更新 (可扩展)**:

```python
class DataSourceManager:
    async def watch_config(self, config_path: Path):
        """监控配置文件变化，自动重新加载"""
        import asyncio
        from watchfiles import awatch
        
        async for changes in awatch(config_path):
            self.logger.info("配置文件已更改，重新加载...")
            self.load_config(config_path)
            self.initialize_sources()
```

---

## 总结

### 设计亮点

1. **高度可扩展**: 新增数据源只需继承 `BaseDataSource`
2. **类型安全**: 充分利用 Python 类型注解 + mypy 检查
3. **asyncio 原生**: 全异步设计，高效 I/O 并发
4. **错误处理完善**: 分层错误处理 + 重试机制 + 部分失败处理
5. **易于测试**: 依赖注入 + Mock 友好 + 清晰的抽象边界

### 未来扩展方向

1. **数据源类型扩展**:
   - GraphQL 数据源
   - gRPC 数据源
   - WebSocket 数据源
   - 数据库数据源 (SQL/NoSQL)

2. **功能增强**:
   - 查询结果缓存
   - 配置热更新
   - 监控指标 (Prometheus)
   - 分布式追踪 (OpenTelemetry)

3. **性能优化**:
   - 连接池优化
   - 结果流式处理
   - 智能路由 (根据数据源健康状态)

4. **运维支持**:
   - 管理后台 (数据源配置、监控)
   - 日志聚合
   - 告警机制

---

## 附录

### A. 完整依赖列表

```txt
# requirements.txt
pydantic>=2.0.0
pydantic-settings>=2.0.0
pyyaml>=6.0
aiohttp>=3.8.0
asyncio>=3.4.3
typing-extensions>=4.0.0
```

### B. 配置文件 Schema

参见代码中的 `DataSourceConfig` 和 `MultiDataSourceConfig` 类

### C. API 参考

参见代码中的类和方法文档字符串

---

**文档版本**: 1.0.0  
**最后更新**: 2024-01-01  
**作者**: GStack Product Reviewer
