# AI-FDE Engine 公开评测基准

> 生成：2026-09-07 22:24 ｜ 模式：`mock-baseline`

## 1. 内置行业种子集 × 评测器基线

| 行业 | 用例数 | 准确率 | 幻觉率 | 召回率 | 格式合规 | 质量门禁 |
| --- | --- | --- | --- | --- | --- | --- |
| 金融业（finance） | 3 | 67% | 5.0% | 63% | 100% | ❌ |
| 政务（government） | 3 | 67% | 5.0% | 63% | 100% | ❌ |
| 制造业（manufacturing） | 3 | 67% | 5.0% | 63% | 100% | ❌ |

## 2. 需求基线黄金集（人工要点标注）

- 样本总数：20 条
  - 金融业：6 条
  - 政务：6 条
  - 制造业：8 条

## 3. 复现方式

```bash
# 本基线（mock，零依赖可复现）
python -m src.evaluation.benchmark_report

# 真实 LLM 黄金集命中率（配置 DeepSeek/Qwen Key 后）
python -m src.evaluation.golden
```

> mock-baseline：评测器在种子集上的可复现基线（无LLM依赖）

---

*方法论：验证前置——所有质量结论必须可复现（docs/01 §设计原则）*