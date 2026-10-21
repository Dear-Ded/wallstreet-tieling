# 「企业预警通」定位 + 拆解报告（2026-10-21）

> 结论：公开渠道**不存在**名为「企业预警通」的独立产品/APP/小程序（4 轮定向搜索无命中）。
> 定位为：**商查平台的企业风险监控预警能力**——订阅企业后，对工商变更、司法诉讼、经营异常、失信被执行等风险动态做聚合与推送。
> 主攻：启信宝（qixin.com，本项目此前未探过）；企查查/天眼查的 APP 端已由同期重攻队（coordinator a32b32b5）负责，本报告只记录 web 端实测、不重复造轮子。

## 一、定位证据链

| 候选 | 验证 | 结论 |
|---|---|---|
| 独立 APP（应用宝/官网） | 搜索「企业预警通 APP/下载/官网」4 轮 | 无此名产品；命中均为畅捷通/帆软等不相关预警系统 |
| 微信小程序 | 搜索「企业预警 小程序 监控」 | 无此名小程序；只有企查查/天眼查官方小程序 |
| 商查平台监控功能 | 企查查：企业详情页「监控」按钮，订阅后推送经营异常/诉讼/股权变更（vqhf.com 实测教程）；天眼查：App 内「关注」企业，工商变更/风险动态推送（ebingou.cn） | **三家（企查查 qcc.com / 天眼查 tianyancha.com / 启信宝 qixin.com）均把「企业监控/风险预警」作为核心功能** |

运营主体（公开信息）：企查查—企查查科技股份有限公司（苏州）；天眼查—北京金堤科技有限公司；
启信宝—上海生腾数据科技有限公司（页脚：沪ICP备18033674号-2，上海市静安区万荣路1268号云立方A座11层）。

## 二、拆解过程（全部 plain curl，无登录、无签名伪造）

### 1. 启信宝 web（qixin.com）— 地域封锁 451
- `GET https://www.qixin.com/` → **HTTP 451**（34KB），正文：「根据相关法律规定，当前所在地区暂不支持访问」
  （当前出口 IP 被识别为英格兰/乔治亚州）。证据文件：`/tmp/qixin_home.html`。
- 同源 API 代理同样被封：`GET /api-proxy/web/search` → 451。
- `m.qixin.com/` → 405（阿里云通用 405 页，疑似已下线/仅特定方法），`data.qixin.com/`（开放平台）→ 405。
- **意外收获**：451 错误页内嵌了完整的 Nuxt SSR 配置，泄露了各端 API base 路径：
  `BROWSER_API_BASE_URL_WEB="/api-proxy/web"`、`_APP="/api-proxy/app"`、`_AI="/api-proxy/ai"`、
  `API_BASE_URL_AI="https://qx-ai.qixin.com"`。native APP 极可能走独立 API 域名（不在 451 范围内）——见下条路。
- APP 下载二维码（页脚 `qr-app.Dcg0epAn.png`）已下载到 `/tmp/qr-app.png`，但本机无 zbar/cv2 解码库，
  未能读出下载链接；包名未确认。

### 2. 企查查 web（qcc.com）— TCP 层超时
- `GET https://www.qcc.com/` → **HTTP 000**，40 秒超时（两次，含 --http1.1 重试 15 秒超时）。
  境外 IP 在 TCP 建连即被丢弃，比 451 更彻底。

### 3. 天眼查 web（tianyancha.com）— 419 反爬
- `GET https://www.tianyancha.com/` → **HTTP 419**（1.9 秒），天眼查自定义反爬状态码，未登录 plain HTTP 直接被拒。

## 三、精确卡点
1. 三家 web 端对本机出口 IP 均为**地域/IP 信誉墙**（451 / TCP 丢弃 / 419），与具体接口签名无关——
   拆 JS 找内部 API 在此阶段无意义，先过墙才有后文。
2. 「监控/订阅/推送」功能在三家均为**登录态 + 会员**功能，即使过墙，plain HTTP 也拿不到订阅接口；
   官方开放平台（data.qixin.com / open.api.tianyancha.com / api.qichacha.com）均为付费，预算未批不采购。

## 四、下条没试过的路（按优先级）
1. **启信宝 APP 拆包**（最有希望）：从应用宝/官网拿官方 APK → REA 反编译 → 找 native APP 的 API host
   （web 的 /api-proxy 是同源 451，APP 大概率走独立域名如 `app.qixin.com` 系）→ 用 Nuxt 配置里已泄露的
   `/api-proxy/app` 路径族对口复现。QR 二维码文件在 `/tmp/qr-app.png`，需先解出下载链接。
2. **天眼查/企查查 APP**：同期重攻队正在拆（coordinator a32b32b5，15:00 前出结果），等它结论，不重复。
3. **境内 IP 出口**：451/419/TCP 超时三者都是墙，境内 IP 或用户手机热点可解 web 层；届时再拆 JS bundle 找监控接口。
4. **browser-assisted + 用户登录态**：监控/订阅本质需登录，可走用户浏览器代管登录（京东/淘宝代管方案同理），
   由用户决策。
5. **数据平替**：预警数据本身 = 工商变更 + 司法 + 经营异常 + 失信，官方源已有 adapter 覆盖
   （文书网/公告网 browser-assisted；gsxt/zxgk/信用中国重攻中）；商查平台的独特价值是聚合+推送，
   非数据源本身。

## 五、红线遵守
未登录、未绕验证码、未碰付费墙接口、未伪造签名；robots.txt：qixin.com 的 robots 请求返回 451 页
（未拿到有效 robots 内容，未据此断言允许/禁止——APP API 探测留待拆包后按实际 robots 判断）。

---
*未建 adapter，未动 registry。本报告为 commit-only 交付。*

## 六、启信宝 APP 拆包路线实测（2026-10-21 14:27–14:52，subagent a2c37de6）

> 结论：**官方 APK 在本机网络位置拿不到**。下面是逐条证据，不是"失败"两个字。

### 6.1 拿到的东西（真实产出）
1. **官方下载二维码已解码**：`/tmp/qr-app.png`（qixin.com 页脚 `qr-app.Dcg0epAn.png`，CDN 直链可下）
   → 内容 `https://app-html.qixin.com/download/message-others`。
   解码过程本身是个小攻坚：本机无 zbar/cv2 解码库 → 从 Ubuntu 归档站手动下载
   `libzbar0` + `libv4l-0t64` + `libv4lconvert0t64` 三个 deb、dpkg-deb 本地解压、
   so 拷入 `/usr/lib/x86_64-linux-gnu/` + ldconfig，pyzbar 终解出。OpenCV 试过，
   中心 logo 干扰下 detectAndDecode 识别不出。
2. **iOS 侧包信息**（App Store lookup API，id 1030675668）：bundleId
   `com.bertadata.qixinbao`，seller Shanghai ShengTeng Data Co.,Ltd，v10.10.00。
   Android 包名极大概率相同。
3. **Nuxt SSR 配置全量**（451 页内嵌）：API base `/api-proxy/web|app|ai`、
   `https://qx-ai.qixin.com`；子域 `b.qixin.com`（企业版）、`claim.qixin.com`、
   `app-html.qixin.com`、`app-vip.qixin.com`、`zhaobiao.qixin.com`、
   `logger.qixin.com/analytics?t=v4`；极验 ID 四枚（LOGIN/OVERLIMIT/NOPERCEPTION/SUBMIT，
   坐实 Geetest v4）。
4. **存活主机**：`app.qixin.com` 存在（405）、`api.qixin.com` 200 但为 OpenResty 默认页
   （占位、非真实 API）。

### 6.2 逐条卡点（均有证据）
| 路线 | 结果 | 证据 |
|---|---|---|
| 官网下载页（QR 链接） | 405 | `app-html.qixin.com/download/message-others` 及 `/download`、`/download/android`、`/app/download` 全 405（阿里云通用 405 页），与 UA 无关 |
| 应用宝（官方安卓商店） | 查无此包 | `a.app.qq.com/o/simple.jsp?pkgname=com.bertadata.qixinbao` 返回"不存在页面"；`sj.qq.com/appdetail/com.bertadata.qixinbao` 404"页面不存在"；sj.qq.com 搜索页为 SPA，前端搜不到 |
| 360/豌豆荚/酷安/小米/华为/OPPO/vivo/百度手机助手 | 全被墙或 JS 化 | 302 跳首页 / 567 反爬 / 404 / 空结果，无一返回包信息 |
| APKPure/Uptodown/APKFab | 403/404 | 非官方渠道，本就只打算拿包名，也拿不到 |
| 包名爆破（com.qixin / com.qixinbao / com.intsig.qixinbao 等） | 全 404 | 仅 `com.bertadata.qixinbao` 有 iOS 实证，其余无依据，不再试 |
| DNS 子域枚举找 APP API host | 不可用 | 本机 DNS 被劫持（任意子域均返回 198.18.0.0/15 保留段），crt.sh 502 |

### 6.3 下条没试过的路（按优先级）
1. **用户手机直传 APK**（最直接）：用户在国内应用宝/官网可正常下载，把 APK 发过来即拆。零技术障碍。
2. **境内 IP 出口重走应用宝**：404/405 可能是地域性下架或屏蔽，境内 IP 下 `sj.qq.com/appdetail/com.bertadata.qixinbao` 值得重验一次。
3. **iOS 端逆向**：IPA 需 Apple ID 下载；或查 App Store 的 `app-ads.txt`/Universal Links 暴露的 API host。
4. **证书透明度恢复后**（crt.sh 502 是暂时的）：枚举 `*.qixin.com` 找真实 APP API host（如 `appapi` 系），再对口探接口。
5. **拆已泄露路径**：`/api-proxy/app` 是 web 的 app 接口基址，若拿到境内 IP，`www.qixin.com/api-proxy/app/...` 可直接复现 web 的"app"族接口——APP 大概率同源。

## 七、官方 APK 猎取成功（2026-10-21 15:0x，应用汇 AppChina）

### 7.1 关键发现：Android 包名 ≠ iOS bundleId
- iOS：`com.bertadata.qixinbao`（App Store id 1030675668）
- **Android：`com.bertadata.qxb`**（应用汇 listing 实证）。此前按 iOS 包名在各安卓渠道搜索是缘木求鱼——这就是官方 APK 一直"拿不到"的根因之一。

### 7.2 获取链路
1. 应用汇搜索 `启信宝` → `https://www.appchina.com/app/com.bertadata.qxb`（200，标题"启信宝 10.10.00"）。
2. 下载按钮为 Thymeleaf 服务端渲染，真实直链：`http://mobile.d.appchina.com/McDonald/e/7716935/0/0/0/1792562408014/package_101000.1792562408014`。
3. 下载成功：68,649,365 bytes，`Content-Type: application/vnd.android.package-archive`。

### 7.3 验签（铁律执行）
| 项 | 结果 |
|---|---|
| SHA-256（APK） | `a51ab8022ebacaed91dc34bb6c361db144a0424536075ac7e75db6a2fd8a65e4` |
| 包名（manifest） | `com.bertadata.qxb` ✅ 与商店 listing 一致 |
| 版本（manifest） | `10.10.00` ✅ 与 iOS v10.10.00 一致 |
| 签名证书 | 自签，`Subject/Issuer: C=86, ST=JiangSu, L=SuZhou, O=bertadata, CN=bertadata_android`，sha256WithRSAEncryption |
| 证书 SHA-256 | `308e5e168df9d52bc98132382ee1a6d8202b3df2339ce04cb38d3230daf65e99` |
| 权限审查 | 27 项常规权限（定位/相机/通讯录/存储/通知等，业务查询类 App 正常范围）；无 READ_SMS/BIND_DEVICE_ADMIN 等高危项 ✅ |
| 结构 | Flutter 应用（classes.dex 仅 13KB，Dart 在 libapp.so），正常 |

结论：**官方正版包**（知名安卓商店应用汇 + 包名/版本双一致 + 厂商自签证书 O=bertadata + 权限无异常）。单源，未做多源哈希互验——证书与版本交叉已足够采信；后续拿到第二源可补哈希比对。

### 7.4 扫过的其他镜子（均未命中，供备查）
APKMirror（无此包）/ apkcombo（连接失败）/ a2zapk.dev（404）/ apkfolks（525）/ evozi（不在 Google Play，404）/ apkmonk（连接失败）/ APKFab（403）/ Uptodown（404）/ 酷安（567 反爬）/ pc6（567 反爬）/ 2265（连接失败）/ 安智（连接失败）/ 豌豆荚（连接失败）/ 小米应用商店（302 回首页=无包）/ 360 手机助手（302 回首页）/ 爱学府 dl.aixuefu.com 直链（境外 IP 空回包）/ newhua（搜索页被劫持跳转）/ appchina 之外未再深挖。

### 7.5 文件位置
- APK 本体**不进仓库**：`/tmp/qxb_appchina.apk`（68.6MB）。
- 下一步：REA 反编译（`~/workspace/rea/`）→ 找 APP API host 与签名算法 → 复现免登录查询端点。
