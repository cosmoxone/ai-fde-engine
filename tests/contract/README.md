# 知识库契约测试(tests/contract)

对任意知识库实现跑**同一组契约场景**(W3 双实现对拍用例集)。

- 契约源:`docs/14-知识库接口规格.md` **v1.2**
- kb-os 原生 API 映射:`kb-os/docs/09-ai-fde对接方案.md` §4(字段映射 §4.4、错误码 §4.1.1)
- 共识依据:09 方案 v1.1 §七 × `docs/15-对接方案评审回复.md`

## 架构:场景内核 + 双断言适配

```
tests/contract/
├── core.py                 场景内核:归一化类型 + KBClient 抽象 + 物料工厂(唯一标记)
├── adapters_spec14.py      spec14 适配:平铺契约(/ingest /search /curate…)
├── adapters_kbos.py        kbos 适配:Envelope + /api/v1/knowledge/*(error_key 优先,数字码映射兜底)
├── conftest.py             fixture:KB_PROFILE 选适配、最终一致轮询(wait_ready)
└── test_kb_contract.py     场景测试(p0/p1 标记,与实现无关)
```

同一场景在两个适配下断言语义一致;差异点(如超批量错误码)收敛在 `Expectations`。

## 运行

```bash
# spec14 形态(Embedded 参考实现 / spec 兼容第三方)
KB_PROFILE=spec14 KB_BASE_URL=http://127.0.0.1:9000 pytest tests/contract -m p0

# kb-os 原生形态(联调实例 + 项目 scoped key)
KB_PROFILE=kbos KB_BASE_URL=http://kbgw:8010 KB_TOKEN=kbos-xxx pytest tests/contract -m p0

# P1 交互闭环叠加
KB_PROFILE=kbos KB_BASE_URL=http://kbgw:8010 KB_TOKEN=kbos-xxx pytest tests/contract -m "p0 or p1"

# 解析慢的环境调大最终一致等待
KB_INDEX_TIMEOUT=600 pytest tests/contract -m p0
```

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `KB_PROFILE` | `spec14` | 断言适配(`spec14` / `kbos`) |
| `KB_BASE_URL` | `http://127.0.0.1:9000` | 被测服务地址 |
| `KB_TOKEN` | (空) | scoped key;设置后启用鉴权负例 |
| `KB_INDEX_TIMEOUT` | `300` | `parsing==0` 等待上限(秒) |

## 场景清单

**P0(联调最小集)**:

| 场景 | 断言要点 |
| --- | --- |
| `test_health` | `/health` 返回 `status ∈ {ok, degraded}` |
| `test_ingest_documents_and_idempotent` | accepted/deduped 计数;同 doc_id 重推全去重 |
| `test_stats_invariant_and_ready` | 三元不变量核账(documents+parsing+parse_failed=累计接受);`parsing==0` 就绪 |
| `test_search_hit_with_traceability` | 就绪后按唯一标记命中;**溯源五字段必填** |
| `test_search_empty_result` | 空结果 `[]` 不报错 |
| `test_error_invalid_request` | 400 `invalid_request` |
| `test_error_over_limit_batch` | 单批 >50 拒绝(spec14: `payload_too_large`;kbos: `invalid_request`) |
| `test_unauthorized_without_token` | (配置 KB_TOKEN 时)401 `unauthorized` |

**P1(交互闭环)**:

| 场景 | 断言要点 |
| --- | --- |
| `test_curate_pending_and_idempotent` | 提交即 pending、队列可见;origin+question_pattern 幂等 |
| `test_confirm_flow_and_search_curated` | confirm 终稿 → 检索命中 `entry_type: curated` |
| `test_reject_flow_invisible` | rejected 保留记录但不出现在检索结果 |
| `test_confirm_idempotent` | 重复 confirm 返回当前终态 |
| `test_entry_not_found` | 404 `not_found`(v1.2 泛化码) |

## W3 对拍怎么跑

> **✅ 已完成（2026-09-17）：真机对拍 13/13**（kb-os 单侧预演 12/13 → 我方合入 stats 用例一行修复 → 真机复跑全绿）。详见 [docs/17-W3对拍预演报告-kb-os.md](../docs/17-W3对拍预演报告-kb-os.md) × [docs/19-W3对拍结果回执-ai-fde.md](../docs/19-W3对拍结果回执-ai-fde.md)。修复同时消解下方"干净库"前提（delta 断言改为相对基线，脏库免疫）。

1. kb-os 侧:`KB_PROFILE=kbos` 指向联调实例(他们可直接当验收用例);
2. 我方侧:`KB_PROFILE=spec14` 指向 Embedded 参考实现(v0.4-a 交付后,起参考服务);
3. 双方各自全绿 → 同 marker 场景输出可比对(检索命中与溯源结构一致)。

> **✅ 2026-09-17 21:40 实测记录（已闭环）**：kb-os 实例切 **:8010**（KB_TOKEN 不变）时曾现鉴权部署
> 回归（无 token 200 ≠ 401，G4 前提未启用；8011 对照正常，其余 12 用例全过）——kb-os 当晚修复
> （`KBGW_AUTH_DEV=false`+`KBGW_API_KEYS`）后我方复验：**四探针符合**（无 key 401 / 错 key 401 /
> 对 key 200 / health 放行）+ **契约套件 13/13（48.48s）**。教训：外部依赖"透明变更"（仅换地址）
> 也必须重跑鉴权负例——详见 [22 号复盘](../../docs/22-过程复盘-v0.4发布收口与黄金集终验.md)。

**kb-os 实例联调前提**(其 16 号回执 §四,kb-os 侧职责):
- 部署须 `KBGW_AUTH_DEV=false` + 配置 `KBGW_API_KEYS`(否则 dev 模式无凭证放行,鉴权负例必挂);
- `parse_failed` 已知简化:失败文档重推同 title 会被幂等去重、计数不自动减少——联调用**干净库**(其 doc_id 幂等升级在途);
- 我方 `wait_ready` 2s 轮询会放大其 stats 扇出——其承诺 W3 前做轻量化/短缓存;联调窗口注意 stats 端点限流(60/min)。

## 注意

- 需要依赖:`httpx`(核心依赖,随 `pip install -e .` 安装);dev venv 重建后即可本地跑;
- `p0`/`p1` 标记已注册于 `pyproject.toml [tool.pytest.ini_options] markers`;
- 场景物料使用每次运行唯一的 `ZZCONTRACT…` 标记,不依赖实现方语料,不清理数据(项目隔离即可)。
