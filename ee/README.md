# ee/ — 商业版目录（Team & Enterprise Edition）

> 状态：**骨架初建（2026-09-18）** | 上游设计：[10-商业计划](../docs/10-商业计划.md)（Open-Core 双轨）
> 路线文档：[23-开源商业双轨与EE目录规划](../docs/23-开源商业双轨与EE目录规划.md) | 本目录路线：[roadmap-ee.md](roadmap-ee.md)

## 这是什么

本仓库主体为 **Community Edition（CE，MIT 开源）**——单机、单用户、全核心功能免费。
本目录存放 **商业版内容（TE/EE）**：

| 版本 | 定位 | 目标用户 | 商业形态 |
| --- | --- | --- | --- |
| **CE**（仓库主体） | 单机开箱即用，全核心功能 | L0/L1 个人 FDE | MIT 免费 |
| **TE**（Team） | 多用户协作 + 团队经验库 + 集中管控 | L2 团队（3-20人） | 订阅（席位） |
| **EE**（Enterprise） | 多租户 SaaS 化 + 白标 + 审计合规 + 私有化实施 | L3 交付公司/集成商 | 一口价 + 实施 |

## 许可边界（重要）

- 仓库根 `LICENSE`（MIT）**不覆盖本目录**——`ee/` 内全部内容适用 [LICENSE-COMMERCIAL.md](LICENSE-COMMERCIAL.md)
- CE 代码**不得 import `ee/`**（单向依赖：ee → CE，反向禁止）——保证开源版可独立构建
- CE 的扩展点（集成面）均为**契约化公开接口**（14 号知识库契约、20 号本体服务契约、
  Gateway/网关抽象、`src/integrations/` webhook），EE 通过这些面扩展而非改内核

## 目录结构

```
ee/
├── README.md               # 本文件：定位/许可/结构
├── LICENSE-COMMERCIAL.md   # 商业许可（占位条款，正式以合同为准）
├── docs/
│   └── roadmap-ee.md       # TE/EE 版本路线（功能分级→交付顺序）
├── src/                    # 私有扩展代码（TE v1.0 起填充）
│   ├── multi_tenant/       # EE：多租户存储层（PG 行级隔离/租户路由）
│   ├── auth/               # EE：SSO/RBAC/审计
│   ├── branding/           # EE：白标（主题/Logo/文案替换）
│   └── collaboration/      # TE：多用户协作/团队经验库
├── deploy/
│   └── docker-compose.ee.yml   # EE 部署形态（FROM core 镜像 + ee 层）
└── tests/                  # ee 专属测试（CI 独立 job，不进开源 test 路径）
```

## 构建关系

```
ghcr.io/cosmoxone/ai-fde-engine:vx.y.z   ← CE core 镜像（开源 CI 产出）
        │ FROM
        ▼
ee/deploy: EE 镜像 = core + ee 层（独立构建，不开源发布；私有 registry）
```

## 当前状态

骨架阶段——`src/` 各子目录为规划占位，首个可交付见 `docs/roadmap-ee.md`（TE v1.0）。
