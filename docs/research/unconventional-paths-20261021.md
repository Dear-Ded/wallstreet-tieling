# 搜索引擎索引片段聚合（商查不寻常路径）— 实测报告（2026-10-21）

> 目标：搜索引擎对 qcc.com / tianyancha.com / qixin.com 公司详情页有大量
> 索引，片段（snippet）常含注册资本/法人/地址等结构化信息；验证
> `site:qcc.com "有限公司"` 类查询是否可编程低频获取结构化片段。
>
> 铁律：零用户身份信息、零注册、不登录、不绕验证码、不碰付费 API；
> 搜索引擎结果页只做低频公开抓取；robots.txt 如实记录。

## 一、robots.txt 实测记录（2026-10-21，curl 直取）

| 引擎 | `User-agent: *` 相关条目 | 结论 |
|---|---|---|
| baidu.com / www.baidu.com | `Disallow: /`（全站，另对 Baiduspider/Googlebot/MSNBot 有 `Disallow: /s?`） | 程序化抓取 /s 结果页被 robots 明确禁止 |
| bing.com / www.bing.com | `Disallow: /search`、`Disallow: /Search`（另有一批 `/images/search?`、`/copilotsearch?q=` 等） | 程序化抓取 /search 结果页被 robots 明确禁止 |
| google.com / www.google.com | `Disallow: /search`（仅放行 `/search/about`、`/search/howsearchworks`） | 程序化抓取 /search 结果页被 robots 明确禁止 |

按本仓库 `SafeResearchAdapter._check_robots` 口径，三家 /search 结果页对
通用 bot 均为 `robots_txt_disallowed`——adapter 层会直接拒绝，连请求都不发。

## 二、低频公开抓取实测（证据）

共 4 次请求，每引擎 1~2 次、间隔 ≥12s，公开 HTML、无 Cookie/登录/验证码绕过。
原始 HTML 存外部证据目录（未提交仓库）：`/tmp/se_snippet_evidence/`。

### 1. 百度 —— 图形验证码硬拦截（判死）
- 请求：`GET www.baidu.com/s?wd=site:qcc.com "有限公司" 注册资本`
- 实测：HTTP 200 但 **302 跳转到 `wappass.baidu.com/static/captcha/tuxing_v2.html`**
  （`ak=c27bbc89afca0463650ac9bde68ebe06`），页面标题"百度安全验证"，
  正文"网络不给力，请稍后重试"。结构化字段命中 0。
- 卡点：裸程序化请求（数据中心出口 IP、无登录态）首跳即触发百度安全验证；
  **绕验证码是红线**，此路判死。

### 2. Bing —— `site:` 算子不可靠，拿不到目标站片段（判死）
- 请求 A：`GET www.bing.com/search?q=site:qcc.com "有限公司" 注册资本`
  → HTTP 200，约 13,800 个结果，`b_algo` 10 条**全部来自 sellfox.com /
  baike.baidu.com 等站外**，`site:qcc.com` 被静默忽略（0 条 qcc.com 结果）。
- 请求 B：`GET www.bing.com/search?q=site:qcc.com 深圳市腾讯计算机系统有限公司`
  → HTTP 200，但页面明示"**没有与此相关的结果**"（`b_algo` 0 条）。
- 卡点：Bing 对程序化请求的 `site:` 限定不稳定（时而忽略、时而零结果），
  片段来源不可控为目标站公司详情页；加之 robots 禁止 /search，判死。

### 3. Google —— 软拦截无结果（判死）
- 请求：`GET www.google.com/search?q=site:qcc.com "有限公司" 注册资本&hl=zh-CN`
- 实测：HTTP 200 但返回的是**重定向中间页**
  （"如果您在几秒钟内没有被重定向，请点击此处"），无任何搜索结果；
  结构化字段命中 0。robots 已 `Disallow: /search`。
- 卡点：裸程序化请求被软拦截；Google ToS 亦禁止未经许可的自动化查询。
  判死。

## 三、卡点汇总

1. **robots.txt 全灭**：三家对 `User-agent: *` 明确 Disallow 搜索结果页路径；
   按仓库既有 robots 门禁口径，adapter 不应发出请求。
2. **反爬全灭**：百度=验证码硬拦截（红线不可绕），Google=重定向软拦截，
   Bing=可达但 `site:` 算子对程序化请求不可靠。
3. **ToS 灰区**：三家 ToS 均限制/禁止自动化查询且无免 key 的文档化查询 API；
   不像 urlscan.io 有公开 API 可走"文档化调用"口径。
4. **片段质量假设未被证伪但也未被证实**：因连结果页都拿不到稳定目标站
   条目，"片段含注册资本/法人/地址"的结构化抽取无从验证。

## 四、结论：不建 adapter

`public_search_snippet_lookup` **不建**。任一搜索引擎的 `site:` 查询均不满足
"可稳定低频获取结构化片段"——三家分别死于验证码 / 算子不可靠 / 软拦截，
且 robots.txt 全部明确禁止。强行建 adapter 会违反仓库 robots 门禁与
"不绕验证码"红线。

registry 条目：无（adapter 未建，`core/connector_registry.py` 未动）。

## 五、诚实缺口与后续可选方向（本次不做）

- 仓库已有 `adapters/public_web_search_tool.py`（DuckDuckGo instant answer /
  自建 SearXNG 零配置 provider）：做的是通用公开搜索归一化，**不支持可靠的
  `site:` 站内限定 + 商查结构化片段抽取**，不能冒充本路径的替代。
- 可选后续（需单独立项实测）：Common Crawl 索引（CC-INDEX）按域名查
  qcc.com/tianyancha.com 抓取记录 → 从 WARC 抽详情页结构化字段；
  或用户自建 SearXNG 实例走其 JSON API（用户侧部署，非零成本）。
- 本次交付：仅本文档。测试计数：0 新增（无 adapter、无 focused test；
  未改动任何代码，现有测试套件不受影响）。

## 六、交付
- 新增：`docs/research/unconventional-paths-20261021.md`（本文）。
- 未新增 adapter / 测试 / registry 条目（见第四节判死结论）。
