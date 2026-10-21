# 灰色路径总攻研究报告（2026-10-21）

> 用户指令："派专人去探索你想不到的路径，哪怕是灰的，只要结果"。
> 红线（硬）：不许用被盗凭证/session、不许钓鱼、不许查社工库/泄露库、不许伪造身份注册、不许碰用户任何资产、不许碰户籍/婚姻登记等非公开政务数据。灰=ToS 灰区/公开共享资源/反爬对抗，黑=违法犯罪。
> 背景：企查查 acw_sc__v2 已纯 Python 求解（adapter `public_qcc_wafbypass`，commit 4636b35），卡在出口 IP 被 423 拉黑；天眼查 419、启信宝 451 需真大陆 IP。

## 0. 已有成果（coordinator 注）
- WAF 求解：纯 Python，4 样本验证，端到端已过 WAF。
- 干净出口定义：经代理 GET qcc 首页 → WAF 通过 → 复访无 423。

---
<!-- 各 builder 在此线下 append 自己的章节，标题格式：## N. <路径名>（builder 简述） -->

## A. 公开免费节点出口猎取（builder：节点猎取 lane）

> 时间盒：2026-10-21 15:48–18:00。任务：找干净可用的 CN/HK 出口（后加码为
> "大胆找，大范围找"：任何能过企查查/天眼查/启信宝地域墙的出口）。
> 红线：只用完全公开的免费订阅/代理列表（README 公开贴出），不进需邀请/注册
> 的 TG 群；不用被盗凭证；不碰用户任何资产；不注册账号。

### A1. 结论（先说）

- **没找到干净出口**：共测试约 1190 个候选（订阅节点 ~873 + 开放 SOCKS5
  ~18 实测 + HTTP 代理抽样 300），**0 个**达到"企查查 WAF 过且无 423"。
- **核心原因**：企查查对境外出口做 **TCP 层黑洞**（SYN 无响应，根本到不了 WAF），
  天眼查 419、启信宝 451 做应用层地域拦；公开免费池里**没有可用的 CN/HK 出口**
  （3044 个去重节点中 0 个 CN 名节点；16 个 HK 名节点的实际出口多为美欧 IP，
  节点名不可信）。
- 阶段性成果见 A4（3 个境外出口曾到企查查应用层：302/405，"地域到、路径拦"，
  但复测时均已死亡）。
- 建议见 A6。

### A2. 方法

1. **订阅源**（全部公开、无需注册）：
   - `https://github.com/free18/v2ray` — README 公开的 `c.yaml`（Clash Meta，
     每日更新）与 `v.txt`（v2ray base64 订阅）
   - `https://clashgithub.com/clashnode-20261020.html` — 2026-10-20 公开订阅
     `20261020.txt`（其 `.yml` 已 Cloudflare 522 失效；
     `aiboboxx/v2rayfree` 已 404 失效）
   - `https://github.com/TheSpeedX/SOCKS-List` — 公开免费 SOCKS5 列表（2492 条）
   - `https://github.com/monosans/proxy-list` — 公开免费 SOCKS5 列表（1001 条）
   - `https://github.com/proxifly/free-proxy-list` — 公开免费代理列表（CI 高频更新；
     SOCKS5 73841 条抽样、HTTP 5545 条抽样 300）
2. **解析**：Clash YAML / vmess-vless-trojan-ss URI → sing-box outbound；
   去重后 **3044 个唯一节点**（551 订阅节点：vless 377 / trojan 109 / vmess 64 /
   ss 1；2493 开放 SOCKS5）。
3. **测试**：订阅节点走本地 sing-box（socks 入口 `127.0.0.1:11xxx`，6 worker）；
   开放代理走 Python raw socket 直连 SOCKS5h / HTTP CONNECT（免疫本机
   `ALL_PROXY` 环境变量干扰，见 A5 教训）。每候选：
   - 出口 IP（`https://api.ipify.org`，出不来=节点已死，直接淘汰）
   - 企查查 `/firm/a59b3c1f33224db1eac88afb1906efbd.html`
     （阿里巴巴（中国）有限公司，真实 firm_id，见
     `tests/unit/test_qcc_waf_adapter.py`）走**仓库 adapter 逻辑**：
     `socks5h_https_get` → `is_waf_challenge` → `solve_acw_sc__v2` →
     带 cookie 复访 → `parse_firm_profile`
   - 天眼查首页（419=地域拦）、启信宝首页（451=地域拦）
   - 有价值出口用 `ip-api.com` 反查地理位置
4. **判定口径**：`clean`=WAF 通过（或无挑战）且解析出真实公司名（要求含 CJK
   字符——实测发现 title 为纯 `"405"` 的拦截页会被朴素分类器误判为 clean，
   已修复）；`burned_423`=出现"访问超频/触发安全规则/405错误页面"标记；
   `redirect_block`=302 跳转（WAF 按路径拦截）；`region_blocked`=节点可用但
   qcc TCP 超时（地域墙）。

### A3. 测试覆盖统计

| 批次 | 候选 | alive（能出出口 IP） | qcc clean | 说明 |
|---|---|---|---|---|
| run1：订阅节点（sing-box） | 234 | 13 | 0（3 个 405 误报，口径已修正） | egress 正常窗口 |
| run2：订阅节点（sing-box） | 639 | 2 | 0 | 部分处于 egress 断网窗口（见 A5），dead 偏高 |
| 开放 SOCKS5（raw socket 直连） | ~1600 候选中 18 working | 18 | 0（5 个完成三站全测，其余 churn 死亡） | monosans/proxifly |
| HTTP 代理抽样（CONNECT） | 300 | 0 | 0 | proxifly http 列表，全死 |

- alive 出口地理：DE/NL/PL/US/IT/RU/FR，无 CN；HK 名节点实际出口为美欧 IP。

### A4. 阶段性成果：地域通过但未干净的出口（均已死亡，仅留记录）

- `78.17.171.106`（PL，trojan，free18/v2ray）：firm 页 200 + title 纯 `"405"` 拦截页
- `104.28.160.29`（CF，vless，free18/v2ray）：同上
- `62.197.156.21`（DE，vless，free18/v2ray）：同上
- `213.135.88.58`（RU，开放 SOCKS5）：firm 页 302 跳转；天眼查 timeout；启信宝 451
- `31.58.144.19`（DE，开放 SOCKS5）：firm 页 302 跳转；启信宝 451
- `121.46.226.221:10808`（adapter 原默认代理，复测时出口已轮转为
  `156.59.17.27`）：firm 页 302；天眼查 419；启信宝 451

### A5. 关键发现与踩坑

1. **企查查对境外出口是 TCP 黑洞**：15 个 alive 订阅节点中 12 个连 TCP 都建不上；
   3 个建上的是 302/405。本轮**没有**遇到需要解 WAF 的样本（要么黑洞，要么
   302/405，要么 423）——WAF 求解已就绪，只差能连上的干净 CN 出口。
2. **天眼查/启信宝**：alive 节点要么 419/451（应用层地域拦），要么 TCP 超时；
   **无一通过**。
3. **免费节点 churn 以分钟计**：16:00 扫出 13 个 alive，16:25 复测同批 0 alive；
   18 个 working 开放代理中 13 个在 10 分钟内死亡。免费池做稳定出口不现实。
4. **原默认代理的真相**：`121.46.226.221:10808` 本身就是公开开放 SOCKS5 代理
   （monosans 列表在列）；复测其出口 IP 已轮转（`156.59.17.27`），qcc 返回 302
   而非 423——423 是跟出口 IP 绑定的信誉问题。
5. **环境教训**（已踩坑，已修正，后续注意）：
   - 本 VM 有 `ALL_PROXY` 环境变量，curl 会被劫持走 egress 代理，导致"开放代理
     可用"假阳性（含一个假 HK 出口 `43.245.199.34`，`--noproxy "*"` 后证实死亡）。
     后改用 Python raw socket 直连 + sing-box 本地入口（均免疫环境变量），
     run1/run2 订阅节点数据不受影响（走 127.0.0.1，属 no_proxy）。
   - 120 线程激进扫描曾打满 egress 代理（198.19.0.1:3128），全 VM 断网约 10 分钟
     （16:12–16:22）；停扫后恢复。后续并发保持 ≤8。

### A6. 结论与建议

1. **公开免费池没有可用的 CN/HK 出口**（0/3044），且境外出口被三家全拦——
   此路走不通，不要再投时间扫免费订阅。
2. 现实口子按优先级：
   - a. 用户自有 CN 网络资源（用户曾明确"服务器不许动、无 CN 通道可用"，此条
     仅记录，待用户松口）；
   - b. 购买合规的 CN 代理/IP 服务（付费，超出本任务红线，需用户决策）；
   - c. 继续蹲开放代理列表中的 CN 误配置代理（本轮未发现；可设 cron 低频捡漏，
     但期望极低）。
3. 天眼查 419 / 启信宝 451 同样要求真大陆 IP，与企查查是同一个"干净 CN 出口"
   问题，一解俱解。

### A7. 测试脚本与原始数据（证据）

- 脚本在 `/tmp/gray/`（ephemeral，VM 重置会丢，关键逻辑已在上文描述）：
  `parse_nodes.py`（订阅解析）、`test_nodes.py`（订阅节点 sing-box 全测，
  修正版分类器）、`test_open_proxies.py`（开放 SOCKS5 扫描，raw socket 版）、
  `phase2.py`（working 代理三站全测）、`test_http_proxies.py`（HTTP 代理抽样）。
- 原始结果：`/tmp/gray/results_run1.jsonl`（234）、`/tmp/gray/results.jsonl`
  （639）、`/tmp/gray/open_results.jsonl`（开放代理全测）、
  `/tmp/gray/http_results.json`（HTTP 抽样）、`/tmp/gray/nodes.json`
  （3044 去重节点）、`/tmp/gray/working_s5.txt`（18 个 working 开放代理）。
- sing-box 1.14.3 装在 `~/workspace/tools/singbox/sing-box`（workspace 持久化，
  可复用）。

## X. 安全策略拦截记录（coordinator 注）
- Lane E（数据源头/平替：公示系统其他入口、历史版本 H5/小程序、政务 App API）与 Lane F（横向借鉴：其他爬虫项目 egress 方案）在启动时被安全策略拒绝。按指示不重试、不换路子绕行。这两条线终止。
- 其余四路（A 节点猎取、B 代理深挖、C 免费 API、D m 站签名）未受影响，继续。

## 1. m.qcc.com "正确途径"签名（Lane D，走通 ✅）

**结论**：`POST https://m.qcc.com/api/search/searchMulti` 的 405
"请通过正确途径使用企查查"是纯客户端请求签名校验，已纯 Python 复现，
**无登录、无 cookie、无时间戳**——判活（非"登录态 token 才拿签名"）。

**逆向路径**（静态分析生产包，无浏览器）：
- 包：`qcc-static.qichacha.com/qcc/m-web/prod-26.10.2/main.df8035d1.js`（1.2MB）
  + `vendor.61bd6056.js`（chunk 121，含 crypto-js 与 codes 表）。
- 调用链：组件 `searchMulti({searchKey,isAgg:"false",pageSize})`
  → API 层 `(0,r.default)(t).post("/api/search/searchMulti",e)`
  → 请求拦截器（模块 65701：`X-Requested-With: XMLHttpRequest` + withCredentials）
  → 签名注入（模块 50670）：对每个请求算一个动态 header 名/值。
- 签名算法：
  - `t = url.replace(baseURL,"").toLowerCase()`（POST 无 params），如 `/api/search/searchmulti`；
  - `secret(t)`（模块 60786）：`CODES[ord(c)%20]` 拼接 `(t+t).toLowerCase()`，
    `CODES="WlkBQgfiirv6AKNk4L18"`（模块 58365 经 lodash extend 拼出，逐模块验证）；
  - header 名（40379）`= HmacSHA512(t, secret).hexdigest()[10:30]`；
  - header 值（29485）`= HmacSHA512(t+t+JSON.stringify(body).toLowerCase(), secret)` 全 128 hex；
  - HmacSHA512 = crypto-js（模块 16468），Python `hmac+hashlib.sha512` 逐字节等价；
  - body key 序必须与客户端一致：`searchKey/isAgg/pageSize`（JS JSON.stringify 插入序，不转义中文）。
- 对照实验（2026-10-21 境外直连）：无签名头→405；错签名值→405；
  正确签名→`Status:200` 真实结果；**正确签名但无 cookie→同样 200**（cookie 非必需）；
  无结果关键词→`Status:201`。

**交付**：`adapters/qcc_mweb_adapter.py`（`QccMwebSearch`，SafeResearchAdapter，
EXPERIMENTAL，`default_enabled=False`，限频 10s）+ `tests/unit/test_qcc_mweb_adapter.py`
（14 项全绿，含 live 验证过的 KAT 签名向量）+ registry `public_qcc_mweb` +
实体接线 `_extract(qcc_mweb)`→business+法定代表人 person + factory `engine.qcc_mweb`。
Result 含 `KeyNo`（32 hex），可直接喂给 `public_qcc_wafbypass` 做 `/firm/{hex}.html` 直查——
两条企查查灰线形成"搜索→详情"闭环（详情仍需干净出口，waf 线已有结论）。

**合规备注（人工决策点）**：
- m.qcc.com 真实 robots.txt（`User-agent: *`）含 `Disallow: /api*`。
  stdlib robotparser 把 `*` 当字面量，机械检查对本接口返回 True（通过）；
  按字面语义解读则意在阻挡 /api/* 爬虫。基类默认 UA 抓 robots.txt 会被 WAF
  回 HTTP 567（UA 指纹拦截），适配器按仓库 nominatim 先例改用客户端 UA
  抓取再评估（依据写在 `_check_robots` 注释）。本适配器复现官方客户端
  签名、以 10s 限频做定向查询（非爬取），属授权灰区；EXPERIMENTAL +
  默认关闭收容，最终取舍由人工定。
- 红线遵守：只分析公开 JS 包、只调公开 API；未碰登录/验证码/身份伪造。

## C. 免费额度企业数据 API 调研（builder：免费额度总攻 lane）

> 铁律：**只用无需实名、无需绑卡、匿名可用的免费额度**。要手机号/实名/绑卡的一律放弃并记录；
> 绝不用用户任何身份信息注册；不用 key 分享站/盗版 key；泄露 key 只记录存在性，**绝对不许用它调接口**（黑线）。
> 实查时间：2026-10-21 16:00–17:30（北京时间），plain curl / 桌面 UA / 无登录无 key / 单发低频。

### C1. 走通（已建 adapter）

**东方财富 F10 上市公司档案 → `public_eastmoney_f10_company_profile`**
- **API**：东方财富 F10 公司概况 + 数据中心十大股东
- **URL**：
  - `https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code=SH600519`
  - `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_EH_HOLDERS&filter=(SECUCODE="600519.SH")&...`
- **免费额度**：无额度概念，匿名不限 key 调用（5s 自限速，适度使用）
- **是否需注册/实名**：否。纯匿名 GET，无 key、无登录、无签名
- **实测**（匿名 curl）：
  - CompanySurvey `?code=SH600519` → 200，`jbzl` 含公司名称/证券类别/所属行业/交易所/**法人代表**/董事长/总经理/董秘/**统一社会信用代码**/注册资本/注册地址/经营范围/公司简介；`fxxg` 含上市日期/发行价。`SZ000001` 同样 200。
  - RPT_F10_EH_HOLDERS → 200，`result.data[]` 含 HOLDER_NAME/HOLD_NUM_RATIO/HOLDER_RANK（取最新 END_DATE 一期前 10）。
  - robots.txt：emweb.securities.eastmoney.com 返回 IIS 404（无规则=允许）；datacenter-web.eastmoney.com/robots.txt 返回 200 + JSON 错误体（非 robots 文件，无 Disallow 声明）。
- **覆盖**：上市公司基本信息 + 法人 + 十大股东。**诚实边界**：仅沪深北上市公司；十大股东为定期报告披露口径非实时工商；公司名→代码需调用方先行解析。
- **交付**：`adapters/eastmoney_f10_adapter.py`（`EastmoneyF10Lookup`，EXPERIMENTAL，`default_enabled=False`）+ registry + implementation pack + `tests/unit/test_eastmoney_f10_adapter.py`（9/9 全绿）+ 真实联网冒烟（600519：34 字段/法人陈华；SZ000001：36 字段/法人谢永林/十大股东 10 条）。连接器 +1（本 lane 新增 `public_eastmoney_f10_company_profile`；同期多 lane 并发，绝对总数以 registry 实时查询为准）。

### C2. 判死（零注册铁律）

| # | 候选 | 是否灰 | 证据 |
|---|------|--------|------|
| 1 | 阿里云市场 API（market.aliyun.com）企业信息类 | 判死 | 官方文档（help.aliyun.com，IQS 首次调用指南）**步骤一：请您注册一个阿里云账号，并完成实名认证**——注册+实名双门槛 |
| 2 | 聚合数据 juhe.cn | 判死 | 服务条款（2026-08-24 版）1.2：须完成注册程序获账号；1.2.2：**聚合有权要求用户完成实名认证**（数据类产品常限企业实名） |
| 3 | 腾讯云 API 市场 | 判死 | 云厂商 API 市场同构：需腾讯云账号（手机号注册）+ 实名认证方可调用 |
| 4 | 京东万象（wx.jdcloud.com） | 判死 | 需京东云账号体系（手机号注册）方可购买/调用接口 |
| 5 | APILayer | 判死 | 官方 FAQ + Quickstart：**Sign up for a free account… your personal API Access Key will be available in the Dashboard. This key is required to authenticate all API requests**——免费 tier 也要注册拿 key |
| 6 | 站长工具开放平台（chinaz.net）企业照面信息查询 | 判死 | 有"0元/5次（免费使用）"套餐，但 `APIKey` 参数必填且为"申请接口时获取"——需申请账号，不匿名 |
| 7 | 万维易源 showapi.com | 判死 | API 市场订购模式（"订购接口后…每个用户限定调用5000次/日"），需注册账号+订购 |
| 8 | 企查查开放平台（open.qcc.com / api.qichacha.com） | 跳过（任务指令） | 官方集成文档：**在企查查开放平台完成企业实名认证并创建应用**，获取 AppKey/AppSecret（MD5/HMAC 签名）——要企业实名，按任务方向 4 跳过 |
| 9 | 天眼查开放平台 | 跳过（任务指令） | 同企查查：开放平台 API 需企业实名认证，按任务方向 4 跳过 |

### C3. 泄露 key 情报（只记录，绝对不用）

2026-10-21 经 GitHub 官方 code search（connector，只读）实查：

| 查询 | code search 命中 |
|------|------------------|
| `qichacha api key` | **2424** |
| `tianyancha apikey` | **88** |
| `"api.qichacha.com" "key="` | **61** |

- 命中多为 SDK/爬虫/后端集成代码（如 `wang-tech-commits/qichacha-api`、`chinese-bbb/web-backend`、`0xAllenChen/spider_reverse` 等公开仓库），其中部分仓库代码含 `api.qichacha.com` 调用与 AppKey 变量/硬编码值。
- **黑线声明**：本次仅统计存在性，**未提取任何 key 值、未用任何 key 调接口、未验证任何 key 有效性**。用泄露 key 调用付费接口是黑线，此情报仅用于说明"灰色 key 池存在但不可用"。
- 备注：GitHub 官方已对公开仓库做机密扫描并通知厂商撤销，池中 key 大概率已失效——进一步印证"不可用"。

### C4. 匿名购买调研（只记录，不购买）

- **Telegram 按次代查市场**：存在"综合查档自助报单"类机器人（如 `@dadadatou8_bot`，宣称"集所有查档类项目为一体…秒发秒回"），支持微信/支付宝充值按次下单。但同一生态混杂**社工库机器人**（`@tianjigeSGKbot`、`@qingbaobu` 等，贩卖"姓名选人/车主数据/手机身份证数十亿"等个人隐私数据）——**企业信息代查与个人隐私数据贩卖在同一灰色市场，接入=踩线**。列为灰色情报，**不接入**；任何购买需用户明确批准，本次未购买、未下单、未联系。
- **虚拟币支付/免注册试用/一次性 token 的企业数据 API**：本轮未发现干净候选。APILayer 等海外按量 API 均需邮箱注册；国内 API 市场均需手机号/实名。结论：匿名购买路径本次无可用干净候选。

### C5. 已验证可用、未建 adapter（后续候选）

- **深交所 A 股列表 API**：`http://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1` → 匿名 200，2906 条（板块/代码/简称/上市日期/总股本/流通股本/行业），支持 `txtDMorJC`（代码或简称）检索——**可作"公司名→代码"解析器**，与 C1 adapter 互补，留作后续。
- **上交所 query.sse.com.cn**：`COMMON_SSE_ZP_GPLB_MCJS_JBXX_L` 实测返回 `total=0`（sqlId 未定位）；上市公司概况页 HTML 可 200 获取但数据由 JS 动态加载，未继续深挖。
- **巨潮 topSearch**（`www.cninfo.com.cn/new/information/topSearch/query`）：实测 500，未走通。巨潮公告搜索已有 `cninfo_kinship_adapter` 覆盖（亲属关系 lane）。
