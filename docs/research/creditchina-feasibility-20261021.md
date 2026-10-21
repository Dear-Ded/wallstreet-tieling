# 信用中国 (creditchina.gov.cn) 适配器可行性报告 — 2026-10-21

**结论：plain HTTP 走不通。知道创宇 WAF 的 JS 防（HTTP 412）拦截全部动态路径；不重建可用 adapter，已有 `adapters/creditchina_adapter.py` 保持 BROKEN stub 仅作结构参考。**

实查时间：2026-10-21 14:05–14:15 左右（北京时间），plain `curl` HTTP 请求，桌面 Chrome UA，无登录、无 cookie、无签名伪造、无 WAF/验证码绕过。探针总数 5 次，单发低频，无扫描。

## WAF 指纹（知道创宇 JS 防）

412 挑战页特征（`/`、`/search`、候选 API 路径三处返回完全同构）：

- `<meta content="<随机串>" r="m">`
- 内联脚本：`$_ts=window['$_ts']; if(!$_ts)$_ts={}; $_ts.nsd=722; $_ts.cd="<数百字符混淆串>"; if($_ts.lcd)$_ts.lcd();`
- 外链混淆 JS：`/z9ItHZeV1nhb/0IdCO1Ghjkrh.d07207d.js`（实测可 200 取回，207,725 B，标准知道创宇 JS 防脚本，不含任何本站业务端点）
- 页尾：`<script>_$cf();</script>`

## 实查表

| # | 方法/URL | 结果 | 摘要 |
|---|----------|------|------|
| 1 | `GET https://www.creditchina.gov.cn/robots.txt` | **404**，4,747 B | 唯一通过 WAF 的路径：源站渲染的 404 页（含站点 keywords/description）。WAF 规则疑似未覆盖此路径；站方无 robots.txt（404 即"无声明"，不是 Disallow） |
| 2 | `GET https://www.creditchina.gov.cn/`（桌面 UA） | **412**，2,528 B | 知道创宇 JS 防挑战页（见上指纹） |
| 3 | `GET /search?keyword=华为` | **412**，2,682 B | 同上；与历史 412 结论一致 |
| 4 | `GET /z9ItHZeV1nhb/0IdCO1Ghjkrh.d07207d.js` | **200**，207,725 B | WAF 自身的挑战脚本可直取；无业务价值 |
| 5 | `GET /api/creditinfo/search?keyword=华为&page=1`（`Accept: application/json`，单发验证） | **412**，2,641 B | 候选 API 路径同样被挑战；该路径是否存在无法从 412 区分（WAF 在路由之前拦截） |
| 6 | wayback availability API（站外，不碰目标站） | 429 | 本出口 IP 被 archive.org 限流，归档取前端包的路子停 |

## 死在哪里

- **动态路径全灭**：`/`、`/search`、候选 `/api/*` 全部 412 → 拿不到搜索页 HTML/前端 JS bundle → 真实 XHR 端点与参数签名无从确认（候选 `/api/creditinfo/search` 只是"也被拦"，不能证实也不能证伪该端点存在）。
- 唯一能直取的是 WAF 自己的 JS（无业务信息）和源站 404 页。
- 执行 WAF JS 求过门票据 = WAF 绕过，红线内不碰。

## 未尝试（按红线/任务约束排除）

- 执行知道创宇 JS 防脚本伪造过门 cookie（WAF 绕过，不碰）
- 换 UA/指纹特征的系统性试探（任务要求单次验证，已做桌面 UA 一次；不扫）
- 路径枚举找未被 WAF 覆盖的 API（= 扫描，不做）
- 登录后维持会话（未获用户授权，不登录）

## 下一条没试过的路（按优先级）

1. **browser-assisted（已批准模式）**：真实浏览器可自动通过知道创宇 JS 防（非滑块/点选验证码，不触发"出现即停"）。浏览器内打开 `/search?keyword=` → 用开发者工具抓真实 XHR（确认搜索 API 的真实路径、参数、是否需要签名）→ 若端点与签名可复现，再按规约建可用 adapter（SafeResearchAdapter + `public_*` 注册 + field_contract + runtime_companion + focused test）。
2. 在 browser-assisted 可达的前提下，验证 `/api/creditinfo/search` 候选路径的真伪（本次 412 无法区分"路径不存在"与"被 WAF 拦"）。

## 建议

- `adapters/creditchina_adapter.py` 维持 BROKEN stub（docstring 已更新指向本报告），不删除——作结构参考。
- 本次之后不要再对该站做 plain HTTP 重试：WAF 指纹稳定，5 次探针结论一致，重试无意义且徒增被封风险。
