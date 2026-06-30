## 模块依赖图

```mermaid
graph TD
    %% 核心引擎层
    engine["core.engine<br/>编排引擎"]:::core
    
    %% core 模块
    interfaces["core.interfaces<br/>抽象接口"]:::core
    rules["core.rules<br/>NFR规则"]:::core
    session_bus["core.session_bus<br/>情报总线"]:::core
    query_cache["core.query_cache<br/>查询缓存"]:::core
    org_memory["core.org_memory<br/>组织记忆"]:::core
    deep_graph["core.deep_graph<br/>关联图谱"]:::core
    roles["core.roles<br/>角色职权"]:::core
    
    %% api 模块
    agent["api.agent<br/>Agent基类"]:::api
    agent_registry["api.agent_registry<br/>Agent注册表"]:::api
    personality["api.personality<br/>人格配置"]:::api
    quality_rules["api.quality_rules<br/>质量规则"]:::api
    config["api.config<br/>配置管理"]:::api
    
    %% adapters 模块
    _base["adapters._base<br/>适配器基类"]:::adapter
    workbuddy["adapters.workbuddy<br/>WorkBuddy适配器"]:::adapter
    cli["adapters.cli<br/>CLI适配器"]:::adapter
    multi_ds["adapters.multi_datasource_tool<br/>多数据源工具"]:::adapter
    
    %% 依赖关系 - Engine 层
    engine --> interfaces
    engine --> rules
    engine --> session_bus
    engine --> agent
    engine --> agent_registry
    engine --> personality
    engine --> quality_rules
    
    %% 依赖关系 - Agent 层
    agent --> session_bus
    agent --> query_cache
    agent --> org_memory
    agent --> deep_graph
    
    %% 依赖关系 - Adapter 层
    workbuddy --> _base
    workbuddy --> interfaces
    workbuddy --> multi_ds
    cli --> _base
    cli --> interfaces
    
    %% 依赖关系 - 质量规则层
    quality_rules --> roles
    
    %% 样式定义
    classDef core fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef api fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef adapter fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

### 依赖说明

| 模块 | 依赖 | 说明 |
|------|------|------|
| `core.engine` | `core.interfaces`, `core.rules`, `core.session_bus`, `api.agent`, `api.agent_registry`, `api.personality`, `api.quality_rules` | 编排引擎依赖所有核心模块 |
| `api.agent` | `core.session_bus`, `core.query_cache`, `core.org_memory`, `core.deep_graph` | Agent 依赖会话总线、缓存、记忆、图谱 |
| `adapters.workbuddy` | `adapters._base`, `core.interfaces`, `adapters.multi_datasource_tool` | WorkBuddy 适配器依赖基类、接口、多数据源工具 |
| `api.quality_rules` | `core.roles` | 质量规则依赖角色职权定义 |

### 修改影响范围

| 被依赖模块 | 影响范围 | 修改风险 |
|------------|---------|---------|
| `core.interfaces` | 所有 adapters + engine | 🔴 高 |
| `core.session_bus` | engine + 所有 Agent | 🔴 高 |
| `api.agent` | engine | 🟠 中 |
| `core.rules` | engine | 🟡 低 |
| `api.personality` | engine | 🟡 低 |
