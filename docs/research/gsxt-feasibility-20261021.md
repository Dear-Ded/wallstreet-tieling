# 国家企业信用信息公示系统 (gsxt.gov.cn) 适配器可行性报告 — 2026-10-21

**结论：plain HTTP 走不通。整站被 521 + `__jsl_clearance_s` JS 算术 cookie 挑战封锁；不建议建 `adapters/gsxt_adapter.py`。**

实查时间：2026-10-21 14:05–14:10 左右（北京时间），plain `curl` HTTP 请求，桌面 Chrome UA，无登录、无 cookie、无签名伪造、无 WAF/验证码绕过、无打码平台。

## 核心发现：连首页 HTML 都拿不到，挑战在 WAF 层

| # | 方法/URL | 结果 | 摘要 |
|---|----------|------|------|
| 1 | `GET https://www.gsxt.gov.cn/`（桌面 UA） | **521**，845 B | 整页是一个 `<script>`：用 JS 算术拼出 `document.cookie='__jsl_clearance_s=' + <算出的值>`，然后 `location.href=location.pathname+location.search` 重载。标准 JSL（加速乐/知道创宇系）JS cookie 挑战 |
| 2 | `GET https://www.gsxt.gov.cn/robots.txt` | **521**，同挑战页 | 连 robots.txt 都被挑战拦截，无法确认站方抓取声明 |
| 3 | `GET http://www.gsxt.gov.cn/` | **521**，703 B | HTTP 通道同样被挑战 |
| 4 | `GET https://gsxt.gov.cn/`（apex） | 连接被重置（curl 52，empty reply） | apex 直接 RST |
| 5 | `GET https://sh.gsxt.gov.cn/`（上海省级节点，单发） | **521**，849 B | 省级节点同属一套挑战，非仅国家门户 |

## 死在哪里

- **第一跳即死**：挑战发生在返回任何业务内容之前——拿不到首页 HTML → 拿不到 JS bundle → 无从得知企业查询的真实 XHR 端点与签名参数（timestamp/nonce/加密串）。本次"拆网站"目标在第一步即终止。
- 挑战要求执行混淆 JS 算出 `__jsl_clearance_s` cookie 值：用脚本算出来属于 WAF 绕过，红线内不碰；且该站历史情报还有**境外 IP 403**与**查询页极验 v4**两道墙（任务背景），即使过了 JS 挑战也大概率撞上。
- 省级节点同样 521：换省站分流的路子不通。

## 未尝试（按红线/任务约束排除）

- 执行/逆向 JSL JS 求 `__jsl_clearance_s`（WAF 绕过，不碰）
- Playwright 代理 browser-assisted 走查询流程——另一路 builder 的代理修复**未能由我实际验证**（仓库内无修复状态信号；本子智能体无 live browser），按任务约定不假设修好，本次未做
- 打码平台过极验 v4（红线：不接）
- 登录后维持会话（未获用户授权，不登录）

## 下一条没试过的路（按优先级）

1. **browser-assisted（已批准模式）**：Playwright 代理修好并经实测验证后，在真实浏览器里走一遍 `www.gsxt.gov.cn` 企业查询流程。JSL 挑战在真实浏览器中自动通过；若查询页弹出极验 v4 滑块/点选——**出现即停**，记录为"需用户侧过验证"，不硬解。若浏览器内可达，再抓 XHR 找真实查询端点与签名参数，届时建 adapter。
2. 替代公开源：企查查/天眼查官方开放平台（付费 API，见 `app-api-reverse-20261021.md`）；其数据即从 GSXT 等官方源聚合，合规路径是走官方 API 而非硬闯公示系统。

## 建议

- 不建 `adapters/gsxt_adapter.py`；`adapters/autonomous_sources.py` 里旧的 `query_gsxt_with_ocr`（ddddocr 路线）针对的是多年前的 `corp-query-search-1.html` 形态，已被 521 挑战整体作废，仅作历史参考。
- 待 browser-assisted 通道就绪后重评；重评前任何轮询式重试都是浪费（30 次/小时配额的说法已无意义——现在是 0 次）。
