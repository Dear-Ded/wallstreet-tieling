FROM python:3.11-slim

# 元数据
LABEL org.opencontainers.image.title="wallstreet-tieling"
LABEL org.opencontainers.image.description="华尔街驻铁岭办事处 · Enterprise Intelligence & Risk Discovery System 0.5.0 Alpha"
LABEL org.opencontainers.image.version="0.5.0"

WORKDIR /app

# 复制完整代码（含编排引擎 + 所有 Agent 模块）
COPY requirements.txt .
COPY api/ api/
COPY core/ core/
COPY adapters/ adapters/
COPY config/ config/
COPY bin/ bin/
COPY release/ release/
COPY SKILL.md .
COPY sub-skills/ sub-skills/
COPY references/ references/

# 安装依赖（与 requirements.txt 单一来源保持一致）
RUN pip install --no-cache-dir -r requirements.txt

# 非 root 用户
RUN useradd --create-home --shell /bin/bash wst && \
    chown -R wst:wst /app
USER wst

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

EXPOSE 8080
ENV PORT=8080
CMD ["python", "-m", "api.server"]
