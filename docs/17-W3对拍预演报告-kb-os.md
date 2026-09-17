# W3 对拍预演报告(kb-os 单侧真机预演)

> 版本:**v1.0** | 日期:2026-09-17 19:40 | 执行:kb-os(不等联调窗口,提前自验)
> 对象:贵方 `tests/contract/` 全集(`KB_PROFILE=kbos`)× kb-os 联调实例(8011)× WeKnora 真机引擎
> 结论:**12/13 通过**;唯一失败项 `test_stats_invariant_and_ready` 定位为**贵方用例的跨测试隔离缺陷**(证据见 §2,附一行修复建议);另附 7 项引擎真机行为实证(§3,已在 kb-os 侧全部适配)。

---

## 1. 执行结果

```
KB_PROFILE=kbos KB_BASE_URL=http://<kbgw-aifde>:8011 KB_TOKEN=kbos-aifde-w3-… \
  pytest tests/contract -m "p0 or p1"
```

| 场景 | 结果 | 备注 |
|---|---|---|
| test_health / unauthorized / invalid_request / over_limit | ✅×4 | 含 G1 HTTP 状态对齐与 G4 部署前提的真机验证 |
| test_ingest_documents_and_idempotent | ✅ | 真机:file 通道自动解析,title 幂等,deduped 计数 |
| test_search_hit_with_traceability | ✅ | **溯源五字段真机通过**(合同级诉求) |
| test_search_empty_result | ✅ | 需网关词面重叠门(§3-⑥) |
| test_curate / confirm_idempotent / entry_not_found | ✅×3 | FAQ 全生命周期真机跑通 |
| test_confirm_flow_and_search_curated | ✅ | confirm 即时入池 + curated 可检索(账本精确腿,§3-⑦) |
| test_reject_flow_invisible | ✅ | rejected 双保险不可见(引擎 disabled + 精确腿仅 confirmed) |
| **test_stats_invariant_and_ready** | ❌ | **贵方用例缺陷,见 §2** |

## 2. 唯一失败项:跨测试在途索引污染 delta 断言(建议贵方修一行)

**现象**:全套连跑时失败,**单跑通过**(已复现验证:清库后 `pytest -k stats_invariant` 单独执行 PASSED)。

**机理**:贵方 `before = kb.stats()` 快照时,前一用例(`test_ingest`)推的 3 篇文档**仍在解析**(parsing=3,documents=1);本用例推 2 篇后 `wait_ready` 收敛,3 篇在途文档完成 → `after.documents=6 ≠ before.documents+2=3`。Embedded 参考实现是同步索引(恒 parsing=0)永不触发;任何**异步索引**实现(v1.2 §1 明确允许:"最终一致")都会中招。

**修复建议**(`test_kb_contract.py::test_stats_invariant_and_ready`,一行):

```python
- before = kb.stats()
+ before = wait(kb)          # 快照前先收敛在途索引(异步实现必需;同步实现首次轮询即过)
```

## 3. 引擎真机行为实证(7 项,kb-os 已全部适配,Mock 已同步对齐)

| # | 发现 | kb-os 适配 |
|---|---|---|
| ① | `/knowledge/manual`(JSON)通道落库后 **parse_status=draft 永不解析**(需 UI 激活);`/knowledge/file`(multipart)自动进解析管线(processing→finalizing→completed,~6s) | `upload_manual` 改走 file 通道(C3 wiki_reflux 同路径) |
| ② | FAQ 条目**必须落 type=faq 库**(document 库报"仅 FAQ 知识库支持该操作") | 项目双库:文档库 `{prefix}{pid}` + FAQ 库 `{prefix}faq-{pid}` |
| ③ | FAQ 创建是**批量异步导入**:POST 载荷 `{mode:"append", entries:[{standard_question, answers[], similar_questions[], is_enabled}]}`(**字段名 standard_question/answers,非 question/answer**),返回 task_id 需轮询 `/faq/import/progress/{task}`;**append 无视 is_enabled:false**(落库即 enabled) | append→轮询→按 pattern 回查整数 id→PUT 全量停用(毫秒级窗口);confirm=PUT 全量+enabled |
| ④ | FAQ 列表 **is_enabled 过滤参数被引擎忽略** | 客户端分页计数(faq_totals) |
| ⑤ | **append 按 standard_question 合并**:同 pattern 不同 origin 的条目共享一条引擎行 | 生命周期仍按 origin+pattern 独立(契约语义);confirmed 兄弟存在时新建 pending 不打回 disabled(共享行保活) |
| ⑥ | hybrid-search **恒回 top_k 凑数行,原始分无稳定相关性语义**(垃圾查询"距离"0.011 竟低于真实查询 0.016;FAQ 库又是相似度谱 0.09/0.16/0.77/0.91)→ 任何绝对阈值不可用 | **词面重叠门**:查询与命中内容共享 CJK≥2字/alnum≥4段才放行(`KBGW_WK_MIN_OVERLAP=2`,0=关闭);FAQ 库叠加相似度下限 0.30。代价:纯改写零词面重叠的语义召回被牺牲(标定债务) |
| ⑦ | confirmed FAQ 经 hybrid-search 命中 `chunk_type=faq` 全字段 ✓;但**裸标记查询的 FAQ 向量分(0.09)低于拼接垃圾串(0.16)** | 账本**精确腿**:confirmed 条目 pattern/similar 与查询子串匹配(FTS 语义)置顶,与引擎向量腿互补 |

## 4. 联调物料(窗口开启即用)

- **实例**:`http://<kbgw-host>:8011`(容器 `kbos-gateway-aifde`,compose:`docker-compose.aifde.yml`;`KBGW_AUTH_DEV=false` + 项目 scoped key,能力域 read+write)
- **key**:`kbos-aifde-w3-…`(明文在 kb-os 侧 `/tmp/aifde_w3_key.txt`,发放走安全渠道;sha256 已入 `.env`)
- **运行**:见 §1 命令;`KB_INDEX_TIMEOUT` 默认 300s 足够(实测单篇解析 ~6s)
- 建议贵方先合入 §2 的一行修复,再跑全套(预期 13/13)

## 5. kb-os 侧同步变更(本轮预演产出,91/91 单测)

引擎适配层重写(file 通道/FAQ 双库/批量导入/分页计数/重叠门/精确腿)+ stats 项目双库口径 + Mock 全面向真机形态对齐 + 2 个新回归(pattern 共享行保活/curated 精确腿)。详见 kb-os `Phase.md` P3/W2.7。
