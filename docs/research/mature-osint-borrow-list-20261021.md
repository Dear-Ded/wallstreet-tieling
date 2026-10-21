# 成熟 OSINT 项目借鉴报告：wallstreet-tieling "Steal This" 清单

**日期**: 2026-10-21
**目标**: 为中文企业/个人实体关联引擎，从成熟开源 OSINT 项目中找可借鉴的模块、技术、数据源
**优先级口径**: person-company linkage > phone intel > domain intel > social media

---

## 一、SpiderFoot (github.com/smicallef/spiderfoot) — 200+ 模块

SpiderFoot 是模块化 OSINT 自动化的标杆。publisher/subscriber 架构：一个模块产出的数据自动喂给其他模块。**这个架构思想本身值得借鉴**（我们的 entity_association 引擎已部分实现，但 SpiderFoot 的 event-driven 更彻底）。

### 最值得偷的模块

| 模块 | 技术/数据源 | 免费/可达 | 移植计划 |
|---|---|---|---|
| `sfp_accounts` | **WhatsMyName 数据集** (wmn-data.json)：700+ 站点用户名枚举，手工维护、低误报。这是半个 OSINT 生态的底层引擎（Blackbird、SpiderFoot 都用它） | ✅ 完全免费，JSON 文件 | 1行计划：下载 wmn-data.json，写 adapter 按用户名逐站点查存在性，重点加中文站点（抖音/快手/小红书/微博/知乎/B站） |
| `sfp_callername` | 电话号码→来电人姓名（免费 API 聚合） | ✅ 免费 API | 1行计划：我们已有 phone_mark_adapter，照抄 sfp_callername 的多源聚合思路，加 360/腾讯标记源 |
| `sfp_crt` + `sfp_certspotter` | 证书透明度：crt.sh JSON API + certspotter.com API | ✅ 免费 | 1行计划：已建成 cert_transparency_adapter；追加 certspotter.com 作为第二源（API 免费，监控新证书） |
| `sfp_gleif` | **GLEIF API** (api.gleif.org)：全球法人识别编码，免费查公司 LEI、法人关系 | ✅ 免费无 key | 1行计划：新建 gleif_adapter，查中国企业的 LEI 记录（含母子公司关系） |
| `sfp_google_tag_manager` | 提取网站 GTM 容器 ID → 关联同一运营者 | ✅ 免费 | 1行计划：已建成 analytics_pivot_adapter；追加 GTM 容器 ID 提取（`GTM-XXXXXX` 正则） |
| `sfp_email` + `sfp_emailrep` | 邮箱提取 + emailrep.io 信誉查询 | ✅ emailrep.io 免费层 | 1行计划：email_intel_adapter 已有 MX/Gravatar；追加 emailrep.io 查询（查邮箱是否一次性/可疑） |
| `sfp_github` | GitHub 用户/组织/代码搜索 | ✅ 免费 | 1行计划：github_deep 已有；照抄 sfp_github 的"搜代码中泄露的域名/邮箱"逻辑 |
| `sfp_commoncrawl` | Common Crawl 索引查历史页面 | ✅ 免费 | 1行计划：新建 commoncrawl_adapter，用 CC Index API 查域名的历史 URL（含已删除页面） |
| `sfp_grayhatwarfare` | grayhatwarfare.com： exposed S3 buckets 数据库 | ✅ 免费层 | 1行计划：查目标企业名的暴露存储桶（低优先级） |
| `sfp_bingsharedip` | 同一 IP 上的其他域名（Bing `ip:` 搜索） | ✅ 免费 | 1行计划：用 Bing `ip:1.2.3.4` 查同 IP 域名（2026-10-21 实测已死，不建） → 关联企业 |

### 架构借鉴

- **Correlation Rules** (SpiderFoot 4.0+)：YAML 规则自动发现关联（如"同一 IP 的多个域名"）。我们的 interesting_patterns 已实现类似功能，但 YAML 化可让运营人员自定义规则而不改代码。
- **Target types**: 支持 ASN、Bitcoin 地址等。我们可加：统一社会信用代码、企业名、人名作为一等 seed 类型。

---

## 二、theHarvester (github.com/laramies/theHarvester) — 40+ 数据源

专注邮箱/子域名/人名收割。核心价值是**数据源清单**。

### 数据源清单（按对我们的价值排序）

| 数据源 | 找什么 | 免费/可达 | 移植计划 |
|---|---|---|---|
| **CertSpotter** | 子域名（CT 日志） | ✅ 免费 API | 1行计划：并入 cert_transparency_adapter 作第二源 |
| **Hunter.io** | 邮箱（按域名查）+ 邮箱验证 | ✅ 免费 25次/月 | 1行计划：email_intel 追加 hunter.io 查询（找企业邮箱格式） |
| **DNSdumpster** | DNS 记录、子域名 | ✅ 免费（Photon 也有插件） | 1行计划：新建 dnsdumpster_adapter |
| **Netcraft** | 子域名、技术栈 | ✅ 免费 | 1行计划：domain_intel 追加 netcraft 查询 |
| **Intelx** | 邮箱、hosts（历史数据） | ⚠️ 需 API key（免费层有限） | 1行计划：低优先级，需 key |
| **LinkedIn** (via Bing) | 员工名 | ✅ 免费（Bing site:linkedin.com） | 1行计划：maimai_adapter 已用搜狗；追加 Bing `site:linkedin.com 公司名` |
| **GitHub code search** | 邮箱、子域名（代码泄露） | ✅ 免费 | 1行计划：github_deep 追加代码搜索 |

### 技术借鉴

- **多源聚合去重**：theHarvester 对同一目标查 40+ 源后去重合并。我们的 entity_association 已做 fan-out，但 theHarvester 的"按源打分"（多源命中=高置信）值得借鉴。

---

## 三、Recon-ng — 模块化框架

完整模块列表已获取。最相关的：

| 模块 | 功能 | 移植计划 |
|---|---|---|
| `recon/companies-multi/github_miner` | 按公司名搜 GitHub 提及 | 1行计划：github_deep 追加"按公司名搜 repo/description" |
| `recon/companies-multi/whois_miner` | WHOIS 挖公司联系人 | 1行计划：domain_intel 追加 WHOIS registrant 提取（注意 GDPR 后多为脱敏） |
| `recon/companies-contacts/bing_linkedin_cache` | Bing 缓存挖 LinkedIn 公司员工 | 1行计划：用 Bing cache 查领英公司页（反爬注意） |
| `recon/domains-hosts/certificate_transparency` | CT 查子域名 | 1行计划：已有 crt.sh；照抄其"多 CT 源聚合" |
| `recon/domains-hosts/ssl_san` | SSL SAN 查关联域名 | 1行计划：cert_transparency 的 query_live_cert 已实现 |
| `recon/domains-contacts/whois_pocs` | WHOIS 联系人 | 1行计划：同上 |
| `recon/locations-locations/geocode` + `reverse_geocode` | 地址↔坐标 | 1行计划：amap/baidu 已有地理编码；追加"POI 地址聚类找关联企业" |

### 架构借鉴

- **Workspace 数据库模型**：domains/hosts/contacts/credentials 表结构 + SQL 查询。这是 investigation packet 的下一阶段：把 JSON 报告升级为可查询的 SQLite。
- **模块命名规范** `recon/<from>-<to>/<source>`：清晰表达"有什么→查什么→用什么源"。我们的 connector_registry 可借鉴此命名。

---

## 四、OWASP Amass — 子域名枚举之王

### 数据源清单（重点：中文源）

| 类别 | 数据源 | 对我们的价值 |
|---|---|---|
| **证书** | Crtsh, CertSpotter, Censys, FacebookCT, GoogleCT, Digitorus | 已有 crt.sh；Censys 需 key |
| **网络** | BGPView, Robtex, IPinfo | 免费，查 ASN/IP 归属 |
| **爬虫** | **Baidu**, Bing, DuckDuckGo, Searx | **Baidu！** Amass 用百度做子域名爬虫——中文域名覆盖 |
| **Web 归档** | Wayback, CommonCrawl, Arquivo | CommonCrawl 免费 |
| **API** | **FOFA**, **ZoomEye**, **360PassiveDNS**, URLScan, VirusTotal, ThreatBook, Quake | **FOFA/ZoomEye/360 都是中文互联网测绘！** FOFA 免费层可查；ZoomEye 需 key；ThreatBook（微步）有免费 API |

### 最值得偷的 3 个

1. **FOFA** (fofa.info)：中文网络空间测绘，`domain="xxx.com"` 查关联资产。免费注册有查询额度。**1行计划：新建 fofa_adapter，查企业域名→IP→同 IP 资产→关联企业**
2. **360PassiveDNS**：360 的被动 DNS，中文域名覆盖好。**1行计划：调研 API 可达性**
3. **ThreatBook (微步)**：中文威胁情报，IP/域名信誉。**1行计划：免费 API 查域名/IP 信誉**

---

## 五、Photon (github.com/s0md3v/Photon) — 爬虫

### 可借鉴的技术

| 技术 | 说明 | 移植计划 |
|---|---|---|
| **JS 端点提取** | 从 JS 文件中正则提取 API 端点/URL | 1行计划：新建 js_endpoint_adapter，抓企业官网 JS，提取 API 路径（含可能的内部接口） |
| **Intel 提取** | 爬取时自动提取邮箱、社交账号、S3 buckets | 1行计划：已有 email_intel；追加"页面社交账号链接提取" |
| **密钥发现** | 高熵字符串检测（API keys） | 1行计划：低优先级（企业官网少见） |
| **Wayback 种子** | `--wayback` 用 archive.org 的 URL 作爬虫种子 | 1行计划：domain 调查时先拉 Wayback URL 列表再爬（覆盖已删除页面） |
| **自定义正则** | 用户自定义 regex 匹配 | 1行计划：entity_association 加"自定义模式"（如备案号、信用代码正则） |
| **DNS 插件** | 爬取时顺带做子域名枚举 | 1行计划：domain_intel 流程中自动触发 crt.sh |

### 插件架构

Photon 的 plugins/（wayback, dnsdumpster, exporter）是轻量扩展点。我们的 SafeResearchAdapter 已类似，但 Photon 的"爬取中触发"（crawl → 自动调 DNS 枚举）值得借鉴：entity_association 的 depth-2 追查可更自动化。

---

## 六、Maltego — 变换 (Transforms)

### 中文相关发现

- **Social Links** 变换包有 **[Weibo] Profile Exists**：用手机号查微博账号是否存在。这是"手机号→社交账号"的标准 pivot。**1行计划：研究其技术路线（可能是微博的 find-by-phone 接口），看能否复现**
- **OSINT Industries**：手机号→多社交平台画像（付费）
- **Truecaller**：手机号→姓名（付费，Social Links 有变换）
- **未发现**公开的企查查/天眼查/微信 Maltego 变换。中文商业数据变换是空白——**这是我们的机会**。

### 可借鉴的 pivot 思路

1. 手机号→社交账号存在性检查（Weibo/Twitter/Facebook）
2. 邮箱→Gravatar→社交账号（我们已有 Gravatar）
3. 图谱可视化：Maltego 的 entity-relationship 图是我们的 report_charts 可对标升级的方向

---

## 七、Sherlock / Maigret — 用户名枚举

| 工具 | 特点 | 移植计划 |
|---|---|---|
| **WhatsMyName** (wmn-data.json) | 700+ 站点，手工维护，误报率最低。是 Blackbird/SpiderFoot 的底层数据 | 1行计划：**最高优先级**。下载数据集，建 whatsapp_my_name_adapter，重点补中文站点 |
| **Sherlock** | 400+ 站点，URL 存在性检查，快 | 1行计划：与 WhatsMyName 二选一（选 Wmn，质量更高） |
| **Maigret** | 3000+ 站点，**解析 profile 元数据**（bio/位置/真名），递归追踪 | 1行计划：Maigret 的"profile 解析"值得借鉴——不只查存在，还提 bio 里的关联信息 |
| **Blackbird** | 600+ 站点 + AI 画像 | 1行计划：AI 画像暂不需要 |

### 关键洞察

Maigret 证明：用户名枚举的价值不在"存在性"，而在 **profile 元数据**（bio 里的公司名、位置、链接）。我们的 weibo_adapter 已提简介；应推广到所有社交 adapter：**bio 解析是关联金矿**。

---

## 八、优先级排序："Steal This" 清单

### P0（本周可做，影响最大）

1. **WhatsMyName 数据集** → 用户名枚举 adapter（700+ 站点，补中文站点）
   - 源：github.com/WebBreacher/WhatsMyName (wmn-data.json)
   - 免费，需定期更新数据集

2. **FOFA** → 中文资产测绘 adapter
   - 源：fofa.info API（免费注册有额度）
   - domain → IP → 同 IP 资产 → 关联企业

3. **Bing `ip:` 搜索** → 同 IP 域名发现
   - 源：Bing（免费）
   - 并入 cert_transparency 或独立 adapter

4. **GTM 容器 ID 提取** → 追加到 analytics_pivot_adapter
   - 正则 `GTM-[A-Z0-9]+`，与百度统计 ID 同等效力

5. **Common Crawl Index API** → 历史页面查询
   - 源：index.commoncrawl.org（免费）
   - 查域名的历史 URL，找已删除的关联信息

### P1（下周，影响大）

6. **GLEIF API** → 全球法人识别
   - 源：api.gleif.org（免费无 key）
   - 查企业 LEI、母子公司关系

7. **Hunter.io** → 企业邮箱发现+验证
   - 源：hunter.io（免费 25次/月）
   - 找企业邮箱格式，喂给 email_intel

8. **DNSdumpster** → DNS 记录/子域名
   - 免费（Photon 有插件可参考）

9. **Maigret 式 profile 解析** → 推广到所有社交 adapter
   - 不只查存在，解析 bio/位置/链接找关联

10. **ThreatBook（微步）** → 中文威胁情报
    - 免费 API，查 IP/域名信誉

### P2（有空再做）

11. **emailrep.io** → 邮箱信誉
12. **BGPView / Robtex** → ASN/IP 归属
13. **Wayback 种子爬虫** → Photon 模式
14. **JS 端点提取** → Photon 模式
15. **SpiderFoot Correlation Rules YAML 化** → 让运营自定义关联规则

---

## 九、中文 OSINT 的空白与机会

调研确认：**公开渠道没有成熟的企查查/天眼查/微信 Maltego 变换，没有中文商业数据的 SpiderFoot 模块**。西方 OSINT 工具链对中文商业世界基本是盲区。

这意味着：
- 我们的 amap/baidu POI、dianping、douyin、icp_beian、qyyjt 路线是**差异化优势**
- WhatsMyName 这类西方数据集**缺中文站点**——我们补上就是贡献
- FOFA/ZoomEye/360 是中文世界独有的基础设施数据源，西方工具用得少

**结论**：不要只抄西方工具，要做"西方技术 + 中文数据源"的结合。SpiderFoot 的架构 + 企查查的数据 = 降维打击。
