# ORCID 可行性调查 — 判死 (2026-10-21)

调查对象：`https://pub.orcid.org/v3.0/search/?q=<name>` + record 拉取（免 key 公开 API）。

## 实测

1. **API 本身可通**：`GET pub.orcid.org/v3.0/search/?q=given-names:Geoffrey+AND+family-name:Hinton&rows=3`
   （`Accept: application/json`）→ 200，返回 `{"result":[{"orcid-identifier":{"uri":"https://orcid.org/0000-0002-8063-7209",...}}],"num-found":1}`。
   record 端点 `https://pub.orcid.org/v3.0/<orcid-id>/record` 为标准 JSON 视图，可取到教育/工作单位、论文 DOI、
   合作者信息（co-author via works）。

2. **robots.txt 一票否决**：`GET https://pub.orcid.org/robots.txt` →
   ```
   User-agent: *
   Disallow: /
   ```
   全域禁止自动化抓取。SafeResearchAdapter 框架在 query 前自动执行 `_check_robots()`，
   `can_fetch()` 返回 False 时直接返回 `robots_txt_disallowed` 空结果，不发请求。
   ORCID 主站 `orcid.org/robots.txt` 只屏蔽 /account、/oauth、/orcid-search/ 等私有路径，
   但本任务规定的数据入口（pub.orcid.org search API）被明确屏蔽。

## 结论：判死

- 红线："robots.txt Disallow 的不碰"。即使 API 返回 200，也不走。
- 即便将来 ORCID 放行 robots，也要注意：免 key 配额约 **20 req/day**（Anonymous API），
  超出需换 Personal Access Token——信息平权路线（零成本）上不合算。
- ORCID profile 页（orcid.org/<id>）是 JS 渲染，无 server-rendered 公开 HTML，可爬性也差。

## 替代

学术单位/合作者/论文线索由 Semantic Scholar 线覆盖（见 `semanticscholar-feasibility-20261021.md`），
两者字段重合度足够（affiliations、论文数、引用数、合作者可从论文 authors 反推）。
