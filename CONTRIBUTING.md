# Contributing to WallStreet Tieling Office

首先，感谢你愿意为这个项目添砖加瓦 🙌

## 🐛 报告问题

- **Issues**: 在 [GitHub Issues](https://github.com/Dear-Ded/wallstreet-tieling/issues) 提交
- **安全漏洞**: 请直接发邮件至 derrickdad@foxmail.com（不要公开提交）
- **提问前**：先搜索现有 Issues，避免重复

提交 Issue 时请包含：
1. 你的使用场景（ChatGPT / Claude / WorkBuddy / 其他）
2. 预期行为 vs 实际行为
3. 如果有，附上报错截图或日志

---

## 💡 提交功能建议

1. 先开一个 Issue 打声招呼，标注 `enhancement`
2. 描述你希望新增什么角色/数据源/能力
3. 等初步讨论后再开始写代码

---

## 🔧 本地开发（Skill 模式）

```bash
# 安装到本地
npx skills add Dear-Ded/wallstreet-tieling -g -y

# 找到安装目录
# ~/.workbuddy/skills/华尔街驻铁岭办事处/
```

直接在 skill 目录下修改：
- `SKILL.md` — 主入口，控制触发逻辑
- `sub-skills/*.md` — 各角色 prompt 和工具
- `api/wst.py` — 动态编排器

修改后测试：
```bash
# 语法验证
python -c "import ast; ast.parse(open('api/wst.py').read()); print('✅ 语法通过')"

# 干运行（无需 API Key）
python api/wst.py --mode standard --target "测试企业" --dry-run
```

---

## 📝 代码规范

### Prompt 规范
- **约束词优先级**: `不能 > 禁止 > 建议不`（越强烈越靠前）
- **数据来源**: 所有输出必须标注来源，格式 `[来源: 工具名, 日期]`
- **编造禁令**: 绝不编造数据/数字/日期/人名，不确定时标注 `[未获取]`

### Python 规范
- Python 3.11+，使用 `from __future__ import annotations` 和 dataclass
- 异常处理链完整，不吞异常
- 路径操作使用 `os.path.realpath` + `commonpath` 防穿越
- 外部输入调用 `sanitize_target()` 过滤
- API Key 必须从环境变量读取，不硬编码

### 文档规范
- 子 skill 文件需包含：角色定义 / 能力列表 / 工具映射 / Non-Goals
- 新增外部依赖需更新 `references/compatibility.md`
- CHANGELOG 按 `[Unreleased]` → `[版本号] - YYYY-MM-DD` 格式追加

---

## 🔄 PR 流程

1. 从 `master` 创建功能分支：`git checkout -b feature/your-feature`
2. 提交前运行语法验证（见上）
3. 如果有新的子 skill 或数据源，更新 `README.md` 的团队表/数据源矩阵
4. 提交 PR，标题前缀：
   - `[feat]` — 新功能（新角色、新数据源）
   - `[fix]` — 缺陷修复
   - `[docs]` — 文档改进
   - `[refactor]` — 代码重构
   - `[chore]` — 构建/工具/依赖
5. PR 描述中说明改动范围和测试方式

> 这是个人开源项目，响应时间可能不固定。能回就会回 ✌️
