# ============================================
# AI-FDE Engine Makefile
# ============================================

.PHONY: help install install-full dev test test-cov lint format type-check docker-single docker-build docker-up docker-down docker-logs docker-restart backup clean

# 默认目标
help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ===== 开发 =====
install: ## 安装核心依赖（Mock模式零配置可运行）
	pip install -r requirements-core.txt
	pip install -e ".[dev]"

install-full: ## 安装全量生产依赖（Docling/Qdrant/DeepEval/Aider/Mem0）
	pip install -r requirements.txt
	pip install -e ".[dev]"

dev: ## 启动开发服务器
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# ===== 测试 =====
test: ## 运行测试
	pytest tests/ -v

test-cov: ## 运行测试并生成覆盖率报告
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-fast: ## 快速测试（跳过慢速测试）
	pytest tests/ -v -m "not slow"

# ===== 代码质量 =====
lint: ## 代码检查
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## 代码格式化
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check: ## 类型检查
	mypy src/

# ===== Docker部署 =====
docker-single: ## 单容器模式（拉取GHCR镜像并运行，SQLite持久化，开箱即用）
	docker pull ghcr.io/cosmoxone/ai-fde-engine:latest || \
	  docker build -f deploy/Dockerfile --build-arg REQUIREMENTS=requirements-core.txt -t ghcr.io/cosmoxone/ai-fde-engine:latest .
	docker rm -f aifde-single 2>/dev/null || true
	docker run -d --name aifde-single -p 8000:8000 -v aifde-data:/app/data ghcr.io/cosmoxone/ai-fde-engine:latest
	@echo "控制台: http://localhost:8000/dashboard"

docker-build: ## 构建全量镜像（六服务编排用）
	cd deploy && docker compose -f docker-compose.full.yml build

docker-up: ## 启动所有服务（全量编排）
	cd deploy && docker compose -f docker-compose.full.yml up -d

docker-down: ## 停止所有服务
	cd deploy && docker compose -f docker-compose.full.yml down

docker-restart: ## 重启应用服务
	cd deploy && docker compose -f docker-compose.full.yml restart ai-fde-app

docker-logs: ## 查看应用日志
	cd deploy && docker compose logs -f ai-fde-app

docker-ps: ## 查看服务状态
	cd deploy && docker compose ps

docker-prune: ## 清理未使用的Docker资源
	docker system prune -f

# ===== 数据库 =====
db-migrate: ## 执行数据库迁移
	alembic upgrade head

db-rollback: ## 回滚数据库迁移
	alembic downgrade -1

# ===== 备份 =====
backup: ## 备份数据
	cd deploy && bash backup.sh

# ===== 清理 =====
clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml 2>/dev/null || true

# ===== 项目初始化 =====
init: install ## 初始化项目（安装依赖+初始化数据库）
	@echo "项目初始化完成"
	@echo "运行 'make dev' 启动开发服务器"
