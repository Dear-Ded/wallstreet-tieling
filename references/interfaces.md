# 华尔街驻铁岭办事处 — 接口参考

> 本文件为技术总监周通的快速参考手册。详细接口体系定义见 SKILL.md 第五章·兵器。

## Tier 1：开箱即用（任何平台）

### WebSearch
- **用途**：通用搜索，新闻舆情、行业动态、公开报道
- **调用方式**：各平台内置工具
- **参数**：query (string), topic (可选: news/finance/technology等)
- **适用角色**：王思远（行业动态）、赵刚（舆情预警）、张铁柱（企业新闻）

### WebFetch
- **用途**：抓取特定网页内容并结构化提取
- **调用方式**：各平台内置工具
- **参数**：url (string), prompt (string)
- **适用角色**：周通（接口降级时）、张铁柱（官方公示信息抓取）

### 模型知识
- **用途**：行业常识、法规解读、术语解释、财务分析框架
- **适用角色**：李明远（会计准则）、王思远（经济学原理）、赵刚（风控框架）
- **注意**：纯模型知识输出的数据必须标注 [模型推理，待核实]

## Tier 2：本地增强（需安装）

### qcc-company（企查查）⭐ 核心接口
- **用途**：工商信息、股权结构、诉讼记录、财务数据、实控人穿透
- **安装方式**：Connector配置
- **核心接口**：
  - `get_company_by_query` - 模糊搜索企业（张铁柱首选）
  - `get_company_registration_info` - 工商登记信息
  - `get_shareholder_info` - 股东信息
  - `get_actual_controller` - 实际控制人穿透（张铁柱三层穿透法关键接口）
  - `get_beneficial_owners` - 受益所有人（AML合规口径）
  - `get_financial_data` - 财务数据（李明远五维X光数据源）
  - `get_external_investments` - 对外投资
  - `get_contact_info` - 联系方式
  - `get_change_records` - 工商变更记录（张铁柱变更异常分析）
  - `get_key_personnel` - 主要管理人员
  - `get_branches` - 分支机构
  - `get_listing_info` - 上市信息
  - `get_annual_reports` - 年度报告
  - `verify_company_accuracy` - 企业信息核验（郑慎之审计用）

### neodata-financial-search
- **用途**：金融数据查询（A股行情、财务数据、资金流向）
- **安装方式**：`npx skills add neodata-financial-search -g -y`
- **适用角色**：李明远（实时行情补充）、王思远（行业数据）

### deep-research
- **用途**：深度调研（学术级）
- **安装方式**：`npx skills add deep-research -g -y`
- **适用角色**：王思远（行业深度研究）、赵刚（风险深度排查）

### multi-search-engine
- **用途**：多搜索引擎聚合
- **安装方式**：`npx skills add multi-search-engine -g -y`
- **适用角色**：周通（接口扩展时多源交叉验证）

### lingxi-financialsearch-skill
- **用途**：国泰海通金融数据
- **安装方式**：`npx skills add lingxi-financialsearch-skill -g -y`
- **适用角色**：李明远（A股财务数据补充）

### tencent-news
- **用途**：新闻资讯搜索
- **安装方式**：`npx skills add tencent-news -g -y`
- **适用角色**：王思远（政策动态）、赵刚（舆情预警）

### excel-xlsx
- **用途**：Excel文件处理
- **安装方式**：`npx skills add excel-xlsx -g -y`
- **适用角色**：刘文华（报告导出Excel）、李明远（财务数据表格化）

### nano-pdf
- **用途**：PDF文件处理
- **安装方式**：`npx skills add nano-pdf -g -y`
- **适用角色**：刘文华（报告导出PDF）、张铁柱（用户上传PDF解析）

### baidu-search
- **用途**：百度搜索
- **安装方式**：`npx skills add baidu-search -g -y`
- **适用角色**：王思远（中文行业资讯）、张铁柱（企业中文新闻）

### tyc-mcp（天眼查）⭐ 核心接口
- **用途**：162项企业全维度数据，与企查查形成双源验证
- **安装方式**：Connector配置
- **覆盖**：工商、司法、知识产权、经营、历史、董监高等全维度
- **适用角色**：张铁柱（企查查替代/补充）、李明远（财务数据交叉验证）
- **备注**：与qcc-company形成双源验证，数据质量更高

## Tier 3：全网接口猎取（周通动态发现）

### 国家企业信用信息公示系统
- **URL**：https://www.gsxt.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：中国境内企业工商信息验证
- **适用角色**：张铁柱（工商信息交叉验证）、郑慎之（数据溯源核查）

### 裁判文书网
- **URL**：https://wenshu.court.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：中国境内诉讼记录
- **适用角色**：张铁柱（诉讼记录）、赵刚（法律风险）

### 信用中国
- **URL**：https://www.creditchina.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：失信被执行人、行政处罚
- **适用角色**：赵刚（信用风险）、张铁柱（失信查询）

### OpenCorporates
- **URL**：https://opencorporates.com/
- **获取方式**：公开API / WebFetch
- **覆盖**：全球企业基本信息
- **适用角色**：张铁柱（海外企业尽调）

### FRED (Federal Reserve Economic Data)
- **URL**：https://fred.stlouisfed.org/
- **获取方式**：公开API
- **覆盖**：美国宏观经济数据
- **适用角色**：王思远（宏观经济分析）

### World Bank API
- **URL**：https://data.worldbank.org/
- **获取方式**：公开API
- **覆盖**：国际经济数据
- **适用角色**：王思远（国际对比分析）

## 接口-角色映射速查

| 角色 | 首选接口 | 备选接口 |
|------|----------|----------|
| 张铁柱（尽调） | qcc-company + tyc-mcp | 国家企业信用信息公示系统、OpenCorporates |
| 李明远（财务） | qcc-company(财务数据) | neodata-financial-search、lingxi-financialsearch-skill |
| 王思远（行业） | WebSearch + deep-research | FRED、World Bank API、tencent-news |
| 赵刚（风险） | qcc-company(诉讼/失信) | 信用中国、裁判文书网、WebSearch(舆情) |
| 刘文华（报告） | excel-xlsx + nano-pdf | - |
| 郑慎之（审计） | verify_company_accuracy | WebSearch(交叉验证) |
