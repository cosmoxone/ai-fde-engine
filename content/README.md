# 内容专栏：AI 交付方法论

> 源自真实交付实践，每篇附 15 分钟可复现步骤（Mock 模式零 API Key）。
> 转载请注明出处：[AI-FDE Engine](https://github.com/cosmoxone/ai-fde-engine)（MIT 开源）

| # | 文章 | 核心观点 |
| --- | --- | --- |
| 1 | [验证前置：为什么 AI 项目交付必须先定验收标准](01-verification-first.md) | AI 项目的质量是开工前定义出来的——Benchmark 先行，返工归零 |
| 2 | [质量门禁与夜间迭代：让 AI 系统上线后不再雪崩](02-quality-gate-and-nightly-iteration.md) | 上线后质量靠门禁拦 + 迭代攒；AI 修能修的，建议修不了的 |
| 3 | [FDE 的经验复利：从项目记忆到跨项目经验库](03-experience-compound.md) | FDE 的护城河是下一项目能调用多少前项目的沉淀 |

## 为什么写这个系列

市面上的 AI 内容集中在"怎么搭应用"（RAG/Agent/Prompt），但 AI 落地的失败大多发生在**交付阶段**：需求扯皮、验收模糊、上线即巅峰、坏例雪崩、经验蒸发。

这四件事正是 FDE（Forward Deployed Engineer）的日常，也是 AI-FDE Engine 把交付方法论工具化的四个模块。我们把这些方法论连同可复现步骤一起开源——**观点可以争论，流程可以直接跑**。

## 内容计划

- ✅ 第 1 批：验证前置 / 质量门禁与夜间迭代 / 经验复利（本系列）
- ⏳ 第 2 批（征集中，欢迎 [Discussion](https://github.com/cosmoxone/ai-fde-engine/discussions) 提问）：
  - 三方案交叉校验：产品/技术/验证方案的一致性怎么守
  - 黄金集：20 条样本如何评估 LLM 输出质量（附 `python -m src.evaluation.golden`）
  - 行业模板：制造业/金融/政务三包的设计取舍
