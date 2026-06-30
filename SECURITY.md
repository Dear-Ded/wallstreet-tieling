# 安全政策

## 报告漏洞

如果你发现了安全漏洞，请不要公开提交 Issue。

请通过 GitHub Security Advisory 或项目维护入口提交，附上详细的漏洞描述和复现步骤。

我会在 48 小时内确认收到，并在 7 天内给出评估和处理方案。

## 范围

本安全政策涵盖：

- `api/*.py` — Python 编排引擎和 API 服务
- `lib/*.js` — Node.js MCP 服务器
- `SKILL.md` / `sub-skills/*.md` — Prompt 模板
- `deploy/` — 部署配置

## 已知限制

本项目是一个 Prompt 工程 + 编排器的混合系统，以下事项不属于安全漏洞：

- LLM 本身的幻觉和偏见（由上游模型决定）
- 粘贴模式下缺少 MCP 数据源（这是使用方式的差异，不是漏洞）
- 无认证的本地 API 服务（`api/server.py` 默认绑定 127.0.0.1，仅供本地开发，详见 DEPENDENCIES.md）

## 感谢

感谢所有以负责任方式报告安全问题的贡献者。你的名字将在修复后的 CHANGELOG 中致谢。
