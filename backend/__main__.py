"""PyInstaller 入口（v0.2 桌面打包用）。

开发模式照旧：cd lifemgr-pwa && python -m uvicorn backend.main:app --reload --port 8765
桌面模式：LIFEMGR_DATA_DIR + LIFEMGR_FRONTEND_DIR 由 Electron 主进程注入。
"""
from __future__ import annotations

import os

import uvicorn

# 静态 import 让 PyInstaller 能追踪到 backend.main
from backend.main import app  # noqa: E402  静态引用，方便打包器追踪


def main() -> None:
    port = int(os.environ.get("LIFEMGR_PORT", "8766"))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level=os.environ.get("LIFEMGR_LOG_LEVEL", "warning"),
        access_log=False,
    )


if __name__ == "__main__":
    main()
