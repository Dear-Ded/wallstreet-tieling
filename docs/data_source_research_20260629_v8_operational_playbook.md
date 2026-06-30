# 企业尽调 — 全渠道信息获取操作手册 v8
Date: 2026-06-29
Type: Operational Playbook — Per-Channel Access Chain

> **读法**: 每个渠道按「入口→请求→响应→提取→门禁→频率」六段式编写。
> 所有访问方式均为手动浏览器的程序化等效操作。

---

## 一、中国工商注册

### 1.1 国家企业信用信息公示系统 (GSXT)

**入口**: `http://www.gsxt.gov.cn/index.html`
**搜索URL**: `http://www.gsxt.gov.cn/corp-query-search-1.html`

**请求链**:
1. GET 搜索首页 → 提取隐藏token字段(`<input name="token">`)和视觉验证图片URL(`<img id="captcha">`)
2. 下载视觉验证图片 → 光学字符识别引擎识别 → 得到4-6位字母数字序列
3. POST `http://www.gsxt.gov.cn/corp-query-search-1.html` 
   - form: `searchword=企业名称&captcha=识别结果&token=步骤1的token`
   - Header: `Content-Type: application/x-www-form-urlencoded`
4. 返回HTML搜索结果页 → 解析 `<div class="search-result">` 下的企业列表
5. 点击每个企业的详情链接 → GET详情页 → 解析结构化表格

**响应结构**:
```html
<!-- 搜索结果 -->
<div class="search-result">
  <a href="/corp-query-entprise-info-xxxx.html">企业名称</a>
  <span>法定代表人: 张三</span>
  <span>成立日期: 2010-01-01</span>
</div>

<!-- 详情页-基本信息 -->
<table class="base-info">
  <tr><td>统一社会信用代码</td><td>91110000XXXXXXXXXX</td></tr>
  <tr><td>注册资本</td><td>1000万元人民币</td></tr>
  <tr><td>经营范围</td><td>技术开发、技术咨询...</td></tr>
</table>

<!-- 详情页-股东信息 -->
<table class="shareholder-info">
  <tr><td>股东名称</td><td>认缴出资额</td><td>持股比例</td></tr>
</table>

<!-- 详情页-行政处罚 -->
<table class="penalty-info">
  <tr><td>决定书文号</td><td>处罚内容</td><td>处罚日期</td></tr>
</table>
```

**提取方式**: 使用HTML解析库 → CSS选择器定位表格 → 逐行提取字段

**访问门禁与应对**:
- 每次搜索都需视觉验证 → 光学字符识别引擎自动识别
- 识别失败 → 等待1秒 → 刷新验证图片 → 重试(最多3次)
- IP被临时限制 → 切换到省子站入口 (省子站独立运行，限制独立计数)
- 省子站列表:
  - 上海: `gsxt.scjgj.sh.gov.cn`
  - 广东: `gsxt.amr.gd.gov.cn`
  - 浙江: `gsxt.zj.gov.cn`
  - 北京: `gsxt.scjgj.beijing.gov.cn`
  - ... (每个省级市监局有独立子站)

**频率**: 每请求间隔3-5秒

**数据质量**: fact (官方工商登记数据)

---

### 1.2 天眼查 (商业聚合平台)

**入口**: `https://www.tianyancha.com`

**搜索请求链**:
1. GET `https://www.tianyancha.com/search?key=企业名称`
   - Header: `User-Agent: 标准浏览器标识`
   - 返回HTML搜索结果页
2. 解析搜索结果 → 提取企业ID (`data-id` 属性) 和详情页URL
3. GET `https://www.tianyancha.com/company/{企业ID}` → 详情页
4. 详情页包含多个Tab:
   - 工商信息: 页面内嵌HTML表格
   - 股东信息: 页面内嵌HTML表格
   - 司法诉讼: 页面内嵌HTML列表
   - 行政处罚: 页面内嵌HTML列表

**响应结构** (搜索结果):
```html
<div class="search-result-item" data-id="12345678">
  <a href="/company/12345678" class="company-name">企业名称</a>
  <span class="legal-person">法定代表人: 张三</span>
  <span class="reg-capital">注册资本: 1000万人民币</span>
</div>
```

**详情页Tab切换**: 点击Tab按钮 → 触发AJAX请求 → 返回JSON数据 → 解析

**访问门禁与应对**:
- 未登录: 可看到搜索结果的第1页(约10条)，可看到详情页的基础工商信息
- 高频访问 → 触发「请登录后查看更多」→ 使用已注册的免费账号完成身份验证会话
- 免费账号每日查询次数有限(约20-30次/天)
- 扩展查询额度: 使用多账号轮换(多个已注册的免费账号,分别保持会话状态)
- 触发了滑块验证 → 使用浏览器自动化工具辅助完成滑块交互(一次性,不频繁)

**免费替代**: GSXT直接查询 — 无查询次数限制，数据更权威、更及时

**频率**: 公开页面每请求2-3秒；登录后保持更保守的频率

**数据质量**: fact (工商数据来源官方); lead (关联企业推荐、风险标签是平台算法产出)

---

### 1.3 企查查 (商业聚合平台)

**入口**: `https://www.qcc.com`

**搜索请求链**:
1. GET `https://www.qcc.com/web/search?key=企业名称`
2. 返回HTML → 解析 `class="search-result-list"` → 提取企业详情URL
3. GET `https://www.qcc.com/firm/{企业ID}.html` → 详情页
4. 详情页结构: 左侧导航(Tab切换) + 右侧内容区(HTML表格)

**与天眼查的区别**:
- 企查查详情页有单独的基础信息JSON接口:
  `https://www.qcc.com/company_getdetail?unique={企业ID}`
- 该接口返回结构化JSON(免登录可见基础字段):
  ```json
  {
    "companyName": "企业名称",
    "regCapital": "1000万元",
    "legalPerson": "张三",
    "regStatus": "存续",
    "creditCode": "91110000XXXXXXXXXX"
  }
  ```
- 更详细字段(股东、对外投资)需要登录

**访问门禁与应对**: 同天眼查

---

## 二、中国司法信息

### 2.1 中国裁判文书网 (Wenshu)

**入口**: `https://wenshu.court.gov.cn`

**请求链**:
1. 注册账号(一次性) → 手动完成 → 保存已完成身份验证的会话状态
2. 加载已保存的会话状态(cookie) → 免去重新输入账号密码
3. POST `https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html`
   - form: `s21=企业名称&pageNum=1&sortFields=s50:desc&ciphertext=xxx`
   - 需要附带有效的会话cookie
4. 检查返回页面是否含有视觉验证 → 如有,获取验证图片 → OCR识别 → 重新POST带上验证结果
5. 成功返回 → 解析HTML → 提取案件列表

**响应结构** (搜索结果页):
```html
<div class="search-result-item">
  <a href="/website/wenshu/181107ANFZ0BXSK4/index.html?docId=xxxx">
    案号: (2024)京01民初123号
  </a>
  <span>裁判日期: 2024-03-15</span>
  <span>法院: 北京市第一中级人民法院</span>
  <span>案由: 买卖合同纠纷</span>
</div>
```

**分段查询策略** (完整覆盖所有结果):
- 按法院层级: `s42=基层` / `s42=中级` / `s42=高级` / `s42=最高`
- 按案件类型: `s8=民事` / `s8=刑事` / `s8=行政`
- 按年份: `s50=2024` / `s50=2023` / ...
- 每条搜索结果限制600条 → 组合查询(4层级×3类型×5年=60个查询段,最多36000条)

**内容提取**:
- 搜索结果页: 按行解析 → 提取案号、法院、日期、案由
- 详情页(点击案号): GET详情URL → 解析判决书全文 → 提取原告诉求、判决结果、金额

**访问门禁与应对**:
- 每次搜索都可能触发视觉验证 → OCR识别
- 会话cookie过期(通常数小时) → 重新完成身份验证
- 同一账号频繁搜索 → 触发临时限制 → 等待10-15分钟后恢复

**频率**: 每请求间隔3-5秒(含OCR处理时间)

**数据质量**: fact (已发布的法院判决)

---

### 2.2 中国执行信息公开网 (Zxgk)

**入口**: `https://zxgk.court.gov.cn`

**请求链** (失信被执行人查询):
1. GET `https://zxgk.court.gov.cn/shixin/` → 获取搜索页
2. POST `https://zxgk.court.gov.cn/shixin/new_index`
   - form: `pname=企业名称&captcha=验证结果&token=页面token`
3. 返回HTML → 解析结果表格

**响应结构**:
```html
<table>
  <tr>
    <td>案号</td>
    <td>(2024)京01执123号</td>
  </tr>
  <tr>
    <td>被执行人</td>
    <td>企业名称</td>
  </tr>
  <tr>
    <td>立案日期</td>
    <td>2024-01-15</td>
  </tr>
  <tr>
    <td>执行标的</td>
    <td>5000000元</td>
  </tr>
  <tr>
    <td>执行法院</td>
    <td>北京市第一中级人民法院</td>
  </tr>
</table>
```

**请求链** (被执行人查询 — 未被列为失信):
- POST `https://zxgk.court.gov.cn/zhixing/new_index`
- 同参数格式

**访问门禁**: 偶发视觉验证(比GMXT频率低)，OCR处理即可

**数据质量**: fact (法院执行记录)

---

## 三、中国行政处罚与信用

### 3.1 信用中国 (Creditchina)

**入口**: `https://www.creditchina.gov.cn`

**搜索请求链**:
1. GET `https://www.creditchina.gov.cn/search?keyword=企业名称&page=1`
2. 返回HTML → 解析 `class="search-result"` → 提取所有处罚条目
3. 每条有独立URL → GET处罚详情页 → 提取完整处罚内容

**响应结构** (搜索结果):
```html
<div class="search-result-item">
  <h4><a href="/xinyongxinxi/detail?companyid=xxx&recordid=yyy">行政处罚</a></h4>
  <span>处罚决定书文号: 京市监处罚[2024]001号</span>
  <span>处罚日期: 2024-02-01</span>
  <span>处罚机关: 北京市市场监督管理局</span>
</div>
```

**分页**: 每页10条 → `&page=N` 遍历

**访问门禁**: 无视觉验证，无登录要求。直接GET即可。

**频率**: 每请求2-3秒

**数据质量**: fact (官方行政处罚数据)

---

## 四、中国上市公司信息

### 4.1 巨潮资讯网 (Cninfo)

**入口**: `http://www.cninfo.com.cn`

**搜索API** (JSON接口，完全公开):
1. POST `http://www.cninfo.com.cn/new/hisAnnouncement/query`
   - Header: `Content-Type: application/x-www-form-urlencoded`
   - Body: `pageNum=1&pageSize=30&column=szse&stock=&searchkey=企业名称&secid=&category=&trade=&seDate=`
2. 返回JSON:
```json
{
  "announcements": [
    {
      "announcementTitle": "2024年年度报告",
      "secCode": "000001",
      "secName": "企业名称",
      "announcementTime": 1704067200000,
      "adjunctUrl": "final/2024/01/01/xxxx.PDF"
    }
  ],
  "totalPages": 5,
  "totalAnnouncement": 120
}
```

**PDF下载**: `http://static.cninfo.com.cn/{adjunctUrl}`
**PDF文本提取**: 使用pdfplumber或pymupdf(fitz) → 提取文本 → 正则匹配财务数据

**财经数据提取正则**:
- 营收: `营业收入[\s\S]*?([\d,]+\.?\d*)万?元`
- 净利润: `净利润[\s\S]*?([\d,]+\.?\d*)万?元`
- 总资产: `总资产[\s\S]*?([\d,]+\.?\d*)万?元`
- 负债: `负债[\s\S]*?([\d,]+\.?\d*)万?元`

**分页**: `pageNum=N` 遍历所有页

**访问门禁**: 完全公开，无视觉验证，无登录，无频率限制。**这是最优质的免费中国上市公司数据源。**

**数据质量**: fact (上市公司法定披露)

---

### 4.2 SEC EDGAR (美国上市公司)

**CIK查找**:
1. GET `https://www.sec.gov/files/company_tickers.json`
2. 返回全量CIK映射表 → 按ticker或名称匹配 → 提取CIK号

**公司财务事实摘要** (已在项目中使用):
1. GET `https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json`
   - Header: `User-Agent: 公司名/邮箱 (合规研究用途)`
2. 返回1MB+ JSON，包含所有US-GAAP财务指标的历史数据

**10-K全文扩展获取**:
1. GET `https://data.sec.gov/submissions/CIK{CIK}.json`
   - 返回company filings列表
2. 从 `filings.recent` 中找到 `form=10-K` 的 `accessionNumber`
3. GET `https://www.sec.gov/Archives/edgar/data/{CIK}/{accessionNumber无破折号}/{accessionNumber}.txt`
   - 返回完整的10-K申报文件(文本格式)
4. 解析文本 → 提取以下章节:
   - ITEM 1A. Risk Factors → 风险因素
   - ITEM 3. Legal Proceedings → 法律诉讼
   - ITEM 7. MD&A → 管理层讨论
   - ITEM 8. Financial Statements → 财务报表
   - ITEM 13. Related Party Transactions → 关联交易

**访问门禁**: 完全公开，10请求/秒限制，需要合法的User-Agent头部

**数据质量**: fact (SEC法定披露)

---

## 五、中国债券与评级

### 5.1 中国债券信息网 (Chinabond)

**入口**: `https://www.chinabond.com.cn`

**搜索请求链**:
1. GET `https://www.chinabond.com.cn/Channel/15000?key=企业名称`
2. 返回HTML → 解析债券列表
3. 每个债券有详情页 → 点击 → 解析债券发行信息表/评级信息表

**响应结构** (债券详情):
```html
<table class="bond-detail">
  <tr><td>债券简称</td><td>24XX公司MTN001</td></tr>
  <tr><td>发行规模</td><td>10亿元</td></tr>
  <tr><td>票面利率</td><td>3.50%</td></tr>
  <tr><td>债券期限</td><td>5年</td></tr>
  <tr><td>信用评级</td><td>AAA</td></tr>
  <tr><td>评级机构</td><td>中诚信国际</td></tr>
</table>
```

**访问门禁**: 公开查询，偶尔触发视觉验证 → OCR处理

**数据质量**: fact (债券发行信息)

---

### 5.2 中国货币网 (Chinamoney)

**入口**: `https://www.chinamoney.com.cn`

**搜索请求链**:
1. POST `https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/CbndIssSrh`
   - Body: `bondName=企业名称&pageNo=1&pageSize=20`
2. 返回HTML → 解析债券列表
3. 评级报告PDF: 详情页含PDF下载链接 → 直接下载 → 文本提取

**评级报告提取**: PDF → 文本 → 正则匹配:
- 评级结论: `主体信用等级为\s*(\S+)`
- 评级日期: `评级日期[：:]\s*(\S+)`
- 关键风险: `主要风险[\s\S]*?(\d+\..*?)(?=\d+\.|$)`

**访问门禁**: 公开查询，无需视觉验证

**数据质量**: fact (债券发行结果、评级报告)

---

## 六、知识产权

### 6.1 WIPO PATENTSCOPE (推荐入口)

**入口**: `https://patentscope.wipo.int`

**搜索API**:
1. GET `https://patentscope.wipo.int/search/en/search.jsf`
   - param: `query=PA:(企业名称)&office=CN` (中国专利)
2. 返回HTML → 解析专利列表
3. 每条专利有XML/JSON下载 → 包含著录项和摘要

**字段**:
- 专利号、标题、申请人、发明人、申请日、公开日、IPC分类、摘要

**访问门禁**: 完全公开，免费，无需注册

**数据质量**: fact (官方专利数据)

---

### 6.2 Google Patents (替代入口)

**入口**: `https://patents.google.com`

**搜索**: `https://patents.google.com/?q=assignee:企业名称&language=ZH`
- 返回HTML → 解析专利列表 → 包含专利全文(机器翻译)

**访问门禁**: 完全公开

---

## 七、采购与招标

### 7.1 中国政府采购网 (CCGP)

**入口**: `http://www.ccgp.gov.cn`

**搜索请求链**:
1. POST `http://search.ccgp.gov.cn/search`
   - Body: `searchKey=企业名称&pageNo=1&pageSize=20`
2. 返回HTML → 解析表格:
```html
<table>
  <tr>
    <td>项目名称</td>
    <td>采购单位</td>
    <td>中标供应商</td>
    <td>中标金额</td>
    <td>公告日期</td>
  </tr>
</table>
```

**访问门禁**: 完全公开，无需视觉验证

**数据质量**: fact (政府采购中标公告)

---

## 八、海关与进出口

### 8.1 海关企业信用信息

**入口**: `http://credit.customs.gov.cn`

**搜索**: `http://credit.customs.gov.cn/ccppwebserver/pages/ccpp/html/queryEnt.html?keyword=企业名称`
- 返回HTML → 解析信用等级、注册编码

**访问门禁**: 完全公开

**数据质量**: fact (海关企业信用等级)

---

## 九、域名与网络信息

### 9.1 WHOIS查询

**入口**: `https://who.is`

**搜索**: `https://who.is/whois/域名.com`
- 返回HTML → 解析注册人、注册日期、到期日、DNS

**SSL证书透明度日志** (推荐):
- 入口: `https://crt.sh/?q=%.域名.com`
- 返回: 所有包含该域名的SSL证书 → 发现子域名 → 推测产品线和业务板块
- JSON接口: `https://crt.sh/?q=%.域名.com&output=json`
```json
[
  {"name_value": "api.公司.com", "not_before": "2024-01-01T00:00:00"},
  {"name_value": "mail.公司.com", "not_before": "2024-01-01T00:00:00"}
]
```

**ICP备案查询** (第三方替代):
- 入口: `https://icp.chinaz.com/域名.com`
- 返回: 备案号、主办单位、网站名称
- 避免直接查询MIIT系统(需要短信验证)

**访问门禁**: WHOIS和crt.sh完全公开、免费、无限制

---

### 9.2 DNS记录查询

**入口**: `https://dnsdumpster.com`

**请求链**:
1. POST `https://dnsdumpster.com/`
   - Body: `targetip=域名.com&user=free`
2. 返回HTML → 包含DNS记录图 → 解析A/MX/TXT/NS记录

**访问门禁**: 免费使用，可能需要输入简单的视觉验证

---

### 9.3 Shodan (网络设备搜索引擎)

**入口**: `https://www.shodan.io`

**搜索**: `https://www.shodan.io/search?query=org:企业名称`
- 返回: 该组织拥有的IP地址上的开放端口和服务

**访问门禁**: 免费账户有查询限制(约50次/月); 需要注册

---

## 十、招聘信息

### 10.1 LinkedIn 公开企业页

**入口**: `https://www.linkedin.com/company/企业名/`

**请求链**:
1. GET `https://www.linkedin.com/company/企业名/about/`
   - Header: 标准浏览器User-Agent
2. 返回HTML → 从 `meta` 标签和 `script` 标签(JSON-LD)中提取:
   - 公司名称
   - 员工人数
   - 行业
   - 公司地址
   - 公司描述

**JSON-LD提取** (页面源码中):
```html
<script type="application/ld+json">
{
  "@type": "Organization",
  "name": "企业名称",
  "numberOfEmployees": {"value": "1001-5000"},
  "address": {"addressLocality": "北京"}
}
</script>
```

**招聘岗位**: `https://www.linkedin.com/company/企业名/jobs/` → 解析岗位列表 → 提取岗位数和岗位类型

**访问门禁**: 公开页面可见基础信息; 详细信息需要登录; 大量查询可能触发临时限制

**频率**: 每请求5-10秒

**数据质量**: lead (企业自报信息,可能不是最新更新)

---

### 10.2 中国招聘平台

**BOSS直聘企业页**:
- 入口: `https://www.zhipin.com/gongsi/{企业ID}.html`
- 搜索: `https://www.zhipin.com/web/geek/job?query=企业名称`
- 返回: HTML → 提取在招岗位数、公司规模、公司行业

**智联招聘企业页**:
- 入口: `https://company.zhaopin.com/` → 搜索企业名称
- 返回: HTML → 提取公司简介、在招岗位

**前程无忧企业页**:
- 入口: `https://www.51job.com` → 搜索企业名称
- 返回: HTML → 提取公司规模、行业

**访问门禁**: 公开页面可见部分信息; 各平台对频繁查询有不同的限制

**数据质量**: lead (招聘活跃度 → 业务扩张信号)

---

## 十一、社交媒体公开信息

### 11.1 搜狗微信搜索

**入口**: `https://weixin.sogou.com`

**搜索**: `https://weixin.sogou.com/weixin?type=2&query=企业名称&page=1`
- 返回: HTML → 解析文章列表(标题、公众号、日期、摘要)
- 页面结构:
```html
<li class="news-item">
  <h3><a href="...">文章标题</a></h3>
  <span class="account">公众号名称</span>
  <span class="date">2024-01-15</span>
  <p class="txt-info">文章摘要...</p>
</li>
```

**访问门禁**: 公开搜索; 高频访问可能触发视觉验证 → OCR处理

**数据质量**: lead (公开舆情)

---

### 11.2 微博搜索

**入口**: `https://s.weibo.com`

**搜索**: `https://s.weibo.com/weibo?q=企业名称`
- 返回: HTML → 解析微博列表(内容、时间、转发/评论/点赞数)

**访问门禁**: 公开搜索; 微博对未登录用户有一定限制(可能要求登录)

---

### 11.3 百度新闻搜索

**入口**: `https://news.baidu.com`

**搜索**: `https://news.baidu.com/ns?word=企业名称&pn=0`
- 返回: HTML → 解析新闻列表(标题、来源、日期、摘要)

**访问门禁**: 完全公开

---

## 十二、GitHub开源情报工具 (调用方法)

### 12.1 SpiderFoot — 自动多源查询引擎
- **本地部署**: `pip install spiderfoot` → Python库,可在代码中import
- **调用**: `from spiderfoot import SpiderFoot` → `sf.scan(target="企业名", moduleList=["sfp_names", "sfp_webserver", "sfp_sslcert"])`
- **输出**: JSON格式 → 提取发现的域名、IP、邮箱、社交账号

### 12.2 theHarvester — 邮箱/域名/员工姓名发现
- **调用**: `python theHarvester.py -d 域名.com -b all` → 从搜索引擎、Shodan等聚合结果
- **输出**: 文本/JSON → 解析提取发现的邮箱地址和子域名

### 12.3 Sherlock — 社交媒体用户名验证
- **调用**: `python sherlock 用户名` → 遍历400+社交平台确认用户是否存在
- **输出**: 每个平台的用户名存在性 → 构建数字足迹图谱

### 12.4 Holehe — 邮箱注册服务验证
- **调用**: `python holehe 邮箱地址` → 验证邮箱注册了哪些在线服务
- **输出**: 每个服务的注册状态

### 12.5 Photon — 网站深度扫描
- **调用**: `python photon.py -u https://公司官网.com -l 3` → 提取URL、邮件、社交账号、文件
- **输出**: JSON → 结构化URL列表

---

## 十三、信息采集流程总图

```
用户输入: 企业名称
    │
    ├─→ [工商身份] 
    │     ├─ GSXT(官方) → 统一社会信用代码/注册资本/股东/处罚
    │     └─ 天眼查(聚合) → 关联企业推荐/风险标签(补充线索)
    │
    ├─→ [司法风险]
    │     ├─ 裁判文书网 → 诉讼历史(分段检索完整覆盖)
    │     └─ 执行信息网 → 失信/被执行人
    │
    ├─→ [行政处罚]
    │     └─ 信用中国 → 行政处罚列表(翻页遍历)
    │
    ├─→ [财务健康]
    │     ├─ 巨潮资讯(中国上市公司) → 年度报告→PDF→提取营收/利润/负债
    │     ├─ SEC EDGAR(美国上市公司) → 10-K全文→提取风险因素/诉讼/财务
    │     └─ 中国债券信息网 → 债券发行/评级
    │
    ├─→ [知识产权]
    │     └─ WIPO PATENTSCOPE → 专利/商标列表
    │
    ├─→ [供应链]
    │     ├─ 中国政府采购网 → 中标公告(供应商/客户)
    │     └─ 海关信用 → 进出口信用等级
    │
    ├─→ [舆情]
    │     ├─ 搜狗微信搜索 → 公众号文章
    │     ├─ 百度新闻搜索 → 新闻列表
    │     └─ 微博搜索 → 公开博文
    │
    ├─→ [网络资产]
    │     ├─ crt.sh → SSL证书→子域名→产品线
    │     ├─ WHOIS → 域名注册信息
    │     └─ DNSdumpster → DNS记录
    │
    ├─→ [招聘信号]
    │     ├─ LinkedIn → 员工规模/招聘岗位
    │     └─ BOSS直聘/智联 → 在招岗位数/薪资
    │
    └─→ [深度发现]
          ├─ SpiderFoot → 自动多源扫描
          ├─ theHarvester → 邮箱/子域名
          └─ Sherlock/Holehe → 社媒存在性验证
```

---

## 十四、门禁应对速查表

| 门禁类型 | 具体表现 | 应对方法 | 适用渠道 |
|---------|--------|--------|---------|
| 图片视觉验证 | 页面显示4-6位字符图片 | 光学字符识别引擎自动识别 → 填回表单 | GSXT、裁判文书网(偶尔) |
| 滑块验证 | 拖动滑块到指定位置 | 浏览器自动化辅助工具完成滑块交互 | 天眼查(高频后)、微博 |
| 短信验证 | 要求输入手机验证码 | (不自动处理) 提示用户手动完成 | 裁判文书网(注册)、MIIT ICP |
| 登录要求 | 查看详情需要登录 | 加载已保存的会话状态(cookie) | 裁判文书网、天眼查/企查查(高频后) |
| IP频率限制 | 短时间内过多请求 | 出口地址轮换 + 增加请求间隔 | GSXT、裁判文书网 |
| 搜索结果上限 | 如"最多600条" | 分段查询(按法院/年份/类型拆分) | 裁判文书网 |
| 分页限制 | 每页仅显示N条 | 遍历翻页参数(page=N) | 信用中国、巨潮资讯 |
| 滑块/点击验证 | 点击图片中的特定物体 | 浏览器自动化 + 手动预标注训练数据 | 少见,主要在商业平台 |
