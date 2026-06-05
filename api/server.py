#!/usr/bin/env python3
"""华尔街驻铁岭办事处 API Server
一键启动: python api/server.py
Docker: docker run -p 8080:8080 wallstreet-tieling
"""

import os
import sys
from pathlib import Path

# -- 检查依赖 --
try:
    from flask import Flask, request, jsonify, Response
    from flask_cors import CORS
except ImportError:
    print("安装依赖中...")
    os.system(f"{sys.executable} -m pip install flask flask-cors requests -q")
    from flask import Flask, request, jsonify, Response
    from flask_cors import CORS

import requests as http_requests
import json
import time

# -- 加载 SKILL.md --
skill_path = Path(__file__).parent.parent / "SKILL.md"
with open(skill_path, "r", encoding="utf-8") as f:
    SKILL_CONTENT = f.read()

# -- 配置 --
app = Flask(__name__)
CORS(app)

# API Key 从环境变量读取
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("WALLSTREET_MODEL", "gpt-4o-mini")
PORT = int(os.environ.get("PORT", 8080))


def build_system_prompt(task_type: str, **kwargs) -> str:
    """构建完整的 System Prompt"""
    task_prompts = {
        "due_diligence": f"你正在执行企业尽调任务。目标企业: {kwargs.get('company', '未指定')}。深度: {kwargs.get('depth', 'standard')}。",
        "people": f"你正在执行人员背景调查。目标: {kwargs.get('name', '未指定')}。",
        "financial": f"你正在执行财务分析。目标企业: {kwargs.get('company', '未指定')}。",
        "anti_nominee": f"你正在执行反代持穿透。目标企业: {kwargs.get('company', '未指定')}。",
    }
    task_header = task_prompts.get(task_type, f"任务类型: {task_type}")
    return f"{SKILL_CONTENT}\n\n---\n{task_header}\n开始执行。"


def call_llm(system_prompt: str, user_message: str, stream: bool = False) -> dict | str:
    """调用 LLM API"""
    if not OPENAI_API_KEY:
        return {"error": "未配置 API Key", "hint": "设置环境变量 OPENAI_API_KEY"}

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.3,
        "stream": stream,
    }

    resp = http_requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=300,
        stream=stream,
    )

    if stream:
        return resp  # 返回原始响应对象用于流式输出
    return resp.json()


# -- API 路由 --

@app.route("/")
def index():
    return jsonify({
        "name": "华尔街驻铁岭办事处",
        "version": "1.0.0",
        "description": "银行信贷情报专家团 API",
        "endpoints": {
            "POST /api/analyze": "执行分析任务",
            "GET /api/health": "健康检查",
            "GET /api/skill": "获取完整SKILL.md",
            "GET /api/docs": "API文档",
        },
        "setup": "设置 OPENAI_API_KEY 环境变量后启动",
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok" if OPENAI_API_KEY else "missing_api_key",
        "model": MODEL,
        "time": time.time(),
    })


@app.route("/api/skill")
def get_skill():
    fmt = request.args.get("format", "text")
    if fmt == "json":
        return jsonify({"skill": SKILL_CONTENT, "length": len(SKILL_CONTENT)})
    return Response(SKILL_CONTENT, mimetype="text/markdown; charset=utf-8")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json() or {}
    task_type = data.get("type", "due_diligence")
    user_message = data.get("message", data.get("company", data.get("name", "")))
    stream = data.get("stream", False)

    if not user_message:
        return jsonify({"error": "缺少 message/company/name 参数"}), 400

    system_prompt = build_system_prompt(task_type, **data)
    result = call_llm(system_prompt, user_message, stream=stream)

    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500

    if stream:
        def generate():
            for line in result.iter_lines():
                if line:
                    yield line.decode("utf-8") + "\n"
        return Response(generate(), mimetype="text/event-stream")

    # 非流式：提取回复文本
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    return jsonify({
        "task_type": task_type,
        "result": content,
        "model": MODEL,
        "usage": result.get("usage", {}),
    })


@app.route("/api/analyze/stream", methods=["POST"])
def analyze_stream():
    data = request.get_json() or {}
    data["stream"] = True
    return analyze()


@app.route("/api/docs")
def docs():
    return jsonify({
        "quickstart": {
            "curl": """curl -X POST http://localhost:8080/api/analyze \\
  -H "Content-Type: application/json" \\
  -d '{"type":"due_diligence","company":"ABC公司","depth":"standard"}'""",
            "python": """import requests
r = requests.post("http://localhost:8080/api/analyze", json={
    "type": "due_diligence",
    "company": "ABC公司",
    "depth": "standard"
})
print(r.json()["result"])""",
        },
        "types": ["due_diligence", "people", "financial", "anti_nominee"],
        "formats": ["json", "stream"],
    })


if __name__ == "__main__":
    print(f"""
🏛️  华尔街驻铁岭办事处 API Server
━━━━━━━━━━━━━━━━━━━━━━━━━━━
端  口: {PORT}
模  型: {MODEL}
API Key: {'已配置 ✅' if OPENAI_API_KEY else '未配置 ⚠️'}

终端测试:
  curl http://localhost:{PORT}/api/health
""")
    app.run(host="0.0.0.0", port=PORT, debug=False)
