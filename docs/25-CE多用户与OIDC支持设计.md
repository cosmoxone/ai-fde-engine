# CE 多用户与 OIDC 支持（v0.5 设计）

> 版本：**v1.0-draft** | 日期：2026-09-18 | 状态：设计探讨稿（待拍板）
> 背景：TE 走传统 SaaS 形态（单应用多租户），多用户与第三方认证**下沉 CE 内核**（2026-09-18 拍板）；
> 认证对接 **CASDoor**（统一认证中心），LLM 代理计费走 **Token Gateway**（统一外部系统）
> 关联：[23 号](23-开源商业双轨与EE目录规划.md)（双轨）/ ee 侧 design-te-v1.md v1.1（本地）
> 兼容红线：**无 OIDC 配置 = 现单用户模式，单机零依赖不变**（CI 承诺、Mock 模式、既有用户无感升级）

---

## 1. 设计目标与分层原则

```
改造分层（什么进 CE 开源、什么留 TE）：
  CE v0.5（本设计）  ：多用户系统 + OIDC 登录 + 项目成员/角色 —— 通用能力，开源用户同样受益
                        （开源用户可自接 CASDoor 自托管团队部署 = 免费版"小 TE"，符合获客逻辑）
  TE（ee/，不改内核） ：租户(Org)编排 + 订阅计量 + 共享资产运营 + 托管运维
  统一外部系统（对接） ：CASDoor（认证） / Token Gateway（LLM 代理+计费）——CE 只对接不自建
```

## 2. 用户与认证模型

### 2.1 三种运行模式（一个内核，配置决定形态）

| 模式 | 触发条件 | 行为 | 用户 |
| --- | --- | --- | --- |
| **单用户模式（现状）** | 未配置 `AUTH_PROVIDER` | 完全等同 v0.4.0：无登录页、所有 API 直通、SQLite 默认 | 单人（本地） |
| **OIDC 模式** | `AUTH_PROVIDER=oidc` + CASDoor 端点 | 登录页→CASDoor 授权码流；API 需 JWT 会话 | 多用户（团队自托管） |
| **OIDC+多租户（TE）** | OIDC + Org 数据 | 同上 + tenant 贯穿 + 订阅计量（ee 层） | SaaS 全量 |

**实现要点**：FastAPI 认证依赖注入（`get_current_user`）——单用户模式返回内置 `local-admin`（行为零变化）；OIDC 模式解析 JWT 会话 cookie。全部端点经统一依赖，项目 API 追加成员归属校验。

### 2.2 CASDoor 对接（OIDC）

- 协议：OIDC Authorization Code + PKCE；CASDoor 作为 **Provider**（应用注册→client_id/secret→回调）
- CE 侧新增（预计 ~300 行 + 测试）：
  - `src/auth/oidc.py`：授权跳转/回调换 token/JWKS 验签（复用 httpx，trust_env=False）
  - `src/auth/session.py`：HttpOnly cookie 会话（签名 JWT，含 user_id/org_id/roles）
  - `src/auth/models.py`：`User`（id/external_sub/邮箱/显示名/平台角色/状态）、`ProjectMember`（project_id/user_id/项目角色）
  - `GET /api/v1/auth/login|callback|logout|me` + Dashboard 登录页（无 OIDC 时不出现）
- CASDoor 侧约定：应用=ai-fde；用户属性映射 `sub/email/name`；组织（Org）映射 CE 租户（TE 模式）
- **不绑定 CASDoor**：标准 OIDC（Keycloak/企业 IdP 均可）；CASDoor 为默认实测对象

### 2.3 角色模型（与 TE 设计对齐）

| 层 | 角色 | 权限 |
| --- | --- | --- |
| 平台 | admin（内置首个）/ member | 管理用户/全局配置 vs 常规 |
| 项目 | project_owner / fde / domain_expert / client_viewer | 全权 / 交付操作 / 审核队列（KB 条目·本体·经验） / **只读白名单**（读端点子集+验收标记） |

只读白名单由 CE OpenAPI 端点清单自动生成（GET 集合 + 验收类端点），契约测试守护（CE 端点演进不破 TE）。

## 3. 租户（Org）与数据层

### 3.1 租户模型（v0.5 先最小，TE 扩展）

```
User ──N:M── ProjectMember ──N:1── Project ──N:1── Org(v0.6 表; TE 层先以 org_id 字段承载)
```

- v0.5（本设计）：**User + ProjectMember** 进内核；项目归属 user/org 以 `org_id` 字段预留（默认 `local`）
- 租户贯穿 = `org_id` 行级过滤：所有 storage 查询经统一 scope 注入（SQLite/PG 同语义）
- TE（ee 层）：Org 生命周期/订阅/计量——消费 `org_id`，不新增隔离机制

### 3.2 storage 层扩展

| 项 | 现状 | v0.5 |
| --- | --- | --- |
| SQLite | ✅ | ✅ 新增 users/project_members 表（单机多用户自托管可用） |
| PostgreSQL | —（全量编排历史遗留） | **新增 provider**（TE SaaS 需要；复用现有 StorageProvider 抽象，行级 org_id） |
| 知识库/本体 | 独立 SQLite，project_id 隔离 | **零改造**（project_id 即租户内隔离单元；SaaS 下可配 PG 版网关实现，契约 14/20 不变） |

## 4. Token Gateway（LLM 代理与计费）

**CE 零代码改动**，纯配置对接（既有能力组合）：

```bash
# 平台代理模式（计费在 gateway 侧按 token 记）
LLM_PROVIDER=custom
LOCAL_MODEL_BASE_URL=https://token-gateway.internal/v1
LOCAL_MODEL_API_KEY=<gateway 发放的代理 key>
MODEL_TASK_RESEARCH=deepseek-chat   # gateway 透传模型名（白名单在 gateway 侧）
```

- BYOK：用户配自己的 `DEEPSEEK_API_KEY` 等 → 流量不经 gateway、不计平台费（te-gateway 层按 header 路由提示）
- 用量：gateway 侧计费系统出账；CE 的 health/统计不涉计费语义（解耦）
- 文档职责：本设计 + 24 号总览写清配置法；CE 不实现计费

## 5. API 与前端变化

- 新增：`/api/v1/auth/*`（登录流）；`/api/v1/users`（admin：列表/禁用）；`/api/v1/projects/{id}/members`（邀请/改角色/移除）
- 既有端点：全部加认证依赖（单用户模式无感）+ 项目成员校验（client_viewer 白名单）
- Dashboard：登录页（OIDC 模式）；成员管理入口；用户菜单；**单用户模式界面零变化**
- 导出/备份：全量导出能力随多用户扩展（user/project/member 关系一并导出——反锁定承诺）

## 6. 兼容与迁移

| 场景 | 升级路径 |
| --- | --- |
| v0.4 单机用户 → v0.5 | 零操作：无 AUTH_PROVIDER 即旧行为；DB 自动迁移加表（空用户表） |
| 单机 → 自托管多用户 | 起 CASDoor（或任意 OIDC）→ 配 3 个环境变量 → 邀请成员 |
| 自托管多用户 → TE SaaS | 数据导出→导入（PG）+ CASDoor Org 迁移；或直接把部署交给托管 |
| TE SaaS → EE 专属 | 整库导出 + 同一 CASDoor 可联邦部署 |

## 7. 测试与验收

- 单用户回归：v0.4 全部 554 测试不倒退（认证依赖在单用户模式恒通过）
- OIDC 模式：mock JWKS/授权码流（httpx MockTransport）；登录→项目访问→角色矩阵→viewer 白名单
- 多用户并发：两用户各自项目互不可见（SQLite/PG 双跑）
- 白名单契约测试：OpenAPI 生成快照比对

## 8. 工作量与节奏（CE v0.5 内）

| 项 | 量级 |
| --- | --- |
| auth 模块（oidc/session/models + 4 端点 + 登录页） | ~1.5 周 |
| 成员/角色/白名单 + API 归属校验 | ~1.5 周 |
| PG storage provider | ~1 周 |
| 测试与回归 | ~1 周 |
| **合计（并入 v0.5）** | **~5 周** |

## 9. 开放决策（待拍板）

| # | 问题 | 倾向 |
| --- | --- | --- |
| D1 | Org 实体进 CE（v0.6）还是留在 ee | v0.5 先 org_id 字段；Org 管理进 CE v0.6（开源用户也有"团队"诉求） |
| D2 | 本地密码登录要不要（无 CASDoor 的多用户） | 不做——多用户=OIDC 前置（简化内核；单机多用户也建议起 CASDoor，docker 一行） |
| D3 | 现有 night-factory/RPA webhook 面的认证方式 | webhook token 保持（机器对机器），与用户会话分离 |

## 10. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0-draft | 2026-09-18 | 初版：三运行模式/CASDoor 对接（OIDC 标准）/角色模型/租户 org_id 贯穿/PG provider/Token Gateway 纯配置对接/兼容矩阵 |
