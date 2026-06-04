<p align="center">
  <img src="https://img.shields.io/badge/version-3.6.0-c9a84c?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-WorkBuddy%20%7C%20OpenClaw%20%7C%20Marvis%20%7C%20CodeBuddy-blue?style=flat-square" alt="Platforms">
  <img src="https://img.shields.io/badge/models-Claude%20%7C%20GPT%20%7C%20Gemini%20%7C%20DeepSeek%20%7C%20混元%20%7C%209%2B-purple?style=flat-square" alt="Models">
  <img src="https://img.shields.io/badge/experts-11-orange?style=flat-square" alt="Experts">
  <img src="https://img.shields.io/badge/category-finance-c9a84c?style=flat-square" alt="Category">
  <img src="https://img.shields.io/badge/triggers-70%2B-red?style=flat-square" alt="Triggers">
</p>

# 华尔街驻铁岭办事处

> 信贷情报专家团 — 银行信贷经理的全流程情报服务
>
> 当你提到尽调、贷前、贷后、财务分析、行业研究、风险预警、授信评估、股东穿透、实控人查询、财报解读时，我们就来了。
>
> **只摆事实，不给建议——决策是你的事儿，扒皮是我们的活儿。**

🌐 **在线主页**: https://dear-ded.github.io/wallstreet-tieling/

---

## 📦 安装

```bash
npx skills add Dear-Ded/wallstreet-tieling -g -y
```

| 平台 | 安装方式 |
|------|---------|
| **WorkBuddy** | `npx skills add Dear-Ded/wallstreet-tieling -g -y` |
| **OpenClaw / CodeBuddy** | `npx skills add Dear-Ded/wallstreet-tieling -g -y` |
| **Marvis 马维斯** | 下载 [`marvis/SKILL.md`](marvis/SKILL.md) 放置到技能目录 → [安装指南](marvis/README.md) |
| **通用AI平台** | 复制 [SKILL.md](SKILL.md) 内容粘贴到对话中 |

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔍 **企业尽调** | 工商信息 · 股权穿透(至自然人) · 实控人 · 关联关系 · 失信被执行人 |
| 💰 **财务分析** | 五维财务X光 · 偿债能力 · 现金流真相 · 粉饰识别 · 3年行业对标 |
| 📊 **行业研究** | PEST宏观 · 五力竞争 · 产业链 · 周期定位 · 政策解读 |
| 🚨 **风险识别** | 风险雷达六维图 · 担保圈传染 · 合规扫描 · 贷后监控 · 压力测试 |
| 📝 **智能报告** | Word/PDF/Markdown输出 · 公文排版规范 · 图表嵌入 · 跨平台适配 |
| 🎯 **格式确认** | 输出前询问格式偏好 · 默认Markdown+可转Word/PDF · 移动端/打印适配 |

---

## 🎯 触发词

| 场景 | 触发词 |
|------|--------|
| **核心业务** | 尽调、贷前调查、贷后检查、财务分析、行业研究、风险预警、授信评估、信贷审查 |
| **企业调查** | 企业查询、客户尽调、股东穿透、实控人、关联方、担保圈、工商信息、股权结构、担保、抵押、质押、征信 |
| **财务分析** | 财报分析、财务报表、资产负债表、利润表、现金流量表、偿债能力、现金流、审计报告 |
| **行业研究** | 行业对标、竞争格局、PEST分析、五力模型、产业链 |
| **报告辅助** | 尽调报告、授信报告、信贷报告、风险报告 |
| **输出格式** | Word文档、PDF、公文格式、公文排版、Markdown、纯文本 |
| **English** | due diligence, credit analysis, loan review, financial analysis, risk assessment, UBO, KYC, KYB, AML |
| **🔴 全网扒光** | 扒光、彻查、深挖、蛛丝马迹、追查到底、全面调查、深度调查、OSINT、开源情报 |

---

## 👥 团队

```
用户（信贷经理）
     ↓
【总经理 · 钱守正】需求翻译 · 任务分配 · Token优化
     ↓
├── 吴德厚（管理）→ 监督 · 激励 · 思想工作 · PUA
├── 陈志远（业务）→ 任务拆解 · 分配 · 质量控制
├── 周通（技术）    → 误判修复 · 模型路由 · 全网接口猎取 · Skill编排
├── 郑慎之（审计）→ 三阶段独立审计 · 数据溯源
└── 业务组：
    ├── 张铁柱（尽调）· 前SEC调查员 · "三层穿透法"
    ├── 李明远（财务）· 前PwC审计经理 · "五维财务X光"
    ├── 王思远（行业）· MIT经济学博士 · "PEST+五力+周期"
    ├── 赵刚（风险）   · 退伍军人+CRO · "风险雷达六维图"
    └── 刘文华（报告）· 前McKinsey顾问 · "金字塔+公文规范"
```

---

## ⚖️ 铁律

1. 🚫 **禁止输出信贷决策** — 给数据不给建议
2. 🚫 **禁止编造数据** — 无法验证标注 [待核实]
3. 🚫 **禁止模糊表述** — 数据说话，不用形容词
4. ✅ **所有数据标注来源** — 格式：[来源：企查查/2025年报]

---

## 🖥️ 兼容性

| 维度 | 覆盖 |
|------|------|
| **大模型** | Claude · GPT · Gemini · 通义千问 · 文心一言 · 混元 · DeepSeek · Kimi · GLM · Minimax |
| **平台** | WorkBuddy · OpenClaw · CodeBuddy · Marvis马维斯 · 通用AI对话 |
| **最低上下文** | 8,000 tokens |
| **推荐上下文** | 32,000 tokens |

---

## 📡 数据源

| Tier | 类型 | 示例 |
|------|------|------|
| Tier 1 | 开箱即用 | WebSearch · WebFetch · 模型知识 |
| Tier 2 | 本地增强 | 企查查 · 天眼查 · 启信宝 · 企业预警通 · 金融数据 |
| Tier 3 | 全网猎取 | 周通动态发现：公开API · 网页抓取 · Bash脚本 |
| Tier 4 | 用户协作 | 手动查询 · 文件上传 · API Key授权 |
| 🔴 OSINT | 全网扒光 | 官方数据 · 商业平台 · 专业领域 · 舆情监控 · 蛛丝马迹追踪 |

---

## 📄 许可

MIT License · 作者：**爹** · [GitHub](https://github.com/Dear-Ded/wallstreet-tieling) · [在线主页](https://dear-ded.github.io/wallstreet-tieling/)
