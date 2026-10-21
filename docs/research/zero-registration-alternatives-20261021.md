# key 门零注册替代方案 — 可行性报告（2026-10-21）

> 铁律：零注册。绝不使用用户真实身份信息（邮箱/手机/实名）向任何第三方注册；
> 不用用户 Gmail 收验证码；需编造身份才能过的，一律放弃。

## 一、走通（已建 adapter）

### 1. public_urlscan_lookup（urlscan.io 公开扫描档案）
- 实测：`GET /api/v1/search/?q=domain:github.com&size=2` → 200，返回真实扫描任务
  （task uuid/time/visibility、page url/domain/ip/country/server/technologies）。
- 免 key、文档化公开 API；限频 5s、小 size、默认关闭。
- robots.txt `Disallow: /api/`（针对爬虫，见 adapter docstring 如实记录）。
- 覆盖：域名/IP → 历史扫描（IP/ASN/国家/服务器指纹/技术栈/TLS 上下文）。
  部分替代 FOFA"资产画像"与 URLhaus/ThreatFox"恶意 URL 上下文"场景。
- 测试：`tests/unit/test_urlscan_adapter.py` 7 项全绿。

### 2. public_email_pattern_lookup（Hunter.io 零注册替代）
- 纯离线模式候选生成（~14 种常见企业邮箱模式）+ DoH MX 存在性检查。
- 全部候选 confidence=low、明确"未验证"；**SMTP 存活探测是红线，不做**。
- 用途限定：交叉验证线索（如与公开简历/Gravatar 邮箱比对），不得断言归属。
- 测试：`tests/unit/test_email_pattern_adapter.py` 6 项全绿。

## 二、判死（有证据）

### 3. abuse.ch 家族（ThreatFox / URLhaus）—— 零注册判死
- 实测：`POST threatfox-api.abuse.ch/api/v1/` `{"query":"get_info",...}` →
  `{"error": "Unauthorized"}`；`POST urlhaus-api.abuse.ch/v1/host/` →
  `{"error": "Unauthorized"}`（2026-10-21 plain curl，无 key）。
- 官方文档（threatfox.abuse.ch/api/）："Auth-Key (Required)… get one for free
  here: abuse.ch Authentication Portal"——需注册 portal 拿 key，违反零注册。
- 结论：判死。下条路：无（portal 注册即要身份）。

### 4. OpenCorporates 无 token —— 判死
- 实测：`GET /v0.4/companies/search?q=tencent&per_page=2`（无 token）→
  HTTP 401 `{"error":{"message":"Invalid Api Token. Please check your
  OpenCorporates account"}}`。
- 匿名额度已不存在（历史上的有限匿名查询已关闭）。结论：判死。

## 三、诚实缺口评估（无新 adapter）

### 5. 高德/百度 POI vs Nominatim
- 现有 `public_nominatim_address_verification`（nominatim.openstreetmap.org，
  1.1s 限频）：全球地址 geocode 可用，**中国大陆 POI 覆盖弱**——无中文商业
  POI 深度（商户名/电话/分类）、无百度系数据。
- 高德/百度 key 必须手机号注册 → 零注册无解。如实记录，不建"假替代"。

### 6. FOFA 零注册替代：urlscan.io + crt.sh + dnsdumpster + infra_intel
- 能覆盖：域名→IP/ASN（urlscan 历史扫描、dnsdumpster A 记录）、同证书域名
  （crt.sh SAN pivoting）、子域名枚举、技术栈指纹（urlscan）。
- **诚实差距**：无 banner/服务指纹全文检索、无 icon/favicon hash 搜索、
  无 CIDR 段资产枚举、无全网实时扫描；urlscan 是用户提交档案（未出现≠不存在），
  crt.sh 偶发 502（adapter 已做 5xx 优雅降级）。
- 结论：替代约 40% 的"已知资产画像"场景；"全网狩猎"场景无零注册解。

## 四、交付
- 新增：`adapters/urlscan_adapter.py`、`adapters/email_pattern_adapter.py`、
  `tests/unit/test_urlscan_adapter.py`、`tests/unit/test_email_pattern_adapter.py`、
  registry 2 条（均 EXPERIMENTAL、default_enabled=False）。
- 连接器总数：104 → **106**。
