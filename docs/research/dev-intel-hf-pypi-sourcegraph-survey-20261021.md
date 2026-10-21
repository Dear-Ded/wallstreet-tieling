# 开发者线情报渠道可行性调查 — HuggingFace / PyPI / Sourcegraph（2026-10-21）

调查人：builder lane（feat/osint-acquisition）。结论：HuggingFace 全线走通并已建
`adapters/huggingface_adapter.py`；PyPI 两条路线均判死；Sourcegraph 判死不建。

## 1. HuggingFace — 可行，走通（BUILD）

- `GET https://huggingface.co/api/models?author=<username>`：免 key，200，
  返回该作者全部公开模型（modelId、likes、downloads、pipeline_tag、tags、
  createdAt）。不存在的 author 返回 200 `[]`。
- `GET https://huggingface.co/api/users/<username>/overview`：免 key，200，
  返回 fullname、type（user/org）、orgs（name/fullname）、numModels/
  numDatasets/numSpaces/numFollowers、details（简介）、avatarUrl、createdAt。
  不存在用户返回 404。注意：`/api/users/<username>`（无 /overview 后缀）返回 404，
  该端点不存在。
- robots.txt：`User-agent: *` / `Allow: /`，两条端点均允许。
- 判：username → 模型列表 / 组织归属 / 粉丝数 / 注册时间，全部走通。
  实测证据：`karpathy` → overview 200（fullname "Andrej K"，orgs
  compvis-community、llmc，numModels 7，followers 2052）；models 200
 （nanochat-d32、tinyllamas、774M_export…）。

## 2. PyPI — 判死（不建 adapter、不注册 connector）

两条路线都被红线卡死，证据：

1. **包→作者**：`https://pypi.org/pypi/<project>/json` 技术上走通
   （`/pypi/requests/json` → 200，含 author/author_email/maintainer
   字段，如 author_email `Kenneth Reitz <me@kennethreitz.org>`），但
   `https://pypi.org/robots.txt` 明确 `Disallow: /pypi/*/json` 和
   `Disallow: /pypi/*/*/json`。本项目 `SafeResearchAdapter._check_robots`
   对该路径直接返回 False（robots_txt_disallowed），红线"robots.txt
   Disallow 的不碰"——此路判死。
2. **按人名搜包**：`https://pypi.org/search/?q=...` 同样
   `Disallow: /search*`，且搜索 UI 本就没有 author 过滤字段
   （只能按关键词/分类搜）。此路判死。

结论：PyPI 唯一合法的公开信息渠道（JSON 元数据 API）被 robots.txt
明确禁止使用；合法路径下"人名→包"无任何端点。两条全判死。

## 3. Sourcegraph — 判死（不建，仅备选调查）

- `GET https://sourcegraph.com/.api/search/stream` 免 key 技术上走通
  （200，SSE event 流），commit-author 查询如
  `q=context:global type:commit author:karpathy` 有结果。
- 但 robots.txt 明确 `Disallow: /search?q=*`：搜索 UI 的后端正是该流式
  API，用程序化方式抓取搜索结果属于绕过该 Disallow 的精神，红线踩线。
- 情报价值弱：commit author 映射的是 commit 中的姓名/邮箱（多为
  noreply 占位地址），没有稳定的人→身份映射；人名撞车时无法归一，
  需要额外跳步，且未经身份验证的配额历史上 429 频繁，不适合管道。
- 判：技术可通但合规踩线、价值/维护比差，不建。
