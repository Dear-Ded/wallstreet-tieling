# wallstreet-tieling v3.2.0 → v4.0.0 迁移指南

## TL;DR

v4.0.0 将编排引擎与平台解耦。`api/orchestrator.py` 仍可用（向后兼容），但新代码应使用 `core/engine.py`。

## 代码变更

### 旧方式 (v3.2.0)
```python
from api.orchestrator import Orchestrator
import api.config as config

config.reload_config()
orch = Orchestrator(target="ABC公司", mode="standard")
result = await orch.orchestrate()
```

### 新方式 (v4.0.0)
```python
from core.engine import Engine
from adapters.workbuddy import create_adapter

adapter = create_adapter()
engine = Engine(target="ABC公司", adapter=adapter, mode="standard")
result = await engine.run()
```

### CLI 独立运行
```bash
python adapters/cli.py "ABC公司" standard
```

## 新增能力

| 能力 | v3.2.0 | v4.0.0 |
|------|:--:|:--:|
| 平台适配器 | ❌ | ✅ WB / CLI / Dify / Coze |
| SessionBus 情报传递 | ❌ 散装文本 | ✅ 结构化 JSON |
| 团队会议 Phase 1.5 | ❌ | ✅ 钱守正主持三轮议事 |
| 质量门禁 L2 | ❌ 跳过 | ✅ L1+L2 完整 |
| OrgMemory 组织记忆 | ❌ | ✅ 五层本地存储 |
| 查询缓存 | ❌ | ✅ QueryCache + GlobalCache |
| 深度关联图 | ❌ | ✅ ≤8跳遍历 + 环检测 |

## 人设不变

13 个角色的 PersonalityProfile 完全保留。新增 RoleAuthority（职权体系）不影响角色行为。

## 测试

```bash
pytest tests/unit/ -q  # 402 passed
```
