#!/usr/bin/env python3
"""兼容入口：aifde CLI 已迁移至 src/cli.py（v0.1.4 打包布局）"""

from src.cli import build_parser, main  # noqa: F401

if __name__ == "__main__":
    main()
