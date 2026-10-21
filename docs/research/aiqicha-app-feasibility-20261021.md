# 爱企查 APP 端 API 逆向可行性报告 — 2026-10-21

**结论：时间盒内走不通。未拿到官方 APK，未拆到任何类/方法/签名算法；不建议建 `adapters/aiqicha_app_adapter.py`。**

实查时间：2026-10-21 14:05–14:33（北京时间）。红线：APK 只从官方渠道（应用宝/官网/APKPure 官方包）；不登录、不碰付费接口、不绕验证码。

前置阅读：`aiqicha-feasibility-20261021.md`（网站端已判死：aiqicha.com 301 到 aiqicha.baidu.com，全被百度 heicha JS 挑战 + 登录门拦）。

## 本次尝试：官方 APK 获取（卡在第 0 步）

| # | 动作 | 结果 |
|---|------|------|
| 1 | APKPure `d.apkpure.com/b/APK/<pkg>?version=latest`，6 个候选包名 | 全部 404：`com.baidu.aiqicha`、`com.aiqicha`、`com.aiqicha.app`、`com.baidu.aiqichacha`、`cn.com.aiqicha`、`com.qcc.enterprise`（后者为顺手验证企查查，同样 404） |
| 2 | 站内/全网搜索 "爱企查 apkpure"、应用宝详情页、酷安包名 | 无 APKPure 详情页；无应用宝详情页 URL 可用；包名未在任何可信渠道确认 |
| 3 | 官网 `aiqicha.baidu.com` 下载页 | 同网站端结论：heicha 门，无 plain HTTP 可达的下载入口 |
| 4 | GitHub 开源情报（爱企查 APP 抓包/签名） | 无公开的 APP 端 API/签名实现；已知爬虫均为网站端路线，已被 heicha 判死 |

**精确卡点**：官方 Android 包名未确认 → APKPure 无收录（疑似百度系应用未上架/被下架，企查查同样缺席 APKPure）；官网下载页被 heicha 拦；无 APK 就没有静态逆向的起点。

## 假设（未验证）

- APP 端 API 可能不走 heicha（任务出发点），但无任何证据证实或证伪——需要 APK 或真机抓包才能回答。
- 百度系 APP 普遍使用自有加固 + 接口签名，即使拿到 APK 也可能需要动态脱壳（参考天眼查：`classes.dex` 13KB 纯 loader + `libdu.so` 加固，见 `app-api-reverse-20261021.md`）。

## 下一条路（按成本排序）

1. **用户提供 APK**：让用户从其手机（已装爱企查）导出 APK，或从应用宝/官网手动下载后传文件——成本最低，官方包可信。
2. **Frida 动态**：在用户真机/云手机上装官方 APP，抓包看 API host + 签名参数（需用户配合或单独授权设备操作）。
3. **旧版本 APK**：官网历史版本/第三方存档（非官方渠道，红线内不可直接采用，仅作签名算法参考需谨慎）。
4. 若拿到 APK：jadx 静态 → 找 `http`/`okhttp` 调用点、签名类（关键词：`sign`、`token`、`ts`、`appkey`、`getSign`）；加固则转 Frida hook 签名函数。

## 建议

- 不建 adapter；本报告即交付物。
- 爱企查在三大商业平台中是唯一"基础查询免费、门槛低"的一家（第三方导航站口径），APP 端仍是值得挖的口子——建议等用户提供 APK 后重启本任务。
