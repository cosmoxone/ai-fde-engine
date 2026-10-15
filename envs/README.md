# 环境体系（local / preview / dev / test / prod × CE / TE）

> 统一入口：**`envs/run.sh`**（用法：`envs/run.sh <环境> <ce|te> <up|down|restart|ps|logs|seed>`）
> 环境定义文件：`envs/<环境>.env`（端口/认证/数据目录/外部依赖——可本地覆写不改脚本）

## 环境矩阵

| 环境 | 用途 | CE 端口 | TE 端口 | 形态 | 数据 | 认证 | 外部依赖 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **local** | 灵活本地快速开发验证（热改源码） | 8021 | 8012 | 源码 uvicorn（.venv） | `data_local_*`（可携） | CE=单用户；TE=local 多用户（激活码） | 无 |
| **preview** | 验证分支特性（干净库，不污染 local） | 8022 | 8016 | 源码 uvicorn（切分支后 `up`） | `data_preview_*`（可弃） | 同 local | 无 |
| **dev** | 完整本地自测+远端组件（CI 口径同此） | 8000 | 8014 | docker compose 栈 | 具名卷（持久） | TE=CASDoor@17100；CE=本地多用户 | CASDoor；kb-os 可选（KBOS_ADMIN_*） |
| **test** | 独立完整系统测试（一次性+自动 seed） | 8024 | 8027 | 源码 uvicorn（隔离 DATA_DIR） | `data_test_*`（重建即弃） | 同 local（TE 走 M0 直跑档） | 无（embedded 对等模式） |
| **prod** | 生产（**不在本机起**） | 运维定 | 运维定 | compose 生产模板 | 备份卷 | CASDoor 域名+正式 org | 全量（见各 README 生产清单） |

## 现存实例归属（2026-09-20 起）

| 实例 | 归属 | 说明 |
| --- | --- | --- |
| ce-standalone 栈 @8000 | **dev-ce** | compose（deploy/ce-standalone），已带 demo 数据 |
| te-saas 栈 @8014 + casdoor@17100 | **dev-te** | compose（ee/deploy/te-saas），已带 demo 数据 |
| 源码直跑 @8012 + casdoor@17000 | **local-te**（历史 dev 实例，保留） | 旧调试栈；17000 CASDoor 为 M1 联调建 |
| kbos-gateway @8010 | kb-os 共享实例（非本仓环境） | 不动 |

## 常用命令

```bash
envs/run.sh local ce up        # 源码快速起 CE（单用户，改码即生效需 restart）
envs/run.sh local te up        # TE 本地多用户直跑（激活码见 local.env）
envs/run.sh preview te up      # 切到 feature 分支后起干净库验证
envs/run.sh dev te ps          # 查看 compose 栈（8014）
envs/run.sh test te up         # 独立系统测试实例（自动 seed，embedded 模式全功能）
envs/run.sh test te seed       # 重放演示数据（幂等）
envs/run.sh <env> <form> down  # 停（源码形态按 PID 精确停；compose 形态 down）
```

## 纪律（对齐复盘 P-3/坑 17）

- 源码形态一律 **nohup 后台 + PID 落 `envs/run/<tag>.pid` + 日志 `envs/run/<tag>.log`**——超时/退出后可精确核对清理
- test 环境数据目录可随时整删（`rm -rf data_test_*`）；local 数据可携；dev 数据在卷（down 不丢）
- prod 只做 `run.sh prod <form> config`（校验 env 完整性并打印清单），不起容器
