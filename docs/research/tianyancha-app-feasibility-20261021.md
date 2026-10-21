# 天眼查 / 企查查 APP 端可行性报告 — 2026-10-21

**结论：无免登录可用接口；不建 adapter。官方开放平台均为付费（只记录，不采购）。**

实查时间：2026-10-21 14:25–14:35（北京时间），plain HTTP，无登录、无 cookie、无签名伪造、无 WAF 绕过。

前置阅读：`app-api-reverse-20261021.md`（APK 静态逆向已判死：天眼查重度加固；企查查包未找到；官方 API 付费）。

## 本次实查：免费/试用面与 webview H5

| # | 方法/URL | 结果 | 摘要 |
|---|----------|------|------|
| 1 | `GET https://www.qcc.com/search?key=华为`（iPhone UA） | 200，23 KB，但**无数据** | 返回阿里云 WAF JS 挑战页（`acw_sc__v2` cookie + `renderData` 解混淆脚本），正文零企业数据；plain HTTP 拿不到任何结果 |
| 2 | `GET https://m.tianyancha.com/search?key=华为`（iPhone UA） | **419**，102 KB | 天眼查反爬状态码，请求被拒；H5 移动站同样不给免登录面 |
| 3 | 企查查开放平台免费试用 | 存在 20 次试用，但**需企业实名认证 + 创建应用** | 属"付费接口的试用"，按红线只记录不采购；且实名主体是用户企业，非助手可代办事项 |
| 4 | 天眼查 APP webview H5 未加固接口 | 未发现 | APP 本体此前已确认重度加固（`classes.dex` 13KB loader + `libdu.so` + `libJMEncryptBox.so`），静态无入口；H5 端（#2）同样被拦 |

## 官方付费 API（记录，不采购）

- **天眼查**：`http://open.api.tianyancha.com/services/open/`，Header `Authorization: <token>`，167+ 接口（`search/2.0`、`ic/baseinfoV2/2.0` 含电话/邮箱、`jr/lawSuit/3.0` 等），Python SDK `iamsk/tianyancha`。
- **企查查**：`https://api.qichacha.com/`，Query `key=<AppKey>` + Header `Token=MD5(key+Timespan+SecretKey)`（32 位大写）+ `Timespan` 时间戳；多数接口 0.50–1.00 元/次，开通需企业实名。

## 下一条路

1. **browser-assisted**（需用户授权）：企查查 `qcc.com/search` 在真实浏览器 + 用户自有登录态下可正常用；可按 sogou_wx/dianping 模式评估（用户侧维持会话，助手只读公开结果页）。这是目前唯一不花钱的口子。
2. **预算批准后**：接入天眼查官方 API（SDK 成熟，推荐）或企查查官方 API。
3. **Frida 动态脱壳**：天眼查 APP 动态分析，投入大、产出不确定，排最后。

## 建议

- 不建 adapter；本次报告 + `app-api-reverse-20261021.md` 即交付物。
- 若用户后续问"天眼查/企查查能不能接"，标准答复：免费路线只有 browser-assisted（企查查，需授权）；干净路线是官方付费 API（等预算）。
