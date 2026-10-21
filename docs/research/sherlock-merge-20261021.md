# Sherlock 数据集合并可行性（2026-10-21）— 结论：GO，已合并

## 数据集
- 来源：`https://github.com/sherlock-project/sherlock`，当前路径
  `sherlock_project/resources/data.json`（旧 `sherlock/resources/data.json` 已 404）。
- 规模：482 条目，许可证 MIT（repo LICENSE + GitHub API license.spdx_id=MIT）。
- 条目语义：`url`（`{}` 为用户名占位符）、`errorType` ∈ {message, status_code,
  response_url}、`errorMsg[]`、`errorUrl`、`regexCheck`、`urlMain`。

## 与 wmn-data.json 重合度
- WMN 692 条 vs Sherlock 481 条（有 url 的）。
- 归一化名（alnum+小写）重合 **192**，Sherlock 独有 289。
- 另有 3 条无 `{}` 占位符（Discord、Diskusjon.no、Kvinneguiden）：
  无法做用户名枚举，合并时剔除（否则只会产生误报）。
- 合并后：**692 + 286 = 978** 站点。

## 检测语义映射（check_site 扩展）
- `message`：任一 errorMsg 在 body → 不存在；都不在 → 存在（sherlock 本体语义）。
- `status_code`：200 → 存在；≥400 → 不存在；其他 → None。
- `response_url`：跟踪最终 URL，== errorUrl → 不存在，否则 → 存在。
- `regexCheck`：用户名不合格式 → 该站跳过（found=None, note=regex_mismatch）。
- WMN 原生四段式逻辑（m_string/e_string/m_code/e_code）保持不变。

## 回归
- `tests/unit/test_whatsmyname_adapter.py` 11 项全过。
- 新增 `tests/unit/test_whatsmyname_sherlock_merge.py` 10 项（合并计数、三种
  detect、regex、去重断言）全过。
- 合并脚本：`adapters/_vendor/whatsmyname/merge_sherlock.py`（可重跑、带审计打印）。
