# OSINT 数据获取通道操作手册

> 面向操作员（中文）。覆盖 `feat/osint-acquisition` 分支新增的全部 OSINT 数据源：
> 如何启用、问什么问题、要什么凭证、频率限制是什么、证据能用到什么程度。
> 通用铁律：**所有来源默认关闭（default_enabled=False），显式启用才跑；所有产出都是线索（leads），不是事实（facts）。**

---

## 1. 边界声明（先读）

- 只采集**当事人主动公开**的数据和**公开基础设施**数据（DNS、证书、公开 API）。
- **明确不做**：泄露库（"社工库"）查询、邮箱存活探测（SMTP VRFY/RCPT TO）、账号找回/密码重置探测、钓鱼、伪装套话、任何侵入式扫描（端口扫描等）。
- 人物级**身份断言**永远不允许：跨源一致只产出"线索提示"，人物事实需要 exact/strong 主体匹配 + 复核。

---

## 2. 数据源清单

### 2.1 企业注册（MONEY 线）

| 连接器 | `public_opencorporates_company_registry` |
|---|---|
| 适配器 | `adapters/opencorporates_adapter.py::OpenCorporatesCompanyLookup` |
| 回答的问题 | 该公司在 130+ 司法管辖区有没有注册？注册号、公司类型、成立/注销日期、注册地址、登记机关链接是什么？ |
| 方法 | `query(name, jurisdiction_code=?)` / `query_by_jurisdiction_number(jurisdiction, number)` |
| **凭证** | **需要**。OpenCorporates v0.4 现要求免费 `api_token`（opencorporates.com 注册，约 2 分钟）。token 只通过**构造参数**传入：`OpenCorporatesCompanyLookup(api_token="...")`，**不落盘、不进日志**。无 token 时明确返回 `credentials_required`。 |
| 频率限制 | 3.0 秒/请求（类属性 `min_request_interval`） |
| 真实验证 | 2026-10-20 实测：无 token 时 API 返回 `Invalid Api Token`（确认需要 token）；有 token 的路径为 stub 测试，未做真实 token 联网验证——拿到 token 后先跑一次冒烟。 |
| 默认关闭 | 是（EXPERIMENTAL） |

| 连接器 | `public_opencorporates_officer_records` |
|---|---|
| 适配器 | `adapters/opencorporates_adapter.py::OpenCorporatesOfficerLookup` |
| 回答的问题 | 这个人名在哪些公司担任过职务（职位、起止日期）？用于交叉核验，不做身份断言。 |
| 方法 | `query(person_name)` |
| 凭证 | 同上（共用 api_token） |
| 频率限制 | 3.0 秒/请求 |
| 真实验证 | 同上（待 token 冒烟） |
| 默认关闭 | 是（EXPERIMENTAL） |

### 2.2 注册地址核验（MONEY 线）

| 连接器 | `public_nominatim_address_verification` |
|---|---|
| 适配器 | `adapters/nominatim_geocode_adapter.py::NominatimGeocodeLookup` |
| 回答的问题 | 注册地址是真实存在的地方吗？地点性质是商业/住宅/未知？（`place_nature_hint`） |
| 方法 | `query(address, countrycodes=?)` / `reverse_geocode(lat, lon)` |
| 凭证 | 不需要 |
| 频率限制 | **1.1 秒/请求**（Nominatim 使用政策要求 ≤1 req/s；适配器用标识性 UA `WallstreetTieling/0.6.0`，单地址核验、**禁止批量地理编码**） |
| 真实验证 | 2026-10-20 真实联网通过：`1600 Amphitheatre Parkway, Mountain View, CA` → 200，正确判为 `likely_commercial`。 |
| 特殊说明 | robots.txt 检查被重写过：基类用默认 Python UA 抓 robots.txt 会被 Nominatim 回 403，robotparser 会误判为全站禁止；适配器改用政策合规 UA 抓取（依据写在代码注释里）。`/search` 的 Disallow 是针对网络爬虫的，API 使用的管辖文件是 Nominatim Usage Policy。 |
| 默认关闭 | 是（EXPERIMENTAL） |

### 2.3 邮件情报（PEOPLE 线）

| 连接器 | `public_email_infrastructure_intel` |
|---|---|
| 适配器 | `adapters/email_intel_adapter.py::EmailIntelLookup` |
| 回答的问题 | 邮箱格式有效吗？域名有 MX 记录吗（真收信）？当事人在 Gravatar 注册过公开头像吗？是一次性邮箱/角色账号吗？ |
| 方法 | `query(email)`（内部 fan-out：格式→MX(nslookup)→Gravatar(d=404)→离线名单） |
| 凭证 | 不需要 |
| 频率限制 | 2.0 秒/请求 |
| 真实验证 | 2026-10-20：Gravatar `?d=404` 技巧验证通过（未注册返回 404）；编排器端到端冒烟 `torvalds@linux-foundation.org` MX=True。 |
| 设计排除 | 不查泄露库、不做邮箱存活探测、不碰账号找回流程（见 §1）。 |
| 默认关闭 | 是（EXPERIMENTAL） |

### 2.4 GitHub 深度画像（PEOPLE 线）

| 连接器 | `public_github_deep_enrichment` |
|---|---|
| 适配器 | `adapters/github_deep_adapter.py::GitHubDeepEnrichment` |
| 回答的问题 | 这个人的技术足迹是什么（仓库语言/星标/主题，去 fork）？公开加入了哪些组织（最强的公开雇佣信号）？最近有什么公开动态？ |
| 方法 | `query(github_username)`（内部调 4 个公开端点：profile、repos、orgs、events） |
| 凭证 | 不需要（未认证 API 60 req/h；适配器 3s 间隔，单次画像约 4 次调用） |
| 频率限制 | 3.0 秒/请求 |
| 真实验证 | 2026-10-20 真实联网通过：`torvalds` → 200，12 个仓库、C 语言为主、30 条公开动态。 |
| 默认关闭 | 是（EXPERIMENTAL） |

### 2.5 用户名跨平台足迹（PEOPLE 线）

| 连接器 | `mass_cross_platform_profiler`（注册表中已有） |
|---|---|
| 适配器 | `adapters/mass_profiler.py::MassCrossPlatformProfiler` |
| 回答的问题 | 这个用户名在 30+ 公开平台（GitHub、GitLab、Reddit、StackOverflow、Medium…）有没有公开档案？ |
| 方法 | `massive_cross_check(username)`（注意方法名不是 `query`；编排器已做兼容） |
| 凭证 | 不需要，但需要**显式启用**：`profiler.enable(h=24)`（UserAuthorizationGate 门禁） |
| 频率限制 | 类内 1.0 秒间隔 + 每平台间 0.3s sleep；全量约 30+ 平台 |
| 真实验证 | 历史验证：`torvalds` → 17/29 平台命中（适配器 docstring 记录）。 |
| 默认关闭 | 是（`default_config` 中 `default_enabled: False`） |

### 2.6 基础设施情报（MONEY/风控线）

| 连接器 | `public_urlscan_domain_history` |
|---|---|
| 适配器 | `adapters/infra_intel_adapters.py::UrlScanDomainLookup` |
| 回答的问题 | 这个域名被公开扫描过多少次？最近扫描到的 URL/标题是什么？（无记录=低可见度或新域名，本身也是信号） |
| 方法 | `query(domain, size=?)` |
| 凭证 | 不需要（免费搜索 API） |
| 频率限制 | 2.0 秒/请求 |
| 真实验证 | 2026-10-21 真实联网通过：`github.com` → 200，total 10000+。 |
| 默认关闭 | 是（EXPERIMENTAL） |

| 连接器 | `public_hackertarget_infra_lookup` |
|---|---|
| 适配器 | `adapters/infra_intel_adapters.py::HackertargetInfraLookup` |
| 回答的问题 | DNS 记录（A/MX/NS/TXT）是什么？同 IP 上还有哪些域名（共享主机/关联资产线索）？HTTP 头暴露了什么技术栈？ |
| 方法 | `query(target, endpoints=["dnslookup", "reverseiplookup"])`；可选 `httpheaders`。非法 endpoint 自动回退到 `dnslookup`。 |
| 凭证 | 不需要 |
| 频率限制 | 2.0 秒/请求（多端点 fan-out 时每个端点前都限流） |
| 真实验证 | 2026-10-21 真实联网通过：`github.com` → 200，返回 A/MX/NS/SOA/TXT。 |
| 设计排除 | 只做公开查询端点，不做端口扫描等侵入式探测。 |
| 默认关闭 | 是（EXPERIMENTAL） |

| 连接器 | `public_ipapi_geolocation` |
|---|---|
| 适配器 | `adapters/infra_intel_adapters.py::IpApiGeolocationLookup` |
| 回答的问题 | 这个 IP 实际在哪个国家/城市？归属哪个组织/AS？是不是托管机房（`is_hosting`）？——注册地址 vs 服务器实际位置不一致是经典风险信号。 |
| 方法 | `query(ip)` |
| 凭证 | 不需要（免费层 45 req/min；适配器 2s 间隔远低于限额） |
| 频率限制 | 2.0 秒/请求 |
| 真实验证 | 2026-10-21 真实联网通过：`140.82.121.3` → 德国、GitHub, Inc.、`is_hosting=True`。 |
| 默认关闭 | 是（EXPERIMENTAL） |

### 2.7 社交监听（另一 lane 在建）

`adapters/social_listen_adapters.py` **已落地**（2026-10-21）：`HackerNewsAlgoliaSearch`（HN 故事搜索）与 `StackExchangeSearch`（Stack Overflow 问答搜索），连接器 `public_hn_algolia_search` / `public_stackexchange_search`，EXPERIMENTAL 默认关闭，配套 implementation pack 已注册。

---

## 3. 人物情报编排器

`core/people_intel.py::PeopleIntelOrchestrator` 把 PEOPLE 线适配器拧成一次调用：

```python
from core.people_intel import PeopleIntelOrchestrator, PersonQuery
from adapters.email_intel_adapter import EmailIntelLookup
from adapters.github_deep_adapter import GitHubDeepEnrichment

orch = PeopleIntelOrchestrator(
    email_adapter=EmailIntelLookup(),       # 不传=不跑
    github_adapter=GitHubDeepEnrichment(),  # 不传=不跑
)
graph = orch.investigate(PersonQuery(
    name="Jane Doe", email="jane@example.com",
    username="janedoe", github_username="janedoe",
))
```

- **注入式**：适配器由调用方传入，不传就不跑——默认零运行。
- **单源失败独立降级**：一个源报错只记 `{"error": ...}`，不打断其他源。
- **跨源线索**（`corroborations`，只提示、不做断言）：
  - `domain_company_consistent`：邮箱域名 vs GitHub 公开公司
  - `officer_org_consistent`：任职记录公司 vs GitHub 公开组织
  - `username_github_consistent`：用户名跨平台命中 GitHub 且与提供的一致
  - `disposable_email_flag` / `role_account_note`：一次性邮箱/角色账号风险提示
- 真实验证：2026-10-20 端到端冒烟通过（torvalds 邮箱 MX + GitHub 画像）。

---

## 4. REST 端点

`POST /api/people-intel`（`api/server.py`）：

```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "username": "janedoe",
  "github_username": "janedoe",
  "sources": ["email", "github", "username", "officer"],
  "opencorporates_token": "..."
}
```

- `sources` **显式指定才运行**对应适配器，不传=全部不跑（200，`source_count=0`）。
- `officer` 需要 `opencorporates_token`（请求体内传递，**不落盘**）；缺 token 返回 400。
- `username` 源在请求内显式启用 profiler 1 小时。
- 无任何标识符时返回 400。

---

## 5. 新增适配器流程（照着做）

1. **写适配器**：继承 `adapters/safe_research_adapter.py::SafeResearchAdapter`，实现 `_build_url(keyword, **params)` 和 `_extract_public_fields(raw_data)`；声明 `source_domain` / `source_type` / `data_boundary="fully_public"` / `requires_credentials` / `min_request_interval`。基类自带 robots.txt 检查、频率限制、审计日志（`audit.verify_integrity()`）。
2. **写测试**：`tests/unit/test_<name>.py`，用 `execute_query` override stub 掉 HTTP（不碰真实网络）；覆盖正常提取、垃圾数据、凭证门禁、审计链完整性。
3. **注册**：`core/connector_registry.py::default_connector_capabilities()` 末尾加 `ConnectorCapability`，`status=EXPERIMENTAL`，**`default_enabled=False`**，写清 `notes` 和 `risk_flags`。
4. **implementation pack**：`_SOURCE_STRENGTHENING_IMPLEMENTATION_PACKS` 加条目，含 `runtime_companion`（type=`source_strengthening_runtime_companion`，带 connector 名）——否则 `bin/verify_report_bundle.py` 会报 `source_strengthening_runtime_companion_missing`。
5. **CHANGELOG**：`CHANGELOG.md` 的 Unreleased 区加条目（含真实验证状态）。
6. **本手册**：按 §2 格式补一行。

禁止事项：硬编码任何 token/key/password；把凭证写入文件、日志或测试固件；默认开启任何需凭证或重型的源。

---

## 6. 已实测淘汰的备选源

| 源 | 结论 | 日期 |
|---|---|---|
| bgpview.io | 本机网络不通（HTTP 000） | 2026-10-21 |
| threatfox-api.abuse.ch | 现需 API key（Unauthorized） | 2026-10-21 |
| OpenCorporates 免 key 层 | 已关闭，v0.4 需免费 api_token | 2026-10-20 |

---

## 7. 快速启用检查表

- [ ] OpenCorporates：opencorporates.com 注册 → 拿到 api_token → 构造参数传入 → 先 `query("Tesla Inc")` 冒烟
- [ ] 其余源：确认 `ConnectorRegistry().get("<连接器名>").default_enabled is False` → 在编排器/`/api/people-intel` 中显式指定 sources
- [ ] 跑 `pytest tests/unit/test_<name>.py tests/unit/test_connector_registry.py -q` 确认门禁测试通过
