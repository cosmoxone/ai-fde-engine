# W3 对拍结果回执（ai-fde-engine）

> 版本：**v1.0** | 日期：2026-09-17 20:15 | 状态：**W3 对拍通过（13/13）**
> 回复：[17-W3对拍预演报告-kb-os](17-W3对拍预演报告-kb-os.md)（贵方单侧预演 12/13 + 一行修复建议）
> 环境：kb-os 联调实例（本机 8011，容器 `kbos-gateway-aifde`）× 项目 scoped key（`kb:read+kb:write`，已收到）

---

## 1. §2 一行修复：已合入，双实现零回归

采纳贵方建议，`tests/contract/test_kb_contract.py::test_stats_invariant_and_ready` 已改：

```python
- before = kb.stats()
+ before = wait(kb)  # 快照前先收敛在途索引(异步实现必需;同步实现首次轮询即过,零开销)
```

确认贵方机理分析正确：Embedded（同步索引，恒 parsing=0）永不触发；该缺陷对任何异步实现均存在，属我方用例的跨测试隔离问题，非契约偏差。**契约 v1.2 §1"最终一致"与 §3.6 就绪判据无需任何修改。**

合修复后本地双实现回归：

- spec14 参考服务（Embedded）：12 passed + 1 skipped（unauthorized 无 token 条件跳过）——修复对同步实现零开销
- kbos 真机：13/13（见下）

## 2. 真机对拍：13/13 通过（2026-09-17 20:10）

```
KB_PROFILE=kbos KB_BASE_URL=http://127.0.0.1:8011 KB_TOKEN=<scoped key> \
  pytest tests/contract -m "p0 or p1"
→ 13 passed in 40.47s
```

| 场景组 | 结果 |
|---|---|
| health / unauthorized(401) / invalid_request / over_limit | ✅×4（G1 HTTP 状态化 + G4 部署前提真机复验） |
| ingest 幂等（title 等价）/ stats 三元不变量 + 就绪（**修复后**） | ✅×2 |
| 检索溯源五字段 / 空结果（词面重叠门） | ✅×2 |
| curate→pending / confirm→curated 可检索 / confirm 幂等 / reject 不可见 / entry_not_found | ✅×5 |

## 3. 环境确认（两点，均无需处理）

1. **非干净库**：实例 `documents=1`（贵方预演残留）。我方修复后 delta 断言为**相对基线**（`before=wait(kb)` 先收敛再快照），对残留脏库免疫，实测通过——16 号"干净库"前提由该修复消解，后续联调无需清库。
2. **stats 限流**：全套连跑（13 用例含 wait_ready 轮询，2s 间隔）未触发 429；贵方 W3 前承诺的 stats 轻量化如有排期照常即可，当前规模无压力。

## 4. 结论

- **W3 验收达成**：roadmap 协作项验收条件"Remote 模式端到端通过（`KNOWLEDGE_SERVICE_URL` 切 kb-os 实例实测）"满足；契约 v1.2 双实现（Embedded 参考实现 × kb-os 真机）同一组场景对拍一致。
- 贵方 §3 七项引擎真机行为适配（file 通道/FAQ 双库/批量导入/分页计数/重叠门/精确腿）经对拍间接验证有效，无新增发现。
- 后续消费侧工作（v0.4-b 本体抽取 / v0.4-c research RAG 化）在我方仓库推进，按需再来打扰。

---

*对拍命令与前提已同步至我方 `tests/contract/README.md`；本轮我方侧变更（一行修复 + 文档）见 CHANGELOG `[Unreleased]`。*
