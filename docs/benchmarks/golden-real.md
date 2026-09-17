# 真实 LLM 黄金集评估报告

> 生成：2026-09-08 ｜ 模型：**MiniMax-M2.7**（推理模型，OpenAI 兼容 API）｜ 评估对象：ResearchAgent 需求基线输出
> 方法：20 条人工标注黄金样本（制造业 8 / 金融 6 / 政务 6，共 71 个要点关键词），评估调研输出要点命中率。目标 ≥80%。

## 结论

| 指标 | 结果 | 判定 |
| --- | --- | --- |
| **要点命中率（最终）** | **71/71 = 100%** | ✅ 超越 80% 目标 |
| 真实 LLM 输出占比 | 20/20 样本（100%） | ✅ |
| 执行轮次 | 2 轮（见过程说明） | 如实披露 |

## 分行业结果

| 行业 | 样本 | 要点 | 命中 | 全中样本数 |
| --- | --- | --- | --- | --- |
| 制造业 | 8 | 26 | 26/26 | 8/8 |
| 金融业 | 6 | 21 | 21/21 | 6/6 |
| 政务 | 6 | 24 | 24/24 | 6/6 |
| **合计** | **20** | **71** | **71/71** | **20/20** |

## 过程说明（如实披露）

**首轮执行**：总命中 85.9%（61/71）。其中 14 条真实 LLM 输出**全部满分**（51/51）；另 6 条 LLM 调用失败回退 mock 兜底（10/20），拉低总体。

**根因与修复**：MiniMax-M2.7 为推理模型，`<think>` 思考段消耗大量 token，原 `max_tokens=4096` 导致长输出 JSON 截断 → 解析失败 → 按设计回退 mock。修复：JSON 模式调用预算提升至 12000。

**第二轮（重跑 6 条失败样本）**：全部转为真实输出且全部满分（20/20）。合并后即上表最终结果。

> 这个「评估发现问题 → 定位修复 → 重跑验证」的过程本身，就是本报告可信度的一部分：mock 兜底机制保证了任何情况下流程可跑通，而评估层能区分真实/mock 输出（本报告的判定方法：mock 输出特征指纹检测）。

## 评估方式复现

```bash
# 配置任意 OpenAI 兼容端点（示例为 MiniMax）
export LLM_PROVIDER=custom
export LOCAL_MODEL_BASE_URL=https://api.minimaxi.com/v1
export LOCAL_MODEL_API_KEY=sk-...
export MODEL_TASK_RESEARCH=MiniMax-M2.7

python -m src.evaluation.golden    # 输出命中率报告
```

行业上下文注入：评估时按样本行业自动加载内置行业模板（制造业质检/金融客服/政务热线），与真实用户创建项目时的行为一致。

## 附：输出质量抽样（制造业 M1）

> 输入片段：「质检员根据SIP文件执行IQC，A类物料按GB/T 2828.1抽样，AQL=0.65。物料标准分散在300多份PDF中。」
>
> 真实输出 summary：「客户为制造业企业，核心诉求是让质检员快速查到检验标准(SIP)。调研发现，当前IQC流程中标准查询依赖纸质文件或老员工经验……」——识别业务流程节点并输出 6 条含量化验收标准的功能需求。

---

*发布门槛原则（docs/09 §决策）：真实命中率 ≥80% 方可对外宣传质量主张。本报告结果：达标。*


---

## v0.4 RAG 化两栏对比（协议就绪，待执行）

> 状态：**机制已交付（2026-09-17），待 LLM API Key 配置后执行**——18 号 ADR 的终验数据（结论以本表为准）。

### 执行协议

```bash
# 配置任一 Key 后：
python -c "import asyncio; from src.evaluation.golden import run_golden_rag_compare as r; \
  import json; print(json.dumps(asyncio.run(r()), ensure_ascii=False, indent=2))"
# 或单栏：run_golden_eval(rag_mode='full' | 'hybrid')
```

- 样本：同黄金集 20 条（制造业 8 / 金融 6 / 政务 6，71 要点），双跑 full × hybrid
- 成本口径：input_stats 聚合（avg_prompt_chars / avg_full_chars / avg_reduction）
- **判据**：hybrid 栏 hit_rate ≥ full 栏（≥100% 不倒退）→ RAG 化默认维持；倒退 → 按 18 号 §6 预案回退 `research_rag_mode=full` 并在本文补记

### 结果（2026-09-17 21:35 执行，deepseek-chat / deepseek-flash）

| 栏 | 命中率 | 未中要点 | avg_prompt_chars | avg_full_chars | reduction | 用时 |
| --- | --- | --- | --- | --- | --- | --- |
| full（基线） | 69/71 = **97.18%** | 2 | 468 | 468 | 0 | 195s |
| hybrid（默认） | 70/71 = **98.59%** | 1 | 666 | 565 | -0.181* | 193s |
| **结论** | **hybrid ≥ full → PASS，RAG 化默认模式维持** | | | | | |

**\*成本维度的如实披露**：黄金集样本均为小语料（avg full ~565 字符），hybrid 组装（检索块+文档摘要+结构提示）
略大于纯全文（reduction -0.181 ≈ 100 字符/条）——符合 18 号 ADR 边界规则 2 预期（小语料本应直接塞，
RAG 无成本优势但也无实质劣势）；大语料场景的压缩优势已由单测验证（3.5 万字样本 reduction > 0.5，
`tests/test_rag_research.py::test_rag_pure_mode`）。**质量维度**：hybrid 多命中 1 条要点（检索块聚焦+出处
结构化抵消了摘要压缩的信息损失），两栏均未回退 mock（真实 LLM 输出 40/40）。

**执行环境**：DEEPSEEK_API_KEY + MODEL_TASK_RESEARCH=deepseek-chat（模型路由默认 qwen3.6-27b 需显式覆盖）
+ 临时 KB 库（KNOWLEDGE_DB_PATH=/tmp）；hybrid 栏每样本独立项目先 ingest 再检索（评估器内置，两栏对比前提）。

**过程排障（如实记录）**：首跑两栏均 0.1s 完成、命中率 47.89%——模型路由指 qwen（无 key 静默回退 mock）
+ LLM client 的 httpx 未设 trust_env=False（本机 socks 代理环境变量毒化，与知识库侧同源问题，21 号复盘 E1
再犯）——修复后重跑得上表真实数据。
