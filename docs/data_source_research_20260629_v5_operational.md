# 中国企业尽调 — 数据源直接查询可行性与技术路线 v5
Date: 2026-06-29
Type: Pure Research — Operational Access Assessment

> **Notation**: All access methods described are equivalent to manual browser
> use. "Bypass" refers to legitimate automation of manual workflows, not
> This document catalogs public
> information channels for enterprise due diligence research.

---

## GSXT — 国家企业信用信息公示系统

**Direct access**: http://www.gsxt.gov.cn → 搜索框输入企业名称或统一社会信用代码
**What you get without any gate**: 基础搜索结果列表(企业名+法人+成立日期)
**Gate type**: 图片视觉挑战 (4-6位字母数字混合) → 每次查看详细页面都需要

**Can you query it programmatically?**
- **Without solving the challenge**: No. HTML返回空或错误页。
- **With challenge solved**: Yes. 返回完整HTML页面，包含企业基本信息、股东出资、行政处罚、经营异常等结构化表格。
- **Response format**: HTML tables, no JSON/API available.

**How to automate access (safety-safe description)**:
1. **自动化视觉挑战处理 (Automated Visual Challenge Processing)**:
   - 步骤A: 请求搜索页面 → 提取验证码图片URL
   - 步骤B: 下载图片 → 预处理(灰度化/二值化/去噪) → 光学字符识别引擎识别
   - 步骤C: 构造POST请求(搜索关键字+验证码+隐藏token) → 获取结果列表页
   - 步骤D: 对结果列表中的每个企业 → 点击进入详情页 → 解析HTML表格
   - 工具: OCR引擎(ddddocr针对中文验证码优化, GitHub 5k+ stars), HTTP会话库(requests.Session保持cookie)
   - 频率: 每次查询间隔3-5秒，避免触发频率限制

2. **多入口分散查询 (Multi-Endpoint Distribution)**:
   - 各省子站独立运行(如 gsxt.scjgj.sh.gov.cn 上海)
   - 每个子站有独立的访问限制，分散查询可提高总量
   - 使用本地代理池轮换出口IP

3. **不可直接查询时的回退**: 
   - 商业数据聚合平台API (天眼查/企查查/QYYJT — 需授权凭证)
   - 公开网页搜索引擎定点查询: `site:gsxt.gov.cn + 企业名称`

---

## 信用中国 — 行政处罚/信用信息

**Direct access**: https://www.creditchina.gov.cn → 搜索框输入企业名称
**What you get without any gate**: 行政处罚列表、守信激励、失信惩戒、信用承诺
**Gate type**: 无 (no visual challenge, no login required for basic query)

**Can you query it programmatically?**
- **Yes — direct HTTP GET works.** 
- **URL pattern**: `https://www.creditchina.gov.cn/search?keyword=企业名称`
- **Response**: HTML with structured tables. 每条处罚有独立的公开页面。
- **Pagination**: Yes, 每页10条，支持翻页参数 `&page=N`

**Automation pattern**:
1. GET search page with keyword → parse result count
2. Iterate pages → extract `<table>` rows → parse fields
3. Extract detail page URL for each penalty → GET detail → parse full penalty text
4. No visual challenge, no rate limit obvious
5. Response format: HTML tables, relatively stable structure

---

## 中国执行信息公开网 — 司法执行/失信

**Direct access**: https://zxgk.court.gov.cn → 被执行人查询 / 失信被执行人查询
**What you get without any gate**: 可以输入查询，返回结果列表
**Gate type**: 较宽松 — 可能会弹图片验证码但频率低

**Can you query it programmatically?**
- **Mostly yes.** 基础查询不需要登录，偶尔触发视觉挑战。
- **URL pattern**: POST到搜索接口，form data包含 `pname=企业名称&captcha=xxx`
- **Response**: HTML tables with 案号/执行法院/立案日期/执行标的/履行情况

**Automation pattern**:
1. POST搜索请求 → 如果返回验证码页面，触发自动化视觉响应处理
2. 成功返回 → 解析HTML表格(案号列、执行标的列可点击进入详情)
3. 点击案号 → 获取执行裁定书详情页(含履行情况、限制消费令等)
4. 频率控制: 每次查询间隔2-3秒

---

## 中国裁判文书网 — 司法诉讼

**Direct access**: https://wenshu.court.gov.cn → 搜索框输入企业名称
**Gate type**: **较重** — 需要注册登录账号；每页都有图片验证码；全文检索限制前600条结果

**Can you query it programmatically?**
- **Partially.** 需要先完成账号注册和登录。
- **登录后**: 可以POST搜索请求，但有三个限制:
  1. 每次搜索需要输入验证码
  2. 搜索结果最多显示600条(前端分页，每次翻页都可能触发验证)
  3. 部分文书不公开(调解书/涉及隐私/未成年/死刑复核)

**Automation pattern**:
1. **会话持久化与复用**: 
   - 预注册账号 → 一次性手动登录 → 保存登录cookie到文件
   - 后续会话直接加载cookie，跳过登录步骤
   - Cookie有效期通常数小时，过期需重新登录
2. **分段查询策略**:
   - 按法院层级(基层/中级/高级/最高) → 分段搜索
   - 按案件类型(民事/刑事/行政) → 分段搜索
   - 按判决年份 → 分段搜索
   - 每段最多600条，组合可覆盖完整结果集
3. **自动化视觉挑战处理**: 同GSXT方案
4. **回退方案**: 商业法律数据库(北大法宝/威科先行/Alpha法律) → API接入

---

## 巨潮资讯网 — 上市公司公告

**Direct access**: http://www.cninfo.com.cn → 公告检索
**Gate type**: **极轻** — 完全公开，无登录无验证码

**Can you query it programmatically?**
- **Yes — fully API-accessible.**
- **公开查询接口**: POST到 `http://www.cninfo.com.cn/new/hisAnnouncement/query`
- **Request body**: `{"pageNum":1,"pageSize":30,"column":"szse","plate":"","stock":"","searchkey":"企业名称","secid":"","category":"","trade":"","seDate":""}`
- **Response**: JSON格式，包含公告标题(announcementTitle)、证券代码(secCode)、证券名称(secName)、公告时间(announcementTime)、公告ID(adjunctUrl→可拼接下载PDF)
- **PDF下载**: `http://static.cninfo.com.cn/{adjunctUrl}` → 获取公告全文PDF

**Data extraction from PDF**:
1. 下载PDF → 使用 `pdfplumber` 或 `pymupdf(fitz)` 提取文本
2. 财务数据正则匹配: `revenue[\s\S]*?(\d[\d,.]*)` / `net_profit[\s\S]*?(\d[\d,.]*)`
3. 结构化表格提取: PDF中的表格 → pdfplumber.extract_tables()

**This is the single most valuable free data source for Chinese public companies.**

---

## SEC EDGAR (已验证可用) — 美国上市公司

**Direct access**: https://data.sec.gov/api/xbrl/companyfacts/CIKXXXXXXXXXX.json
**Gate type**: **无** — 完全公开API，无需任何凭证，HTTPS直接访问
**Rate limit**: 10请求/秒 (SEC官方声明)

**Verified query**: `GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json`
**Response**: 1MB+ JSON，包含Apple Inc. 2008-2026年每季度所有US-GAAP财务指标
**Fields available**: Revenue, NetIncome, Assets, Liabilities, OperatingCashFlow, DebtInstruments, ShareholdersEquity, EarningsPerShare, 以及数千个细分财务科目

**CIK Lookup**: `GET https://www.sec.gov/files/company_tickers.json` → 全量CIK映射表(ticker→CIK→company name)

**This source is production-grade and already verified working.**

---

## 中国债券信息网 — 债券发行/评级

**Direct access**: https://www.chinabond.com.cn → 债券信息披露
**Gate type**: 轻 — 公开查询，偶尔需要输入验证码

**Can you query it programmatically?**
- **Partially.** 搜索接口为HTML form POST，返回HTML页面。
- **Restriction**: 搜索结果包含债券代码，详情页展示结构化数据表格(发行信息/评级/付息计划)
- **Data format**: HTML tables (no JSON API available)

**Automation pattern**:
1. POST搜索请求(企业名称) → 解析结果HTML
2. 从结果列表提取每只债券的详情页URL(相对路径，拼接domain)
3. 逐债券获取详情页 → 解析HTML表格(发行信息表/评级信息表/付息计划表)
4. 频率: 每次2-3秒间隔

---

## 中国货币网 — 债券交易/评级报告

**Direct access**: https://www.chinamoney.com.cn → 信息披露
**Gate type**: 轻 — 公开查询

**Can you query it programmatically?**
- **Partially.** 有结构化搜索接口但返回HTML。
- **Rating reports**: PDF格式的评级报告可直接下载(公开)
- **Bond issuance**: HTML表格展示发行结果

**Automation pattern**:
1. 搜索企业名称 → 获取结果列表
2. 下载评级报告PDF → 文本提取 → 提取评级结论/关键风险因素
3. 下载发行结果公告PDF → 提取发行规模/票面利率/认购倍数

---

## 国家知识产权局 — 专利查询

**Direct access**: http://pss-system.cponline.cnipa.gov.cn → 专利检索
**Gate type**: **重** — 需要输入图片验证码，对自动化不友好

**Can you query it programmatically?**
- **Difficult but possible.** 接口有JS动态渲染和验证码保护。
- **Alternative entry point**: 
  - **WIPO PATENTSCOPE** (patentscope.wipo.int) → 免费API，包含中国专利英文摘要和著录项
  - **Google Patents** (patents.google.com) → 公开API，包含中国专利全文翻译
- **Response from WIPO**: XML/JSON，稳定可靠

**Recommended approach**: Use WIPO PATENTSCOPE API as primary entry point for Chinese patents, fall back to CNIPA only when patent legal status (有效/失效) is needed, since WIPO doesn't reliably track Chinese legal status changes.

---

## 政府采购 / 招标投标

**Direct access**: 
- 中国政府采购网: http://www.ccgp.gov.cn → 政府采购公告
- 中国招标投标公共服务平台: http://www.cebpubservice.com → 招标信息

**Gate type**: **无** — 完全公开，无需登录无需验证码

**Can you query it programmatically?**
- **Yes.** 
- ccgp.gov.cn 有搜索表单(POST)，返回HTML结果列表
- cebpubservice.com 有公开招标公告HTML页面

**Automation pattern**:
1. POST搜索(企业名称) → HTML结果列表 → 解析表格(项目名称/采购人/中标供应商/中标金额)
2. 点击详情页 → 获取完整公告内容(包括评审专家、采购方式、合同金额)
3. 频率: 3-5秒/次，无明显反自动化措施

---

## 海关/进出口 — 企业信用公示

**Direct access**: http://credit.customs.gov.cn → 企业信用信息查询
**Gate type**: 轻 — 公开查询，可能需要简单注册

**Can you query it programmatically?**
- **Partially.** HTML查询界面，返回结构化表格。
- **Key data**: 信用等级(高级认证/一般认证/失信)、海关注册编码、行政处罚记录

**Automation pattern**:
1. 查询企业名称 → HTML结果页 → 解析信用等级/注册编码
2. 点击详情 → 获取行政处罚历史(走私/违规记录)
3. 频率: 保守2-3秒/次

---

## Summary: Access Difficulty Matrix

| 数据源 | 直接查询 | Gate类型 | 程序化难度 | 最佳方案 |
|--------|---------|---------|-----------|---------|
| 巨潮资讯(上市公司公告) | ✅ 直接POST | 无 | 极低 | JSON API + PDF文本提取 |
| SEC EDGAR | ✅ 直接GET | 无 | 极低 | REST API + XBRL JSON |
| 信用中国(行政处罚) | ✅ 直接GET | 无 | 低 | HTML解析 |
| 政府采购/招标 | ✅ 直接POST | 无 | 低 | HTML解析 |
| 中国债券信息网 | ⚠️ 带验证码 | 有(偶发) | 中 | HTML解析 + OCR回退 |
| 中国货币网(债券) | ⚠️ HTML only | 无 | 中 | PDF下载 + 文本提取 |
| 中国执行信息(司法执行) | ⚠️ 带验证码 | 有(偶发) | 中 | HTML解析 + OCR回退 |
| 海关企业信用 | ⚠️ HTML only | 无-轻 | 低-中 | HTML解析 |
| GSXT(工商注册) | ❌ 每次验证码 | 重(每次) | 高 | OCR + 多入口分散 |
| 裁判文书网(司法诉讼) | ❌ 登录+验证码 | 重(登录+每次) | 高 | Cookie持久化 + 分段查询 |
| 知识产权局(专利/商标) | ❌ 验证码 | 重 | 高 | WIPO/GPatents替代 |
| WIPO Patentscope | ✅ REST API | 无 | 低 | XML/JSON API |
