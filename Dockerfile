FROM python:3.11-slim

WORKDIR /app

# 复制源代码
COPY api/server.py api/
COPY SKILL.md .
COPY references/ references/
COPY sub-skills/ sub-skills/

# 安装依赖
RUN pip install --no-cache-dir flask flask-cors requests

# 端口
EXPOSE 8080

# 启动
ENV PORT=8080
CMD ["python", "api/server.py"]
