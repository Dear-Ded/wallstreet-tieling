# 更新日志

> 版本号遵循语义化版本：MAJOR.MINOR.PATCH

---

## Unreleased — OSINT 数据获取加强

### 2026-10-21 下午 — Telegram 公开频道/群组情报源
- 新增 `adapters/telegram_channel_adapter.py`：`TelegramChannelLookup`（SafeResearchAdapter，EXPERIMENTAL，`default_enabled=False`）。核心：`https://t.me/s/<handle>` 公开预览页免登录解析（频道名/简介/订阅数/近 20 条帖子文本+时间戳+帖子 URL+阅读量+媒体标记）；不存在或私有 handle 走 302 到 `t.me/<handle>`（无 /s/）即判为无公开预览，不盲跟。关键词仅做直接 handle 解析，无效 handle 返回结构化空结果。
- tgstat.com 逆向挖掘（`docs/research/telegram-tgstat-reverse-20261021.md`）：前端 JS 定位到 `POST /channels/global-search`（TopSearch 类，`data={query}`），plain HTTP 复现确认**全部搜索端点登录墙**（`/channels/global-search`、`/search`、`/channels/search` 均返回 Authentication Required / Sign in to access this page），未登录、未绕验证，按证据停止。公开可用：`GET /channel/@<handle>`（200、服务端渲染、robots.txt 允许）→ 精确订阅数 + 频道简介 + 关联 handle（频道主其他公开频道，发现路线）。已落地为 opt-in 增强 `enrich_with_tgstat(handle)` / `query_channel(..., enrich=True)`，独立 5s 限速 + 独立审计记录。
- `core/connector_registry.py` 注册 `public_telegram_channel_lookup`（field_contract + runtime_companion implementation pack，domains=PEOPLE+SOCIAL_WEB）。
- 新增 `tests/unit/test_telegram_channel_adapter.py`（18 项）：fixture 离线覆盖 handle 归一化、URL 构建、302 判定、帖子/计数解析、tgstat 解析与失败降级、enrich 合并。真实联网冒烟：`t.me/s/durov` 20 条帖子解析正常、精确订阅数 10303163、关联 handle 5 个。
- 红线：不登录、不碰私有群组/私聊、不绕任何验证；只做公开预览面。

### 2026-10-21 下午 — WhatsMyName Maigret 式 profile 深挖
- 新增 `core/profile_metadata.py`：纯函数 profile 元数据解析 — 通用 fallback（og:description/meta description/标题）+ 5 个专用解析（GitHub 嵌入 JSON、微博 ajax JSON、豆瓣 signature、知乎嵌入 JSON、Gitee og+嵌入 JSON）；`profile_text()` 拼待挖掘文本喂 `core/contact_extractor`。
- `adapters/whatsmyname_adapter.py` 扩展：`query(..., enrich_profiles=True)` 对命中站点抓取公开 profile 页（默认关闭，避免默认 692 次请求；`max_profiles=20`、`profile_interval=2.0s` 限速；robots.txt 不允许则跳过；单站失败降级）。`fields` 新增 `sites_found` + `profile_metadata`（含联系方式），同步修复引擎 `_extract` 的 whatsmyname 分支此前读不到 fields 的问题。
- `core/entity_association.py`：新增 `_wmn_profile_entities()` — profile 昵称→`person`、邮箱/手机号→`email`/`phone`、QQ/微信/平台 UID→`username_profile`（只用已有实体类型词汇，context 标注站点/URL/置信度）；`_extract` 的 whatsmyname 分支并入。
- 新增 `tests/unit/test_profile_metadata.py`（15 项）：fixture 离线覆盖通用 fallback + 5 专用解析 + contact_extractor 联动 + 引擎分支。相关套件 113 项全绿；全量 `tests/unit` 2343 通过，仅 2 项预置失败（`test_release_hygiene` 隐私扫描与 `test_trademark_adapter`，基线 commit 已失败，无关本次改动；新 fixture 已避开隐私扫描硬编码号段）。
- 红线：只抓公开 profile 页，不登录；尊重 robots/限速。

### 2026-10-21 下午 — 实体关联引擎 `_extract` 全覆盖
- 补齐 `_extract` 处理器 12 个分支：`patent`（申请人/发明人）、`gleif`（LEI 法人+母子公司）、`customs`（提单收货人/对手方/地址）、`software_copyright`/`juhe_copyright`（软著权人）、`toutiao`（作者）、`weibo_relation`（关注/粉丝）、`commoncrawl`（历史 URL host）、`dnsdumpster`（子域名/IP）、`threatbook`（IP/ASN/恶意判定）、`hunter`（企业邮箱）、`gd_credit`（企业/法定代表人/地址）；只用已有实体类型词汇。
- `_SEED_FANOUT` 新增：`business_name` += gleif/customs/software_copyright；`person_name` += weibo_relation（juhe_copyright 仅 handler，keyed 默认不 fanout）。
- 工厂 `create_engine_with_all_adapters` 补注入：`software_copyright`（知服服免 key）、`weibo_relation`（免 key）、`juhe_copyright`（`juhe_api_key` 提供时）。
- 新增 `tests/unit/test_entity_extract_biz.py`（21 项）、`tests/unit/test_entity_extract_infra.py`（9 项），fixture 离线；引擎测试合计 66 项全绿。GLEIF 真实联网冒烟（Tencent → 10 个 business 实体）。注：dnsdumpster 实查被其 robots.txt（Disallow /htmld/）拦截，属适配器按设计拒绝，未绕行。
- 爱企查结论：走不通。aiqicha.com 已整体 301 至 aiqicha.baidu.com，所有免登录入口均被百度 heicha JS 挑战+登录门拦截，robots.txt 明示 Disallow /*ajax；只写 `docs/research/aiqicha-feasibility-20261021.md`，未建适配器。
- `adapters/phone_mark_adapter.py` 修复：切 tw.chahaoba.com 子站、固话 URL 保留横线、手动 robots 检查（17/17 测试通过）。

### 2026-10-21 上午 — OSINT 数据获取加强

- 新增 `adapters/opencorporates_adapter.py`：OpenCorporates v0.4 公开 API 适配器（公司名搜索 / 司法管辖区+注册号查详情 / 任职人员搜索），覆盖 130+ 司法管辖区 1.4 亿+ 公司。实测发现 v0.4 现需免费 `api_token`（官网注册），token 经构造参数传入、不落盘不进日志；无 token 时明确返回 `credentials_required`。
- 新增 `adapters/nominatim_geocode_adapter.py`：OpenStreetMap Nominatim 地理编码适配器，核验注册地址真实性并初判地点性质（commercial/residential/unknown）。遵守 Nominatim 使用政策：1.1 秒间隔、标识性 UA、单地址核验不批量。robots.txt 检查改为带政策合规 UA 抓取（基类默认 UA 会被 403 误判为全站禁止，已在代码注释中说明依据）。
- `core/connector_registry.py` 新增三个 EXPERIMENTAL 连接器（`public_opencorporates_company_registry`、`public_opencorporates_officer_records`、`public_nominatim_address_verification`），全部 `default_enabled=False`，符合"模块化、可审计、默认关闭"门禁。
- 新增 `tests/unit/test_osint_acquisition_adapters.py`（13 项）：HTTP 全 stub；覆盖字段提取、token 门禁、robots 策略、审计链完整性、注册表默认关闭。Nominatim 已做真实联网冒烟（200，Google 总部正确判为 likely_commercial）。

### 2026-10-20 晚 — 人物情报迭代（PEOPLE 线）

- 新增 `adapters/email_intel_adapter.py`：公开基础设施邮件情报 — 格式校验、MX 记录存在性（nslookup）、Gravatar 主动注册检查（d=404 技巧）、一次性邮箱识别（离线名单）、角色账号识别。明确排除：泄露库查询、邮箱存活探测、账号找回探测。
- 新增 `adapters/github_deep_adapter.py`：GitHub 公开 API 深度画像 — 仓库技术足迹（语言/星标/主题，去 fork）、公开组织归属（最强公开雇佣信号）、近期公开动态。免 token（60 req/h，适配器 3s 间隔单次画像约 4 次调用）。
- 注册表新增 `public_email_infrastructure_intel`、`public_github_deep_enrichment`（EXPERIMENTAL，默认关闭）及配套 source-strengthening implementation pack（含 runtime_companion）。
- 新增 `tests/unit/test_people_intel_adapters.py`（8 项）。GitHub 已做真实联网冒烟（torvalds：200，12 仓库、C 语言为主、30 条公开动态）。
- 新增 `core/people_intel.py` 人物情报编排器：把 PEOPLE 线适配器拧成一次调用 — 注入式适配器（默认什么都不跑）、单源失败独立降级、跨源一致性只产出线索（域名↔公司、任职↔组织、一次性邮箱/角色账号风险提示），不做身份断言。真实端到端冒烟通过（torvalds 邮箱 MX + GitHub 画像）。
- 新增 `POST /api/people-intel` REST 端点：`sources` 显式指定才运行对应适配器（默认零运行）；`opencorporates_token` 随请求体传递、不落盘。
- 人物编排器接入 `MassCrossPlatformProfiler`（30+ 平台用户名足迹）：`username_adapter` 注入、`massive_cross_check` 优先调用、跨源线索新增用户名↔GitHub 一致性；REST 端点 `sources` 支持 `username`（请求内显式启用 1 小时）。

### 2026-10-21 凌晨 — 基础设施情报（MONEY/风控线）

- 新增 `adapters/infra_intel_adapters.py`（三个免 key 公开源，全部 EXPERIMENTAL 默认关闭）：
  - `UrlScanDomainLookup`：urlscan.io 域名公开扫描历史（扫描次数、最近扫描 URL/标题）；
  - `HackertargetInfraLookup`：DNS 记录、反查同 IP 邻居（共享主机/关联资产线索）、HTTP 头技术栈披露，非法端点回退到 dnslookup；
  - `IpApiGeolocationLookup`：IP 地理/ASN/运营商、hosting 机房标识（注册地址 vs 服务器实际位置是经典风险信号）。
- 注册表新增三个连接器及配套 implementation pack（含 runtime_companion）。
- 新增 `tests/unit/test_infra_intel_adapters.py`（9 项）。三源真实联网冒烟全过（urlscan github.com 10000+ 扫描、hackertarget 返回 A/MX/NS/SOA/TXT、ip-api 判 GitHub IP 为德国机房托管）。
- 备选源实测淘汰：bgpview.io 本机不通、threatfox-api.abuse.ch 现需 key。
- 新增 `adapters/doh_adapter.py`：Google DNS-over-HTTPS（A/MX/NS/TXT/CNAME/SOA），独立 DNS 视角交叉验证；`tests/unit/test_doh_adapter.py` 4 项；真实冒烟通过。
- 新增 `adapters/social_listen_adapters.py`：`HackerNewsAlgoliaSearch`（HN 故事搜索，28319 hits 实测）+ `StackExchangeSearch`（Stack Overflow 问答搜索）；`tests/unit/test_social_listen_adapters.py` 10 项。
- 新增 `core/intel_enrichment.py`：`enrich_domain`（三源聚合+跨源 A 记录传递+风险线索）与 `enrich_person`（编排器委托）；`tests/unit/test_intel_enrichment.py` 8 项。
- 新增 `docs/OSINT_LANE_RUNBOOK.md`：中文操作手册（边界声明、9 源清单、新增适配器流程）。
- 注册表新增连接器：`public_hn_algolia_search`、`public_stackexchange_search`、`public_doh_dns_verification`（EXPERIMENTAL，默认关闭）及配套 implementation pack。
- 修复：`work_order_count` 改为计数实际交出的 top_work_orders（`candidate_count` 保留全队列长度），此前新源加入后队列超 8 导致 bundle 校验失败。
- 新增 `adapters/premium_keyed_adapters.py`（key-ready，就绪待 key）：`ShodanHostLookup`（暴露面/端口/服务/banner/漏洞提示）、`OtxDomainLookup`（威胁脉冲引用）、`VirusTotalDomainLookup`（多引擎恶意检出）；key 只走构造参数、不进 URL（OTX/VT 走 header）、不进日志；无 key 时明确返回 `credentials_required`。注册表新增三个连接器及配套 pack。`tests/unit/test_premium_keyed_adapters.py` 5 项（含 key 不泄露断言）。
- 新增 `POST /api/domain-intel`：`{"domain","sources":["urlscan","hackertarget","ipapi"]}`，显式指定才运行。
- 人物编排器新增 `social_adapter`（HN/StackExchange）：`social_mention_signal` 线索；`/api/people-intel` 支持 `sources:["social"]`。
- 红队审查修复：opencorporates 详情接口补 token+凭证门禁、email_intel 补 robots 检查、people_intel 加 `_safe_int`；MX 检查改走 DoH（去 nslookup 二进制依赖）。
- 主流程可选接入：`bin/investigate.py` 新增 `--intel-domain` / `--intel-person`（`name=|email=|github=|username=`），opt-in 运行情报 enrichment 并挂载为 `packet['intel_enrichment']`；双 flag 真实 CLI 冒烟通过。
- 新增 `adapters/keybase_adapter.py`：`KeybaseIdentityLookup`（免费无 key API；抓取用户密码学身份证明：Twitter/GitHub/Reddit/HackerNews/DNS/PGP 跨平台绑定声明），已接入 `dev_footprint_adapters`；连接器 `public_keybase_identity_proofs`（EXPERIMENTAL 默认关闭）。真实冒烟：`max` 7 个证明全抓到。
- 新增 `RubyGemsOwnerLookup`（免费无 key；gem 发布记录）；Bitbucket 用户名查询端点已废弃（404），放弃。连接器 `public_rubygems_owner_lookup`。
- MCP 新增 `people_intel` / `domain_intel` 两个真实情报工具（CLI/API 之外的第三调用面）；`domain_intel` 经 MCP 协议真实调用验证通过。

## Unreleased — 报告可视化：SVG 图表渲染

- 新增 `core/report_charts.py`：零依赖内联 SVG 图表渲染器（交付质量维度条形图、风险严重程度分布+综合风险评分环、来源构成堆叠条、证据/线索/缺口环形图），全部字符串经 HTML 转义，空数据时静默降级、永不抛异常打断报告生成。
- 便携 HTML 报告新增「风险可视化」章节：图表直接画在报告里，不再只是图表元数据表格；打印样式同步适配。
- `bin/verify_report_bundle.py` 新增 `chart_section` 校验：报告包是否内嵌 SVG 图表章节一目了然，老包不上报失败、只标记 `present: false`。
- 新增 `tests/unit/test_report_charts.py`（14 项）：渲染器单元测试 + 一键 CLI 端到端产品链路测试（离线 fixture 跑通并断言 HTML 内嵌 ≥3 张 SVG）。
- 演示页 `index.html` 新增「风险可视化」面板：JS 直绘交付质量维度条形图与风险严重程度分布，演示包补齐 `dimension_scores`/`severity_counts` 示例数据。
- 视觉 QA（2026-10-20 晚，结构化验证代替像素截图）：浏览器沙箱禁 loopback、file:// 不可用，本机 headless Chromium 在此环境无法截图；改用结构化断言——4 张 SVG 全部良构、无矩形溢出 viewBox、无负尺寸、无文本节点未转义尖括号；章节顺序 cards → 风险可视化 → premium-qa 正确。像素级渲染未亲眼验证。

---

## v0.5.0 (2026-06-07 — 2026-06-10) — 架构跃迁：子母 Skill + 真并发 Agent + 平台无关引擎

> 最终测试数：**402** (was 36 in v2.6.0)

### 2026-06-07: 子母 skill 架构重构

**Token 节省 79-93%**

- 主 SKILL.md 从 125KB 缩减到 4.5KB（97%缩减）
- 13 个角色拆分为独立 sub-skills/ 子 skill 文件
- 渐进式披露：主 SKILL 只含调度表+铁律，子 skill 按需加载
- 简单查询（主+3 子 skill）：~3,149 tokens — 节省 93%
- 标准尽调（主+10 子 skill）：~6,496 tokens — 节省 85%
- 深度尽调（全 13 子 skill）：~8,928 tokens — 节省 79%
- 标准 YAML frontmatter（兼容 6 大工具）
- 小米 MiMo 模型适配（mimo-v2.5/pro/flash）
- 陈志远（陈工）任务拆解子 skill
- CHANGELOG.md 版本管理
- 删除空 agents/ 和 personality/ 目录
- 删除 4 个陈旧 references/ 文件

### 2026-06-07: 子 skill 业务逻辑补全

- 钱守正：完整调度决策树（1469B→2700B，+84%）
- 陈志远：任务 DAG + 4 场景拆解方案（1190B→2377B，+100%）
- 吴德厚：PUA 触发时机 + 质量检查清单
- 周通：环境检测流程 + 数据获取步骤
- 刘文华：报告合并流程 + 完整 MD 模板
- data-sources.md：21KB→1.8KB 实用速查表（瘦身92%）
- SKILL.md：新增输出质量检查点（交付前强制执行）
- 数据源数字修正：200+→实际可用 10-30

### 2026-06-09: 文档补全 + 工程优化

**GStack 三专家综合审计 · README 全面重写 · 项目管理规范化**

- GStack 三专家综合审计（产品评审员/安全官/调查员）
- README.md 全面重写（42/100 → 90+/100），新增 7 个章节
- 防杜撰六层防御体系独立成章
- 质量保障三道防线（L1 正则 + L2 评分 + L3 政委 PUA）
- 动态编排引擎（3 阶段流水线 + 6 模式 + 6 条件分支）
- 部署形态 8 种（Skill 粘贴/MCP/Docker/REST API/npm CLI/Custom GPT/Claude/国产 Bot）
- 成本控制（模式 Token 预算 + 多模型价格表 + 节省率）
- REST API 服务（4 端点 + curl 示例）
- 多分支优化策略（4 分支 + git checkout 指南）
- 数字修正：OSINT 3→5、MCP 2→5、平台 8→14+
- 3 个新 Badge：防杜撰 6 层防御 / L1+L2 双检 / Token 节省 85-93%

**新建文件**: DEPENDENCIES.md / CODE_OF_CONDUCT.md / SECURITY.md / .github/ISSUE_TEMPLATE/ (3个) / .github/PULL_REQUEST_TEMPLATE.md

**重写文件**: LIMITATIONS.md / index.html

**仓库管理**: 根目录清理 / .gitignore 补全 / 分支清理 / ROADMAP.md 修正

**版本统一**: SKILL.md / package.json / clawhub.json / mcp-server.json / server.py / regression.json 全文件版本号统一为 v0.5.0

### 2026-06-10: 真并发Agent架构 + 拟人化升级

**五维度全面审计驱动 · 安全红线清零 · 真并发Agent · 13角色人格化**

- **真并发 Agent 系统**：从单LLM多调用升级为独立Agent实例（DueDiligenceAgent）
  — 每个Agent拥有独立状态/记忆/情感追踪/内部独白/消息通信
- **Agent 注册中心**（AgentRegistry）：13角色生命周期管理、通信路由、团队状态快照
- **AgentMessage 结构化消息**：替代 prev_context 字符串拼贴，支持点对点/广播/闲聊
- **统一编排引擎入口**：server.py 和 wst.py 走同一 Orchestrator，消除架构孤岛
- **13角色人格档案**（PersonalityProfile）：背景故事/性格特征/口头禅/同事关系
- **情感状态追踪**（EmotionalState）：信心/挫败/兴奋动态变化，6种情绪模式
- **政委 PUA 保留**：三级退回话术 + 降级不阻塞流水线
- **安全修复**: server.py 移除运行时 `os.system(pip install)` / API Key 双回退 / VAGUE_WORDS 单一来源
- **工程优化**: config.py / utils.py / agent.py / personality.py / agent_registry.py / quality_rules.py / orchestrator.py 新模块
- **文档修复**: 清理 ma-li-quan.md ~100行重复 / 版本号统一 / 项目管理中枢规范化
- Python 包结构 / Logging / Dockerfile 打包 / 配置中心

### 2026-06-10: CI/CD 强化 + 测试基建 + Bug 修复

**测试从 36 → 376**：test_agent.py（63）+ test_orchestrator.py（53）+ test_quality_rules.py（32）+ test_registry.py（31）+ test_config.py（29）+ test_personality.py（158）+ test_utils.py（30）

- CI/CD: Python syntax check / flake8 / markdownlint
- Bug修复: L1 short_output 阻断 L2 fabrication_risk / EmotionalState 浮点精度 (float→Decimal) / 衰减顺序修正
- QualityRules 模块化拆分 / Test fixtures 共享 (conftest.py)

### 2026-06-10: 平台无关引擎

- **core/ 引擎核心**: 零平台依赖的纯编排引擎
- core/interfaces.py: LLMProvider / ToolProvider / OutputProvider 抽象
- core/roles.py: 13 角色职权体系 (report_to/domain/decisions/must_not)
- core/session_bus.py: 结构化 Phase 间情报传递
- core/engine.py: 3-Phase + Phase 1.5 团队会议 + 条件分支
- core/deep_graph.py: 多跳关联图 ≤8跳, 环检测
- core/query_cache.py / core/org_memory.py: 五层本地组织记忆
- adapters/: WB / CLI 适配器 + 贡献模板
- MIGRATION.md / ARCHITECTURE.md
- **测试从 376 → 402**（新增 26 tests）
- api/: v0.5.0 层完全向后兼容 / sub-skills/: 14 角色提示词不变 / api/personality.py 不变

---

## v2.6.0 (2026-06-06)

- 问题上报机制（简单/中等/复杂三级）
- 头脑风暴机制（7 步会议流程）
- 拟人化交互示例

## v2.5.0 (2026-06-06)

- CrewAI 风格调度架构
- 三种模式：流水线/层次化/并行
- 并行执行规则（最大 5 并行，超时 5 分钟，重试 3 次）

## v2.4.0 (2026-06-06)

- 13 个 agents/ 子 skill 文件创建
- 小米 MiMo 模型适配

## v2.3.0 (2026-06-06)

- OSINT 工具依赖配置 + 依赖检测/提示/降级方案
- 蛛丝马迹推理框架

## v2.2.0 (2026-06-06)

- 中小企业尽调能力：企业类型识别 + 独有指标 + 行业特殊指标（餐饮/零售/贸易）

## v2.1.0 (2026-06-06)

- 颜好看（颜设计）角色：前 Apple 设计团队成员
- 设计系统：颜色/字体/间距/圆角

## v2.0.1 (2026-06-05)

- 智能推导引擎 + OSINT 数据源矩阵 + 质量控制机制 + 冲突数据展示

## v1.0.0

- 初始版本：12 人团队协作 + 五层数据源矩阵

### 2026-10-21 上午 — 实体关联引擎 + 97 连接器（feat/osint-acquisition）

**核心：实体关联引擎** `core/entity_association.py`：
- `associate(seed)` 多跳关联：phone/address/business/person/email/domain 种子，depth-2 有界追查
- 家族/实控推断：同姓聚类、挂名法人、夫妻店、穿透持股、控制网（全标注"疑似"+置信度）
- 跨平台身份归一：同用户名+同地点=高置信度同一人
- 联系方式提取：QQ/微信/手机/邮箱/平台UID 自动提取（`core/contact_extractor.py`）
- 三调用面：REST `/api/entity-associate`、CLI `--associate`、MCP `entity_associate`

**新增连接器 25 个**（72→97）：
- 线下商业：高德POI、百度POI、大众点评、抖音、快手、B站、小红书、文书网、搜狗微信
- 企业深度：ICP备案（工信部直连）、商标、专利（Google Patents）、软著、海关（Zauba）、GLEIF、政府采购（CCGP）、法院公告、广东信用
- 个人深挖：豆瓣、微博、微博关系链、脉脉、查號吧、Telegram、WhatsMyName、FOFA、拉勾、智联、BOSS直聘、头条号、Hunter.io
- 基础设施：证书透明度、Analytics ID pivot、Common Crawl、DNSdumpster（在途）、微步（在途）

**死路**（实测）：Bing `ip:` 已死；gsxt/zxgk/creditchina/爱企查/58/知乎/贴吧/LinkedIn 均 blocked。
