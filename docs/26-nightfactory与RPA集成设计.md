# night-factory / RPA 集成设计（CE 精简 × TE 完整双特性）

> 版本：**v1.0-draft** | 日期：2026-09-18 | 状态：设计稿（含对 nf/RPA 侧的设计要求）
> 背景（2026-09-18 拍板）：**nf 与 RPA 同样存在"TE 版本特性 × CE 精简特性"问题**——CE 只集成对接
> **core 精简部分**；TE 环境用完整版能力。本文从 **CE 角度 / nf 角度 / RPA 角度**三方设计。
> 现状盘点：night-factory=**文件级单向导出**（需求基线→`tasks/*.json` 工单，schema 兼容）；
> RPA=**webhook 三端点**（`POST /jobs` 派发、`GET /jobs/{id}` 轮询；`src/integrations/rpa_runner.py` 注释即契约）

---

## 1. 双版本特性问题定义

nf（夜间无人值守编码系统）与 RPA（自动化测试执行）是**独立外部产品**，对接形态随部署环境分叉：

```
CE（单机开源）──精简集成──→ nf / RPA 的 CE 兼容模式（core API 子集）
TE（SaaS/EE）──完整集成──→ nf / RPA 的 TE 模式（认证统一/多租户/回调/计量）
```

**原则**（延续本仓库双轨红线）：

1. **CE 集成面冻结为最小核心**：文件级/webhook 级、静态机器凭证、单项目语义、零编排——精简面即**稳定性承诺**（像契约 14 号一样冻结，不随 TE 需求膨胀）
2. **TE 完整能力在 ee 层编排**：不往 CE 集成核心塞 TE 特性；TE 需要的新面（回调/多租户/计量）由 nf/RPA 侧提供 **TE 模式 API**，ee 层适配
3. **nf/RPA 侧双 profile**：同一产品两种 API profile（CE 兼容模式冻结 / TE 模式迭代）——这是对 nf/RPA 团队的核心设计要求

## 2. CE 精简集成（core 子集，v0.5 冻结）

### 2.1 night-factory（CE 面）

| 项 | 设计 |
| --- | --- |
| 集成方式 | **文件级导出**（现状保留并冻结）：`generate_tickets()` → `tasks/*.json`（schema 兼容 nf tasks 目录，含 acceptance 机械化验收） |
| 状态回流 | **手动/文件级**：CE 不调 nf API；用户把 nf 产物（PR/报告）自行接入项目交付物（上传端点既有） |
| 配置 | `NIGHT_FACTORY_TARGET_REPO`（唯一配置项） |
| 认证 | 无（文件交换无需认证） |
| 语义 | 单项目→单仓库；无并发/租户概念 |

### 2.2 RPA（CE 面）

| 项 | 设计 |
| --- | --- |
| 集成方式 | **webhook 三端点**（现状冻结）：`POST {RPA_WEBHOOK_URL}/jobs`、`GET /jobs/{id}`；轮询模式（无回调要求） |
| 认证 | **静态机器 token**（v0.5 新增）：`RPA_MACHINE_TOKEN` 共享密钥，`Authorization: Bearer` 头双向（CE→RPA 派发带 token；RPA 若回调也带）；与用户会话体系**完全分离**（D3 拍板） |
| 语义 | 单项目单端点；job 生命周期=dispatched→running→completed |
| 未配置行为 | `pending_integration`（现状：编排位就绪，明确提示）——保持 |

### 2.3 CE 面验收

- 工单 schema 快照测试（冻结）；RPA 三端点契约测试（mock server：token 校验/401/轮询闭环）
- 零新增必选依赖；`requirements-core.txt` 不变

## 3. TE 完整集成（ee 层编排，nf/RPA TE 模式）

### 3.1 能力矩阵（CE 精简 vs TE 完整）

| 能力 | CE 精简 | TE 完整（ee + nf/RPA TE 模式） |
| --- | --- | --- |
| 工单/任务派发 | 文件导出 / webhook 派发 | **API 派发**（带 org/project 上下文） |
| 状态同步 | 手动 / 轮询 | **回调推送**（nf 工单状态、RPA job 结果 webhook 回推 CE 实例 → 任务进度自动更新） |
| 认证 | 静态机器 token | **服务账号凭证**（CASDoor client_credentials / 平台签发的服务 token；经 TE 网关交换） |
| 多租户 | 无 | **org 路由**：nf 仓库池 `te-{org}-*`；RPA job 带 `X-TE-Org`，结果按 org 回投 |
| 计量 | 无 | nf 编码 token 走 **Token Gateway**（nf 侧 LLM 消耗统一计费）；RPA 按执行时长/用例数计量 |
| 编排 | 人工串联 | **交付流水线自动串联**：Benchmark→RPA 执行→night-factory 修复→回归（night-factory 定时迭代既有钩子扩展） |
| 并发 | 单项目 | 多项目并行队列（ee 层任务队列调度） |

### 3.2 ee 侧落位

```
ee/src/integrations_te/
├── nf_te_client.py      # nf TE 模式客户端（API 派发/状态订阅/回调接收）
├── rpa_te_client.py     # RPA TE 模式客户端（回调接收替代轮询）
├── callback_router.py   # 回调统一入口：验签→org 路由→映射到租户项目任务
└── metering_hook.py     # nf/RPA 用量→计量汇聚（token gateway 数据对账）
```

CE 侧**零改动**：TE 回调经 ee 网关转成 CE 既有任务更新 API（复用 `update_task`）。

## 4. 对 nf / RPA 侧的设计要求（协作输入）

### 4.1 双 profile API 矩阵（请 nf/RPA 团队按此提供）

| 面 | CE 兼容模式（冻结） | TE 模式（可迭代） |
| --- | --- | --- |
| nf 工单 | `tasks/*.json` 文件 schema（**现状即契约，冻结**） | `POST /api/te/tickets`（org 上下文+服务凭证）；`PATCH /tickets/{id}/status` 回调注册 |
| nf 消耗 | 自备 LLM key | LLM 调用路由 **Token Gateway**（平台 key 注入） |
| RPA 派发 | `POST /jobs`（静态 token）+ `GET /jobs/{id}` | 同端点 + `X-TE-Org` 头 + **`POST {callback}/jobs/{id}/result` 回调**（签名回推） |
| 版本策略 | v1 冻结（变更需 deprecation 通知，14 号兼容策略风格） | 语义化版本迭代 |

### 4.2 契约化建议

nf 工单 schema 与 RPA webhook 契约目前以"代码注释+文档"存在——建议照 14 号模式**各出一份接口契约文档**
（冻结面/错误码/幂等键），对拍用 CE 侧既有 mock 契约测试（RPA 已有测试位）。协作顺序：nf/RPA 出契约
草案 → CE 侧对齐验收测试 → 冻结 v1。

## 5. 演进与兼容

| 阶段 | 内容 |
| --- | --- |
| v0.5（CE） | RPA 机器 token 补齐 + 两契约文档化冻结 + 契约测试（~3 天） |
| TE M3+（ee） | nf/RPA TE 模式客户端与回调路由（依赖 nf/RPA 侧 TE API 就绪，W4 类协作项） |
| 后续 | EE 专属部署：nf/RPA 可整体随安装包部署（专属实例），认证联邦回企业 IdP |

## 6. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0-draft | 2026-09-18 | 初版：双版本特性问题定义 / CE 精简面冻结（nf 文件级+RPA webhook+机器 token）/ TE 完整面（回调/多租户/计量/流水线）/ nf·RPA 侧双 profile API 矩阵与契约化建议 |
