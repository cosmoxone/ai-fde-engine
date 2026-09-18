# TE 总体架构与 CE 边界（设计总纲）

> 版本：**v1.0** | 日期：2026-09-18 | 状态：**定稿**（本轮架构探讨的收口文档）
> 范围：TE（Team Edition）总体架构 × CE（Community Edition）边界定义 × 外部系统对接 × nf/RPA 双版本特性
> 分题文档：[25 号](25-CE多用户与OIDC支持设计.md)（认证抽象）· [26 号](26-nightfactory与RPA集成设计.md)（nf/RPA）·
> [23 号](23-开源商业双轨与EE目录规划.md)（双轨总纲）· ee/ 本地：design-te-v1.md v1.2 / roadmap-ee.md v1.2
> 一句话：**CE 保持"本地单用户内核+可替换认证点"；TE 以传统 SaaS 单体形态在替换点上整块接管
> 认证/租户/计量，并统一对接 CASDoor 与 Token Gateway 两类外部系统；nf/RPA 走双 profile 集成**

---

## 1. 设计历程与决策链（三版演进，思路存档）

本轮（2026-09-18）TE 架构经三版演进，每版被推翻的原因与最终结论：

| 版 | 方案 | 核心思路 | 推翻原因 / 结论 |
| --- | --- | --- | --- |
| v1.0 | **实例隔离**（每租户一 CE 容器） | 多租户外包给编排层，CE 零改动 | **推翻**：资源密度低一个量级、共享域要跨实例、协作查询绕远；用户拍板"走传统 SaaS 形态" |
| v1.1 | 传统 SaaS 单体多租户，**多用户/OIDC 下沉 CE 内核** | CE 内置三运行模式（单用户/OIDC/多租户） | **部分推翻**：多租户/OIDC 是 TE 商业特性，不应进开源版；CE 被 SaaS 假设污染，违背 open-core 边界 |
| **v1.2（定稿）** | 传统 SaaS 单体多租户，**CE 只留替换点** | CE=本地用户管理+AuthProvider 抽象；**TE 整块替换认证用户模块**（CASDoor+org 贯穿在 ee 层） | ✅ 最终形态（本文） |

**沉淀的设计原则**：商业特性以"内核替换点"接入而非"内核内置开关"——CE 永远不包含 SaaS 假设，
但必须为商业化留出干净的替换面（AuthProvider 即第一个此类替换点）。

## 2. 最终架构总图

```
   ┌─────────────────┐        ┌──────────────────────┐
   │ CASDoor 统一认证 │        │ Token Gateway          │
   │ (OIDC 登录/目录)  │        │ (LLM 代理 × token 计费) │
   └────────┬────────┘        └──────────┬───────────┘
            │ 替换 LocalAuthProvider                │ OpenAI 兼容 API（CE 零代码，
┌───────────▼──────────────────────────────────────▼──────────────┐
│ TE SaaS 单体（传统多租户应用）                                     │
│                                                                  │
│  ee 层（TE 特性）                    CE 内核（开源，无 SaaS 假设）  │
│  ├─ CasdoorAuthProvider ◄─替换─► ┌─ AuthProvider 抽象（替换点）    │
│  ├─ org 行级贯穿（PG 扩展）        │   └─ LocalAuthProvider 默认    │
│  │   （users/projects/tasks 加列） │      （单用户/本地多用户两档）   │
│  ├─ 订阅计量（席位×用量，软限）      ├─ 八步交付全流程（v0.4 全量）    │
│  ├─ 共享资产运营（团队 KB/经验库/   ├─ 知识库/本体（契约 14/20 号，   │
│  │   模板库——走契约面）            │   project_id 即租户内隔离单元）  │
│  ├─ nf/RPA 完整集成（回调/计量/    ├─ nf/RPA 精简集成（冻结面）      │
│  │   流水线）                      └─ Dashboard                     │
│  └─ 托管运维（备份/升级/巡检）                                      │
│                                                                  │
│  kb-os（共享 KB，契约 14）· 平台本体服务（契约 20）                    │
└──────────────────────────────────────────────────────────────────┘
```

## 3. CE 边界定义（进 / 不进 清单）

| 进 CE（开源，v0.5） | 不进 CE（TE 特性，ee 层） |
| --- | --- |
| AuthProvider 抽象（Protocol + 装配机制） | CASDoor/OIDC 对接（CasdoorAuthProvider） |
| LocalAuthProvider：单用户默认 + 本地多用户（邀请码流，≤10 人内网自托管定位） | 多租户 Org/org_id 贯穿（PG 行级扩展） |
| User/ProjectMember 表（SQLite）+ 项目角色矩阵 + client_viewer 只读白名单（OpenAPI 自动生成+契约测试） | 订阅/计量/账单（Token Gateway 计费数据对接） |
| 本地登录页与成员管理（本地多用户档） | 白标/审计合规（EE）/大容量层（EE） |
| nf 文件级导出 + RPA webhook 三端点 + 机器 token（**冻结面**） | nf/RPA 完整集成（回调/多租户路由/计量/流水线） |
| 全部 v0.4 既有能力原样（知识库=**Embedded 内置唯一推荐**） | 共享资产运营（团队 KB 发布流/经验库贡献审核）；**TE 默认接平台 kb-os 池** |

**判定规则**（后续新增特性的裁决依据）：*该能力是否要求"单机用户不部署任何外部系统就能用"？*
是 → CE（且不得因商业版阉割）；否（需要 CASDoor/TokenGateway/org 概念）→ ee 层经替换点或契约面接入。

## 4. 认证架构（替换制）

```
单机 CE（默认）      ：AuthProvider=local·单用户档 → 内置 local-admin，v0.4 行为零变化
本地多用户（可选）    ：AuthProvider=local·多用户档 → 邀请码+本地口令+签名 cookie
TE（ee 替换）        ：AuthProvider=casdoor → OIDC 授权码流+JWT 会话；用户目录/Org 同步自 CASDoor
EE（专属部署）       ：同 TE 替换件；CASDoor 可联邦企业 IdP（仅配置差异）
```

- 平台角色：admin/member；项目角色：project_owner / fde / domain_expert（审核队列）/ client_viewer（只读白名单）
- **凭证体系分离**：用户会话（OIDC/本地）与机器凭证（RPA webhook token、nf 文件交换）完全分离（D3）

## 5. 外部系统对接（统一外部系统原则）

| 系统 | 职责 | CE 对接方式 | TE 对接方式 |
| --- | --- | --- | --- |
| **CASDoor** | 统一认证（登录/MFA/用户目录/Org） | 不对接（CE 用本地用户管理） | CasdoorAuthProvider 整块替换（标准 OIDC，不绑定实现） |
| **Token Gateway** | LLM 代理 × token 计费 | 纯配置（`LOCAL_MODEL_BASE_URL` 指过去，OpenAI 兼容）；BYOK 直连不经网关 | 同配置路径 + 计费数据对接（gateway 侧出账）；nf 编码消耗也经此计量 |
| **kb-os** | 知识库模块（契约 14 v1.2） | **Embedded 内置（CE 唯一推荐形态）**；远程对接配置面保留但属 TE/EE 场景 | **平台 kb-os 项目池为 TE 默认**（`te-{org}-*` 命名域 + key 池编排） |
| **本体服务** | 本体模块（契约 20 v0.1） | Embedded 默认 / URL 可选 | 平台本体服务 + 团队共享域 |
| **night-factory** | 夜间无人值守编码 | 文件级导出（冻结） | API 派发+状态回调+org 仓库池 |
| **RPA** | 自动化测试执行 | webhook 三端点+机器 token（冻结） | 回调回推+org 路由+执行计量 |

## 6. 数据与租户模型

- **租户 = Org（订阅主体）**，仅存在于 ee 层：users/projects/tasks 等表在 ee 的 PG 扩展中加 `org_id` 列，行级过滤由 ee 注入（CE 查询无 org 概念，天然兼容）
- **项目即隔离单元**：CE 内 `project_id` 已贯穿知识库（契约 14）、本体（契约 20）、任务、导出——多租户下 org→项目集映射，隔离机制零改造
- **数据主权（红线 6）**：租户可自助全量导出（CE 数据+kb-os 项目导出）；TE→EE 整体迁移为设计预期

## 7. 演进路线

| 阶段 | 内容 | 依赖 |
| --- | --- | --- |
| CE v0.5（~3 周） | AuthProvider 抽象 + LocalAuthProvider 两档 + 成员/角色/白名单 + 登录页 | 无 |
| TE M1（~1.5 周） | CasdoorAuthProvider + org 贯穿（PG 扩展）+ TE 网关骨架 | CE v0.5 合入；CASDoor 实例 |
| TE M2-M3（~4 周） | 共享资产（kb-os key 池/经验库/模板库）+ Dashboard 壳 | kb-os admin API（W4 协作） |
| TE M4-M5（~3.5 周） | 订阅计量（Token Gateway 数据）+ 托管运维 + 计费通道 | Token Gateway 实例 |
| nf/RPA（并行） | 26 号发 nf/RPA 团队 → 双 profile 契约冻结 → TE 完整集成 | nf/RPA 团队评审 |
| EE v1.0（其后） | TE 整体搬迁专属部署（deploy-mode=saas\|dedicated）+ capacity/ops_toolkit/branding/audit/hybrid_cloud | TE v1.0 完成 |

## 8. 开放问题（后续裁决）

| # | 问题 | 状态 |
| --- | --- | --- |
| O1 | CASDoor 实例由谁运营（TE 平台侧统一 vs 每环境独立） | 待 TE M1 前定（倾向：平台统一，EE 联邦） |
| O2 | Token Gateway 是否已有现成实现/规格（对接规格文档） | 待外部提供（24 号总览已挂占位） |
| O3 | kb-os admin API（key 池自动化发放） | W4 协作项（TE M3 依赖，过渡期手工） |
| O4 | nf/RPA 双 profile 契约评审 | 26 号待发 nf/RPA 团队 |

## 9. 决策记录（截至 v1.0）

| # | 决策 | 日期 | 落档 |
| --- | --- | --- | --- |
| D0 | TE 优先实施；TE=全功能开箱即用；EE≈独立部署的 TE+增强包 | 09-18 | ee/design-te-v1 §0 |
| D-A1 | 实例隔离 → 传统 SaaS 单体多租户 | 09-18 | design-te-v1 v1.1 |
| D1 | 多租户/OIDC=TE 特性，不进 CE；CE=AuthProvider 抽象+本地用户管理 | 09-18 | 25 号 v1.1 |
| D2 | 认证=CASDoor（统一认证中心）；LLM 代理计费=Token Gateway | 09-18 | 25/24 号 |
| D3 | nf/RPA 双版本特性：CE 精简面冻结 × TE 完整面 | 09-18 | 26 号 |
| D4 | **知识库形态分轨**：CE=Embedded 内置唯一推荐（外部对接不进主线叙事）；TE=默认平台 kb-os 池 | 09-18 | 24/27 号 |

## 10. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-09-18 | 定稿：三版演进存档 / 最终架构总图 / CE 边界清单与判定规则 / 替换制认证 / 外部系统对接矩阵 / 演进路线 / 开放问题与决策记录 |
