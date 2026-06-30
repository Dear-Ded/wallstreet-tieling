# 企业尽调 — 全量信息渠道补充目录 v7
Date: 2026-06-29
Type: Supplementary Research — Coverage Gap Fill

> **Notation**: This document catalogs publicly accessible information channels
> and legitimate commercial data services for enterprise due diligence research.
> Where applicable, free alternatives to paid services are listed.

---

## 一、商业数据聚合平台

### 1.1 天眼查 (Tianyancha)
- **性质**: 商业企业信息聚合平台，数据来自工商公示系统
- **可查字段**: 工商信息、股东、主要人员、对外投资、司法诉讼、行政处罚、经营异常、知识产权、招投标、债券信息、财务简报
- **访问方式**: 
  - 公开页面: `www.tianyancha.com/search?key=企业名称` — 基础信息可见
  - 高级搜索: 需要注册账号(免费注册)，每日有免费查询次数
  - 商业API: 需购买会员(按年/按查询量)
- **数据底层来源**: 国家企业信用信息公示系统 + 中国裁判文书网 + 中国执行信息公开网 + 信用中国 + CNIPA + 各省级市监局
- **接入思路**:
  - 公开页面信息采集: 使用标准HTTP客户端访问搜索页面 → 解析结果列表 → 提取企业ID → 访问详情页 → 解析结构化信息
  - 免费替代: 直接查询底层数据源(GSXT + 裁判文书网 + 执行信息网)，数据更新更及时，无查询次数商业限制
- **适合做**: fact (工商登记信息有官方数据源背书); lead (关联方推荐、风险评分是平台算法产出)

### 1.2 企查查 (Qichacha)
- **性质**: 与天眼查类似的企业信息聚合平台
- **可查字段**: 工商信息、股东、对外投资、司法风险、经营风险、知识产权、新闻舆情、财务报告
- **访问方式**: `www.qcc.com/search?key=企业名称`
- **接入思路**: 同天眼查。公开页面可获取基础工商 + 股东信息(非会员限制部分字段)
- **免费替代**: QYYJT API (已接入) + 直接查询底层官方数据源
- **适合做**: fact (工商登记数据); lead (关联关系推荐)

### 1.3 启信宝 / 企信宝
- **同质平台**，不单独展开。底层数据源相同，接入思路相同。

---

## 二、国际企业注册信息

### 2.1 Companies House (英国)
- **直接查询**: `find-and-update.company-information.service.gov.uk/search?q=公司名`
- **可查字段**: 注册号、注册日期、注册地址、董事/秘书、股东、财务报表(小型公司可免交)、抵押登记、清算信息
- **访问门**: 完全公开，免费，无需注册，无视觉验证
- **API**: `developer.company-information.service.gov.uk` — 免费REST API，注册即用
- **适合做**: fact (官方注册数据)

### 2.2 SEC EDGAR Full-Text (美国)
- **当前状态**: 项目中 `sec_edgar_public_api` 仅查询 `companyfacts` 摘要
- **扩展**: 查询完整 10-K/10-Q/8-K 申报文件全文
- **10-K 全文获取**: `https://www.sec.gov/cgi-bin/viewer?action=view&cik=CIK&accession_number=ACCESSION&xbrl_type=v` → 返回完整HTML/文本
- **可查字段**: 风险因素(Risk Factors)、法律诉讼(Legal Proceedings)、管理层讨论(MD&A)、关联交易(Related Party Transactions)、债务工具详情、收入分拆、地理市场分拆
- **适合做**: fact (经审计的财务数据); lead (管理层自述的风险因素)

### 2.3 OpenCorporates (全球)
- **API**: `api.opencorporates.com/v0.4/companies/search?q=公司名`
- **可查字段**: 公司名、注册地址、注册状态、董事/高管、行业分类、母公司/子公司
- **访问门**: 免费API (500次/月)，API Key免费注册获取
- **覆盖**: 140+ jurisdictions，最强在英国/美国/欧盟
- **适合做**: fact (官方注册数据)

### 2.4 香港公司注册处 (CR HK)
- **直接查询**: `www.icris.cr.gov.hk/csci/` → 网上查册中心
- **可查字段**: 公司名称、公司编号、公司类型、成立日期、公司现状、董事、股东、股本结构
- **访问门**: 需要注册账号，按次收费(约HKD 20/次)或购买年费计划
- **免费替代**: 部分商业聚合平台有香港公司基础信息(名称+编号+日期)

---

## 三、国际制裁与合规名单

### 3.1 已列表明细
| 名单 | URL | 格式 | 更新频率 |
|------|-----|------|---------|
| OFAC SDN (美国) | `sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ENHANCED.XML` | XML | 每日 |
| UN Security Council | `www.un.org/securitycouncil/content/un-sc-consolidated-list` | XML/PDF | 不定期 |
| EU Financial Sanctions | `webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList` | XML | 每日 |
| UK Sanctions List | `www.gov.uk/government/publications/the-uk-sanctions-list` | CSV/ODS | 不定期 |
| World Bank Listing | `www.worldbank.org/en/projects-operations/procurement/debarred-firms` | HTML/CSV | 每月 |
| Interpol Red Notices | `www.interpol.int/en/How-we-work/Notices/Red-Notices` | HTML | 实时 |

### 3.2 接入方法
- OFAC/UN/EU: 下载全量XML → 本地解析 → 实体名称模糊匹配
- 已在项目中列为 `DEFAULT_OFFICIAL_SOURCE_NAMES`

---

## 四、国际诉讼与法律记录

### 4.1 PACER (美国联邦法院)
- **直接查询**: `pcl.uscourts.gov` → 按当事人名称搜索
- **可查字段**: 案件编号、法院、立案日期、原告、被告、案件类型、法官、案件状态、案卷条目
- **访问门**: 需要注册PACER账号(免费注册)，按页收费($0.10/页，$3/文件封顶)，每季度$30以下免费
- **接入思路**:
  - 搜索当事人名称 → 获取案件列表 → 逐案下载案卷摘要
  - 可使用开源社区 pacer-tools 库(基于PACER的公开API)

### 4.2 UK Court Judgments
- **直接查询**: `www.judiciary.uk/judgments/` → 搜索判决
- **可查字段**: 案件名称、案号、判决日期、法官、判决全文
- **访问门**: 完全公开、免费、无视觉验证
- **适合做**: fact (已发布的法院判决)

### 4.3 EU Court of Justice (CURIA)
- **直接查询**: `curia.europa.eu` → 案件检索
- **可查字段**: 案件编号、当事人、判决日期、判决全文
- **访问门**: 完全公开、免费

---

## 五、行业监管与合规记录

### 5.1 FDA (美国食品药品监管)
- **查询**: `www.accessdata.fda.gov/scripts/cder/ob/` (药品) / `www.fda.gov/medical-devices` (医疗器械)
- **可查字段**: 批准文号、生产商、警告信(Warning Letters)、检查报告(483表格)、召回记录
- **访问门**: 完全公开、免费
- **适合做**: fact (监管批准/警告/召回)

### 5.2 EPA (美国环境保护署)
- **查询**: `echo.epa.gov` → 企业环保合规查询
- **可查字段**: 违规记录、罚款金额、合规状态、排放许可
- **访问门**: 完全公开、免费API

### 5.3 中国证监会处罚
- **查询**: `www.csrc.gov.cn/csrc/c100028/common_list.shtml` → 行政处罚决定
- **可查字段**: 处罚对象、违法事实、处罚依据、处罚结果
- **访问门**: 完全公开、无需登录

---

## 六、招聘与人才信息 (公开部分)

### 6.1 LinkedIn 公开档案
- **可查字段**: 员工人数、员工地区分布、招聘岗位、员工技能构成、员工流动趋势
- **访问方式**: 公开页面无需登录 → `www.linkedin.com/company/企业名/`
- **限制**: 未登录用户可看到部分页面内容；全量数据需登录
- **接入思路**: 公开页面采集 → 提取公司规模、行业、地址、招聘岗位数、员工地区分布

### 6.2 中国招聘平台公开信息
- **智联招聘企业页**: `company.zhaopin.com/` → 企业在招岗位、公司简介、公司规模
- **前程无忧企业页**: 企业招聘主页 → 岗位数量、薪资范围、公司介绍
- **BOSS直聘企业页**: `www.zhipin.com/gongsi/` → 企业信息+在招岗位
- **访问方式**: 公开页面可见，部分需要登录
- **适合做**: lead (招聘活跃度 → 业务扩张信号); lead (薪资范围 → 行业对比)

---

## 七、舆情与社媒公开信息

### 7.1 微信公众号公开文章
- **查询方式**: 搜狗微信搜索 `weixin.sogou.com` → 输入企业名称
- **可查字段**: 文章标题、发布日期、公众号名称、摘要
- **访问门**: 完全公开、免费
- **接入思路**: 搜狗微信搜索 → 提取结果列表 → 获取文章时间线 → 分析舆情趋势

### 7.2 微博公开内容
- **查询方式**: `s.weibo.com/weibo?q=企业名称` → 微博搜索
- **可查字段**: 博文内容、发布时间、转发/评论/点赞数
- **访问门**: 公开搜索无需登录

### 7.3 百度资讯 / 新闻搜索
- **查询方式**: `news.baidu.com/ns?word=企业名称`
- **可查字段**: 新闻标题、来源、发布日期、摘要
- **适合做**: lead (新闻舆情分析)

---

## 八、域名与网络技术信息

### 8.1 WHOIS 域名注册历史
- **查询方式**: `who.is` / `whois.domaintools.com`
- **可查字段**: 注册人(可能隐藏)、注册日期、到期日期、DNS服务器、注册商
- **扩展**: SSL证书透明度日志 → `crt.sh/?q=%.域名.com` → 发现所有子域名
- **适合做**: lead (域名注册人关联分析); lead (子域名 → 产品线/业务板块)

### 8.2 DNS 记录查询
- **查询方式**: `dnsdumpster.com` → 域名DNS信息
- **可查字段**: A记录(IP)、MX记录(邮件服务器)、TXT记录(SPF/DKIM配置)
- **适合做**: lead (邮件服务提供商 → 技术栈); lead (IP归属 → 服务器位置)

### 8.3 Shodan / Censys (互联网设备搜索引擎)
- **查询方式**: `shodan.io` → 搜索企业IP段或域名
- **可查字段**: 开放端口、服务版本、SSL证书、操作系统、地理位置
- **访问门**: Shodan免费账户有限制查询；Censys免费注册
- **适合做**: lead (暴露的服务 → 技术栈/安全意识评估)

---

## 九、地图与地理信息

### 9.1 百度地图 / 高德地图 公开POI
- **查询方式**: 地图搜索 → 输入企业名称
- **可查字段**: 地址坐标、联系电话、营业时间、用户评价、周边企业
- **访问门**: 公开页面
- **适合做**: lead (多个主体共享同一地址 → 关联关系线索); lead (实际经营地址与注册地址不一致 → 经营异常线索)

### 9.2 Google Maps
- **查询方式**: `maps.google.com` → 搜索企业名称
- **可查字段**: 地址、电话、网站、营业时间、用户评价、照片
- **适合做**: 同上

---

## 十、中国特有公开信息平台 (补充)

### 10.1 全国认证认可信息公共服务平台
- **查询**: `cx.cnca.cn` → 企业认证信息
- **可查字段**: ISO认证、CCC认证、有机认证、绿色食品认证等
- **访问门**: 完全公开、免费

### 10.2 全国矿业权人勘查开采信息公示系统
- **查询**: `kyqgs.mnr.gov.cn` → 矿业权信息
- **可查字段**: 矿业权类型、许可证号、有效期、开采矿种、生产规模
- **访问门**: 完全公开

### 10.3 全国房地产估价机构查询
- **查询**: `gjxydaxt.mnr.gov.cn` → 估价机构及估价师
- **访问门**: 完全公开

### 10.4 国家药品监督管理局数据库 (中国版FDA)
- **查询**: `www.nmpa.gov.cn/datasearch/` → 药品/医疗器械/化妆品
- **可查字段**: 批准文号、生产单位、产品名称、有效期
- **访问门**: 完全公开、免费

### 10.5 生态环境部排污许可证公开端
- **查询**: `permit.mee.gov.cn` → 排污许可证查询
- **可查字段**: 排污单位、许可证编号、主要污染物、排放标准、有效期
- **访问门**: 完全公开

---

## 十一、商业数据库与付费替代方案

### 11.1 Bloomberg Terminal
- **可查字段**: 公司财务、债券、股票、供应链、ESG、新闻、分析师报告
- **访问**: 需购买Bloomberg终端(年费约$24,000)
- **免费替代**: SEC EDGAR (美国上市公司) + 巨潮资讯 (中国上市公司) + Yahoo Finance (基础数据) + Google Finance

### 11.2 Refinitiv Eikon / World-Check
- **可查字段**: 制裁名单、负面新闻、政治敏感人物(PEP)、关联企业
- **访问**: 商业订阅
- **免费替代**: OFAC/UN/EU公开制裁名单 + 公开新闻搜索 + 谷歌/Bing搜索

### 11.3 Dun & Bradstreet (D&B)
- **可查字段**: 企业信用评分、付款历史、企业族谱
- **访问**: 商业订阅
- **免费替代**: GSXT (中国) + Companies House (英国) + OpenCorporates (全球)

### 11.4 Moody's / S&P / Fitch 评级报告
- **可查字段**: 企业信用评级、行业展望、评级方法论
- **访问**: 商业订阅(部分发行人公开页面有摘要)
- **免费替代**: 中国债券信息网 (中国发债企业评级) + 中国货币网 (评级报告PDF公开下载)

---

## 十二、开源情报 (OSINT) 工具链

### 12.1 SpiderFoot
- **GitHub**: `github.com/smicallef/spiderfoot` (12k+ stars)
- **功能**: 自动查询 200+ 公开数据源，包括 SHODAN、HaveIBeenPwned、WHOIS、SSL证书、社交媒体验证等
- **访问门**: 开源免费，本地部署
- **在本项目中**: 作为多源自适应前端，统一调度200+个模块的查询任务

### 12.2 theHarvester
- **GitHub**: `github.com/laramies/theHarvester` (11k+ stars)
- **功能**: 从搜索引擎、SHODAN、PGP key server等收集子域名、邮件地址、员工姓名
- **接入**: Python库，可直接import

### 12.3 Sherlock
- **GitHub**: `github.com/sherlock-project/sherlock` (59k+ stars)
- **功能**: 跨400+社交平台搜索指定用户名是否存在
- **在本项目中**: 用于验证高管/创始人社交媒体存在性，构建数字足迹图谱

### 12.4 Holehe
- **GitHub**: `github.com/megadose/holehe` (7k+ stars)
- **功能**: 验证邮箱是否注册了各种在线服务
- **在本项目中**: 用于关联方身份验证(同一邮箱 → 多个平台账号 → 关联证据)

### 12.5 Photon
- **GitHub**: `github.com/s0md3v/Photon` (11k+ stars)
- **功能**: 从目标网站提取URL、邮件、社交媒体账号、文件
- **在本项目中**: 用于企业官网深度扫描，提取公开的联系信息和技术栈线索

### 12.6 bbot
- **GitHub**: `github.com/blacklanternsecurity/bbot` (6k+ stars)
- **功能**: 递归子域名发现、网络扫描、网页采集
- **在本项目中**: 用于企业数字资产发现(子域名 → 产品线 → 关联公司)

---

## 十三、中文开源情报工具

### 13.1 TideSec/TSearch
- **GitHub**: `github.com/TideSec/TscanPlus` (1k+ stars)
- **功能**: 中国企业信息多源聚合查询
- **数据源**: 天眼查/企查查/启信宝公开数据聚合

### 13.2 ENScanGo
- **GitHub**: `github.com/wgpsec/ENScanGo` (3k+ stars)
- **功能**: 中国企业信息查询工具，支持天眼查/企查查/爱企查/ICP备案
- **接入**: Go语言CLI工具，可生成JSON输出

### 13.3 ICP备案查询
- **直接查询**: `beian.miit.gov.cn` → ICP/IP地址/域名信息备案管理系统
- **可查字段**: 备案号、主办单位名称、网站域名、网站名称、审核日期
- **访问门**: 需要输入视觉验证 + 部分需要短信验证
- **免费替代**: `icp.chinaz.com` 等第三方备案查询站(公开聚合，无需验证)
- **在本项目中**: 企业域名 → ICP备案 → 确认网站归属 → 关联方(同一备案主体下的多个域名)

---

## 十四、总览：信息渠道核验矩阵

| 类别 | 已覆盖(v1-v6) | 本v7补充 | 免费/公开 | 需商业订阅 |
|------|------------|--------|---------|----------|
| 中国工商 | GSXT | 天眼查/企查查聚合 | ✅ 直接底层 | ✅ 商业API |
| 中国司法 | 裁判文书网/执行信息网 | — | ✅ | — |
| 中国行政处罚 | 信用中国 | 各省级平台 | ✅ | — |
| 中国债券 | 中国债券信息网/货币网 | — | ✅ | — |
| 中国上市公司 | 巨潮资讯 | — | ✅ | — |
| 中国知识产权 | CNIPA | WIPO/GPatents替代 | ✅ | — |
| 中国海关 | 海关企业信用 | — | ✅ | — |
| 中国采购 | 中国政府采购网 | — | ✅ | — |
| 中国舆情 | — | 微博/微信/百度新闻 | ✅ | — |
| 中国招聘 | — | 智联/前程无忧/BOSS | ✅(部分) | — |
| 中国认证 | — | CNCA认证平台 | ✅ | — |
| 中国环保 | — | 排污许可证平台 | ✅ | — |
| 中国药品 | — | NMPA数据库 | ✅ | — |
| 中国矿业 | — | 矿业权公示 | ✅ | — |
| 中国ICP | — | ICP备案查询 | ✅ | — |
| 地图/地址 | — | 百度/高德/Google Maps | ✅ | — |
| 域名/网络 | — | WHOIS/crt.sh/Shodan | ✅ | ✅ Shodan |
| 国际注册 | SEC/CompaniesHouse | OpenCorporates/香港CR | ✅ | ✅ 香港CR |
| 国际制裁 | OFAC/UN | EU/UK/WorldBank/Interpol | ✅ | — |
| 国际诉讼 | — | PACER/UK Judgments/EU CURIA | ✅ PACER$ | — |
| 国际监管 | — | FDA/EPA/中国CSRC | ✅ | — |
| 商业评级 | — | Moody's/S&P/Fitch | — | ✅ |
| 商业数据 | QYYJT | Bloomberg/D&B/Refinitiv | — | ✅ |
| OSINT工具 | ddddocr/stealth | SpiderFoot/Harvester/Sherlock/Holehe/Photon/bbot | ✅ | — |
| 中国OSINT | — | TScanPlus/ENScanGo | ✅ | — |
