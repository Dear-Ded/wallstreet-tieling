# 裁判文书网 (wenshu.court.gov.cn) DES 反爬拆解 — 2026-10-21

**结论：DES 加密逻辑已完整逆向、可字节级复现，但服务端仍返回 `code: 9 没有权限请求接口`；直接 API 路线暂未打通，不建议现在建直连接口适配器。现有 `adapters/wenshu_court_adapter.py`（browser-assisted）保持不变。**

实查时间：2026-10-21 14:05–14:45（北京时间）。plain HTTPS 请求 + 静态/动态 JS 拉取分析，无登录、无打码、无验证码硬解。共发起 4 次 `rest.q4w` 探测 POST（已收手，避免触发 -11/-14 风控）。

## 拆解链（动态 JS 定位完成）

任务原假设"DES 逻辑疑似动态加载"被证实。真实加载链：

1. 列表页 HTML `https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html`
   → `index.js?v=1.6`（页面模块配置，含 `$website.dataParsePath = "/website/parse/rest.q4w"`）
2. 首页 `index.js`（`181029CR4M5A62CH`）内嵌 `document.createElement("script")`
   动态加载 **`/common/static/scripts/lawyeeui/website.js?v=1565674602639`**（94.5 KB，含完整 CryptoJS + `DES3` 封装 + `$.WebSite.getData/parseModule/refreshModule` 请求管线）
3. 列表页 HTML 另加载 **`../js/strToBinary.js`**（842 字节）——内含反爬核心函数 `cipher()`

## `cipher()` 完整逆向（可复现）

```js
function cipher() {
    var date = new Date();
    var timestamp = date.getTime().toString();      // 毫秒时间戳
    var salt = $.WebSite.random(24);                // 24 位随机 [0-9a-zA-Z]
    var year = date.getFullYear().toString();
    var month = (date.getMonth() + 1 < 10 ? "0" + (date.getMonth() + 1) : date.getMonth()).toString();
    var day = (date.getDate() < 10 ? "0" + date.getDate() : date.getDate()).toString();
    var iv = year + month + day;                    // ⚠️ month 分支有 bug：10–12 月取 getMonth()（0-based），如 10 月 iv="2026921"（7 位）
    var enc = DES3.encrypt(timestamp, salt, iv).toString();  // 3DES-CBC/PKCS7，key=UTF8(salt)，iv=UTF8(iv)，输出 base64
    var str = salt + iv + enc;
    return strTobinary(str);                        // 每个字符转**二进制**（toString(2)），空格连接
}
```

`DES3` 封装（website.js 内）：`CryptoJS.TripleDES.encrypt(明文, Utf8.parse(key24), {iv: Utf8.parse(iv), mode: CBC, padding: Pkcs7})`。
**字节级验证**：Python（pycryptodome，iv 不足 8 字节时 `\x00` 右补齐）与 Node `crypto.des-ede3-cbc` 对同一输入输出完全一致（`akbgnA67ZwlQrViTt0F+Sg==`），即与 CryptoJS 语义等价。

## 请求/响应格式（已还原）

```
POST /website/parse/rest.q4w
  cfg=           com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO@queryDoc
  sortFields=    s50:desc
  ciphertext=    cipher() 输出（空格分隔的二进制串）
  pageNum=       1
  pageSize=      15
  queryCondition={"s8":"02"} / {"s21":"民间借贷"} 等（明文 JSON，字段见下）
  wh=900 ww=1440 cs=0            # 客户端指纹：窗口高/宽、cookieEnabled?0:1
```

- 查询字段即文书字段键：`s1`案件名称、`s2`法院、`s6`文书类型、`s7`案号、`s8`案件类型、`s17`当事人、`s21`全文、`cprqStart/cprqEnd`裁判日期等。
- 成功响应：`{"code":1, "result":"<DES3加密的JSON>", "secretKey":"<密钥>"}`；
  解密：`DES3.decrypt(result, Utf8.parse(secretKey), iv=当日yyyyMMdd)` → `resultList`（字段 `s1/s2/s5(docId)/s6/s7/s8/s11/s17/s31`，与现有 adapter 解析口径一致）。
- 错误码实测：`-4`未登录、`-11`访问频繁→图片验证码、`-12`→noauth 实名认证页、`-14`→blackip。

## 探测结果

| # | 探测 | 结果 |
|---|------|------|
| 1 | 无 ciphertext 的裸 POST（历史行为复现） | `code:9` |
| 2 | 十进制 charCode 版 ciphertext + `X-Requested-With` 等浏览器头 | `code:9`，`没有权限请求接口,cfg=…` |
| 3 | 修正为**二进制** charCode（与 JS 一致） | `code:9`，同上 |
| 4 | 二进制版 + 贴近页面默认加载（`queryCondition={"s8":"02"}`，pageSize=15，jQuery Content-Type） | `code:9`，同上 |

4 次探测均未触发 -11/-14（IP 暂未被封/限频）。

## 精确卡点

服务端对 `ciphertext` 的校验逻辑在黑盒内。已排除的变量：charCode 进制（二进制已对齐）、3DES 参数（与 Node/CryptoJS 字节一致）、salt 字符集、时间戳新鲜度（VM 时钟与服务端 `Date` 头仅差 3 秒）、浏览器头（UA/Referer/Origin/X-Requested-With/Accept-Language）、queryCondition 键（s21 与页面默认 s8 均试过）、cookie（站点不下发任何 Set-Cookie）。

剩余嫌疑（按可能性排序）：

1. **服务端 iv 解析与 month-bug 的交互**：10–12 月浏览器实际发送 7 位 iv（`2026921`）。若服务端 Java 以固定 `substring(24,32)` 切分 iv/enc，或用正确 `20261021` 解密，则 Q4 所有请求都会失败——真实浏览器用户是否同样失败未知，这是最值得验证的一点（换月/换日复测，或用 1–9 月的正确 8 位 iv 行为做对照）。
2. **应用层 IP 信誉**：边缘 WAF 放行 GET，但 `rest.q4w` 解析服务可能对非中国大陆出口 IP（本机出口为境外 IPv6 `2a04:4e41::/32` 段）直接判 `没有权限请求接口`。注意 zxgk 同出口被 GeoBL 硬拦，wenshu 可能是"软拦"。
3. **缺失的握手前置步骤**：可能存在页面加载时必须先调的注册/令牌接口（未在静态链中发现，但动态行为未穷尽）。

## 下一条没试过的路（按推荐排序）

1. **境内出口复测**：用中国大陆出口 IP（用户自有网络/合规代理）重放本次已验证的请求构造——若 code 9 消失，则卡点是 #2，直接建适配器。
2. **真机抓包对照**：在浏览器中完成一次真实搜索，抓取 Network 面板的 `ciphertext` 原始值，与本逆向输出逐段比对（定位到底是 salt/iv/enc 哪一段被服务端拒绝）。
3. **官方 APP/小程序**：公开检索未发现"中国裁判文书网"官方 APP；微信小程序是否存在及其后端域名未从公开渠道确认——需在微信客户端内实查（超出本次纯 HTTP 范围）。
4. **响应解密链已通**：一旦请求通过，响应解密逻辑已就绪（secretKey 随响应下发，iv=当日日期）。

## 建议

- 暂不新建直连适配器；`wenshu_court_adapter.py` 的 browser-assisted 模式继续有效（操作员在浏览器完成搜索后解析 `rest.q4w` 响应 JSON——注意其响应 `result` 为 DES3 加密，需用响应内 `secretKey` 解密，现有 adapter 的 `_extract_public_fields` 对加密 result 会解析失败，**后续可在 browser-assisted 路径内补一个 `decrypt_result(secretKey)` 步骤**）。
- `pycryptodome` 已装入本仓库 `.venv`（PoC 用），`requirements.txt` 暂未加——建直连适配器时再补 `pycryptodome>=3.20`。
- 本次逆向产物（JS 证据文件）存于临时目录未入库；需要时可按上述 URL 重新拉取（均为公开静态资源）。
