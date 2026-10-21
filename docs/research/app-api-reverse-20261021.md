# App API 逆向报告：企查查 / 天眼查

**日期**: 2026-10-21
**方法**: APK 静态分析 (jadx) + GitHub 开源情报 + 官方开放平台文档

---

## 1. 天眼查 (com.tianyancha.skyeye)

### APK 分析
- **来源**: APKPure 直接下载 (`https://d.apkpure.com/b/APK/com.tianyancha.skyeye?version=latest`)
- **大小**: 51MB，APK 有效 (7087 文件，含 AndroidManifest.xml + dex)
- **加固**: 重度加固
  - `classes.dex` 仅 13KB (纯 loader)
  - `lib/arm64-v8a/libdu.so` (1.2MB) - 加固器主模块
  - `lib/arm64-v8a/libJMEncryptBox.so` - 加密模块
  - jadx 反编译仅得 5 个 Java 文件 (R.java + 混淆 loader)
- **结论**: 静态逆向不可行，需动态脱壳 (Frida/dump dex)，投入大

### 从 APK 提取的域名 (assets/*.json)
```
image.tianyancha.com
img5.tianyancha.com
kfzhx.tianyancha.com
m.tianyancha.com
n.tianyancha.com
static.tianyancha.com
```

### 官方开放 API (open.tianyancha.com) - 付费
- **Base URL**: `http://open.api.tianyancha.com/services/open/`
- **认证**: HTTP Header `Authorization: <token>` (需购买 token)
- **SDK 参考**: https://github.com/iamsk/tianyancha (Python SDK)

**核心端点** (167+ 接口，节选最有价值):

| 方法名 | 路径 | 参数 | 说明 |
|---|---|---|---|
| search | `search/2.0` | word | 企业搜索 |
| ic_baseinfo | `ic/baseinfo/2.0` | keyword | 企业基本信息 |
| ic_baseinfoV2 | `ic/baseinfoV2/2.0` | keyword | 基本信息+联系方式 (电话/邮箱/网址) |
| ic_baseinfoV3 | `ic/baseinfoV3/2.0` | keyword | 基本信息+主要人员 |
| ic_contact | `ic/contact` | keyword | 企业联系方式 |
| ic_staff | `ic/staff/2.0` | keyword, pageNum, pageSize | 主要人员 (董监高) |
| ic_holder | `ic/holder/2.0` | keyword | 股东信息 |
| ic_holderList | `ic/holderList/2.0` | keyword | 股东列表 |
| ic_inverst | `ic/inverst/2.0` | keyword | 对外投资 |
| ic_branch | `ic/branch/2.0` | keyword | 分支机构 |
| ic_annualreport | `ic/annualreport/2.0` | keyword | 企业年报 |
| ic_changeinfo | `ic/changeinfo/2.0` | keyword | 变更信息 |
| jr_lawSuit_3.0 | `jr/lawSuit/3.0` | keyword | 法律诉讼 |
| jr_zhixinginfo | `jr/zhixinginfo/2.0` | keyword | 被执行人 |
| jr_dishonest | `jr/dishonest/2.0` | keyword | 失信被执行人 |

**Verdict**: ❌ 无免费/无 key 路线。需企业付费购买 token。

---

## 2. 企查查 (qcc.com)

### APK 下载
- **状态**: 未找到 APKPure 上的包名 (尝试 10+ 常见包名均 404)
- **原因**: 企查查可能未上架 APKPure，或包名非常规
- **替代**: 官方开放平台文档已足够详细，无需 APK 逆向

### 官方开放 API (open.qcc.com / api.qichacha.com) - 付费
- **Base URL**: `https://api.qichacha.com/`
- **认证** (三要素):
  - Query: `key=<AppKey>`
  - Header: `Token = MD5(key + Timespan + SecretKey)` (32位大写)
  - Header: `Timespan = <Unix时间戳(秒)>`
- **开通**: 需企业实名认证 + 创建应用获取 AppKey/AppSecret (open.qcc.com)
- **价格**: 多数接口 0.50-1.00 元/次，免费试用 20 次

**核心端点**:

| 接口 | 路径 | 说明 |
|---|---|---|
| 企业搜索 | `Company/Search` | 按名称/信用代码搜索 |
| 股东信息 | `ECIPartner/GetList` | 股东姓名/持股比例/认缴出资 (ApiCode 731) |
| 分支机构 | `ECIBranch/GetList` | 分支机构名称/状态/法人 (0.50元/次) |
| 企业客户 | `Customer/GetList` | 客户名称/销售金额/占比 |
| 上市公告 | `IPOAnnouncement/GetList` | A股/新三板公告 (1.00元/次) |

**Verdict**: ❌ 无免费路线。需企业实名 + 付费。

---

## 3. 爱企查 (aiqicha.baidu.com)

- **状态**: 未深入 (百度系，大概率同样加固 + 无免费 API)
- **已知**: 官网 aiqicha.baidu.com 有 Web 版，API 需 JS 签名 (之前已验证 `{"status":-23}`)

---

## 总结

| 平台 | 免费 API | 付费 API | APK 可逆向 |
|---|---|---|---|
| 天眼查 | ❌ 无 | ✅ open.tianyancha.com (token) | ❌ 重度加固 |
| 企查查 | ❌ 无 | ✅ api.qichacha.com (AppKey+MD5签名) | N/A (未找到包) |
| 爱企查 | ❌ 无 | 未知 | N/A |

**关键结论**:
1. 三大商业数据平台**均无免费 API**，全部要付费 + 企业实名
2. 天眼查 APK 重度加固，静态逆向走不通
3. **官方 API 文档本身就是最好的"逆向成果"** - 端点、参数、认证方式全部公开
4. 如果用户愿意付费，天眼查/企查查官方 API 是**最干净、最稳定**的数据源 (167+ 接口，含股东/法人/联系方式/司法全维度)
5. 免费路线只能继续走公开渠道 (POI/社交/ICP/文书网等)，商业数据平台指望不上

**建议**:
- 短期: 继续免费公开源深挖 (已建 82 连接器)
- 长期: 如用户批准预算，接入天眼查或企查查官方 API (建议天眼查，Python SDK 成熟，`iamsk/tianyancha`)
