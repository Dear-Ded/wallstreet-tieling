# 搜索引擎索引片段聚合（商查不寻常路径）— 实测报告（2026-10-21）

> 目标：搜索引擎对 qcc.com / tianyancha.com / qixin.com 公司详情页有大量
> 索引，片段（snippet）常含注册资本/法人/地址等结构化信息；验证
> `site:qcc.com "有限公司"` 类查询是否可编程低频获取结构化片段。
>
> 铁律：零用户身份信息、零注册、不登录、不绕验证码、不碰付费 API；
> 搜索引擎结果页只做低频公开抓取；robots.txt 如实记录。

---

# 省级公示系统 + 招投标/政府采购（商查不寻常路径）— 实测报告（2026-10-21）

> 目标：国家企业信用信息公示系统（gsxt）国家门户境外 IP 被 521 + JSL 挑战拦截，
> 逐个轻测 31 省级子站（HTTP 状态、验证码、GeoIP），找弱口子；同时测
> ccgp.gov.cn（中国政府采购网）与中国招标投标公共服务平台
> （cebpubservice.com）——中标公告/企业资质信息，法定公开、免费免登录。
>
> 红线（铁律）：零用户身份信息、零注册、不登录、不绕验证码；
> 只做公开端点 plain HTTP 低频实测；robots.txt 如实记录。
>
> **结论：两条路都不通于 plain HTTP。31 个省级 GSXT 节点全部被同一套 JSL
> （加速乐）JS cookie 挑战锁死；cebpubservice.com 在 WAF 层直接 405 拦截
> （含 robots.txt）。不新建 adapter；招投标线已由 `adapters/ccgp_adapter.py`
> 覆盖（`public_ccgp_bid_lookup`，16 个 focused test 全绿）。**

实查窗口：2026-10-21 15:20–15:35（北京时间）。方法：plain curl HTTP 请求，
桌面 Chrome UA，无登录、无 cookie、无签名伪造、无 WAF/验证码绕过、
无打码平台、无 TLS 指纹伪装。出口 IP：`104.29.200.237`（境外 egress）。

## 一、省级 GSXT 子站：31/31 全军覆没（同一套挑战）

### 逐省实测结果

| 省 | 域名 | 首页状态 | 挑战页 | 验证码标记 | robots.txt 状态 |
|----|------|----------|--------|------------|-----------------|
| 北京 | bj.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 上海 | sh.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 天津 | tj.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 重庆 | cq.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 河北 | he.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 山西 | sx.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 内蒙古 | nm.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 辽宁 | ln.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 吉林 | jl.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 黑龙江 | hl.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 江苏 | js.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 浙江 | zj.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 安徽 | ah.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 福建 | fj.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 江西 | jx.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 山东 | sd.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 河南 | ha.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 湖北 | hb.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 湖南 | hn.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 广东 | gd.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 广西 | gx.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 海南 | hi.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 四川 | sc.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 贵州 | gz.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 云南 | yn.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 西藏 | xz.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 陕西 | sn.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 甘肃 | gs.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 青海 | qh.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 宁夏 | nx.gsxt.gov.cn | 521 | 是 | 无 | 521 |
| 新疆 | xj.gsxt.gov.cn | 521 | 是 | 无 | 521 |

（逐节点原始输出 `/tmp/gsxt_probe2_results.txt`：首页 521、挑战页约 821–924B；
请求间隔 ≥2s，31 省 × 2 请求共 62 次低频请求。按 AGENTS.md 卫生规则，
/tmp scratch 不提交仓库。）

### 卡点分析

- **挑战位置**：第一跳即死。31 个节点返回均为同一形态挑战页——`<script>`
  用字符级拼接（`('_')+('_')+('j')+('s')+('l')+('c')+('l')+…`，样本见
  `/tmp/gb_bj.html`）算出 `document.cookie='__jsl_clearance_s=…'` 后
  `location.href` 重载。这是知道创宇/加速乐系 JS 算术 cookie 挑战，
  与国家门户 `www.gsxt.gov.cn` 完全一致（见 `docs/research/gsxt-feasibility-20261021.md`）。
  **换省分流的路子不通——省级节点与国家门户共用同一套 WAF。**
- **robots.txt**：同样被挑战页拦截（521），无法确认站方抓取声明——如实记录：不可达。
- **GeoIP 侧记**：本次从境外出口 IP 发起，观察到的是 521 JS 挑战而非
  403 GeoIP 明确拒绝；31 节点 DNS 在本环境出口代理下被映射为连续
  `198.18.143–198.18.173`（CGNAT 段，代理内部分配），真实源站 IP 不可见——
  GeoIP 维度无可观测差异。
- **验证码**：挑战页内无极验/滑块标记（验证码在挑战之后、查询页才有——
  但查询页根本到不了）。

### 未尝试（按红线排除）

- 用脚本算出 `__jsl_clearance_s`（WAF 绕过，不碰）
- TLS/HTTP 指纹伪装绕过挑战（同属绕过，不碰）
- 打码平台过查询页极验 v4（红线：不接）
- 登录后维持会话（未授权，不登录）

## 二、中国招标投标公共服务平台（cebpubservice.com）：WAF 层 405 拦截

| # | 方法/URL | 结果 |
|---|----------|------|
| 1 | `GET https://www.cebpubservice.com/`（裸 curl） | **405**，2657B 阿里云 WAF 拦截页（"很抱歉，由于您访问的URL有可能对网站造成安全威胁，您的访问被阻断。"，traceid `276082b417925671807827694e6423`） |
| 2 | 同上 + 完整桌面浏览器请求头（Accept/Accept-Language/Upgrade-Insecure-Requests 等） | **405**，同拦截页——不是缺头的问题 |
| 3 | `GET https://www.cebpubservice.com/robots.txt` | **405**，同拦截页——robots.txt 不可达，无法确认抓取声明 |
| 4 | `GET http://www.cebpubservice.com/`（80 端口） | **405**，同拦截页 |
| 5 | 文本抓取工具（browser.open）同 URL | upstream 405——从本环境发出的请求在服务端被统一拒绝 |

卡点：拦截发生在返回任何业务内容之前，且 robots.txt 同样被拦。
结合第 2 条（完整浏览器头仍被拦），大概率是 TLS 指纹 / 客户端信誉 /
地域维度的 WAF 策略——plain HTTP 无合法路径可达。
搜索/公告列表等业务端点同属该主机，主机层已封，无需再逐个试。

拦截页样本：`/tmp/ceb_h2.html`（未入库）。

## 三、招投标/政府采购线：已由 sibling 覆盖，无需重复

- `adapters/ccgp_adapter.py`（`CcgpBidLookup`，中国政府采购网
  `search.ccgp.gov.cn/bxsearch` + 公告详情页）已存在并在本分支实测可用；
  `tests/unit/test_ccgp_adapter.py` **16/16 全绿**（本次复跑确认）。
- 其注册条目 `public_ccgp_bid_lookup` 已在 `core/connector_registry.py`
  中（implementation pack + runtime companion）。本次不重复建 adapter、
  不重复注册。

## 四、结论：不建 adapter

`public_provincial_gsxt` **不建**：31 省全 521，plain HTTP 路径不存在。
`public_cebpubservice` **不建**：WAF 405 全主机封锁。
强行建 adapter 会违反"不绕验证码/WAF"红线。

registry 条目：无新增（adapter 未建，`core/connector_registry.py` 未动；
ccgp 条目已存在，不重复）。

## 五、诚实缺口与后续可选方向（本次不做）

- browser-assisted（真实浏览器，JSL 自动通过）通道就绪后，可在浏览器内
  验证某省站查询页；若查询页弹出极验滑块——出现即停，
  记录"需用户侧过验证"。
- 工程招标类公开数据可评估各省级公共资源交易平台（分散、各省反爬强度
  不一——与本轮 GSXT 省站的统一性不同，值得单独一轮轻测，但属于新任务）。
- 本次交付：仅本节。测试计数：0 新增（无 adapter、无 focused test；
  未改动任何代码，现有测试套件不受影响）。

## 六、交付

- 追加：`docs/research/unconventional-paths-20261021.md`（本节）。
- 未新增 adapter / 测试 / registry 条目（见第四节判死结论）。

## 一、robots.txt 实测记录（2026-10-21，curl 直取）

| 引擎 | `User-agent: *` 相关条目 | 结论 |
|---|---|---|
| baidu.com / www.baidu.com | `Disallow: /`（全站，另对 Baiduspider/Googlebot/MSNBot 有 `Disallow: /s?`） | 程序化抓取 /s 结果页被 robots 明确禁止 |
| bing.com / www.bing.com | `Disallow: /search`、`Disallow: /Search`（另有一批 `/images/search?`、`/copilotsearch?q=` 等） | 程序化抓取 /search 结果页被 robots 明确禁止 |
| google.com / www.google.com | `Disallow: /search`（仅放行 `/search/about`、`/search/howsearchworks`） | 程序化抓取 /search 结果页被 robots 明确禁止 |

按本仓库 `SafeResearchAdapter._check_robots` 口径，三家 /search 结果页对
通用 bot 均为 `robots_txt_disallowed`——adapter 层会直接拒绝，连请求都不发。

## 二、低频公开抓取实测（证据）

共 4 次请求，每引擎 1~2 次、间隔 ≥12s，公开 HTML、无 Cookie/登录/验证码绕过。
原始 HTML 存外部证据目录（未提交仓库）：`/tmp/se_snippet_evidence/`。

### 1. 百度 —— 图形验证码硬拦截（判死）
- 请求：`GET www.baidu.com/s?wd=site:qcc.com "有限公司" 注册资本`
- 实测：HTTP 200 但 **302 跳转到 `wappass.baidu.com/static/captcha/tuxing_v2.html`**
  （`ak=c27bbc89afca0463650ac9bde68ebe06`），页面标题"百度安全验证"，
  正文"网络不给力，请稍后重试"。结构化字段命中 0。
- 卡点：裸程序化请求（数据中心出口 IP、无登录态）首跳即触发百度安全验证；
  **绕验证码是红线**，此路判死。

### 2. Bing —— `site:` 算子不可靠，拿不到目标站片段（判死）
- 请求 A：`GET www.bing.com/search?q=site:qcc.com "有限公司" 注册资本`
  → HTTP 200，约 13,800 个结果，`b_algo` 10 条**全部来自 sellfox.com /
  baike.baidu.com 等站外**，`site:qcc.com` 被静默忽略（0 条 qcc.com 结果）。
- 请求 B：`GET www.bing.com/search?q=site:qcc.com 深圳市腾讯计算机系统有限公司`
  → HTTP 200，但页面明示"**没有与此相关的结果**"（`b_algo` 0 条）。
- 卡点：Bing 对程序化请求的 `site:` 限定不稳定（时而忽略、时而零结果），
  片段来源不可控为目标站公司详情页；加之 robots 禁止 /search，判死。

### 3. Google —— 软拦截无结果（判死）
- 请求：`GET www.google.com/search?q=site:qcc.com "有限公司" 注册资本&hl=zh-CN`
- 实测：HTTP 200 但返回的是**重定向中间页**
  （"如果您在几秒钟内没有被重定向，请点击此处"），无任何搜索结果；
  结构化字段命中 0。robots 已 `Disallow: /search`。
- 卡点：裸程序化请求被软拦截；Google ToS 亦禁止未经许可的自动化查询。
  判死。

## 三、卡点汇总

1. **robots.txt 全灭**：三家对 `User-agent: *` 明确 Disallow 搜索结果页路径；
   按仓库既有 robots 门禁口径，adapter 不应发出请求。
2. **反爬全灭**：百度=验证码硬拦截（红线不可绕），Google=重定向软拦截，
   Bing=可达但 `site:` 算子对程序化请求不可靠。
3. **ToS 灰区**：三家 ToS 均限制/禁止自动化查询且无免 key 的文档化查询 API；
   不像 urlscan.io 有公开 API 可走"文档化调用"口径。
4. **片段质量假设未被证伪但也未被证实**：因连结果页都拿不到稳定目标站
   条目，"片段含注册资本/法人/地址"的结构化抽取无从验证。

## 四、结论：不建 adapter

`public_search_snippet_lookup` **不建**。任一搜索引擎的 `site:` 查询均不满足
"可稳定低频获取结构化片段"——三家分别死于验证码 / 算子不可靠 / 软拦截，
且 robots.txt 全部明确禁止。强行建 adapter 会违反仓库 robots 门禁与
"不绕验证码"红线。

registry 条目：无（adapter 未建，`core/connector_registry.py` 未动）。

## 五、诚实缺口与后续可选方向（本次不做）

- 仓库已有 `adapters/public_web_search_tool.py`（DuckDuckGo instant answer /
  自建 SearXNG 零配置 provider）：做的是通用公开搜索归一化，**不支持可靠的
  `site:` 站内限定 + 商查结构化片段抽取**，不能冒充本路径的替代。
- 可选后续（需单独立项实测）：Common Crawl 索引（CC-INDEX）按域名查
  qcc.com/tianyancha.com 抓取记录 → 从 WARC 抽详情页结构化字段；
  或用户自建 SearXNG 实例走其 JSON API（用户侧部署，非零成本）。
- 本次交付：仅本文档。测试计数：0 新增（无 adapter、无 focused test；
  未改动任何代码，现有测试套件不受影响）。

## 六、交付
- 新增：`docs/research/unconventional-paths-20261021.md`（本文）。
- 未新增 adapter / 测试 / registry 条目（见第四节判死结论）。

---

# 二线聚合站免费面（商查不寻常路径）— 实测报告（2026-10-21）

> 目标：二线企业信息聚合站的免费面实测——水滴信用（shuidi.cn）、
> 企查猫（qichamao.com）、爱企查之外的百度系、查企业、114/本地宝企业频道。
> 逐个测：免登录公司搜索/详情页的结构化字段（注册资本/法人/地址/股东/
> 风险提示）、反爬强度、robots.txt。
>
> 红线（铁律）：零用户身份信息、零注册、不登录、不绕验证码、不碰付费墙；
> 只做公开页面 plain HTTP 低频实测；robots.txt 如实记录。
>
> **结论：六个候选面全部走不通，不建 adapter。**
> 实测窗口 2026-10-21 15:20–16:10（北京时间）。全部为 plain `curl` 匿名
> 低频单发：桌面 Chrome UA，无登录、无 cookie、无验证码绕过、无付费接口
> 调用、无签名伪造、无 WAF/地域封锁绕过。测试公司名统一用公开大企业
> 「华为技术有限公司」（仅作连通性探针）。

## 一、总览

| # | 候选面 | 探针数 | 结论 | 卡点 |
|---|--------|--------|------|------|
| 1 | 水滴信用 shuidi.cn | 4 | 判死 | 地域封锁（非 CN IP）+ 详情页登录墙 |
| 2 | 企查猫 qichamao.com | 3 | 判死 | 搜索硬登录墙 + robots 明示 `Disallow: /search/` + 匿名搜索需 verify token |
| 3 | 百度系（除爱企查） | 3 | 判死 | 搜索页 302 空回 + robots `Disallow: /s?`；企业信用已并入爱企查反爬门 |
| 4 | 查企业 | 0（无站可测） | 无法立项 | 公开渠道找不到独立权威官网；候选域名本地 DNS 被劫持 |
| 5 | 114（114.com） | 2 | 判死 | 域名已转作 Shopify 电商站（bestshop.com），企业黄页面不复存在 |
| 6 | 本地宝 bendibao.com | 2 | 判死 | 纯城市生活服务门户，无企业/工商/黄页频道，无结构化企业数据面 |

## 二、逐站实测证据

### 1. 水滴信用（shuidi.cn）— 地域封锁 + 登录墙

| 探针 | 结果 |
|---|---|
| `GET https://shuidi.cn/robots.txt` | 200，85 B：`Sitemap: https://shuidi.cn/sitemap.txt`，`Disallow: /facilitator`，`Disallow: /index.html` |
| `GET https://shuidi.cn/sitemap.txt` | 200，320 KB：含 `company-<32位hex>.html` 企业详情 URL 列表（SEO 面存在） |
| `GET https://shuidi.cn/` | 200 但最终 URL `/ipbaned.html`，460 B：「根据中国相关法律法规，由于您为非中国大陆地区IP，水滴无法为您提供服务」 |
| `GET https://shuidi.cn/company-82a4b0b25695599e75845dcbbd2f8b08.html`（取自 sitemap） | 200 但最终 URL `/pcuser-tologin`（43 KB 登录页），无任何企业数据 |

**卡点**：双重墙。① 通道级地域封锁：非中国大陆 IP 全站不可用；
② 详情页实测落到登录墙。零注册路线无数据面。
**下条路**：CN 出口 IP + 登录态（需用户账号，超出"公开免登录"范围）。

### 2. 企查猫（qichamao.com）— 搜索硬登录墙

| 探针 | 结果 |
|---|---|
| `GET https://www.qichamao.com/robots.txt`（`qichamao.com` 301 到 www） | 200，941 B：`Disallow: /search/`、`/trade-search/`、`/dishonest/`、`/judge/`、`/gonggao/`、`/patent/` 等约 40 条数据路径——**站方明确禁止抓取搜索与全部风险/司法/专利数据面** |
| `GET https://www.qichamao.com/` | 200，459 KB（28 s，偏慢），标题「企查猫（企业查询宝）-一键查询全国企业工商信用信息」 |
| `GET https://www.qichamao.com/search/qy/<urlencode(华为技术有限公司)>` | **302 → `/UserCenter/Login`**（标题「登录-企查猫」）；页面 99 处"登录"、73 处"验证码/verify"标记，0 处"注册资本/法定代表人"，0 处目标公司名 |

首页内嵌 JS 实锤匿名门禁逻辑（`hdUserId==0` 时搜索先走 `verify()` 拿
`mfccode` token，已登录才直跳）：

```js
var topSearch = function (n) {
    if (parseInt($("#hdUserId").val()) == 0) {
        verify(function (mfccode) {
            location.href = "/search/all/" + n + "?mfccode=" + mfccode;
        });
    } else {
        location.href = "/search/all/" + n;
    }
}
```

**卡点**：三重。① 匿名搜索 302 到登录页（硬登录墙）；
② 匿名搜索即便在浏览器里也要先过 `verify()` 拿 token（验证码门，红线内不碰）；
③ robots.txt 明确 `Disallow: /search/`（站方明示信号，按仓库惯例不建爬虫）。
**下条路**：用户登录态 + browser-assisted（用户未授权，不展开）。

### 3. 百度系（除爱企查）— 已整体收归爱企查反爬门

| 探针 | 结果 |
|---|---|
| `GET https://www.baidu.com/s?wd=<urlencode(华为技术有限公司)>`（桌面 UA） | 302，536 B 空回，最终 URL 不变，无标题、无"注册资本/法定代表人"、无目标公司名——plain HTTP 拿不到搜索结果，更无企业知识卡片 |
| `GET https://www.baidu.com/robots.txt` | 200：`Disallow: /s?`、`Disallow: /ulink?` 等——**百度明确禁止抓取搜索结果页** |
| `GET https://xin.baidu.com/`（百度企业信用旧入口） | 200 但最终 URL `https://aiqicha.baidu.com/acount/accessrestriction`——已 301 并入爱企查，落到同一百度 heicha 反爬门（见 `aiqicha-feasibility-20261021.md`） |

**卡点**：百度系企业信息面已收缩为单一入口（爱企查），而该入口对匿名
plain HTTP 是 JS 挑战 + 登录门（前序实测结论）。百度地图 POI 商户面仓库
已有 `baidu_map_adapter.py`，不属新增面。
**下条路**：无（与爱企查同墙）。

### 4. 查企业 — 无独立权威站点可立项

- 4 轮公开检索（中文 web search）未找到独立权威的「查企业」官网；命中均为
  企查查/天眼查/爱企查介绍页与导航站收录。
- 候选域名 `chaqiye.com` / `chaqiye.cn` / `chaqiye.net` / `chaqi.com` /
  `chachacha.cn` 的本地 DNS 解析全部被劫持到 `198.18.253.137–141`
  （198.18.0.0/15 本地 sinkhole；与前序 `mob.qichacha.com` 被劫持现象一致），
  无真实 IP 可验证。
- 按任务口径「qichacha 仿站不算」：市面自称"查企业"的多为企查查仿站/SEO 站，
  不计入。

**卡点**：目标不明确，无可测的权威站。**下条路**：请任务方给出确切域名后重测。

### 5. 114（114.com）— 域名已转作电商站

| 探针 | 结果 |
|---|---|
| `GET https://114.com/robots.txt` | 404（无 robots.txt） |
| `GET https://114.com/` | 200，1.16 MB，最终 URL `https://bestshop.com/`——英文 Shopify 电商站
  （`shopify.exit_interstitial` 脚本、`lang="en"`），0 处"企业/公司/工商/
  信用"结构化字段 |

**卡点**：域名已易主/repurposed，原电信 114 企业黄页/电话查询面不复存在。
**下条路**：无（域名层面死亡；不追踪不知名的"114 黄页"克隆站）。

### 6. 本地宝（bendibao.com）— 无企业信息面

| 探针 | 结果 |
|---|---|
| `GET https://bendibao.com/robots.txt` | 200，582 B：Discuz! X2 默认模板（`Disallow: /api/`、`/search.php` 等，无企业相关路径） |
| `GET https://bendibao.com/` → `http://www.bendibao.com/index.htm` | 200，40 KB，标题「深圳本地宝-爱上本地宝，生活会更好」；全站为 396 个城市分站入口；全文仅 1 处"企业"相关文本（"企业文化"），0 处"工商/黄页/企业库/公司库"频道链接 |

**卡点**：本地宝是城市生活服务/便民资讯门户，不存在"企业频道"或结构化
企业工商数据面；其"商家"内容为生活服务类（餐饮/租房等），无注册资本/
法人/股东/风险字段。
**下条路**：无（产品定位就不含企业征信面）。

## 三、robots.txt 如实记录汇总

| 站点 | robots.txt | 关键 Disallow |
|---|---|---|
| shuidi.cn | 200，有 sitemap | `/facilitator`、`/index.html`（搜索/详情页未明示禁止，但被地域+登录墙挡住） |
| www.qichamao.com | 200 | `/search/`、`/trade-search/`、`/dishonest/`、`/judge/`、`/gonggao/`、`/patent/` 等约 40 条数据路径——**明示禁抓** |
| www.baidu.com | 200 | `/s?`、`/ulink?`、`/link?` 等——**明示禁抓搜索结果** |
| 114.com | 404（无） | —（域名已非原站） |
| bendibao.com | 200（Discuz 默认） | `/api/`、`/search.php` 等通用路径，无企业面可言 |

## 四、红线合规声明

本节共 **13 次目标站 HTTP 探针**（另有 5 次 DNS 解析、4 轮公开 web 检索用于
目标定位），全部为匿名单发 GET：无登录、无 cookie 维持、无验证码识别或
绕过、无付费接口调用、无签名伪造、无地域封锁绕过（含 shuidi.cn 的 IP
地域墙：仅如实记录其存在，未尝试代理/伪装 CN IP 突破）。robots.txt /
sitemap.txt 的读取为公开合规读取。证据 HTML 存 `/tmp/wstl-probe/`
（未进仓库）。

## 五、建议

1. **不建任何 adapter**：六个面无一具备"免登录 + 结构化 + 站方允许"三要素。
   企查猫/百度搜索虽有数据，但 robots 明示禁抓，按仓库惯例（`aiqicha-feasibility`
   将 `Disallow: /*ajax` 视为站方明示信号）不建爬虫。
2. **registry 不动**：无走通项，故无 `core/connector_registry.py` 的 dict entry
   需要提交；本报告即为交付物。
3. 商查"不寻常路径"至此基本收敛：主流（企查查/天眼查/爱企查/启信宝，见
   `gap-assault-p2-20261021.md`）+ 二线（本节）+ 官方 gsxt（见
   `gsxt-feasibility-20261021.md`）均无零注册结构化面。剩余缺口如需填补，
   现实路线只剩：① 用户授权的 browser-assisted 登录态复用；② 官方开放平台
   付费 API；③ CN 运行时 + 用户登录态的水滴信用（仍需验证）。

## 六、交付

- 追加：`docs/research/unconventional-paths-20261021.md`（本节：二线聚合站免费面）。
- 未新增 adapter / 测试 / registry 条目（见第五节判死结论）。
- 测试计数：本节 13 次目标站 HTTP 探针；新增 focused test 0（无 adapter，
  现有测试套件不受影响）。
