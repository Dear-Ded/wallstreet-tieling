# 更新日志

> 版本号遵循语义化版本：MAJOR.MINOR.PATCH

---

## Unreleased

## v0.6.0 (2026-11-11) — 高置信修复、侦查与爬虫能力

> 最终测试数：**2691 passed, 10 skipped**（PR #2 基线 1760 passed, 9 skipped）。版本号从 0.5.0 升到 0.6.0。这不是把 `feat/osint-acquisition` 整支合并进来。

- 财务分析不再把缺失现金流、缺失客户集中度或 ROE 为 0 当成健康、低风险或可交易结论。
- 修复编排引擎用法说明，以及设计 Token 里被版本号替换截断的背景色。
- 角色数量检查和 GitHub Pages 环境 URL 改为失败即失败；Pages 产物补上 README 引用的品牌卡。
- 测试不再写入真实家目录（`~/.workbuddy`、`~/.wallstreet`），并发跑测试不会再写坏 JSONL；17 个被同名覆盖的测试恢复运行或删除；CI 改为跑完整 testpaths（含 `test_security.py`）。`validate.yml` 仍按 13 个角色子技能检查。
- Docker 镜像补齐 `core/` 等代码目录，镜像可以启动；`flask-cors` 升到 6.x；`GlobalCache` 单例方法不再被覆盖；发布隐私扫描不再把用户名当子串误报；文档入口命令与实际一致；`"ip"` 关键词改为整词匹配。`UsernameCrossPlatformVerifier` 不再调用不存在的 Maigret API；`deep_osint.query_tool` 在工具已安装时会真正执行，未安装时返回 `optional_tool_not_installed`。
- 新增可选 SOCMINT 工具集成（`adapters/osint_tools.py`、`bin/osint_tools.py`、`requirements-osint.txt`）：Maigret / Sherlock / holehe / PhoneInfoga / socid-extractor / theHarvester / GHunt 运行时检测。GPL/AGPL 工具只走子进程或 HTTP 边界，不把源码拷进仓库。递归身份扩展有深度和标识符上限。标准记录为 `osint_tool_run`、`social_account_candidate`、`phone_number_intel`、`identity_relationship`。未知或未报告的站点记为证据缺口，不写成“未找到”。文档不再写死“已安装”。
- 新增爬虫运行时（`core/crawl_runtime.py`、`core/crawl_presets.py`、`bin/crawl.py`）：去重请求队列、会话池与运营方 Cookie、运营方代理池（`WST_PROXY_URLS`）、按域名限速与自适应、重试退避、JSON 断点续爬、条目管道；预置雪球行情/讨论与站点链接抽取。验证码/拦截页转人工交接并记为证据缺口，不内置求解器。
- 吸收 `feat/osint-acquisition` 中的合规采集能力：约 60 个公开/授权数据源适配器（默认关闭）、人物情报、亲属与实体关联、关联图谱、风险评分、时间线、富化报告与图表，以及对应测试。未吸收：企查查 WAF 求解与移动站签名复现、抖音 a_bogus 签名、知服服内置密钥签名、工信部 ICP 滑块验证码自动求解、免费代理猎取。

## v0.5.0 (2026-06-07 — 2026-06-10) — 架构跃迁：子母 Skill + 真并发 Agent + 平台无关引擎

> 最终测试数：**402** (was 36 in v2.6.0)

### 2026-06-07: 子母 skill 架构重构

**Token 节省 79-93%**

- 主 SKILL.md 从 125KB 缩减到 4.5KB（97%缩减）
- 13 个角色拆分为独立 sub-skills/ 子 skill 文件
- 渐进式披露：主 SKILL 只含调度表+铁律，子 skill 按需加载
- 简单查询（主+3 子 skill）：~3,149 tokens — 节省 93%
- 标准尽调（主+10 子 skill）：~6,496 tokens — 节省 85%
- 深度尽调（全 13 子 skill）：~8,928 tokens — 节省 79%
- 标准 YAML frontmatter（兼容 6 大工具）
- 小米 MiMo 模型适配（mimo-v2.5/pro/flash）
- 陈志远（陈工）任务拆解子 skill
- CHANGELOG.md 版本管理
- 删除空 agents/ 和 personality/ 目录
- 删除 4 个陈旧 references/ 文件

### 2026-06-07: 子 skill 业务逻辑补全

- 钱守正：完整调度决策树（1469B→2700B，+84%）
- 陈志远：任务 DAG + 4 场景拆解方案（1190B→2377B，+100%）
- 吴德厚：PUA 触发时机 + 质量检查清单
- 周通：环境检测流程 + 数据获取步骤
- 刘文华：报告合并流程 + 完整 MD 模板
- data-sources.md：21KB→1.8KB 实用速查表（瘦身92%）
- SKILL.md：新增输出质量检查点（交付前强制执行）
- 数据源数字修正：200+→实际可用 10-30

### 2026-06-09: 文档补全 + 工程优化

**GStack 三专家综合审计 · README 全面重写 · 项目管理规范化**

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

**新建文件**: DEPENDENCIES.md / CODE_OF_CONDUCT.md / SECURITY.md / .github/ISSUE_TEMPLATE/ (3个) / .github/PULL_REQUEST_TEMPLATE.md

**重写文件**: LIMITATIONS.md / index.html

**仓库管理**: 根目录清理 / .gitignore 补全 / 分支清理 / ROADMAP.md 修正

**版本统一**: SKILL.md / package.json / clawhub.json / mcp-server.json / server.py / regression.json 全文件版本号统一为 v0.5.0

### 2026-06-10: 真并发Agent架构 + 拟人化升级

**五维度全面审计驱动 · 安全红线清零 · 真并发Agent · 13角色人格化**

- **真并发 Agent 系统**：从单LLM多调用升级为独立Agent实例（DueDiligenceAgent）
  — 每个Agent拥有独立状态/记忆/情感追踪/内部独白/消息通信
- **Agent 注册中心**（AgentRegistry）：13角色生命周期管理、通信路由、团队状态快照
- **AgentMessage 结构化消息**：替代 prev_context 字符串拼贴，支持点对点/广播/闲聊
- **统一编排引擎入口**：server.py 和 wst.py 走同一 Orchestrator，消除架构孤岛
- **13角色人格档案**（PersonalityProfile）：背景故事/性格特征/口头禅/同事关系
- **情感状态追踪**（EmotionalState）：信心/挫败/兴奋动态变化，6种情绪模式
- **政委 PUA 保留**：三级退回话术 + 降级不阻塞流水线
- **安全修复**: server.py 移除运行时 `os.system(pip install)` / API Key 双回退 / VAGUE_WORDS 单一来源
- **工程优化**: config.py / utils.py / agent.py / personality.py / agent_registry.py / quality_rules.py / orchestrator.py 新模块
- **文档修复**: 清理 ma-li-quan.md ~100行重复 / 版本号统一 / 项目管理中枢规范化
- Python 包结构 / Logging / Dockerfile 打包 / 配置中心

### 2026-06-10: CI/CD 强化 + 测试基建 + Bug 修复

**测试从 36 → 376**：test_agent.py（63）+ test_orchestrator.py（53）+ test_quality_rules.py（32）+ test_registry.py（31）+ test_config.py（29）+ test_personality.py（158）+ test_utils.py（30）

- CI/CD: Python syntax check / flake8 / markdownlint
- Bug修复: L1 short_output 阻断 L2 fabrication_risk / EmotionalState 浮点精度 (float→Decimal) / 衰减顺序修正
- QualityRules 模块化拆分 / Test fixtures 共享 (conftest.py)

### 2026-06-10: 平台无关引擎

- **core/ 引擎核心**: 零平台依赖的纯编排引擎
- core/interfaces.py: LLMProvider / ToolProvider / OutputProvider 抽象
- core/roles.py: 13 角色职权体系 (report_to/domain/decisions/must_not)
- core/session_bus.py: 结构化 Phase 间情报传递
- core/engine.py: 3-Phase + Phase 1.5 团队会议 + 条件分支
- core/deep_graph.py: 多跳关联图 ≤8跳, 环检测
- core/query_cache.py / core/org_memory.py: 五层本地组织记忆
- adapters/: WB / CLI 适配器 + 贡献模板
- MIGRATION.md / ARCHITECTURE.md
- **测试从 376 → 402**（新增 26 tests）
- api/: v0.5.0 层完全向后兼容 / sub-skills/: 14 角色提示词不变 / api/personality.py 不变

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
