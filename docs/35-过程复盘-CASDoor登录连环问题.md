# 过程复盘：CASDoor OIDC 登录连环问题（三层递进）与容器化 OIDC 部署经验

> 版本：v1.0 | 日期：2026-09-21 | 覆盖时段：2026-09-20 15:00 → 09-21 15:30（约 1 天）
> 上下文：TE SaaS compose 栈（8014 + CASDoor@17100）部署后，用户浏览器登录反复失败
> 面向：人类同事 + agent（含可执行纪律）
> 一句话：**三层独立故障叠加在同一登录流上，每层修完暴露下一层——本质是"OIDC 是浏览器
> ↔IdP↔应用三方协作，任何一方的网络可达性/路由面/接口面不完整都会断链，且断点不报真相**。

---

## 1. 问题全貌（三层递进）

```
浏览器 ────①②③──→ TE@8014（/api/v1/auth/login → /oidc/callback）
   │                        │④⑤
   └───⑥──→ CASDoor@17100──┘（authorize → SPA 登录 → 回调）
```

| 层 | 用户看到的症状 | 根因 | 修复 | 确认证据 |
| --- | --- | --- | --- | --- |
| **L1 路由层** | 跳 CASDoor 后回来报 `{"detail":"未登录（CASDoor 会话缺失或已过期）"}` | CE `auth_guard` 全局中间件的白名单只有 local 登录三件路径，**不认识 TE 的 `/oidc/callback`** → 回调在守卫层就被 401，code 根本没进换码逻辑 | `_PUBLIC_EXACT` 补 `/api/v1/auth/oidc/callback` | 假 code 请求从"未登录"变为"invalid_grant"（证明到达了换码层） |
| **L2 网络层** | 同样报错（两种路径都试了） | CASDoor `origin = http://casdoor:8000`（容器内网名）→ SPA 登录成功后的跳转指向浏览器解析不了的地址 → 用户手动导航回 8014 时无会话 | origin 改为 docker 网关地址 `http://172.29.0.1:17100`（浏览器+服务端双可达）；compose 固定子网防 IP 漂移 | 程序化验证：CASDoor 会话建立（get-account=ok）、authorize 带 code 参数 |
| **L3 接口层** | 还是报错（第三轮） | 回调已成功（日志 307 ✓、项目 200 ✓）但 **`/api/v1/auth/me` 返回 404**——casdoor provider 只有 login/callback/logout 三路由，没有 `/me`；Dashboard JS 检测 `!r.ok` → 重新跳登录 → 死循环 | casdoor `login_routes()` 补 `/api/v1/auth/me` 端点（返回当前用户+项目角色） | Bearer 验证 `/me` 200（含 project_roles） |

**关键认知**：L1 修复后 L2/L3 其实同时存在——只是 L1 挡在最前面。每层修完暴露下一层，
用户看到的症状几乎一样（"还是不行"），极易误判为"修了没用"。

## 2. 排查过程（方法论）

| 步 | 动作 | 产出 |
| --- | --- | --- |
| 1 | 精读用户报错串原文 + 定位代码出处（`current_user` line 170） | 确定报错来源是守卫而非回调 |
| 2 | 程序化复现：带 state cookie 打 callback | 复现 401"未登录"→证明路由面被拦 |
| 3 | 读 `auth_guard` 源码 + `_PUBLIC_EXACT` 白名单 | 白名单缺路径（L1 实锤） |
| 4 | L1 修后，程序化走 CASDoor dance（login→authorize→callback） | 发现 authorize 200 不回跳（SPA 事实，程序模拟不了） |
| 5 | 检查 origin 与端点一致性问题 | origin=容器内网名（L2 实锤） |
| 6 | L2 修后，查 docker logs——**日志是金** | 回调 307 ✓ 但 `/auth/me` 404（L3 实锤） |
| 7 | L3 修后，Bearer 验 `/me` 200 | 三层全通 |

## 3. 经验教训

### 教训 1：OIDC 部署的"三方可达性"必须画拓扑图

```
浏览器 ──→ CASDoor authorize/token（需浏览器可达：域名/端口映射）
应用容器 ──→ CASDoor JWKS/token（需容器内可达：内网/网关）
应用容器 ──→ 自身 callback（需路由守卫放行）
```

**三方任一不通都会静默断链**——错误经常不在真正的断点处冒出（L1 在守卫报 401 而非路由 404；
L3 在 Dashboard 报"未登录"而非"接口不存在"）。

### 教训 2：auth_guard 白名单是"许可制"——新增认证路由必须同步登记

CE 的全局守卫是安全性正确的设计，但**provider 替换面新增的路由不在 CE 的知识范围内**。
TE casdoor 的 login_routes 加了 `/oidc/callback`，但 CE 白名单不知道——**跨层耦合（provider
路由 vs CE 守卫白名单）没有自动保障**，是装配面漏洞。解法（长期）：守卫改为"检查路由是否
属于 provider 的 login_routes"而非硬编码清单；短期：**加路径时必须同步白名单（检查单）**。

### 教训 3：CASDoor origin 即 token issuer 即 SPA 跳转域——三者必须一致且浏览器可达

`origin` 不只是元数据：① token iss=origin → 验签 issuer 必须匹配；② SPA 登录后跳转到
origin 域 → 浏览器必须可达。容器部署的陷阱：origin 设容器内网名（`http://casdoor:8000`）
→ 服务端通、浏览器死。解法：**origin = 浏览器可达地址**（域名或网关 IP），服务端用同一地址
或分域双端点（`CASDOOR_PUBLIC_ENDPOINT`）。

### 教训 4：provider 替换的接口面必须**完整对齐**，不能只做"最小可用"

casdoor provider 一开始只实现了 login/callback/logout（OIDC 核心）+ current_user（内部协议），
但 Dashboard 消费的是 CE local provider 的**完整接口面**（含 `/auth/me`、`/auth/users` 等）。
**替换方≠完整方时，消费方每个调用都可能 404**。教训：替换面必须穷举消费方接口清单
（grep Dashboard JS/前端所有 `/api/v1/auth/` 调用）并逐一实现或显式 501。

### 教训 5：同一症状的三种不同根因——"还是不行"时要换排查维度

| 维度 | 排查法 | 本轮应用 |
| --- | --- | --- |
| 路由面 | curl 直接打路由，看响应是"未登录"还是"路由不存在"还是"参数错误" | L1（假 code 从"未登录"变"invalid_grant"证明穿透了守卫） |
| 网络面 | 从容器内 curl 外部服务，检查 DNS/代理/网络策略 | L2（容器→网关可达性） |
| 接口面 | **看服务端日志**——什么路径、什么状态码 | L3（`docker logs te-saas` 一眼看到 `/auth/me 404`） |

### 教训 6：容器代理劫持（前置轮坑 #10，本轮复现）

容器内小写 `http_proxy`（docker daemon 注入）会让 httpx/urllib 把请求发到 SOCKS 代理
（本机 7897）而非目标地址 → 502 Bad Gateway。httpx.get() 默认 `trust_env=True` 读环境
变量——**生产容器必须显式清空大小写代理变量**（compose 已固化）。

## 4. 后续注意事项（Checklist）

- [ ] **OIDC 部署五查**（新增 OIDC 形态时逐项打勾）：
  1. `auth_guard` 白名单含 `/api/v1/auth/oidc/callback`
  2. CASDoor `origin` = 浏览器可达地址（非容器内网名）
  3. TE `CASDOOR_ENDPOINT` = 服务端可达地址（与 origin 一致或用双端点分域）
  4. casdoor provider 有 `/api/v1/auth/me`（Dashboard 用户框必需）
  5. 容器内代理变量已清空（大小写六个变量）

- [ ] **provider 替换面完整性**：实现 `login_routes()` 前先 `rg "api/v1/auth" static/` 穷举
  前端消费面，逐一实现或明确 501

- [ ] **白名单同步**：CE `_PUBLIC_EXACT` 新增认证路径时，在代码注释标注来源 provider
  （哪些形态依赖此路径）

- [ ] **浏览器流程验证不可省**：程序化模拟到"SPA 面前"就会停（authorize 200 是 CASDoor
  SPA 壳，不是失败也不是成功）——**最终必须真浏览器走一遍**，无痕窗口防旧 cookie 干扰

- [ ] **docker logs 是第二双眼睛**：用户说"不行"时，先看服务端日志最后 20 行——路径×状态码
  矩阵能立刻定位断在哪一层

## 5. 本轮产出清单

| 产出 | 位置 |
| --- | --- |
| auth_guard 白名单补路径 | `src/main.py` `_PUBLIC_EXACT` |
| CASDoor origin 统一 + compose 固定子网 | `ee/deploy/te-saas/casdoor-conf/app.conf` + `docker-compose.yml` |
| 分域双端点（public/internal） | `ee/src/auth/casdoor.py` `public_endpoint` |
| `/api/v1/auth/me` 端点 | `ee/src/auth/casdoor.py` `login_routes()` |
| 换码失败硬化（502/401 干净错误） | `ee/src/auth/casdoor.py` `_exchange()` |
| 本文 | `docs/35-过程复盘-CASDoor登录连环问题.md` |

## 6. 一句话

**OIDC 登录链是三方协作的"木桶"——浏览器、IdP、应用的路由/网络/接口面缺一块就漏水，
而水不会从缺的那块流出来（它从最低的那块流出来）——所以症状在哪不重要，日志在哪才重要。**
