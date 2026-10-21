# 中国执行信息公开网 (zxgk.court.gov.cn) 可行性报告 — 2026-10-21

**结论：走不通。本机出口在 WAF 边缘即被 GeoIP 封锁（`reason:GeoBL`），瑞数 v5 之前的门都进不去；移动端/小程序弱口未从公开渠道找到。不建议建适配器。**

实查时间：2026-10-21 14:05–14:45（北京时间），plain `curl` HTTPS 请求，无登录、无打码、无验证码硬解，未触碰 robots.txt Disallow 路径（见下）。

## 实测证据

| # | 方法/URL | 结果 |
|---|----------|------|
| 1 | `GET https://zxgk.court.gov.cn/`（桌面 UA，IPv6 出口） | **403**，WAF 回执 `eventID: …-waf03zzst reason:GeoBL`，`Client IP: 2a04:4e41:0:6f75::b5bf:ef75`——GeoIP 黑名单，请求未到达应用层 |
| 2 | 同上强制 IPv4 | **403**，同因 |
| 3 | `GET https://zxgk.court.gov.cn/robots.txt` | **403**（同上，连 robots 都拿不到） |
| 4 | `GET https://m.zxgk.court.gov.cn/`（移动端 host 猜测） | TCP 建连后**空回包**（curl exit 52, Empty reply）——疑似 WAF 直接 RST；robots 同样空回包 |
| 5 | DNS | `zxgk.court.gov.cn` 与 `m.zxgk.court.gov.cn` 均解析正常（经出口代理的 198.18.253.x），说明是应用层/WAF 策略封锁而非 DNS 问题 |

robots.txt 内容**无法获取**（被 403 挡），无从确认 Disallow 路径——本次未做任何路径枚举，遵守"robots 明确 Disallow 的不碰"红线。

## 弱口排查（均未命中）

- **移动端页面**：`m.zxgk.court.gov.cn` 存在 DNS 记录但连接被重置，无可用 H5 入口。
- **微信小程序/公众号后端接口**：公开检索未发现"中国执行信息公开网"小程序的后端域名或未授权可调的公开接口；只见到第三方付费聚合 API（如站长工具 `openapi.chinaz.net/v1/1014/creditblacklist` 失信黑名单查询、`/v1/1036/judgementdetailv4` 司法综合查询，均需 APIKey 按量付费）——属商业数据转售，非官方免费口，不符合"公开证据"定位。
- **瑞数 v5**：按红线不硬解；且本次卡点在瑞数之前的 GeoBL，解瑞数也无意义。

## 死在哪里

三层门，第一层就过不去：

1. **GeoBL（边缘 WAF）**：非中国大陆出口 IP 直接 403，连瑞数 JS 都加载不到。历史结论（GeoIP 封锁 + 瑞数 v5 + 逐查询验证码）依然成立，且第一层比记忆中更靠前。
2. 瑞数 v5（未到达，不评估）。
3. 逐查询验证码（未到达，不评估）。

## 未尝试（需授权或换环境）

- **境内出口重放**：中国大陆 IP 下 `zxgk.court.gov.cn` 是否仍 GeoBL、瑞数 v5 是否可被 browser-assisted 模式承载（参考已批准的 browser-assisted 交互墙应对模式：验证码墙出现即停并记录）。这是唯一可能把第一层门推开的变量。
- **用户自有设备代查**：登录态/境内网络均在用户侧，符合"公开数据、用户授权"边界。
- 微信客户端内实查官方小程序是否存在及抓包其后端域名（超出本次纯 HTTP 范围；且小程序查询大概率同样要求境内网络+微信登录态）。
- 付费商业 API（站长工具等）：按量付费、数据非实时，与本项目"公开免费证据"定位冲突，仅记录为备选。

## 建议

- 不建 `adapters/zxgk_*_adapter.py`。
- 若后续拿到境内出口或用户授权 browser-assisted：先复测 `GET /` 是否 200，再评估瑞数 v5 在 Playwright 下的行为（验证码墙出现即停）。
- 失信被执行人数据的免费公开替代：裁判文书网（wenshu，见同期 `wenshu-des-feasibility-20261021.md`，境内 IP 下有望打通）文书正文中的执行信息、各地法院官网公告。
