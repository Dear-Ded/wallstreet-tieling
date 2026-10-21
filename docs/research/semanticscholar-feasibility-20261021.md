# Semantic Scholar 可行性调查 — 可行，走通 (2026-10-21)

调查对象：`https://api.semanticscholar.org/graph/v1/` 公开 REST API（免 key）。

## 实测

1. **robots.txt**：`GET https://api.semanticscholar.org/robots.txt` → `{"error":"Not found"}`（无文件）。
   无 robots 限制；API 端点为官方公开文档接口（https://api.semanticscholar.org/api-docs），
   匿名配额 **100 req / 5 min**（有 key 1 req/s，本任务免 key）。

2. **作者搜索**：`GET /graph/v1/author/search?query=Geoffrey%20Hinton&fields=name,affiliations,paperCount,citationCount,hIndex,url,homepage&limit=2`
   → 200：`{"total":22, "data":[{"authorId":"2257301155","name":"G. Hinton","affiliations":[],...,"paperCount":41,"citationCount":959,"hIndex":11}, ...]}`。
   注意返回多条候选（同名/缩写变体），需按查询名做 exact/strong/review 三档匹配分级，
   绝不把第一条直接当事实。

3. **中文名检索**：`query=李飞飞` → 200，`total=934`，返回近似名变体（"飞飞 李"、"飞翔 李"、"飞 李"），
   paperCount/citationCount 字段齐全。**结论：中文名可检索，但同名率高**，subject_match_levels
   中 exact 要求姓名全字匹配，其余进 review 档供人工/下游判别。

4. **作者详情**：`GET /graph/v1/author/{authorId}?fields=name,affiliations,paperCount,citationCount,hIndex,url,homepage`
   → 200，字段齐全（含 `url` = semanticscholar 作者页、`homepage` 个人主页）。

5. **论文→合作者**：`GET /graph/v1/author/{authorId}/papers?fields=title,year,authors&limit=10`
   → 200，`data[].authors[]` 含 `authorId`+`name`，可抽取合作者去重（剔除本人）。

## 数据边界

全部字段均为 Semantic Scholar 公开图谱数据（论文元数据、公开引用关系），
无个人隐私字段。数据边界：`fully_public`。

## 构建要点

- 限速：保守 `min_request_interval=2.0s`（匿名配额 100/5min ≈ 1 req/3s 上限，2s 绰绰有余）。
- 请求流：search（取候选）→ detail（最优候选）→ papers(limit=10，合作者）。单次 query 最多 3 请求。
- 匹配分级：exact（姓名归一后全等）/ strong（缩写或单位交叉）/ review（其余）。
- 合作者只取近 10 篇论文的去重作者，避免超大合作论文（如高能物理千人作者）污染图谱；
  单篇论文 authors > 50 时跳过该篇（大科学协作噪声）。
