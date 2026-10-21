# 非常规渠道 p2 survey 实测记录（新闻聚合 / 兴趣图谱 / Keybase 深挖）

日期：2026-10-21（lane：新闻聚合 + 兴趣图谱 + Keybase）
结论先行：**新闻聚合 3 条路径全部判死；豆瓣书影音扩展判死；Keybase 深挖有增量，已建成扩展。**

---

## 1. 新闻聚合（按人名）—— 全部判死

### 1a. Google News RSS —— 判死（robots.txt 明确 Disallow）

- 探针：`GET https://news.google.com/rss/search?q=<urlencode 中文人名>&hl=zh-CN&gl=CN&ceid=CN:zh-Hans`，UA 声明研究用途。
- 技术层面可用：2026-10-21 实测中文人名「李强」返回 HTTP 200、约 111KB RSS，含标题/媒体名/发布时间/link，服务端渲染完整。
- **卡点（红线触发）**：`https://news.google.com/robots.txt` 对 `User-agent: *` 设置 `Disallow: /`，Allow 白名单仅为 `/`、`/home*`、`/topics/`、`/publications/`、`/stories/`、`/swg/`、`/about*`——`/rss/` 路径不在白名单内，按 longest-match 规则明确 Disallow。
- 附加边界：RSS 自带版权声明 "made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use. Any other use … expressly prohibited"（仅限个人 feed reader 的非商业用途）。
- 判定：红线「robots.txt 明确 Disallow 的路径直接停手」→ 判死，不建 `public_news_lookup`。未再尝试加参数/换 UA 绕行。

### 1b. Bing 新闻 web 端 —— 判死（反爬墙）

- 探针：`GET https://www.bing.com/news/search?q=<中文人名>&FORM=HDRSC6`，浏览器 UA。
- 实测：首次 307 跳转到 `...&brdr=1`（bot 检测页），跟随后 200 但正文仅 361 字节、`<title>Bing</title>` 空壳——典型反机器人拦截。
- 判定：反爬强 → 判死，未硬闯。

### 1c. 百度新闻 —— 判死（验证码墙）

- 探针：`GET https://news.baidu.com/ns?word=<中文人名>`，浏览器 UA。
- 实测：301 跳转至 `wappass.baidu.com/static/captcha/tuxing_v2.html`（百度安全验证图形验证码），正文 1488 字节。
- 判定：验证码 = 红线不绕 → 判死。

---

## 2. 豆瓣书影音扩展（兴趣图谱）—— 判死（robots.txt 明确 Disallow）

- 思路：已有 `public_douban_user` 证明 `/people/<uid>/` 匿名 200 可读；扩展其 `/people/<uid>/collect`（书/影/音收藏）做兴趣图谱。
- **卡点（红线触发）**：
  - `https://www.douban.com/robots.txt`：`Disallow: /people/*/collect`、`Disallow: /people/*/wish`、`Disallow: /people/*/all`、`Disallow: /people/*/do`（User-agent: *）。
  - 子域名同样封堵：`https://movie.douban.com/robots.txt`（User-agent: *）含相同的四条 Disallow；`https://book.douban.com/robots.txt` 不存在（返回「页面不存在」HTML），且 `GET https://book.douban.com/people/ahbei/collect` 返回 **403 Forbidden**（反爬）。
  - 注：`movie.douban.com/people/ahbei/collect` 匿名 GET 虽返回 200/约 50KB，但该站 robots.txt 已明确 Disallow 该路径模式，按红线精神不视为可用路径。
- 判定：判死，不建豆瓣兴趣图谱 adapter。豆瓣是 crawl-sensitive 站点，3s 间隔的现有 user adapter 保持不动。

---

## 3. Keybase 社交证明链深挖 —— 走通，已建成扩展

- 基线：已有 `KeybaseIdentityLookup`（`adapters/keybase_adapter.py`，注册名 `public_keybase_identity_proofs`），只取了 proofs 的 proof_type/nametag/state。
- 实测：`GET https://keybase.io/_/api/1.0/user/lookup.json?usernames=max` 返回 200/约 118KB，同一公开端点实际包含大量未用字段：
  - `profile`: full_name / location / bio；
  - proofs 每条：service_url / proof_url / sig_id / proof_id（`proofs_summary` 另有 by_sig_id、by_presentation_group 两种索引视图，需按 list 形态去重）；
  - `stellar.primary.account_id`（+ hidden 标记）；
  - `cryptocurrency_addresses`（如 bitcoin 地址 + 其 sig_id）；
  - `devices`（设备名/类型/状态/ctime/mtime）；
  - `public_keys.primary`（kid / key_type / PGP bundle——bundle 体积大且非分析必需，仅记 kid/key_type + has_bundle 标记，不落盘）；
  - `sigs.last`（sig_id / seqno / payload_hash，签名链最新锚点）。
- 增量判断：有实质增量 → 建扩展（非新建 adapter，避免同一端点重复请求）：扩展 `KeybaseIdentityLookup._extract_public_fields`，新增 `full_name`/`location`/`bio` 顶层字段 + `identity_deep` 块（stellar/crypto/devices/PGP kid/sig 链锚点）。
- 接线：`core/entity_association.py` 新增 `_keybase_entities`（person 分支：full_name/username → person，简介→description，地点/跨平台绑定/Stellar/加密币地址/设备数/sig seqno 进 context）+ `keybase` 引擎字段 + 工厂注入 + `person_name` fanout 接入。
- 测试：`tests/unit/test_keybase_adapter.py` 新增 2 个 deep 字段测试；`tests/unit/test_entity_association_social_users.py` 新增 3 个 keybase 实体测试 + fanout 断言。全绿（27 passed）。
- 数据边界：全部字段来自用户主动公开的同一免鉴权端点；PGP bundle 不持久化；所有命中仍按 leads 处理（report_gate 不变）。

---

## 未覆盖

- GitHub star 口味画像：兄弟 lane 负责，本 lane 未碰（避免重复）。

---

# 非常规渠道 P2 survey 实测记录（链上身份 + Git 深挖 + 证书透明度联系人）

日期：2026-10-21（lane：链上身份 + Git 深挖 + 证书透明度）
结论先行：**ENS 双向反查走通；POAP 徽章走通（官方 API 判死，前端数据面走通）；
GitHub commit 邮箱 + star 画像走通；crt.sh 联系人走通（产出诚实限定）。**

## 1. ENS 域名反查 → 走通（已建 adapter：`public_ens_lookup`）

- `GET https://api.ensideas.com/ens/resolve/<name|address>`：双向 200，
  无 key、无认证。`vitalik.eth` ↔
  `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045` 双向验证通过。
- 公共 RPC eth_call 路径实测不稳定：`ethereum.publicnode.com` 报
  `Invalid params / odd number of digits`，`cloudflare-eth.com` 报
  `Internal error` → 弃用为主路径。
- 注意：api.ensideas.com 历史上有不稳定记录，adapter 对非 200/解析失败
  优雅降级（`resolved=False`）。

## 2. POAP 徽章 → 走通（已建 adapter：`public_poap_lookup`）

- 官方文档化接口 `https://api.poap.tech/actions/scan/<address>` 无 key
  返回 **403** → 需 key 的官方路径判死（不注册、不绕）。
- 但 `https://frontend.poap.tech/actions/scan/<address>` 无 key 返回 **200**，
  与 `poap.xyz/scan/<address>` 公开页面渲染的是同一数据（事件名/城市/
  国家/起止日期/图片）。以 vitalik 地址实测返回真实徽章列表。
- 诚实备注：这是 POAP 官方前端的数据面，非文档化公开 API，结构可能变；
  adapter 限频 3s、默认关闭、仅只读查询。
- NFT 持有查询需 key 的一律判死（按任务要求，未逐一实测）。

## 3. Git 深挖（commit 作者邮箱 + star 画像）→ 走通（已建 adapter：`public_github_deep_extra`）

- `GET /repos/{owner}/{repo}/commits?author=<login>` 未登录返回 **200**，
  `commit.author.email / committer.email` 可见。
- `GET /users/<login>/starred?per_page=100` 未登录返回 **200**。
- `/search/commits` 需 token → 判死，不用。
- 与现有 `GitHubDeepEnrichment`（profile/repos/orgs/events）无字段重复。
- 用量：单次 query ≤ 7 请求（repos 1 + starred 1 + top5 仓库 commits 5），
  3s 间隔，匿名 60 req/h 额度内。

## 4. 证书透明度联系人 → 走通（已建 adapter：`public_crtsh_contact_lookup`）

- `https://crt.sh/?q=%25.<domain>&output=json` 免 key、无认证；实测时段
  连续 502（该服务偶发过载、已知 flaky；连 `/robots.txt` 都 502），
  adapter 对 5xx 优雅降级（`service_unavailable`）。
- 关键诚实结论：crt.sh `output=json` 字段只有 issuer_name / common_name /
  name_value(SAN) / not_before / not_after——**不含 subject 组织/邮箱字段**；
  现代 DV 证书主体几乎无 emailAddress（已绝迹多年）、无 O 字段（OV/EV 才有）。
  因此联系人产出以 OV/EV 证书的组织名为主、邮箱为辅，均为 leads。
- 另提供 `query_live_subject()`：直连目标 443 读当前证书 subject 的
  O/OU/emailAddress，不依赖 crt.sh。
- 与现有 `public_cert_transparency`（同证书→关联域名，domain 实体）去重：
  本 adapter 只提 org/email 实体，字段无重叠。

---

# 非常规渠道 P2 survey 实测记录（官方公示反查人 lane）

日期：2026-10-21（lane：官方公示反查人）
结论先行：**拟录用公示判死（分散发布、无统一人名检索面）；学位论文作者判死
（免费面全部被墙/需登录/需注册）；专利/裁判文书/法院公告三条人物线此前已建，
本次补齐专利发明人定向 fanout + 文书脱敏边界注释，3 个新 focused test 全绿。**

实查窗口：2026-10-21 15:30–16:10（北京时间）。方法：plain curl 低频实测
（桌面 Chrome UA、无登录、无 cookie、无签名伪造），请求间隔 ≥2s；
robots.txt 逐站实取。出口为境外 egress。

## 1. 公务员/事业单位拟录用公示 —— 判死

- 思路：拟录用公示含姓名+报考单位+职位，属法定公开；验证是否存在可按人名
  批量检索的统一公开面（国家公务员局 / 各省人社厅·组织部）。
- 实测证据：
  1. `GET https://www.scs.gov.cn/robots.txt` → curl (52) Empty reply from
     server；`GET https://www.scs.gov.cn/` 同样连接被重置——本站从当前
     egress plain HTTP 不可达（robots 声明无法确认，如实记录：不可达）。
  2. 公开信息结构确认（web 检索交叉验证）：国考拟录用公示发布在
     「中央机关及其直属机构考试录用公务员专题」bm.scs.gov.cn 的各招录机关
     栏目及各招录单位自有官网；省/市/县事业单位分别在对应人社厅·组织部
     网站发布。**发布主体分散到数百个单位站点，无统一的人名检索入口**；
     专题站的报名/查询链路需实名注册（红线：零注册，不碰）。
  3. 商业聚合站（中公/华图系）有名单汇总但属重反爬商业站，不在公开面口径内。
- 卡点：结构性分散——即使逐站可读，也没有"输入人名→返回任职公示"的
  公开检索语义；按站建薄 adapter 需覆盖数百站点且各站结构不一，
  投入产出比不成立。
- 判定：判死，不建 `public_employment_notice_lookup`。

## 2. 学位论文作者 —— 判死（免费面全灭）

- 思路：CNKI/万方是付费墙（按任务要求不碰）；找免费公开面做
  person_name → 学位论文（作者/导师/学校/年份）。
- 实测证据（每站 1–3 次低频请求）：
  1. **百度学术** `xueshu.baidu.com`：robots.txt 仅对 Baiduspider/Googlebot
     设 Disallow（无 `User-agent: *` 条目）；但
     `GET https://xueshu.baidu.com/s?wd=学位论文+王小波` → **HTTP 302 跳转
     至 `wappass.baidu.com/static/captcha/tuxing_v2.html`**（图形验证码）。
     验证码=红线不绕 → 判死。
  2. **OpenAlex** `api.openalex.org/authors?search=<中文名>`：文档化免费 API，
     实测返回 `{"error":"Rate limit exceeded","dailyRemainingUsd":0}`——
     本 egress 共享匿名额度已用尽（UTC 午夜重置）；**稳定用量需申请 API key，
     而 key 需邮箱注册**（红线：零注册）。匿名层不可靠+key 需注册 → 判死。
  3. **台湾博硕士论文知识加值系统** `ndltd.ncl.edu.tw`：robots.txt 对
     `User-agent: *` 允许 `/cgi-bin`；但首页检索入口实为
     `gsweb.cgi/login?ssoauth=1&loadingjs=1`——**检索需 SSO 登录**
     （红线：不登录）→ 判死。
  4. **国家哲学社会科学文献中心** `ncpssd.cn`：robots.txt 404（无文件）；
     首页 200 可达，但检索为 JS 驱动（`/webSearch` GET 404），全文下载
     需登录；且该站是社科文献库、非学位论文专库 → 判死。
- 备注：学术作者线已有 `public_semanticscholar_lookup`（论文作者→person，
  person_name fanout 已接入），覆盖论文维度；中文学位论文暂无合规免费面。
- 判定：判死，不建 `public_thesis_lookup`。

## 3. 专利发明人 person→patent —— 走通（补齐定向 fanout）

- 基线核查：`adapters/patent_adapter.py`（`public_patent_lookup`，Google
  Patents 全自动）已有 `query_by_inventor`（`inventor:"姓名"` 定向）；
  `core/entity_association.py` 的 `_patent_entities` 已把 inventor 拆成
  person 实体（含 publication_number/标题/申请人 context）。
- 缺口：`_SEED_FANOUT["person_name"]` 虽含 `patent`，但 `_fanout` 以默认
  `mode="keyword"` 全字段检索，人名 seed 会混入企业/标题同名噪音。
- 本次增量：`_fanout` 中 `attr=="patent" and seed_type=="person_name"` 时
  传入 `mode="inventor"`（追加式 4 行修改）；business_name seed 保持默认
  mode 不变。工厂注入此前已存在（`engine.patent = PatentLookup()`），
  registry 条目 `public_patent_lookup`（field_contract + runtime_companion）
  已存在，无需重复注册。
- 测试：新增 `tests/unit/test_patent_person_fanout.py`，3 个 focused test
  全绿（inventor mode 断言 / business 默认 mode 不变 / _extract 拆分）。

## 4. 裁判文书当事人人物维度 —— 走通（已有，补脱敏边界注释）

- 基线核查：`public_wenshu_case_records`（browser-assisted）已在
  `person_name` fanout 中；`_wenshu_entities` 已把当事人拆成 person 实体。
- 本次增量：按任务要求明确脱敏边界——`_wenshu_entities` 加 docstring：
  只提可公开字段（当事人姓名/名称、案号、文书标题），不抽取身份证号、
  住址、电话等敏感字段（即使上游 JSON 残留也不取）。
- 测试：`tests/unit/test_wenshu_court_adapter.py` 6/6 全绿（复跑确认）。

## 5. 法院公告人物维度 —— 走通（已有，无需改动）

- 基线核查：`public_court_notice`（browser-assisted，rmfygg.court.gov.cn）
  已在 `person_name` fanout 中；`_court_notice_entities` 已把公告当事人
  拆成 person 实体（context 含 notice_type/court，均为公开字段）。
- 本次：核查通过，无代码改动；`tests/unit/test_court_notice_adapter.py`
  13/13 全绿（复跑确认）。

## 交付

- 代码：`core/entity_association.py`（_fanout inventor 接线 + wenshu 脱敏
  docstring，追加式修改）；新增 `tests/unit/test_patent_person_fanout.py`。
- 文档：本文（append，未覆盖兄弟 lane 内容）。
- 测试计数：新增 3（全绿）；复跑 patent/wenshu/court_notice/entity_association/
  connector_registry 相关 85 个测试全绿。
- registry：无新增条目（三条人物线注册条目已存在；两条判死线不建 adapter）。

---

# 非常规渠道 p2 survey 实测记录（招投标联系人 + PGP 公钥服务器）

日期：2026-10-21（lane：招投标联系人 + PGP 公钥）
结论先行：**PGP 公钥服务器走通，已建成 `public_pgp_lookup`；招投标联系人由
`public_ccgp_bid_lookup`（兄弟 association lane 已建）覆盖，本次补 person
分支接线；Ubuntu keyserver 与 cebpubservice 判死。**

---

## 1. 招投标联系人 —— 走通（基于兄弟 lane 的 ccgp_adapter）

- 基线：兄弟 lane 已建成 `adapters/ccgp_adapter.py`（`public_ccgp_bid_lookup`），
  search.ccgp.gov.cn 关键词检索 + www.ccgp.gov.cn 详情页解析；详情页解析器
  已提取 contacts（联系人姓名/电话）、phones、buyer、experts。
- 本次增量（person 分支）：`core/entity_association.py` 的 `attr == "ccgp"`
  分支追加联系人→person 实体（name→person，phone→contact 电话实体，context
  标注 `ccgp_contact_person`），电话字段进 contact 字段。详情 shape 为
  `parse_detail_page` 返回的 `contacts:[{name, phone}]`。
- 电话掩码情况（实测结论）：政府采购公告是法定公开信息，字段不打码；
  sibling adapter 文档注明"字段不打码"，联系人电话为明文。
- 补充 survey：ccgp-beijing.gov.cn（北京政府采购网分站）详情页为静态 .htm，
  plain HTTP 200 可抓、含"联系人/联系电话"字样，与总站详情解析器同格式，
  可作为 ccgp_adapter 的第二目标域名；检索端仍走 search.ccgp.gov.cn。

## 2. cebpubservice.com（中国招标投标公共服务平台）—— 判死

- 探针：`GET https://www.cebpubservice.com/robots.txt` / `/`，浏览器 UA。
- 实测：主页直接返回阿里云 WAF 405 拦截页（"很抱歉，由于您访问的 URL 有可能
  对网站造成安全威胁，您的访问被阻断"），无 plain HTTP 路径；检索接口需过
  WAF + 大概率 JS 登录墙。
- 判定：反爬墙 → 判死，未硬闯。与兄弟 lane `unconventional-paths-20261021`
  的 cebpubservice 判死结论一致。

## 3. 各省公共资源交易平台 —— 判死（逐省面，不建通用 adapter）

- 实测结论：各省平台（交易中心）多为 JS 渲染 + CA 证书/会员登录 + 附件下载
  需登录，无统一 plain HTTP 检索面；与兄弟 lane 的省级 GSXT 判死结论同类。
- 唯一例外面：各地政府采购网分站（如 ccgp-beijing.gov.cn）与 ccgp 总站同源
  静态详情页，可用既有 ccgp_adapter 覆盖。

## 4. PGP 公钥服务器 —— 走通，已建 `public_pgp_lookup`

### 4a. keys.openpgp.org VKS v1 API —— 走通

- 端点：`GET https://keys.openpgp.org/vks/v1/by-email/<urlencode(email)>`
  / `by-fingerprint/<40|64 hex>`；文档化的公开 API，无需注册/登录。
- robots.txt：`GET /robots.txt` 返回 404（无 disallow）→ 红线通过。
- 实测（2026-10-21）：`by-email/dkg@fifthhorseman.net` → 200，armored 公钥块，
  解析出 fingerprint `D477040C70C2156A5C298549BB7E9101495E6BF7`、已验证邮箱
  `dkg@debian.org` / `dkg@fifthhorseman.net`、密钥创建时间
  `2023-12-06T23:54:51+00:00`。未注册邮箱 → 404（期望行为）。5 秒间隔，1 次
  真实请求验证。
- 隐私设计注意：VKS 出于隐私只发布已验证邮箱，UID 常无姓名（这是服务端
  行为）；person 实体以邮箱为标识，姓名有则取之。
- 解析器：无第三方依赖的最小 OpenPGP 包解析（new/old format 定长包，
  tag 13 User ID / tag 6 Public-Key 取创建时间），详见
  `adapters/public_pgp_adapter.py`。

### 4b. keyserver.ubuntu.com /pks/lookup —— 判死（robots.txt 红线）

- 探针：`GET https://keyserver.ubuntu.com/robots.txt`。
- 实测：对 `User-agent: *` 明确 `Disallow: /pks/`（及 /d/ /g/ /s/
  /download/ /get/ /search/）。
- 判定：红线"robots.txt 明确 Disallow 的路径直接停手"→ 判死，
  `/pks/lookup?op=get&search=<q>` 即使技术可行也不用，不建 ubuntu 路径。

## 交付

- 代码：新增 `adapters/public_pgp_adapter.py`（SafeResearchAdapter，
  EXPERIMENTAL，default_enabled=False，5s 限速）；`core/entity_association.py`
  加 `attr == "pgp"` person/email 分支 + `attr == "ccgp"` 联系人 person 分支
  + email fanout 接线 + dataclass 工厂注入（与兄弟 lane 并发编辑，全部为
  追加式修改，已随 lane commit 5a31815 落库）。
- 注册：`core/connector_registry.py` 新增 `public_pgp_lookup` implementation
  pack（含 field_contract + runtime_companion）与 ConnectorCapability
 （REST_API/PUBLIC/EXPERIMENTAL/default_enabled=False）。
- 文档：本文（append，未覆盖兄弟 lane 内容）。
- 测试计数：`tests/unit/test_pgp_adapter.py` 13/13 全绿（含真机单请求验证）；
  registry/entity_association 导入校验通过。

---

# 非常规渠道 P2 survey 实测记录（非常规关联人发现 lane）

日期：2026-10-21（lane：个人侧非常规渠道 — 非常规关联人发现）
结论先行：**8 条路径中 6 条走通（4 条关系层扩展 + 2 条新建 adapter），
3 条判死（WHOIS 反查 / 豆瓣友邻 / B站互关），1 条部分判死（文书 agent_of）。
新闻聚合 lane 已判死（见本文档新闻聚合节），新闻共现改走通用 contract。**

实查窗口：2026-10-21 15:25–16:00（北京时间）。方法：plain curl / adapter
单次低频实测（桌面 Chrome UA、无登录、无 cookie、无签名伪造），请求间隔
≥2s；robots.txt 逐站实取。出口为境外 egress。

铁律遵守：零用户身份信息、零注册、不登录、不绕验证码、不碰付费墙、
不伪造身份、不查泄露库内容、不做 SMTP 探测、不钓鱼、只做公开面。
robots.txt 明确 Disallow 的路径直接停手（本次无命中 Disallow 的走通项）。

## 一、走通路径（6）

### 1. 裁判文书共同当事人 person↔person —— 走通（关系层扩展）

- 基线：`public_wenshu_case_records`（browser-assisted）已在 fanout；
  `_wenshu_entities` 已从 cases[].parties/case_number 抽取当事人 person 实体；
  引擎已有 person→business 的 `co_party_in_case`（weak）。
- 本次增量：同一 case_number 的 person↔person 配对 → `co_party_in_case`
 （weak，note 带案号）。无需新 adapter。
- `agent_of`（代理律师/代理人）：**判死**。证据：搜索列表 API
  `/website/parse/rest.q4w` 的当事人字段（s17）只有当事人名称字符串，
  无代理人字段；代理人信息只在文书全文，需逐 doc 页浏览器人工打开——
  不建。

### 2. 新闻/名单共现 —— 走通（关系层；新闻 adapter 判死后改走通用 contract）

- 兄弟 lane 结论（本文档新闻聚合节）：Google News RSS（robots Disallow /）、
  Bing 新闻（反爬）、百度新闻（验证码）全部判死 → `public_news_lookup`
  不会建成。
- 本次增量（不重复造新闻 adapter）：
  - 新增 `co_mentioned_in`（person↔person，review）：同一公开报道/名单
    共现，强制带来源 URL + 标题。消费通用 contract
    `{"title","url","persons":[...]}`（`_news_cooccurrence_entities`），
    任何能产出该 contract 的报道/名单源均可接入。
  - 另补齐学术共现：Semantic Scholar 的 co_authors 实体此前只有 context
    标记、无关系构建；新增 `co_author`（person↔person，strong，
    note 带共享论文标题）。该 adapter 免 key 可用（既有）。
- 现状：toutiao/sogou/maimai 既有抽取均为单作者记录，不产生共现对；
  共现对等待未来报道源接入 contract。

### 3. 专利共同发明人 —— 走通（关系层扩展，adapter 实测通过）

- 实测：`PatentLookup.query("华为技术有限公司", mode="assignee")`
  单次请求返回 total 23214，inventor/assignee/publication_number 完整。
- 本次增量：同一 publication_number 的 patent_inventor 配对 →
  `co_inventor`（strong，note 带专利号+标题+Google Patents URL）。
  无需新 adapter（兄弟 lane 已补 inventor 定向 fanout）。

### 4. 招投标联合体 —— 走通（关系层；parser + relation kind，不碰 fetching）

- 边界：招投标 fetching 由兄弟 lane 在建，本 lane 只做"联合体成员关系"层，
  不重复造 adapter、不改 `adapters/ccgp_adapter.py`。
- 本次增量：
  - 纯函数 `parse_consortium_members(text)`：解析"联合体：A公司（牵头人）、
    B公司" / "联合体成员：A、B" / "以联合体形式投标…"三种常见表述，
    识别牵头人角色；不足 2 家返回 []（fixture 实测通过）。
  - `_consortium_entities` 消费 contract
    `{"members":[{"name","role"}],"url","title"}`（公告获取方后续可接入）。
  - `consortium_member_of`（business↔business，strong，法定公告，
    note 带公告标题+URL）。

### 5. GitHub 共同贡献者 —— 走通（新建 adapter）

- 实测：`GET /repos/octocat/Hello-World/contributors?per_page=3`
  免 key 返回 200（login/contributions/type/html_url）；
  `torvalds/linux` 返回 403 "The history or contributor list is too large…"
 （文档化限制，非封禁）→ 优雅降级 `repo_too_large`。
  匿名 60 req/h → 限频 5s、per_page ≤ 100。
- 新建 `adapters/github_contributors_adapter.py`
 （`GithubContributorsLookup`，SafeResearchAdapter，EXPERIMENTAL，
  default_enabled=False；registry `public_github_contributors_lookup`）。
- 关联：`co_contributor`（username_profile↔username_profile，review，
  note 带仓库 URL；Bot 账号标注并排除配对）。与兄弟 lane 的
  `public_github_deep_extra`（commit 邮箱/star 画像）无字段重复。
- 引擎接线：新 seed 类型 `github_repo`（"owner/repo"）→ fanout；
  工厂 `create_engine_with_all_adapters` 注入。

### 6. 微博互关 —— 走通（关系层扩展；weibo_relation 深度已够）

- 基线核查：`WeiboRelationLookup`（browser-assisted）parse 结果已含
  `follow_me`/`following`/profile_url/verified_reason；深度足够，无需新 adapter。
- 本次增量：`_weibo_relation_entities` 的 context 补上
  follow_me/following；`_extract` 从 pagination.containerid
  （`231051_-_followers_-_<uid>`）解析 seed 用户建 seed person 实体；
  双方互关 → `mutual_follow`（person↔person，review，
  note 带 profile_url）。

### 7. 链上交易对手 —— 走通（新建 adapter；Etherscan 官方判死）

- 实测：
  - `GET https://eth.blockscout.com/api/v2/addresses/<addr>/transactions`
    免 key 返回 200，每页 50 笔（cursor 分页，v2 不支持 limit 参数），
    字段 from.hash/to.hash/timestamp 齐全；robots.txt 对 /api 无 Disallow
    （`User-agent: * Allow: /`，仅封 /auth/*、/account/*）。
  - ENS：`api.ensideas.com/ens/resolve/vitalik.eth` 免 key 200
    （与兄弟 lane 的 `public_ens_lookup` 同源，双向验证已由该 lane 完成）。
  - Etherscan 官方 API 现需 API key（注册）→ 按红线判死，不用。
- 新建 `adapters/blockscout_adapter.py`（`BlockscoutAddressLookup`，
  SafeResearchAdapter，EXPERIMENTAL，default_enabled=False；
  registry `public_blockscout_lookup`）。单次 query 最多 2 请求
  （ENS 解析 + 交易第一页），限频 5s；只读第一页（50 笔），
  合约创建/自转/零地址跳过，对手方按出现次数 Top-20。
- 关联：`onchain_counterparty`（evm_address↔evm_address，weak，
  note 带交易次数/方向/起止时间+浏览器链接）。与兄弟 lane 的
  `public_ens_lookup`（名↔址解析）无字段重复。
- 引擎接线：新 seed 类型 `evm_address`（0x 地址或 xxx.eth）→ fanout；
  新实体类型 `evm_address`；工厂注入。

## 二、判死路径（3+1）

### D1. WHOIS/注册人共现 —— 判死

- `GET https://rdap.verisign.com/com/v1/domain/baidu.com` → 200，
  但 entities 仅含 registrar，registrant 组织/邮箱全部脱敏（GDPR 后常态）。
- `https://rdap.cnnic.cn/rdap/domain/baidu.cn` → 连接失败（当前 egress
  不可达）。
- 结论：无免 key 的 reverse-whois（按注册邮箱/组织查域名）公开面；
  同 IP 域名聚合已有 `HackertargetInfraLookup` reverseiplookup 覆盖，
  不重复。不建 adapter。

### D2. 豆瓣友邻 /people/<uid>/contacts —— 判死

- `GET https://www.douban.com/people/ahbei/contacts`（桌面 UA）→ **403**
 （反爬；profile 页可匿名读但 contacts 页拒绝）。
- robots.txt（User-agent: *）未 Disallow `/people/*/contacts`，
  但服务端 403 即停手（判死口径：服务端拒绝 = 不可用）。
  兄弟 lane 已判死豆瓣书影音扩展（robots 明确 Disallow），豆瓣维持现有
  user adapter 3s 间隔不动。不建。

### D3. B站互关 —— 判死

- `GET https://api.bilibili.com/x/relation/followings?vmid=2&pn=1&ps=3`
  → HTTP 200 但 `{"code":-352}`（B站风控拦截码）。
- 境外 egress 下关系链 API 不可用 → 判死，不建。

### D4. 文书 agent_of（代理律师） —— 判死（见 §一.1）

## 三、交付

- 代码：
  - 新增 `adapters/github_contributors_adapter.py`、
    `adapters/blockscout_adapter.py`（SafeResearchAdapter，
    EXPERIMENTAL，min_request_interval 5.0）。
  - `core/entity_association.py`（追加式）：新 seed 类型
    `github_repo`/`evm_address` + fanout；新引擎字段
    `github_contributors`/`blockscout` + `_extract` 分支 + 工厂注入；
    新 relation kind 7 个（co_inventor / co_author / co_mentioned_in /
    mutual_follow / co_contributor / onchain_counterparty /
    consortium_member_of）+ co_party_in_case 扩展至 person↔person；
    新 extractor（github/blockscout/共现/联合体）+ `parse_consortium_members`；
    weibo context 补 follow_me/following。
  - `core/connector_registry.py`（追加式）：`public_github_contributors_lookup`、
    `public_blockscout_lookup`（field_contract + runtime_companion，
    experimental/default_enabled=False）。
- 测试：
  - `tests/unit/test_github_contributors_adapter.py` 9 个、
    `tests/unit/test_blockscout_adapter.py` 9 个、
    `tests/unit/test_entity_association_unconventional.py` 17 个，
    全绿（35 个）。
  - 回归：含兄弟 lane 相关（keybase/weibo/patent/semanticscholar/
    entity_extract_*）共 94 个全绿；全量 tests/unit 后台复跑中。
- 判死项：D1–D4 不建 adapter，证据见上。
- Commit only，不 push。

---

# 非常规渠道 P2 survey 实测记录（亲属关系 lane：公开披露证据升级）

日期：2026-10-21（lane：亲属关系）
结论先行：**巨潮资讯公告路径走通（金标准，已建 adapter）；裁判文书亲属表述走通（browser-assisted 扩展）；**
**亲属表述抽取层建成（core/kinship_extract.py，公告/文书/报道/自曝四源共享）；**
**社交自曝走通（豆瓣简介扩展，review 级）；实时新闻/讣告源判死（兄弟 lane 已判死三源，无红线内替代）；**
**推理层升级完成（kinship_* relation kind + exact/strong/review 分级 + 措辞 guard）。**

红线遵守：只做公开面；户籍/婚姻登记等非公开政务数据未碰；无登录、无验证码绕行、
无付费墙、无泄露库；cninfo robots.txt 返回错误页（非明确 Disallow）→ 按基类语义允许。

## 1. 招股书/年报/上市公司公告 —— 走通（已建 adapter：`public_cninfo_kinship_lookup`）

- 探针：`POST http://www.cninfo.com.cn/new/hisAnnouncement/query`
  （pageNum/pageSize/column=szse/tabName=fulltext/searchkey=关键词），免登录无 key。
- 实测：searchkey=一致行动人 → 200，totalAnnouncement=24150，含 adjunctUrl；
  PDF 经 `http://static.cninfo.com.cn/<adjunctUrl>` 免登录下载，文字版 PDF，
  pdftotext 可提正文（4 页/149 行，中文正常）。
- 抽取目标实证：简式权益变动报告书含"一致行动关系说明"节，
  家族式披露标准表述如"张三与李四系夫妻关系"/"王五系赵六之子"可被结构化抽取。
- Adapter（`adapters/cninfo_kinship_adapter.py`，`CninfoKinshipLookup`）：
  query(人名/公司名) → 公告搜索 → 标题加权排序（权益变动/收购/年度报告优先）→
  前 N 篇 PDF（默认 2）下载 + pdftotext 正文抽取 → kinship_statements
  （evidence_level="exact"，quote 原文引用 + 公告标题/日期/pdf_url 来源标注）。
  pdftotext 缺失/扫描版 PDF 优雅降级（pdf_note 记因，公告元数据仍作线索）。
  5 秒间隔（巨潮限频，保守）。EXPERIMENTAL，default_enabled=False。
- 接线：`core/entity_association.py` 新增 `_extract` 分支（person 实体 +
  kinship_statement 上下文）+ person_name fanout + 工厂注入；
  `core/connector_registry.py` 注册（field_contract + runtime_companion +
  ConnectorCapability）。

## 2. 裁判文书亲属表述 —— 走通（扩展既有 browser-assisted adapter）

- 基线：`public_wenshu_case_records`（`adapters/wenshu_court_adapter.py`）为
  browser-assisted（DES 加密反爬，不绕），query() 返回 interaction_required。
- 扩展：新增 `parse_doc_text(doc_text, focus_name, case_number)` —— 操作员在浏览器
  打开文书全文页、粘贴正文，抽取"系夫妻关系/系父子/系兄弟"等表述，
  evidence_level="strong"，措辞"文书载明"。不新增任何网络路径，
  不碰验证码/DES，与既有 browser-assisted 纪律一致。
- 判死项：文书网搜索 API 直接调用（无 DES 绕行）不可行，已在既有 adapter 中判死，
  本 lane 不重探。

## 3. 公开报道与讣告 —— 实时源判死；抽取层建成（人工粘贴文本可用）

- 兄弟 lane（新闻聚合）已判死三源：Google News RSS（robots.txt 明确 Disallow /rss/）、
  Bing 新闻（反爬 307→空壳）、百度新闻（图形验证码墙）。本 lane 不重复建
  `public_news_lookup`，不另寻新闻源（红线内无可用替代）。
- 交付：`core/kinship_extract.py` 的 `extract_kinship_statements()` 即"亲属表述抽取层"，
  可作用于人工粘贴的公开报道/讣告文本（含讣告常见"其子/其女/长子/次子"回指模式），
  evidence_level 由调用方指定（报道建议 review，讣告原文可 strong）。
- 与兄弟 lane 无代码重复：它负责新闻源（已判死），本 lane 只做抽取层。

## 4. 当事人自曝 —— 走通（豆瓣简介扩展，review 级）

- Survey：豆瓣用户页 `intro_display`（个人简介）匿名可读（兄弟 lane 已验证），
  微博简介亦有 description 字段；简介中"张三的妻子"类自述真实存在。
- 交付：`extract_self_claimed_kinship(bio_text, profile_name)`（"X 的妻子/丈夫/儿子/女儿/…"
  + "本人系 X 之妻"模式），evidence_level 固定 "review"（自述，低置信度）。
- 接线：`adapters/douban_user_adapter.py` 在 intro 解析后追加
  `self_claimed_kinship` 字段（无命中不加字段）；`core/entity_association.py`
  的 `_douban_user_entities` 透传进 context，`_kinship_disclosure_associations`
  生成关联（person_a 回填资料主人）。

## 5. 推理层升级 —— 完成

- `core/entity_association.py`：
  - 新 relation kind：`kinship_spouse` / `kinship_parent_child` /
    `kinship_sibling` / `kinship_inferred_family`（翁婿/叔侄/舅甥/祖孙/表亲/泛称亲属）。
  - 新方法 `_kinship_disclosure_associations()`，在 `associate()` 中继
    `_infer_family_control()` 之后调用；strength 直接映射 evidence_level
    （exact/strong/review）；去重（pair+relation）。
  - 措辞 guard：`core/kinship_extract.py::statement_note()` —— 只允许
    "披露显示 / 文书载明 / 自述/疑似"，绝不断言（无"实锤/确认"）。
  - 既有 `possible_family_with`（同姓聚类 weak）、`suspected_controls`、
    `possible_couple_business` 保持不动（推理线），本 lane 为披露证据线，
    两者正交。
- 每条关联带来源标注（公告标题+日期+pdf_url / 文书案号 / profile_bio）与原文 quote。

## 判死清单

| 路径 | 判定 | 证据 |
|---|---|---|
| 户籍/婚姻登记等政务数据 | 红线，不碰 | 无合法公开口子 |
| 实时新闻源（Google/Bing/百度） | 判死 | 兄弟 lane 实测：robots Disallow / 反爬 / 验证码 |
| 文书网搜索 API 直调 | 判死（既有） | DES 加密反爬，不绕 |
| 扫描版 PDF 公告正文 | 降级（非判死） | pdftotext 无可提文本 → pdf_note 记因，元数据仍作线索 |

## 交付

- 代码：
  - 新增 `core/kinship_extract.py`（共享抽取层：结构化模式 + 松散归因 +
    自曝模式 + statement_note 措辞 guard）。
  - 新增 `adapters/cninfo_kinship_adapter.py`（`CninfoKinshipLookup`，
    SafeResearchAdapter，EXPERIMENTAL，5s 间隔，default_enabled=False）。
  - `adapters/wenshu_court_adapter.py`（追加式）：`parse_doc_text()` +
    `extract_kinship_from_doc_text()`。
  - `adapters/douban_user_adapter.py`（追加式）：intro 后 `self_claimed_kinship`。
  - `core/entity_association.py`（追加式）：`cninfo_kinship` 引擎字段 +
    person_name fanout + `_extract` 分支 + `_kinship_disclosure_associations()` +
    `associate()` 接线 + `_douban_user_entities` 透传 + 工厂注入。
  - `core/connector_registry.py`（追加式）：`public_cninfo_kinship_lookup`
   （field_contract + runtime_companion + ConnectorCapability）；
    `public_wenshu_case_records` operator_notes 追加 kinship 说明。
- 测试：
  - `tests/unit/test_kinship_extract.py` 22 个、
    `tests/unit/test_cninfo_kinship_adapter.py` 8 个、
    `tests/unit/test_entity_association_kinship.py` 10 个、
    wenshu 追加 3 个、douban 追加 2 个，全绿（45 个）。
  - 回归：connector_registry / entity_association_social_users / keybase /
    douban_adapter 共 68 个全绿。
- Commit only，不 push。
