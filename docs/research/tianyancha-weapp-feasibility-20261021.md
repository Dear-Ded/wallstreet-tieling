# 天眼查 / 企查查小程序后端路线可行性报告 — 2026-10-21

> 结论：**小程序后端路线部分验证，但两家均未打通免登录企业查询；不建 adapter。**
> 企查查小程序后端域确认存活（`wxapi.qichacha.com`，nodejs-wechat），但搜索接口路径未公开披露、
> 免登录面未验证；天眼查未发现专用小程序后端域，已知 Web/APP 后端接口实测要登录态。

实查时间：2026-10-21 14:40–14:53（北京时间），plain curl 单发低频，无登录、无 cookie、
无签名伪造、无 WAF 绕过。证据文件均在 `/tmp`（wxapkg/APK 本体未进仓库）。

## 一、企查查小程序后端 — 域确认，路径未公开

### 1.1 域名确认
- `GET https://wxapi.qichacha.com/` → **200**，正文 `<h1>nodejs-wechat@prod-26.05.9</h1>`。
  该域是从企查查 m-web 正式 JS 包（`qcc-static.qichacha.com/qcc/m-web/prod-26.10.2/main.df8035d1.js`，
  1.2MB，已拉到 `/tmp/qccmain.js`）里实锤的字符串，命名即"微信小程序 API"。
- `GET https://wxapi.qichacha.com/owx/v1/` → `{"status":404,"message":"您请求的资源不存在"}`
  （nodejs 服务正常路由，路径不存在而非被拦）。
- JS 包内唯一公开的 `/owx/` 路径：**`/owx/v1/admin/getSignature?url=`**（微信 JSSDK 签名接口，
  不是业务接口）。

### 1.2 业务搜索路径 — 未找到
- m-web JS 包（`/tmp/qccmain.js`，m.qcc.com 的生产包）内 grep `owx/v1` 仅命中上述一条；
  m-web 本身的搜索走另一套 AJAX 面（shell 页 `__INITIAL_STATE__` 的 `freeCoy:[]` 为空，结果客户端渲染），
  未从该包中解析出小程序专用的企业搜索路径。
- 公开 web 搜索（中文 4 轮：`天眼查 小程序 抓包` / `企查查 小程序 api 接口` / `"wxapi.qichacha.com"` /
  `企查查 wxapkg 解包`）未发现任何已披露的小程序 request 域名或接口路径；GitHub 上无公开的企查查
  wxapkg 归档。
- **卡点**：小程序业务接口路径未知，且按微信小程序惯例其 `wx.request` 必然携带小程序
  登录态（`wx.login` code 换 session_key / 自有 token），免登录复现无从下手。

### 1.3 顺带发现（m-web 包内）
- APP 端 webview 接口前缀：`https://mob.qichacha.com/app/AggregateSearchMain?input=`（APP 内核接口，供参考）。
- m.qichacha.com → 301 → `m.qcc.com`；`GET https://m.qcc.com/search?key=华为` → 200 但仅 2.5KB Vue 空壳
  （`/tmp/qccm.html`），无服务端渲染结果。

## 二、天眼查小程序后端 — 未找到专用域，已知后端要登录

- 猜测的小程序域全部不可达（`wxapi./miniapp./wxmp./mpapi.tianyancha.com` → curl 000）。
- 已知 Web/APP 后端（公开 spider 项目披露，deepwiki 实证）：
  - `GET https://api9.tianyancha.com/services/v3/search/sNorV3/华为` → 200
    `{"data":null,"isLogin":0,"message":"unauthorized api","state":"warn"}` —— **接口活着，但要求登录态 token**。
  - `GET https://capi.tianyancha.com/cloud-facade/company/familyBucket` → 200 `bannedLocation`
    （出口 IP 87.81.224.24 非 CN，地域封锁；即便有 token 本环境也过不去）。
- 公开渠道未发现天眼查小程序 request 域名披露。

## 三、APP 并行线（按任务第 4 条）

- 天眼查 APK：APKPure 官方包下载+jadx 拆解工作量超出本轮时间盒（上一轮已判重度加固
  `classes.dex` 13KB loader + `libdu.so` + `libJMEncryptBox.so`，静态无入口）；本轮时间优先小程序路线，未重复下载。
- 企查查：APKPure 无收录，跳过下载；公开资料搜集如上（仅开放平台付费 API，按红线只记录不采购）。

## 四、下条路（按优先级）

1. **企查查 `wxapi.qichacha.com` 是最有希望的口子**。拿到小程序 wxapkg（需真机/微信 PC 端从
   `/data/data/com.tencent.mm/.../appbrand/pkg` 提取，属用户设备操作）→ 解包 `app-config.json` 看
   request 合法域名 → 看 JS 里 `/owx/v1/` 下的业务路径与签名参数形状 → 再评估免登录面。
   或在用户授权的真机上打开企查查小程序并抓包一次（用户侧操作），一次即得全量路径。
2. **天眼查**：api9 v3 接口的 `unauthorized api` 说明其鉴权是"登录态 token"而非强签名；
   若用户后续提供自有登录态（browser-assisted），`services/v3/search/sNorV3/{q}` 可直接复用，
   免登录则无路。
3. 兜底不变：两家官方开放平台均为付费（天眼查 `open.api.tianyancha.com`，企查查 `api.qichacha.com`，
   后者 Token=[SECURITY_DATA] `(key+Timespan+SecretKey)` 32 位大写），只记录不采购。

## 五、红线合规

- 本轮所有请求均为匿名单发 GET/HEAD，无登录、无打码平台、无付费接口调用、无 WAF/地域封锁绕过尝试。
- 未下载 APK/wxapkg 本体进仓库；`/tmp` 证据文件不提交。
