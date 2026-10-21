# Google Scholar 可行性调查 — 判死 (2026-10-21)

调查对象：无官方 API；实测一次即定结论，不恋战。

## 实测

1. **robots.txt 直接封搜索入口**：`GET https://scholar.google.com/robots.txt` →
   ```
   User-agent: *
   Disallow: /search
   Disallow: /index.html
   Disallow: /scholar
   Disallow: /citations?
   Allow: /citations?user=
   Disallow: /citations?*cstart=
   Disallow: /citations?user=*@    (email-based profiles)
   ```
   关键词发现路径（`/scholar?q=`、`/citations?view_op=search_authors`）全部被 `Disallow` 覆盖。
   SafeResearchAdapter 的 robots 检查会拦截任何自动化的搜索请求。

2. **唯一 Allow 的是 profile 深链**：`/citations?user=<USERID>` 允许抓取，但：
   - Google 不提供任何从姓名到 userId 的公开 API/索引端点（search_authors 本身就是 Disallow 的）；
   - 即使拿到 userId，datacenter 出口对 scholar.google.com 长期是 429/CAPTCHA 重兵封锁（业内共识，serpapi 等付费代理存在的根本原因）；
   - 本任务红线：不绕验证、不伪造身份。CAPTCHA 绕行出局。

## 结论：判死

关键词发现（姓名→学者）这条路被 robots.txt 堵死，userId 发现无合法公开入口。
学术线统一走 Semantic Scholar（公开 API、免 key，见 `semanticscholar-feasibility-20261021.md`）。
