# 启信宝 APP 逆向报告（2026-10-21）

**包**: `/tmp/qxb_appchina.apk`（68.6MB，`com.bertadata.qxb` v10.10.00，应用汇官方包）
**验签**: 通过。厂商自签 `O=bertadata`，SHA-256 `a51ab8022ebacaed91dc34bb6c361db144a0424536075ac7e75db6a2fd8a65e4`
**应用类型**: Flutter（`classes.dex` 仅 13KB 壳；Dart 逻辑在 `lib/arm64-v8a/libapp.so` 29MB）
**结论**: **API host 与 501 个接口路径全图已恢复；但无免登录可复现端点**——网关（`Server: Qxb Proxy Server`）对未认证请求一律 404，不建 adapter。

## 拆出来的东西

### 1. API 主域名
- `assets/setting/prod.json`（225KB，`fileCreatedTime: 2026-10-17`）中 `networkRequestDomain` = **`https://appc-v6.qixin.com`**
- Dart 层无硬编码 host（`appc-v6` 在 libapp.so 无出现），base URL 运行时从 prod.json 读取后拼接 `/enterprise/*` 路径。

### 2. 接口全图（501 个去重路径，见附）
核心族：
- 搜索：`/enterprise/advanceSearch2`、`/enterprise/riskSearchAgg`、`/enterprise/searchRiskLawsList`、`/enterprise/searchInvestment`、`/enterprise/searchComplaint`
- 企业详情：`/enterprise/getAbnormalEntList`、`/enterprise/getAdministrativePunishmentList`、`/enterprise/equity/getEquityPledgeOverview`、`/enterprise/bondDefault/getEntBondDefaultList`、`/enterprise/caseInfo/getCaseAgg`
- 监控/预警：`/enterprise/getNoticeAgg`、`/enterprise/getCourtNoticeList`、`/enterprise/getDeliveryNoticeListV2`、`/enterprise/getHistoryReduceCapitalNotice`
- 风险评分：`/enterprise/qxrisk/getEntQixinCountStatic`、`/enterprise/qxrisk/getEntQixinCountTrendChart`
- 域名/IP：`/enterprise/domain/getDomainICPList`、`/enterprise/domain/getDomainSubListV2`、`/enterprise/domain/getQuickAppList`

### 3. 配套 host（经实测）
| Host | 用途 | 状态 |
|---|---|---|
| `appc-v6.qixin.com` | API 主域（`Qxb Proxy Server`） | 存活，未认证请求 404 |
| `app-query.qixin.com` | H5 查询页 | 存活 |
| `app-web.qixin.com` / `app-vip.qixin.com` / `finance.qixin.com` | H5 功能页 | 存活 |
| `qx-ai.qixin.com` | AI 助手后端 | 存活 |
| `logger.qixin.com/track` | 埋点 | 存活 |
| `app.qixin.com` | 存活但阿里云 WAF 405 拦截 | 被墙 |
| `api.qixin.com` | OpenResty 占位页 | 无 API |
| `b.qixin.com` | 业务引流 H5 | 406（需 UA） |
| `static-cdn-p.qixin.com` / `qxb-c-osscache.qixin.com` | 静态资源 CDN | 存活 |

### 4. 客户端证据
- 极验 Geetest v4：`lib/arm64-v8a/libgtc4core.so`（1.1MB）存在。
- Deep Link：`qxb://`、`bertadata.qixinbao://`；`app-html.qixin.com`、短链域 `q.cc.co`。
- 渠道：`assets/channel` = `baidu`（百度手机助手包）。
- prod.json `bConstant` = `GhltJlIAewbd7REqtIcUbb9jta8Mj2d/JEwCgWjuJlM=`（疑似请求加解密相关常量，未深挖——属付费墙内机制）。
- `latestVersion` 显示官方最新为 10.09.00，本包 10.10.00 为更新版本。

## 精确卡点

1. **登录墙是硬门槛**：`https://appc-v6.qixin.com/enterprise/*` 对 GET/POST、空/测试参数一律返回 404（159 字节，`Server: Qxb Proxy Server`）——网关按认证状态路由，未登录直接隐藏接口，不存在免登录查询面。
2. **无游客/试用端点**：字符串全扫无 guest/trial/anonymous 相关 API 路径。
3. **签名算法未完全恢复**：请求签名逻辑在 Dart AOT 中，需 Frida 动态 hook（`DioMixin` 请求拦截器）才能拿到；静态 strings 不足。且即便复现签名，无有效登录态也拿不到数据——投入产出比不成立，未继续。
4. 唯一 200 的是静态样例页（`exportDataBSample.html`），无数据价值。

## 下条路（按优先级）

1. **用户登录态 + browser-assisted**：仓库已有 playwright 骨架；拿到登录态后按本报告的 501 路径逐个复现——接口全图已备好，这是最短的路。（需用户在手机上登录启信宝，无实名之外的额外动作。）
2. **Frida 动态分析**：真机/模拟器跑 APP，hook Dio 拦截器拿签名算法与 token 刷新逻辑——仍需登录态才能产出数据，优先级低于 1。
3. **H5 免登录面**：`app-query.qixin.com` 等 H5 页可能有部分免登录查询（如热搜、企业简览），值得单独扫一遍。
4. **小程序**：启信宝有微信小程序，其 `wx.request` 后端可能与 APP 不同签，另起一路。

## 红线遵守
未登录、未绕过极验验证码、未触碰付费墙、未伪造签名；仅分析公开 APK 包；`robots.txt` 已在 web 侧报告中记录。

## 附：接口路径清单
501 个 `/enterprise/*` 去重路径已存 `/tmp/enterprise_paths_qxb.txt`（本次任务产物，未进仓库——体积与敏感度考虑；需要时从该路径取）。
