# 技术边界、已知限制与演进方向

> v0.5.0 · 诚实披露技术局限，明确规划方向。

---

## 核心架构型限制

这些是当前架构设计的内生局限，短期内不计划根本性改变。

### 1. 同上下文角色扮演（v0.5.0 已改善）

> ⚠️ **v0.5.0 起已部分解决**：引入真并发 Agent 架构（DueDiligenceAgent 独立状态/记忆/情感/消息通信），不再是单一 LLM 实例角色扮演。但 Agent 间通过结构化消息通信，非完整的多进程独立推理。

| 表现 | 原因 | 当前状态 |
|:-----|:-----|:---------|
| Agent 可并发独立调用 LLM | asyncio.gather 并行调度 | ✅ v0.5.0 已实现 |
| Agent 拥有独立状态/记忆/情感 | DueDiligenceAgent 独立实例 | ✅ v0.5.0 已实现 |
| Agent 间结构化消息通信 | AgentMessage + AgentRegistry 路由 | ✅ v0.5.0 已实现 |
| 独立进程/线程推理 | 非完整 CrewAI/LangGraph 架构 | 🔮 未来规划 |

**规划方向**：Phase 2/3 — 引入独立Agent进程（CrewAI/LangGraph方案调研中）

### 2. Token消耗与上下文预算

子skill按需加载已大幅降低Token消耗（85-93%节省），但仍受模型上下文窗口限制。

| 场景 | Token消耗 | 建议最小上下文 | 推荐模型 |
|:-----|:---------|:------------|:---------|
| simple（4-5角色） | ~3K | 8K | 任意 |
| standard（8-10角色） | ~7K | 16K | 大部分模型 |
| deep（全13角色） | ~9K | 32K | DeepSeek V4 Pro / MiMo v2.5 Pro |
| deep + Word报告 | ~15K | 64K | DeepSeek V4 Pro（1M上下文） |

**缓解**：8K窗口模型使用 `--brief` 模式或 `simple` 模式；超过64K建议使用DeepSeek V4 Pro（1M上下文，x0.25积分）。

### 3. Trigger词匹配而非NLU

当前通过关键词匹配触发角色调度（`trigger_phrases`），而非意图路由（NLU）。

```python
# 当前：关键词匹配
"实控人|股权穿透|代持" → 张铁柱
"财务|营收|利润|现金流|偿债" → 李明远

# 规划：NLU意图路由
"帮我看一下这家公司到底谁说了算" → 意图路由 → 张铁柱
```

**影响**：较长的模糊描述可能无法触发正确角色。**缓解**：每个角色配置20+触发词，覆盖近200个词组。

---

## 功能实现型限制

这些是当前实现完整但存在边界的限制，大部分有明确降级方案。

### 4. OSINT工具依赖本地环境

| 工具 | 覆盖范围 | 本地安装 | 缺失后降级 |
|:-----|:--------|:--------|:----------|
| maigret | 3,000+网站 | `pip install maigret` | → WebSearch + WebFetch |
| sherlock | 400+网站 | `pip install sherlock-project` | → WebSearch |
| theHarvester | 多搜索引擎 | `pip install theharvester` | → WebSearch |
| holehe | 120+网站 | `pip install holehe` | → WebSearch |
| phoneinfoga | 国际号码 | `pip install phoneinfoga` | → WebSearch |

**快速安装**：`pip install maigret sherlock-project theharvester holehe phoneinfoga`  
**完整依赖清单**：[`DEPENDENCIES.md`](DEPENDENCIES.md)

> 请注意：OSINT工具搜索**可能触发目标网站的访问日志**。请遵守当地法律法规，本工具仅用于合法尽调场景。

### 5. MCP连接器非默认集成

企查查(qcc-company)、天眼查(tyc-mcp)等MCP连接器需在WorkBuddy中手动安装，非开箱即用。

| 场景 | 数据质量 | 备注 |
|:-----|:--------|:-----|
| MCP已安装 + API Key有效 | ✅ 精确工商/股权/司法数据 | 推荐配置 |
| 无MCP + WebSearch | ⚠️ 60-70%准确率 | 降级可用 |
| MCP已安装但API Key过期 | ⚠️ 需重新认证 | 各连接器独立计费 |

### 6. Word/PDF/HTML报告依赖Python包

| 输出格式 | 依赖包 | 缺失后 |
|:--------|:------|:------|
| Word (docx) | `python-docx` | 降级为Markdown |
| HTML (设计型) | 无需额外依赖 | 始终可用 |
| PDF | `reportlab` / `pymupdf` | 降级为Markdown |

### 7. 粘贴模式下部分功能降级

将SKILL.md粘贴到ChatGPT/Claude/豆包等平台使用时：

| 功能 | 完整模式（WorkBuddy） | 粘贴模式 |
|:-----|:-------------------|:---------|
| MCP数据连接 | ✅ | ❌（需手动提供数据） |
| 动态编排器 | ✅ | ❌（需手动选择角色） |
| 异步并行调用 | ✅ | ❌（LLM串行） |
| L1+L2质量扫描 | ✅ | ⚠️ 仅L1（吴德厚prompt规则） |
| 子skill按需加载 | ✅ | ✅ |
| 13角色全部可用 | ✅ | ✅ |
| 六层防杜撰 | ✅ | ✅ |

---

## 平台特定限制

### 8. 非WorkBuddy平台的MCP不可用

MCP连接器仅在WorkBuddy/OpenClaw/CodeBuddy平台可用。其他平台强制降级为WebSearch。

### 9. 国产Agent平台System Prompt长度受限

百炼/千帆/元器/Coze等平台的System Prompt限制（8K-16K）可能导致子skill加载不全。

**缓解**：可根据目标平台手动裁剪SKILL.md，仅保留核心角色定义 + 铁律。

### 10. 本地模型（Ollama/vLLM）推理能力边界

- 需要8K+上下文窗口的模型
- OSINT本地工具无法调用
- 输出质量取决于模型本身

---

## 前版本限制（v0.5.0 已解决）

| 限制 | v0.5.0-v0.5.0状态 | v0.5.0状态 |
|:-----|:----------------|:----------|
| 无日志和可观测性 | ❌ 黑盒运行 | ✅ SentinelMiddleware + JSON报告 |
| 错误处理纯Prompt | ❌ 仅指令 | ✅ 3层try/except链 + 重试 + 降级 |
| 无跨角色数据传递 | ❌ 角色独立输出 | ✅ `extract_structured_data()` Phase间传递 |
| 调度规则硬编码 | ❌ Prompty硬编码 | ✅ MODE_TEMPLATES + CONDITIONAL_BRANCH_RULES 结构化 |
| 子skill加载无缓存 | ⚠️ 依赖模型 | ✅ 单会话内缓存（不再重复加载已加载的子skill） |
| 质量检查自动化率低 | ❌ 30% | ✅ L1正则扫描零成本 + L2深度验证评分0-100 |
| 版本号不统一 | ❌ SKILL.md 0.0.1 ≠ package.json v0.5.0 | ✅ 全文件统一 v0.5.0 |

---

## 演进路线

| 阶段 | 目标 | 当前状态 |
|:-----|:-----|:--------|
| Phase 1 | 角色化Prompt工程 + 6大尽调能力 + 工程化质量保障 + 8种部署形态 | ✅ **v0.5.0 已完成** |
| Phase 2 | 多Agent并行 + 平台深度适配 → 真并发Agent (v0.5.0) + 测试工程化 (v0.5.0) | ✅ **v0.5.0 当前版本** |
| Phase 3 | RAG + 本地知识库 + 端到端一键尽调流水线 | 📋 规划中 |

> 完整路线图以本仓库公开文档和 `docs/RELEASE_PORTAL.md` 为准；私有开发计划不进入公开包。

---

## 诚实声明

本项目的核心哲学是**只摆事实，不给建议**。以下承诺适用于整个项目周期：

1. ✅ 每条数据标注来源（`[来源: 工具, 参数, 时间]`）
2. ✅ 不确定数据标注不确定度（`[未获取]` / `[推测]` / `[数据不一致]`）
3. ✅ 绝不编造数字、日期、人名、财务数据
4. ✅ 绝不输出信贷决策结论（建议/推荐/风险可控 等）
5. ⚠️ 不提供投资建议、法律意见、税务咨询
6. ⚠️ OSINT搜索合法性由用户自行判断
7. ❌ 不保证100%覆盖所有公开信息（受限于数据源可用性）
