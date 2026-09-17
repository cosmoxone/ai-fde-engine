# 更新日志

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.4.0] - 2026-09-17 知识与本体（v0.4-a 契约接入 × v0.4-b 本体抽取 × v0.4-c Research RAG 化）

> **发布概要**：测试 488→549 全绿（含契约套件 13 用例）；契约 14 号 v1.2 定版并双实现（Embedded × kb-os 真机）对拍一致；
> 新增 `src/knowledge/`（8 模块）与 `src/ontology/`（7 模块，含对外独立服务契约 20 号 v0.1-draft）；
> Dashboard 新增知识库 + 本体图谱两页面；文档组扩展至 13~21 号（含 RAG 技术立场 ADR 与两日冲刺过程复盘）。

### v0.4-c — Research RAG 化与迭代闭环

#### Added — research RAG 化（设计 13 号 §3.3 机制 2/4；决策依据 18 号）

- **三模式输入组装** `research_rag_mode`（config，默认 `hybrid`）：`full` 现状全文截断（基线）/ `hybrid` 知识库检索块+本体摘要+每文档压缩摘要 / `rag` 纯检索+文档清单——修掉 `content[:30000]` 静默截断（约 97% 内容丢弃）
- **适用边界代码化**（18 号 §6）：KB 无命中自动回退 full（`full-fallback`），检索/本体异常不阻断
- **`input_stats` 成本观测**：mode_effective/kb_hits/ontology_injected/prompt_chars/full_chars/reduction——RAG vs 全文对比数据（发布时进 golden-real 两栏报告）
- **本体注入**：`business_model_summary` 进 research prompt（13 号机制 1×2 枢纽）
- **badcase→CuratedEntry 闭环**（机制 4）：knowledge 归因修复 → 草稿进 pending 审核队列（origin=badcase-loop，幂等；人工确认门，不直接污染知识库；KB 故障不阻断）
- **Embedded 检索质量修复**：查询整串 phrase 匹配对自然语言长句命中率极低 → 三级降级（整串 phrase → 分片 OR → LIKE 兜底）——RAG 消费场景的必要修复，契约语义不变
- **黄金集两栏终验 PASS**（deepseek-chat，2026-09-17）：hybrid 98.59%（70/71）≥ full 97.18%（69/71）——18 号 ADR 结论生效，RAG 化默认维持；hybrid 栏评估器内置"先 ingest 再检索"（否则空检索回退 full、两栏失真）
- **机制 3 Benchmark 溯源**：hybrid/rag 模式下 `test_case.source={filename, chunk_index}` 注入（合同级验收标准可追溯；full 留空兼容）
- 修复：`src/llm/client.py` httpx 补 `trust_env=False`（本机 socks 代理环境变量毒化 LLM 调用，静默回退 mock——21 号复盘 E1 同源问题再犯，已修）

#### Changed

- `research.run()` 输出 metadata 增 `input_stats`；测试 545 passed（+6：三模式/回退/本体注入/闭环幂等/KB 故障隔离）

### v0.4-b — 本体抽取与对外服务

#### Added — 本体模块 `src/ontology/`（~1000 行；设计 13 号 §3.2，对外契约 20 号 v0.1-draft）

- **数据与存储**：`types.py`（Entity/Relation/Rule/MergeReport，稳定哈希 id 幂等）+ `store.py`（SQLite 增量 merge：同名实体属性合并、source_docs 追加去重、**图规模不重复增长**；孤儿关系过滤；**软删不复活**——人工删除权威，13 号风险表）
- **抽取管线**：`extractor.py` LLM 结构化抽取（chat_json + required_keys 校验重试）+ Mock 行业模板派生（制造业模板 24 实体/18 关系/4 规则 + 文档标题派生项目实体；无 Key 流程可跑通）
- **三态 Gateway**（镜像知识库接入层）：Embedded（默认）/ Remote（`ONTOLOGY_SERVICE_URL` 即启用）/ Fallback（远端故障降级 Embedded 标记 degraded_since；契约错误不降级）
- **对外独立服务**：`server.py`（六端点 `/extract /graph /mermaid /summary /entities /hints` + 软删 DELETE；`ONTOLOGY_SERVICE_TOKEN` 可选鉴权；`X-Onto-Project` 项目上下文；错误统一 `{"error":{code,message}}`）——**独立组件融合入口**：`POST /hints` 供前期处理组件生成 entity_hints
- **引擎接线**：`POST /api/v1/projects/{id}/ontology/extract`（任务化增量，doc_ref 记账跳过已抽取，force 重抽幂等）+ 图/Mermaid/摘要/实体检索/人工删除 6 端点；`entity_hints` 预标注回填 `knowledge/pipeline`（本体不可用回退空，不违契约 14 号"存而不滤"）
- 测试 539 passed（+19：merge 幂等/增量验收/软删/网关三态/独立服务/引擎 API/hints 回填闭环）

### v0.4-a — 知识库契约与接入层（契约 14 号 v1.2 [W0 转正] × kb-os 联合方案；W3 真机对拍 13/13）

#### Added — 知识库独立模块接入（契约 14 号 v1.2 [W0 转正] × kb-os 联合方案）

**契约协作**（双方共识存档：`docs/15-对接方案评审回复.md` × kb-os《09-ai-fde对接方案》v1.1 §七）：
- 14 号规格三轮升版（v1.0→v1.1→v1.2，2026-09-17 W0 会议确认转正正式版）：文档级推送主协议（幂等按 doc_id）、Scoped API Key 即项目身份（请求体去 project_id）、页码分页、就绪信号文档级 `parsing`（三元不变量 `documents+parsing+parse_failed=累计接受`）、错误码表定版（稳定字符串码 + kb-os 数字码映射 + `error_key` 双轨）、溯源五字段必填、附录 A chunk 降级模式
- 三决策定版：文档级推送 / scoped key 隔离 / 走法 A（KbOsGateway 薄适配器，~1 人日）
- 契约测试套件 `tests/contract/`：场景内核 + spec14/kb-os 双断言适配（13 用例，集成性质，需 `KB_BASE_URL`）；对参考服务实测 12 过 1 跳（鉴权负例）
- **W3 真机对拍 13/13 通过**（2026-09-17，kb-os 联调实例 8011 × WeKnora 引擎 × scoped key）：合入 kb-os 预演报告（[17 号](docs/17-W3对拍预演报告-kb-os.md)）定位的 stats 用例跨测试隔离修复（`before=wait(kb)`，异步索引实现必需），双实现零回归；对拍回执 [19 号](docs/19-W3对拍结果回执-ai-fde.md)
- 技术立场存档 `docs/18-RAG化技术立场-v0.4-c决策依据.md`：v0.4-c RAG 化决策依据（RAG-less 趋势辨析、检索不可替代的四场景、黄金集止损线与适用边界规则）

**代码落地 `src/knowledge/`**（~1100 行）：
- `types.py` 契约类型与错误体系（KBContractError 4xx 不降级 / KnowledgeGatewayError 触发降级）
- `chunker.py` 标题感知切块器（title_path 滚动、字符偏移溯源、超长句读二次切分）
- `embedded.py` EmbeddedKnowledgeGateway：SQLite FTS5 trigram 参考实现（「参考实现即规格」；文档级 ingest + 附录 A 降级 + curate 生命周期 + BM25 归一化 + curated 加权）
- `kbos.py` KbOsGateway：kb-os 原生 API 适配（Envelope 解包、error_key 优先、50002→降级语义）
- `gateway.py` 工厂（`KNOWLEDGE_SERVICE_URL` 热切换）+ FallbackKnowledgeGateway（Remote 不可用自动降级 Embedded 并标记）
- `server.py` spec14 HTTP 参考服务（全端点 + 鉴权 + 错误分支；`uvicorn src.knowledge.server:app`）
- `pipeline.py` 上传自动 ingest（失败不阻断，`kb_status` 记入文档记录）+ 项目级重建

**引擎接线**：
- 上传文档自动入知识库（文档级主协议）；Dashboard 端点：`GET /projects/{id}/kb/stats|search`、`POST /projects/{id}/kb/ingest`（重建）、`GET /kb/entries`（待确认队列）、`POST /kb/entries/{id}/confirm|reject`
- `config` 新增 `knowledge_service_url / knowledge_service_token / knowledge_db_path`

#### Changed

- 测试 488 → **520 passed**（+32 知识库单测/API 测试全绿；契约 13 条集成态按守卫跳过）
- 13 号设计文档摘要与 14 号 v1.2 对齐；09 号 roadmap 落 v0.4-a 范围与 kb-os 协作排期（W1~W3）

## [0.3.0] - 2026-09-08

### Added — 四大卖点定位（生态集成版）

**定位重构**：本项目深做卖点 1+2（本体抽取/需求分析、自动知识库/Benchmark），卖点 3/4 通过生态集成编排：
- **卖点3 night-factory 集成**：`GET /delivery/tickets`（需求基线→工单，schema 兼容 night-factory tasks/*.json）；**核心衔接：需求量化验收标准 → 工单 acceptance[]**（验证前置跨产品贯穿）；priority→预算映射（P0=high）
- **卖点4 RPA 编排**：`POST /benchmarks/{id}/rpa-dispatch`（webhook 契约见 rpa_runner.py；未配置返回 pending_integration）
- **夜间迭代定时调度**（遗留L2-1收口）：零依赖进程内调度，`iteration_cron="HH:MM"` 每日触发全部项目，空/旧格式自动关闭
- `docs/benchmarks/golden-real.md` 真实 LLM 报告占位（待 API Key 生成，含决策原则：达标才宣传）
- README 中英重构为四大卖点叙事表

### Changed

- 测试 470 → **479**（生态集成 9 条）

## [0.2.1] - 2026-09-07

### Added

- **文档体系完善**：`docs/00-文档导读.md`（按角色索引 + 设计基线 vs 实现现状对照表）；01-07 号文档统一加状态标注（语义有效/已更新/差异说明）；技术方案新增「v0.2.0 实现现状」附录（架构演进对照 + 新增模块图谱）

### Changed

- 方法论专栏移出仓库管理（本地 `content/`，已 gitignore）

## [0.2.0] - 2026-09-07

### Added

- **本地经验库（D1）**：`GET /api/v1/memory/global/search` 跨项目记忆检索（按重要性排序、标注来源项目）——「这个客户类似问题以前怎么解决的」；`GET /projects/{id}/retrospective` 一键复盘报告（执行概况/需求范围/质量与 badcase 归因/评审协同/经验沉淀清单，零数据容错）；复盘纳入交付物（07-复盘报告，MD/DOCX）；Dashboard 新增 🧠 经验库页
- **模板贡献体系（D2）**：`src/templates/validate.py` 贡献准入校验器（量化验收红线/对抗安全红线/三类齐备，CLI 一键自检）；`docs/12-模板贡献指南.md`（字段规范/评审标准/认领方向）
- **公开评测基准（D3）**：`python -m src.evaluation.benchmark_report` —— 内置种子集 × 评测器基线（三行业指标 + 门禁判定），mock 模式零依赖可复现；报告输出至 `docs/benchmarks/baseline.md`

### Changed

- 测试 450 → **470**（经验库 6/模板校验 11/基准报告 3）

## [0.1.4] - 2026-09-07

### Added

- **MCP 工具全覆盖（C2）**：26 个工具覆盖完整交付流程（新增 12 个：文档上传/列表、Benchmark 生成/列表/评测、夜间迭代、badcase 提交/列表、交付物导出、需求编辑、记忆检索）——Claude Desktop/Cursor 用户可直接驱动全流程；multipart 上传双实现（requests/urllib 手工 boundary 降级）
- **CLI 全流程整合（C1'）**：`aifde` 命令就绪（serve/doc/badcase/export/templates/golden/llm + 原有 project/agent/task/review）；`[project.scripts]` 入口，src 布局打包就绪（PyPI 发布按计划暂缓）
- **英文 README（C3）**：`README.en.md` + 中文主页语言切换
- **社区建设（C4）**：GitHub Discussions 开启（Show your delivery）；贡献方向标签（template/golden-set/good first issue）
- **CI 覆盖率报告（C5'）**：pytest-cov → Job Summary（零外部服务依赖）

### Fixed

- CLI/MCP 客户端 urllib 路径 `data={}` 误判为无 body 导致 POST 422

### Changed

- 测试 444 → **450**（MCP 工具契约 6 条，另 1 条运行时用例随 mcp 包执行）

## [0.1.3] - 2026-09-07

### Added

- **可编辑确认流（B4）**：`PATCH /projects/{id}/requirements/{rid}` 与 `PATCH /projects/{id}/solutions/features/{fid}`——AI 产出为初稿，FDE 修改后直接进入基线（记录修改轨迹），导出交付物包含最新内容；Dashboard 项目详情新增「需求基线✏️」标签页支持行内编辑
- **FDE 用户手册（B6）**：`docs/11-用户手册.md`——30 分钟跑通首个项目全流程（安装/配 Key/八步操作/日常工作流/FAQ/命令速查）

### Changed

- 测试 438 → **444**（可编辑确认流 6 条）
- 路线图版本调整：分发生态顺延为 v0.1.4

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
