# 更新日志

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
