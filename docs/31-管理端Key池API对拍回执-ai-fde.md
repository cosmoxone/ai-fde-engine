# 管理端 Key 池 API 对拍回执（ai-fde → kb-os，W4 收尾）

> 版本：**v1.0** | 日期：2026-09-19 01:45 | 状态：**对拍完成**——admin API 域全过；
> knowledge 域发现 1 高危隔离缺口（F1）+ 1 运维陷阱（F2）+ 1 规格澄清（C1），待 kb-os 裁决
> 对拍对象：kb-os《24-管理端Key池API规格》v1.1 定版（M1 已实现，commit 4eeb04a W16b）
> 我方依据：[30-管理端Key池API评审回复](30-管理端Key池API评审回复-kb-os.md) · 契约 14 号 v1.2
> 测试载体：`ee/tests/test_kb_pool.py`（桩 19 例 + 真机 5 例，真机由 `KB_ADMIN_BASE_URL/KB_ADMIN_TOKEN` 门控）

---

## 1. 对拍环境（可复现）

- **隔离实例**：kb-os 仓库源码 `main.py --port 8013`（不动共享实例 8010——其镜像 09-18 19:15 构建，
  早于 M1 提交，仍为 M0 代码）；**内存轨** keystore（无 PG，管理端点可用、重启即失——对拍专用形态）
- 关键 env：`KBGW_AUTH_DEV=false`（**必须**——默认 dev 模式下无凭据 dev-user 直通 key 管理面，
  40101/40301 全是假绿灯）；`KBGW_TENANT_KEY_QUOTA=2`（验 40302）；
  `KBGW_WK_EMBED_MODEL_ID=builtin-embedding-embo01` + `KBGW_WK_LLM_MODEL_ID=builtin-llm-minimax-m3`
  （**两个都要**，见 F2）；WeKnora 指向既有 8080 实例
- 委派链真实验证：admin（env 引导轨）→ 签发 tenant-admin（ns=te）→ 发放下游 `te-{org}-p{N}` key →
  以该 key 走 **CE 生产客户端 KbOsGateway** 完成 knowledge 全链

## 2. 结果矩阵（24 号 §4.2 对拍面）

| 对拍项 | 期望 | 结果 |
| --- | --- | --- |
| M0 基线：发放→清单→回收→40401 | 全通 | ✅ |
| 委派发放：tenant-admin(ns=te) 发 `te-acme-*` read/write | kbos-{name}-{24hex} 一次性明文 | ✅ |
| 提权拦截：发 `read+admin` / `read+tenant-admin` | 40301（子集律） | ✅ ×2 |
| 越命名空间发放：tenant_id=other-x | 40301 | ✅ |
| 配额：第 3 把（quota=2） | 40302（先 count 后 mint） | ✅ |
| 清单锁域：tenant=te-acme 过滤 | 仅本域、无明文字段 | ✅ |
| 清单越域过滤：tenant=other-x | ~~空清单~~ → **40301 显式拒绝** | ✅（澄清 C1，见 §3） |
| 越租户回收：DELETE 他人 key | 40401（不泄露存在性） | ✅ |
| 回收幂等：重复 DELETE | 40401 | ✅ |
| 未认证/错 key | 40101 | ✅ |
| **检索通**：发放的项目 key 入库→检索命中标记→stats | 全链 | ✅（chunks 秒级可检索） |
| 回收即失效：同 key 再检索 | 40101（内存轨即时；PG 轨 ~30s 窗口为既知语义） | ✅ |
| 隔离反例：零挂载新 key 检索他人项目 | 不得命中 | ❌ **F1（见 §3）** |

**admin API 域结论：M0/M1 语义与 24 号 v1.1 规格一致，全过——TE 可切换 `KBOS_ADMIN_M1_PARAMS=1`。**

## 3. 发现项（待 kb-os 裁决）

### F1【高危·契约 14 域】零挂载 principal 检索 = 全网库扇出（跨租户数据暴露）

- **现象（铁证）**：全新 key（te-pairiso2，从未入库）检索命中**另一租户**（te-pairkb）的文档
  （`PAIRKB-MARKER-*` 4 条）；首轮 xfail 用例曾因扇出超时假阴性，手动复 probe 稳定复现。
- **代码定位**：`kbgw/retrieval/service.py::_engine_kb_ids`（零挂载 → None）×
  `kbgw/retrieval/engine_weknora.py::resolve_kb_ids(None)` → `all_ids[:MAX_KB_FANOUT]`（全网）。
  fetch 注释已写"默认收敛到项目双库（决策 2）"，但 `resolve_project_kb_ids(...) or None` 的
  **`or None` 把"项目无库"翻转回全网扇出**——疑为笔误级缺口。
- **影响**：TE 场景下新发 key 在首次入库前可读平台上**所有租户**的知识库——隔离红线。
- **修复建议（一行级）**：删 `or None`（项目无库 → 空集 → "引擎无可检索知识库"）；
  或 kb-os 默认挂载自有库。**TE M3 前必须闭环**；在此之前 TE kb_pool 兜底：发 key 后
  首次检索前强制完成一次入库/挂载（已在 kb_pool 待办）。
- 我方测试留证：`test_real_isolation_fresh_key_scoped`（xfail 非严格；持续 XPASS 即已修复）。

### F2【中·运维陷阱】ensure_kb 模型绑定要求 LLM+Embed 双配，配一半=静默卡死

- `engine_weknora.py::ensure_kb`：`if cfg.weknora_llm_model_id and cfg.weknora_embed_model_id:`
  才绑定——只配 embed 时**静默跳过绑定**，新库文档永久 `is_processing`（parsing=1 不收敛、
  无 parse_failed、无日志）。代码注释自认"否则解析卡 processing（POC 实测坑）"。
- 对拍首轮"检索通"失败即由此而来（我方实例漏配 LLM 模型 id）。
- 建议：半配置启动 fail-fast 或建库时告警；文档写明"双配缺一不可"。

### C1【规格澄清·已按实现定版】tenant-admin 按域外租户过滤清单 → 40301

- 24 号 §3.3"tenant-admin 强制锁定自身命名空间"存在两种解读（静默夹紧返回空 vs 显式拒绝）；
  实现=**40301"越权：tenant 超出命名空间 te 的管辖域"**。更透明，我方接受并已按此断言。
- 建议 kb-os 将此句补进 24 号正文消歧。

### 附带：对拍残留

- 首轮无模型绑定的失败对拍在 WeKnora 留下数个永久 processing 的僵尸库
  （kbos-project-te-pairdbg*/pairflow*/pairkb*）——kb-os 无删库 API，请提供清理口径或代清。

## 4. 我方状态与移交

- `ee/src/saas/kb_pool/` M0 已在用、M1 参数门控就绪——**对拍通过后即可 `KBOS_ADMIN_M1_PARAMS=1`**
  （存量 key 回填脚本随 kb-os M1 交付，24 号 §4.1-Q2-(a)）
- 全量回归：`pytest tests ee/tests` **606 passed**（注意顺序：ee 在前会触发 settings
  lru_cache 跨目录污染——既知口径，见 0918 复盘坑 3 同族）
- 待 kb-os：F1 修复（M3 前）/ F2 建议 / C1 正文消歧 / 僵尸库清理
- 待 TE：F1 未修期间的 kb_pool 兜底（首检前强制入库）；M3 运营化时明文 key 列加密（PG+KMS）

## 5. 一句话

**admin API 域一次对拍全绿、M1 提前就绪名副其实；但"检索通"用例顺手扯出一个跨租户隔离
缺口（`or None` 一行级修复）——对拍的价值从来不止于验证承诺，更在于把"没人问过的路径"走一遍。**

---

## 6. W17a 复检记录（2026-09-19 15:07，对应 kb-os 27 号知会 + 规范 v1.1）

**环境**：隔离实例切 W17a 口径 `KBGW_TENANCY=multi`（配额 4）；全量 `pytest tests ee/tests`
606 passed；真机 21 passed + 2 xfailed（F4/F3 留证）。

| 项 | 结果 |
| --- | --- |
| 平台规范 v1.1（R1-R7 处置） | ✅ 确认——§3 私域默认不可见重写 / §2.2 补 multi×private 人类凭证（TE local 为首个实例）/ 40303 预留，全部采纳到位 |
| admin M1 契约（W17a 后回归） | ✅ 全矩阵仍绿（40301×3/40302/40401/40101/幂等/锁域），矩阵用例已泛化任意配额 |
| R1 私域隔离语义（同租户跨项目不可见） | ✅ 手动链路验证成立（p2 查 p1 私域标记零命中） |
| **F3（新·高）项目键看不到租户共享库** | ❌ `retrieval/service.py::_engine_kb_ids` 默认链早退：`if project_ids: return project_ids`——有自有库的项目 key 拿不到 shared 集，仅零库 key 落到 shared 分支。违背贵方 27 号"te-{org} 键天然可见 org 共享库"承诺与规范 v1.1 §3 意图（缺省链末端应 **own ∪ shared**）。**W17a 核心价值（共享域）对真实项目键不可达**；贵方 154 绿疑缺"有自有库的项目键见共享"正例（我们两个 xfail 探针此前都被零库路径误导） |
| **F4（~~新·高~~已撤回，见 §7）F1 在 multi 口径下回归** | ~~隔离红线失效~~ **16:xx 复检撤回**：现行 fetch 已正确区分 `None`/`[]`（`[]→引擎无可检索知识库`）；干净 multi 实例 3×复测 + 全量 1 xpassed 无泄漏。15:3x 那次 xfail 为长寿命实例状态残留（不可复现），本人曾误引 F1 时期旧代码作根因——**F4 不成立**。隔离探针转回"修复留证"常态位（当前 xpass=已修复态） |

**修复建议**（均在贵方仓，两行级）：F3 改 `return sorted(set(project_ids) | vis["shared"])`（multi 分支）；
F4 改 `if kb_ids is None:`（严格判 None，空列表=空集合法语义）。
**建议 F3/F4 修复合入后再重建共享 8010**（当前 8010 仍是 09-18 19:15 旧镜像，正好赶上）。
两用例已 xfail 留证（`test_real_w17a_tenant_visibility` / `test_real_isolation_fresh_key_scoped`），
修复后持续 XPASS 即可转正。

## 7. 对 kb-os 27 号 §5（W17a/W17b 知会）的回应（2026-09-19 18:30）

> 前提说明：贵方 §5（15:30）先于我方 §6（15:35）成文，两边并行——本节按贵方四点逐条回应，
> 并含 §6 的 F4 撤回更正。

1. **multi 口径 ✓ / "首检兜底可撤" ✗（F3 未修，兜底继续保留）**：`KBGW_TENANCY=multi`
   已验证（干净实例全量 21 passed）。但"新 key 缺省可见租户共享库"只对**零库 key** 成立——
   有自有库的项目 key（真实生产形态）因 `_engine_kb_ids` 早退（`if project_ids: return
   project_ids`，service.py:130）**仍看不到租户共享库**（F3，复测维持 xfail）。贵方 154 绿
   疑只覆盖零库→shared 路径；建议补"有自有库的项目键见 te-{org}-shared"正例。**修复前
   我方 kb_pool"首检前强制入库"兜底不撤**（撤了 = 项目键连 own 库检索都丢失 shared 补齐——
   现状 own 可见、shared 不可见，兜底无增益但无害，保留至 F3 修复后一并验证撤销）。
2. **W17b 验签核心收到**：TE M1（CASDoor 对接）后联调，permission→scopes 建模落地时按
   规范 §6（R4 分层前提）回写，双方 review。
3. **8010 重建 ✓**（镜像 15:15 实证）：admin M1 面 OK；注意其携带 F3 未修——不影响当前
   对拍/联调（共享域消费在 TE M3），但 F3 修复后需再滚动一次。
4. **夹具确认**：`te-w17*` / `te-pkb*` 前缀库确为我方对拍夹具（W17a 可见性用例/检索通用例），
   **一次性残留，请贵方径用 cleanup 脚本清理**（同批如有 `te-dbg*`/`te-pairdbg*`/
   `te-pairflow*` 亦为我方调试残留，一并清）。我方后续对拍改用每轮唯一 org + 隔离实例，
   不再在共享引擎留夹具。
5. **F4 更正致歉**：§6 所报"F1 在 multi 口径回归"经干净实例 3×复测**不成立**（现行 fetch
   正确区分 None/[]）——根因归因误引了 F1 时期旧代码，前述 xfail 系长寿命实例状态残留。
   唯一真实遗留为 **F3**（一行级：multi 分支改 `own ∪ shared`）。

## 8. F3 修复验证记录（2026-09-19 18:41，全闭环）

- kb-os d796f4d：multi 缺省链改 **own ∪ shared 并集**（引用本文件 §7-1）+ 规范 §3 消歧 + 夹具清理 + 8010 再滚动（镜像 18:35 实证）
- TE 隔离实例（KbgwTenancy=multi）复测：**23 passed**——w17a 可见性（项目键见共享/不见他人私域）与 isolation（零库 key 不泄漏）双双转正为正式回归位（去 xfail，回归直接红）
- **O3 全链闭环**：规格（24 号 v1.1）→ 实现（M1+W17a/W17b）→ 对拍（本文）→ 平台规范（v1.1 R1-R7）→ 三轮发现（F1/F2/C1/F3，F4 误报已撤）全部修复验证
- kb_pool"首检前强制入库"兜底：**可撤窗口开启**（TE M3 开发时撤并跑回归；撤前无害）
