# 贡献指南

感谢您考虑为 AI-FDE Engine 贡献代码！

## 开发环境搭建

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/<your-fork>/ai-fde-engine.git
cd ai-fde-engine

# 2. 安装最小核心依赖（Mock 模式可运行全部功能）
pip install -r requirements-core.txt
pip install -e ".[dev]"

# 3. 验证环境（330 个测试应全部通过）
pytest tests/ -v

# 4. 启动开发服务器
make dev
```

> 也可使用 `requirements.txt` 安装全量依赖（含 Docling/DeepEval/Mem0 等真实组件），
> 详见 [docs/05-模块切换指南.md](docs/05-模块切换指南.md)。

## 分支规范

- `main`：稳定分支，始终保持测试通过
- `feature/<功能名>`：新功能分支，如 `feature/memory-consolidation`
- `fix/<问题名>`：缺陷修复分支，如 `fix/benchmark-ratio`
- `docs/<文档名>`：文档改进分支

## 提交信息规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```
<type>(<scope>): <subject>

feat(agent): 新增记忆巩固 Capability
fix(evaluator): 修复幻觉率门禁方向判断
docs(readme): 更新项目结构图
test(api): 补充审核工作台接口测试
refactor(memory): 抽取记忆合并排序逻辑
```

常用 type：`feat` / `fix` / `docs` / `test` / `refactor` / `perf` / `chore`

## 代码质量要求

提交 PR 前请确保以下检查全部通过：

```bash
make lint          # ruff 代码检查 + 格式校验
make format        # ruff 自动格式化（如有需要）
make test          # 全量测试通过（330 个）
make type-check    # mypy 类型检查
```

要求：

- **测试**：新增/修改功能必须附带测试；保持 `pytest tests/ -v` 全绿
- **类型注解**：公共函数、类必须有完整类型注解
- **Mock 优先**：新外部依赖必须提供 mock 降级实现，保证核心依赖下可运行
- **文档**：新增配置项请同步更新 README 配置表与 `deploy/.env.example`
- **需求追踪**：涉及 F 编号功能的改动，请同步更新 `docs/08-测试用例追踪矩阵.md`

## PR 流程

1. 从 `main` 拉取最新代码创建特性分支
2. 开发并完成上述质量检查
3. 提交 PR，描述：改动内容、关联需求编号（如 F4.1）、测试方式
4. 等待 CI 通过 + 至少一名维护者 Review
5. 合并后删除特性分支

## 报告问题

提交 Issue 请包含：

- 问题描述与复现步骤（curl 命令或操作路径）
- 预期行为 vs 实际行为
- 环境信息（Python 版本、部署方式、`.env` 中非敏感配置）
- 日志片段（注意脱敏，勿粘贴 API Key）

## 行为准则

- 保持专业与尊重，对事不对人
- 讨论聚焦技术与事实
- 安全漏洞请勿公开 Issue，参见 [SECURITY.md](SECURITY.md)
