# AI-FDE Engine

> An AI-driven delivery engine for FDEs (Forward Deployed Engineers) — reinventing how AI solutions get delivered, with AI.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-470%20passed-brightgreen.svg)](tests/)
[![CI](https://github.com/cosmoxone/ai-fde-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmoxone/ai-fde-engine/actions/workflows/ci.yml)

**中文文档** | [English](README.en.md)

> ⚠️ **0.x status**: APIs may change before 1.0. Single-machine / single-container by design — do not expose the API to the public internet (no auth yet, see [SECURITY.md](SECURITY.md)).

## What is this?

A local-first productivity tool that runs the **entire AI delivery workflow** for forward-deployed engineers:

```
Customer docs → Research (requirements baseline w/ quantified acceptance)
             → Solution design (product/tech/validation, cross-checked)
             → Benchmark-first testing (50 cases: high-freq/edge/adversarial)
             → Delivery → Badcase collection → Nightly iteration (auto-fix
               or human-ready fix suggestions, quality-gated deployment)
             → Deliverables export (DOCX/Markdown)
```

**Core methodology**: verification-first (define acceptance before building), AI-led with human decision points, daily iteration loops, cross-project memory reuse.

## Why it's different

| | ChatGPT et al. | Dify/Coze | **AI-FDE Engine** |
|---|---|---|---|
| Full delivery lifecycle | ❌ Q&A only | ❌ app building | ✅ research→design→deliver→iterate |
| Benchmark-first / quantified acceptance | ❌ | ❌ | ✅ core feature |
| Quality gate + regression blocking | ❌ | ❌ | ✅ |
| Cross-project experience memory | ❌ | ❌ | ✅ temporal graph |
| Open source, data stays local | ❌ | partial | ✅ MIT |

## Quick start

**Docker (recommended)**:

```bash
docker run -d --name aifde -p 8000:8000 -v aifde-data:/app/data \
  ghcr.io/cosmoxone/ai-fde-engine:latest
# open http://localhost:8000/dashboard → paste your DeepSeek/Qwen key (hot-reload, no restart)
```

**Local**:

```bash
git clone https://github.com/cosmoxone/ai-fde-engine.git && cd ai-fde-engine
pip install -r requirements-core.txt   # mock mode, zero API keys needed
uvicorn src.main:app --port 8000
```

**3-minute demo**:

```bash
bash examples/run_demo.sh   # project → docs → research → benchmark → nightly iteration → deliverables in output/
```

## Highlights

- **Six agents**: Research / Design / Delivery / Project Control / Self-Service (F7) / Training (F8)
- **Industry templates** (v0.1.2): manufacturing QC, finance customer-service, government hotline packs auto-injected
- **Editable confirmation flow** (v0.1.3): AI output is a draft — your edits become the baseline and exports
- **Deliverables export** (v0.1.2): 6 document types → Word/Markdown zip
- **SQLite persistence** (v0.1.1): single file `data/aifde.db`, survives restarts
- **26 MCP tools** (v0.1.4): drive the full workflow from Claude Desktop / Cursor
- **Swappable providers**: DeepSeek/Qwen/Local LLMs, Docling, Qdrant, DeepEval, Aider, Mem0 — mock by default, one `.env` to switch ([switching guide](docs/05-模块切换指南.md))
- **450 tests**, ruff-clean, CI on 3.11/3.12 + Docker smoke

## Editions (Open-Core)

| Edition | Scope | Price |
|---|---|---|
| **Community** (this repo) | single-machine, full core features | free, MIT |
| Team / Enterprise | multi-user, shared team memory, RBAC, multi-tenant SaaS | planned — see [business plan](docs/10-商业计划.md) (Chinese) |

## Docs & Links

- [User manual](docs/11-用户手册.md) (Chinese) — 30-min full walkthrough
- [Roadmap](docs/09-后续规划.md) (Chinese) — v0.1.x series & commercial track
- [All docs](docs/) (Chinese): requirements, tech design, verification, deployment, module switching, test traceability matrix

## Contributing

PRs welcome! `pip install -r requirements-core.txt && pip install -e ".[dev]"`, then `make lint && make test`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 AI-FDE Team
