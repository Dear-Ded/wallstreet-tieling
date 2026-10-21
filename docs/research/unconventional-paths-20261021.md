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
---

# GitHub spider 项目技术挖掘（商查不寻常路径之一）— 实测报告（2026-10-21）

> 目标：在 GitHub/技术博客找大家怎么爬企查查/天眼查/启信宝——搜
> qcc/tianyancha/qixin spider/scraper 项目，读它们的 technique（签名算法、
> 公开端点、H5 技巧、历史接口），用实测验证其中免登录可用的数据面。
> 天眼查 api9 v3 就是这么发现的——继续深挖：企查查历史 API、启信宝 web
> 接口、天眼查 suggest/老版本 v1/v2 接口。
>
> 红线（铁律）：零用户身份信息、零注册、不登录、不绕验证码、不碰付费
> openAPI、不伪造身份、不查泄露库。只做公开 web 端点的 plain HTTP 低频
> 实测；签名算法客户端复现仅限公开端点（项目已有先例：抖音 a_bogus 纯
> Python 复现）。
>
> **结论：走不通，不建 adapter。** 全部已披露的社区技术都收敛到\"登录态
> token / 用户 cookie / WAF 解挑战\"三扇门之一；免登录的 api9 v1/v2/v3
> （含 suggest 系列）实测全部显式 `unauthorized api`；企查查历史端点已
> 404/下线；启信宝对本出口地域封锁（451）。

实查窗口：2026-10-21 15:19–16:40（北京时间）。方法：GitHub 公开仓库只读
（connector MCP，`search_repositories`/`search_code`/`get_file_contents`），
+ 公开 web 端点 plain curl 低频单发（桌面/手机 UA，无登录、无 cookie
维持、无签名伪造、无挑战绕过）。出口 IP：境外 egress（对方自报
87.81.230.x，非 CN）。

## 一、GitHub 项目清单（按平台）

### 天眼查 spider 项目

| 仓库 | 更新 | technique 摘要 |
|------|------|----------------|
| `CharlesPikachu/pytools`（pytools/modules/tianyancha） | 长期维护 | `api9.tianyancha.com/services/v3/search/sNorV3/{q}` + 详情 `services/v3/t/common/baseinfoV5/{id}`；请求头含 **`version: TYC-XCX-WX`**（小程序面）、`Authorization: 0###…`（session token，已打码）、`x-auth-token`（神策 analytics 追踪 id） |
| `854771076/tyc_qcc_spider`（`天眼查.py`） | 近期 | 同 api9 v3，`Authorization` + `X_AUTH_TOKEN` 均为作者自有登录态（源码中已打码） |
| `claireymeng/Tianyancha_Spider`（2025-01, Playwright） | 2025 | 浏览器自动化（需登录态） |
| `YunCan-code/TianYanChaSpider`（2025-01, selenium） | 2025 | 浏览器自动化（需登录态） |
| `imquanquan/tyc_urls`（2025-03, scrapy） | 2025 | URL 采集骨架，未见免登录数据面 |
| 其余（pom1205、jianrongzeng、crawlerclub 等） | 2017–2023 | 旧 web HTML / selenium，均需登录或已失效 |

### 企查查 spider 项目

| 仓库 | 更新 | technique 摘要 |
|------|------|----------------|
| `854771076/tyc_qcc_spider`（`企查查.py`） | 近期 | **pid/tid + HMAC 签名**：先 `GET www.qcc.com/web/search/advance?hasState=true` 从页面正则取 `pid`/`tid`，再对请求做 `seeds_generator` 字符映射 + HMAC 签名；**但全程依赖作者自有用户 cookie**（settings 注\"一对可访问500次\"） |
| `tenlee2012/qichacha-spider`（2024-08, scrapy-redis） | 2024 | 纯 HTML 爬虫：`g_{prov}_{p}.html` 分省列表页 → 详情页；无签名、无登录——**但今天该面已被阿里云 WAF（acw_sc__v2）锁死**（见 §二） |
| `YzaSoLong/qichacha_spider`（2023-08, selenium） | 2023 | 远程调试 Chrome + QQ OAuth 登录（`graph.qq.com/oauth2.0` → `qichacha.com/user_callbackqq`），登录态采集 |
| `doublezjia/qichacha-spider` 等十余个 | 2016–2022 | 旧版 web HTML 爬虫，全部过期 |

### 启信宝 spider 项目

- GitHub **无**以 qixinbao/qixin 为目标的 spider 仓库（`qixinbao spider`
  检索 0 命中；`qixinbao.com` 代码检索仅命中过期域名列表噪音）。
- 唯一相关公开技术资料：启信宝（合合信息）自有发明专利 CN 111881337 A
  （\"请求预处理来克服签名验证的反爬虫机制\"）——**反向证据**：其服务端
  有签名验证反爬，无公开免登录面可指望。

## 二、实测证据（本节 20 次目标站 HTTP 探针）

### 1. 天眼查：api9 v1/v2/v3 + suggest 全系显式拒匿名

| # | 探针 | 结果 |
|---|------|------|
| 1 | `GET api9.tianyancha.com/services/v1/search/suggestV1?word=华为` | 200，`{\"isLogin\":0,\"message\":\"unauthorized api\",\"state\":\"warn\"}` |
| 2 | `GET api9.tianyancha.com/services/v2/search/sNorV2/华为` | 200，同 `unauthorized api` |
| 3 | `GET api9.tianyancha.com/services/v3/search/suggestV3/华为` | 200，同 `unauthorized api` |
| 4 | `GET api.tianyancha.com/services/v1/search/suggestV1?word=华为`（旧 host） | **000**（host 已不可达） |
| 5 | `GET www.tianyancha.com/tongji/华为.json`（老热搜统计接口） | 404，`{\"state\":\"error\",\"message\":\"系统异常\"}` |
| 6 | `GET www.tianyancha.com/search/suggest.json?key=华为` | 200，`{\"state\":\"error\",\"message\":\"系统异常\"}`（端点已死） |
| 7 | `GET www.tianyancha.com/search?key=华为` | **419**（天眼查反爬专用码）+ 地域封锁页 |

**判定**：api9 接口族活着，但鉴权=登录态 token（`Authorization` 头），
CharlesPikachu 仓库中的 token 均已打码、无可复现的公开面；
老版本（v1 host、tongji、suggest.json）全部下线/死亡。

### 2. 企查查：历史端点 404/WAF，当前 bundle 无公开 JSON 面

| # | 探针 | 结果 |
|---|------|------|
| 8 | `GET mob.qichacha.com/app/AggregateSearchMain?input=华为`（m-web JS 包内 APP webview 接口前缀） | **404**（nginx，路径已下线） |
| 9 | `GET www.qcc.com/web/search?key=华为` | 200，23.6 KB——**整页阿里云 WAF JS 挑战**（`acw_sc__v2` + `renderData` 混淆脚本），零企业数据 |
| 10 | `GET www.qichacha.com/web/search?key=华为`（旧域名） | 000（TLS 建连后被重置，域名已迁） |
| 11 | `GET www.qcc.com/web/search/advance?hasState=true`（pid/tid 签名源页面） | 200，23.6 KB——同样 WAF 挑战页，`pid`/`tid` 正则取不到 |
| 12 | `GET www.qcc.com/` + `qcc-static.qcc.com/qcc/pc-web/prod-26.10.145/main.e1cc8c62.js`（1.35 MB 生产 bundle 静态分析） | bundle 内**无独立 JSON 搜索 API host**；搜索走页面导航 `/web/search`，AJAX 面需 WAF cookie（pid/tid 逻辑在挑战之后，不可达） |

**判定**：2019 年的 APP v1（`appv3.qichacha.net`，md5 sign）与小程序 v1
（`xcx.qichacha.com`）已在前序报告中判死（host 死亡/需登录 token）；
当前生产面只有 WAF 后的页面流，无免登录 JSON 端点。

### 3. 启信宝：边缘 451 地域封锁（本出口），web API 形态已摸清

| # | 探针 | 结果 |
|---|------|------|
| 13 | `GET https://www.qixinbao.com/` | 000（TLS 建连后停滞——旧域名已废弃/不可达） |
| 14 | `GET https://www.qixin.com/` | **451**，34.7 KB Nuxt 报错页：`window.__NUXT__.config` 自报 `ip: 87.81.230.25`、`provinceName: 科罗拉多州`——**边缘对非中国大陆 IP 直接地域封锁** |
| 15 | `GET https://www.qixin.com/api-proxy/web/web/v8/ent/enterprise/getHotSearchEntList`（POST，空 body） | 同 451 报错页（API 同源代理 `/api-proxy/web` + `/web/v8/…`，同样被地域门挡在外面） |
| 16 | `GET https://m.qixin.com/` / `/search?keyword=华为` | **405**（m 站已下线/parked） |

**附带发现（静态分析，合规）**：qixin.com 生产 Nuxt 配置泄露了完整
web API 形态——浏览器侧 `BROWSER_API_BASE_URL_WEB: "/api-proxy/web"`，
业务路径如 `/web/v8/ent/enterprise/getEntInfo`、
`/web/v8/ent/enterprise/getHotSearchEntList` 等数十条（bundle
`c-cdn.qixin.com/web/_web/CgF0nkFh.js`，701 KB），另有
`GEETEST_ID_LOGIN/OVERLIMIT/NOPERCEPTION/SUBMIT` 四个极验 captcha id。
**这意味着：换 CN 出口后，`/api-proxy/web/web/v8/…` 是最值得复测的
候选面**（但本出口连门都摸不到，且极验 id 说明匿名高频必触发验证）。

## 三、大家怎么做的（technique 归纳）

1. **天眼查**：全部走 `api9.tianyancha.com/services/v3/*`（小程序后端，
   `TYC-XCX-WX`），鉴权=登录态 `Authorization` token。社区无人披露过
   免登录走通的 v1/v2 老接口——老 host `api.tianyancha.com` 已死，
   `tongji/*.json`、`search/suggest.json` 已死。
2. **企查查**：新派（2024+）= 带用户 cookie 的 pid/tid+HMAC 签名批量
   接口（`tyc_qcc_spider`，500 次/cookie 对）；旧派（2016–2022）= 纯
   HTML 爬虫（`g_{prov}_{p}.html`），已被阿里云 WAF 团灭。登录派 =
   selenium/QQ OAuth。
3. **启信宝**：社区无公开 spider；官方专利证实有请求签名反爬；web 面为
   同源 `/api-proxy/web` + `/web/v8/`，但对非 CN IP 边缘 451。
4. **共性**：三家都把 2019 年的弱鉴权老接口清干净了；当前唯一\"看起来
   免登录\"的面是 web 详情页/搜索页，而这些面在本出口被 WAF（企查查）、
   419+地域（天眼查）、451 地域（启信宝）三重门挡住——**门在 IP/地域层，
   不是签名层**，纯 HTTP 复现在本环境无解。

## 四、精确卡点

1. 天眼查 api9：`unauthorized api` 是**显式鉴权拒绝**，不是签名可绕的
   弱门；仓库 token 均打码，无公开复现材料。
2. 企查查：WAF `acw_sc__v2` 在**第一跳**即拦（IP 层，换 UA 无用）；
   解挑战=绕 bot 检测，红线禁区。pid/tid 签名本身需要先拿到挑战后的
   页面，死循环。
3. 启信宝：451 地域封锁发生在任何业务逻辑之前；m 站 405、旧域名 TLS
   死亡。CN 出口+匿名是否可达 `/api-proxy/web/web/v8/…` 未验证（本
   出口无法验证）。
4. 搜索引擎/二线站/分享链等 sibling 路径已在本文档前序章节判死，
   不重复。

## 五、红线合规声明

- GitHub 侧：仅只读公开仓库（MCP `search_*`/`get_file_contents`），未
  fork、未提 issue、未触碰任何私有内容；仓库中打码的 token/cookie/
  secretKey **均未尝试还原或使用**。
- 网络侧：20 次目标站探针全部为匿名单发 GET/POST（仅 1 次带空 JSON
  body 的 API 门形态探针），无登录、无 cookie 维持、无验证码识别或
  绕过、无付费接口调用、无签名伪造、无地域封锁绕过（含启信宝 451：
  仅如实记录，未尝试 CN 代理突破）。
- 静态分析：qcc/qixin 的生产 JS bundle 为公开 CDN 资源，只读 grep，
  未做反混淆执行、无挑战求解。
- `/tmp` 下探针原始 HTML/JS 为证据草稿，未入库。

## 六、建议（给 parent 的下一步选项）

1. **不建 adapter、不改 `core/connector_registry.py`**；本报告即交付物，
   故无 registry dict entry 提交。
2. **换 CN 出口复测**（最可能走通的一条）：启信宝
   `https://www.qixin.com/api-proxy/web/web/v8/ent/enterprise/getHotSearchEntList`
   与企查查 `www.qcc.com/firm/{hex}.html`（§三 robots 口径放行
   `/firm/*.html`），从 CN IP 匿名测一次。若渲染出字段，adapter 可按
   `fiftyeight_h5_adapter.py` 模式建（EXPERIMENTAL、默认关闭）。
3. **用户授权的 browser-assisted**：企查查/天眼查在用户自有登录态下
   均可正常用（`sogou_wx`/`dianping` 模式已有先例）。
4. **预算批准后**：官方付费 openAPI（天眼查 `open.api.tianyancha.com`、
   企查查 `api.qichacha.com`）——红线内只记录不采购。
5. **不建议**：伪造 sign / 解 WAF JS 挑战 / 打码平台 / 买 key / 借用他人
   登录态 cookie（全部踩红线）。

## 七、交付

- 追加：`docs/research/unconventional-paths-20261021.md`（本节：GitHub
  spider 项目技术挖掘）。
- 未新增 adapter / 测试 / registry 条目（见第六节判死结论）。
- 测试计数：本节 20 次目标站 HTTP 探针 + 约 15 次 GitHub 公开只读 API
  调用；新增 focused test 0（无 adapter，现有测试套件不受影响）。

---

# 分享链 H5 + 老版本 API（商查不寻常路径之一）— 实测报告（2026-10-21）

> 目标：(1) 天眼查/企查查/启信宝的分享链接（APP/小程序分享出的 H5）常对访客
> 渲染完整公司信息——找其 URL 规律并实测免登录渲染字段。(2) 老版本 API：
> qcc/tyc/qixin 历史 v1/v2 接口（从 GitHub spider 项目、Wayback、JS bundle
> 历史版本里找），鉴权可能弱于现行版，逐个轻测。
>
> 红线（铁律）：零用户身份信息、零注册、不登录、不绕验证码、不碰付费
> openAPI、不伪造签名。只做公开端点 plain HTTP 低频实测。
>
> **结论：走不通，不建 adapter。** 三家的分享链 H5 与历史 v1/v2 API，在红线
> 内没有一条能从当前出口吐出可用公司字段。卡点全部是出口侧可复现的硬门
> （WAF JS 挑战 / 地域封锁 / 显式鉴权拒绝），不是解析问题。

实查窗口：2026-10-21 15:20–16:10（北京时间）。方法：plain curl HTTP 请求，
手机 Safari UA（桌面 UA 复测一次），无登录、无 cookie、无签名伪造、
无 WAF/验证码绕过。出口 IP：美国（对方页面自报 87.81.230.109 / 87.81.238.59）。

## 一、分享链 H5：URL 规律

全网未索引到任何一家的 `/share` 独立路径（`tianyancha.com/share`、
`qcc.com/share`、`qixin.com/share` 均无命中）。三家 APP/小程序"分享"出去的
实际就是各自的**规范详情页**：

| 平台 | 分享/详情 URL 规律 | 规律来源 |
|------|-------------------|----------|
| 企查查 | `https://www.qcc.com/firm/{32位hex}.html` | Wikidata P10439 formatter URL；Global Energy Monitor、Retraction Watch 引用实例如 `f44b2e73df8264aa94c784be8a48933c`（六盘水化乐煤业有限公司） |
| 天眼查 | `https://www.tianyancha.com/company/{数字ID}` | Wayback 归档实例 `/company-jyfx/2949131241`；robots 明确放行 `/company/*`（仅禁 `?nav=` 查询串） |
| 启信宝 | H5 宿主为 `app-html.qixin.com`（生产 Nuxt 配置 `URL_HTML`；App Store 上架信息中隐私政策/用户协议/自动续费 H5 均挂在此 host，如 `/privacy-policy/ios`、`/user-protocol`、`/auto-renewal/app`） | qixin.com 报错页内嵌的 `window.__NUXT__.config` + FoxData 应用营销页 |

**免登录渲染字段实测：三家均为零**（本出口）：

| # | 探针 | 结果 |
|---|------|------|
| 1 | `GET www.qcc.com/firm/f44b2e73df8264aa94c784be8a48933c.html`（手机 UA） | 200，23670B，**整页是阿里云 WAF JS 挑战**（`acw_sc__v2` cookie，`renderData.l1` + 混淆 JS）。无 title、无 h1、无公司字段。桌面 UA 复测（`48b6cc86563a59e9fb7c20a05a7f1bb6`）同样 200/23670B/WAF——门在 IP 层，与 UA 无关 |
| 2 | `GET www.tianyancha.com/company/2949131241`（手机 UA，ID 取自 Wayback 归档） | **HTTP 419**（天眼查反爬专用状态码）+ 地域封锁页："根据相关法律规定，当前所在地区暂不支持访问…当前IP：87.81.230.109，当前地区：美国" |
| 3 | `GET www.qixin.com/robots.txt` | 无 robots.txt；直接返回 451 地域封锁页（"当前所在地区暂不支持访问"，IP 弗吉尼亚州）。`m.qixin.com/` 同样被阿里云 WAF 以 405 阻断 |
| 4 | `GET app-html.qixin.com/privacy-policy/ios` | 200，610B——H5 host 本身可达，但仅白名单法务页面可 serving；`/robots.txt` 被 WAF 405 阻断，无从得知分享页路径 |

## 二、老版本 API：清单与轻测

从 GitHub spider 项目源码挖到的历史接口（均为公开仓库代码中的 endpoint
常量，非抓包）：

| 宿主 | 路径 | 版本/端 | 鉴权要求 | 2026-10-21 实测 | 判定 |
|------|------|---------|----------|-----------------|------|
| `appv3.qichacha.net` | `/app/v1/admin/getAccessToken`、`/app/v1/base/getNewCompanys` | 企查查 APP v1（2019，`zhaoboy9692/qccspider`） | `sign=md5(deviceId+timestamp+secretKey)`——**secretKey 在仓库中被作者隐去**（"请关注公众号留言获取"）；作者自注"企查查升级，该接口失效" | 连接失败（HTTP 000，host 已不可达） | 已死亡；且伪造 sign 本就踩红线 |
| `xcx.qichacha.com` | `/wxa/v1/base/advancedSearchNew`、`/wxa/v1/base/getEntDetail`、`/wxa/v1/admin/getAreaList` | 企查查微信小程序 v1（2019，`bouxin/company-crawler`） | 1 小时有效 token（需 APP 登录获取）+ no-login cookie | TLS 建连后空回包；DNS 解析到 `198.18.253.142`（benchmark 段，出口黑洞） | 本出口不可达；且 token 需登录 |
| `api9.tianyancha.com` | `/services/v3/search/sNorV3/{q}` | 天眼查小程序 v3（`TYC-XCX-WX`，`bouxin/company-crawler`） | `Authorization` + `x-auth-token` 请求头（仓库中均已打码） | 200 返回 `{"data":null,"isLogin":0,"message":"unauthorized api","state":"warn"}` | 存活但**显式拒绝未鉴权调用**，门是明的 |
| `api.tianyancha.com` | `/services/open/...` | 付费 openAPI | 付费 key | 未探（红线：不碰付费 openAPI） | 出局 |
| `api.qichacha.com` | `/ECIPartner/GetList` 等 167 个 | 付费 openAPI | 付费 key + `Md5(key+Timespan+SecretKey)` | 未探（红线） | 出局 |

另：2018 年左右的 `Dephin/Tianyancha` 等老爬虫走的是纯 web HTML
（`/search?key=` + 详情页），无独立 API；如今天眼查 robots 已
`Disallow: /search*`，此路同样被 robots 判死。

## 三、robots.txt 口径（adapter 若要建必须遵守）

- `www.qcc.com`：`Disallow: /api*`、`/*?*`、`/*.shtml$`、`/search?key=*`、
  `/weblogin?*`、`/mlogin*`——任何带查询串的 API 探针在此口径下都不合规；
  `/firm/*.html` 原则放行。
- `www.tianyancha.com`：放行 `/company/*`（禁 `?nav=`）；禁 `/search*`、
  `/wxApi/*`、`/pagination/*`、`/snapshot*`、`/*?*`。
- `www.qixin.com`：无 robots.txt（本出口直接 451）。
- `app-html.qixin.com`：robots.txt 自身被 WAF 405，未知。

## 四、精确卡点

1. **企查查**：访客详情页被阿里云 WAF `acw_sc__v2` JS 挑战拦（IP 层，换 UA
   无用）；解挑战=绕 bot 检测，红线禁区。老 APP v1 host 已死亡；小程序 v1
   host 本出口不可达且要登录 token。
2. **天眼查**：本出口（美国 IP）被地域封锁 + 419 反爬；小程序 v3 API 存活但
   明示 `unauthorized api`；web 搜索路径被 robots 禁止。
3. **启信宝**：全站（含 m 站）对非中国大陆 IP 地域封锁/WAF 阻断；H5 host 仅
   白名单法务页可达，分享页路径未知且无法枚举。
4. 共性：三家都把"弱鉴权老接口"清干净了——2019 年的 v1 全部下线或收紧到
   登录态；当前唯一的免登录渲染面是 web 详情页，而详情页又被 WAF/地域门挡
   在本出口之外。

## 五、红线合规声明

本节共 **13 次目标站 HTTP 探针**（上表探针 #1–#4 与 §二实测列），全部为
无凭证、低频 GET（仅 1 次 API 门形态探针带查询串，其余无查询串）；
8 次公开 web 搜索；GitHub API / raw.githubusercontent / web.archive.org
CDX 只读公开资料。未注册、未登录、未伪造签名、未解任何挑战、未触碰付费
接口。`/tmp` 下探针原始 HTML 为证据草稿，未入库。

## 六、建议

1. **不建 adapter、不改 `core/connector_registry.py`**；本报告即交付物，
   故无 registry dict entry 提交。
2. **换 CN 出口复测**（最可能走通）：三家详情页都被搜索引擎索引、被第三方
   引用，说明从国内 IP 访客可渲染。需要 parent 具备条件的通道（用户浏览器
   代管 / CN 出口）复测探针 #1、#2；若渲染出字段，adapter 可按
   `fiftyeight_h5_adapter.py` 模式建（EXPERIMENTAL、默认关闭、遵守 §三 robots
   口径）。
3. **用户给一条真实分享链接**：从其手机 APP 分享一家公司给助手，捕获真实
   分享 URL（含可能的参数），再定向测试该形态。
4. 启信宝 H5 分享路径：拿到真实分享链接前不做枚举（WAF 会把枚举当攻击）。
5. **不建议**：伪造 sign（红线）、解 WAF JS 挑战（绕验证，红线）、买
   openAPI key（红线）、登录态 cookie（红线）。

## 七、交付

- 追加：`docs/research/unconventional-paths-20261021.md`（本节：分享链 H5 +
  老版本 API）。
- 未新增 adapter / 测试 / registry 条目（见第六节判死结论）。
- 测试计数：本节 13 次目标站 HTTP 探针；新增 focused test 0（无 adapter，
  现有测试套件不受影响）。
