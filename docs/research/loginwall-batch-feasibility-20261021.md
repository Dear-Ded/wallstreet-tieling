# 登录墙/信誉墙批量复查 — 移动端/APP 拆解（2026-10-21）

任务：重攻 58.com + 批量复查 知乎 / 贴吧 / 美团 / 百家号 / LinkedIn。
原则：不登录（用户未授权）、不绕验证码、robots.txt 明确 Disallow 的不碰、只做公开证据。
判死标准：连续两条独立路径被同一堵墙拦下 → 判"需用户登录态"，写清要什么登录 + 用户侧下一步一句话。
所有网络探测均为 2026-10-21 当日单次低频请求（非扫描）。

---

## 1. 58.com ✅ 建 adapter（`public_fiftyeight_h5`）

背景：桌面站 www.58.com 对机房出口是 JA3 指纹级反爬，302 → 404.58.com。

试了什么：
- `GET https://m.58.com/`（iPhone Safari UA）→ 302 到 `https://m.58.com/bj/`（城市地理跳转，正常；`/bj/` 落页首次连接曾 tarpit 一次，重试正常）。
- `GET https://m.58.com/bj/zufang/`（手机 UA）→ **200，~467KB，服务端渲染，无登录墙/验证码标记**，~90 个 `<a class="list-item">`，含 infoid、uid、干净详情链接、标题、户型/区域、价格、广告标记。
- `GET https://m.58.com/bj/zufang/<infoid>x.shtml`（无 query 的干净 URL）→ **200，~104KB**：标题、price 字段均可解析，无登录门；电话号码不在服务端 HTML 里（点击展开，JS 渲染），**不提取**。
- `GET https://app.58.com/` → 302 Tengine 跳转。APP API 需要设备绑定的签名请求（app-signed），纯 HTTP 无法复现，未尝试——文档内记为 stop。
- `GET https://m.58.com/robots.txt`（200）：
  ```
  Allow: /shoujidaquan/*
  Disallow: /*?*      ← URL 禁止带 query：adapter 对所有 URL 断言无 "?"
  Disallow: /sou/*Q*  ← 手机搜索路径禁用：adapter 不支持关键词搜索
  ```
  分类列表页（`/bj/zufang/` 等）无 `?`，允许。

交付：`adapters/fiftyeight_h5_adapter.py`（SafeResearchAdapter，EXPERIMENTAL，default_enabled=False，
min_request_interval=5.0s；iPhone UA；city/channel 归一化防注入），字段：infoid / detail_url（无 query）/
title / addr / price / tag / image；`detail=True` opt-in 详情丰富（限前 5 条，同样限速）。
注册 `public_fiftyeight_h5`（field_contract + runtime_companion），focused test 8/8 绿。

边界：手机搜索 `/sou/` 被 robots 禁用 → 只有城市+频道浏览，无关键词搜索；APP 签名接口未复现；
详情页电话不渲染不提取。

## 2. 知乎 ✅ 建 adapter（`public_zhihu_public`）

试了什么：
- 热榜 API `GET https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=10&desktop=true` → **200，JSON**：`data[].target{title_area.text, excerpt_area.text, metrics_area.text(热度), link.url}`，标题/热度/问题链接均为公开信息。
- 用户公开资料 `GET https://www.zhihu.com/api/v4/members/<url_token>` → **200，JSON**：name / headline / avatar_url / gender / user_type / is_org / is_realname / org_verify_status / ip_info / url（尽调可用的身份元数据；粉丝数等字段此 variant 不返回）。
- 回答列表 `GET https://www.zhihu.com/api/v4/members/<token>/answers` → **401** `{"error":{"message":"第三方应用独立请求时，无此操作权限","code":602,"name":"AuthenticationInvalidClient"}}` → 内容级接口要登录态，不碰。

robots 语义：www.zhihu.com/robots.txt 只有 Googlebot/bingbot 等命名爬虫的规则，**没有 `User-agent: *` 通配组**；
按惯例对未命名客户端无约束。adapter 自定义 `_check_robots`：无通配组视为允许，有通配组则按其规则执行。

交付：`adapters/zhihu_public_adapter.py`（mode=hot / mode=profile；profile 的 keyword/url_token 校验防注入；
robots_checker 注入优先便于单测），注册 `public_zhihu_public`，focused test 8/8 绿。

Verdict：部分开通 —— 热榜 + 用户公开资料免登录可用；回答/文章列表 401。
**需用户动作（如要回答内容）：** 用户浏览器代管登录知乎账号后，由登录态通道抓取。

## 3. 贴吧 ❌ 判死 —— 需用户登录态

- `GET https://tieba.baidu.com/f?kw=李毅&ie=utf-8`（桌面 UA）→ **403**，页面含 `anquan.baidu.com` + "安全验证"。
- 同 URL（iPhone UA，独立路径）→ **403**，同样"安全验证"。

两条独立路径被同一百度安全验证墙拦下 → 判死。
**需什么：** 百度账号登录态（贴吧需百度账号）。
**用户侧下一步：** 在用户浏览器代管中登录百度账号（贴吧/百度同账号），或用户手机上提供目标贴吧帖子链接由登录态通道抓取。

## 4. 美团 ❌ 判死 —— 需用户登录态

- `GET https://bj.meituan.com/meishi/` → **301** → `https://www.meituan.com/win-together`（营销页，分类列表已下线/迁移），200 但无 POI 数据。
- `GET https://i.meituan.com/`（手机 UA）→ **301** → `https://i.meituan.com/mttouch/page/home` → **302**（继续跳转，无登录态拿不到数据）。

两条路径均无登录态可用数据；美团 POI/店铺数据接口（ptapi/apimobile）需要设备签名+登录态，纯 HTTP 无法复现。
**需什么：** 美团账号登录态（手机号+短信验证，风控严）。
**用户侧下一步：** 用户在其手机美团 App 上查到目标店铺/菜品信息截图发回，或浏览器代管登录美团账号（需用户实时收短信验证码配合）。

## 5. 百家号 ❌ 判死 —— 需用户登录态

- `GET https://baijiahao.baidu.com/` → **302** → `http://baijiahao.baidu.com/pcui/register/index`（作者注册页；内容消费入口对机房出口不可见）。
- 文章页 `GET https://baijiahao.baidu.com/s?id=1878697559018641227`（真实 URL，来自公开搜索结果）→ 200 / 48KB，但 **只有 `<title>`，正文不在服务端 HTML 里**（JS 壳；含 passport.baidu 引用与登录标记）。

两条路径均无正文 → 判死。
**需什么：** 百度账号登录态 + JS 渲染通道。
**用户侧下一步：** 用户浏览器代管登录百度账号后走渲染通道抓取，或直接提供文章在百度搜索的缓存/快照链接。

## 6. LinkedIn ❌ 判死 —— 需用户登录态

- `GET https://www.linkedin.com/in/williamhgates` → **HTTP 999**（1.5KB 拒绝页，IP 级）。
- `GET https://www.linkedin.com/company/linkedin` → **HTTP 999**。

两条路径同一堵 IP 级 999 墙 → 判死。公开 profile 免登录渲染已不存在（机房出口）。
**需什么：** LinkedIn 账号登录态。
**用户侧下一步：** 用户浏览器代管登录 LinkedIn 账号（注意异地登录风控，建议用户常用设备/网络），或接受仅用搜索引擎摘要（Bing/Google snippet）做弱证据。

---

## 汇总

| 站点 | Verdict | 交付 |
|---|---|---|
| 58.com | ✅ 开通（H5 免登录） | adapter `public_fiftyeight_h5` + test |
| 知乎 | ✅ 部分开通（热榜+用户资料） | adapter `public_zhihu_public` + test |
| 贴吧 | ❌ 需百度账号登录态 | 本文档 |
| 美团 | ❌ 需美团账号（短信）登录态 | 本文档 |
| 百家号 | ❌ 需百度账号登录态+渲染 | 本文档 |
| LinkedIn | ❌ 需 LinkedIn 账号登录态 | 本文档 |

变更文件：`adapters/fiftyeight_h5_adapter.py`、`adapters/zhihu_public_adapter.py`、
`tests/unit/test_fiftyeight_h5_adapter.py`、`tests/unit/test_zhihu_public_adapter.py`、
`core/connector_registry.py`、本文档。
