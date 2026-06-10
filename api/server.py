#!/usr/bin/env python3
"""华尔街驻铁岭办事处 API Server v3.2.0
一键启动: python api/server.py
Docker: docker run -p 8080:8080 wallstreet-tieling

v3.1.0 变更: 路由到 wst 编排引擎（统一质量门禁），移除独立 LLM 路径。
"""
import importlib
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("wst.server")

# ── 依赖检查 ──
MISSING_DEPS = []
for mod_name in ["flask", "flask_cors"]:
    try:
        importlib.import_module(mod_name)
    except ImportError:
        MISSING_DEPS.append(mod_name)

if MISSING_DEPS:
    print("=" * 60)
    print("  缺少依赖，请手动安装：")
    print(f"  pip install {' '.join(MISSING_DEPS)}")
    print("=" * 60)
    sys.exit(1)

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ── 配置 ──
from . import config
from .orchestrator import Orchestrator

config.reload_config()

app = Flask(__name__)
CORS_ORIGINS = os.environ.get("WALLSTREET_CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
CORS(app, origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()])
PORT = int(os.environ.get("PORT", 8080))

# ── API 认证 (P0 修复) ──
# 安全策略: 未配置 token → 强制 127.0.0.1; 已配置 → 0.0.0.0 + Bearer auth
AUTH_TOKEN = os.environ.get("WALLSTREET_AUTH_TOKEN", "")
BIND_HOST = "0.0.0.0" if AUTH_TOKEN else "127.0.0.1"

# 无需认证的公开端点
_PUBLIC_PATHS = {"/", "/api/docs", "/api/health"}


@app.before_request
def check_auth():
    # 公开端点放行
    if request.path in _PUBLIC_PATHS or request.path.startswith("/api/health"):
        return
    # 未配置 token → 不拦截（此时已强制绑定 127.0.0.1）
    if not AUTH_TOKEN:
        return
    # Bearer token 校验
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        return jsonify({"error": "unauthorized", "hint": "设置 Authorization: Bearer <token>"}), 401


# ── 请求体大小限制 (P1) ──
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB


# ── 请求日志中间件 ──
@app.before_request
def log_request():
    logger.info("%s %s from %s", request.method, request.path,
                request.remote_addr)


@app.after_request
def log_response(response):
    logger.info("%s %s → %d", request.method, request.path,
                response.status_code)
    return response


# ── API 路由 ──

@app.route("/")
def index():
    return jsonify({
        "name": "华尔街驻铁岭办事处",
        "version": "3.2.0",
        "description": "银行信贷情报专家团 API · 真并发Agent架构",
        "endpoints": {
            "POST /api/analyze": "执行尽调分析 (通过编排引擎)",
            "GET /api/health": "健康检查",
            "GET /api/skill": "获取完整SKILL.md",
            "GET /api/docs": "API文档",
        },
        "setup": "设置 DEEPSEEK_API_KEY 环境变量后启动",
    })


@app.route("/api/health")
def health():
    has_key = bool(config.get_api_key())
    return jsonify({
        "status": "ok" if has_key else "missing_api_key",
        "model": config.DEFAULT_MODEL,
        "version": "3.2.0",
        "time": time.time(),
    })


@app.route("/api/skill")
def get_skill():
    skill_path = config.SKILL_DIR / "SKILL.md"
    if not skill_path.exists():
        return jsonify({"error": "SKILL.md not found"}), 404
    fmt = request.args.get("format", "text")
    content = skill_path.read_text(encoding="utf-8")
    if fmt == "json":
        return jsonify({"skill": content, "length": len(content)})
    return Response(content, mimetype="text/markdown; charset=utf-8")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """v3.2.0: 路由到 wst 编排引擎（完整 3-Phase + 质量门禁）"""
    data = request.get_json() or {}
    target = data.get("company", data.get("message", data.get("name", "")))
    if not target:
        return jsonify({"error": "缺少 company/message/name 参数"}), 400

    mode = data.get("depth", data.get("mode", "standard"))
    if mode not in config.MODE_TEMPLATES:
        mode = "standard"

    # 异步调用编排引擎
    try:
        concurrency = min(int(data.get("concurrency", 5)), 20)   # P0 硬上限
        max_retries = min(int(data.get("max_retries", 3)), 5)    # P0 硬上限
    except (ValueError, TypeError):
        concurrency = 5
        max_retries = 3

    try:
        orch = Orchestrator(
            target=target,
            model=data.get("model"),
            mode=mode,
            concurrency=concurrency,
            max_retries=max_retries,
        )
        # 使用 new_event_loop 避免 "Event loop is already running" 在 WSGI 多线程环境下的冲突
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(orch.orchestrate())
        finally:
            loop.close()
        return jsonify({
            "task_type": "due_diligence",
            "report": result["report"],
            "model": orch.model,
            "mode": mode,
            "roles_activated": result["roles_activated"],
            "branches_triggered": result["branches_triggered"],
        })
    except RuntimeError as e:
        logger.exception("Orchestration failed: %s", e)
        return jsonify({"error": "编排失败，请检查日志获取详情"}), 500
    except Exception as e:
        logger.exception("Orchestration failed")
        return jsonify({"error": "编排失败，请检查日志获取详情"}), 500


@app.route("/api/docs")
def docs():
    return jsonify({
        "quickstart": {
            "curl": """curl -X POST http://localhost:8080/api/analyze \\
  -H "Content-Type: application/json" \\
  -d '{"company":"ABC公司","depth":"standard"}'""",
        },
        "types": ["due_diligence"],
        "modes": list(config.MODE_TEMPLATES.keys()),
        "formats": ["json"],
    })


if __name__ == "__main__":
    print(f"""
🏛️  华尔街驻铁岭办事处 API Server v3.2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━
端口: {PORT}
绑定: {BIND_HOST}
模型: {config.DEFAULT_MODEL}
API Key: {'已配置 ✅' if config.get_api_key() else '未配置 ⚠️'}
认证: {'Bearer Token ✅' if AUTH_TOKEN else '仅本机 (127.0.0.1) 🔒'}

测试:
  curl http://localhost:{PORT}/api/health""")
    if AUTH_TOKEN:
        print(f'  curl -H "Authorization: Bearer $WALLSTREET_AUTH_TOKEN" ...')
    print()
    app.run(host=BIND_HOST, port=PORT, debug=False)
