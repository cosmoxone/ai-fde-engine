# demo/ —— 演示数据（专门目录，随特性演进）

> 设计原则：
> 1. **幂等**：重复执行不重复造数（按项目名查重跳过）；**随时可重放**（升级后补跑，新特性数据增量入）
> 2. **走 API 不碰库**：演示数据 = 真实用户路径（也是一层冒烟测试）
> 3. **双形态**：`--mode ce`（本地多用户，8000）/ `--mode te`（SaaS CASDoor，8014+17100）
> 4. **演进纪律**：每个里程碑落地后在本文件登记新增场景（当前覆盖 v0.5：M0-M3 全量）

## 用法

```bash
# CE 本地多用户（deploy/ce-standalone 栈 @8000；首次需 .env 激活码已在种子内默认）
python3 demo/seed.py --mode ce  --base http://localhost:8000

# TE SaaS（ee/deploy/te-saas 栈 @8014；CASDoor@17100）
python3 demo/seed.py --mode te  --base http://localhost:8014
```

## 场景清单（随版本演进）

| 版本 | 场景 | 落点 |
| --- | --- | --- |
| v0.4 | 演示项目「智驱制造-设备预测性维护」（3 文档+研究记录） | /projects |
| v0.5-M0 | admin 激活 + 第二成员（alice）+ 项目隔离对照 | /auth/* |
| v0.5-M2 | alice 项目角色 fde；mallory 无角色（只读演示位） | /api/te/*, /auth/users |
| v0.5-M3 | 文档发布到共享域 + 1 条 pending 经验贡献（演示审核队列）+ 共享检索命中 | /api/te/kb/*, contributions |
