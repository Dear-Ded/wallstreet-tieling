import re

content = open('sessions/LATEST.md', 'r', encoding='utf-8').read()

note = """

---

## 2026-06-15 下午会话（续）

> 用户说"接着干，不要一直请示"，推进 v2 设计 Phase 4。

### v2 设计系统 Phase 4 完成

#### Prism.js 语法高亮集成
- `core/reporter_html.py` 重写：
  - `_parse_md_sections()`: 检测 ``` 代码块，生成 @@CODE_BLOCK@@ 令牌
  - `_render_code_block()`: 渲染为 `<pre class="line-numbers"><code class="language-xxx">`
  - `build_html()`: 内联 Prism CSS + JS（本地 `static/` 优先，CDN fallback）
- `static/`: 本地化 Prism.js v1.29.0 + Tomorrow 主题 CSS + 行号插件 CSS
- `core/report_v2.css`: +122 行 Prism 覆盖样式
  - `pre[class*="language-"]` 液态玻璃风格
  - Token 颜色映射到 v2 色板
  - 行号插件样式

#### CSS 变量文档自动生成
- `docs/DESIGN-v2-CSS-VARS.md` 新建（22 个 CSS 变量）

### 测试结果
- **384/384 全绿** ✅

### Commits
- `ec7cca5` — Phase 4: Prism.js syntax highlighting + CSS vars doc
- `1452c1f` — docs: add Phase 4 to v2 design roadmap

### 当前状态
- **v2 设计系统 Phase 1+2+3+4 全部完成** ✅
- **可选改进**（长期，不阻塞）：本地字体加载、更多 Prism 语言包
- **等待用户通知**（产品团队忙完后通知）
"""

if '## 2026-06-15 下午会话（续）' not in content:
    content += note
    print('Appending note...')
else:
    print('Note already present')

open('sessions/LATEST.md', 'w', encoding='utf-8').write(content)
print('Done')
