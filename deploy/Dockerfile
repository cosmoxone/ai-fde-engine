# ============================================
# AI-FDE Engine Dockerfile
# 多阶段构建：减小最终镜像体积
# ============================================

# ===== 构建阶段 =====
FROM python:3.11-slim AS builder

# REQUIREMENTS: requirements-core.txt（轻量，Mock模式）/ requirements.txt（全量，真实组件）
ARG REQUIREMENTS=requirements.txt

WORKDIR /build

# 安装系统依赖（编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements-core.txt requirements.txt ./

# 安装依赖到临时目录
RUN pip install --no-cache-dir --prefix=/install -r ${REQUIREMENTS}

# ===== 运行阶段 =====
FROM python:3.11-slim AS runtime

LABEL maintainer="AI-FDE Team"
LABEL description="AI驱动的FDE交付引擎"
LABEL version="0.1.3"

WORKDIR /app

# 安装运行时系统依赖
# git: Aider代码生成需要
# curl: 健康检查
# libgomp1: sentence-transformers/docling运行时需要
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的依赖
COPY --from=builder /install /usr/local

# 复制应用代码
COPY src/ ./src/
COPY tests/ ./tests/
COPY requirements.txt .
COPY pyproject.toml .

# 创建必要目录
RUN mkdir -p /app/logs /app/data /tmp/aifde-docs /tmp/aifde-memory /tmp/openhands-workspaces

# 创建非root用户（安全加固）
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser && \
    chown -R appuser:appuser /app /tmp/aifde-docs /tmp/aifde-memory /tmp/openhands-workspaces

# 切换到非root用户
USER appuser

# 环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
