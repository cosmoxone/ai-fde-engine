# AI-FDE Engine

> AI驱动的FDE（Forward Deployed Engineer）交付引擎 —— 用AI重构AI落地本身的生产方式

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-330%20passed-brightgreen.svg)](tests/)
[![CI](https://github.com/cosmoxone/ai-fde-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmoxone/ai-fde-engine/actions/workflows/ci.yml)

## 当前状态（请先阅读）

本项目处于 **MVP v1.0** 阶段，采用「接口真实 + 实现可切换」架构：

- ✅ **开箱可跑**：仅安装核心依赖（`requirements-core.txt`）、零 API Key，全部功能以 Mock/降级模式运行，330 个测试全绿
- ✅ **一键切换生产组件**：配置 `.env` 即可切换 DeepSeek/Qwen LLM、Docling 解析、Qdrant 知识库、DeepEval 评测、Aider 代码生成、Mem0 记忆（见 [模块切换指南](docs/05-模块切换指南.md)）
- ⚠️ **已知边界（规划中）**：业务数据为内存态存储（v1.1.0 将落地 SQLite 单文件持久化）；夜间迭代当前需手动触发（v1.1 进程内定时）。项目定位**本机/单容器**使用，API 无认证——请勿暴露公网。路线图见 [docs/09-后续规划.md](docs/09-后续规划.md)：开源主线聚焦单机开箱即用与交付价值，企业级特性（多用户/PostgreSQL/多租户）在商业轨道单独演进

## 项目简介

AI-FDE Engine 是一套面向FDE团队的AI化交付生产系统，把FDE从「手工作坊式交付」升级为「数据驱动的规模化交付」。

### 核心设计理念

1. **验证前置**：先做Benchmark、先定验收标准，再开发，需求基线可量化可验证
2. **AI主导、人做决策**：80%重复性工作AI自动执行，人只在关键节点审核
3. **日迭代闭环**：白天收集真实业务数据，夜间自动修复迭代
4. **记忆驱动**：时序知识图谱记忆，项目经验自动沉淀，跨项目复用

### 四大核心Agent

| Agent | 职责 | 推荐模型 |
| --- | --- | --- |
| 调研分析Agent | 业务流程建模、数据梳理、Benchmark生成、需求分析 | Qwen3.6 |
| 方案设计Agent | 产品方案、技术方案、验证方案并行生成 | DeepSeek V4 Pro |
| 开发交付Agent | 代码生成、知识库构建、Badcase修复、自动部署 | DeepSeek V4 Pro |
| 项目管控Agent | 进度跟踪、风险预警、文档生成、资产沉淀 | Qwen3.6 |

### 技术栈（2026年9月最新）

- **Agent编排**：Pydantic AI V2（类型安全、Capabilities可组合）
- **基础模型**：DeepSeek V4 Pro/Flash + Qwen3.6系列
- **记忆系统**：时序知识图谱（Zep Graphiti风格）+ 三级会话记忆
- **知识库**：LightRAG（知识图谱增强RAG）+ Qdrant v1.18
- **文档解析**：Marker v2 / Docling
- **评测引擎**：DeepEval（断言式评测 + 质量门禁）
- **代码生成**：OpenHands / Aider / OpenCode
- **迭代流水线**：Argo Workflows风格DAG编排
- **基础设施**：FastAPI + PostgreSQL + Redis + MinIO + Docker

## 快速开始

### 方式一：Docker Compose 一键部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url> ai-fde-engine
cd ai-fde-engine

# 2. 配置环境变量
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env，至少配置 LLM API Key
vim deploy/.env

# 3. 启动所有服务
cd deploy
docker compose up -d

# 4. 查看状态
docker compose ps

# 5. 访问Dashboard控制台
# http://localhost:8000/dashboard

# 6. 访问API文档
# http://localhost:8000/docs
```

### 方式二：本地开发

```bash
# 1. 安装核心依赖（Mock模式，零API Key可运行全部功能与330个测试）
pip install -r requirements-core.txt
pip install -e ".[dev]"

# 完整生产依赖（Docling/Qdrant/DeepEval/Aider/Mem0，镜像较大）
# pip install -r requirements.txt

# 2. 启动开发服务器
make dev
# 或: uvicorn src.main:app --reload

# 3. 访问Dashboard
# 浏览器打开 http://localhost:8000/dashboard

# 4. 运行测试
make test
```

### 三分钟体验（示例）

```bash
# 服务启动后，一键跑通：创建项目→上传文档→调研→Benchmark→夜间迭代
bash examples/run_demo.sh
```

## 两种使用模式

### 模式一：交互式调用（API驱动）
前端工具、IDE插件、聊天界面直接调用REST API，实时获取结果。
- 同步API：项目管理、自助交付、审核操作
- 异步API：调研/设计/交付/Benchmark/迭代（返回task_id，轮询任务状态）

### 模式二：后台异步流水线
提交需求后，Agent在后台自动完成全流程（调研→设计→开发→质量门禁→夜间迭代），完成后自动进入审核队列，人工审核确认后通知客户。
- Dashboard「审核工作台」查看所有待审核项
- 审核通过/驳回，支持批注
- 审核通过后自动推进项目阶段

## 项目结构

```
ai-fde-engine/
├── docs/                          # 项目文档（8份，完整工程链路）
│   ├── 01-需求文档.md             # 角色/功能F1-F8/非功能/验收标准
│   ├── 02-技术方案.md             # 架构/模块设计/数据模型/API
│   ├── 03-验证方案.md             # 四层验证/性能/安全测试方案
│   ├── 04-部署方案.md             # 部署架构/配置详解/备份恢复
│   ├── 05-模块切换指南.md         # Mock→真实组件切换手册
│   ├── 06-系统测试文档.md         # F1-F6系统测试用例
│   ├── 07-用户验收测试文档.md     # 分角色UAT场景
│   └── 08-测试用例追踪矩阵.md     # 需求→用例→脚本追踪
├── src/                           # 源代码
│   ├── main.py                    # FastAPI主应用（REST API + Dashboard）
│   ├── config.py                  # 配置管理（provider切换/模型路由）
│   ├── agents/                    # Agent层（自研框架，Pydantic AI风格）
│   │   ├── base.py                # Agent基类（Capabilities机制）
│   │   ├── research.py            # 调研分析Agent（F1）
│   │   ├── design.py              # 方案设计Agent（F2）
│   │   ├── delivery.py            # 开发交付Agent（F3）
│   │   ├── project.py             # 项目管控Agent（F6）
│   │   ├── self_service.py        # 自助交付Agent（F7）
│   │   └── training.py            # FDE培训成长Agent（F8）
│   ├── memory/                    # 记忆层
│   │   └── manager.py             # 双层记忆（图谱+会话，Mem0/Zep可切换）
│   ├── llm/                       # LLM层
│   │   └── client.py              # OpenAI兼容客户端（DeepSeek/Qwen/本地）
│   ├── tools/                     # 工具层（MCP风格，mock/真实可切换）
│   │   ├── doc_parser.py          # 文档解析（Mock/Docling/Marker）
│   │   ├── knowledge_base.py      # 知识库（Mock/Qdrant+embedding）
│   │   ├── benchmark.py           # Benchmark生成与跑批
│   │   ├── code_gen.py            # 代码生成（Mock/Aider/OpenHands）
│   │   └── data_explorer.py       # 数据探查
│   ├── evaluation/                # 评测层
│   │   └── evaluator.py           # 评测引擎 + 质量门禁（Mock/DeepEval）
│   └── pipeline/                  # 流水线层
│       └── iteration.py           # 夜间迭代流水线（DAG编排）
├── static/
│   └── dashboard.html             # Dashboard控制台（单文件）
├── tests/                         # 测试（330个：单元/集成/系统/自助/UAT）
├── examples/                      # 示例（业务文档/Badcase/API演示脚本）
├── deploy/                        # 部署配置（Docker Compose/Nginx/备份）
├── cli.py                         # CLI工具（前后端分离，HTTP调用）
├── mcp_server.py                  # MCP Server（接入Claude/Cursor等）
├── switch_modules.py              # 模块自动化切换脚本
├── demo_e2e.py                    # Agent层端到端演示
├── .github/workflows/ci.yml       # CI（ruff + pytest + docker build）
├── requirements-core.txt          # 核心依赖（Mock模式）
├── requirements.txt               # 全量依赖（真实组件）
├── pyproject.toml
├── Makefile
├── CONTRIBUTING.md                # 贡献指南
├── SECURITY.md                    # 安全策略
├── CHANGELOG.md                   # 更新日志
├── .gitignore
└── README.md
```

## API 概览

完整API文档请访问 `/docs`（Swagger UI）。

### 核心接口

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| POST | `/api/v1/projects` | 创建项目 |
| GET | `/api/v1/projects` | 项目列表 |
| POST | `/api/v1/projects/{id}/documents` | 上传文档 |
| POST | `/api/v1/projects/{id}/research/run` | 触发调研分析 |
| POST | `/api/v1/projects/{id}/design/run` | 触发方案设计 |
| POST | `/api/v1/projects/{id}/delivery/run` | 触发开发交付 |
| POST | `/api/v1/projects/{id}/benchmarks/generate` | 生成Benchmark |
| POST | `/api/v1/projects/{id}/benchmarks/{bid}/run` | 跑Benchmark评测 |
| POST | `/api/v1/projects/{id}/iteration/run` | 触发夜间迭代 |
| POST | `/api/v1/projects/{id}/badcases` | 提交Badcase反馈 |
| GET | `/api/v1/projects/{id}/memory/search` | 检索项目记忆 |
| GET | `/api/v1/projects/{id}/progress` | 项目进度 |
| GET | `/api/v1/tasks/{task_id}` | 任务状态 |
| GET | `/api/v1/health` | 健康检查 |

## 典型使用流程

```bash
# 1. 创建项目
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "智能审核助手", "client_name": "某制造企业", "industry": "制造业"}'

# 2. 上传业务文档
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/documents \
  -F "file=@业务手册.pdf"

# 3. 触发调研分析（异步）
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/research/run \
  -H "Content-Type: application/json" \
  -d '{"client_requirements": "需要一个智能资料审核助手"}'

# 4. 查看任务状态
curl http://localhost:8000/api/v1/tasks/{task_id}

# 5. 调研完成后触发方案设计
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/design/run

# 6. 生成Benchmark测试集
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/benchmarks/generate

# 7. 触发代码生成
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/delivery/run \
  -H "Content-Type: application/json" \
  -d '{"task_type": "generate_code", "project_name": "review-assistant"}'

# 8. 提交Badcase反馈，触发夜间迭代
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/iteration/run \
  -H "Content-Type: application/json" \
  -d '{"badcases": [{"id": "B1", "input": "用户问题", "actual_output": "错误回答", "severity": "major"}]}'
```

## 测试

```bash
# 运行全部测试
make test

# 查看测试覆盖率
make test-cov

# 代码检查
make lint
```

测试覆盖（共 330 个，全部通过）：
- 配置模块测试（9）
- 记忆系统测试（14）：记忆读写、检索、巩固、持久化、跨项目
- Agent测试（25）：四大Agent端到端流程 + Capability注入
- 工具测试（24）：文档解析、知识库、Benchmark、代码生成、数据探查
- 评测引擎测试（16）：断言、指标计算、质量门禁
- 迭代流水线测试（8）：全流程、回滚、版本报告
- API集成测试（21）：全部REST接口
- 系统测试（57）：F1-F6需求全覆盖（ST用例）
- 自助交付测试（45）：F7引导流程/机会识别/纠偏/审核
- 培训模块测试（34）：F8能力模型/学习路径/沙箱/教练
- UAT场景测试（77）：分角色验收场景

> 需求-用例-脚本追踪见 [测试用例追踪矩阵](docs/08-测试用例追踪矩阵.md)。

## 配置说明

核心配置项（通过环境变量或 `.env` 文件设置）：

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_PROVIDER` | 模型提供方 | deepseek |
| `DEEPSEEK_API_KEY` | DeepSeek API密钥 | - |
| `QWEN_API_KEY` | Qwen API密钥 | - |
| `MEMORY_PROVIDER` | 记忆提供方（mock/zep/mem0/letta） | mock |
| `DOC_PARSER_PROVIDER` | 文档解析提供方（mock/marker/docling） | mock |
| `KB_PROVIDER` | 知识库提供方（mock/lightrag） | mock |
| `EVALUATION_PROVIDER` | 评测提供方（mock/deepeval） | mock |
| `CODE_GEN_PROVIDER` | 代码生成提供方（mock/openhands/aider） | mock |

> MVP阶段所有外部依赖默认使用mock模式，无需配置API Key即可运行。
> 生产环境切换为真实服务，并安装对应可选依赖。

## 生产环境切换

从MVP mock模式切换到生产环境：

```bash
# 1. 安装生产依赖
pip install -e ".[all]"  # 包含docling、marker、deepeval

# 2. 修改.env配置
MEMORY_PROVIDER=zep
DOC_PARSER_PROVIDER=marker
KB_PROVIDER=lightrag
EVALUATION_PROVIDER=deepeval
CODE_GEN_PROVIDER=openhands

# 3. 配置Zep、OpenHands等外部服务地址
# 4. 重启服务
docker compose restart ai-fde-app
```

## 文档

详细文档请查看 [`docs/`](docs/) 目录：

- [需求文档](docs/01-需求文档.md) — 角色体系、功能需求F1-F8、非功能需求、验收标准
- [技术方案](docs/02-技术方案.md) — 架构设计、模块详细设计、数据模型、API设计
- [验证方案](docs/03-验证方案.md) — 测试策略、性能测试、安全测试、验收标准
- [部署方案](docs/04-部署方案.md) — 部署架构、环境要求、配置详解、备份恢复
- [模块切换指南](docs/05-模块切换指南.md) — Mock→真实组件切换、验证与回滚
- [系统测试文档](docs/06-系统测试文档.md) — F1-F6系统测试用例设计
- [用户验收测试文档](docs/07-用户验收测试文档.md) — 分角色UAT场景与记录模板
- [测试用例追踪矩阵](docs/08-测试用例追踪矩阵.md) — 需求→用例→自动化脚本追踪
- [后续规划](docs/09-后续规划.md) — 遗留问题清单 + P2 生产化路线（持久化/认证/调度/验收）

> 说明：技术方案中的架构为设计目标蓝图；当前代码为自研轻量 Agent 框架（Pydantic AI 风格的 Capabilities 机制），
> `pydantic-ai` 依赖保留以备后续迁移，Mock/真实组件切换能力已全部落地。

## 贡献指南

参见 [CONTRIBUTING.md](CONTRIBUTING.md)，要点：

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改（遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)）
4. 确保 `make lint` 与 `make test`（330 个测试）通过
5. 推送分支并开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 致谢

- [Pydantic AI](https://github.com/pydantic/pydantic-ai) - 类型安全的Agent框架
- [LightRAG](https://github.com/HKUDS/LightRAG) - 轻量级知识图谱RAG
- [DeepSeek](https://github.com/deepseek-ai) - 开源大模型
- [Qwen](https://github.com/QwenLM) - 通义千问开源模型
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) - 开源自主编程Agent
- [DeepEval](https://github.com/confident-ai/deepeval) - LLM评测框架
