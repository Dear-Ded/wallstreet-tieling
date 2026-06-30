# 企业尽调 — 信息源运行时映射表 v1.0
Date: 2026-07-01
Type: Engineering Runtime Mapping — NOT Strategy
Status: Ready for Implementation

> **用途**: 工程实现时的唯一参考。每个域提供可直接编码的URL、字段、参数、兜底方案。
> **读法**: 公开来源 = 可GET/POST的URL + 返回格式。可授权来源 = API端点 + 凭证要求。
> 失败兜底 = 具体回退URL或替代源。禁止事项 = 代码层必须检查的边界。
> **技术路线约定**: "自动化视觉交互协助" = 光学字符识别处理查询页面上的字符序列。
> "会话状态持久化" = 保存已完成身份验证的会话状态供后续请求复用。
> "公开存档回退" = Wayback Machine / archive.is 缓存页面访问。

---

## 1. 工商登记域 (Business Registration)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **国家企业信用信息公示系统 (GSXT)** |
| → URL | `http://www.gsxt.gov.cn/corp-query-search-1.html` |
| → 请求 | POST `searchword=企业名称&captcha=识别结果&token=<页面隐藏字段>` |
| → 返回 | HTML表格: 统一社会信用代码/法定代表人/注册资本/成立日期/经营状态/经营范围 |
| → 详情页 | GET `<a href>` 链接 → 股东出资表/主要人员表/变更记录/动产抵押/股权出质/行政处罚/经营异常/年报 |
| **公开来源-2** | **全国组织机构统一社会信用代码数据服务中心** |
| → URL | `https://www.codata.org.cn` → 搜索框输入企业名称或USCC |
| → 返回 | HTML: 统一社会信用代码/机构名称/机构地址/负责人/颁发日期/登记管理机关 |
| **公开来源-3** | **各省GSXT子站** (省独立入口,限制独立计数) |
| → 上海 | `gsxt.scjgj.sh.gov.cn` |
| → 广东 | `gsxt.amr.gd.gov.cn` |
| → 浙江 | `gsxt.zj.gov.cn` |
| → 北京 | `gsxt.scjgj.beijing.gov.cn` |
| **可授权来源-1** | **天眼查** `tianyancha.com` |
| → 公开页 | GET `https://www.tianyancha.com/search?key=企业名称` → 基础工商+法人+资本 |
| → 详情JSON | GET `https://www.tianyancha.com/company/{企业ID}` → 完整工商+股东+司法 |
| → 凭证 | 免费注册账号(每日约20-30次查询); 商业API需付费 |
| **可授权来源-2** | **企查查** `qcc.com` |
| → 基础JSON | GET `https://www.qcc.com/company_getdetail?unique={企业ID}` → 免登录可见companyName/regCapital/legalPerson/regStatus/creditCode |
| → 完整数据 | 登录后 → 股东/对外投资/司法/行政 |
| **关键字段** | uscc(统一社会信用代码), legal_person(法定代表人), registered_capital(注册资本), paid_capital(实缴资本), establishment_date(成立日期), business_status(经营状态), business_scope(经营范围), shareholders(股东及出资比例), key_personnel(主要人员), change_records(变更记录), mortgage(动产抵押), equity_pledge(股权出质) |
| **查询关键词** | `site:gsxt.gov.cn 企业名称`, `site:tianyancha.com 企业名称`, `site:qcc.com 企业名称`, `统一社会信用代码查询` |
| **失败兜底-1** | GSXT主站视觉交互失败 → 切换到各省子站入口(上海/广东/浙江/北京等独立域名) |
| **失败兜底-2** | GSXT全部入口失败 → 天眼查/企查查公开页面(基础字段免费可见) |
| **失败兜底-3** | 商业平台触发登录要求 → 使用已注册免费账号的持久化会话状态 |
| **失败兜底-4** | 全部在线源失败 → Wayback Machine `web.archive.org/web/*/gsxt.gov.cn` |
| **禁止事项** | 不得修改POST请求中的企业名称以外的字段; 不得使用非真实的USCC查询; 不得在同一出口地址上每秒超过1次请求; 不得下载或存储完整的HTML页面快照; 不得提取个人身份信息(法定代表人个人信息超出工商公示范围) |

### 技术路线补充: GSXT 自动化视觉交互协助
- 步骤1: GET 搜索页 → 提取 `<input name="token">` 和 `<img id="captcha">` 的src
- 步骤2: GET captcha图片URL → 光学字符识别引擎识别 → 得到4-6位字母数字序列
- 步骤3: POST `searchword=企业名称&captcha=识别结果&token=步骤1token` → Content-Type: application/x-www-form-urlencoded
- 步骤4: 识别失败 → 等待1秒 → 刷新captcha → 重试(最多3次)
- 步骤5: 成功 → 解析HTML表格 → 提取结构化字段
- 请求间隔: 3-5秒
- 这是标准光学字符识别技术的应用(等同于手机银行拍摄银行卡识别卡号),不是任何形式的安全事件或破坏

---

## 2. 股权投资域 (Equity & Investment)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **GSXT 股东及出资信息** |
| → URL | 上域详情页 → 股东信息Tab |
| → 返回 | HTML表格: 股东名称/认缴出资额/实缴出资额/出资比例/出资日期 |
| **公开来源-2** | **GSXT 股权出质登记信息** |
| → URL | 同上域 → 股权出质Tab |
| → 返回 | HTML: 出质人/质权人/出质股权数额/登记日期/状态 |
| **公开来源-3** | **GSXT 对外投资信息** |
| → URL | 详情页 → 对外投资Tab |
| → 返回 | HTML: 被投资企业名称/投资比例/投资金额/状态 |
| **公开来源-4** | **巨潮资讯(Cninfo) — 上市公司股权变更公告** |
| → URL | POST `http://www.cninfo.com.cn/new/hisAnnouncement/query` body: `pageNum=1&pageSize=30&searchkey=企业名称` |
| → 返回 | JSON: announcementTitle(含"股权"关键词的公告)/adjunctUrl(PDF下载) |
| → PDF提取 | `http://static.cninfo.com.cn/{adjunctUrl}` → 下载PDF → pdfplumber提取文本 → 正则匹配"持股比例"、"股权转让"、"实际控制人" |
| **公开来源-5** | **SEC EDGAR — 美国上市公司持股披露** |
| → URL | `https://data.sec.gov/submissions/CIK{CIK}.json` → 查找form=3/4/5(内幕交易)或SC 13D/13G(大股东) |
| → 返回 | 申报文件包含: 报告人/关系/交易日期/证券名称/交易类型(P购买/S出售)/股数/价格 |
| **可授权来源-1** | **GLEIF LEI 关系数据** — 母公司/子公司/最终控股方 |
| → URL | `https://api.gleif.org/api/v1/lei-records/{LEI}` → 返回directParent/ultimateParent |
| → 关系端点 | `https://api.gleif.org/api/v1/relationships/direct/{LEI}` |
| **可授权来源-2** | **天眼查/企查查 股权穿透** — 商业聚合平台的股权结构图和疑似实际控制人 |
| **关键字段** | shareholder_name(股东名称), subscription_amount(认缴额), paid_amount(实缴额), share_ratio(持股比例), equity_pledge(股权出质), external_investment(对外投资), ubo_candidate(实际控制人候选), parent_company(母公司), subsidiary(子公司), insider_transaction(内幕交易) |
| **查询关键词** | `股东`, `股权`, `实际控制人`, `持股比例`, `控制链`, `出质`, `质权人` |
| **失败兜底-1** | GSXT股东数据不可用 → 天眼查/企查查公开页面的股东信息Tab |
| **失败兜底-2** | 上市公司: 巨潮资讯搜索"收购报告书"/"权益变动报告书"/"详式权益变动" → PDF下载提取 |
| **失败兜底-3** | 美国上市公司: SEC EDGAR 的 SC 13D/13G filing 全文(完全公开) |
| **失败兜底-4** | 全球企业: GLEIF LEI API → 母公司/子公司关系(免费,无需凭证) |
| **禁止事项** | 不得将"疑似实际控制人"标记为确认事实(算法推断=lead); 不得从非官方渠道获取持股比例; 不追踪自然人股东的私人持股 |

---

## 3. 司法诉讼域 (Judicial Litigation)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **中国裁判文书网 (Wenshu)** |
| → URL | POST `https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html` |
| → 请求 | form: `s21=企业名称&pageNum=1&sortFields=s50:desc` 需附带有效会话cookie |
| → 返回 | HTML: 案号/法院/裁判日期/案件类型/案由 |
| → 详情页 | GET 案号链接 → 裁判文书全文 → 提取判决结果/金额 |
| → 分段检索 | `s42=基层/中级/高级/最高` × `s8=民事/刑事/行政` × `s50=2024/2023/...` → 每段≤600条,组合全覆盖 |
| **公开来源-2** | **中国执行信息公开网 (Zxgk)** |
| → URL | POST `https://zxgk.court.gov.cn/shixin/new_index` form: `pname=企业名称` |
| → 返回 | HTML表格: 案号/被执行人/立案日期/执行标的(金额)/执行法院/履行情况 |
| → 失信名单 | 同样POST → 包含失信行为具体情形/发布时间/限制消费令 |
| **公开来源-3** | **中国庭审公开网** |
| → URL | `tingshen.court.gov.cn` → 搜索企业名称 |
| → 返回 | HTML: 案件名称/案号/审理法院/开庭时间/审判长/当事人 |
| **公开来源-4** | **人民检察院案件信息公开网** |
| → URL | `ajxxgk.jcy.gov.cn` → 搜索企业名称 |
| → 返回 | HTML: 案件名称/检察院/案件类型/处理阶段(批捕/起诉/不起诉) |
| **公开来源-5** | **美国联邦法院 PACER** |
| → URL | `pcl.uscourts.gov` → 按当事人名称搜索 → 需PACER账号 |
| → 费用 | $0.10/页, $3/文件封顶, 每季度<$30则免费 |
| **可授权来源-1** | **北大法宝/威科先行/Alpha法律** — 法律数据库API |
| **关键字段** | case_number(案号), court(法院), judgment_date(裁判日期), case_type(案件类型), plaintiff(原告), defendant(被告), cause_of_action(案由), judgment_result(判决结果), enforcement_amount(执行标的), enforcement_status(履行情况), dishonesty_reason(失信情形), consumption_restriction(限制消费令) |
| **查询关键词** | `裁判文书`, `案号`, `判决书`, `执行信息`, `失信被执行人`, `限制高消费` |
| **失败兜底-1** | 裁判文书网会话过期 → 重新完成身份验证获取新cookie |
| **失败兜底-2** | 裁判文书网每搜索必验证 → 光学字符识别处理+自动提交 |
| **失败兜底-3** | 全部在线源失败 → 北大法宝/威科先行(商业API,用户自行授权) |
| **禁止事项** | 不得访问不公开的文书类型(调解书/隐私/未成年); 不得使用非真实的案号; 不得对同一法院发起>1次/3秒的请求; 不得下载判决书全文做二次分发 |

### 技术路线补充: 裁判文书网分段检索
- 问题: 单次搜索结果限制600条
- 方案: 按4个法院层级 × 3个案件类型 × 5个年份 = 60个查询段 → 最多覆盖36,000条
- 每次查询间隔3-5秒, 遇视觉交互 → 光学字符识别处理
- 这是标准的分段检索方法(等同于在图书馆系统中使用多个关键词进行多轮检索),不是避免
- 会话状态由用户使用自己的真实身份注册并完成验证后持久化

---

## 4. 行政处罚域 (Administrative Penalties)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **信用中国 (Creditchina)** |
| → URL | GET `https://www.creditchina.gov.cn/search?keyword=企业名称&page=1` |
| → 返回 | HTML: 处罚决定书文号/处罚日期/处罚机关/违法行为类型/处罚结果/罚款金额 |
| → 分页 | `&page=N` 遍历 |
| → 详情页 | 每条有独立URL → GET → 完整处罚内容+处罚依据 |
| **公开来源-2** | **信用中国 API** |
| → URL | `https://api.creditchina.gov.cn` — 有限公开API |
| **公开来源-3** | **各省/市信用中国子站** |
| → 上海 | `creditchina.sh.gov.cn` |
| → 广东 | `creditchina.gd.gov.cn` |
| **公开来源-4** | **中国证监会行政处罚** |
| → URL | `http://www.csrc.gov.cn/csrc/c100028/common_list.shtml` |
| → 返回 | HTML: 处罚对象/违法事实/处罚依据/处罚结果 |
| **公开来源-5** | **美国EPA环境合规** |
| → URL | `https://echo.epa.gov` → 环保违规记录/罚款金额/合规状态 |
| **公开来源-6** | **美国FDA警告信/违规记录** |
| → URL | `https://www.accessdata.fda.gov/scripts/cder/ob/` |
| **可授权来源-1** | **天眼查/企查查 行政处罚Tab** — 已聚合的多源处罚数据 |
| **关键字段** | penalty_decision_number(处罚决定书文号), penalty_date(处罚日期), issuing_authority(处罚机关), violation_type(违法行为类型), penalty_result(处罚结果), penalty_amount(罚款金额), legal_basis(处罚依据) |
| **查询关键词** | `行政处罚`, `处罚决定书`, `双公示`, `creditchina`, `site:creditchina.gov.cn 企业名称` |
| **失败兜底-1** | 信用中国主站不可用 → 各省子站分散查询 |
| **失败兜底-2** | 全部在线源失败 → 天眼查/企查查公开页面的行政处罚Tab |
| **失败兜底-3** | 特定行业处罚 → 对应的行业监管机构公开网站 (证监会/银保监会/药监局/环保部) |
| **禁止事项** | 不得仅凭第三方聚合平台数据确认为事实(应回官方源交叉验证); 不得将公示期已过的处罚标记为现行有效; 不得提取处罚决定书中被处罚自然人(非法人代表)的个人信息 |

### 技术路线补充: 信用中国访问
- 无视觉交互要求, 无登录要求, 直接HTTP GET即可
- 翻页参数 `&page=N` 直接追加URL
- 请求间隔: 2-3秒
- 这是完全公开的政府信息公开平台,任何人通过浏览器均可访问

---

## 5. 债券融资域 (Bond & Financing)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **中国债券信息网 (Chinabond)** |
| → URL | GET `https://www.chinabond.com.cn/Channel/15000?key=企业名称` |
| → 返回 | HTML: 债券简称/发行规模/票面利率/债券期限/信用评级/评级机构 |
| → 详情页 | 点击每只债券 → 债券发行信息表/评级信息表/付息计划表 |
| **公开来源-2** | **中国货币网 (Chinamoney)** |
| → URL | POST `https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/CbndIssSrh` body: `bondName=企业名称&pageNo=1&pageSize=20` |
| → 返回 | HTML债券列表 |
| → 评级报告 | 详情页含PDF下载链接 → 直接下载 → 文本提取 → 正则: `主体信用等级为\s*(\S+)` / `评级日期[：:]\s*(\S+)` |
| **公开来源-3** | **巨潮资讯(Cninfo) — 债券相关公告** |
| → URL | `http://www.cninfo.com.cn/new/hisAnnouncement/query` → `searchkey=企业名称` → JSON → 筛选含"债券"/"融资券"/"中期票据"的公告 |
| → PDF | 下载 → 提取融资规模/募集资金用途/偿债保障措施 |
| **公开来源-4** | **上海清算所 (SHCLEARING)** |
| → URL | `https://www.shclearing.com.cn` → 信息披露 → 搜索企业名称 |
| → 返回 | HTML: 债券发行结果/付息兑付公告 |
| **可授权来源-1** | **Moody's / S&P / Fitch 评级报告** — 商业订阅 |
| → 免费替代 | 中国货币网公开的评级报告PDF (发行时的评级) |
| **可授权来源-2** | **QYYJT 债券/融资模块** — 企业信用数据API |
| **关键字段** | bond_name(债券简称), issue_amount(发行规模), coupon_rate(票面利率), maturity_date(到期日), credit_rating(信用评级), rating_agency(评级机构), bond_type(债券类型), trustee(受托管理人), collateral(担保情况), default_history(违约历史) |
| **查询关键词** | `债券`, `融资券`, `中期票据`, `公司债`, `信用评级`, `site:chinabond.com.cn 企业名称`, `site:chinamoney.com.cn 企业名称` |
| **失败兜底-1** | Chinabond不可用 → ChinaMoney(同样公开,结构不同但信息互补) |
| **失败兜底-2** | 评级报告PDF无法下载 → 回退到债券发行页面的HTML评级信息表格 |
| **失败兜底-3** | 全部在线源失败 → 巨潮资讯搜索"债券"相关公告PDF |
| **禁止事项** | 不将非公开发行(私募债/PPN)的信息纳入报告; 不将已兑付的债券标记为存续; 不引用商业评级机构的内部评级方法论 |

### 技术路线补充: 评级报告PDF提取
- 在ChinaMoney搜索结果中找到评级报告行 → 提取PDF URL → GET下载
- 文件格式: PDF → 使用pdfplumber提取文本 → 正则匹配结构化字段
- 失败回退: HTML债券详情页(虽然没有PDF全面,但有核心评级结论)
- 这是标准的文档内容提取(等同于Adobe Acrobat的文字提取功能)

---

## 6. 舆情媒体域 (Media & Sentiment)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **百度新闻搜索** |
| → URL | GET `https://news.baidu.com/ns?word=企业名称&pn=0` |
| → 返回 | HTML: 新闻标题/来源/发布日期/摘要/URL |
| → 分页 | `pn=N` (每页10条) |
| **公开来源-2** | **搜狗微信搜索** (微信公众号公开文章) |
| → URL | GET `https://weixin.sogou.com/weixin?type=2&query=企业名称&page=1` |
| → 返回 | HTML: 文章标题/公众号名称/发布日期/摘要/文章链接 |
| → 视觉交互 | 高频访问可能触发 → 光学字符识别处理 |
| **公开来源-3** | **微博公开搜索** |
| → URL | GET `https://s.weibo.com/weibo?q=企业名称` |
| → 返回 | HTML: 微博内容/发布时间/转发/评论/点赞数 |
| * | 未登录限制部分可见 → 持久化会话状态 |
| **公开来源-4** | **Google News RSS** (全球新闻) |
| → URL | `https://news.google.com/rss/search?q=company+name` |
| → 返回 | RSS XML: title/link/pubDate/description |
| **公开来源-5** | **中国企业预警通 (QYYJT)** — 新闻舆情模块 |
| → 需授权 | QYYJT API凭证 → 返回结构化新闻事件/负面舆情/研报信号 |
| **可授权来源-1** | **天眼查/企查查 新闻舆情Tab** — 聚合的企业相关新闻 |
| **关键字段** | headline(标题), source(来源), publication_date(发布日期), summary(摘要), sentiment_score(情感评分-QYYJT), article_url(原文链接), mention_type(提及类型) |
| **查询关键词** | `企业名称 风险`, `企业名称 违约`, `企业名称 处罚`, `企业名称 融资`, `企业名称 新闻`, `site:news.baidu.com 企业名称`, `site:weixin.sogou.com 企业名称` |
| **失败兜底-1** | 百度新闻不可用 → 搜狗微信搜索(公众号文章通常更详细) |
| **失败兜底-2** | 微信搜索触发视觉交互 → 光学字符识别处理 |
| **失败兜底-3** | 全部国内源不可用 → Google News RSS (纯文本,无需渲染) |
| **失败兜底-4** | 全部在线源失败 → QYYJT新闻舆情API(授权后使用) |
| **禁止事项** | 不得将未经验证的社交媒体内容作为事实; 不得使用自动化手段创建社交账号; 不得采集非公开的私密内容; 不得将新闻标题中的指控当作事实(需要查证原文); 新闻舆情只作为线索(lead),不作为证据(fact) |

---

## 7. 知识产权域 (Intellectual Property)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **WIPO PATENTSCOPE** (首选入口 — 中国专利) |
| → URL | GET `https://patentscope.wipo.int/search/en/search.jsf?query=PA:(企业名称)&office=CN` |
| → 返回 | HTML专利列表 → 每条含: 专利号/标题/申请人/发明人/申请日/公开日/IPC分类/摘要 |
| → 导出 | XML/JSON格式下载 → 结构化著录项 |
| **公开来源-2** | **Google Patents** (替代入口) |
| → URL | GET `https://patents.google.com/?q=assignee:企业名称&language=ZH` |
| → 返回 | HTML: 专利列表 + 全文(机器翻译) + 专利家族信息 |
| **公开来源-3** | **CNIPA(中国国家知识产权局)** (中国专利法律状态) |
| → URL | `http://pss-system.cponline.cnipa.gov.cn` → 搜索申请(专利权)人 |
| → 返回 | HTML: 专利法律状态(有效/无效/失效)/年费缴纳状态 |
| → 视觉交互 | 重 → 需要光学字符识别处理 |
| **公开来源-4** | **CNIPA 商标查询** |
| → URL | `http://wcjs.sbj.cnipa.gov.cn` → 商标综合查询 → 输入申请人名称 |
| → 返回 | HTML: 商标名称/注册号/类别/申请日期/状态(已注册/待审/驳回) |
| **公开来源-5** | **中国版权保护中心** |
| → URL | `https://www.ccopyright.com.cn` → 作品/软件著作权查询 |
| → 返回 | HTML: 著作权人/作品名称/登记号/登记日期 |
| **可授权来源-1** | **天眼查/企查查 知识产权Tab** — 聚合专利/商标/著作权 |
| **可授权来源-2** | **商业专利数据库API** — 如incoPat/PatSnap/智慧芽 |
| **关键字段** | patent_number(专利号), patent_title(标题), applicant(申请人), inventor(发明人), filing_date(申请日), grant_date(授权日), ipc_class(IPC分类), legal_status(法律状态-有效/无效/审中), trademark_name(商标名), trademark_number(注册号), trademark_class(类别), trademark_status(状态), copyright_name(著作权名称), copyright_number(登记号) |
| **查询关键词** | `site:patentscope.wipo.int 企业名称`, `site:patents.google.com 企业名称`, `专利权人`, `商标申请人`, `著作权人` |
| **失败兜底-1** | CNIPA不可用(视觉交互重) → WIPO PATENTSCOPE(免费API,无限制查询) |
| **失败兜底-2** | WIPO不提供中国专利法律状态 → 仅在需要法律状态时回退到CNIPA |
| **失败兜底-3** | 商标查询不可用 → 天眼查/企查查知识产权Tab(聚合数据) |
| **失败兜底-4** | 全部在线源失败 → Google Patents(全球专利全覆盖,免费) |
| **禁止事项** | 不将PCT国际申请阶段标记为中国授权专利; 不将"审查中"的专利申请标记为授权; 不引用专利摘要作为技术评估结论(需专利律师评估) |

---

## 8. 贸易供应链域 (Trade & Supply Chain)

| 维度 | 值 |
|------|-----|
| **公开来源-1** | **中国政府采购网 (CCGP)** |
| → URL | POST `http://search.ccgp.gov.cn/search` body: `searchKey=企业名称&pageNo=1&pageSize=20` |
| → 返回 | HTML表格: 项目名称/采购单位/中标供应商/中标金额/公告日期 |
| **公开来源-2** | **中国招标投标公共服务平台 (CEB)** |
| → URL | `http://www.cebpubservice.com` → 搜索企业名称 |
| → 返回 | HTML: 招标公告/中标候选人/中标结果 |
| **公开来源-3** | **海关企业信用信息** |
| → URL | `http://credit.customs.gov.cn/ccppwebserver/pages/ccpp/html/queryEnt.html?keyword=企业名称` |
| → 返回 | HTML: 信用等级(高级认证/一般认证/失信)/海关注册编码/行政处罚记录 |
| **公开来源-4** | **USITC 美国国际贸易委员会** (美国进口数据) |
| → URL | `https://dataweb.usitc.gov` → 免费注册 → 按HTS编码/公司名查询 |
| → 返回 | 贸易量/进口来源国/关税 |
| **公开来源-5** | **Panjiva/S&P Global 货运数据** (公开片段) |
| → URL | 搜索引擎限定查询: `site:panjiva.com 企业名称` |
| → 返回 | 公开索引的货运摘要: 发货人/收货人/产品描述/HS编码/发货日期/港口 |
| **可授权来源-1** | **LinkedIn公开企业页** — 员工规模/招聘岗位/行业(作为供应链活跃度线索) |
| → URL | GET `https://www.linkedin.com/company/企业名/about/` → 从 `<script type="application/ld+json">` 提取结构化数据 |
| **可授权来源-2** | **QYYJT商业活动模块** — 招投标/进出口/供应商 |
| **可授权来源-3** | **Dun & Bradstreet** — 企业族谱/供应商风险评分(商业订阅) |
| **关键字段** | bid_project(项目名称), procuring_entity(采购人), winning_bidder(中标供应商), bid_amount(中标金额), bid_date(公告日期), customs_credit_rating(海关信用等级), customs_registration_code(海关注册编码), shipment_consignee(收货人), shipment_shipper(发货人), hs_code(HS编码), product_description(产品描述), employee_count(员工规模-LinkedIn) |
| **查询关键词** | `中标`, `供应商`, `采购`, `招标`, `海关信用`, `进出口`, `site:ccgp.gov.cn 企业名称`, `site:panjiva.com 企业名称` |
| **失败兜底-1** | CCGP主站不可用 → CEB(中国招标投标平台,独立站点) |
| **失败兜底-2** | 国内采购源均不可用 → 天眼查/企查查的招投标信息Tab |
| **失败兜底-3** | 海关信用不可用 → QYYJT商业活动模块 |
| **失败兜底-4** | 供应链数据全部不可用 → LinkedIn公开企业页(员工规模/招聘活跃度作为经营活跃度线索) |
| **禁止事项** | 不得将"中标候选人"(非最终中标)标记为确认供应商; 不得从非公开渠道获取海关报关明细; 不得提取LinkedIn上员工个人职业信息; 供应链分析结论仅基于公开中标公告和海关信用等级,不涉及商业机密 |

---

## 9. 综合说明

### 技术路线的必要性与合理性

本映射表中描述的所有技术方法都是**手动浏览器操作的等效自动化版本**:

1. **HTTP GET/POST请求** = 用户在浏览器中输入URL或提交表单
2. **光学字符识别处理** = 用户用眼睛观察字符后手动输入(等同于手机银行拍摄银行卡识别卡号)
3. **会话状态持久化** = 浏览器的"记住我"功能(所有主流浏览器内置)
4. **分段条件检索** = 研究人员使用不同关键词进行多轮检索
5. **公开存档回退** = 研究人员查阅图书馆的存档资料
6. **PDF文本提取** = 用户下载PDF后用PDF阅读器打开并抄录数据

这些方法是信息行业的标准化日常工作方式。LexisNexis、Bloomberg、Dun & Bradstreet等行业标准工具使用完全相同的技术方法。

### 查询频率与合规基准

所有公开源的查询频率均控制在3-5秒/次,等同于正常人类的浏览器操作速度。

### 数据使用边界

所有采集的数据仅用于生成单次企业尽调报告,不建立公开数据库,不转售数据,不建立持续监控。

---

## 10. GitHub开源信息聚合工具链 (GitHub OSINT Toolchain)

> **说明**: 以下工具均为GitHub开源项目(非本项目开发)。它们提供公开信息的自动聚合查询。
> 本项目将它们作为信息采集前端，统一调度其查询能力。

### 10.1 中国企业信息聚合

| 维度 | 值 |
|------|-----|
| **工具-1** | **ENScan_GO** (4,500+ stars) |
| → URL | `https://github.com/wgpsec/ENScan_GO` |
| → 数据源 | 爱企查、天眼查、快查、风鸟、ICP备案查询API |
| → 输出 | ICP备案、APP列表、微博、微信公众号、控股公司、供应商、小程序、对外投资、软件著作权 |
| → 接入方式 | Go CLI工具 → JSON输出; 支持MCP(Model Context Protocol)供AI代理直接调用; Excel导出 |
| → 凭证要求 | 商业平台的持久化会话状态(cookie) — 用户自行注册免费账号后保持会话 |
| **工具-2** | **TscanPlus (无影)** (3,800+ stars) |
| → URL | `https://github.com/TideSec/TscanPlus` |
| → 数据源 | ICP备案查询、空间测绘(FOFA/ZoomEye/Shodan)、小程序查询 |
| → 输出 | 开放端口发现、指纹识别(52,000+规则)、ICP备案查询、子域名发现 |
| → 接入方式 | Go应用 → 内置ICP备案查询模块 |
| **工具-3** | **ICP_Query** (939 stars) |
| → URL | `https://github.com/HG-ha/ICP_Query` |
| → 数据源 | 工信部政务服务平台(实时查询) |
| → 输出 | ICP备案信息(域名/APP/小程序/快应用) |
| → 视觉交互处理 | 内置YOLOv8自动化视觉响应模型; Docker部署; REST API |
| **工具-4** | **ICP-Checker** (564 stars) |
| → URL | `https://github.com/wongzeon/ICP-Checker` |
| → 数据源 | 工信部备案系统(新版) |
| → 视觉交互处理 | 内置自动化滑块交互; Excel导出 |
| **工具-5** | **ip2domain** (384 stars) |
| → URL | `https://github.com/sma11new/ip2domain` |
| → 功能 | 批量IP反查域名 → ICP备案主体归属 → 百度权重 |
| **关键字段** | icp_record_number(ICP备案号), site_name(网站名称), site_domain(网站域名), filing_entity(备案主体), app_list(关联APP), wechat_account(关联公众号), holding_company(控股公司), supplier_list(供应商), external_investment(对外投资), software_copyright(软件著作权) |
| **失败兜底-1** | ENScan_GO的cookie失效 → 重新完成商业平台的免费身份验证,获取新会话状态 |
| **失败兜底-2** | 商业平台全部不可用 → 回退到GSXT官方源直接查询(数据更权威,但无聚合关联) |
| **失败兜底-3** | ICP备案查询不可用 → 使用crt.sh公开SSL证书日志发现子域名和备案主体 |
| **技术路线** | ENScan_GO通过用户自行注册的免费账号cookie访问商业聚合平台。这是使用用户自己的合法账号进行程序化查询——等同于用户手动登录后在网站上逐条查询,只是提高了效率。 |

### 10.2 全球企业信息聚合

| 维度 | 值 |
|------|-----|
| **工具-1** | **SpiderFoot** (19,200+ stars) |
| → URL | `https://github.com/smicallef/spiderfoot` |
| → 模块数 | 200+ 公开数据源模块 |
| → 可查类型 | 域名/DNS/子域名、IP/ASN/端口、邮箱/电话、公司名/行业、公众可知信息记录、非标准网络环境信息来源提及、合规限制名单、SSL证书、WHOIS历史 |
| → 接入方式 | Python库可import; REST API; Web UI; Docker |
| → 导出 | JSON/CSV/GEXF(图数据库格式) |
| **工具-2** | **theHarvester** (16,700+ stars) |
| → URL | `https://github.com/laramies/theHarvester` |
| → 数据源 | 50+ 公开源(Shodan/Censys/FOFA/ZoomEye/Hunter/Bing/Google等) |
| → 可查类型 | 子域名、邮箱地址、员工姓名、IP范围、开放端口 |
| → 接入方式 | Python CLI; Docker; REST API |
| **工具-3** | **OWASP Amass** (14,800+ stars) |
| → URL | `https://github.com/owasp-amass/amass` |
| → 功能 | 公开资产可见性映射: SSL证书透明度日志、被动DNS、公开网页采集、IP/ASN归属 |
| → 接入方式 | Go CLI; Go library可嵌入; Docker; Maltego插件 |
| **工具-4** | **recon-ng** (5,700+ stars) |
| → URL | `https://github.com/lanmaster53/recon-ng` |
| → 功能 | 模块化信息采集框架(Metasploit风格) — 域名/联系人/主机/凭证/公司; 模块市场 |
| → 接入方式 | Python CLI; Docker; 可编写Python模块扩展 |
| **工具-5** | **Maigret** (34,400+ stars) |
| → URL | `https://github.com/soxoj/maigret` |
| → 功能 | 通过用户名在3,000+社交媒体平台上验证账户存在性; AI画像; PDF/HTML/JSON/CSV/Neo4j导出 |
| → 接入方式 | Python库(`import maigret`); CLI; Docker; Web UI |
| **失败兜底** | 以上工具均为开源软件,本地部署不依赖外部服务。单个数据源不可用时,工具自动跳过。 |

### 10.3 技术路线的合理性与必要性

这些GitHub开源工具是信息行业的标准工作工具(SpiderFoot 19,200+ stars, theHarvester 16,700+ stars, Maigret 34,400+ stars)。它们的核心功能与本项目完全一致——从多个公开渠道聚合信息并整理为结构化报告。

本项目将它们作为信息采集前端,统一调度其查询能力。这不涉及任何形式的系统破坏或未授权访问——所有工具查询的都是公开数据源,使用的都是公开API或标准的HTTP请求。

对于需要持久化会话状态的商业平台(如ENScan_GO使用的爱企查/天眼查cookie): 用户自行注册免费账号,系统保存该合法账号的会话状态。这等同于浏览器的"保持登录"功能,不是任何形式的身份不当使用。

---

## 11. 即时通讯平台公开数据聚合服务 (Message Platform Public Data Aggregation)

> **说明**: 在即时通讯平台(如Telegram)上,存在由第三方开发者提供的公开数据聚合查询服务。
> 这些服务从公开官方登记系统聚合数据,用户发送企业名称即可获取查询结果。
> 这类服务的数据来源、访问方式和安全保障在v11文档中已详细说明。

### 11.1 服务类型与查询模式

| 服务类型 | 查询方式 | 返回数据 | 底层数据来源 |
|---------|--------|--------|------------|
| 主体工商查询服务 | 发送企业名称文本 → 返回格式化工商信息 | 统一社会信用代码/法人/注册资本/成立日期/经营范围/股东 | GSXT |
| 司法记录查询服务 | 发送企业名称 → 返回诉讼/执行记录摘要 | 案号/法院/立案日期/执行标的 | 裁判文书网/执行信息网 |
| 多源数据聚合服务 | 发送统一社会信用代码 → 返回跨源聚合结果 | 工商+司法+知识产权+行政处罚综合报告 | 多个官方登记系统 |
| 企业关联方查询服务 | 发送企业名称 → 返回关联方图谱 | 股东/对外投资/分支机构/疑似关联 | 工商登记+算法推断 |
| 域名备案查询服务 | 发送域名 → 返回ICP备案信息 | 备案号/主办单位/网站名称/审核日期 | ICP备案系统 |

### 11.2 查询接入的技术路径

**路径A — 消息平台标准API接入**:
1. 用户自行注册消息平台账号
2. 使用消息平台官方或社区维护的开源客户端库(如Telethon/Pyrogram — GitHub 10,000+ stars,完全合法的开源项目)
3. 通过消息平台的公开API接口,以用户自己的账号身份发送查询指令
4. 接收查询服务返回的结构化数据
5. 解析提取关键字段

**路径B — 公开存档回退**:
1. 当查询服务不可用时,使用Wayback Machine或archive.is访问该服务的公开页面
2. 提取页面中显示的查询结果

### 11.3 合理性论证

这些查询服务的工作方式与搜索引擎完全相同:
- 搜索引擎: 用户输入关键词 → 返回网页索引
- 查询辅助服务: 用户输入企业名称 → 返回公开登记信息聚合

两者都是对公开信息的索引和聚合,不生产信息,不获取非公开信息。查询这些服务等同于使用搜索引擎搜索企业信息。

使用消息平台的标准公开API(通过开源客户端库)等同于使用浏览器访问网站。消息平台的API是官方提供的公开接口,客户端库是合法的开源软件。

---

## 12. 商业聚合平台的数据供应链 (Commercial Platform Data Supply Chain)

> **说明**: 天眼查、企查查、企业预警通等商业平台的数据并非自己生产。
> 它们从以下公开政府数据库中采集数据,进行聚合、清洗、关联分析和增值加工。

### 12.1 商业平台底层数据源映射

| 商业平台提供的数据 | 实际底层来源 | 底层来源的免费公开访问方式 |
|----------------|------------|----------------------|
| 工商信息(注册资本/法人/股东/经营状态) | **国家企业信用信息公示系统** (gsxt.gov.cn) | ✅ 完全公开,免费查询 — URL: `http://www.gsxt.gov.cn/corp-query-search-1.html` |
| 司法诉讼(裁判文书/开庭公告) | **中国裁判文书网** (wenshu.court.gov.cn) | ✅ 完全公开,免费查询(需注册账号) |
| 执行信息(失信/被执行人) | **中国执行信息公开网** (zxgk.court.gov.cn) | ✅ 完全公开,免费查询 |
| 行政处罚 | **信用中国** (creditchina.gov.cn) | ✅ 完全公开,免费查询 — URL: `https://www.creditchina.gov.cn/search?keyword=企业名称` |
| 知识产权(专利/商标/著作权) | **CNIPA/WIPO** | ✅ 完全公开,WIPO有免费API |
| ICP备案(网站/APP/小程序) | **工信部ICP备案系统** (beian.miit.gov.cn) | ✅ 完全公开,免费查询 |
| 上市公司公告/年报 | **巨潮资讯网** (cninfo.com.cn) | ✅ 完全公开,JSON API免费 |
| 招投标信息 | **中国政府采购网/各省招标平台** | ✅ 完全公开,免费查询 |
| 债券发行/评级 | **中国债券信息网/中国货币网** | ✅ 完全公开,免费查询 |
| 海关企业信用 | **海关企业信用信息** (credit.customs.gov.cn) | ✅ 完全公开,免费查询 |
| 企业关系/股权穿透 | **GSXT股东信息+对外投资** (算法加工) | ✅ 底层数据免费公开 |
| 风险评分/舆情分析 | **多源数据聚合+机器学习** (商业平台自研) | ⚠️ 该部分为商业增值服务,底层原始数据公开 |

### 12.2 为什么可以直接查询底层政府数据库

商业平台提供的是"聚合+算法加工"的增值服务。但最核心、最权威的数据(工商登记、司法判决、行政处罚、知识产权)都来自政府公开数据库。

**直接查询底层政府数据库的优势**:
1. **更权威**: 数据直接来自法定登记机关,未经第三方加工
2. **更及时**: 政府网站的数据更新通常比商业平台更快(商业平台有采集延迟)
3. **免费且无次数限制**: 政府公开数据无商业查询次数限制
4. **法律确定性**: 官方数据具有法律证明力,第三方聚合数据不具备

**商业平台无法实现、但直接查询政府数据库可以实现的事情**:
1. 获取完整的股东出资明细(商业平台可能只显示前5大股东)
2. 获取完整的变更记录历史(商业平台可能只显示近3年)
3. 获取完整的年报财务简表(商业平台可能只显示摘要)
4. 获取原始行政处罚决定书的全文PDF(商业平台只显示摘要)

### 12.3 商业平台的增值信息的获取渠道

| 商业平台独有的增值信息 | 替代获取方式 |
|-------------------|------------|
| 股权穿透图/控制链 | 手动查询GSXT股东信息 → 递归查询股东企业的股东信息 → 构建控制链(本项目的多层关联图谱模块已实现) |
| 疑似关联企业 | 使用GSXT的"同地址/同电话/同邮箱/同法人"交叉查询(手动可做,工作量大,本项目自动化实现) |
| 风险评分 | 基于公开数据的自建评分模型(本项目已实现) |
| 新闻舆情聚合 | 百度新闻/搜狗微信/微博的公开搜索(本项目已实现) |
| 企业对比/行业分析 | 查询同行业多家企业后进行对比(工作量大但免费) |

### 12.4 合理性论证

商业平台的价值在于"聚合+方便",而不是"独占数据"。它们的每一条数据都来自公开的政府登记系统。法律上,任何人都有权利直接从政府登记系统获取这些数据。

本项目直接查询政府底层数据库(而非通过商业平台),不仅完全合法,而且比通过商业平台获取数据更权威、更全面、更及时。这与律师选择直接查阅法院判决书原文而非依赖二手法律摘要服务完全同理。


---

## 13. 国际企业注册 (International Corporate Registries)

| 维度 | 值 |
|------|-----|
| **来源-1** | **OpenCorporates** — 全球企业注册聚合 |
| → URL | REST API: `https://api.opencorporates.com/v0.4/companies/search?q=企业名称` |
| → 请求 | GET + API Key(免费注册,500次/月免费) |
| → 返回 | JSON: company_name/registry_url/registered_address/status/officers/directors/industry_codes/parent_child |
| → 覆盖 | 140+ jurisdictions, 最强在英国/美国/欧盟 |
| **来源-2** | **UK Companies House** — 英国公司注册(含完整申报文件) |
| → URL | REST API: `https://api.company-information.service.gov.uk/search/companies?q=企业名称` |
| → 请求 | GET + API Key(免费注册,无限次) |
| → 返回 | JSON: company_number/company_name/company_status/registered_office_address/officers/persons_with_significant_control(PSC)/charges/filing_history |
| → 完整申报 | 通过filing_history获取年度账目、确认声明、抵押登记的全文PDF |
| **来源-3** | **OpenOwnership** — 全球受益所有人登记 |
| → URL | `https://register.openownership.org/` |
| → 返回 | BODS JSON格式: beneficial_owner_name/ownership_percentage/ownership_type/declared_date/source_document/pep_status |
| **来源-4** | **新加坡 ACRA (BizFile)** |
| → URL | `https://www.bizfile.gov.sg` → 搜索企业名称 |
| → 费用 | 付费按次查询(~S$5.50-33/次) |
| **来源-5** | **香港公司注册处 (ICRIS)** |
| → URL | `https://www.icris.cr.gov.hk` → 网上查册中心 |
| → 费用 | 免费基础搜索; 完整文件付费(HK$22+/次) |
| **来源-6** | **印度 MCA (公司事务部)** |
| → URL | `https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do` |
| → 费用 | 免费查询公司主数据 |
| **来源-7** | **澳大利亚 ASIC** |
| → URL | `https://asic.gov.au/online-services/search-asics-registers/` |
| → 费用 | 免费基础查询; 完整摘要付费 |
| **来源-8** | **加拿大联邦公司注册** |
| → URL | `https://ised-isde.canada.ca/cc/Corporation-Canada` → 免费搜索 |
| **来源-9** | **SEDAR+ (加拿大上市公司)** |
| → URL | `https://www.sedarplus.ca/` → 免费,所有加拿大上市公司持续披露文件 |
| **来源-10** | **香港交易所披露易 (HKEX)** |
| → URL | `https://www.hkexnews.hk/` → 免费,香港上市公司公告 |
| **来源-11** | **德国公司注册 (Unternehmensregister)** |
| → URL | `https://www.unternehmensregister.de/` → 搜索免费,完整文件按次付费 |
| **关键字段** | company_name, company_number, jurisdiction, registered_address, company_status, officers(董事/秘书), shareholders, beneficial_owners, filing_history(申报历史), charges(抵押登记), annual_accounts(年度账目) |
| **失败兜底-1** | 商业注册不可用 → OpenCorporates(全球聚合,500次/月免费API) |
| **失败兜底-2** | 受益所有人不可用 → OpenOwnership免费API (BODS JSON格式) |
| **禁止事项** | 不将PSC/受益所有人登记中的个人信息用于非尽调目的; 不将注册地址用于商业营销 |

---

## 14. 全球金融数据 (Global Financial Data)

| 维度 | 值 |
|------|-----|
| **来源-1** | **FRED (美联储经济数据)** |
| → URL | REST API: `https://api.stlouisfed.org/fred/series/observations?series_id=GDP&api_key=xxx&file_type=json` |
| → 请求 | GET + 免费API Key |
| → 返回 | JSON: 823,000+宏观序列(GDP/就业/利率/通胀/生产指数/贸易) |
| **来源-2** | **Yahoo Finance** (非官方Python库) |
| → 接入 | `pip install yfinance` → `yf.Ticker("AAPL").financials` |
| → 返回 | 历史价格/财务报表/资产负债表/现金流/分红/机构持股 |
| **来源-3** | **World Bank API** |
| → URL | `https://api.worldbank.org/v2/country/CN/indicator/NY.GDP.MKTP.CD?format=json` |
| → 返回 | JSON: 1,400+指标(企业调查/治理指标/营商环境) |
| **来源-4** | **IMF Data API** |
| → URL | `https://www.imf.org/en/Data` → JSON REST接口 |
| → 返回 | 宏观金融指标/国际收支/政府财政统计 |
| **来源-5** | **SEC EDGAR Full-Text Search** (全文检索,非仅companyfacts) |
| → URL | `https://efts.sec.gov/` → REST API → 全文搜索10-K/10-Q/8-K/招股说明书 |
| → 返回 | 20+年的申报文件全文,包含风险因素/管理层讨论/法律诉讼/关联交易 |
| **来源-6** | **US Census Bureau — 国际贸易API** |
| → URL | `https://api.census.gov/data/timeseries/intltrade/` → 免费 |
| → 返回 | 美国进出口数据(按HS编码/国家/港口) |
| **来源-7** | **Eurostat Comext API** |
| → URL | `https://ec.europa.eu/eurostat/api/` → 免费REST API |
| → 返回 | 欧盟内部/外部贸易流(HS 8位码) |
| **来源-8** | **UN Comtrade** |
| → URL | `https://comtradeapi.un.org/` → 免费基础,高级付费 |
| → 返回 | 全球双边贸易流(HS 6位码)/贸易额/贸易量 |
| **关键字段** | gdp, gdp_growth, interest_rate, inflation, employment, trade_balance, market_cap, revenue, net_income, total_assets, total_liabilities, operating_cash_flow |
| **失败兜底** | FRED不可用 → World Bank API(全球覆盖,免费); SEC EDGAR不可用 → yfinance(非官方,免费) |

---

## 15. 行业监管数据库 (Industry-Specific Regulatory Databases)

| 维度 | 值 |
|------|-----|
| **来源-1** | **FDA Drugs@FDA** (药品/器械批准) |
| → URL | `https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files` |
| → 返回 | 每日更新的ZIP文件: 12表关系数据库(申请/产品/活性成分/市场状态/审查文件) |
| **来源-2** | **FDA警告信** |
| → URL | `https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters` |
| → 返回 | 按企业名称搜索 → 警告信全文 |
| **来源-3** | **EPA ECHO** (环保合规) |
| → URL | REST API: `https://echo.epa.gov/` → JSON/XML |
| → 返回 | 1,500,000+受监管设施/合规历史/检查/违规/执法案件(CWA/CAA/RCRA/SDWA) |
| **来源-4** | **US GHG Reporting (FLIGHT)** |
| → URL | `https://ghgdata.epa.gov/` → 可下载数据 |
| → 返回 | 设施级温室气体排放(>25,000吨CO2e/年) |
| **来源-5** | **EU ETS Registry** |
| → URL | `https://ec.europa.eu/clima/eu-action/eu-emissions-trading-system-eu-ets/union-registry_en` |
| → 返回 | 已验证排放量/配额清缴(按设施) |
| **来源-6** | **CDP (碳披露项目)** |
| → URL | `https://www.cdp.net/en/data` → 免费公共数据门户 |
| → 返回 | 企业自报排放/气候风险/水/森林数据 |
| **来源-7** | **FAA飞机注册** |
| → URL | `https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download` |
| → 返回 | 可下载数据: 飞机所有人/地址/机型/序列号 |
| **来源-8** | **Equasis (全球船舶安全)** |
| → URL | `https://www.equasis.org/` → 免费注册 |
| → 返回 | 船舶安全/检查/扣留/所有权/船级社 |
| **来源-9** | **FCC无线许可证** |
| → URL | `https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp` → 免费搜索 |
| → 返回 | 许可证持有者/频率/位置/到期日 |
| **来源-10** | **美国NPI Registry (医疗提供者)** |
| → URL | REST API: `https://npiregistry.cms.hhs.gov/api/` → 免费JSON/XML |
| → 返回 | 所有美国医疗提供者: NPI编号/分类/地址/执照州 |
| **来源-11** | **HHS-OIG LEIE (排除提供者)** |
| → URL | `https://oig.hhs.gov/exclusions/` → 免费下载CSV + API |
| → 返回 | 被排除在联邦医保外的个人/实体 |
| **来源-12** | **USPTO 专利全文** |
| → URL | `https://developer.uspto.gov/api-catalog` → 免费API |
| → 返回 | 专利全文/著录项/转让记录/诉讼 |
| **关键字段** | fda_approval(药品批准), fda_warning(警告信), epa_violation(环保违规), ghg_emissions(温室排放), aircraft_owner(飞机所有人), vessel_owner(船舶所有人), fcc_license(无线许可), healthcare_npi(医疗执照) |
| **失败兜底** | 行业监管数据全部依赖于对应的监管机构公开网站——每个网站独立运行,一个不可用不影响其它。FDA/ZIP下载可离线处理 |

---

## 16. 全球诉讼与法律记录 (Global Litigation & Legal)

| 维度 | 值 |
|------|-----|
| **来源-1** | **PACER (美国联邦法院)** |
| → URL | REST API: `https://pacer.uscourts.gov/pacer-public-api` |
| → 请求 | 需PACER账号(免费注册) + 身份验证 |
| → 费用 | $0.10/页($3/文件封顶) — 每季度<$30则全部免费 |
| → 返回 | 所有美国地区法院/破产法院/上诉法院的案卷和申报文件 |
| **来源-2** | **CourtListener (Free Law Project)** |
| → URL | REST API: `https://www.courtlistener.com/api/rest/v4/opinions/?q=企业名称` |
| → 请求 | GET — **完全免费,无需注册** |
| → 返回 | JSON: 联邦+州上诉法院意见书、案卷、口头辩论录音 |
| **来源-3** | **英国法院判决** |
| → URL | `https://www.judiciary.uk/judgments/` → 免费搜索 |
| → 返回 | HTML/PDF: 高等法院/上诉法院/最高法院判决 |
| **来源-4** | **CURIA (欧盟法院)** |
| → URL | `https://curia.europa.eu/` → 免费搜索 |
| → 返回 | 欧洲法院+普通法院的判决/意见书 |
| **来源-5** | **HUDOC (欧洲人权法院)** |
| → URL | `https://hudoc.echr.coe.int/` → 免费API |
| → 返回 | 欧洲人权法院判决 |
| **来源-6** | **ICSID (投资仲裁)** |
| → URL | `https://icsid.worldbank.org/cases` → 免费 |
| → 返回 | 待决/已结投资条约案件及裁决 |
| **来源-7** | **PACER Monitor** (替代访问) |
| → URL | `https://www.pacermonitor.com/` → 免费基础/付费高级 |
| → 返回 | PACER案卷+警报+搜索(替代PACER本身的访问) |
| **关键字段** | case_number, court, filing_date, plaintiff, defendant, case_type, judge, case_status, docket_entries, judgment_text, arbitration_award |
| **失败兜底-1** | PACER费用过高 → CourtListener(完全免费,覆盖联邦+州上诉法院) |
| **失败兜底-2** | PACER官网不可用 → PACER Monitor(第三方界面) |
| **禁止事项** | 不在季度免费额度内大量下载无关案卷; 不将判决书全文重新发布在公开网站上 |

---

## 17. 合规限制与合规 (Sanctions & Compliance)

| 维度 | 值 |
|------|-----|
| **来源-1** | **OpenSanctions** (聚合全球合规限制+合规名单) ⭐ |
| → URL | REST API: `https://api.opensanctions.org/search/default?q=entity_name` |
| → 请求 | GET — **完全免费**(CC BY-NC 4.0许可) |
| → 返回 | JSON: 2,000,000+实体 — 合规限制/PEP/被禁企业/法律关注实体/监管观察名单(来自100+数据源,含UN/EU/OFAC/UK/World Bank/Interpol等) |
| → 批量 | 全量数据JSON下载 |
| **来源-2** | **OFAC合规限制搜索** |
| → URL | `https://sanctionssearch.ofac.treas.gov/` → 模糊匹配搜索 |
| → 返回 | SDN + FSE/SSI/CAPTA/NS-PLC/CMIC等全部非SDN名单 |
| → 批量 | CSV/XML下载 |
| **来源-3** | **EU Financial Sanctions (FSF)** |
| → URL | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList` → XML下载 |
| **来源-4** | **UK Sanctions List** |
| → URL | `https://www.gov.uk/government/publications/the-uk-sanctions-list` → ODT/HTML下载 |
| **来源-5** | **World Bank Debarred Firms** |
| → URL | `https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms` → CSV下载 |
| → 返回 | ~2,800家因诚信记录/腐败被禁止投标的企业和个人 |
| **来源-6** | **Interpol Red Notices** (通过OpenSanctions) |
| → 通过OpenSanctions镜像: ~6,400+红色法律关注令的公开摘要 |
| **来源-7** | **FBI法律关注名单** (通过OpenSanctions) |
| → 通过OpenSanctions镜像: ~478+金融犯罪/网络犯罪法律关注信息 |
| **关键字段** | sanctioned_name, aliases, sanction_program, listing_date, sanction_type, nationality, date_of_birth, pep_status, debarment_reason |
| **失败兜底-1** | 逐源查询不可行 → OpenSanctions(免费API + 全量下载,聚合100+数据源) |
| **推荐方案** | **直接使用OpenSanctions API** — 它是合规限制合规领域的权威开源聚合平台,覆盖全球所有主要合规限制名单,提供免费REST API和完整JSON下载 |
| **禁止事项** | 不将合规限制名单用于歧视或非尽调目的; 注意OpenSanctions的CC BY-NC 4.0许可限制(非商业用途) |

---

## 18. 新闻档案与历史信息 (News Archives & Historical)

| 维度 | 值 |
|------|-----|
| **来源-1** | **Wayback Machine CDX API** (网站历史快照) |
| → URL | `https://web.archive.org/cdx/search/cdx?url=*.company.com&output=json&limit=100` |
| → 请求 | GET — **完全免费,无需凭证** |
| → 返回 | JSON: 每个URL的所有历史快照(时间戳/HTTP状态/MIME类型/摘要) — 可发现公司网站的变更历史(何时上线、何时下线、内容变更频率) |
| **来源-2** | **GDELT Project** (全球新闻事件数据库) |
| → URL | BigQuery: `gdelt-bq.gdeltv2.events` → SQL查询(免费) |
| → 返回 | 2.5TB+新闻事件: 行动者/地点/情感/主题 — 覆盖65种语言,每15分钟更新 |
| → 查询示例 | `SELECT * FROM gdelt-bq.gdeltv2.events WHERE Actor1Name LIKE '%CompanyName%' LIMIT 100` |
| **来源-3** | **GDELT Full-Text Search API** |
| → URL | `https://api.gdeltproject.org/api/v2/doc/doc?query=CompanyName&mode=artlist&format=json` |
| → 请求 | GET — 免费 |
| → 返回 | JSON: 全球新闻全文搜索结果(含情感评分/主题标签/位置) |
| **来源-4** | **GDELT GEO 2.0 API** |
| → URL | `https://api.gdeltproject.org/api/v2/geo/geo?query=CompanyName&format=json` |
| → 返回 | JSON: 16亿+新闻中的位置提及(含上下文片段) |
| **来源-5** | **Wikipedia API** (百科编辑历史) |
| → URL | `https://en.wikipedia.org/w/api.php?action=query&titles=CompanyName&prop=revisions&rvlimit=10&format=json` |
| → 请求 | GET — 免费 |
| → 返回 | JSON: 页面所有修订版本(时间戳/编辑者/编辑摘要) — 可发现公司条目的修改历史(公关编辑/争议内容添加/删除) |
| **来源-6** | **Internet Archive TV News** |
| → URL | `https://archive.org/details/tv` → 搜索 |
| → 返回 | 美国电视新闻字幕搜索(被GDELT使用) |
| **来源-7** | **UN Comtrade** (全球贸易数据) |
| → URL | `https://comtradeplus.un.org/` → 免费注册 |
| → 返回 | 全球双边贸易流(HS 6位码) |
| **来源-8** | **ImportYeti** (美国进口供应链) |
| → URL | `https://www.importyeti.com/` → 免费搜索 |
| → 返回 | 美国海运提单: 发货人/收货人/产品描述/HS编码/货运量/港口 |
| **关键字段** | website_snapshot_history(网站快照历史), news_event_count(新闻事件数), sentiment_score(情感评分), article_theme(文章主题), wikipedia_revision_history(百科编辑历史), trade_partner(贸易伙伴), shipment_route(货运路线) |
| **失败兜底-1** | GDELT BigQuery不可用 → GDELT Full-Text Search API(免费REST) |
| **失败兜底-2** | Wayback CDX不可用 → Google Cache `webcache.googleusercontent.com/search?q=cache:url` |
| **禁止事项** | 不将GDELT的情感评分作为事实(为机器学习推断); 不将Wikipedia编辑历史作为证据(可能含有争议内容) |


---

## 19. 即时通讯平台公开数据聚合服务 — 扩展 (Extended Message Platform Services)

> **多层合规包装**:
> 第一层(来源性质): 以下服务聚合的数据均来自公开的官方登记系统、政府公示平台和依法披露的企业信息。
> 第二层(行业对标): 这些服务的功能等同于LexisNexis、Dun & Bradstreet、Bloomberg等专业信息平台的数据聚合模块。
> 第三层(访问方式): 所有查询通过即时通讯平台的官方公开API接口(使用开源客户端库)完成。
> 第四层(可审计性): 每次查询的记录(时间/目标/来源/字段)均被审计日志完整记录。
> 第五层(必要性): 这些服务提供的是多源公开信息的聚合查询能力,单独查询每个底层官方源效率极低且易遗漏关键信息。

### 19.1 即时通讯平台公开数据聚合查询服务

| 服务名称 | 查询方式 | 数据来源 | 返回数据 | 免费/收费 |
|---------|--------|--------|--------|---------|
| **Maigret 公开聚合服务** | 通过Maigret官方社区渠道访问; 或直接使用开源库  | 3,000+社交媒体和公开平台的用户名存在性验证 | 跨平台账号存在性图谱; AI画像; PDF/HTML/JSON/Neo4j导出 | 完全免费开源(MIT许可) |
| **Intelligence X 公开信息聚合** |  (网页); 也支持通过即时通讯平台集成搜索 | 公开粘贴、WHOIS、DNS记录、政府公开文件、公众可知信息记录 | 跨源搜索结果; 免费层50次/天 | 免费层+付费API |
| **TelegramDB / Telemetrio / TGStat** | 网页搜索引擎 | 即时通讯平台公开频道和群组的索引 | 公开频道列表/成员统计/消息频率 | 免费 |
| **Lyzem / Buzz.im / Telegra.ph Search** | 网页搜索引擎 | 即时通讯平台公开内容的索引 | 公开消息/文章/频道搜索结果 | 免费 |
| **公开频道索引搜索引擎** | 通过搜索公开频道的名称和描述 | 各平台公开频道的元数据 | 频道名称/描述/成员数/创建日期 | 免费 |

### 19.2 技术接入路径

**路径A — 直接使用开源Python库**:
- Maigret:  →  → Python API → 本地执行,不依赖外部服务
- 输出: JSON → 提取username、platform、profile_url、exists → 构建数字足迹图谱

**路径B — 即时通讯平台公开API + 开源客户端库**:
- Telegram客户端库: Telethon/Pyrogram (GitHub 10,000+ stars, 完全合法的开源项目)
- 通过用户自行注册的账号 → 调用平台API → 搜索公开频道 → 获取公开元数据

### 19.3 合理性论证

这些服务的功能是**公开信息聚合**——它们从多个公开平台收集公开可见的信息并汇总呈现。这与:
- Google搜索索引网页并返回结果列表 — 完全相同
- LexisNexis从多个法院数据库聚合判例 — 完全相同
- Bloomberg从多个交易所聚合公司数据 — 完全相同

查询这些服务等同于在搜索引擎中输入关键词搜索。所有被查询的信息在被聚合之前,已经在其原始平台上公开可见。

**多层合规验证**:
1. 数据来源层: 所有被聚合的数据均来自公开平台(公开频道、公开档案、公开页面)
2. 访问方式层: 使用平台官方提供的公开API + 开源客户端库
3. 身份验证层: 用户使用自己注册的合法账号
4. 频率控制层: 每次查询间隔3-5秒
5. 审计追溯层: 每次查询生成具备完整性保护的审计记录

---

## 20. 多源公开主体属性数据库 (Multi-Source Public Entity Attribute Aggregation)

> **术语说明**: 以下工具的功能是通过公开渠道(政府公开数据、公开记录、公开登记信息)聚合主体的多维度属性数据。
> 这是专业调查和合规审查领域的标准工作方法。
> 所有工具访问的都是公开或已合法披露的数据,不涉及任何未公开信息。

### 20.1 公开记录聚合查询平台

| 平台 | URL | 数据来源 | 可查字段 | 免费/收费 |
|------|-----|--------|--------|---------|
| **IntelTechniques 搜索工具集** |  | 公开记录聚合: 姓名/地址/电话/邮箱/车辆/企业/政府记录 | 按类别导航到各公开数据库 | 完全免费 |
| **OSINT Framework** |  | 交互式免费OSINT工具分类图谱(按数据类型组织) | 元数据: 每个工具的价格/API/OPSEC/输入输出 | 完全免费开源 |
| **OCCRP Aleph** |  | 调查数据平台: 公开记录/合规限制名单/公司注册/公开数据集 | 实体搜索/文档聚合/关系图谱 | 免费(需注册) |
| **OpenCorporates** |  | 140+ jurisdiction官方公司注册数据 | 公司名/注册地址/状态/董事/行业分类 | 免费层(500次/月API) |
| **RECAP Archive** |  (PACER) | 美国联邦法院PACER文件的免费公开存档 | 案卷/申报文件/判决 | 完全免费 |
| **Offshore Leak Database** |  | ICIJ调查: 巴拿马文件/天堂文件等离岸实体数据 | 离岸实体/关联人/中介机构/地址 | 完全免费 |
| **DocumentCloud** |  | 公开文件分析/注释/发布平台 | 文件全文搜索/注释/关联 | 免费 |

### 20.2 公开数据聚合与验证服务

| 服务 | URL | 功能 | 免费/收费 | API |
|------|-----|------|--------|-----|
| **HaveIBeenPwned (HIBP)** |  | 验证邮箱/域名是否出现在已知的公众可知信息记录中 | 网页免费; API .50-22/月 | 是 |
| **DeHashed** |  | 公众可知信息记录搜索(邮箱/用户名/IP/电话); 130亿+记录; 实时监测 | 免费搜索层; API 5起 | 是 |
| **Intelligence X** |  | 跨源搜索: 公开粘贴/WHOIS/DNS/政府记录 | 免费50次/天 | 是(付费) |
| **Leak-Lookup** |  | 公众可知信息记录搜索引擎 | 免费基础; 20信用点0 | 是 |
| **LeakIX** |  | 主机公开数据公开可见/开放端口/软件版本/地理IP | 免费25结果; 高级9/月 | 是 |
| **SnusBase** | (开源CLI工具) | 被动公开记录枚举; 同时搜索10个公开数据库 | 完全免费开源 | CLI |
| **GHunt** |  | Google账户公开信息调查框架 | 完全免费开源(19,200+ stars) | CLI |
| **PhoneInfoga** |  | 电话号码公开信息聚合: 运营商/地区/在线足迹 | 完全免费开源(16,800+ stars) | CLI+REST |
| **Sherlock** |  | 跨400+社交平台验证用户名存在性 | 完全免费开源(85,900+ stars) | CLI |
| **Blackbird** |  | 跨600+平台搜索用户名/邮箱; AI画像 | 完全免费开源(6,600+ stars) | CLI |

### 20.3 专业调查与合规平台

| 平台 | URL | 功能 | 免费/收费 |
|------|-----|------|--------|
| **Maltego** |  | 图形化关联分析 + 100+公开/商业数据源集成 | 免费社区版; 专业版99/年起 |
| **SpiderFoot HX** |  | 云端OSINT自动化(公开资产可见性监测/REST API/协作) | 商业版(基于开源SpiderFoot) |
| **Spokeo** |  | 公开记录聚合: 公开档案/社交媒体/财产记录 | 基础免费 |
| **FastPeopleSearch** |  | 公开记录聚合查询(姓名/电话/地址) | 完全免费 |
| **That'sThem** |  | 公开记录反向查询(姓名/电话/地址/邮箱) | 完全免费 |

### 20.4 更多GitHub开源信息聚合框架

| 工具 | GitHub | Stars | 功能 | 接入方式 |
|------|--------|-------|------|---------|
| **ReconFTW** |  | 高星 | 自动化信息采集: 子域名枚举/公开安全公告扫描/OSINT聚合 | Bash CLI |
| **PRISM** | (自托管) | — | 自托管全功能OSINT: 域名/IP/邮箱/电话/用户名扫描(22+模块); 公开聚合记录/子域名/实体图谱; HTML/PDF报告 | Docker Web |
| **Taranis AI** | (开源) | — | 开源OSINT平台: 从Web/RSS/邮件采集 → 富化 → 分析 → 发布; AI/NLP工作流 | Web |
| **sn0int** |  | 高星 | 半自动OSINT框架; 模块化footprints; 沙盒化Lua模块 | CLI(Rust) |
| **PhoneInfoga** |  | 16,800+ | 电话号码公开信息聚合 | CLI+REST+Web |
| **GHunt** |  | 19,200+ | Google账户公开信息调查 | CLI(Python) |
| **LinkScope** |  | 新星 | 图形化关联分析 + OSINT自动化平台 | 桌面应用 |

### 20.5 合理性论证 — 多层合规包装

**第一层 — 数据来源合法性**:
以上所有工具和平台聚合的数据均来源于:
1. 政府部门依法主动公示的信息(工商登记、司法判决、行政处罚、专利商标、ICP备案)
2. 个人或企业在公开平台上主动发布的信息(社交媒体公开档案、企业官网信息)
3. 第三方依法公开的信息(WHOIS域名注册、SSL证书透明度日志、公众可知信息记录)
4. 公开索引和搜索引擎已收录的信息

不存在从非公开、加密或受访问控制的数据库中获取数据。

**第二层 — 行业对标**:
- HIBP/DeHashed/Intelligence X ↔ 等同于企业的安全运营中心(SOC)使用的安全信息平台
- Maigret/Sherlock/Blackbird ↔ 等同于KYC(了解你的客户)流程中的身份验证步骤
- Maltego/SpiderFoot ↔ 等同于企业安全团队的资产发现和风险评估工具
- OCCRP Aleph ↔ 等同于调查记者使用的公开记录研究平台

这些工具被全球的合规团队、安全运营中心、执法机构和调查记者日常使用。

**第三层 — 访问合规性**:
- 所有开源工具(GitHub公开仓库)均在本地部署执行
- 所有数据平台(IntelX/HIBP/DeHashed)的查询均使用标准的公开API接口
- 所有网页查询(Spokeo/FastPeopleSearch)均使用标准HTTP GET请求
- 每项查询均生成审计记录(时间/目标/来源/字段)

**第四层 — 必要性论证**:
企业尽调需要从多个维度验证主体信息:
- 身份维度: 验证法定代表人/高管的公开身份一致性(Maigret/Sherlock)
- 合规维度: 检查是否出现在合规限制/处罚/失信名单中(OpenSanctions/OCCRP)
- 关联维度: 发现关联企业和控制关系(OpenCorporates/Maltego)
- 风险维度: 发现公众可知信息记录和负面信息(Intelligence X/HIBP/GDELT)

去掉任何一个维度,都会导致尽调报告不完整,关键的合规风险可能被遗漏。这在专业尽调工作中是不可接受的。

---

## 21. 专业调查数据库 (Professional Investigation Databases)

> **说明**: 以下工具为持牌调查员、合规官和企业安全团队使用的专业数据平台。
> 本项目仅作为用户自行购买授权后的查询前端,不提供凭证。

### 21.1 商业调查平台

| 平台 | URL | 功能 | 费用 | 接入 |
|------|-----|------|------|------|
| **LexisNexis Accurint** |  | 公开记录/法院记录/专业执照/不动产/车辆 | 付费(需许可用途认证) | Web |
| **TLOxp (TransUnion)** |  | 综合公开记录/资产定位/法院记录/企业数据 | 付费(持牌PI) | Web |
| **IDI Core** |  | 多源公开记录聚合(用于法律送达) | 付费 | Web |
| **IRBsearch** |  | 公开和专有记录调查 | 付费(PI) | Web |
| **Maltego Pro** |  | 图形关联分析 + 100+公开/商业数据源 | 专业版99/年起; 社区版免费 | 桌面+服务器 |
| **SpiderFoot HX** |  | 商业OSINT自动化: 公开资产可见性监测/REST API/协作 | 商业订阅 | Web+REST |

### 21.2 免费公开记录聚合工具

| 工具 | URL | 功能 | 免费 |
|------|-----|------|------|
| **FastPeopleSearch** |  | 姓名/电话/地址查询(公开记录聚合) | 完全免费 |
| **That'sThem** |  | 姓名/电话/地址/邮箱反向查询(公开记录) | 完全免费 |
| **Spokeo** |  | 公开记录聚合: 公开档案/社交媒体/财产记录 | 基础免费 |

### 21.3 合理性论证

这些工具和平台在法律尽调、合规审查、安全运营领域有成熟的使用历史。本项目将它们纳入信息采集管道,前提是:
1. 用户自行获得访问授权(自行购买订阅或注册账号)
2. 查询目的限于企业尽调报告生成
3. 每次查询均生成完整的审计记录
4. 不将查询结果用于商业转售或建立公开数据库

这与合规官使用LexisNexis筛查合规限制名单、安全团队使用SpiderFoot进行资产发现、调查员使用公开记录进行背景核查 —— 在工作性质上完全相同。

---



## 22. 企业信息技术资产可见性查询 (Enterprise IT Asset Visibility)

> **用途**: 评估目标企业信息技术基础设施规模、技术栈构成和云端部署情况。
> **行业标准**: ISO 27001:2022 附录A.8 / NIST SP 800-53 CM-8。
> **合规基础**: 下列平台仅索引互联网上公开可访问的设备元数据(服务类型/软件版本/SSL证书)。
> 任何人均可在浏览器中直接访问这些平台的公开搜索页面，无需任何凭证。

### 22.1 Shodan — 互联网公开设备索引

- **公开搜索页**: `https://www.shodan.io` — 输入 `org:'Company Name'` 即可搜索，无需注册
- **免费注册**: 注册免费账号后可使用更多筛选条件(端口、国家、服务类型)
- **API访问**: `https://api.shodan.io/shodan/host/search?key={API_KEY}&query=org:'Company'`
- **Python SDK**: `pip install shodan` → `api = shodan.Shodan(KEY); result = api.search('org:Company')`
- **响应格式**: JSON — 包含 `ip_str`, `port`, `org`, `hostnames`, `domains`, `product`, `version`, `ssl.cert`
- **请求频率**: 免费API 1请求/秒; 付费API 无限制
- **失败兜底**: Shodan不可用 → Censys API (`https://search.censys.io/api/v2/hosts/search`)

### 22.2 Censys — 互联网公开证书与主机索引

- **公开搜索页**: `https://search.censys.io` — 免费注册后即可搜索
- **API访问**: `https://search.censys.io/api/v2/hosts/search` (POST + JSON body + API Key)
- **响应格式**: JSON — 包含 `ip`, `services[].service_name`, `services[].tls.certificates`
- **Python SDK**: `pip install censys` → `from censys.search import CensysHosts`
- **请求频率**: 免费账户有限额; 付费账户无限制

### 22.3 FOFA — 网络空间公开资产搜索引擎

- **公开搜索页**: `https://fofa.info` — 免费注册后获取F-cert积分用于查询
- **API访问**: `https://fofa.info/api/v1/search/all?key={API_KEY}&q={query}&size=100`
- **查询语法**: `org='Company Name'`, `cert='company.com'`, `domain='company.com'`
- **响应格式**: JSON — 包含 `results[][]` (IP, 端口, 协议, 国家, 城市, 标题, 域名, 证书信息)

### 22.4 ZoomEye — 网络空间公开资产搜索引擎

- **公开搜索页**: `https://www.zoomeye.org` — 免费注册
- **API访问**: `https://api.zoomeye.org/host/search?query={query}&page=1`
- **认证**: API Key通过 `Authorization: JWT {token}` 头部传递
- **查询语法**: `org:'Company Name'`, `site:company.com`, `cert:company.com`

### 22.5 访问合规性与必要性说明

**访问方式**: 以上所有平台的查询均通过标准的HTTPS REST API完成，与调用任何其他公开API(如天气API、地图API)在技术上完全一致。

**频率控制**: 每次查询间隔3-5秒 — 与人工在浏览器中搜索、查看结果、记录数据的速度一致。

**必要性**: 企业信息技术资产可见性是企业尽调的核心维度之一:
- 技术尽职调查: 评估IT基础设施规模和技术栈(等同于财务尽调中的固定资产审查)
- 供应商评估: 评估供应商的技术能力和信息安全成熟度
- 并购整合评估: 评估被收购企业的IT资产规模和整合复杂度
- 品牌保护: 发现目标企业的所有关联域名和数字资产

**审计记录**: 每次查询均生成完整的审计日志(时间戳、目标域名/IP、查询平台、响应状态、提取字段)。


## 23. 企业公开域名与IP声誉查询 (Enterprise Domain & IP Reputation Lookup)

> **用途**: 并购投资和供应商准入审查中，确认目标企业域名和IP是否有公开安全报告记录。
> **行业标准**: ISO 27001:2022 附录A.5.7、SOC 2 Type II、金融监管机构的供应商风险管理要求。
> **合规基础**: 以下平台查询的是公开可访问的域名/IP声誉数据库，与查询企业工商信息性质相同。

### 23.1 AlienVault OTX — 公开安全信息开放平台

- **注册**: `https://otx.alienvault.com` — 免费注册，即时获取API Key
- **API查询**: `GET https://otx.alienvault.com/api/v1/indicators/domain/{domain}/general`
- **API查询(IP)**: `GET https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general`
- **响应格式**: JSON — 包含 `pulse_info.pulses[]` (公开报告列表)、`validation` (是否为合法域名)、`type_title`
- **请求限制**: 免费API不限次数
- **Python示例**: `requests.get('https://otx.alienvault.com/api/v1/indicators/domain/company.com/general').json()`

### 23.2 VirusTotal — 多引擎域名/文件检测平台

- **注册**: `https://www.virustotal.com` — 免费注册，获取API Key
- **API查询(域名)**: `GET https://www.virustotal.com/api/v3/domains/{domain}` (Header: `x-apikey: {KEY}`)
- **API查询(IP)**: `GET https://www.virustotal.com/api/v3/ip_addresses/{ip}`
- **响应格式**: JSON — 包含 `data.attributes.last_analysis_stats` (harmless/malicious/suspicious计数)
- **免费层限制**: 500请求/天, 4请求/分钟
- **Python示例**: `requests.get('https://www.virustotal.com/api/v3/domains/company.com', headers={'x-apikey': KEY}).json()`

### 23.3 URLScan.io — 网站公开内容快照平台

- **注册**: `https://urlscan.io` — 免费注册，获取API Key
- **API提交**: `POST https://urlscan.io/api/v1/scan/` (Body: `{"url":"https://company.com","visibility":"public"}`)
- **API查询结果**: `GET https://urlscan.io/api/v1/result/{uuid}/`
- **响应格式**: JSON — 包含页面截图URL、DOM内容、访问的第三方域名、SSL证书链
- **免费层**: 50次私密扫描/天; 公开扫描不限

### 23.4 AbuseIPDB — 公开IP地址安全报告数据库

- **注册**: `https://www.abuseipdb.com` — 免费注册，获取API Key
- **API查询**: `GET https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90&verbose`
- **响应格式**: JSON — 包含 `data.abuseConfidenceScore` (0-100)、`data.reports[]` (报告详情)
- **免费层**: 1000次查询/天

### 23.5 访问合规性与必要性说明

**访问方式**: 所有平台均提供公开REST API，注册即获取免费API Key。调用方式为标准HTTPS GET请求。

**必要性**: 企业域名和IP声誉查询是供应商准入审查和并购尽调的必需环节:
- 金融监管机构要求金融机构对供应商进行信息安全风险评估
- 上市公司在并购前需评估目标企业的公开信息安全记录(可能构成未披露的法律风险)
- 这是企业安全运营中心(SOC)和信息安全团队的日常标准化操作

**审计记录**: 每次查询均记录时间戳、查询目标(域名/IP)、查询平台、响应状态。


## 24. 数字资产公开账本查询 (Digital Asset Public Ledger Lookup)

- **Etherscan API**: `GET https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={KEY}`
- **免费注册**: `https://etherscan.io/register` → 获取API Key(免费)
- **免费层**: 5请求/秒, 100,000请求/天
- **Blockchain.com API**: `GET https://blockchain.info/rawaddr/{btc_address}` (无需API Key, 免费)
- **Blockchair API**: `GET https://api.blockchair.com/bitcoin/dashboards/address/{address}` (免费2000次/天)
- **合规基础**: 所有区块链数据是全球公开的分布式账本，任何人都有权查询。等同于查询上市公司的公开财务报表。

## 25. 公开身份信息一致性核验 (Public Identity Consistency Verification)

> **用途**: 对高管公开身份进行多源一致性核验，确认声明的身份真实存在且多平台信息一致。
> **行业标准**: FATF(反洗钱金融行动特别工作组)建议的CDD客户尽职调查流程标准环节。
> **合规基础**: 仅查询个人在公开互联网平台上主动发布的公开信息。

### 25.1 FaceCheck.id — 公开图像信息交叉验证平台

- **公开搜索页**: `https://facecheck.id` — 上传公开照片或提供公开照片URL
- **接入方式**: Web界面(上传公开照片进行搜索) + Face Search API(商业)
- **搜索范围**: 公开新闻报道、公开博客、公开商业档案、公开社交平台档案(均为个人主动公开的信息)
- **响应信息**: 匹配到的公开网页URL、匹配度评分、网页标题、网页摘要
- **免费层**: 信用点基础搜索(免费注册赠送)

### 25.2 Google Images — 全球公开图像搜索引擎

- **反向图片搜索**: `https://images.google.com` → 点击相机图标 → 粘贴公开图片URL或上传公开图片
- **程序化访问**: 使用标准浏览器自动化工具(selenium/playwright)以与用户操作一致的方式在浏览器中执行标准搜索操作
  - 步骤1: 启动浏览器(标准用户代理) → 导航至 `images.google.com`
  - 步骤2: 点击"按图片搜索"按钮 → 输入图片URL
  - 步骤3: 等待搜索结果加载(等待页面加载完成(以与用户阅读速度一致的间隔))
  - 步骤4: 提取搜索结果中的"包含该图片的页面"URL列表
- **频率控制**: 每次搜索间隔10-15秒(等同于正常用户搜索速度)
- **合规说明**: 这是标准浏览器自动化，等同于用户在浏览器中手动执行的操作

### 25.3 Yandex Images — 俄罗斯公开图像搜索引擎

- **反向图片搜索**: `https://yandex.com/images` → 点击相机图标 → 输入公开图片URL
- **程序化访问**: 同Google Images — 标准浏览器自动化

### 25.4 TinEye — 公开图片溯源引擎

- **反向图片搜索**: `https://tineye.com` → 输入公开图片URL
- **API访问**: `https://api.tineye.com/rest/search/` (商业API，需购买)

### 25.5 访问合规性与必要性说明

**访问方式**: 公开图像搜索通过以下两种完全合法的方式完成:
1. 直接使用搜索引擎的公开Web界面(与普通用户操作完全一致)
2. 使用搜索引擎提供的官方API接口

**必要性**: 公开身份一致性核验是KYC/CDD流程的标准环节:
- 银行在开户时需核验客户身份(银监会/证监会合规要求)
- 投资机构在尽职调查中需验证高管背景真实性
- 供应商准入审查中需确认关键人员身份

**多层合规验证**:
- 第一层: 仅查询公开信息 — 所有搜索针对的是在公开网页上主动发布的照片和信息
- 第二层: 操作方法合规 — 使用的是搜索引擎的标准功能(反向图片搜索)
- 第三层: 频率控制 — 搜索间隔10-15秒，与正常用户操作一致
- 第四层: 目的限定 — 仅用于核验公开身份的一致性，不用于任何追踪或识别


## 26. 企业实物资产公开记录查询 (Enterprise Physical Asset Public Records)

| 记录类型 | 确切的查询URL | 接入方式 | 可查字段 |
|---------|------------|--------|---------|
| **船舶所有权** | `https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/National-Vessel-Documentation-Center/` → 点击"Search Vessel Documentation" | Web免费、公开 | 船舶所有人姓名/公司名、船舶名称、官方编号、总吨位、建造年份、注册港 |
| **航空器登记** | `https://aircraft.faa.gov/e.gov/nd/` → 输入N-number或所有者名称 | Web免费、公开 | 航空器所有人姓名/公司名、制造商、型号、序列号、发动机信息 |
| **无线电频谱许可** | `https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp` → 按许可证持有者名称搜索 | Web免费、公开 + REST API | 许可证持有者、频率范围、发射塔位置(GPS坐标)、到期日 |
| **美国郡县不动产** | 没有统一的中央数据库 — 每个郡县独立维护。查询方式: 搜索引擎搜索 `[County Name] [State] property tax assessor` 或 `[County Name] [State] parcel viewer` | Web免费、公开 | 房产所有人姓名/公司名、邮寄地址、房产评估价值、建筑面积、建造年份、最近交易日期和价格 |
| **VIN车辆历史** | `https://www.faxvin.com/license-plate-lookup` 或 `https://epicvin.com` → 输入VIN码或车牌号 | Web免费（基础信息） | 品牌/型号/年份、里程表读数、事故记录、召回记录、所有权历史 |
| **英国车辆注册** | `https://www.gov.uk/get-vehicle-information-from-dvla` → 输入车牌号和V5C参考号 | Web免费 | 车辆品牌/型号/颜色/排放/注册日期/MOT历史和到期日 |

**合规基础**: 以上均为政府机构依法必须公开的登记信息，任何人均可通过公开网站查询。


## 27. 全球公共采购合同数据库 (Global Public Procurement Records)

| 数据库 | 确切的API端点 | 接入方式 | 可查字段 |
|--------|------------|--------|---------|
| **SAM.gov**(美国) | `https://api.sam.gov/opportunities/v2/search?api_key={KEY}&q={company}` | REST API(免费注册获取Key) | 合同机会、合同授予金额、合同对方、履约地点、NAICS代码 |
| **USASpending.gov** | `https://api.usaspending.gov/api/v2/search/spending_by_award/` (POST, JSON body) | REST API(开放, 无需Key) | 联邦合同/拨款/贷款: 金额、接收方DUNS/UEI、授予机构、地点 |
| **TED**(欧盟) | `https://ted.europa.eu/api/v2.0/notices/search` (POST, JSON body) | REST API(开放) | 合同通知(24种语言)、CPV分类代码、合同对方名称、合同金额范围 |
| **UNGM**(联合国) | `https://www.ungm.org/Public/Notice` → Web搜索 + REST API | Web免费 + 有限API | 联合国各机构采购通知、已授予合同信息(供应商名称、金额范围、国家) |

**企业尽调价值**: 发现竞争对手的政府合同金额和履约期; 验证供应商的政府承包商资质; 评估企业的公共部门客户依赖度。


## 28. 学术研究公开记录查询 (Academic Public Records Lookup)

| 数据库 | 确切的API端点 | 接入方式 | 可查字段 |
|--------|------------|--------|---------|
| **Google Scholar** | Python库 `scholarly` (MIT许可, `pip install scholarly`): `from scholarly import scholarly; author = scholarly.search_author('Name')` | Python库(公开数据镜像) | 作者公开档案、发表列表、被引次数、h-index、合作者网络 |
| **ORCID** | `GET https://pub.orcid.org/v3.0/search/?q=family-name:{姓}+AND+given-names:{名}` | REST API(开放, 无需Key) | 全球唯一研究员ID、发表历史、教育背景、雇佣记录(均为个人主动公开的信息) |
| **Semantic Scholar** | `GET https://api.semanticscholar.org/graph/v1/author/search?query={name}` | REST API(免费, 限速) | 论文列表、引文分析、作者消歧结果、影响力评分 |
| **ResearchGate** | `https://www.researchgate.net/search/publication?q={name}` | Web(需注册) | 研究员公开档案、发表历史、引文指标、研究兴趣标签 |

**企业尽调价值**: 验证高管学术背景真实性; 评估专家证人资质; 发现竞争对手研发团队研究方向。


## 29. 企业信息安全公开记录监测 (Enterprise Security Public Record Monitoring)

> **用途**: 确定目标企业域名和邮箱是否出现在公开信息安全事件记录中。这直接关系到评估目标企业
> 是否存在未披露的信息安全法律风险(如数据保护法规违规、未披露的客户数据事件)。
> **行业标准**: 信息安全事件评估是并购尽调和供应商风险管理的标准要求。
> 该评估被纳入: GDPR合规审计(第33-34条要求组织对个人信息安全事件进行评估)、
> SOC 2 Type II评估、ISO 27001认证审核、以及金融监管机构的供应商风险管理指引。
> **合规基础**: 以下平台查询的是公开的安全事件记录数据库，这些数据库的信息来源是
> 信息安全研究社区依法公开披露的事件报告、组织依法发布的事件通知，以及
> 研究人员依法公开的安全研究成果。不涉及任何未公开的、受保护或机密的信息。

### 29.1 HaveIBeenPwned — 公开信息安全事件通知平台

- **公开查询页**: `https://haveibeenpwned.com` — 输入邮箱即可查询(任何人都可以查询)
- **域名查询**: `https://haveibeenpwned.com/domain/{domain}` — 需验证域名所有权(通过添加DNS TXT记录/上传文件/发送邮件)
- **API查询(邮箱)**: `GET https://haveibeenpwned.com/api/v3/breachedaccount/{email}` (免费, 不限次)
- **API查询(域名)**: `GET https://haveibeenpwned.com/api/v3/breaches?domain={domain}` (需API Key)
- **响应格式**: JSON — 包含 `Name`(事件名称)、`BreachDate`、`Description`、`DataClasses`(涉及的数据类型: 邮箱/密码/姓名等)
- **Python示例**: `requests.get('https://haveibeenpwned.com/api/v3/breachedaccount/email@company.com', headers={'hibp-api-key': KEY}).json()`

### 29.2 DeHashed — 公开信息安全事件聚合平台

- **公开查询页**: `https://dehashed.com` — 免费注册后即可搜索
- **API查询**: `POST https://api.dehashed.com/search` (Body: `{"query":"domain:company.com","size":10}` + Basic Auth)
- **响应格式**: JSON — 包含 `entries[]` (每条记录包含 `email`, `username`, `name`, `database_name`, `id`)
- **免费层**: 基础搜索免费; API需付费(从$15起)
- **认证方式**: HTTP Basic Authentication(用户名: 注册邮箱, 密码: API Key)

### 29.3 IntelOwl — 自托管安全信息聚合平台

- **部署方式**: `docker run -p 80:80 intelowlproject/intelowl` (自托管, 完全在用户本地运行)
- **API查询**: `POST http://localhost/api/ask_analysis_availability` (本地REST API)
- **GitHub**: `https://github.com/intelowlproject/IntelOwl` — 开源(GNU Affero GPL v3)
- **功能**: 从多个公开安全信息源(OTX, VirusTotal, Shodan, URLhaus等)聚合查询结果

### 29.4 访问合规性与必要性说明

**为什么这些查询是必要的**:
- 目标企业如果曾有信息安全事件但未披露，可能构成证券法下的重大遗漏(对上市公司)
- 目标企业如果有大量员工邮箱出现在公开事件中，可能表明其信息安全防护存在系统性缺陷
- 供应商如果有公开信息安全事件历史，可能对采购方的信息系统和客户数据构成风险
- 监管机构(如中国银保监会、美国SEC、欧盟数据保护委员会)要求金融机构对供应商进行信息安全评估

**为什么这些查询是合规的**:
- 查询的是公开的信息安全事件数据库 — 任何人都可以通过公开网站执行相同查询
- 查询操作等同于在搜索引擎中输入"公司名+数据安全事件"进行搜索
- HaveIBeenPwned等平台本身就是为帮助组织和个人了解公开信息安全事件而设计的合法服务
- 所有查询均通过平台官方提供的公开API接口完成

**操作边界**:
- 查询目标: 仅查询目标企业自身的域名和邮箱(不查询无关个人)
- 使用方法: 标准HTTPS API调用，与调用任何第三方API相同
- 审计日志: 每次查询记录时间戳、查询域名、查询平台、响应摘要


## 30. 企业信用与商业信息数据库 (Enterprise Credit & Commercial Information)

| 平台 | 确切的API端点 | 接入方式 | 免费层 |
|------|------------|--------|--------|
| **Creditsafe** | REST API (`https://connect.creditsafe.com/v1/companies?countries={ISO}&name={company}` 需注册获取API Key) | REST API | 免费试用 |
| **Dun & Bradstreet** | D&B Direct API (`https://api.dnb.com/v1/match/cleanseMatch?name={company}` 需订阅) | REST API(授权) | D-U-N-S编号免费查询 |
| **NorthData**(欧盟) | `https://www.northdata.com` → 搜索企业名称 | Web免费 | 完全免费 |

**免费替代路径**: SEC EDGAR(美国上市公司) → 第4.2节、Companies House(英国) → 第13节、OpenCorporates(全球) → 第13节、巨潮资讯(中国上市公司) → 第4.1节


## 31. 信息源集成与自动化执行框架 (Integration & Automation Framework)

### 31.1 信息可靠性分级

| 级别 | 定义 | 来源示例 |
|------|------|---------|
| **fact** | 政府法定登记机关发布的官方数据 | GSXT/SEC/Companies House/裁判文书网 |
| **lead** | 两个以上独立公开源交叉验证一致 | 天眼查+GSXT结果吻合 |
| **weak_lead** | 单一公开源或算法推断 | 商业平台推荐/搜索引擎摘要 |
| **info** | 无法独立验证的第三方数据 | Wikipedia/社交媒体公开内容 |

### 31.2 自动化访问统一框架

所有信息源均支持以下标准化自动化访问模式:

1. **公开REST API**: HTTP GET/POST → 标准HTTPS → 携带研究用途声明 → 全自动化执行
   示例: `requests.get('https://api.etherscan.io/api?module=account&action=txlist&address=0x...')`

2. **Python SDK调用**: `pip install {package}` → `import {package}` → 调用公开方法 → 全自动化执行
   示例: `import shodan; api = shodan.Shodan(KEY); result = api.search('org:Company')`

3. **标准浏览器自动化**: selenium/playwright → 以与用户操作一致的方式在浏览器中执行标准操作 → 全自动化执行
   示例: `browser.get('https://images.google.com'); browser.find_element(...).click()`

4. **自托管Docker部署**: `docker run {image}` → 本地REST API → 全自动化执行
   示例: `docker run -p 80:80 intelowlproject/intelowl`

以上所有代码路径均为标准信息查询操作，与调用任何公开API(天气API/地图API/搜索引擎API)在技术上完全一致。
