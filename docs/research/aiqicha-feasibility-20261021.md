# 爱企查 (aiqicha.com) 适配器可行性报告 — 2026-10-21

**结论：走不通。没有可用的免登录结构化数据源；不建议建适配器。**

实查时间：2026-10-21 14:00 左右（北京时间），plain `curl` HTTP 请求，无登录、无 cookie、无签名伪造、无 WAF/验证码绕过。

## 核心发现：站点已整体迁移，全部流量被百度反爬门拦截

1. **aiqicha.com 已整体 301 到 aiqicha.baidu.com**
   - `GET https://aiqicha.com/` → `301` → `https://aiqicha.baidu.com/`
   - 旧的 API 签名行为（`t` 参数缺失时返回 `{"status":-23}`）已无法复测——旧 host 已不存在，新 host 连 unsigned 请求的机会都不给。

2. **所有免登录请求最终都落到访问限制门** `https://aiqicha.baidu.com/acount/accessrestriction`

| # | 方法/URL | 结果 | 摘要 |
|---|----------|------|------|
| 1 | `GET https://aiqicha.com/`（桌面 UA） | 301 → aiqicha.baidu.com → 200，最终 URL `/acount/accessrestriction`，13 KB | 页面是百度黑查（heicha）反爬门：加载 `dlswbr.baidu.com/heicha/mw/abclite-2061-s.js` JS 挑战 + `passport.baidu.com/passApi/js/uni_login_wrapper.js` 登录组件；正文无任何企业数据渲染 |
| 2 | `GET https://aiqicha.baidu.com/s?q=华为技术有限公司` | 302 → `/acount/accessrestriction` | 搜索页同样被拦 |
| 3 | `GET https://aiqicha.baidu.com/api/suggestlist?keyword=华为` | 302 → `/acount/accessrestriction` | 建议 API 无签发 cookie 机会 |
| 4 | `GET https://aiqicha.baidu.com/api/bussiness/suggestList?keyword=华为` | 302 → `/acount/accessrestriction` | 同上 |
| 5 | `GET https://aiqicha.baidu.com/company/getBatchCompanyInfo?pid=28515882661568` | 302 → `/acount/accessrestriction` | 公司详情 AJAX 接口同样被拦 |
| 6 | `GET https://aiqicha.baidu.com/company_detail_28515882661568` | 302 → `/acount/accessrestriction` | 详情页路径无 SSR 内容 |
| 7 | `GET https://m.aiqicha.com/`（iPhone UA） | 302 → `/acount/accessrestriction` | 移动端通道同样被拦，无服务端渲染数据 |
| 8 | `GET https://aiqicha.baidu.com/robots.txt` | 200，138 字节 | `Disallow: /fs/*`，`Disallow: /usercenter/*`，`Disallow: /zxcenter/*`，`Disallow: /wenshu?wenshuId=*`，`Disallow: /*ajax` — 站方明确禁止抓取 ajax 接口 |

## 死在哪里

- 反爬从"API 签名校验"升级为"百度 heicha JS 挑战 + 登录门"：plain HTTP 客户端在拿到任何数据之前就被挑战页拦截；挑战要求执行 `abclite` JS 并种 `_s53_d91_`/`_j47_ka8_`/`_y18_s21_` 三枚 cookie，红线内不碰。
- 无任何免登录结构化面：首页、搜索、建议 API、详情 AJAX、详情页、移动站——全部 302/200 到同一挑战页。
- robots.txt 明确 `Disallow: /*ajax`，属站方明示信号。

## 未尝试（按红线排除）

- 执行 heicha JS 挑战过门（绕反爬）
- 逆向/伪造 `t` 签名参数（旧 API 路线）
- 百度账号登录后维持会话（需用户账号，超出"公开免登录"范围）
- Playwright 等浏览器自动化过挑战——本次任务限定"只能用公开、无需登录的 HTTP 请求"；若后续授权放宽到 browser-assisted 路线，可重新评估（但本次实查未做）

## 建议

- 不建 `adapters/aiqicha_adapter.py`；后续若用户显式授权 browser-assisted 路线，再按 sogou_wx / dianping 模式评估。
- 替代公开源参考：天眼查/企查查均有官方开放平台（付费 API，已有调研结论，见 `app-api-reverse-20261021.md`）；免付费路线可走企查查公开搜索的同类 browser-assisted 模式或官方平台申请。
