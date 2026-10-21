# 「企业预警通」(www.qyyjt.cn) 拆解可行性报告（2026-10-21）

> **结论先行**：企业预警通是真实独立产品（纠正 `qiyeyujingtong-feasibility-20261021.md`
> 中"不存在独立产品"的错误结论：qyyjt = 企业预警通拼音首字母）。
> 数据 API 真实存在但**需要登录态**，且主站有地域墙；本轮未找到**免登录**的数据通路。
> 下有 4 条具体可走的路（见第五节），不是"失败"。

## 一、产品主体确认

| 项 | 证据 |
|---|---|
| 产品名 | 企业预警通（iTunes `trackName`，`https://itunes.apple.com/lookup?id=1297123402&country=cn` 实查） |
| 运营主体 | 上海大智慧财汇数据科技有限公司（Financial China Information & Technology Co.,Ltd，iTunes `sellerName`；官网 www.finchina.com 页脚 ICP **沪ICP备06009028号-9A**，2026-10-21 自邀请页实查；客服 (+86) 021-20219912） |
| Web 端 | https://www.qyyjt.cn/（React SPA，`REACT_APP_CLIENT:"pc-web;pro"`） |
| Android | `finchinaEdr-release.apk` V8.4.2（官方版本接口实查，见下） |
| iOS | id1297123402，V8.6.2，bundleId `news.finchina.com` |
| 微信小程序 | 官方产品页 `applets.7d3ee982.png` 为标准微信**小程序码**（中央企业预警通闪电 logo + 右下微信角标，已目视确认） |

## 二、拆解过程（全部 plain curl，无登录、无签名伪造）

### 1. www.qyyjt.cn — 地域墙（知道创宇 WAF，抖动）

- `GET https://www.qyyjt.cn/` → 有时 **HTTP 418**（`Server: CW`，正文明示
  "根据相关法律法规，企业预警通暂不支持中国大陆以外地区的访问"），
  有时 **HTTP 200** 返回 SPA 壳（"你需要启用JavaScript才能运行此网页"）。
  本机出口在境外，WAF 按 GeoIP 拦，表现抖动。

### 2. Web 主 bundle 逆向（经 Wayback 拿到 2024-05 版 `main.df07f5ed.js`，708KB）

解出 API 全部为**同源相对路径**（base = `window.location.origin`，生产即 www.qyyjt.cn）：

- 搜索：`/finchinaAPP/v1/finchina-search/v1/multipleSearch`（GET，参数 `text/pagesize/skip/template/list/isRelationSearch`）
- 债券公告：`/finchinaAPP/v1/finchina-search/v1/webNotice/getF9NoticeList`（POST，form）
- 用户信息：`/finchinaAPP/v1/user/info`
- 风险监控：`/information/riskMonitor`（子路径 `/credit` `/news` `/notice`
  `/management/*` `/judical/*` 等 20+）、`/information/riskDetail`
- 债券/机构：`/bond/nonStandardAssetRisk`、`/cloud/bondRiskDaily`、
  `/full/financingInstitution/creditRiskAsset`、`/zwb/pc/risk_*`

### 3. app.finchina.com（同公司未封锁 host）的 `.action` 后端 — 可用但仅服务邀请/下载链路

- `GET /finchinaAPP/getJSSign.action?url=...` → 200，返回微信 JS-SDK 签名 JSON
  `{"returncode":0,"data":{"jsapi_ticket":"sM4AOVdWfPE4DxkXGEs8VN-...","nonceStr":"...","timestamp":"...","signature":"..."}}`
- `GET /finchinaAPP/getAppVersion.action?sys=Android` → 200，**结构化版本信息**：
  `{"returncode":0,"data":{"version":"V8.4.2","size":"128.8MB","url":"https://app.finchina.com/finchinaAPP/download/finchinaEdr-release.apk","content":"「五篇大文章智能识别系统」上线..."}}`
  （`sys=ios` 返回 iTunes 链接 `id1297123402`；大小写敏感）
- `POST /finchinaAPP/uploadOptionLog.action` → 埋点接口，无数据价值
- `/finchinaAPP/v1/finchina-search/v1/multipleSearch` 在此 host 上 200 但恒返回空；
  `/finchinaAPP/v1/user/info` 在此 host 上被 WAF 418（路径规则，真接口的信号）

### 4. APK 链路 — 官方渠道已定位，下载被拦

- 版本接口给出的 APK 地址 302 跳转到 `https://cdn.finchina.com/app/download/apk/finchinaEdr-release.apk`
  → **HTTP 403**（阿里云 OSS `AccessDenied`，私有 bucket，需签名 URL）
- 邀请页走 OpenInstall SDK（appKey `z04lou`），其 `backupDownload` 配置为加密载荷，
  SDK 深度混淆，未继续
- 应用宝/酷安/360 等商店 Web 搜索均被反爬或无结果（噪音大，"大智慧"多为证券软件）

### 5. API 实测（未登录）— 全部空回

| 请求 | 结果 |
|---|---|
| `GET www.qyyjt.cn/finchinaAPP/v1/finchina-search/v1/multipleSearch?text=腾讯&pagesize=10` | 200 `{"info":"暂无相关数据","returncode":200,"total":0}` |
| `POST .../multipleSearch`（form） | WAF 拦截页（HTML） |
| `GET www.qyyjt.cn/finchinaAPP/v1/user/info` | 200 同上空 JSON |
| `GET www.qyyjt.cn/information/riskMonitor` | 200 但为 SPA 壳 HTML（前端路由，非 API） |
| `GET app.finchina.com/information/riskMonitor` | 418（WAF 路径规则，证实为真接口） |

**规律**：未登录请求一律返回 `{"info":"暂无相关数据","returncode":200,"total":0}`，
不 401、不报错——登录态是硬门槛。

## 三、精确卡点

1. **登录墙**：数据 API（搜索/风险监控/债券/用户信息）全部要登录 session，
   产品本身是付费终端（"登录网页版"、邀请码、18+）。未登录 = 空 JSON。
2. **地域墙**：www.qyyjt.cn 对境外 IP 418（知道创宇 WAF，GeoIP 规则），虽抖动但不可靠；
   红线要求不伪装境内 IP。
3. **APK 拿不到**：CDN 私有 bucket 403；OpenInstall 加密；商店 Web 端反爬。
   无 APK → 无法 REA 找 APP 端 API host（APP 接口可能不走地域墙，如 app.finchina.com 就不走）。
4. 小程序码已确认官方存在，但无微信环境无法解码/抓包其 `wx.request` 域名。

## 四、与仓库现状的关系

- 仓库已有 `adapters/qyyjt_adapter.py`（1488 行，45 模块，基于 `/finchinaAPP/v1/` 端点族）
  及 `qyyjt_playwright_adapter.py` / `qyyjt_cookie_manager.py` / `qyyjt_auto_login.py`，
  测试全绿（fixture 级）。本轮拆解**证实了其端点结构为真**（bundle 逆向 + WAF 路径规则 + 实测），
  卡点与之一致：缺登录态 + 地域墙。
- 本报告纠正 `docs/research/qiyeyujingtong-feasibility-20261021.md`
  的"不存在独立产品"结论（当时把企业预警通误判为商查平台的监控功能）。

## 五、下条没试过的路（按优先级）

1. **微信小程序**（最有希望的新面）：官方小程序码已确认。需在微信环境打开小程序，
   抓其 `wx.request` 域名——小程序的后端域名是公开配置，且小程序接口常比 Web 端轻量。
   需 parent/用户侧配合（本 subagent 无微信环境）。
2. **用户登录态 + browser-assisted**：仓库已有 playwright 适配器与 cookie 管理器骨架；
   用户若有企业预警通账号，走"浏览器代管登录"（京东/淘宝代管方案同理）即可驱动
   `/finchinaAPP/v1/` 与 `/information/riskMonitor` 全套接口。由用户决策。
3. **真机拿 APK → REA**：在用户手机/境内设备从官方邀请页经 OpenInstall 正常下载 APK，
   用 `~/workspace/rea/` 反编译找 APP 端 API host（大概率不在地域墙内）。
4. **境内 IP 出口**：地域墙消失后，Web 端 + API 均可直连；届时再补 bundle 差分
   （2024-05 版已拿到，可对照新版找新增接口）。

## 六、红线遵守

未登录、未绕验证码、未碰付费墙接口、未伪造签名、未伪装境内 IP；
robots：`app.finchina.com/robots.txt` 为 `Disallow: *`（已记录，未据此爬取）；
APK 只尝试官方渠道（版本接口/OpenInstall/商店），未用第三方镜像；
Wayback 存档为公开历史快照，仅用于静态分析。
