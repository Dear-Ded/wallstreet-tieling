# GitHub 可发现性设置指南

> 完成下面两个步骤后，当前搜索可见性从 2.9/10 提升到 7.0/10

---

## 步骤一：设置 15 个 Topics

### 操作路径
浏览器打开 https://github.com/Dear-Ded/wallstreet-tieling
→ 页面右侧 About 区域 → 点击 Topics 旁边的齿轮图标

### 逐条输入（每输一个按回车确认）

```
ai-agent
agent-skill
due-diligence
financial-analysis
risk-assessment
osint
banking
kyc
credit-intelligence
workbuddy
deepseek
multi-agent
skill
corporate-investigation
chinese
```

### 保存
点击 Save changes

### 效果
About 区域显示 15 个蓝色标签。GitHub 搜索 `due-diligence agent-skill` 可见本仓库。

---

## 步骤二：设置 Description

### 操作路径
仓库首页 → ⚙️ Settings → General → Description 输入框

### 粘贴以下英文描述
```
AI credit intelligence agent skill for banking due diligence, financial analysis, risk assessment, KYC/KYB/AML/OSINT. 13-agent crew with 10-30 data sources. Install: npx skills add Dear-Ded/wallstreet-tieling -g -y
```

### 保存
点击 Save

### 效果
仓库首页 About 区域显示英文描述。搜索 `AI agent skill banking KYC` 可见。

---

## 验证
完成后搜索以下词确认：
- `due-diligence agent-skill`（应在前5名）
- `OSINT banking`（应在前10名）
- `credit-intelligence workbuddy`（应在前3名）
- `尽调 agent-skill`（应在前5名）

## FAQ
- **Topics 输入不显示？** → 每个 topic 输入后按回车确认
- **最多几个？** → GitHub 限制 20 个，当前 15 个
