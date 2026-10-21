# 商查缺口总攻 part 2 — 剩余免登录面实测报告（2026-10-21）

> **结论：企查查 / 天眼查 / 企业预警通 / 启信宝四家，均无免登录企业数据面。不建 adapter。**
> 实测时间 2026-10-21 15:12–15:35（北京时间），全部 plain HTTP 匿名低频单发：
> 无登录、无 cookie、无验证码绕过、无付费接口调用、无签名伪造、无 WAF/地域封锁绕过。

## 一、启信宝 H5 面 — 无数据面

| 探针 | 结果 |
|---|---|
| `app-query.qixin.com/`、`/api-proxy/app/*`、`/enterprise/*` | 全路径 **405**（阿里云通用 405 页，前端占位） |
| `app-web.qixin.com`、`finance.qixin.com` | 同上，全 405 |
| `vip.qixin.com` | DNS 不可达 |
| `appc-v6.qixin.com`（APK 反编译实锤网关，DoH 得真实 IP `120.26.143.97`） | `/enterprise/*` 未登录 **一律 404**（网关按认证状态路由，直接隐藏接口） |

**卡点**：身份墙。**下条路**：① Frida 动态拿 Dart 签名 ② 扫 H5 免登录面（本轮已扫完，无）③ 启信宝微信小程序后端。

## 二、企查查 APP 内核面 — 通道掐死

- `mob.qichacha.com/app/AggregateSearchMain`（m-web 生产 JS 包实锤的 APP 内核接口）：本地 DNS 被劫持（→198.18.0.0/15）；DoH 得真实 IP `183.192.176.62`（kunlungr CDN），**直连 000**（CDN 边缘掐境外 IP）。
- `apph5.qichacha.com`：200，但为 Vue 空壳（`qcc-identity: qcc-apph5`，客户端渲染）。
- `m.qcc.com/api/search/*`（m-web JS 包内 12 条实锤路径）：GET **500** 错误页 / POST 空回包 30s 超时——网关存在，但无鉴权信息不工作。
- `wxapi.qichacha.com`：存活（`nodejs-wechat@prod-26.05.9`），但业务搜索路径未公开披露，且按微信小程序惯例需 `wx.login` session。

**卡点**：通道级封锁（CDN 地域掐 + 接口需鉴权）。**下条路**：① 真机提取 wxapkg 看 request 域名与业务路径 ② 用户侧一次抓包即得全量路径。

## 三、天眼查 — 接口活着，要 token

- `www.tianyancha.com/company/<id>`：**419** 反爬秒拒。
- `m.tianyancha.com`：200（17 万字节，人物 SEO 目录页 `/human/*`，非可检索企业数据）；站内搜索 API **419**。
- `api9.tianyancha.com/services/v3/search/sNorV3|/suggestV3`：200 但 `{"isLogin":0,"message":"unauthorized api"}`——**接口活着，鉴权=登录态 token**（非强签名）。
- `capi.tianyancha.com`：`bannedLocation`（出口 IP 非 CN，地域封锁）。

**卡点**：登录态 token。**下条路**：用户自有登录态 + browser-assisted 可直接复用（用户已拒绝实名，不再提）。

## 四、企业预警通 — 数据面全要登录

- `app.finchina.com/finchinaAPP/getJSSign.action`：200（仅微信 JSSDK ticket，无数据）。
- `…/v1/finchina-search/v1/multipleSearch` 等数据接口：**一律 `{"info":"暂无相关数据","returncode":200,"total":0}`**（登录墙，第二次实锤）。
- 微信小程序：已确认存在官方小程序；无微信环境，公开资料挖掘未做。

**卡点**：登录墙。**下条路**：小程序公开信息面挖掘（需微信环境）。

## 五、m.qcc.com — 网关存在但不工作

- `/api/search/getTopHotWords|/searchHotCompany` 等：GET 500 / POST 空回包；猜测的 suggest 路径全 404。
- 结论同第二条。

## 六、红线合规声明

本轮所有请求均为匿名 GET/POST 单发，未登录、未使用打码平台、未调用付费接口、
未伪造签名、未尝试绕过 WAF/地域封锁（含 DoH 仅用于解析被劫持的 DNS，未用于伪装境内身份）。
APK/JS 包分析对象均为公开渠道包体。证据文件在 `/tmp`（`tyc_cfg.js`、`qccmain.js`、
`apph5.html` 等），未进仓库。
