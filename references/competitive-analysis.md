# GitHub 竞品/参考项目分析

> 分析日期：2026-06-05 | 目标：借鉴顶级开源项目思路，优化华尔驻铁岭办事处的架构和功能

---

## 🔬 重点参考项目

### 1. Ballerine (13K+ Stars) — 开源 KYC/KYB 合规平台

**仓库**: https://github.com/ballerine-io/ballerine

**核心架构**：
```
用户 → SDK Flow（前端采集） → 规则引擎 → 第三方插件 → 人工审核 → 决策输出
```

**可借鉴思路**：

| 特性 | Ballerine 实现 | 我们的借鉴方向 |
|------|---------------|---------------|
| **规则引擎** | 灵活的 JSON 规则配置，支持 AND/OR/阈值逻辑 | 钱总任务拆解时可以引用规则模板，降低判断偏差 |
| **插件系统** | 数据源以插件形式接入，统一接口规范 | 周通接口猎取标准化——所有新数据源遵循统一适配器接口 |
| **人工审核留痕** | 关键决策点留痕，支持驳回/复审 | 郑慎之三阶段审计 → 增加"审计留痕"格式，标注检查点 |
| **风险评分** | 多维度加权评分，可配置权重 | 赵刚的风险雷达六维图 → 增加可配置权重，支持行业定制 |
| **工作流可视化** | 前端展示流程状态 | 刘文华 HTML 报告可增加"调查过程时间线"组件 |

### 2. OpenBB (64K+ Stars) — 开源金融数据平台

**仓库**: https://github.com/OpenBB-finance/OpenBB

**核心架构**：
```
Data Providers → OpenBB Core (统一数据层) → Python SDK / CLI / REST API / MCP Server
```

**可借鉴思路**：

| 特性 | OpenBB 实现 | 我们的借鉴方向 |
|------|------------|---------------|
| **统一数据层** | `obb.equity.price.historical("AAPL")` 一条命令，背后自动路由到 Yahoo/Bloomberg/Polygon | 周通接口抽象——用户说"查ABC公司财务"，自动选择最优数据源 |
| **Provider 扩展系统** | 每个数据源都是一个 Provider，实现标准接口 | 我们的 Tier 0-4 数据源体系可以做标准化 Provider 封装 |
| **MCP Server** | 支持作为 MCP Server 供 AI Agent 直接调用 | 我们的 Skill 如果宿平台支持 MCP，可以暴露标准化查询接口 |
| **CLI + Python SDK** | 多层次接入，用户可根据技术能力选择 | 为高级用户提供 Python 脚本模板，直接在本地环境跑 |
| **标准化输出** | DataFrame 统一格式 | 所有业务组输出统一为结构化 JSON + Markdown 双格式 |

### 3. SpiderFoot (12K+ Stars) — OSINT 自动化框架

**仓库**: https://github.com/smicallef/spiderfoot

**核心架构**：
```
Target → Scanner Modules (100+) → Data Correlation Engine → Visual Graph → Report
```

**可借鉴思路**：

| 特性 | SpiderFoot 实现 | 我们的借鉴方向 |
|------|----------------|---------------|
| **模块化扫描器** | 100+ 独立模块，每个模块查询一个数据源 | "全网扒光模式"可升级为模块化扫描——每层数据源一个扫描模块 |
| **自动关联** | 跨数据源关联分析（IP → 域名 → 企业 → 人员） | 张铁柱"蛛丝马迹追踪"可增加自动关联推荐 |
| **可视化图谱** | 实体关系图，自动发现隐藏关联 | HTML 报告增加 D3.js/Mermaid 实体关系图 |
| **扫描策略** | 可配置扫描深度（浅/中/深） | 全网扒光模式增加"三档深度"：快速扫描/标准尽调/深度扒光 |
| **数据去重** | 跨源数据自动去重和冲突解决 | 郑慎之事后审计增加"跨源交叉验证"步骤 |

### 4. OpenSanctions (5K+ Stars) — 开源制裁/PEP 数据库

**仓库**: https://github.com/opensanctions/opensanctions

**核心架构**：
```
100+ Source Crawlers → ETL Pipeline → Dedup Engine → API / Bulk Download
```

**可借鉴思路**：

| 特性 | OpenSanctions 实现 | 我们的借鉴方向 |
|------|-------------------|---------------|
| **多源聚合** | 聚合 100+ 制裁/通缉/PEP 数据源 | 制裁筛查作为张铁柱尽调的"第一步必查项" |
| **实体去重** | 跨源智能去重，识别同一实体 | 企查查+天眼查+启信宝三方交叉验证逻辑 |
| **标准化数据模型** | FollowTheMoney 数据模型 | 定义统一的企业尽调数据 Schema |
| **API 优先** | 所有数据通过 REST API + Bulk Download 提供 | 参照设计我们的数据输出格式 |

### 5. Credit-Risk-Intelligence — 企业级信贷风险系统

**仓库**: https://github.com/Sol-so-special/Credit-Risk-Intelligence

**可借鉴思路**：

| 特性 | 实现 | 我们的借鉴方向 |
|------|------|---------------|
| **ML 预测模型** | 87% ROC-AUC 违约预测 | 赵刚风险评估可加入"行业违约率参考"辅助判断（不替代决策） |
| **交互式 Web 仪表板** | 实时数据展示 | HTML 报告可增加"风险仪表盘"组件 |
| **特征工程** | 财务指标自动计算 | 李明远五维财务 X 光可自动计算并展示派生指标 |
| **可解释 AI** | SHAP 值展示影响因子 | 风险分析结论附带"关键影响因子"说明 |

### 6. OpenOwnership / BODS — 受益所有权数据标准

**仓库**: https://github.com/openownership

**可借鉴思路**：
- 受益所有人数据标准 (BODS) 作为股权穿透的标准化输出格式
- 支持多层级股权结构的 JSON 表达
- 可与 OpenCorporates/OpenSanctions 联动

---

## 🎯 对各链路的优化建议

### 链路 1：需求理解 → 任务拆解（钱守正 + 陈志远）

| 当前状态 | 借鉴项目 | 优化方向 |
|----------|----------|----------|
| 简单描述匹配 | Ballerine 规则引擎 | 增加"尽调模板库"——不同行业/企业类型对应不同尽调套餐 |
| 无优先级排序 | SpiderFoot 扫描策略 | 轻量扫描 vs 标准尽调 vs 深度扒光，三档可选 |
| 无成本估算 | OpenBB 路由机制 | 开始前告知预计 Token 消耗和时间，支持用户确认 |

### 链路 2：数据采集（周通 + 张铁柱）

| 当前状态 | 借鉴项目 | 优化方向 |
|----------|----------|----------|
| 逐个查询 | SpiderFoot 模块化扫描 | 数据源并行调用 + 结果聚合 |
| 手动切换 | OpenBB 统一数据层 | Provider 模式——"查ABC"自动选企查查/天眼查/Wind |
| 无去重 | OpenSanctions 去重引擎 | 多源数据自动去重和冲突标注 |
| 单层查询 | BODS 数据标准 | 股权穿透输出标准化 JSON |

### 链路 3：分析研判（李明远 + 王思远 + 赵刚）

| 当前状态 | 借鉴项目 | 优化方向 |
|----------|----------|----------|
| 定性判断为主 | Credit-Risk-Intelligence | 增加定量参考指标（行业分位数、历史违约率） |
| 无交互 | Ballerine 人工审核留痕 | 分析过程可暂停让用户确认关键发现 |
| 静态分析 | SpiderFoot 关联引擎 | 自动关联推荐（"这家企业和上次尽调的X公司是同一实控人"） |

### 链路 4：审计验证（郑慎之）

| 当前状态 | 借鉴项目 | 优化方向 |
|----------|----------|----------|
| 三阶段审计 | Ballerine 审核留痕 | 增加"审计检查清单"——每项数据点状态跟踪 |
| 手动核实 | OpenSanctions 标准化 | 数据格式校验 + 异常值自动告警 |

### 链路 5：报告生成（刘文华）

| 当前状态 | 借鉴项目 | 优化方向 |
|----------|----------|----------|
| 5 种格式 | Credit-Risk-Intelligence 仪表板 | HTML 报告增加交互式图表（可展开/折叠） |
| 静态 Mermaid | SpiderFoot 图形 | 实体关系图 + 时间线 + 风险热力图 |
| 独立格式 | OpenBB 标准化输出 | 统一为 JSON Schema，各格式从 JSON 生成 |

---

## 🏗️ 架构升级建议

### 当前架构
```
用户 → 钱总 → 陈志远拆解 → 各组并行执行 → 刘文华整合 → 郑慎之审计 → 交付
```

### 建议升级架构（借鉴 OpenBB + Ballerine + SpiderFoot）
```
用户
  ↓
【钱总】需求分析 → 选择尽调套餐(轻/标/深) → 预估资源消耗
  ↓
【陈志远】MECE 拆解 → 任务编排(DAG) → 并行/串行调度
  ↓
┌─────────────────────────────────────────────┐
│        【周通】统一数据层 (Provider 模式)        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  │QCC   │ │TYC   │ │Wind  │ │Bloom │ ...     │
│  │Provider│Provider│Provider│Provider│        │
│  └──────┘ └──────┘ └──────┘ └──────┘        │
│         ↓ 自动路由 + 去重 + 冲突解决 ↓          │
└─────────────────────────────────────────────┘
  ↓
【业务组】并行分析 (含自动关联推荐)
  ↓
【郑慎之】交叉验证 + 异常告警 + 审计留痕
  ↓
【刘文华】JSON Schema → Markdown/Word/PDF/HTML
  ↓
【钱总】最终交付
```

---

## 📊 优先级排序

| 优先级 | 优化项 | 来源 | 影响范围 | 实现难度 |
|--------|--------|------|----------|----------|
| **P0** | 数据源 Provider 模式统一封装 | OpenBB | 周通/张铁柱 | ⭐⭐⭐ |
| **P0** | 三档尽调深度（轻/标/深） | SpiderFoot | 全局流程 | ⭐⭐ |
| **P1** | 多源数据自动去重和交叉验证 | OpenSanctions | 郑慎之/张铁柱 | ⭐⭐⭐ |
| **P1** | 审计检查清单 + 留痕 | Ballerine | 郑慎之 | ⭐ |
| **P1** | HTML 报告交互式图表 | Credit-Risk-Intelligence | 刘文华 | ⭐⭐ |
| **P2** | 实体关系图 + 风险热力图 | SpiderFoot | 刘文华 | ⭐⭐⭐ |
| **P2** | 行业尽调模板库 | Ballerine | 钱总/陈志远 | ⭐⭐ |
| **P3** | Token/时间预估 | OpenBB | 钱总 | ⭐ |
| **P3** | MCP Server 支持 | OpenBB | 周通 | ⭐⭐⭐⭐ |

---

## 🔗 参考链接

- Ballerine: https://github.com/ballerine-io/ballerine
- OpenBB: https://github.com/OpenBB-finance/OpenBB
- SpiderFoot: https://github.com/smicallef/spiderfoot
- OpenSanctions: https://github.com/opensanctions/opensanctions
- OpenOwnership: https://github.com/openownership
- Credit-Risk-Intelligence: https://github.com/Sol-so-special/Credit-Risk-Intelligence
- Awesome OSINT: https://github.com/jivoi/awesome-osint
