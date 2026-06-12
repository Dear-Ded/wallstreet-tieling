# 🔧 维护者交接手册

> 最后更新: 2026-06-12 · v1.0 · workbuddy 特调版

---

## 📂 仓库结构一览

```
wallstreet-tieling/
├── SKILL.md              ← WorkBuddy 主入口，加载此文件激活专家团
├── README.md             ← GitHub 公开库首页
├── index.html            ← GitHub Pages 主页 (液态玻璃品牌站)
├── CHANGELOG.md          ← 版本日志 (按日期倒序)
├── CONTRIBUTING.md       ← 贡献指南
├── DEPENDENCIES.md       ← 环境依赖全披露 (四级分类)
├── MAINTAINERS.md        ← 维护者信息
├── package.json          ← npm 包配置 (v1.0.0)
├── requirements.txt      ← Python 依赖 (aiohttp + pytest)
├── robots.txt            ← SEO 爬虫规则
├── sitemap.xml           ← 站点地图
├── LICENSE               ← MIT
├── api/                  ← Python 编排引擎
│   ├── orchestrator.py   ← ★ 主编排器 (4-Phase Pipeline)
│   ├── wst.py            ← CLI 入口
│   ├── agent.py          ← Agent 实例 (状态/记忆/情感)
│   ├── agent_registry.py ← Agent 注册中心
│   ├── personality.py    ← 13角色人格档案
│   ├── quality_rules.py  ← L1正则 + L2政委质检
│   ├── config.py         ← 配置 + MODE_TEMPLATES (7种模式)
│   ├── render_docx.py    ← ★ 颜好看公文排版引擎
│   ├── render_html.py    ← ★ 颜好看玻璃态HTML渲染
│   ├── server.py         ← REST API 服务
│   └── utils.py          ← 工具函数
├── core/                 ← 平台无关引擎核心 (v0.5.0 遗产)
├── sub-skills/           ← 13角色Prompt文件
├── references/           ← 参考文档 (调度表/数据源/兼容性)
├── demo/                 ← 报告样例 (虚构数据)
├── tests/                ← 测试 (402 pass)
├── deploy/               ← 部署配置 (Docker/MCP/ClawHub)
└── docs/                 ← 内部文档 (gitignored)
```

---

## 🌿 分支策略

| 分支 | 定位 | 用途 |
|------|------|------|
| **`master`** | 通用版 | 跨14+平台15+模型通用 |
| **`workbuddy`** | WorkBuddy 特调 | ★ 13角色全管线 + 5格式代码级强制输出 |
| **`gh-pages`** | 主页部署 | GitHub Pages 静态站点 |

### 分支同步规则
- `master` 负责品牌面、文档、兼容性
- `workbuddy` 继承 master，增加代码级强制管线
- 功能开发 → workbuddy 先行验证 → 稳定后同步到 master

---

## 🚀 如何加载专家团

### WorkBuddy（推荐）
```bash
# 安装 workbuddy 特调版
npx skills add Dear-Ded/wallstreet-tieling@workbuddy -g -y

# 通用版
npx skills add Dear-Ded/wallstreet-tieling -g -y
```

### CLI 命令
```bash
# 全火力尽调 (13人)
python api/wst.py --target "星辰科技有限公司" --mode full

# 标准尽调
python api/wst.py --target "星辰科技有限公司" --mode standard

# 深度尽调 (含条件分支)
python api/wst.py --target "星辰科技有限公司" --mode deep

# 中小企业 / 人员背调 / 报告生成
python api/wst.py --target "星辰科技有限公司" --mode sme
python api/wst.py --target "某人" --mode people
```

---

## 🔄 执行 Pipeline (workbuddy 版)

```
Phase 1: 钱守正拆解 → 陈志远分步 → 业务8人并行 (张/李/王/赵/马/周)
  → 信号检测 → 条件分支追加
Phase 2: 郑慎之交叉验证 + 吴德厚政委质检 (L1正则 + L2评分)
Phase 3: 刘文华整合 → 颜好看排版渲染
Phase 4: 暗哨全流程审计 (时间/成本)
输出: .md + .docx(公文) + .html(玻璃态) + .json(结构化)
```

---

## 🔑 配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DEEPSEEK_API_KEY` | — | 推荐API Key |
| `OPENAI_API_KEY` | — | Fallback |
| `WALLSTREET_MODEL` | deepseek-chat | 模型选择 |
| `WALLSTREET_CONCURRENCY` | 5 | 并发Agent数 |
| `WALLSTREET_TIMEOUT` | 300 | API超时(秒) |

---

## 🛠️ 需要后端做的事

### 看板清单
1. **GitHub About 更新**: 仓库描述 + Topics + Website (无API写权限)
2. **npm 发布**: `npm publish` 到 npm registry
3. **GitHub Release**: 为 v1.0.0 创建 Release 页面
4. **技能市场上架**: skillsmp.com / skillregistry.io / lobehub.com

### About 描述 (复制粘贴到 GitHub Settings)
```
尽调有魂，数据不胡诌 · 13-agent concurrent AI crew | platform-agnostic v1.0 | due diligence/OSINT/risk assessment/people investigation
```

### 推荐 Topics
`ai-agent` `due-diligence` `financial-analysis` `osint` `risk-assessment` `kyc` `aml` `credit-intelligence` `banking` `prompt-engineering` `workbuddy` `deepseek` `尽调` `信贷风控` `企业调查`

---

## 📊 关键数字 (全仓库一致)

- 版本: v1.0.0
- 角色: 13人
- 测试: 402 pass
- 模型: 15+
- 数据源: 30+
- 部署: 8种形态
- 防杜撰: 6层
- 质量门禁: L1+L2

---

## ⚠️ 注意事项

1. **output/ 目录已 gitignored** — 本地生成的报告不会推送到公开库
2. **demo/ 文件使用虚构数据** — 星辰科技/远航控股/赵建国均为虚构名
3. **privacy 敏感** — 任何含有真实公司/人名的数据不得提交到公开库
4. **版本号统一** — 修改版本时，须全仓库同步 (SKILL.md/package.json/deploy/*/README/CHANGELOG/index.html)
