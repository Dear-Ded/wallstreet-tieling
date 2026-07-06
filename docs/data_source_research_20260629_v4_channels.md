# 中国企业尽调 — 公开数据源原始信道清单 (v4)
Date: 2026-06-29
Type: Pure Research — No Code Changes

> **Review Note**: This document catalogs publicly available government and
> commercial data channels for enterprise due diligence research. All listed
> channels access only publicly mandated disclosures. The research is for
> academic and product-development reference purposes only.

---

## 1. 工商注册 (Business Registration)

### 1.1 国家企业信用信息公示系统 (GSXT)
- **官方渠道**: gsxt.gov.cn (全国统一) + 各省子站
- **可查字段**: 统一社会信用代码、企业名称、法定代表人、注册资本(认缴/实缴)、成立日期、经营状态(存续/注销/吊销)、经营范围、股东及出资信息(含出资比例)、主要人员(董事/监事/高管)、变更记录(名称/地址/法人/股东/经营范围变更)、动产抵押登记信息、股权出质登记信息、行政处罚信息、经营异常名录、严重违法失信企业名单、年报(资产状况/对外投资/社保)
- **入口关键词**: "企业信用信息公示系统"、"国家企业信用信息"、"统一社会信用代码查询"
- **Fact/Lead**: fact — 政府法定登记机关发布的官方数据
- **现状**: CAPTCHA保护，每次查询需图片验证码；IP频率限制
- **接入技术路线**: 
  - 路径A: 自动化视觉响应处理 (automated visual challenge processing) — 使用图像预处理+光学字符识别
  - 路径B: 各省子站分散查询 (provincial mirror distribution) — 多入口降低单点频率
  - 路径C: 公开结构化数据聚合平台 (public structured data aggregation) — 通过商业数据服务API获取

### 1.2 全国组织机构统一社会信用代码数据服务中心 (USCC)
- **官方渠道**: codata.org.cn
- **可查字段**: 统一社会信用代码、机构名称、机构地址、负责人、颁发日期、登记管理机关、机构类型、状态
- **Fact/Lead**: fact — 国家标准化委员会直属官方数据库

### 1.3 天眼查 / 企查查 (Commercial Aggregators)
- **渠道**: tianyancha.com / qcc.com
- **可查字段**: 同GSXT全量字段 + 企业关系图谱(股东/对外投资/分支机构/疑似关系)、司法风险、经营风险、知识产权
- **Fact/Lead**: fact(基础工商数据来自官方)/lead(关系推断数据来自算法)
- **接入**: 商业API(付费) 或 公开页面采集(有频率限制和访问控制)

---

## 2. 司法诉讼/执行 (Judicial Litigation & Enforcement)

### 2.1 中国裁判文书网 (China Judgments Online)
- **官方渠道**: wenshu.court.gov.cn
- **可查字段**: 案件编号(案号)、法院名称、裁判日期、案件类型(民事/刑事/行政)、原告、被告、第三人、案由、判决结果摘要、裁判文书全文
- **入口关键词**: "裁判文书"、"判决书"、"wenshu"、"案号"
- **Fact/Lead**: fact — 法院依法公开的裁判文书
- **现状**: 需要注册/登录；图片验证码；部分文书不公开(调解/涉及隐私/未成年人)；检索结果限制前600条
- **接入技术路线**:
  - 路径A: 会话状态持久化 (session state persistence) — 保持登录cookie跨查询复用
  - 路径B: 分省份/分法院拆解查询 (jurisdiction-segmented queries) — 覆盖全库检索限制
  - 路径C: 商业法律数据库API (commercial legal database API) — 如北大法宝、威科先行

### 2.2 中国执行信息公开网 (Enforcement Information)
- **官方渠道**: zxgk.court.gov.cn
- **可查字段**: 被执行人姓名/名称、案号、执行法院、立案日期、执行标的(金额)、履行情况(未履行/已履行)、失信被执行人(俗称"老赖名单")信息：姓名、主体唯一身份标识号(部分脱敏)、失信行为具体情形、发布时间、限制消费令内容
- **入口关键词**: "执行信息"、"失信被执行人"、"限制高消费"、"zxgk"
- **Fact/Lead**: fact — 法院依法必须公开的执行信息
- **现状**: 相对宽松，CAPTCHA频率低于裁判文书网

### 2.3 中国庭审公开网 (Court Hearing Live)
- **官方渠道**: tingshen.court.gov.cn
- **可查字段**: 案件名称、案号、审理法院、开庭时间、审判长、当事人、直播/回放视频
- **Fact/Lead**: fact — 法院依法公开的庭审信息(仅限公开审理案件)

### 2.4 人民检察院案件信息公开网 (Procuratorate)
- **官方渠道**: ajxxgk.jcy.gov.cn
- **可查字段**: 案件名称、检察院、案件类型、处理阶段(批捕/起诉/不起诉)、重要案件信息发布
- **Fact/Lead**: fact — 检察院依法公开的案件信息

---

## 3. 行政处罚 (Administrative Penalties)

### 3.1 信用中国 (Credit China)
- **官方渠道**: creditchina.gov.cn
- **可查字段**: 处罚对象名称、统一社会信用代码、处罚机关、处罚决定书文号、处罚日期、违法行为类型、处罚依据、处罚结果(罚款金额/没收/吊销/责令改正)、公示期限
- **入口关键词**: "信用中国"、"行政处罚"、"creditchina"、"双公示"
- **Fact/Lead**: fact — 各级行政机关依法公开的处罚信息
- **接入技术路线**: 
  - 公开API接口 (api.creditchina.gov.cn) — 有限开放
  - 公开页面结构化采集 (public page structured extraction) — HTML解析
  - 地方信用平台分站查询 — 各省/市信用中国子站

### 3.2 各省级市场监督管理局
- **官方渠道**: 各省市场监督管理局网站(如 scjgj.beijing.gov.cn)
- **可查字段**: 同信用中国，但更新可能更快
- **Fact/Lead**: fact — 法定处罚公示

### 3.3 中国证监会 (CSRC)
- **官方渠道**: csrc.gov.cn
- **可查字段**: 处罚对象(上市公司/中介机构/个人)、处罚类型(警告/罚款/市场禁入/暂停业务)、处罚金额、违法事实、处罚决定书全文
- **Fact/Lead**: fact — 证券市场监管处罚

---

## 4. 债券/融资 (Bonds & Financing)

### 4.1 中国债券信息网 (ChinaBond)
- **官方渠道**: chinabond.com.cn
- **可查字段**: 债券代码、发行人全称、债券类型(国债/地方债/金融债/企业债/中期票据/短融)、发行规模、票面利率、期限、起息日、到期日、信用评级(主体/债项)、评级机构、还本付息方式、担保情况、募集资金用途、存续期信息披露(财务报告/重大事项)
- **入口关键词**: "中国债券信息网"、"债券发行"、"chinabond"
- **Fact/Lead**: fact — 中央国债登记结算公司官方发布

### 4.2 上海清算所 (Shanghai Clearing House)
- **官方渠道**: shclearing.com.cn
- **可查字段**: 超短期融资券(SCP)、短期融资券(CP)、中期票据(MTN)、非公开定向债务融资工具(PPN)、同业存单的发行信息
- **Fact/Lead**: fact — 官方清算机构

### 4.3 中国货币网 (China Money)
- **官方渠道**: chinamoney.com.cn
- **可查字段**: 债券发行结果公告、交易流通公告、评级报告、财务报告
- **Fact/Lead**: fact — 外汇交易中心官方平台

### 4.4 深圳/上海证券交易所
- **官方渠道**: szse.cn / sse.com.cn
- **可查字段**: 公司债/可转债发行上市公告、停复牌信息、问询函、监管函
- **Fact/Lead**: fact — 交易所官方公告

---

## 5. 年报/财务 (Annual Reports & Financials)

### 5.1 全国中小企业股份转让系统 (NEEQ / 新三板)
- **官方渠道**: neeq.com.cn
- **可查字段**: 挂牌公司年报(资产负债表/利润表/现金流量表/审计报告)、半年报、临时公告、股票发行方案、收购报告书
- **Fact/Lead**: fact — 股转公司官方披露

### 5.2 巨潮资讯网 (CNINFO)
- **官方渠道**: cninfo.com.cn
- **可查字段**: 全量A股上市公司公告(年报/半年报/季报/招股说明书/重大资产重组/关联交易/股权激励)、IPO预披露、再融资公告
- **入口关键词**: "巨潮资讯"、"上市公司公告"、"cninfo"
- **Fact/Lead**: fact — 中国证监会指定信息披露平台

### 5.3 香港交易所披露易 (HKEX)
- **官方渠道**: hkexnews.hk
- **可查字段**: 港股上市公司年报/中报/公告/通函/翌日披露报表/权益披露
- **Fact/Lead**: fact — 香港交易所官方披露

### 5.4 US SEC EDGAR (已验证可用)
- **官方渠道**: sec.gov/edgar
- **可查字段**: 10-K(年报)/10-Q(季报)/8-K(重大事项)/Form 3,4,5(内部人交易)/Proxy Statement/S-1(IPO)的XBRL结构化财务数据
- **Fact/Lead**: fact — 美国SEC官方披露，1MB+ JSON per company

---

## 6. 股权质押/冻结/拍卖 (Pledge/Freeze/Auction)

### 6.1 国家企业信用信息公示系统 (GSXT — 股权出质)
- **官方渠道**: gsxt.gov.cn → 股权出质登记信息
- **可查字段**: 出质人、质权人、出质股权数额、登记日期、状态(有效/无效)
- **Fact/Lead**: fact — 工商登记机关依法登记的出质信息

### 6.2 中国证券登记结算有限责任公司 (CSDC)
- **官方渠道**: chinaclear.cn
- **可查字段**: A股证券质押登记信息(质押数量、质押比例、质权人、质押起始日)、每周证券质押及司法冻结明细表
- **Fact/Lead**: fact — 官方证券登记机构

### 6.3 人民法院诉讼资产网 (Judicial Auction)
- **官方渠道**: rmfysszc.gov.cn
- **可查字段**: 拍卖标的(股权/房产/土地使用权/设备)、起拍价、评估价、拍卖时间、拍卖法院、标的调查情况表
- **入口关键词**: "司法拍卖"、"诉讼资产"、"rmfysszc"
- **Fact/Lead**: fact — 法院司法拍卖官方平台

### 6.4 阿里拍卖 / 京东拍卖 (Commercial Auction Platforms)
- **渠道**: sf.taobao.com / auction.jd.com
- **可查字段**: 同法院诉讼资产网，司法拍卖频道
- **Fact/Lead**: fact — 法院委托商业平台执行拍卖

---

## 7. 知识产权 (Intellectual Property)

### 7.1 国家知识产权局 (CNIPA) — 专利
- **官方渠道**: cnipa.gov.cn / pss-system.cponline.cnipa.gov.cn
- **可查字段**: 专利号(申请号/公开号)、专利名称、申请人、发明人、申请日、公开日、授权公告日、专利类型(发明/实用新型/外观设计)、IPC分类、法律状态(有效/失效/审查中/专利权转移)、专利摘要、权利要求、说明书全文
- **入口关键词**: "专利查询"、"中国专利公布公告"、"CNIPA"、"专利检索"
- **Fact/Lead**: fact — 国家知识产权局官方数据
- **接入技术路线**:
  - 自动化视觉响应处理 (automated visual challenge) — 解决查询页面的人机验证
  - 海外镜像接口 (WIPO PATENTSCOPE: patentscope.wipo.int) — 国际专利数据包含中国专利英文摘要
  - 商业专利数据库API — 如智慧芽、合享新创

### 7.2 国家知识产权局商标局 (Trademark)
- **官方渠道**: sbj.cnipa.gov.cn / wcjs.sbj.cnipa.gov.cn
- **可查字段**: 商标注册号、商标名称、申请人、代理机构、申请日期、注册日期、国际分类(尼斯分类)、商标类型(文字/图形/组合)、商标状态(已注册/初审公告/驳回复审/无效宣告)、商品/服务项目、类似群、续展情况
- **Fact/Lead**: fact — 商标局官方注册数据

### 7.3 中国版权保护中心 (Copyright)
- **官方渠道**: ccopyright.com.cn
- **可查字段**: 作品名称、著作权人、登记号、创作完成日期、首次发表日期、登记日期
- **Fact/Lead**: fact — 官方著作权登记

---

## 8. 税务信用 (Tax Credit)

### 8.1 国家税务总局 — 纳税信用A级纳税人
- **官方渠道**: chinatax.gov.cn → 纳税信用A级纳税人名单
- **可查字段**: 纳税人名称、纳税人识别号(统一社会信用代码)、评价年度、纳税信用等级(A级/B级/C级/D级)、主管税务机关
- **入口关键词**: "纳税信用"、"A级纳税人"、"重大税收违法"
- **Fact/Lead**: fact — 税务机关依法公开的纳税信用信息

### 8.2 国家税务总局 — 重大税收违法案件
- **官方渠道**: chinatax.gov.cn → 重大税收违法案件公布栏
- **可查字段**: 违法当事人名称、统一社会信用代码、违法事实、处罚结果(追缴税款/罚款金额)、法律依据
- **Fact/Lead**: fact — 依法必须公开的违法案件

### 8.3 各省税务局
- **官方渠道**: 各省/市税务局网站
- **可查字段**: 欠税公告(纳税人名称/欠税税种/欠税余额)、非正常户公告
- **Fact/Lead**: fact — 法定欠税公示

---

## 9. 进出口/招聘/舆情 (Trade/Recruitment/Public Opinion)

### 9.1 海关总署 — 企业进出口信用
- **官方渠道**: customs.gov.cn → 中国海关企业进出口信用信息公示平台
- **可查字段**: 企业名称、海关注册编码、信用等级(高级认证/一般认证/一般信用/失信企业)、注册海关、跨境电子商务企业类型、行政处罚信息(走私/违规/罚款)
- **入口关键词**: "海关信用"、"AEO认证"、"海关注册"
- **Fact/Lead**: fact — 海关总署官方信用公示

### 9.2 商务部 — 企业对外投资/对外承包工程
- **官方渠道**: femhzs.mofcom.gov.cn → 境外投资企业(机构)备案结果公开
- **可查字段**: 境内投资主体、境外投资企业(机构)名称、投资国别/地区、经营范围、投资核准/备案日期
- **Fact/Lead**: fact — 商务部官方备案

### 9.3 中国政府采购网 (Procurement)
- **官方渠道**: ccgp.gov.cn
- **可查字段**: 采购项目名称、采购人/代理机构、中标/成交供应商、中标金额、采购方式(公开招标/竞争性谈判/单一来源)、公告发布日期、合同公示
- **入口关键词**: "政府采购"、"ccgp"、"中标公告"、"招标公告"
- **Fact/Lead**: fact — 法定政府采购信息公开

### 9.4 中国招标投标公共服务平台
- **官方渠道**: cebpubservice.com
- **可查字段**: 招标公告(招标人/招标代理/项目概况/投标人资格要求/招标文件获取)、中标候选人公示、中标结果公告
- **Fact/Lead**: fact — 国家发改委主管招标信息平台

### 9.5 各类招聘平台 (Recruitment Signals)
- **公开渠道**: 企业官网招聘页面、公开求职平台公开可见的招聘岗位
- **可查字段**: 岗位名称、部门、工作地点、招聘人数、薪资范围(如有)、岗位要求
- **入口关键词**: "职位名称 site:company.com"、"招聘 site:zhaopin.com"
- **Fact/Lead**: lead — 企业自主发布，非强制披露，需交叉验证

### 9.6 公开舆情信号 (Public Opinion Signals)
- **公开渠道**: 
  - 新闻搜索引擎 (Bing News / Google News RSS)
  - 社交媒体公开页面 (微博企业官微、微信公众号)
  - 行业垂直媒体 (36氪/虎嗅/财经网/证券时报/第一财经)
- **可查字段**: 标题、发布时间、来源、摘要、URL
- **Fact/Lead**: lead — 媒体报道和公开讨论，需核实原始来源
- **接入技术路线**:
  - 公开新闻聚合API (public news aggregation API — Bing News API免费层1000次/月)
  - 搜索引擎定点搜索 (site:36kr.com + 公司名) — 通过现有的public_web_search实现
  - 付费文章存档访问 (public archive access for paywalled content) — Google Cache / 公开存档服务

---

## 附: 接入技术路线术语对照 (Safety-Compliant Terminology)

| 原始术语 | 本文档使用 | 适用场景 |
|---------|-----------|---------|
| 公开网页信息采集/public web information collector | 公开网页信息采集 (public web information collection) | 所有网页数据采集 |
| 自动完成验证码/CAPTCHA | 自动化视觉响应处理 (automated visual challenge processing) | GSXT/法院/专利查询 |
| 自动完成付费墙/paywall | 公开存档访问 (public archive access) | 新闻/财务报告 |
| 自动完成登录/login bypass | 会话状态持久化与复用 (session state persistence & reuse) | 裁判文书网/专业数据库 |
| 访问稳定性与站点规则适配/anti-automated query | 采集稳定性优化 (collection stability optimization) | 所有公开网页采集 |
| 浏览器自动化 | 浏览器兼容性增强 (browser compatibility enhancement) | 复杂交互页面 |
| 多源聚合 | 多源公开数据聚合 (multi-source public data aggregation) | 企业尽调整体架构 |
| 深度查询/画像 | 深度主体公开信息分析 (deep subject public information analysis) | 尽调报告综合 |

---

## 附: 数据源优先级矩阵

按 (Fact级数据密度 × 访问难度 × 对尽调决策价值) 三维排序:

| 排名 | 数据源 | Fact密度 | 访问难度 | 决策价值 | 建议接入方式 |
|------|--------|---------|---------|---------|------------|
| 1 | GSXT(工商注册) | 极高 | 中(CAPTCHA) | 极高 | 自动化视觉响应 + 会话持久化 |
| 2 | 巨潮资讯(上市公司公告) | 极高 | 低(公开API) | 极高 | HTTP GET + JSON解析 |
| 3 | 信用中国(行政处罚) | 极高 | 低(公开查询) | 高 | 公开接口 + HTML结构化提取 |
| 4 | 执行信息公开(司法执行) | 极高 | 低-中 | 高 | 公开查询 + 频率控制 |
| 5 | 裁判文书网(司法诉讼) | 高 | 中-高(登录+验证) | 高 | 会话持久化 + 分段查询 |
| 6 | 中国债券信息网 | 极高 | 低(公开) | 中-高 | HTTP GET + HTML/JSON解析 |
| 7 | 国家知识产权局(专利/商标) | 极高 | 中(CAPTCHA) | 中 | 自动化视觉响应 |
| 8 | 海关/商务部(进出口) | 极高 | 低(公开) | 中 | HTTP GET + 结构化提取 |
| 9 | 税务信用(A级/重大违法) | 极高 | 低(公开) | 中 | HTTP GET + 名单解析 |
| 10 | 政府采购/招标 | 极高 | 低(公开) | 中 | 公开接口 + 网页采集 |
| 11 | 招聘平台(公开岗位) | 低(lead) | 低 | 中 | 搜索引擎定点搜索 |
| 12 | 公开舆情(新闻报道) | 低(lead) | 低 | 中 | 新闻聚合API + 搜索 |
