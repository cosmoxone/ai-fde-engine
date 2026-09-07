# 示例目录

本目录提供最小可用的示例输入，用于快速体验 AI-FDE Engine 的完整交付流程。

## 快速开始

```bash
# 1. 启动服务（Mock 模式，无需 API Key）
pip install -r requirements-core.txt
make dev

# 2. 运行端到端演示脚本（直接走 Agent 层，不依赖 HTTP 服务）
python3 demo_e2e.py

# 3. 或通过 API 体验（新开终端）
bash examples/run_demo.sh
```

## 文件说明

| 文件 | 说明 |
| ---- | ---- |
| `sample-business-doc.md` | 模拟客户业务文档（制造业质量管理手册节选），用于上传后触发调研分析 |
| `sample-badcases.json` | 模拟客户使用中的 Badcase 反馈，用于触发夜间迭代流水线 |
| `run_demo.sh` | 通过 curl 调用 REST API 跑通：创建项目 → 上传文档 → 调研 → 设计 → Benchmark → 迭代 |

## 真实业务接入

将客户的真实业务文档（PDF/DOCX/TXT）替换 `sample-business-doc.md`，
并在 `.env` 中配置 `DEEPSEEK_API_KEY` 或 `QWEN_API_KEY` 后即可获得真实 AI 输出。
组件切换详见 [docs/05-模块切换指南.md](../docs/05-模块切换指南.md)。
