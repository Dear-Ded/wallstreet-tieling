# 华尔街驻铁岭办事处 — 接口参考

## Tier 1：开箱即用（任何平台）

### WebSearch
- **用途**：通用搜索，新闻舆情、行业动态、公开报道
- **调用方式**：各平台内置工具
- **参数**：query (string), topic (可选: news/finance/technology等)

### WebFetch
- **用途**：抓取特定网页内容并结构化提取
- **调用方式**：各平台内置工具
- **参数**：url (string), prompt (string)

## Tier 2：本地增强（需安装）

### qcc-company（企查查）
- **用途**：工商信息、股权结构、诉讼记录、财务数据、实控人穿透
- **安装方式**：Connector配置
- **核心接口**：
  - `get_company_by_query` - 模糊搜索企业
  - `get_company_registration_info` - 工商登记信息
  - `get_shareholder_info` - 股东信息
  - `get_actual_controller` - 实际控制人穿透
  - `get_beneficial_owners` - 受益所有人
  - `get_financial_data` - 财务数据
  - `get_external_investments` - 对外投资
  - `get_contact_info` - 联系方式
  - `get_change_records` - 工商变更记录
  - `get_key_personnel` - 主要管理人员
  - `get_branches` - 分支机构
  - `get_listing_info` - 上市信息
  - `get_annual_reports` - 年度报告
  - `verify_company_accuracy` - 企业信息核验

### neodata-financial-search
- **用途**：金融数据查询（A股行情、财务数据、资金流向）
- **安装方式**：`npx skills add neodata-financial-search -g -y`

### deep-research
- **用途**：深度调研（学术级）
- **安装方式**：`npx skills add deep-research -g -y`

### multi-search-engine
- **用途**：多搜索引擎聚合
- **安装方式**：`npx skills add multi-search-engine -g -y`

### lingxi-financialsearch-skill
- **用途**：国泰海通金融数据
- **安装方式**：`npx skills add lingxi-financialsearch-skill -g -y`

### tencent-news
- **用途**：新闻资讯搜索
- **安装方式**：`npx skills add tencent-news -g -y`

### excel-xlsx
- **用途**：Excel文件处理
- **安装方式**：`npx skills add excel-xlsx -g -y`

### nano-pdf
- **用途**：PDF文件处理
- **安装方式**：`npx skills add nano-pdf -g -y`

### baidu-search
- **用途**：百度搜索
- **安装方式**：`npx skills add baidu-search -g -y`

## Tier 3：全网接口猎取（周通动态发现）

### 国家企业信用信息公示系统
- **URL**：https://www.gsxt.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：中国境内企业工商信息验证

### 裁判文书网
- **URL**：https://wenshu.court.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：中国境内诉讼记录

### 信用中国
- **URL**：https://www.creditchina.gov.cn/
- **获取方式**：WebFetch抓取
- **覆盖**：失信被执行人、行政处罚

### OpenCorporates
- **URL**：https://opencorporates.com/
- **获取方式**：公开API / WebFetch
- **覆盖**：全球企业基本信息

### FRED (Federal Reserve Economic Data)
- **URL**：https://fred.stlouisfed.org/
- **获取方式**：公开API
- **覆盖**：美国宏观经济数据

### World Bank API
- **URL**：https://data.worldbank.org/
- **获取方式**：公开API
- **覆盖**：国际经济数据
