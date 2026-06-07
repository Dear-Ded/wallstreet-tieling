# 子skill数据传递协议

## 输出格式契约
每个子skill输出必须包含：
1. `role`: 角色名
2. `timestamp`: 输出时间
3. `data`: 结构化数据（yaml或表格）
4. `sources`: 数据来源列表
5. `confidence`: 可信度（high/medium/low/待核实）

## 刘文华合并规则
- 按role分组 → 去重（相同数据合并sources） → 按章节模板组织
- 数据冲突 → 标注[冲突]两侧来源 → 优先级:官方>商业>OSINT>推论
- 无法验证 → 标注[待核实]
