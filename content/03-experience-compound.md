# FDE 的经验复利：从项目记忆到跨项目经验库

> AI-FDE Engine 方法论系列 · 第 3 篇 | 2026-09 | 附 10 分钟复现步骤

## FDE 职业生涯的最大浪费

做交付三年，你一定经历过：

- 第二次遇到"客户数据在 Excel 里且格式混乱"的场景，解决方案要从头再想一遍
- 换了公司/团队，前两年攒的所有项目经验清零
- 新人问"这类客户怎么谈验收"，你脑子里有答案，但它散落在 20 个项目的聊天记录里

**经验没有复利，是 FDE 和程序员最大的区别**。代码可以复用，但"这个行业的客户在意什么、哪类需求容易扯皮、什么方案在什么场景翻过车"——这些最有价值的知识，每次项目结束就蒸发一次。

项目复盘？大多数公司也有，但复盘文档写完就进档案室，因为**没人会在新项目开始时翻 20 份旧 PDF**。

## 三层递进：记忆 → 复盘 → 经验库

我们在 AI-FDE Engine 里把"经验资产化"拆成三层：

### 第 1 层：项目记忆（自动，零成本）

项目进行中，所有关键事件自动入库：需求基线确认、方案决策、badcase 归因、验收标准。Agent 执行任务时自动检索注入——"这个客户上次为什么否掉了类似方案？"

### 第 2 层：项目复盘（一键，10 分钟）

项目结束点一下，自动聚合生成复盘报告：

```
执行概况（任务/迭代/badcase 处理统计）
质量与 Badcase 归因分布（哪类错误占 80%？下次预防什么？）
评审协同记录（哪些决策点人工介入了？）
经验沉淀清单 ←最有价值：验收标准模板/Benchmark 种子/行业踩坑
```

### 第 3 层：跨项目经验库（检索，10 秒）

新项目遇到问题，一句话检索所有历史项目：

> "特采放行以前怎么处理的？" → 命中制造业项目 A 的规则口径 + 项目 B 的拒答话术 + 相关 badcase 归因

**这就是复利**：第 N 个项目的起点 = 前 N-1 个项目的全部沉淀。

## 10 分钟复现

```bash
# 1. 启动，创建两个不同项目（模拟两个交付项目）
docker run -d --name aifde -p 8000:8000 -v aifde-data:/app/data \
  ghcr.io/cosmoxone/ai-fde-engine:latest

curl -X POST localhost:8000/api/v1/projects -H "Content-Type: application/json" \
  -d '{"name":"华宇质检项目","industry":"制造业"}'
curl -X POST localhost:8000/api/v1/projects -H "Content-Type: application/json" \
  -d '{"name":"某金融客服项目","industry":"金融"}'

# 2. 在项目A跑一次调研（记忆自动沉淀：含特采场景的业务知识）
curl -X POST localhost:8000/api/v1/projects/<A的ID>/research/run \
  -H "Content-Type: application/json" -d '{"client_requirements":"质检知识库，关注特采流程"}'

# 3. 项目B开工时，检索跨项目经验（第3层）
curl "localhost:8000/api/v1/memory/global/search?query=特采"

# 4. 给项目A生成复盘（第2层），看"经验沉淀清单"章节
curl localhost:8000/api/v1/projects/<A的ID>/retrospective

# 5. 或直接在 Dashboard 体验：localhost:8000/dashboard → 🧠经验库
```

第 3 步的返回会标注每条经验的**来源项目**——你知道该去问谁、翻哪个项目的文档深挖。

## 经验库 + 行业模板 = 团队资产的飞轮

单机经验库解决"个人复利"。再进一步（开源版已预留接口）：

```
个人经验库（CE，免费）
   ↓ 沉淀出高质量行业模板（验收标准/Benchmark种子/踩坑清单）
团队经验库（TE，商业版规划中）← 组织记忆：人员流动不带走
   ↓ 团队模板沉淀
行业模板市场（社区贡献，校验器保证质量红线）
```

你的行业经验值得变成模板包被全世界 FDE 复用——[贡献指南](../docs/12-模板贡献指南.md)，复制一份 JSON 就能开始。

## 一句话总结

> FDE 的护城河不是做过多少项目，而是**下一个项目能调用多少前项目的沉淀**。记忆自动化、复盘一键化、检索十秒化——复利从此开始。

---

**上篇**：[质量门禁与夜间迭代：让 AI 系统上线后不再雪崩](02-quality-gate-and-nightly-iteration.md)

*系列完。方法论均已工具化于 [AI-FDE Engine](https://github.com/cosmoxone/ai-fde-engine)（MIT 开源）——流程可跑通、质量可验证、经验可复用。*
