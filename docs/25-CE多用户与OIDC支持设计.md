# CE 认证抽象与本地用户管理（v0.5 设计）

> 版本：**v1.1-draft** | 日期：2026-09-18 | 状态：设计修订稿（v1.0 的"OIDC/多租户下沉 CE"方案已按拍板撤销）
> **拍板修订（2026-09-18）**：**多租户是 TE 特性，不进 CE**。CE 默认**本地用户管理**（简版、开箱即用）；
> **TE 完全替换认证用户管理模块**（CASDoor OIDC + Org 多租户 = ee 层实现，对接 CE 的替换点）。
> 关联：[23 号](23-开源商业双轨与EE目录规划.md) / [26 号](26-nightfactory与RPA集成设计.md)（nf/RPA 双版本特性）
> 兼容红线：**不启用本地多用户 = 现单用户模式，零依赖不变**（CI/Mock/既有用户无感）

---

## 1. 分层原则（修订后）

```
CE v0.5（本设计）  ：AuthProvider 可替换抽象 + LocalAuthProvider 默认实现（本地用户管理）
                     ——开源用户获得"简版多用户"（自托管团队可用），无 OIDC/无租户概念
TE（ee/，整块替换） ：CasdoorAuthProvider + Org 多租户（org 行级贯穿）+ 订阅计量
                     ——实现同一 AuthProvider 接口，替换 CE 默认实现，内核其余零感知
```

**与 v1.0 草案的差异**：OIDC 客户端、CASDoor 对接、Org/org_id 贯穿、PG 多租户 provider **全部移出 CE**
→ 归 TE（ee）。CE 侧只留"可替换的认证接口 + 本地默认实现"——更薄、更符合 open-core（CE 无 SaaS 假设）。

## 2. AuthProvider 抽象（CE 的替换点）

```python
# src/auth/provider.py（新增，~60 行）
class AuthProvider(Protocol):
    def current_user(self, request: Request) -> User: ...        # FastAPI 依赖（全部端点注入）
    def verify_project_access(self, user: User, project_id: str, action: str) -> bool: ...
    def login_routes(self) -> list[APIRoute]: ...                 # 可为空（无登录页模式）
```

- **User**（CE 语义，无租户字段）：`id / display_name / platform_role (admin|member) / project_roles: {project_id: role}`
- 装配：`AUTH_PROVIDER=local`（默认）｜**替换点**：entry point 注册（ee 层注册 `casdoor` provider，CE 零代码感知）
- 全部既有端点经 `Depends(get_current_user)`；**LocalAuthProvider 单用户模式返回内置 `local-admin`，行为与 v0.4 逐字节一致**

## 3. LocalAuthProvider（CE 默认：本地用户管理）

### 3.1 两档（同 provider 内配置切换）

| 档 | 触发 | 行为 |
| --- | --- | --- |
| **单用户（默认）** | `LOCAL_USERS_ENABLED` 未设/空 | 内置 `local-admin`；无登录页、无用户表——v0.4 全兼容 |
| **本地多用户** | `LOCAL_USERS_ENABLED=true` | User/ProjectMember 两张 SQLite 表 + **简单凭证**（见 3.2）+ Dashboard 登录页 + 成员管理 |

### 3.2 凭证设计（刻意简单——"本地用户管理"不做成认证系统）

- 首个管理员：启动打印/配置 `ADMIN_INVITE_CODE`，首次登录激活
- 后续用户：管理员生成**邀请码**（一次性）→ 用户激活时自设口令（本地 bcrypt 哈希，仅本地 SQLite）
- 会话：签名 cookie（itsdangerous，既有依赖面）；无 OAuth/JWT/MFA——**需要这些的团队 = TE 目标客户**（引导路径明确）
- 明确边界：CE 本地多用户面向"小团队自托管"（≤10 人、内网/可信环境）；不做密码找回邮件流/审计/SSO（写进文档边界）

### 3.3 角色模型（CE 语义，与 TE 对齐但更简）

| 层 | 角色 | 权限 |
| --- | --- | --- |
| 平台 | admin / member | 用户管理+全局配置 / 常规 |
| 项目 | project_owner / fde / domain_expert / client_viewer | 同 TE 语义（审核队列/只读白名单复用同一矩阵——见 §5） |

client_viewer 只读白名单：由 CE OpenAPI 端点清单自动生成（GET 集+验收标记），契约测试守护。

## 4. data 层（CE 侧最小改动）

- 新增表（SQLite，`LOCAL_USERS_ENABLED` 才建）：`local_users`（id/name/pass_hash/platform_role/status）、
  `project_members`（project_id/user_id/role）——**无 org 字段**（租户是 TE 特性，ee 的 PG 扩展自行加列/映射）
- 项目归属：`projects.owner_user_id`（可空=单用户模式全部可见，兼容存量数据）
- PG provider：**移出本设计**（TE SaaS 需要，ee 层按 StorageProvider 抽象扩展——CE 保持 SQLite/memory 两实现）

## 5. TE 替换路径（ee 层概要，详设见 ee/docs/design-te-v1.md v1.2）

| CE 提供 | TE 替换为 |
| --- | --- |
| `AuthProvider` 接口 + `local` 默认实现 | **`CasdoorAuthProvider`**（OIDC 授权码流/JWT 会话/CASDoor 用户目录同步） |
| `User`（无租户） | `TeUser`（扩展 org_id/订阅属性；org 行级过滤在 ee PG 扩展注入） |
| 本地邀请码流 | CASDoor 组织/邀请（admin API） |
| client_viewer 白名单 | 同一矩阵（ee 网关层执行，CE 端点清单仍自动生成） |

## 6. 兼容与迁移

| 场景 | 路径 |
| --- | --- |
| v0.4 单机 → v0.5 | 零操作（默认单用户；新表不建） |
| 单机 → 本地多用户 | 设 `LOCAL_USERS_ENABLED=true` → 激活 admin → 邀请成员（数据原地，项目归属补 owner） |
| 本地多用户 → TE | CE 数据导出 + CASDoor 建组织 → ee 导入（用户映射 external_sub）——**认证体系整体替换是设计预期** |
| TE SaaS → EE | 同 TE（专属部署，CASDoor 可联邦） |

## 7. 测试与验收

- 单用户回归：554 测试零变化（依赖恒返回 local-admin）
- 本地多用户：激活/邀请/登录/角色矩阵/白名单/两用户项目互不可见
- 替换点契约：AuthProvider 接口快照 + mock 替换 provider 全端点通（保证 ee 可替换性）

## 8. 工作量（v1.1 修订后，显著缩小）

| 项 | 量级 |
| --- | --- |
| auth 抽象 + LocalAuthProvider（两档）+ 4 端点 + 登录页 | ~1.5 周 |
| ProjectMember/角色/白名单 + API 归属校验 | ~1 周 |
| 测试与回归 | ~0.5 周 |
| **合计（CE v0.5 内）** | **~3 周**（v1.0 方案 5 周 → 移除 OIDC/PG/租户后减 2 周） |

## 9. 已决事项（本轮拍板落档）

| # | 决策 | 结论 |
| --- | --- | --- |
| D1 | 多租户归属 | **TE 特性，不进 CE**——CE 只留 AuthProvider 替换点；Org/org 贯穿在 ee |
| D2 | 认证形态 | CE=本地用户管理（简版：默认单用户/可选本地多用户邀请码）；**TE 整块替换为 CASDoor** |
| D3 | nf/RPA 接口 | 独立设计成文：[26 号](26-nightfactory与RPA集成设计.md)——CE 精简面冻结（文件级/webhook+机器 token），TE 完整面（回调/多租户/计量）在 ee 编排 |

## 10. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0-draft | 2026-09-18 | 初版（OIDC/多租户下沉 CE 方案）——**已被拍板撤销** |
| v1.1-draft | 2026-09-18 | **修订**：多租户/OIDC/PG 移出 CE → TE；CE=AuthProvider 抽象+LocalAuthProvider（单用户默认/本地多用户可选）；TE=CasdoorAuthProvider 整块替换；工作量 5→3 周；D1-D3 拍板落档 |
