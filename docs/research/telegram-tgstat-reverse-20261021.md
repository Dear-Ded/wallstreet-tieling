# tgstat.com 逆向挖掘记录（2026-10-21）

目标：把 tgstat.com 作为 Telegram 公开频道**搜索入口**（用户要求把"纸飞机群组"纳入信息源后的加码挖掘）。

红线：不登录、不碰私有群组/私聊、不绕验证码。以下全部是公开面、无登录态的 plain HTTP 复现。

## 1. 前端 JS 定位到的搜索端点

- 搜索页（`https://tgstat.com/search?search=test`）内联脚本：
  `new TopSearch({ requestUrl: '/channels/global-search' });`
- `app.js`（1.1MB，minified）中 TopSearch 类逻辑：
  `POST /channels/global-search`，body `data={query: <文本>}`，
  期望返回 JSON `{"status": "ok", "html": "..."}`（结果直接注入下拉容器）。

## 2. Plain HTTP 复现结果（全部需登录，死路）

| 端点 | 方法/参数 | 返回 | 结论 |
|---|---|---|---|
| `/channels/global-search` | POST `query=durov` + session cookie + `X-CSRF-Token` | `{"status":"restricted","html":"…Authentication Required…Please log in to continue using TGStat"}` | 登录墙 |
| `/search`（帖子搜索表单） | POST `_tgstat_csrk` + `q=durov` | HTML "Sign in to access this page" | 登录墙 |
| `/channels/search`（频道高级搜索） | POST XHR `_tgstat_csrk` + `q=durov` | 同上 restricted JSON（429 样式卡片） | 登录墙 |
| `/channels/search` | POST 表单式（无 XHR 头） | 200，重渲染搜索表单，无结果 | 结果走 XHR=登录墙 |

结论：**tgstat 的全部搜索入口都需要登录账号**。没有尝试登录（红线），没有尝试绕验证码。
到此为止是基于证据的停止，不是没试。

## 3. 公开可用的部分（已落地为 adapter 能力）

- `GET https://tgstat.com/channel/@<handle>` → 200，服务端渲染，**免登录**。
  robots.txt 明确允许（仅 ban `/*/quotes`、`/*/share`、`/stat/*` 等）。
- 可稳定提取：精确订阅数（`<h2 class="mb-1 text-dark">10 303 163</h2>` + subscribers 标注）、
  频道简介（`<meta name="description">`）、**关联 handle**（`<h1>` 下 `btn-outline-info` 的
  `@xxx` 按钮 = 频道主的其他公开频道，天然的"种子 handle → 关联 handle"发现路线）。
- 实测 `https://tgstat.com/channel/@durov`：subscribers_exact=10303163，
  related_handles=[feed, lean, paul, rove, snow]。
- 已实现为 `TelegramChannelLookup.enrich_with_tgstat(handle)`（opt-in，
  `query_channel(..., enrich=True)`），独立 5s 限速 + 独立审计记录。

## 4. 其他试过的死路

- telemetr.io：301 跳登录。死路。
- DuckDuckGo html 端点：本机出口超时（exit 28）。死路。
- Bing RSS：`site:` 操作符被忽略；HTML SERP 在数据中心出口下不返回 t.me 结果链接。死路。
- tgstat 付费 API（"Search API of posts"）：需付费 key，未走。

## 5. 最终架构

- 核心：`t.me/s/<handle>` 公开预览（免登录、服务端渲染、20 条帖子）→ `query()` / `query_channel()`。
- 增强：tgstat 公开频道页（精确订阅数 + 关联 handle）→ `enrich=True`。
- 关键词→handle 的发现：仅支持直接 handle 解析（`query("durov")` → `t.me/s/durov`）；
  无效 handle 返回结构化 `channel_found: false`，不做搜索引擎猜测。
