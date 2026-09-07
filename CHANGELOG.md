# 更新日志

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.1.2] - 2026-09-07

### Added

- **交付物导出（B1）**：`GET /projects/{id}/export?format=md|docx` 打包 6 类交付物（项目概览/需求基线/三方案/Benchmark 测试集/迭代报告/评审记录）为 zip；Markdown 零依赖渲染，DOCX 由 python-docx 渲染（未安装自动降级 MD）；Dashboard 项目列表一键导出
- **行业模板库（B2）**：内置制造业质检/金融客服/政务问答三个行业包（调研行业上下文/需求模板/行业 Benchmark 种子含对抗安全样例/方案骨架）；创建项目按行业自动匹配注入；`GET /api/v1/templates`；TemplateSource 扩展点（TE 订阅源可替换）
- **真实 LLM 输出打磨（B3）**：`_call_llm` 增加 required_keys 校验 + 带反馈自动重试；**DesignAgent 补齐真实 LLM 路径**（原为纯 mock）；20 条需求基线黄金集（制造 8/金融 6/政务 6）+ 命中率评估 CLI（`python -m src.evaluation.golden`）
- **Badcase 修复建议闭环（B5）**：Badcase 持久化入库；夜间迭代自动归集未处理 badcase、处理完标记版本；不可自动修复的 badcase 输出**修复建议**（业务规则确认草稿/拒答话术+防回归用例）供 FDE 晨间采纳；Dashboard 质量中心 10 秒提交 Badcase

### Changed

- 测试 392 → **438**（导出 14/模板 17/LLM 质量 8/Badcase 闭环 9 + 契约扩展）

### Deferred

- B4 可编辑确认流、B6 用户手册顺延至 v0.1.2.x 收尾迭代（见 docs/09）

## [0.1.1] - 2026-09-07

### Added

- **SQLite 单文件持久化（A1）**：默认 `STORAGE_PROVIDER=sqlite`，业务数据落 `data/aifde.db`（WAL），重启/升级不丢；内存实现保留给测试（`memory`）
- **存储扩展点（A1/A5）**：`src/storage/` 抽象契约 + 双实现（memory/sqlite 契约测试 42 条双跑），TE 商业版可替换 PostgreSQL 后端
- **商业扩展点预留（A5）**：`src/extensions/` PluginRegistry（注册/能力开关/edition 探测）+ AuthProvider 抽象（CE 默认 NoopAuth）
- **单容器模式（A2）**：`docker run -v aifde-data:/app/data` 即全功能；六服务编排降级为可选 `docker-compose.full.yml`；Makefile 新增 `docker-single`
- **Web 配置引导（A3）**：`GET/POST /api/v1/settings/llm`（Key 脱敏返回、保存即热生效、`data/settings.json` 持久化、启动自动恢复）；Dashboard Mock 模式提示条 + LLM 配置弹窗
- **体验打磨（A4）**：`run_demo.sh` 交付物摘要导出到 `output/`

### Fixed

- **SQLite 更新丢列**：`INSERT OR REPLACE` 整行替换导致 `update_task` 后 `project_id` 附属列清空，任务按项目过滤失效；改为定向 `UPDATE data` 列，新增防回归契约测试

### Changed

- `main.py` 全部内存 dict 重构为 storage 调用（API 行为不变）
- 测试 330 → **392**（存储 42 / 扩展点 10 / 运行时设置 9 / 原有 330 + 矩阵回填）

## [0.1.0] - 2026-09-06

### Added

- **四大核心 Agent**：调研分析（F1）、方案设计（F2）、开发交付（F3）、项目管控（F6）
- **自助交付 Agent（F7）**：引导式项目创建、AI 落地机会识别、需求自助梳理、方案自助配置、原型即时生成、价值仪表盘、后台 Review 工作台、智能纠偏
- **FDE 培训成长 Agent（F8）**：能力模型、个性化学习路径、AI 教练对话、实战演练沙箱、能力评估
- **工具层（MCP 风格）**：文档解析、知识库、Benchmark、代码生成、数据探查，全部支持 mock/真实实现切换
- **评测引擎 + 质量门禁**：断言式评测、指标门禁（准确率/幻觉率/召回率/格式合规率/安全合规率）
- **夜间迭代流水线**：数据归集 → 自动归因 → 自动修复 → 回归测试 → 门禁判断 → 自动部署 → 版本报告
- **双层记忆系统**：时序知识图谱（长期）+ 三级会话记忆（运行时），支持跨项目经验检索与记忆巩固
- **REST API + Dashboard 控制台**：项目管理、异步任务、审核工作台、质量中心、自助交付看板
- **CLI 工具**（`cli.py`）与 **MCP Server**（`mcp_server.py`，可接入 Claude Desktop/Cursor 等）
- **模块自动化切换脚本**（`switch_modules.py`）：status/check/run/rollback/verify/report
- **部署方案**：Docker Compose 六服务编排（app/nginx/PostgreSQL/Qdrant/MinIO/Redis）、多阶段构建、备份脚本
- **测试体系**：330 个自动化测试（单元/集成/系统/自助交付/培训/UAT），零外部依赖即可运行
- **文档体系**：需求文档、技术方案、验证方案、部署方案、模块切换指南、系统测试、UAT、测试追踪矩阵

### Notes

- MVP 阶段所有外部组件默认 mock/降级模式，配置 API Key 后可切换真实组件
- 已知边界：业务数据为内存态存储（生产化需接入 PostgreSQL）、API 认证未实现、夜间迭代需手动触发
