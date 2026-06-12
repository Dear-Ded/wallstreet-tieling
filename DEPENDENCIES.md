# 环境依赖完整披露

**最后更新**: 2026-06-12  
**适用版本**: v1.0

本文档列出 wallstreet-tieling 项目的所有运行时依赖，按类别分级标注必要性和缺失后的功能降级影响。

---

## 依赖分级体系

| 等级 | 含义 | 缺失影响 |
|:-----|:-----|:---------|
| 🔴 **必需** | 核心功能运行的前提条件 | 对应功能完全不可用 |
| 🟠 **强烈建议** | 显著提升尽调质量和数据覆盖 | 数据覆盖和准确性大幅下降 |
| 🟡 **可选增强** | 特定场景下的质量加成 | 功能降级但不影响基本使用 |
| 🟢 **开发/部署** | 仅在特定部署形态下需要 | 该部署形态不可用 |

---

## 一、LLM API 层

### 🔴 DeepSeek API（推荐）

| 项目 | 说明 |
|:-----|:-----|
| **用途** | 动态编排器 + 全体13位专家角色推理 |
| **Key格式** | `sk-` 开头 |
| **推荐模型** | deepseek-chat (V3), deepseek-reasoner (R1) |
| **获取方式** | https://platform.deepseek.com/ |
| **环境变量** | `DEEPSEEK_API_KEY` |
| **成本参考** | ¥1-2/M token (V3), ¥4-16/M token (R1) |
| **缓存优惠** | 命中缓存输入 ¥0.1/M（90%折扣） |
| **缺失后影响** | 动态编排器和API服务不可用。降级为粘贴SKILL.md到第三方AI平台使用 |

### 🟡 OpenAI API

| 项目 | 说明 |
|:-----|:-----|
| **用途** | 备选LLM后端（fallback链: DEEPSEEK_API_KEY → OPENAI_API_KEY） |
| **Key格式** | `sk-` 开头 |
| **推荐模型** | gpt-4o, gpt-4o-mini |
| **环境变量** | `OPENAI_API_KEY` |
| **成本参考** | ¥17.5-70/M token (GPT-4o), ¥1.1-4.4/M token (GPT-4o-mini) |
| **缺失后影响** | DeepSeek不可用时无法自动fallback |

### 🟡 MiMo Token Plan（订阅制）

| 项目 | 说明 |
|:-----|:-----|
| **用途** | 备选LLM后端，适合宿主平台内置积分场景 |
| **Key格式** | `tp-` 开头（Token Plan），或 `sk-` 开头（按量付费） |
| **推荐模型** | mimo-v2.5, mimo-v2.5-pro |
| **获取方式** | https://token-plan-cn.xiaomimimo.com/ |
| **成本参考** | $0.435-3.48/M token |
| **配置方案** | 见 `~/.workbuddy/skills/mi-token-plan-setup/` |
| **缺失后影响** | 无影响（非默认LLM后端） |

---

## 二、MCP 连接器层

### 🔴 企业工商数据（至少安装一个）

| 连接器 | 平台 | 接口数 | 覆盖范围 | 安装方式 |
|:-------|:-----|:------|:---------|:---------|
| **qcc-company** | 企查查 | 15个工具 | 工商登记、年报、股东、高管、对外投资、实控人 | 宿主平台内置/MCP配置启用 |
| **tyc-mcp** | 天眼查 | 162个工具 | 工商、司法、知识产权、经营、历史、董监高全维度 | 宿主平台内市场安装 |

**缺失后影响**: 🟠 无企业工商精确数据源。强制降级为WebSearch + 国家企业信用信息公示系统手动查询。关键字段（注册资本、股权比例、司法诉讼）准确性从95%+降至60-70%。

### 🟡 金融数据增强

| 连接器 | 平台 | 用途 | 安装方式 |
|:-------|:-----|:-----|:---------|
| **lingxi-financialsearch** | 国泰海通灵犀 | A股实时行情、F10财务数据、技术指标 | 宿主平台市场安装 |
| **neodata-financial-search** | NeoData | 自然语言全品类金融数据查询 | 宿主平台市场安装 |
| **futuapi** | 富途 OpenAPI | 港股/美股行情、期权链、K线、分时 | 宿主平台市场安装 |

**缺失后影响**: 🟡 金融数据精度下降。行情数据降级为WebSearch财经网站爬取（延迟5-15分钟）；F10财务数据降级为年报PDF手动提取。

### 🟡 其他连接器

| 连接器 | 用途 | 缺失后影响 |
|:-------|:-----|:----------|
| **github (MCP)** | 开源情报、技术栈分析 | 🟡 GitHub相关调查无法进行 |
| **qq-mail** | 邮件通知、报告发送 | 🟢 报告无法自动发送，需手动处理 |
| **ardot** | UI设计工具 | 🟢 HTML报告视觉设计降级 |

---

## 三、Python 运行时层

### 🔴 Python 核心（API 服务模式）

| 包名 | 版本要求 | 用途 | 安装命令 |
|:-----|:--------|:-----|:---------|
| **flask** | ≥2.0 | REST API Web框架 | `pip install flask` |
| **flask-cors** | ≥3.0 | 跨域请求支持 | `pip install flask-cors` |
| **aiohttp** | ≥3.8 | 异步HTTP客户端（动态编排器并行API调用） | `pip install aiohttp` |
| **requests** | ≥2.28 | 同步HTTP客户端（API Server） | `pip install requests` |

**安装方式**:

```bash
# 快速安装
pip install flask flask-cors aiohttp requests

# Docker（自动安装，见 Dockerfile）
docker build -t wallstreet-tieling .
```

**缺失后影响**: 🔴 API 服务（`python api/server.py`）、Docker容器、动态编排器的异步并行调用全部不可用。降级为粘贴SKILL.md使用。

### 🟡 Python 可选增强

| 包名 | 用途 | 缺失后影响 |
|:-----|:-----|:----------|
| **python-docx** | Word报告生成 | 🟡 Word格式不可用，降级为Markdown |
| **pymupdf (fitz)** | PDF提取/处理 | 🟡 PDF附件解析不可用 |
| **Pillow** | 图像处理 | 🟡 扫描件OCR预处理不可用 |
| **pytesseract** | OCR文字识别 | 🟡 图片/扫描件文字提取不可用 |
| **openpyxl** | Excel读写 | 🟡 xlsx格式财务数据处理不可用 |

---

## 四、Node.js 运行时层

### 🔴 Node.js（npm CLI + MCP Server 模式）

| 项目 | 说明 |
|:-----|:-----|
| **版本要求** | Node.js ≥18.0.0 |
| **用途** | npm CLI工具、MCP Server |
| **缺失后影响** | 🔴 `npx wallstreet-tieling` CLI和`npm run mcp`不可用。不影响粘贴模式和API服务模式 |

### npm 包信息

| 项目 | 说明 |
|:-----|:-----|
| **包名** | `wallstreet-tieling` |
| **当前版本** | v0.5.0 |
| **入口** | `SKILL.md`（主入口）、`bin/cli.js`（CLI）、`lib/mcp-server.js`（MCP） |
| **安装** | `npx skills add Dear-Ded/wallstreet-tieling -g -y` |

---

## 五、OSINT 工具层

### 🟡 本地安装（强烈建议）

这些工具为 `sub-skills/zhou-tong.md`（技术总监）和 `sub-skills/ma-li-quan.md`（人员背调）提供开源情报收集能力。

| 工具 | 覆盖范围 | 用途 | 安装方式 |
|:-----|:--------|:-----|:---------|
| **maigret** | 3,000+ 网站 | 用户名跨平台搜索 | `pip install maigret` |
| **sherlock** | 400+ 网站 | 社交媒体用户名搜索 | `pip install sherlock-project` |
| **theHarvester** | 多搜索引擎 | 邮箱/域名/IP信息收集 | `pip install theharvester` |
| **holehe** | 120+ 网站 | 邮箱注册状态检查 | `pip install holehe` |
| **phoneinfoga** | 国际号码 | 电话号码信息查询 | `pip install phoneinfoga` |

### 降级机制

OSINT工具缺失时，系统自动降级：

```
L1: 尝试直接调用 pip 包（已安装 → 使用）
L2: 检测 CLI 工具是否在 PATH 中（which <tool>）
L3: 均不可用 → 降级为 WebSearch + WebFetch
    └── 标注 [来源: WebSearch, 引擎结果聚合]
```

**缺失后影响**: 🟠 人员背调（马力全）和OSINT模块的开源情报收集能力显著下降。用户名跨平台关联、邮箱泄露检测、手机号信息查询等功能均降级为纯WebSearch，准确性从85%+降至50-60%。

### 🟢 辅助工具（可选）

| 工具 | 用途 | 缺失后影响 |
|:-----|:-----|:----------|
| **socid_extractor** | 社交账号信息提取 | 🟢 社交账号数据提取降级 |
| **python-whois** | WHOIS域名查询 | 🟢 域名注册信息降级为WebSearch |
| **dnspython** | DNS解析 | 🟢 DNS记录查询降级为在线工具 |
| **cloudscraper** | Cloudflare绕过 | 🟢 部分网站的WebFetch可能失败 |

---

## 六、部署环境层

### 🔴 Docker（容器模式）

| 项目 | 说明 |
|:-----|:-----|
| **基础镜像** | `python:3.11-slim` |
| **端口** | 8080 |
| **命令** | `docker build -t wallstreet-tieling . && docker run -p 8080:8080 -e OPENAI_API_KEY=sk-xxx wallstreet-tieling` |
| **缺失后影响** | 🔴 Docker容器模式不可用，不影响其他部署形态 |

### 🟡 其他部署平台

| 平台 | 配置位置 | 缺失后影响 |
|:-----|:--------|:----------|
| **npm 发布** | `package.json` | 🟡 npm CLI安装不可用 |
| **ClawHub** | `clawhub.json` | 🟡 ClawHub市场发布不可用 |
| **OpenClaw** | `openclaw.json` | 🟡 OpenClaw市场不可用 |

---

## 七、外部免费 API（可选增强）

这些API无需API Key或免费额度充足，仅用于特定场景增强。

| API | 免费额度 | 用途 | 缺失后影响 |
|:----|:--------|:-----|:----------|
| **ocr.space** | 500次/月 | 图片/扫描件文字识别 | 🟢 扫描件OCR降级 |
| **Tavily Search** | 1,000次/月 | AI增强网络搜索 | 🟢 降级为普通WebSearch |
| **Perplexity API** | 试用额度 | AI增强联网回答 | 🟢 降级为普通WebSearch |
| **Exa Search** | 免费层 | 神经搜索引擎 | 🟢 降级为普通WebSearch |

---

## 八、完整依赖清单（按部署形态）

### 形态A：粘贴模式（最小依赖）

**零依赖**。复制 `SKILL.md` 粘贴到任意AI对话窗口即可。所有13位专家角色、6层防杜撰、10条铁律均包含在SKILL.md中。

**局限**：无MCP连接器（企业数据需手动提供）、无动态编排器（需手动选择角色）、无自动化报告生成。

### 形态B：WorkBuddy 完整模式

| 类别 | 依赖 | 必需度 |
|:-----|:-----|:------|
| MCP连接器 | qcc-company 或 tyc-mcp（至少一个） | 🔴 |
| MCP连接器 | lingxi-financialsearch, neodata-financial-search, futuapi | 🟡 |
| OSINT工具 | maigret, sherlock, theHarvester, holehe, phoneinfoga | 🟡 |
| Python包 | aiohttp（动态编排器） | 🟡 |

### 形态C：Docker / REST API 模式

| 类别 | 依赖 | 必需度 |
|:-----|:-----|:------|
| Python包 | flask, flask-cors, aiohttp, requests | 🔴 |
| LLM API Key | DEEPSEEK_API_KEY 或 OPENAI_API_KEY | 🔴 |
| MCP连接器 | 不适用（REST API模式下MCP不可用，数据源降级为WebSearch） | — |
| Docker | docker CLI（仅容器模式） | 🔴 |

### 形态D：npm CLI 模式

| 类别 | 依赖 | 必需度 |
|:-----|:-----|:------|
| Node.js | ≥18.0.0 | 🔴 |
| LLM API Key | 环境变量 DEEPSEEK_API_KEY 或 OPENAI_API_KEY | 🔴 |

---

## 九、平台特定依赖

### WorkBuddy 内置依赖（workbuddy-native 分支）

| 内置资源 | 说明 |
|:---------|:-----|
| **30+ 内置积分模型** | DeepSeek V4, MiMo v2.5, GPT-4o, Claude 3.5 Sonnet 等 |
| **MCP 连接器管理器** | 自动发现和路由 MCP 连接器 |
| **Expert 模式** | 加载单个专家子技能 |
| **Expert Team 模式** | 加载完整13人专家团 |

> 配置指南: `SKILL.md` · `deploy/multi-platform-guide.md`

### 其他平台降级说明

| 平台 | 最大限制 | 影响 |
|:-----|:--------|:-----|
| 豆包 | 系统prompt长度受限 | 全量SKILL.md可能超限，需精简 |
| Coze | Bot prompt长度8K | 仅能加载前6-8个角色 |
| 百炼/千帆/元器 | 系统prompt限制 | 同Coze |
| Ollama/LM Studio | 本地模型推理能力 | 需要支持8K+上下文的模型 |

---

## 十、快速安装脚本

### 一键安装（推荐）

```bash
# WorkBuddy Skill 市场（含所有子技能）
npx skills add Dear-Ded/wallstreet-tieling -g -y

# API 服务模式
pip install flask flask-cors aiohttp requests
export DEEPSEEK_API_KEY="sk-xxx"
python api/server.py

# Docker 模式
docker run -p 8080:8080 -e DEEPSEEK_API_KEY=sk-xxx dearded/wallstreet-tieling
```

### 增强安装（OSINT工具）

```bash
# 人员背调增强（5个OSINT工具）
pip install maigret sherlock-project theharvester holehe phoneinfoga

# 文档处理增强
pip install python-docx pymupdf Pillow pytesseract openpyxl
```

### 验证安装

```bash
# 检查Python依赖
python -c "import flask; import flask_cors; import aiohttp; print('Python OK')"

# 检查Node.js
node --version  # 应 ≥18.0.0

# 检查OSINT工具
pip list | grep -E "maigret|sherlock|holehe|phoneinfoga|theharvester"

# 检查MCP连接器（WorkBuddy内）
ls ~/.workbuddy/skills/ | grep -E "qcc|tyc|lingxi|neodata|futu"
```

---

> ⚠️ 本文档诚实反映当前依赖状态。若某项依赖尚不具备但是必需的，请联系项目维护者或参考 [CONTRIBUTING.md](CONTRIBUTING.md) 参与改进。
