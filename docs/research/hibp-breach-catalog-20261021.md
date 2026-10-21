# HaveIBeenPwned 可行性（2026-10-21）— 结论：API 死，公开名录 GO（已建 adapter）

## v3 API：判死
- 全部 v3 端点（/breachedaccount、/breach、/pasteaccount 等）都需要 API key。
  无 key 不建客户端，未尝试任何绕过。

## /PwnedWebsites 公开目录：可行
- GET https://haveibeenpwned.com/PwnedWebsites → 200，~1MB 服务端渲染 HTML 表格。
- 实测 1047 个 breach 行：`<tr id="<Name>">`，列 `td[data-name=breach|pwncount|date|breachDate]`
 （breach 名、pwn 计数、收录日期、泄露日期），附 `/Breach/<Name>` 链接。
- robots.txt：`/PwnedWebsites` 不在 Disallow 列表。
  Disallow 的是 /BreachSummary、/account/*、/unifiedsearch/* 等账号查询入口——
  这些本就属于红线，不碰。
- robots 解析注意：urllib.robotparser 解析该站 robots.txt 会因
  "Content-Signal:" 非标准行丢弃全部规则（实测 entries 为空），adapter 内用
  手写 Disallow 前缀检查替代。

## 数据边界（写死）
- adapter 只读公开 breach 名录：按**服务/厂商名**查"是否出现在公开名录"。
- 不查具体账号、不拉取泄露库内容、不碰 /account/*（robots Disallow + 红线）。

## 落地
- `adapters/hibp_breach_adapter.py::HIBPBreachCatalog`（SafeResearchAdapter，
  5s 限速，名录进程内缓存 24h，独立审计）。
- registry `public_hibp_breach_catalog`：implementation pack，
  EXPERIMENTAL + default_enabled=False，focused_test 指向
  tests/unit/test_hibp_breach_adapter.py（11 项）。
- `_extract` 新增 `hibp_breach_catalog` 分支 → `breach_signal` 实体；
  business_name fanout + 工厂注入已接。
