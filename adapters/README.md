"""wallstreet-tieling v0.5.0"""
from __future__ import annotations

# ── 平台适配器开发指南 ──
#
# 只需要实现三个接口:
#   1. LLMProvider  — 你的平台怎么调模型
#   2. ToolProvider — 你的平台有什么工具/数据源
#   3. OutputProvider — 你的平台怎么存文件
#
# 然后将它们组合成 PlatformAdapter:
#   from core.engine import Engine, PlatformAdapter
#   adapter = PlatformAdapter(llm=MyLLM(), tools=MyTools(), output=MyOutput())
#   engine = Engine(target="ABC公司", adapter=adapter)
#   result = await engine.run()
#
# ── 平台特定提示词 ──
# 各平台的 prompt 模板放在 prompts/{platform}/ 目录下:
#   prompts/dify/system.md   — Dify 的系统提示词
#   prompts/coze/system.md   — Coze 的系统提示词
#
# 如果平台有内置工具（如 Dify 的知识库检索、Coze 的插件市场），
# 在 ToolProvider.search() 中映射 tool_type 到平台工具:
#   "company_search" → Dify 内置"企业信息查询"工具
#   "risk" → Coze 插件"司法风险查询"
#
# ── 贡献适配器 ──
# 1. Fork 本项目
# 2. 在 adapters/ 下创建 {platform}.py
# 3. 在 prompts/{platform}/ 下创建提示词模板
# 4. 提交 PR 到 master 分支
# 5. 在 SKILL.md 的分支表中添加你的适配器描述
