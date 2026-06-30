# 多形态部署指南

> 华尔街驻铁岭办事处不仅是一个Skill——它可以以多种形态装入各类Agent平台。
> 选你最喜欢的形态，加载方式不同，核心能力完全一样。

## 形态一览

| 形态 | 适用平台 | 加载方式 | 难度 |
|------|---------|---------|------|
| **Skill.md** | WorkBuddy/OpenClaw/CodeBuddy/通用AI | 直接粘贴或 `npx skills add` | ⭐ |
| **MCP Server** | Claude Desktop/Cursor/CodeBuddy/Windsurf | 配置 `.mcp.json` | ⭐⭐ |
| **Custom GPT** | ChatGPT | 粘贴到 Instructions | ⭐ |
| **Claude Project** | Claude.ai | 添加为 Project Knowledge | ⭐ |
| **豆包智能体** | 豆包/扣子(Coze) | 创建智能体+粘贴设定 | ⭐ |
| **百炼应用** | 阿里百炼平台 | 创建应用+注入Prompt | ⭐⭐ |
| **千帆应用** | 百度千帆 | 创建应用+知识库 | ⭐⭐ |
| **智谱智能体** | 智谱清言 | 创建智能体+粘贴 | ⭐ |
| **npm CLI** | 命令行/终端 | `npx wallstreet-tieling` | ⭐ |
| **API Endpoint** | 任何可调API的平台 | Docker部署 | ⭐⭐⭐ |

---

## 形态一：Skill.md（当前主形态）

```bash
# 安装
npx skills add Dear-Ded/wallstreet-tieling -g -y

# 或直接粘贴
复制 SKILL.md 全文 → 粘贴到任意AI对话窗口
```

---

## 形态二：MCP Server

```json
// Claude Desktop: claude_desktop_config.json
{
  "mcpServers": {
    "wallstreet-tieling": {
      "command": "npx",
      "args": ["-y", "wallstreet-tieling", "--mcp"],
      "env": {
        "WST_MCP_TIMEOUT_MS": "120000"
      }
    }
  }
}

// CodeBuddy: .mcp.json
{
  "mcpServers": {
    "wallstreet-tieling": {
      "type": "url",
      "url": "https://raw.githubusercontent.com/Dear-Ded/wallstreet-tieling/main/deploy/mcp-server.json"
    }
  }
}
```

安装后，在任何MCP兼容的Agent中直接调用：
- `investigate_company(company_name="ABC公司", depth="standard")`
- `connector_catalog()`
- `release_readiness()`
- `financial_analysis(company_name="ABC公司", years=3)`

---

## 形态三：ChatGPT Custom GPT

1. 打开 ChatGPT → Explore GPTs → Create
2. Instructions 中粘贴 `SKILL.md` 全文
3. Name: 华尔街驻铁岭办事处
4. Description: 银行信贷情报专家团。尽调/财务分析/行业研究/风险预警/人员穿透。
5. 可选：上传 `references/` 文件作为 Knowledge
6. 发布

---

## 形态四：Claude Project

1. 打开 Claude.ai → Projects → New Project
2. Project Name: 华尔街驻铁岭办事处
3. Custom Instructions 中粘贴 `CLAUDE.md`，再补充 `SKILL.md` 核心章节
4. Project Knowledge 中上传：
   - `README.md`
   - `SKILL.md`
   - `CLAUDE.md`
   - `docs/CLAUDE_CODE_ADAPTER.md`
   - `references/data-sources.md`（数据源速查表）
   - `docs/API_CONTRACTS.md`（API契约）
   - `docs/DATASOURCE_ADMISSION.md`（数据源准入）

---

## 形态五：豆包智能体 / Coze

1. 豆包APP → 发现 → 创建智能体
2. 或 Coze.cn → 创建Bot
3. 人设与回复逻辑：粘贴 `SKILL.md` 中的三、团队 + 二、铁律
4. 知识库：上传 `references/` 中所有 `.md` 文件
5. 插件：在Coze中添加搜索插件
6. 发布

---

## 形态六：百炼/千帆/元器/智谱

这些平台的创建方式高度相似：

1. 创建应用/智能体
2. System Prompt 中粘贴 `SKILL.md`
3. 知识库上传 `references/` 文件
4. 开启联网搜索
5. 发布

---

## 形态七：npm CLI 工具

```bash
# 全局安装
npm install -g wallstreet-tieling

# 直接使用
wallstreet-tieling "帮我查一下ABC公司"
wallstreet-tieling --company "ABC公司" --depth deep --format html
```

---

## 形态八：API Endpoint（Docker）

```bash
# 拉取镜像
docker pull dearded/wallstreet-tieling:latest

# 启动
docker run -p 8080:8080 dearded/wallstreet-tieling

# 调用
curl -X POST http://localhost:8080/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"company": "ABC公司", "depth": "standard", "format": "markdown"}'
```

---

## 核心设计原则

无论哪种形态，核心能力完全一致：

1. 铁律0-6 不变
2. 团队13人分工不变
3. 数据源路由(Tier 0-4)不变
4. 推论严谨性(三步法)不变
5. 审计检查清单(14项)不变

改变的只是"怎么装"，不是"装了什么"。
