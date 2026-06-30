# 美学设计系统 (Aesthetic Design System)

> v1.0.0 | 2026-06-10
> 基于 CodeBuddy frontend-design-pro / ui-ux-designer / ui-ux-pro-max 等插件的方法论精华，
> 为 wallstreet-tieling 尽调报告输出提供系统的前端 UI 设计指南。

---

## 一、设计哲学

```
设计不是装饰，是沟通。
数据不会说谎，但需要好看的衣服。
细节决定成败，一致性是灵魂。
```

### 核心理念
- **信息第一**：设计服务于数据呈现，不是炫技
- **一致性优先**：同类元素同类样式，反复出现反复一致
- **克制即高级**：少即是多，留白是呼吸
- **可访问性内生**：不是后期修补，而是设计 DNA

---

## 二、13 条设计铁律

> 来源：frontend-design-pro/design-wizard/references/design-principles.md

### 1. 视觉层级 (Visual Hierarchy)

引导视线按重要性流动。层级间大小差异 ≥1.5 倍。

```
✅ 正确: h1 5xl+bold → h2 2xl+semibold → body base+regular → caption sm+muted
❌ 错误: 所有文字同级大小，没有主次之分
```

### 2. 对齐 (Alignment)

每个区块统一一种对齐方式，沿不可见网格线排列。

```
✅ 正确: 标题/正文/按钮统一左对齐，卡片内头像/标题/副标题沿同一基线
❌ 错误: 标题居中 + 正文左对齐 + 按钮居中，三套对齐混用
```

### 3. 对比 (Contrast)

重要元素必须突出。文本对比度 ≥4.5:1（WCAG AA）。

```
✅ 正确: 深色文案 #0c0c10 在白色卡片上，CTA 用强调色 #6366f1
❌ 错误: 灰色文字 #999 在灰色背景 #f5f5f5 上，弱对比不可读
```

### 4. 留白 (White Space)

给元素呼吸空间。区块 padding 最小 32px（p-8），最大宽度 max-w-prose。

```
✅ 正确: section p-12 md:p-24，段落间 mb-6，卡片间 gap-8
❌ 错误: 所有元素挤在一起 p-2，行间距 tight
```

### 5. 邻近 (Proximity)

相关元素靠近，无关元素远离。组间间距 > 组内间距。

```
✅ 正确: 卡片内 3px gap → 卡片间 12px gap → section 间 48px gap
❌ 错误: 所有元素统一 16px 间距，无分组感
```

### 6. 重复 (Repetition)

同类元素必须完全相同样式。形成设计系统意识。

```
✅ 正确: 所有信息卡片 bg/圆角/阴影/内边距完全一致
❌ 错误: 卡片A bg-white p-4，卡片B bg-gray-100 p-8，卡片C rounded-2xl
```

### 7. 统一 (Unity)

全局 ≤2 个字体族 + ≤1 套色彩系统 + ≤1 套圆角体系。

```
✅ 正确: display字体+body字体，主色+辅色+强调色，统一 rounded-lg
❌ 错误: 衬线+无衬线+等宽三套字体混用，多色渐变+圆角不一
```

### 8. 平衡 (Balance)

视觉重量均匀分布。重元素（大标题/深色按钮/图片）与轻元素（小字/留白/浅色）交替。

```
✅ 正确: 左侧重磅标题 + 右侧轻量导航，不对称但平衡
❌ 错误: 所有重量压在左侧，右侧只有一个文字链接
```

### 9. 尺度 (Scale)

用大小差距表现重要性，而非步步递增。标题与正文至少差 3 级。

```
✅ 正确: h1 text-6xl → body text-base，跳跃式缩放
❌ 错误: h1 text-2xl → h2 text-xl → body text-lg，单调无节奏
```

### 10. 色彩理论 (Color Theory)

60-30-10 法则：60% 主色(背景) + 30% 辅色(卡片/区块) + 10% 强调色(CTA/高亮)。

```
✅ 正确: bg-gray-50(60%) + bg-white cards(30%) + indigo-600 CTA(10%)
❌ 错误: 紫背景 + 粉标题 + 绿正文 + 橙按钮，色彩爆炸
```

### 11. 排版 (Typography)

正文 ≥16px，行高 1.5-1.75，每行 ≤75 字符。大写字母需 letter-spacing。

```
✅ 正确: body text-base(16px) leading-relaxed(1.625) max-w-prose(65ch)
❌ 错误: body text-sm(14px) leading-none(1.0)，密不透风
```

### 12. 深度 (Depth)

用背景色差 + 阴影 + 模糊创建图层感，不靠繁多装饰。

```
✅ 正确: bg-gray-100页面 → bg-white卡片(shadow-sm) → bg-gray-50嵌套区
❌ 错误: 全白无差异，或过度使用阴影/渐变/模糊
```

### 13. 动效 (Motion)

仅交互状态（hover/focus/active）添加动效，≤300ms，必须尊重 prefers-reduced-motion。

```
✅ 正确: transition-all duration-200 hover:scale-105 + @media(prefers-reduced-motion)
❌ 错误: animate-bounce + animate-pulse + animate-spin 同时使用
```

---

## 三、8 阶段设计工作流

> 来源：frontend-design-pro/commands/design.md — "project design" 完整方法论

### Phase 1: 发现 (Discovery) → 5 问定方向

| # | 问题 | 选项 |
|---|------|------|
| Q1 | 你要做什么？ | Landing / Dashboard / Blog / E-commerce / Portfolio / SaaS |
| Q2 | 项目阶段？ | 个人项目 / 初创 / 成熟品牌 / 客户项目 / 重设计 |
| Q3 | 目标用户？ | 开发者 / 商务 / 创意 / 普通消费者 / Gen-Z / 高端 |
| Q4 | 背景风格？ | 纯白 / 暖白 / 浅色调 / 暗黑 / 自定义 |
| Q5 | 灵感来源？ | URL 分析 / 关键词 / 调研趋势 / 默认 |

### Phase 2: 调研 (Research) → 趋势 + 对标

- **趋势调研**：Dribbble trending → 设计模式 → 色彩/字体趋势
- **对标分析**：URL → 截图分析 → 提取颜色/字体/模式 → 记录要点

### Phase 3: 情绪板 (Moodboard) → 方向确认

综合调研→呈现配色方向→呈现字体方向→UI模式清单→情绪关键词

**迭代**：展示→反馈→优化，最多 3 轮

### Phase 4: 配色 (Color) → 选色定调

映射到设计角色：
```
Primary(CTA/品牌) → Background(页面) → Surface(卡片)
→ Text(heading/body/muted) → Accent(高亮)
```

### Phase 5: 字体 (Typography) → 选字配对

输出：Google Fonts import + Tailwind config + 使用示例

### Phase 6: 实现 (Implementation) → 生产代码

```html
<!DOCTYPE html> → meta viewport → Google Fonts → Tailwind CDN →
<style>动效+focus状态</style> → <body>语义HTML+skip link → 响应式布局
```

### Phase 7: 自查 (Self-Review) → 质量门禁

**反模式（不得出现）：**
- ❌ Hero 徽章/药丸标签在标题上方
- ❌ 通用字体（Inter/Roboto/Arial）
- ❌ 紫蓝渐变白底
- ❌ 装饰性 blob 形状
- ❌ 全局过度圆角
- ❌ 可预测模板布局

**必须满足：**
- ✅ 明确视觉层级 / 对齐 / 对比度≥4.5:1 / 充分留白 / 一致间距
- ✅ skip link / 语义标题序列 / 可见focus状态 / 图片alt / prefers-reduced-motion

### Phase 8: 交付 (Delivery) → 全套输出

```
1. 完整 HTML 文件
2. 设计决策说明
3. 色彩参考卡
4. 字体参考卡
5. 自定义说明
```

---

## 四、wallstreet-tieling 设计 Token

> 颜好看 v0.5.0"#0a0a14"        # 深色主题底色
卡片背景: "rgba(22,22,32,0.65)"  # 玻璃卡片
强调色:   "#6366f1"        # CTA/图表高亮
数据绿:   "#22c55e"        # 正面数据/通过
警告黄:   "#eab308"        # 风险警告
危险红:   "#ef4444"        # 高风险/阻塞
来源灰:   "#777777"        # 数据来源标注
```

### 字体

```yaml
正文: "Noto Sans SC"       # 中文正文
数据: "Geist Mono"         # 数字/代码/表格
字号: [28,16,14,12]px     # h1/h2/body/caption
```

### 间距与圆角

```yaml
间距: [4,8,12,16,20,24,32,40,48,64] px
圆角: [6,8,12,28] px       # 28px 为玻璃卡片专用
行高: 1.6-1.75             # 正文/标题
```

### 组件规范

#### 数据卡片 (Data Card)
```
Background: rgba(22,22,32,0.65)
Border-radius: 28px
Backdrop-filter: blur(28px)
Padding: 24px
Title: 16px/600 Geist Mono
Value: 28px/700 Noto Sans SC
Source: 11px/400 #777777
```

#### 风险等级标签
```
🔴 高风险: bg #FDEDEC, text #922b21, border-left 3px #ef4444
🟡 中风险: bg #FEF9E7, text #7D6608, border-left 3px #eab308
🟢 低风险: bg #E8F8F5, text #1E8449, border-left 3px #22c55e
```

#### 数据表格
```
表头: bg rgba(99,102,241,0.15), text 12px/600 Geist Mono #6366f1
斑马纹: even bg rgba(255,255,255,0.03)
数字列: text-align right, font Geist Mono
来源栏: text 11px #777777
```

---

## 五、反 AI Tells 检查清单

运行任何前端输出前，必须逐项检查：

```
□ 无紫色渐变 (purple-blue gradient)
□ 无 Inter/Roboto/Arial 字体
□ 无装饰性 blob/球体/波浪
□ 无全页圆角卡片
□ 无 Hero badge/pill 在标题上方
□ 无 Lorem ipsum 占位文本
□ 无过度动画 (animate-bounce/spin/pulse 三连)
□ 无 emoji 作为装饰元素
□ 有 skip link
□ 有 prefers-reduced-motion
□ 有语义标题层级 (h1→h2→h3，不跳级)
□ 有数据来源标注
```

---

## 六、设计交付 Pipeline

```
Wall → 刘文华 Markdown 报告
  │
  ▼
颜好看 接收 → 选择输出格式
  │
  ├── HTML: 深色主题 + 玻璃卡片 + 数据密集型
  │     ├── mermaid-diagrams → 架构/流程/产业链图
  │     ├── show_widget → SVG 雷达图/Chart.js 趋势图
  │     └── frontend-dev → 全栈渲染 + 动效
  │
  ├── PPT: pptx-generator 生成幻灯片
  │     └── 套用设计 Token（色彩/字体/间距）
  │
  ├── Word: python-docx 公文排版
  │     └── 宋体正文 + 黑体标题 + 雅黑注释
  │
  └── PDF: md-to-pdf-cjk 固定布局归档
        └── 正式排版 + 品牌标识
```

---

## 七、输出格式速查

| 格式 | 主题 | 字体 | 适用场景 |
|------|------|------|---------|
| HTML 报告 | 深色 #0a0a14 | Noto Sans SC + Geist Mono | Web 交付、交互展示 |
| PPT 演示 | 白底商务 | 按模板 | 高管汇报、路演 |
| Word 公文 | 纯黑印刷 | 宋体12pt/黑体标题 | 正式尽调存档 |
| PDF 归档 | 固定布局 | 与源格式一致 | 不可篡改归档 |

---

## 八、设计决策记录 (ADR)

### ADR-001: 深色主题优先
**决策**: HTML 报告默认深色主题  
**理由**: 数据密集型报告在深色背景下可读性更高，玻璃卡片效果只在深色下显著  
**权衡**: 打印友好度下降 → Word/PDF 用浅色印刷方案补偿

### ADR-002: Geist Mono 数据字体
**决策**: 所有数字/代码/表格使用 Geist Mono 等宽字体  
**理由**: 等宽字体确保数字列对齐，Geist Mono 在中文场景下视觉和谐  
**权衡**: 需 CDN 加载 → 回退方案: 系统 monospace 栈

### ADR-003: 玻璃拟态 (Glassmorphism)
**决策**: 卡片使用 backdrop-filter blur + 半透明背景  
**理由**: 在数据密集型报告中创建深度感和层次，弱化背景噪音  
**权衡**: 旧浏览器不支持 → 降级为纯色背景

---

> 本文档从 CodeBuddy frontend-design-pro / ui-ux-designer / ui-ux-pro-max / design-systems 等插件方法论中提取精华，
> 经 wallstreet-tieling 工程保障团队系统化后纳入项目美学设计模块。
