# CE 本地多用户部署（单容器形态，v0.5+）

> 定位：**本地/主机独立部署的多用户 CE**——一个容器、零外部依赖（Embedded 知识库+本体），
> 内网小团队（≤10 人）自托管。更大的团队/SSO/多租户 = TE（`ee/deploy/te-saas/`）。

## 快速开始

```bash
cd deploy/ce-standalone
cp .env.example .env          # 必改：ADMIN_INVITE_CODE（首个管理员激活码）
docker compose up -d --build  # 首次构建约 3-5 分钟
curl http://localhost:8000/api/v1/health
```

浏览器打开 `http://localhost:8000/api/v1/auth/login`：
1. 首位用户：用户名 + 口令(≥8位) + **激活码**（`.env` 里的 `ADMIN_INVITE_CODE`）→ 激活即 admin
2. admin 在成员管理页生成**邀请码** → 新用户凭码自助激活 → 分配项目角色
3. 角色矩阵：project_owner/fde（读写）/ domain_expert（读+审核）/ client_viewer（只读）

## 环境变量（.env）

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `ADMIN_INVITE_CODE` | ✅ | 首个管理员激活码（admin 就位后可移除） |
| `LOCAL_USERS_ENABLED` | 预置 true | 本地多用户档 |
| `DATA_DIR` | 预置 /data | 数据卷（users/projects/知识库/本体全在这） |
| `LLM_API_KEY` 等 | 可选 | 见仓库 README「LLM 配置」；无 Key=Mock 模式 |

## 数据与备份

- 全部状态在卷 `aifde-ce-data`（`DATA_DIR=/data`）——`docker compose down` 不丢数据
- 备份：`bash ../../deploy/backup.sh`（或直接备份卷目录）

## 边界（诚实声明）

- 本地多用户是**简版凭证**（邀请码+口令哈希，无 SSO/MFA/找回邮件）——需要这些 = TE 目标客户
- Embedded 知识库/本体为进程内实现（SQLite+FTS5）：单机容量；共享域能力与 kb-os 语义对等
  （命名域同构），检索为关键词（非混合向量）
- 请勿暴露公网（无 TLS 终结；需要时前置 nginx，参考 `deploy/docker-compose.full.yml`）
