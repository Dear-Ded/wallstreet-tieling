# 更新日志

> 版本号遵循语义化版本：MAJOR.MINOR.PATCH

---

## v3.0.2 — 文档补全 + 工程优化 (2026-06-09)

**GStack 三专家综合审计 · README 全面重写 · 项目管理规范化**

### 工程优化
- GStack 三专家综合审计（产品评审员/安全官/调查员）
- README.md 全面重写（42/100 → 90+/100），新增 7 个章节
- 防杜撰六层防御体系独立成章
- 质量保障三道防线（L1 正则 + L2 评分 + L3 政委 PUA）
- 动态编排引擎（3 阶段流水线 + 6 模式 + 6 条件分支）
- 部署形态 8 种（Skill 粘贴/MCP/Docker/REST API/npm CLI/Custom GPT/Claude/国产 Bot）
- 成本控制（模式 Token 预算 + 多模型价格表 + 节省率）
- REST API 服务（4 端点 + curl 示例）
- 多分支优化策略（4 分支 + git checkout 指南）
- 数字修正：OSINT 3→5、MCP 2→5、平台 8→14+
- 3 个新 Badge：防杜撰 6 层防御 / L1+L2 双检 / Token 节省 85-93%

### 新建文件
- DEPENDENCIES.md（10 大分类 · 四级必要性披露）
- CODE_OF_CONDUCT.md（贡献者公约 v2.1）
- SECURITY.md（漏洞报告流程 + 已知限制）
- .github/ISSUE_TEMPLATE/（3 个模板）
- .github/PULL_REQUEST_TEMPLATE.md

### 重写文件
- LIMITATIONS.md（基于 v3.0.2 实际能力重写）
- index.html（Hero · 能力 · 数据源 · 安装 · Roadmap 全面翻新）

### 仓库管理
- 根目录清理：Dockerfile/clawhub.json/openclaw.json → deploy/
- .gitignore 补全：`__pycache__/` `*.pyc` `output/` `deliverables/` `docs/`
- 分支清理：删除 china/expert/productivity/mimo-batch
- ROADMAP.md 版本号修正 v1.0.0-beta.1 → v3.0.2

### 版本统一
- SKILL.md / package.json / clawhub.json / mcp-server.json / server.py / regression.json 全文件版本号统一为 3.0.2

---

## v3.0.1 — 子 skill 业务逻辑补全 (2026-06-07)

- 钱守正：完整调度决策树（1469B→2700B，+84%）
- 陈志远：任务 DAG + 4 场景拆解方案（1190B→2377B，+100%）
- 吴德厚：PUA 触发时机 + 质量检查清单
- 周通：环境检测流程 + 数据获取步骤
- 刘文华：报告合并流程 + 完整 MD 模板
- data-sources.md：21KB→1.8KB 实用速查表（瘦身92%）
- SKILL.md：新增输出质量检查点（交付前强制执行）
- 数据源数字修正：200+→实际可用 10-30

---

## v3.0.0 — 子母 skill 架构重构 (2026-06-07)

**Token 节省 79-93%**

### 架构变更
- 主 SKILL.md 从 125KB 缩减到 4.5KB（97%缩减）
- 13 个角色拆分为独立 sub-skills/ 子 skill 文件
- 渐进式披露：主 SKILL 只含调度表+铁律，子 skill 按需加载

### Token 效率
- 简单查询（主+3 子 skill）：~3,149 tokens — 节省 93%
- 标准尽调（主+10 子 skill）：~6,496 tokens — 节省 85%
- 深度尽调（全 13 子 skill）：~8,928 tokens — 节省 79%

### 新增
- 标准 YAML frontmatter（兼容 6 大工具）
- 小米 MiMo 模型适配（mimo-v2.5/pro/flash）
- 陈志远（陈工）任务拆解子 skill
- CHANGELOG.md 版本管理

### 清理
- 删除空 agents/ 和 personality/ 目录
- 删除 4 个陈旧 references/ 文件

---

## v2.6.0 (2026-06-06)

- 问题上报机制（简单/中等/复杂三级）
- 头脑风暴机制（7 步会议流程）
- 拟人化交互示例

## v2.5.0 (2026-06-06)

- CrewAI 风格调度架构
- 三种模式：流水线/层次化/并行
- 并行执行规则（最大 5 并行，超时 5 分钟，重试 3 次）

## v2.4.0 (2026-06-06)

- 13 个 agents/ 子 skill 文件创建
- 小米 MiMo 模型适配

## v2.3.0 (2026-06-06)

- OSINT 工具依赖配置 + 依赖检测/提示/降级方案
- 蛛丝马迹推理框架

## v2.2.0 (2026-06-06)

- 中小企业尽调能力：企业类型识别 + 独有指标 + 行业特殊指标（餐饮/零售/贸易）

## v2.1.0 (2026-06-06)

- 颜好看（颜设计）角色：前 Apple 设计团队成员
- 设计系统：颜色/字体/间距/圆角

## v2.0.1 (2026-06-05)

- 智能推导引擎 + OSINT 数据源矩阵 + 质量控制机制 + 冲突数据展示

## v1.0.0

- 初始版本：12 人团队协作 + 五层数据源矩阵
